/**
 * Peel's submission API.
 *
 * Signing in is Google and nothing else: the app sends an ID token, this checks it by hand and
 * answers with Peel's own bearer token. There is no password, no emailed code and no reset,
 * because Google already proves an address is real and the machinery that used to prove it
 * was where every authentication defect in this file has been found.
 *
 *   POST /account/google  {"idToken"}             -> {"token"}
 *   POST /account/delete  Bearer                  -> {"published"}
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

const SUBMISSIONS_PER_DAY = 10;

/* ---- signing in -----------------------------------------------------------
 *
 * Google's ID token is the whole of it. The six-digit code and the optional password this
 * replaced were where all three authentication defects found on 17 Oct lived, and the code
 * only ever proved an address was real — which Google tells us for nothing.
 */
const GOOGLE_CERTS = "https://www.googleapis.com/oauth2/v3/certs";
const CLOCK_SKEW_S = 60;
/** A token older than this is refused even if Google still considers it valid, which bounds replay. */
const MAX_TOKEN_AGE_S = 5 * 60;
/** How often an unknown key id may make this Worker ask Google for the key set. */
const CERT_REFETCH_MS = 5 * 60 * 1000;
/** Signed-in devices kept per account. Nothing else prunes the table. */
const TOKENS_PER_ACCOUNT = 5;

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
/*
 * Sign-in attempts, counted across everybody and written before the token is looked at. It has
 * to count attempts: a failed sign-in creates no account and a returning person creates no
 * account, so an accounts-per-day ceiling on its own would never fire — which is exactly the
 * mistake the codes limits made, and the reason this endpoint exists at all.
 */
/** The one origin allowed to read like counts from a browser. */
const SITE_ORIGIN = "https://peel.refineco.app";

const SIGN_INS_PER_HOUR = 300;
const SIGN_INS_PER_DAY = 2000;
const ACCOUNTS_PER_DAY = 200;

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return refuse(405, "No such thing here.");
    const { pathname } = new URL(request.url);
    try {
      if (pathname === "/account/google") return await accountGoogle(request, env);
      if (pathname === "/account/delete") return await accountDelete(request, env);
      if (pathname === "/packs") return await packs(request, env);
      if (pathname === "/packs/likes") return await packLikes(request, env);
      if (pathname === "/packs/like") return await setPackLike(request, env);
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

/**
 * Signing in, which is the only way an account is made.
 *
 * The app sends a Google ID token; this checks it and hands back Peel's own bearer token. There
 * is nothing else: no password, no emailed code, no reset. That is the point — codes and
 * passwords were where every authentication defect in this file has been, and Google already
 * tells us an address is real, which was the only thing the code ever proved.
 */
async function accountGoogle(request, env) {
  // Before anything. An unset variable would make the audience check `undefined !== undefined`,
  // which is false, which accepts every Google token ever minted — the hole arrives by
  // omission, not by a wrong comparison, and no happy-path test can see it.
  const audience = env.GOOGLE_WEB_CLIENT_ID;
  if (typeof audience !== "string" || !audience.endsWith(".apps.googleusercontent.com")) {
    throw new Error("GOOGLE_WEB_CLIENT_ID is not configured");
  }

  const now = Date.now();
  const hourAgo = now - 60 * 60 * 1000;
  const dayAgo = now - 24 * 60 * 60 * 1000;

  // Counted before the work, not after, and counting attempts rather than accounts: a failed
  // sign-in makes no account and a returning person makes no account, so an accounts-per-day
  // ceiling would never fire. That was the shape of the dead limits this endpoint replaces.
  const tried = await env.DB.prepare(
    "SELECT COALESCE(SUM(CASE WHEN at > ? THEN 1 ELSE 0 END), 0) AS hour, COUNT(*) AS day " +
    "FROM sign_in_attempts WHERE at > ?"
  ).bind(hourAgo, dayAgo).first();
  if ((tried?.hour ?? 0) >= SIGN_INS_PER_HOUR || (tried?.day ?? 0) >= SIGN_INS_PER_DAY) {
    return refuse(429, "Peel is busy. Try again in a while.");
  }
  await env.DB.batch([
    env.DB.prepare("INSERT INTO sign_in_attempts (id, at) VALUES (?, ?)")
      .bind(crypto.randomUUID(), now),
    env.DB.prepare("DELETE FROM sign_in_attempts WHERE at < ?").bind(dayAgo),
  ]);

  const body = await json(request);
  const claims = await readGoogleToken(env, field(body, "idToken"), audience, now);
  if (!claims) return refuse(401, "That sign-in did not work. Try again.");

  const existing = await env.DB.prepare(
    "SELECT id, blocked_at FROM accounts WHERE google_sub = ?"
  ).bind(claims.sub).first();
  // Checked before any write. An upsert would happily refresh a blocked row and hand back a
  // token, which is how blocking quietly stops meaning anything.
  if (existing?.blocked_at) return refuse(403, "This account cannot send packs.");

  if (!existing) {
    const fresh = await env.DB.prepare(
      "SELECT COUNT(*) AS n FROM accounts WHERE created_at > ?"
    ).bind(dayAgo).first();
    if ((fresh?.n ?? 0) >= ACCOUNTS_PER_DAY) {
      return refuse(429, "Peel is busy today. Try again tomorrow.");
    }
  }
  // One statement, upsert, returning the id. A plain INSERT after a SELECT that found nothing
  // loses a race with itself: a double tap or a retry after the client's timeout has both
  // requests reading "no row", both inserting, and the loser throwing a UNIQUE violation into
  // the 500 handler — which the phone shows as "could not reach Peel" on somebody's very
  // first sign-in. Their Google name or address may also have changed since last time, which
  // this refreshes either way.
  const account = await env.DB.prepare(
    "INSERT INTO accounts (id, email, name, created_at, verified_at, google_sub) " +
    "VALUES (?, ?, ?, ?, ?, ?) " +
    "ON CONFLICT(google_sub) DO UPDATE SET email = excluded.email, name = excluded.name " +
    "RETURNING id"
  ).bind(crypto.randomUUID(), claims.email, claims.name, now, now, claims.sub).first();
  const accountId = account?.id;
  if (!accountId) return refuse(401, "That sign-in did not work. Try again.");

  const token = await issueToken(env, accountId);
  // Nothing else prunes this table. Token issuance used to sit behind the code ceilings and
  // now sits behind nothing, so without this one Google account could fill D1's daily write
  // allowance by signing in in a loop, and /packs would start failing for everybody.
  //
  // The token just handed out is excluded by name rather than trusted to sort to the top:
  // several tokens can share a created_at millisecond, and the tie-break is not ours to
  // choose, so the row this request depends on could otherwise be the one deleted.
  await env.DB.prepare(
    "DELETE FROM tokens WHERE account_id = ? AND token != ? AND token NOT IN " +
    "(SELECT token FROM tokens WHERE account_id = ? ORDER BY created_at DESC LIMIT ?)"
  ).bind(accountId, token, accountId, TOKENS_PER_ACCOUNT - 1).run();
  return Response.json({ token });
}

/**
 * Google's ID token, checked by hand. Returns the claims, or null for anything at all wrong.
 *
 * Every step here is a check that has been got wrong somewhere before. The audience is what
 * stops any Google token working; the `email_verified` comparison is spelled out because
 * Google sends that claim as both a boolean and a string and `if (claim)` accepts `"false"`;
 * `exp` is in seconds while `Date.now()` is milliseconds.
 *
 * What this does NOT prove: that the Peel app sent it. The client id is not a secret — it
 * ships in the APK — and any app may ask Google for a token with it as the audience. So the
 * worst case is somebody creating an account as themselves, which is what the app does anyway,
 * and every pack is still read by a person. The `iat` age bound and the ceiling above carry
 * the rest.
 */
async function readGoogleToken(env, idToken, audience, now) {
  const parts = idToken.split(".");
  if (parts.length !== 3 || parts.some((p) => p.length === 0)) return null;

  const header = decodeSegment(parts[0]);
  const claims = decodeSegment(parts[1]);
  if (!header || !claims) return null;
  // Pinning the algorithm in importKey already defeats the classic confusion — an HMAC
  // signature will not verify against an RSA key — but checking it here turns a 500 from a
  // thrown importKey into a refusal.
  if (header.alg !== "RS256" || typeof header.kid !== "string") return null;

  const jwk = await googleKey(header.kid, now);
  if (!jwk || jwk.kty !== "RSA") return null;

  const key = await crypto.subtle.importKey(
    "jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]
  );
  const signed = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
  const signature = base64urlToBytes(parts[2]);
  if (!signature) return null;
  if (!(await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, signature, signed))) return null;

  return checkClaims(claims, audience, Math.floor(now / 1000));
}

/**
 * Everything about a token that is true or false without any cryptography.
 *
 * Split out and exported for one reason: it is the only way these checks get tested. They sit
 * after the signature check, so nothing reachable without a key Google signed with ever
 * executes them — `check.sh` can send a thousand malformed tokens and every one is refused by
 * the signature long before `aud` is compared. Deleting the audience line outright used to
 * leave the suite green. Now `node --test` runs this directly.
 *
 * Returns the fields worth keeping, or null, and never throws.
 */
export function checkClaims(claims, audience, seconds) {
  if (!claims || typeof claims !== "object") return null;
  if (typeof audience !== "string" || audience.length === 0) return null;
  if (claims.iss !== "accounts.google.com" && claims.iss !== "https://accounts.google.com") return null;
  if (typeof claims.aud !== "string" || claims.aud !== audience) return null;
  if (typeof claims.exp !== "number" || claims.exp + CLOCK_SKEW_S < seconds) return null;
  if (typeof claims.iat !== "number" || claims.iat > seconds + CLOCK_SKEW_S) return null;
  // Bounds replay: a token stays valid to Google for about an hour, and this is cheaper than
  // keeping a nonce or a seen-token table for a flow that runs once per account.
  if (seconds - claims.iat > MAX_TOKEN_AGE_S) return null;
  // Google sends this as a boolean and as a string, and `if (claims.email_verified)` accepts
  // the string "false". Spelled out for that reason.
  if (claims.email_verified !== true && claims.email_verified !== "true") return null;
  if (typeof claims.sub !== "string" || claims.sub.length === 0) return null;
  if (typeof claims.email !== "string" || claims.email.length === 0) return null;

  return {
    sub: claims.sub,
    email: claims.email.toLowerCase(),
    name: (typeof claims.name === "string" ? claims.name : "").slice(0, 60).trim() || "Someone",
  };
}

/**
 * One of Google's signing keys, by id.
 *
 * Kept in the edge cache rather than a module global, so it survives an isolate being recycled
 * and honours the max-age Google sets. A miss refetches — but at most every REFETCH_MS,
 * because the key id arrives in an unauthenticated body: without the throttle, a loop of
 * invented ids is one outbound request to Google each, until Google rate-limits this Worker
 * and real sign-ins start failing. An unknown id between refetches is simply refused, which is
 * what an invented one deserves.
 */
async function googleKey(kid, now) {
  if (certs.keys.some((k) => k.kid === kid)) {
    return certs.keys.find((k) => k.kid === kid);
  }
  // Only once we are holding a key set that is actually fresh does an unknown id mean a
  // forgery. Throttling on "we did not find it" instead refuses valid tokens: the keys were
  // held only in the edge cache, so any miss after a recent fetch — which on a workers.dev
  // subdomain is every single time, because the Cache API does nothing there — returned null
  // for a key Google had signed with minutes earlier. Retrying made it worse, not better.
  if (certs.at && now - certs.at < CERT_REFETCH_MS) return null;

  const fresh = await fetch(GOOGLE_CERTS).catch(() => null);
  if (!fresh?.ok) return null;
  const body = await fresh.json().catch(() => null);
  if (!Array.isArray(body?.keys)) return null;
  certs = { at: now, keys: body.keys };
  return certs.keys.find((k) => k.kid === kid) ?? null;
}

/**
 * Google's signing keys, held for the life of this isolate.
 *
 * A module global and not the edge cache. `caches.default` is a no-op on a workers.dev
 * subdomain, so relying on it meant the keys were never actually retained and the refetch
 * throttle fell on honest sign-ins. An isolate-local copy costs nothing, works on any host,
 * and the throttle now only applies when this is populated and recent.
 */
let certs = { at: 0, keys: [] };

function decodeSegment(segment) {
  const bytes = base64urlToBytes(segment);
  if (!bytes) return null;
  try {
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
}

/** base64url, which atob does not accept: the two characters differ and the padding is gone. */
function base64urlToBytes(text) {
  try {
    const padded = text.replace(/-/g, "+").replace(/_/g, "/")
      .padEnd(text.length + ((4 - (text.length % 4)) % 4), "=");
    const binary = atob(padded);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
    return out;
  } catch {
    return null;
  }
}

/**
 * Deleting the account, which has to mean deleting it.
 *
 * Removes the address, the name, every signed-in device, and every pack still waiting to be
 * read — files and rows both. A pack already *published* is not removed here: other people
 * have downloaded it, so taking it out of the catalogue is a separate, slower thing a person
 * does, and the privacy policy says so rather than implying a button that cannot deliver.
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
  return row ?? null;
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

/* ------------------------------------------------------------------- likes */

/**
 * How many people liked each published pack, and which of them this one did.
 *
 * POST like everything else here, because the Worker answers nothing else — see the method
 * check in fetch(). A token is optional: without one the counts come back and `mine` is
 * empty, which is what the website and a signed-out app both want.
 *
 * Counts are public. They are the only thing anybody learns: who liked what is never sent,
 * and there is no endpoint that could be asked.
 */
async function packLikes(request, env) {
  const session = await whoIs(request, env);
  const rows = await env.DB.prepare(
    "SELECT s.slug AS slug, COUNT(v.account_id) AS n FROM submissions s " +
    "LEFT JOIN votes v ON v.submission_id = s.id " +
    "WHERE s.state = 'published' AND s.slug IS NOT NULL GROUP BY s.slug"
  ).all();
  const likes = {};
  for (const row of rows.results ?? []) likes[row.slug] = row.n ?? 0;

  let mine = [];
  if (session && !session.blocked_at) {
    const own = await env.DB.prepare(
      "SELECT s.slug AS slug FROM votes v JOIN submissions s ON s.id = v.submission_id " +
      "WHERE v.account_id = ? AND s.slug IS NOT NULL"
    ).bind(session.id).all();
    mine = (own.results ?? []).map((row) => row.slug);
  }
  // The website reads this too, from a different origin, so it says who may. Only this
  // endpoint: the ones that take a token stay same-origin, because nothing in a browser has
  // any business carrying a Peel token and keeping the surface small costs nothing here.
  return Response.json({ likes, mine }, { headers: { "Access-Control-Allow-Origin": SITE_ORIGIN } });
}

/**
 * Like a pack, or take it back. `{ slug, on }`, and the answer is the pack's new count.
 *
 * Signing in is the whole gate. One like per account per pack is the primary key's job rather
 * than a check followed by an insert: two taps racing each other then cost one row, not two,
 * and there is no window between the look and the write for the second to fit through.
 *
 * A pack that is not published cannot be liked. That is not only tidiness — the slug is how
 * the app names a pack, and without the state check a guessed slug would let somebody vote on
 * a submission still in the queue.
 */
async function setPackLike(request, env) {
  const session = await whoIs(request, env);
  if (!session) return refuse(401, "Sign in to like a pack.");
  if (session.blocked_at) return refuse(403, "This account cannot do that.");

  let body;
  try {
    body = await request.json();
  } catch {
    return refuse(400, "That did not look like a request.");
  }
  const slug = typeof body?.slug === "string" ? body.slug.trim() : "";
  if (!slug || slug.length > 200) return refuse(400, "That did not look like a pack.");
  const on = body?.on !== false;

  const pack = await env.DB.prepare(
    "SELECT id FROM submissions WHERE slug = ? AND state = 'published'"
  ).bind(slug).first();
  if (!pack) return refuse(404, "No such pack.");

  if (on) {
    await env.DB.prepare(
      "INSERT OR IGNORE INTO votes (submission_id, account_id, created_at) VALUES (?, ?, ?)"
    ).bind(pack.id, session.id, Date.now()).run();
  } else {
    await env.DB.prepare(
      "DELETE FROM votes WHERE submission_id = ? AND account_id = ?"
    ).bind(pack.id, session.id).run();
  }

  const count = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM votes WHERE submission_id = ?"
  ).bind(pack.id).first();
  return Response.json({ slug, likes: count?.n ?? 0, mine: on });
}

function refuse(status, error) {
  return Response.json({ error }, { status });
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
