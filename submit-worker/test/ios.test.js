// node --test
//
// The iPhone waitlist, tested against the real handler rather than a copy of its regex.
//
// The thing worth protecting here is not the happy path. It is that a refusal still carries
// the CORS header — without it the page cannot read its own error and shows a blank line
// instead of a reason, which is the kind of defect that looks like "the form does nothing".

import { strict as assert } from "node:assert";
import test from "node:test";
import { iosWaitlist } from "../src/index.js";

const ORIGIN = "https://peel.refineco.app";

/** A stub D1 that records what it was asked to write and answers the day-count query. */
function fakeDb({ todayCount = 0 } = {}) {
  const writes = [];
  return {
    writes,
    prepare(sql) {
      const statement = {
        args: [],
        bind(...args) { statement.args = args; return statement; },
        async first() { return { n: todayCount }; },
        async run() { writes.push({ sql, args: statement.args }); return { success: true }; },
      };
      return statement;
    },
  };
}

const post = (body, headers = {}) =>
  new Request("https://peel-submit.refineco.workers.dev/ios/waitlist", {
    method: "POST",
    headers: { "Content-Type": "text/plain", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });

test("a good address is stored, lowercased and trimmed", async () => {
  const DB = fakeDb();
  const answer = await iosWaitlist(post({ email: "  Someone@Example.COM  " }), { DB });
  assert.equal(answer.status, 200);
  assert.deepEqual(await answer.json(), { ok: true });
  assert.equal(DB.writes.length, 1);
  assert.equal(DB.writes[0].args[0], "someone@example.com");
});

test("every answer carries the site origin, refusals included", async () => {
  const DB = fakeDb();
  for (const body of [{ email: "nope" }, { email: "fine@example.com" }, "not json"]) {
    const answer = await iosWaitlist(post(body), { DB });
    assert.equal(
      answer.headers.get("Access-Control-Allow-Origin"), ORIGIN,
      `missing on ${JSON.stringify(body)}`,
    );
  }
});

test("shapes that are not addresses are refused, and nothing is written", async () => {
  const DB = fakeDb();
  const bad = ["nope", "a@b", "no spaces@example.com", "@example.com", "two@@example.com",
              "trailing@example.", "x@y.z".slice(0, 4), "a@b.c" + "d".repeat(260), ""];
  for (const email of bad) {
    const answer = await iosWaitlist(post({ email }), { DB });
    assert.equal(answer.status, 400, `accepted ${JSON.stringify(email)}`);
  }
  assert.equal(DB.writes.length, 0);
});

test("a missing or unparseable body is a refusal, not a throw", async () => {
  const DB = fakeDb();
  assert.equal((await iosWaitlist(post("{{{"), { DB })).status, 400);
  assert.equal((await iosWaitlist(post({}), { DB })).status, 400);
  assert.equal((await iosWaitlist(post({ email: 42 }), { DB })).status, 400);
});

test("the day ceiling refuses rather than writing", async () => {
  const DB = fakeDb({ todayCount: 500 });
  const answer = await iosWaitlist(post({ email: "late@example.com" }), { DB });
  assert.equal(answer.status, 503);
  assert.equal(DB.writes.length, 0);
  assert.equal(answer.headers.get("Access-Control-Allow-Origin"), ORIGIN);
});

test("source is kept, capped, and null when absent", async () => {
  const DB = fakeDb();
  await iosWaitlist(post({ email: "a@example.com", source: "share" }), { DB });
  assert.equal(DB.writes[0].args[2], "share");

  await iosWaitlist(post({ email: "b@example.com", source: "x".repeat(99) }), { DB });
  assert.equal(DB.writes[1].args[2].length, 32);

  await iosWaitlist(post({ email: "c@example.com" }), { DB });
  assert.equal(DB.writes[2].args[2], null);
});

test("the country comes off Cloudflare's header, or is null", async () => {
  const DB = fakeDb();
  await iosWaitlist(post({ email: "a@example.com" }, { "CF-IPCountry": "MY" }), { DB });
  assert.equal(DB.writes[0].args[3], "MY");

  await iosWaitlist(post({ email: "b@example.com" }), { DB });
  assert.equal(DB.writes[1].args[3], null);
});

test("an address already on the list answers the same as a new one", async () => {
  // The INSERT is OR IGNORE, so the second write is a no-op in SQLite and the handler cannot
  // tell. That is deliberate: a different answer would say who is on the list.
  const DB = fakeDb();
  const first = await iosWaitlist(post({ email: "same@example.com" }), { DB });
  const again = await iosWaitlist(post({ email: "SAME@example.com" }), { DB });
  assert.deepEqual(await first.json(), await again.json());
  assert.equal(DB.writes[0].args[0], DB.writes[1].args[0]);
});
