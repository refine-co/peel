/**
 * Peel's submission API.
 *
 * The production version of site/tools/submit_server.py, which is the reference the Android
 * client was built and tested against. Same three endpoints, same refusal wording, same email
 * normalisation — if any of those drift apart, the app and the server disagree about identity.
 *
 *   POST /account/code    {"email","name"}        -> 204
 *   POST /account/verify  {"email","code"}        -> {"token"}
 *   POST /packs           multipart + Bearer      -> {"id"}
 *
 * Nothing here publishes anything. Every pack lands in R2 with a row in `submissions` marked
 * `waiting`, and a person decides. That is deliberate and should stay that way: an unmoderated
 * gallery is an unbounded liability for a one-person project.
 */

// Matches PackDownloader.MAX_BYTES on the client. A pack larger than this can never be
// downloaded by the app, so accepting one would publish something nobody could install.
const MAX_UPLOAD = 8 * 1024 * 1024;

// Matches PackArchive.kt.
const MAX_ENTRIES = 40;
const MAX_STICKERS = 30;
const MIN_STICKERS = 3;
// Exactly what PackArchive.kt accepts, which is the specification: a pack whose names this
// allows but that one does not is a pack the app refuses to install after it is published.
const ENTRY = /^(manifest\.json|tray\.png|stickers\/\d{2}\.webp)$/;

// A zip that expands far beyond its compressed size is a bomb, not a pack. Both numbers come
// out of the central directory, so this catches a careless archive rather than a crafted one;
// the real protection is the output cap in inflateEntry.
const MAX_RATIO = 60;
const MAX_MANIFEST_BYTES = 256 * 1024;

const CODE_TTL_MS = 15 * 60 * 1000;
const MAX_CODE_TRIES = 5;
const CODES_PER_HOUR = 5;
const SUBMISSIONS_PER_DAY = 10;

/* ---- the ceilings, so a bill cannot arrive as a surprise -------------------
 *
 * The per-account limits above stop one person being a nuisance. These stop
 * *everyone* being one, which is the case that costs money: accounts are free to
 * make, so a per-account limit alone caps nothing in total.
 *
 * R2 is the only line that can bill quietly — Workers on the free plan simply stops
 * at its daily request limit, but stored bytes keep costing past 10 GB a month. So
 * the hard one is TOTAL_STORED_BYTES, kept well under that free tier: at the
 * measured 2.7 MiB average this is roughly 3,000 packs, far more than a queue a
 * person can read, and it refuses rather than overspends.
 *
 * Raise them deliberately, never automatically.
 */
const TOTAL_STORED_BYTES = 8 * 1024 * 1024 * 1024;   // 8 GiB of the 10 GB free
const GLOBAL_SUBMISSIONS_PER_DAY = 200;
const GLOBAL_CODES_PER_DAY = 500;

/* ---- passwords -------------------------------------------------------------
 *
 * Optional, and deliberately not the only way in. The six-digit code by email
 * stays: it is how a first account is made, and it is the reset path, so a
 * forgotten password locks nobody out and there is no "security question" to
 * get wrong.
 *
 * PBKDF2-HMAC-SHA256, because it is what WebCrypto gives a Worker — bcrypt and
 * argon2 are not available here. The iteration count is stored per account, so
 * raising it later does not invalidate anybody's existing password.
 */
/** Who the code comes from. See the note in sendCode for why it is not on peel.refineco.app. */
const SENDER = "Peel <peel@refineco.app>";

const PW_ITERATIONS = 100_000;
const PW_MIN = 8;
const SIGNIN_TRIES = 8;

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return refuse(405, "No such thing here.");
    const { pathname } = new URL(request.url);
    try {
      if (pathname === "/account/code") return await accountCode(request, env);
      if (pathname === "/account/verify") return await accountVerify(request, env);
      if (pathname === "/account/signin") return await accountSignin(request, env);
      if (pathname === "/account/password") return await accountPassword(request, env);
      if (pathname === "/account/delete") return await accountDelete(request, env);
      if (pathname === "/packs") return await packs(request, env);
    } catch (e) {
      // Never leak an internal message to a phone. The client turns a 5xx into "could not
      // reach Peel", which is the right thing for somebody to see.
      console.error(e);
      return new Response(null, { status: 500 });
    }
    return refuse(404, "No such thing here.");
  },
};

/* ---------------------------------------------------------------- accounts */

async function accountCode(request, env) {
  const body = await json(request);
  const address = field(body, "email");
  const name = field(body, "name").slice(0, 60).trim();
  if (!address || !name) return refuse(400, "A name and an email are needed.");
  const email = normalise(address);
  if (!email.includes("@")) return refuse(400, "That email does not look right.");

  const now = Date.now();
  const hourAgo = now - 60 * 60 * 1000;
  const dayAgo = now - 24 * 60 * 60 * 1000;

  // Counted from `code_requests`, one row per ask. The obvious query — COUNT over `codes` —
  // can only ever answer 0 or 1, because that table's primary key is the address: the ceiling
  // it was meant to enforce never fired, and an address could be sent an unlimited number of
  // messages, each of which also reset the guess counter on the code and on the password.
  const recent = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM code_requests WHERE email = ? AND at > ?"
  ).bind(email, hourAgo).first();
  if ((recent?.n ?? 0) >= CODES_PER_HOUR) return refuse(429, "Too many codes asked for. Wait a while.");

  // The endpoint needs no account, so it is the cheapest thing to abuse: every call is a
  // request and a message. Counted across everybody, and counting codes rather than accounts
  // created — asking repeatedly for one existing address creates no account at all.
  const today = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM code_requests WHERE at > ?"
  ).bind(dayAgo).first();
  if ((today?.n ?? 0) >= GLOBAL_CODES_PER_DAY) {
    return refuse(429, "Peel is busy today. Try again tomorrow.");
  }

  const code = String(crypto.getRandomValues(new Uint32Array(1))[0] % 1000000).padStart(6, "0");

  // Sent before it is stored, and nothing here is caught. A send that fails must leave no
  // trace: storing first meant five failed attempts locked an address out for an hour over
  // messages that were never sent, and left an account behind for somebody who has no way in.
  // The other order is worse in only one way — a code that arrives and then fails to store,
  // which is rarer and recoverable by asking again.
  await sendCode(env, email, code);

  await env.DB.prepare(
    "INSERT INTO codes (email, code, expires_at, tries) VALUES (?, ?, ?, 0) " +
    "ON CONFLICT(email) DO UPDATE SET code = excluded.code, expires_at = excluded.expires_at, tries = 0"
  ).bind(email, code, now + CODE_TTL_MS).run();

  // Remember the name now so verify can create the account without being told again.
  await env.DB.prepare(
    "INSERT INTO accounts (id, email, name, created_at) VALUES (?, ?, ?, ?) " +
    "ON CONFLICT(email) DO UPDATE SET name = excluded.name"
  ).bind(crypto.randomUUID(), email, name, now).run();

  await env.DB.batch([
    env.DB.prepare("INSERT INTO code_requests (id, email, at) VALUES (?, ?, ?)")
      .bind(crypto.randomUUID(), email, now),
    // Nothing else prunes this table, and it only exists to be counted.
    env.DB.prepare("DELETE FROM code_requests WHERE at < ?").bind(dayAgo),
  ]);
  return new Response(null, { status: 204 });
}

async function accountVerify(request, env) {
  const body = await json(request);
  const code = field(body, "code").trim();
  const address = field(body, "email");
  if (!address || code.length !== 6) return refuse(400, "That did not look right.");
  const email = normalise(address);
  const now = Date.now();

  const row = await env.DB.prepare("SELECT code, expires_at, tries FROM codes WHERE email = ?")
    .bind(email).first();
  if (!row || row.expires_at < now) return refuse(401, "That code has expired. Ask for another one.");
  if (row.tries >= MAX_CODE_TRIES) return refuse(429, "Too many tries. Ask for another code.");
  if (row.code !== code) {
    await env.DB.prepare("UPDATE codes SET tries = tries + 1 WHERE email = ?").bind(email).run();
    return refuse(401, "That code does not match. Check it and try again.");
  }

  const account = await env.DB.prepare("SELECT id, blocked_at FROM accounts WHERE email = ?")
    .bind(email).first();
  if (!account) return refuse(401, "Ask for a code again.");
  if (account.blocked_at) return refuse(403, "This account cannot send packs.");

  await env.DB.batch([
    env.DB.prepare("DELETE FROM codes WHERE email = ?").bind(email),
    env.DB.prepare("UPDATE accounts SET verified_at = COALESCE(verified_at, ?) WHERE id = ?")
      .bind(now, account.id),
  ]);
  return Response.json({ token: await issueToken(env, account.id) });
}

/**
 * Signing in with a password, for somebody who set one. Never the only way in — an account
 * with no password simply cannot use this, and is told to ask for a code instead.
 */
async function accountSignin(request, env) {
  const body = await json(request);
  const address = field(body, "email");
  const password = field(body, "password");
  if (!address || !password) return refuse(400, "An email and a password are needed.");
  const email = normalise(address);

  const row = await env.DB.prepare(
    "SELECT id, pw_hash, pw_salt, pw_iters, blocked_at, signin_tries FROM accounts WHERE email = ?"
  ).bind(email).first();
  // The same answer whether the address is unknown or the password is wrong, so this cannot be
  // used to find out who has an account.
  const wrong = () => refuse(401, "That email and password do not match. You can ask for a code instead.");
  if (!row || !row.pw_hash) return wrong();
  if (row.blocked_at) return refuse(403, "This account cannot send packs.");

  if ((row.signin_tries ?? 0) >= SIGNIN_TRIES) {
    return refuse(429, "Too many tries. Ask for a code by email instead.");
  }

  const hash = await hashPassword(password, row.pw_salt, row.pw_iters || PW_ITERATIONS);
  if (!sameHash(hash, row.pw_hash)) {
    // On the account, not on the code row. Writing it there let anybody who knew an address
    // spend somebody else's code tries, and left a code-shaped row with nothing in it.
    await env.DB.prepare("UPDATE accounts SET signin_tries = signin_tries + 1 WHERE id = ?")
      .bind(row.id).run();
    return wrong();
  }
  await env.DB.prepare("UPDATE accounts SET signin_tries = 0 WHERE id = ?").bind(row.id).run();
  return Response.json({ token: await issueToken(env, row.id) });
}

/** Sets or changes the password. Needs a current token, which means a code was verified. */
async function accountPassword(request, env) {
  const session = await whoIs(request, env);
  if (!session) return refuse(401, "Sign in again first.");
  if (session.blocked_at) return refuse(403, "This account cannot send packs.");
  const body = await json(request);
  const password = field(body, "password");
  if (password.length < PW_MIN) return refuse(400, `A password needs at least ${PW_MIN} characters.`);

  const salt = [...crypto.getRandomValues(new Uint8Array(16))]
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  const hash = await hashPassword(password, salt, PW_ITERATIONS);
  await env.DB.batch([
    env.DB.prepare(
      "UPDATE accounts SET pw_hash = ?, pw_salt = ?, pw_iters = ?, signin_tries = 0 WHERE id = ?"
    ).bind(hash, salt, PW_ITERATIONS, session.id),
    // Changing a password has to mean something. Every other phone is signed out; this one
    // keeps the token it arrived with.
    env.DB.prepare("DELETE FROM tokens WHERE account_id = ? AND token != ?")
      .bind(session.id, session.token),
  ]);
  return new Response(null, { status: 204 });
}

/**
 * Deleting the account, which has to mean deleting it.
 *
 * Removes the address, the name, the password, every signed-in device, and every pack still
 * waiting to be read — files and rows both. A pack already *published* is not removed here:
 * other people have downloaded it, so taking it out of the catalogue is a separate, slower
 * thing a person does, and the privacy policy says so rather than implying a button that
 * cannot deliver.
 */
async function accountDelete(request, env) {
  const session = await whoIs(request, env);
  if (!session) return refuse(401, "Sign in again first.");

  const waiting = await env.DB.prepare(
    "SELECT id FROM submissions WHERE account_id = ? AND state = 'waiting'"
  ).bind(session.id).all();

  const published = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM submissions WHERE account_id = ? AND state = 'published'"
  ).bind(session.id).first();

  await env.DB.batch([
    env.DB.prepare("DELETE FROM submissions WHERE account_id = ? AND state = 'waiting'").bind(session.id),
    env.DB.prepare("DELETE FROM votes WHERE account_id = ?").bind(session.id),
    env.DB.prepare("DELETE FROM tokens WHERE account_id = ?").bind(session.id),
    // A published pack keeps its row so the credit on the website still resolves, but it can
    // no longer be traced to a person. It is pointed at the tombstone account rather than at
    // a made-up id: `submissions.account_id` is a foreign key, so a dangling value fails the
    // whole batch — and with the files deleted first, that left somebody with their packs
    // gone and their account still there, unable to retry.
    env.DB.prepare("UPDATE submissions SET account_id = 'deleted' WHERE account_id = ?").bind(session.id),
    env.DB.prepare("DELETE FROM accounts WHERE id = ?").bind(session.id),
  ]);

  // Only now, with the rows gone for good, do the files go. A failure above leaves everything
  // intact and the phone shows an error, which is a state somebody can retry out of.
  for (const row of waiting.results ?? []) {
    await env.PACKS.delete(`${row.id}.peel`);
  }
  return Response.json({ published: published?.n ?? 0 });
}

/** The account behind a Bearer token, or null. */
async function whoIs(request, env) {
  const auth = request.headers.get("Authorization") ?? "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!token) return null;
  const row = await env.DB.prepare(
    "SELECT a.id, a.blocked_at FROM tokens t JOIN accounts a ON a.id = t.account_id WHERE t.token = ?"
  ).bind(token).first();
  // The token travels with the session so a password change can sign out every device except
  // the one asking.
  return row ? { ...row, token } : null;
}

/* ------------------------------------------------------------------- packs */

async function packs(request, env) {
  const session = await whoIs(request, env);
  if (!session) return refuse(401, "Sign in again to send this.");
  if (session.blocked_at) return refuse(403, "This account cannot send packs.");

  const declared = Number(request.headers.get("Content-Length") ?? 0);
  if (declared > MAX_UPLOAD + 64 * 1024) return refuse(413, "That pack is too big to send.");

  const day = Date.now() - 24 * 60 * 60 * 1000;
  const sent = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM submissions WHERE account_id = ? AND created_at > ?"
  ).bind(session.id, day).first();
  if ((sent?.n ?? 0) >= SUBMISSIONS_PER_DAY) {
    return refuse(429, "That is enough packs for one day. Try again tomorrow.");
  }

  // Two ceilings across everyone, checked before a single byte is read into memory. The
  // stored total counts only what is still in the bucket: a pack that has been published or
  // refused has had its object deleted by the review tool, and counting it forever turned the
  // ceiling into a ratchet that would eventually refuse every submission with nobody noticing.
  const totals = await env.DB.prepare(
    "SELECT COALESCE(SUM(CASE WHEN state = 'waiting' THEN bytes ELSE 0 END), 0) AS stored, " +
    "COALESCE(SUM(CASE WHEN created_at > ? THEN 1 ELSE 0 END), 0) AS today " +
    "FROM submissions"
  ).bind(day).first();
  if ((totals?.stored ?? 0) + declared > TOTAL_STORED_BYTES) {
    // Refusing is the right answer: the alternative is paying for storage quietly.
    return refuse(507, "Peel cannot take any more packs right now. Try again in a few days.");
  }
  if ((totals?.today ?? 0) >= GLOBAL_SUBMISSIONS_PER_DAY) {
    return refuse(429, "Peel is busy today. Try again tomorrow.");
  }

  const form = await request.formData();
  const file = form.get("pack");
  const credit = String(form.get("credit") ?? "").trim().slice(0, 60);
  const note = String(form.get("note") ?? "").trim().slice(0, 140);
  if (!(file instanceof File)) return refuse(400, "The pack was missing.");
  if (!credit) return refuse(400, "A credit name is needed.");

  const bytes = new Uint8Array(await file.arrayBuffer());
  if (bytes.byteLength === 0) return refuse(400, "Nothing arrived.");
  if (bytes.byteLength > MAX_UPLOAD) return refuse(413, "That pack is too big to send.");

  const checked = await inspect(bytes);
  if (checked.problem) return refuse(400, checked.problem);

  const sha = await sha256(bytes);
  const already = await env.DB.prepare("SELECT id FROM submissions WHERE sha256 = ?").bind(sha).first();
  if (already) return refuse(409, "That pack has already been sent in.");

  const id = crypto.randomUUID();
  // Stored before the row exists: a file with no row is rubbish a sweep can delete, while a row
  // with no file is a submission the reviewer cannot open.
  await env.PACKS.put(`${id}.peel`, bytes, {
    httpMetadata: { contentType: "application/octet-stream" },
  });
  await env.DB.prepare(
    "INSERT INTO submissions (id, account_id, credit, note, pack_name, stickers, bytes, sha256, state, created_at) " +
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'waiting', ?)"
  ).bind(id, session.id, credit, note, checked.name, checked.stickers, bytes.byteLength, sha, Date.now()).run();

  return Response.json({ id });
}

/* ------------------------------------------------------------- the archive */

/**
 * Reads the zip's central directory by hand rather than decompressing everything: the entry
 * names, the compressed sizes and the uncompressed sizes are all there, so a bomb is refused
 * before a single byte is inflated. Only `manifest.json` is actually decompressed, and only
 * after its declared size has been checked.
 */
async function inspect(bytes) {
  const eocd = findEocd(bytes);
  if (!eocd) return { problem: "That file could not be opened." };
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const count = view.getUint16(eocd + 10, true);
  if (count === 0 || count > MAX_ENTRIES) return { problem: "That does not look like a Peel pack." };

  let at = view.getUint32(eocd + 16, true);
  let manifest = null;
  let compressed = 0;
  let uncompressed = 0;
  let stickerFiles = 0;
  for (let i = 0; i < count; i++) {
    if (at + 46 > bytes.byteLength || view.getUint32(at, true) !== 0x02014b50) {
      return { problem: "That file could not be opened." };
    }
    const nameLen = view.getUint16(at + 28, true);
    const extraLen = view.getUint16(at + 30, true);
    const commentLen = view.getUint16(at + 32, true);
    const csize = view.getUint32(at + 20, true);
    const usize = view.getUint32(at + 24, true);
    const name = new TextDecoder().decode(bytes.subarray(at + 46, at + 46 + nameLen));
    if (!ENTRY.test(name)) return { problem: "That does not look like a Peel pack." };
    if (name.startsWith("stickers/")) stickerFiles += 1;
    compressed += csize;
    uncompressed += usize;
    if (name === "manifest.json") {
      // csize comes from here, the central directory, and never from the local header: a zip
      // written by Java's ZipOutputStream — which is what the app exports — uses a data
      // descriptor and leaves the local header's sizes as zero. Reading them there gives an
      // empty entry and the pack is refused for no reason.
      manifest = { offset: view.getUint32(at + 42, true), usize, csize };
    }
    at += 46 + nameLen + extraLen + commentLen;
  }
  if (!manifest) return { problem: "That does not look like a Peel pack." };
  if (uncompressed > compressed * MAX_RATIO && uncompressed > 4 * 1024 * 1024) {
    return { problem: "That file could not be opened." };
  }
  if (manifest.usize > MAX_MANIFEST_BYTES) {
    return { problem: "That does not look like a Peel pack." };
  }

  let parsed;
  try {
    parsed = JSON.parse(
      new TextDecoder().decode(await inflateEntry(bytes, manifest, MAX_MANIFEST_BYTES))
    );
  } catch {
    return { problem: "That does not look like a Peel pack." };
  }
  if (parsed?.format !== "peel-pack") return { problem: "That does not look like a Peel pack." };
  const stickers = Array.isArray(parsed.stickers) ? parsed.stickers.length : 0;
  if (stickers < MIN_STICKERS || stickers > MAX_STICKERS) {
    return { problem: `A pack needs between ${MIN_STICKERS} and ${MAX_STICKERS} stickers.` };
  }
  // A manifest that claims twelve stickers over an archive holding none is not a pack, and
  // nothing downstream looks again before it is published.
  if (stickers !== stickerFiles) return { problem: "That does not look like a Peel pack." };
  return { name: String(parsed.name ?? "").slice(0, 80), stickers };
}

function findEocd(bytes) {
  const from = Math.max(0, bytes.byteLength - 66 * 1024);
  for (let i = bytes.byteLength - 22; i >= from; i--) {
    if (bytes[i] === 0x50 && bytes[i + 1] === 0x4b && bytes[i + 2] === 0x05 && bytes[i + 3] === 0x06) {
      return i;
    }
  }
  return null;
}

/**
 * Inflates one entry. Only ever called for manifest.json.
 *
 * The compressed size is taken from the central directory, passed in, rather than from the
 * local header: a zip written with a data descriptor carries zeros there.
 *
 * [limit] bounds what comes *out*. Every size in a zip is a number the sender wrote, so the
 * declared-size check before this call proves nothing about the stream: a kilobyte that says
 * it is a kilobyte can still inflate to gigabytes and take the isolate down with it.
 */
async function inflateEntry(bytes, entry, limit) {
  const localOffset = entry.offset;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (view.getUint32(localOffset, true) !== 0x04034b50) throw new Error("bad local header");
  const method = view.getUint16(localOffset + 8, true);
  const csize = entry.csize || view.getUint32(localOffset + 18, true);
  const nameLen = view.getUint16(localOffset + 26, true);
  const extraLen = view.getUint16(localOffset + 28, true);
  const start = localOffset + 30 + nameLen + extraLen;
  const body = bytes.subarray(start, start + csize);
  if (method !== 8 && method !== 0) throw new Error("unsupported method");
  if (method === 0) return body.subarray(0, limit);
  const stream = new Blob([body]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  const reader = stream.getReader();
  const out = new Uint8Array(limit);
  let written = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (written + value.byteLength > limit) {
      await reader.cancel();
      throw new Error("entry inflates past its cap");
    }
    out.set(value, written);
    written += value.byteLength;
  }
  return out.subarray(0, written);
}

/* ------------------------------------------------------------------ pieces */

/** Must agree with AccountStore.normalise on the client. */
function normalise(email) {
  const trimmed = email.trim().toLowerCase();
  const at = trimmed.lastIndexOf("@");
  if (at <= 0) return trimmed;
  const domain = trimmed.slice(at + 1);
  let local = trimmed.slice(0, at).split("+")[0];
  if (domain === "gmail.com" || domain === "googlemail.com") local = local.replaceAll(".", "");
  return `${local}@${domain}`;
}

/**
 * Sends the code, or throws.
 *
 * Both halves of that matter. Printing the code to the console instead was a development
 * convenience with no check on where it was running, so on the deployed Worker it put every
 * sign-in code into the log stream in plain text and still answered 204 — the phone said a
 * code was on its way and none ever was. The log branch now needs DEV set explicitly, and a
 * refusal from the provider is a failure here rather than a silent success.
 */
async function sendCode(env, email, code) {
  if (!env.EMAIL) {
    if (env.DEV !== "1") throw new Error("no EMAIL binding: refusing to pretend a code was sent");
    // `wrangler dev --var DEV:1`: print it, exactly like the reference server. The binding
    // cannot deliver from a local run, and this is the only way to drive the account flow
    // from a phone without spending real sends.
    console.log(`*** code for ${email}: ${code} ***`);
    return;
  }
  // Cloudflare Email Sending, which the Workers Paid plan this already needs includes: 3,000
  // messages a month, then $0.35 per thousand. Peel sends one per account.
  //
  // The sender is on refineco.app and not on peel.refineco.app, which cannot hold the records
  // this needs: that name is a CNAME to GitHub Pages, and a name with a CNAME on it can carry
  // neither MX nor TXT. refineco.app already runs Email Routing, so a reply to this address
  // reaches a person.
  await env.EMAIL.send({
    from: SENDER,
    to: email,
    subject: `${code} is your Peel code`,
    text:
      `${code}\n\nType this into Peel to finish sending your pack. It is good for 15 minutes.\n\n` +
      `If you did not ask for it, nothing has happened and you can ignore this.`,
  });
  // Nothing is caught here on purpose. An unverified sender, a suppressed recipient or a
  // refused send throws, which becomes a 500 and the phone says it could not reach Peel.
  // Answering 204 to a message that was refused leaves somebody waiting for a code forever.
  //
  // What this cannot tell you: _dmarc.refineco.app is p=reject, sp=reject, so a send Cloudflare
  // accepts can still be rejected at the far end if DKIM is not aligned. A successful call is
  // not proof of delivery — the first real address has to be checked by hand.
}

/**
 * One field out of a parsed JSON body, as a string, or "".
 *
 * `String(x)` is a conversion, never a check: `String([])` is `""` and `String({})` is
 * `"[object Object]"`, so a caller who sends `"code": []` can satisfy a truthiness guard and
 * then match an empty stored value. Anything that did not arrive as a string is nothing.
 */
function field(body, name) {
  const value = body?.[name];
  return typeof value === "string" ? value : "";
}

async function json(request) {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

function refuse(status, error) {
  return Response.json({ error }, { status });
}

async function hashPassword(password, saltHex, iterations) {
  const salt = Uint8Array.from(saltHex.match(/../g).map((h) => parseInt(h, 16)));
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations }, key, 256
  );
  return [...new Uint8Array(bits)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Compares without leaking where two hashes first differ. */
function sameHash(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function issueToken(env, accountId) {
  const token = base64url(crypto.getRandomValues(new Uint8Array(24)));
  await env.DB.prepare("INSERT INTO tokens (token, account_id, created_at) VALUES (?, ?, ?)")
    .bind(token, accountId, Date.now()).run();
  return token;
}

async function sha256(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function base64url(bytes) {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
