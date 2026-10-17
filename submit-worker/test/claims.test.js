// node --test
//
// The claim checks, tested directly, because nothing else can reach them.
//
// `check.sh` drives the real endpoint, and every token it can build is refused by the
// signature long before a claim is looked at — so deleting the audience comparison outright
// used to leave that suite green at 19 of 19. These are the checks three separate defects
// have hidden in, so they get a test that actually runs them.

import { strict as assert } from "node:assert";
import test from "node:test";
import { checkClaims } from "../src/index.js";

const AUD = "1072147454316-1vfqpurdr084eabr3q87pojqv370bf3o.apps.googleusercontent.com";
const NOW = 1_760_000_000;

/** A token that should pass, so each case below can change exactly one thing. */
const good = (over = {}) => ({
  iss: "https://accounts.google.com",
  aud: AUD,
  sub: "11223344556677889900",
  email: "Someone@Example.com",
  email_verified: true,
  name: "Someone",
  exp: NOW + 3600,
  iat: NOW - 10,
  ...over,
});

test("a good token passes, and the address is lowercased", () => {
  const out = checkClaims(good(), AUD, NOW);
  assert.equal(out.sub, "11223344556677889900");
  assert.equal(out.email, "someone@example.com");
  assert.equal(out.name, "Someone");
});

test("the audience must match exactly", () => {
  assert.equal(checkClaims(good({ aud: AUD + "x" }), AUD, NOW), null);
  assert.equal(checkClaims(good({ aud: undefined }), AUD, NOW), null);
  assert.equal(checkClaims(good({ aud: null }), AUD, NOW), null);
  // The one that an unset configuration variable produces: both sides undefined, which
  // `!==` calls equal. This is the test the whole split exists for.
  assert.equal(checkClaims({ ...good(), aud: undefined }, undefined, NOW), null);
  assert.equal(checkClaims(good(), "", NOW), null);
});

test("email_verified: the string \"false\" is truthy and must still be refused", () => {
  assert.equal(checkClaims(good({ email_verified: "false" }), AUD, NOW), null);
  assert.equal(checkClaims(good({ email_verified: false }), AUD, NOW), null);
  assert.equal(checkClaims(good({ email_verified: undefined }), AUD, NOW), null);
  assert.equal(checkClaims(good({ email_verified: 1 }), AUD, NOW), null);
  // Google sends the boolean and the string, and both are a yes.
  assert.ok(checkClaims(good({ email_verified: "true" }), AUD, NOW));
});

test("the issuer must be Google, with or without the scheme", () => {
  assert.ok(checkClaims(good({ iss: "accounts.google.com" }), AUD, NOW));
  assert.equal(checkClaims(good({ iss: "https://accounts.google.com.evil.test" }), AUD, NOW), null);
  assert.equal(checkClaims(good({ iss: undefined }), AUD, NOW), null);
});

test("expiry is in seconds, with a minute of skew either way", () => {
  assert.equal(checkClaims(good({ exp: NOW - 3600 }), AUD, NOW), null);
  assert.ok(checkClaims(good({ exp: NOW - 30 }), AUD, NOW), "30s past, inside the skew");
  assert.equal(checkClaims(good({ exp: NOW - 120 }), AUD, NOW), null, "2 min past, outside it");
  // Milliseconds where seconds were meant would sail past every comparison.
  assert.equal(checkClaims(good({ exp: (NOW + 3600) * 1000, iat: NOW * 1000 }), AUD, NOW), null);
  assert.equal(checkClaims(good({ exp: "9999999999" }), AUD, NOW), null);
});

test("a token older than five minutes is refused even if Google still likes it", () => {
  assert.ok(checkClaims(good({ iat: NOW - 299 }), AUD, NOW));
  assert.equal(checkClaims(good({ iat: NOW - 301 }), AUD, NOW), null);
  assert.equal(checkClaims(good({ iat: NOW + 3600 }), AUD, NOW), null, "minted in the future");
  assert.equal(checkClaims(good({ iat: undefined }), AUD, NOW), null);
});

test("subject and address must be real strings", () => {
  assert.equal(checkClaims(good({ sub: "" }), AUD, NOW), null);
  assert.equal(checkClaims(good({ sub: undefined }), AUD, NOW), null);
  assert.equal(checkClaims(good({ sub: 12345 }), AUD, NOW), null);
  assert.equal(checkClaims(good({ email: "" }), AUD, NOW), null);
  assert.equal(checkClaims(good({ email: undefined }), AUD, NOW), null);
});

test("a missing name is not a failure, it is just blank", () => {
  // The screen leaves the credit empty and canSend refuses to send, which is the right
  // answer — better than inventing a name that gets published.
  assert.equal(checkClaims(good({ name: undefined }), AUD, NOW).name, "Someone");
  assert.equal(checkClaims(good({ name: "   " }), AUD, NOW).name, "Someone");
  assert.equal(checkClaims(good({ name: "x".repeat(200) }), AUD, NOW).name.length, 60);
});

test("nothing that is not an object gets through, and nothing throws", () => {
  for (const junk of [null, undefined, "", 0, [], "a string", true]) {
    assert.equal(checkClaims(junk, AUD, NOW), null);
  }
});
