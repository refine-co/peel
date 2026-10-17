-- Applied with:
--   npx wrangler d1 execute peel-submit --remote --file=migrations/0003-google.sql
--
-- Signing in becomes Google and nothing else. The emailed code and the optional password are
-- gone, and with them `codes`, `code_requests` and the three password columns. Identity is
-- Google's `sub`, which is a better key than a normalised address ever was.
--
-- Why this is a table rebuild and not ALTER TABLE: SQLite refuses ADD COLUMN when the column
-- carries UNIQUE, so the constraint has to arrive as a separate index on a table built with
-- the column already on it. Editing schema.sql migrates nothing — it is all
-- CREATE TABLE IF NOT EXISTS, so re-running it against a live database does nothing at all.
--
-- Safe to rebuild because production holds exactly one row, the tombstone. Check before
-- applying:  SELECT COUNT(*) FROM accounts;  -- expect 1
--
-- To go back: redeploy the previous Worker *and* restore the dropped columns. An app build
-- that speaks this API must not reach Play before the Worker is live.

PRAGMA defer_foreign_keys = true;

-- tokens.account_id and votes.account_id cascade on delete, and submissions.account_id is a
-- plain foreign key. Without the pragma above, dropping `accounts` either fails the batch or
-- quietly cascade-deletes every signed-in device.
CREATE TABLE accounts_new (
  id          TEXT PRIMARY KEY,
  -- No longer UNIQUE: identity is google_sub, and somebody whose Google address changes would
  -- otherwise collide with a stranger's old row and turn a sign-in into a 500.
  email       TEXT NOT NULL,
  name        TEXT NOT NULL,
  created_at  INTEGER NOT NULL,
  -- Set when the account is made. A Google-verified address is the verification; the endpoint
  -- that used to write this is gone, and without this the votes table's "an unverified account
  -- may not vote" rule would refuse everybody.
  verified_at INTEGER,
  blocked_at  INTEGER,
  -- Google's subject claim. Stable for a person across address changes, and never reused.
  google_sub  TEXT
);

-- google_sub is carried through where the column already exists, and the WHERE is a guard
-- that cannot be skipped: run a second time on a database holding real accounts, the copy
-- takes nothing, DROP removes the originals and every identity is gone. Re-running this file
-- on an already-migrated database with more than the tombstone in it now copies nothing and
-- the DROP below fails on the foreign keys, which is a loud stop rather than a silent wipe.
INSERT INTO accounts_new (id, email, name, created_at, verified_at, blocked_at, google_sub)
  SELECT id, email, name, created_at, verified_at, blocked_at, NULL FROM accounts
  WHERE (SELECT COUNT(*) FROM accounts) = 1;

DROP TABLE accounts;
ALTER TABLE accounts_new RENAME TO accounts;

-- The only legal way to get the constraint. The tombstone's google_sub is NULL and SQLite
-- allows any number of NULLs under a unique index, so it cannot collide and cannot be signed
-- into — there is no subject to match it.
CREATE UNIQUE INDEX IF NOT EXISTS accounts_google_sub ON accounts(google_sub);
CREATE INDEX IF NOT EXISTS accounts_email ON accounts(email);

INSERT OR IGNORE INTO accounts (id, email, name, created_at)
VALUES ('deleted', 'deleted@invalid', 'A deleted account', 0);

-- One row per sign-in attempt, written before the token is even looked at, counted across
-- everybody. It has to count attempts rather than accounts: a failed sign-in makes no account
-- and a returning person makes no account, so an accounts-per-day ceiling would never fire —
-- which is precisely the defect 0002 was written to repair, in a new place.
CREATE TABLE IF NOT EXISTS sign_in_attempts (
  id TEXT PRIMARY KEY,
  at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sign_in_attempts_at ON sign_in_attempts(at);

DROP TABLE IF EXISTS codes;
DROP TABLE IF EXISTS code_requests;
