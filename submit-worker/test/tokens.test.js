// node --test
//
// Bearer tokens: what is stored, and how long it works for.
//
// Both of these were defects found by audit on 22 November 2026, and both are the kind that no
// happy-path test can see — the old code signed people in and let them submit packs perfectly
// well while storing the credential in plain text and honouring it forever. So these tests
// assert the two things that were wrong, not the thing that worked:
//
//   1. what reaches the database is NOT the token the phone was given
//   2. a token older than the ceiling is refused, even though its row is still there
//
// They talk to the real exported functions, never to a copy of the logic.

import { strict as assert } from "node:assert";
import test from "node:test";
import { issueToken, whoIs } from "../src/index.js";

const DAY = 24 * 60 * 60 * 1000;

/** Hex SHA-256, written out here rather than imported, so the test checks the code's work. */
async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * A stub D1 holding rows in memory.
 *
 * It applies only the filters the SQL actually asks for, and that is the whole point of it.
 * The first version of this stub filtered on hash and expiry unconditionally, whatever the
 * statement said — so deleting `AND t.created_at > ?` from the real query left all these tests
 * green. The stub was answering for the code instead of exercising it. A fake that is kinder
 * than the real engine tests nothing.
 */
function fakeDb(rows = []) {
  const writes = [];
  return {
    rows,
    writes,
    prepare(sql) {
      const statement = {
        args: [],
        bind(...args) { statement.args = args; return statement; },
        async run() { writes.push({ sql, args: statement.args }); return { success: true }; },
        async first() {
          // Read the placeholders in the order the statement declares them, exactly as D1 binds.
          const wantsHash = /token_hash\s*=\s*\?/.test(sql);
          const wantsFloor = /created_at\s*>\s*\?/.test(sql);
          let i = 0;
          const hash = wantsHash ? statement.args[i++] : undefined;
          const floor = wantsFloor ? statement.args[i++] : undefined;

          const row = rows.find((r) => {
            if (wantsHash && r.token_hash !== hash) return false;
            if (wantsFloor && !(r.created_at > floor)) return false;
            return true;
          });
          return row ? { id: row.account_id, blocked_at: row.blocked_at ?? null } : null;
        },
      };
      return statement;
    },
  };
}

const bearer = (token) =>
  new Request("https://peel-submit.refineco.workers.dev/packs", {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

test("the token handed out is never the value stored", async () => {
  const DB = fakeDb();
  const { token, hash } = await issueToken({ DB }, "account-1");

  assert.equal(DB.writes.length, 1);
  const stored = DB.writes[0].args[0];
  assert.notEqual(stored, token, "the plaintext token reached the database");
  assert.equal(stored, hash);
  assert.equal(stored, await sha256Hex(token));
  assert.match(stored, /^[0-9a-f]{64}$/);
  // And the column it goes into is the hash column, not the old one.
  assert.match(DB.writes[0].sql, /token_hash/);
  assert.doesNotMatch(DB.writes[0].sql, /\(token,/);
});

test("a fresh token authorises, and the database is searched by hash", async () => {
  const token = "pretend-this-came-from-a-sign-in";
  const DB = fakeDb([
    { token_hash: await sha256Hex(token), account_id: "account-1", created_at: Date.now() },
  ]);
  assert.deepEqual(await whoIs(bearer(token), { DB }), { id: "account-1", blocked_at: null });
});

test("a token older than the ceiling is refused, row and all", async () => {
  const token = "old-but-still-in-the-table";
  const DB = fakeDb([
    {
      token_hash: await sha256Hex(token),
      account_id: "account-1",
      // 91 days: one day past TOKEN_TTL_MS. The row exists; that is the point.
      created_at: Date.now() - 91 * DAY,
    },
  ]);
  assert.equal(await whoIs(bearer(token), { DB }), null);
});

test("a token just inside the ceiling still works", async () => {
  const token = "eighty-nine-days-old";
  const DB = fakeDb([
    { token_hash: await sha256Hex(token), account_id: "account-1", created_at: Date.now() - 89 * DAY },
  ]);
  assert.equal((await whoIs(bearer(token), { DB }))?.id, "account-1");
});

test("the stored hash is not accepted as a token", async () => {
  // Somebody who reads the database gets hashes. Presenting one must not sign them in, or the
  // hashing would be decoration.
  const token = "the-real-one";
  const hash = await sha256Hex(token);
  const DB = fakeDb([{ token_hash: hash, account_id: "account-1", created_at: Date.now() }]);
  assert.equal(await whoIs(bearer(hash), { DB }), null);
});

test("no Authorization header, or a bare one, is nobody", async () => {
  const DB = fakeDb([{ token_hash: await sha256Hex("x"), account_id: "a", created_at: Date.now() }]);
  assert.equal(await whoIs(bearer(null), { DB }), null);
  assert.equal(
    await whoIs(new Request("https://x/packs", { method: "POST", headers: { Authorization: "Bearer " } }), { DB }),
    null,
  );
});
