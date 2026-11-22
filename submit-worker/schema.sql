-- Peel's submission database, whole, in one file.
--
--     npx wrangler d1 execute peel-submit --remote --file schema.sql
--
-- Why this exists rather than migrations/: the database this replaces was built by hand and by
-- migrations in turn, and its d1_migrations table was EMPTY — so `wrangler d1 migrations apply`
-- against it would have re-run 0002 onwards over tables that already existed, and `0001` was
-- missing from the folder entirely. A migration history that does not describe the database is
-- worse than none, because it invites exactly that command. The database was rebuilt from this
-- file on 22 November 2026; migrations/ is kept only as the record of how the old one grew.
--
-- From here on: change this file, and add a migration beside it for the change.

-- A person. Identity is google_sub, never the address: Google keeps the subject stable across
-- an address change and never reuses it, while two people can hold the same address years apart.
CREATE TABLE IF NOT EXISTS accounts (
  id          TEXT PRIMARY KEY,
  -- Not UNIQUE, deliberately. Somebody whose Google address changes would otherwise collide
  -- with a stranger's old row and turn their sign-in into a 500.
  email       TEXT NOT NULL,
  name        TEXT NOT NULL,
  created_at  INTEGER NOT NULL,
  -- A Google-verified address is the verification. Set when the account is made; without it
  -- the "an unverified account may not vote" rule would refuse everybody.
  verified_at INTEGER,
  blocked_at  INTEGER,
  google_sub  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS accounts_google_sub ON accounts(google_sub);

-- The row every deleted account's published submissions are pointed at, so the credit on the
-- website still resolves while the person behind it is gone. Not an account anybody can sign
-- in to: google_sub is NULL and no subject matches NULL.
--
-- This is load-bearing, not decoration. accountDelete() runs
--   UPDATE submissions SET account_id = 'deleted' WHERE account_id = ?
-- and submissions.account_id is a foreign key, so without this row the whole delete batch
-- fails - after the R2 objects have already gone. That leaves somebody with their packs
-- deleted and their account still present, unable to retry. It was missing for about twenty
-- minutes on 22 Nov 2026 when this file was rewritten without it.
INSERT OR IGNORE INTO accounts (id, email, name, created_at)
VALUES ('deleted', 'deleted@invalid', 'A deleted account', 0);

-- A signed-in device.
--
-- This table holds a SHA-256 of the bearer token and never the token itself. Until 22 November
-- 2026 it held the credential in plain text, which meant anyone who could read this database —
-- a leaked API token, a dashboard session, a backup in the wrong folder — could act as any
-- signed-in person. A hash is not reversible, so a copy of this table is no longer a set of
-- working sessions.
--
-- No salt, no bcrypt: the token is 24 bytes from crypto.getRandomValues. There is no password
-- to guess, so a slow hash would buy nothing and cost latency on every authorised request.
--
-- created_at is compared, not merely recorded: see TOKEN_TTL_MS in src/index.js. Writing a
-- timestamp and never reading it is how the old table let a stolen token live forever.
CREATE TABLE IF NOT EXISTS tokens (
  token_hash TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL
);
-- token_hash is the primary key, so a session lookup is already covered. This index is for the
-- three statements that go the other way: the five-device prune, the account delete, and the
-- cascade.
CREATE INDEX IF NOT EXISTS tokens_account_id ON tokens(account_id);

-- A pack somebody sent in. The file itself lives in R2 under the same id.
-- state: waiting | published | refused | withdrawn
-- Nothing here is public until a person sets state to 'published'.
CREATE TABLE IF NOT EXISTS submissions (
  id          TEXT PRIMARY KEY,
  account_id  TEXT NOT NULL REFERENCES accounts(id),
  credit      TEXT NOT NULL,
  note        TEXT NOT NULL DEFAULT '',
  pack_name   TEXT NOT NULL DEFAULT '',
  stickers    INTEGER NOT NULL DEFAULT 0,
  bytes       INTEGER NOT NULL,
  sha256      TEXT NOT NULL,
  state       TEXT NOT NULL DEFAULT 'waiting',
  reason      TEXT,
  created_at  INTEGER NOT NULL,
  reviewed_at INTEGER,
  slug        TEXT
);
-- The same pack sent twice is one row, decided by content rather than by name.
CREATE UNIQUE INDEX IF NOT EXISTS submissions_sha ON submissions(sha256);
CREATE INDEX IF NOT EXISTS submissions_state ON submissions(state, created_at);
-- Only published packs have a slug, and no two share one.
CREATE UNIQUE INDEX IF NOT EXISTS submissions_slug ON submissions(slug) WHERE slug IS NOT NULL;

-- One like per account per pack, enforced by the primary key rather than by a check followed
-- by an insert: two taps racing each other then cost one row and have no window between them.
CREATE TABLE IF NOT EXISTS votes (
  submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  account_id    TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  created_at    INTEGER NOT NULL,
  PRIMARY KEY (submission_id, account_id)
);

-- Sign-in attempts, counted across everybody, written before the token is looked at. It counts
-- attempts and not accounts on purpose: a failed sign-in makes no account and a returning
-- person makes no account, so an accounts-per-day ceiling would never fire.
CREATE TABLE IF NOT EXISTS sign_in_attempts (
  id TEXT PRIMARY KEY,
  at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sign_in_attempts_at ON sign_in_attempts(at);

-- The iPhone waitlist. Three columns and no more: an address, when, and where they came from.
-- Nothing here needs a new category in the privacy policy.
CREATE TABLE IF NOT EXISTS ios_waitlist (
  -- Lowercased on the way in, so two spellings of one address are one row. INSERT OR IGNORE
  -- against this key is the whole dedupe, with no window for a double tap to fit through.
  email      TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  -- Read off `?from=` on the page: "share" for somebody who was sent a pack and could not open
  -- it, "social" for a post, null for a direct visit. This is what makes the number actionable.
  source     TEXT,
  -- The country Cloudflare saw. Costs nothing and says whether a small list is small everywhere.
  country    TEXT
);
CREATE INDEX IF NOT EXISTS ios_waitlist_created ON ios_waitlist(created_at);
