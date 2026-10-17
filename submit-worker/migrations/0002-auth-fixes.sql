-- Applied with:
--   npx wrangler d1 execute peel-submit --remote --file=migrations/0002-auth-fixes.sql
--
-- What this repairs, all three found in review on 17 Oct 2026:
--
--  1. A failed password sign-in used to write a row into `codes` with an empty code, as a
--     place to count wrong guesses. `verify` compared the stored code against String(body.code),
--     and String([]) is "", so two unauthenticated requests — one wrong password, then
--     {"code": []} — handed out a token for any account that had set a password. The counter
--     moves onto the account, and `codes.code` now has to be six characters long.
--
--  2. Both per-address code ceilings were queries that could never fire: `codes.email` is the
--     primary key, so COUNT(*) over it is 0 or 1, and the global ceiling counted accounts
--     created rather than codes sent. `code_requests` is one row per ask, which is countable.
--
--  3. Deleting an account pointed its published submissions at account_id 'deleted', which is
--     a foreign key with nothing behind it. The tombstone row gives it something.

ALTER TABLE accounts ADD COLUMN signin_tries INTEGER NOT NULL DEFAULT 0;

DROP TABLE IF EXISTS codes;
CREATE TABLE codes (
  email      TEXT PRIMARY KEY,
  code       TEXT NOT NULL CHECK (length(code) = 6),
  expires_at INTEGER NOT NULL,
  tries      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS code_requests (
  id    TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS code_requests_email ON code_requests(email, at);
CREATE INDEX IF NOT EXISTS code_requests_at ON code_requests(at);

INSERT OR IGNORE INTO accounts (id, email, name, created_at)
VALUES ('deleted', 'deleted@invalid', 'A deleted account', 0);
