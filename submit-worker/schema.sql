-- Peel submissions. Applied with:
--   npx wrangler d1 execute peel-submit --remote --file=schema.sql

-- One row per person. The email is stored normalised (dots and +suffix stripped on Gmail), so
-- a.b+peel@gmail.com and ab@gmail.com cannot become two accounts and two votes.
CREATE TABLE IF NOT EXISTS accounts (
  id          TEXT PRIMARY KEY,
  email       TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  created_at  INTEGER NOT NULL,
  -- Set when a code is first verified. An unverified account may not vote.
  verified_at INTEGER,
  -- Set to silence somebody without deleting what they sent.
  blocked_at  INTEGER,
  -- Optional. An account works without one: the six-digit code by email is always available,
  -- and is the reset path, so a forgotten password locks nobody out. Stored as PBKDF2-HMAC-
  -- SHA256 over a per-account random salt, never as the password.
  pw_hash     TEXT,
  pw_salt     TEXT,
  pw_iters    INTEGER,
  -- Wrong-password count, here rather than on the code row. Keeping it with the code meant a
  -- failed sign-in wrote a row into `codes`, which both poisoned the real code somebody was
  -- holding and left an empty one behind that `verify` would accept.
  signin_tries INTEGER NOT NULL DEFAULT 0
);

-- The row every deleted account's published submissions point at, so the credit on the website
-- still resolves while the person behind it is gone. Not an account anybody can sign in to:
-- the address is unroutable and there is no password.
INSERT OR IGNORE INTO accounts (id, email, name, created_at)
VALUES ('deleted', 'deleted@invalid', 'A deleted account', 0);

-- Sign-in codes. Short-lived and single-use; tries is capped so a six-digit code cannot be
-- walked through at leisure.
CREATE TABLE IF NOT EXISTS codes (
  email      TEXT PRIMARY KEY,
  -- Exactly six digits, always. A row with an empty code was a sign-in counter in an earlier
  -- version, and `verify` happily matched it against a request that sent no code at all.
  code       TEXT NOT NULL CHECK (length(code) = 6),
  expires_at INTEGER NOT NULL,
  tries      INTEGER NOT NULL DEFAULT 0
);

-- One row per code asked for, kept only long enough to count. `codes` cannot do this job: its
-- primary key is the address, so a COUNT over it is always 0 or 1 and the per-hour ceiling it
-- was asked to enforce could never fire.
CREATE TABLE IF NOT EXISTS code_requests (
  id    TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS code_requests_email ON code_requests(email, at);
CREATE INDEX IF NOT EXISTS code_requests_at ON code_requests(at);

-- Bearer tokens held on a phone. Deleting a row signs that device out.
CREATE TABLE IF NOT EXISTS tokens (
  token      TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL
);

-- One row per pack sent in. The file itself lives in R2 under the same id.
-- state: waiting | published | refused | withdrawn
CREATE TABLE IF NOT EXISTS submissions (
  id           TEXT PRIMARY KEY,
  account_id   TEXT NOT NULL REFERENCES accounts(id),
  credit       TEXT NOT NULL,
  note         TEXT NOT NULL DEFAULT '',
  pack_name    TEXT NOT NULL DEFAULT '',
  stickers     INTEGER NOT NULL DEFAULT 0,
  bytes        INTEGER NOT NULL,
  sha256       TEXT NOT NULL,
  state        TEXT NOT NULL DEFAULT 'waiting',
  reason       TEXT,
  created_at   INTEGER NOT NULL,
  reviewed_at  INTEGER
);

-- The same pack sent twice is the same submission, not two.
CREATE UNIQUE INDEX IF NOT EXISTS submissions_sha ON submissions(sha256);
CREATE INDEX IF NOT EXISTS submissions_state ON submissions(state, created_at);

-- One like per account per pack, enforced by the primary key rather than by checking first.
CREATE TABLE IF NOT EXISTS votes (
  submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  account_id    TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  created_at    INTEGER NOT NULL,
  PRIMARY KEY (submission_id, account_id)
);
