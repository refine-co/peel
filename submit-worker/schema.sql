-- Peel submissions. Applied with:
--   npx wrangler d1 execute peel-submit --remote --file=schema.sql

-- One row per person, keyed on Google's subject claim. The address is whatever Google says it
-- is and is kept only so a submitter can be written to; it is never shown to anybody.
CREATE TABLE IF NOT EXISTS accounts (
  id          TEXT PRIMARY KEY,
  -- Not unique: identity is google_sub. Somebody whose Google address changes would otherwise
  -- collide with a stranger's old row and turn a sign-in into a 500.
  email       TEXT NOT NULL,
  name        TEXT NOT NULL,
  created_at  INTEGER NOT NULL,
  -- Set when the account is made. A Google-verified address is the verification.
  verified_at INTEGER,
  -- Set to silence somebody without deleting what they sent. Checked at sign-in as well as on
  -- upload, or blocking means nothing to anybody who can still get a token.
  blocked_at  INTEGER,
  -- Google's subject claim, which is who a person is here. There is no password and no
  -- emailed code: that machinery is where every authentication defect found on 17 Oct lived,
  -- and it only ever proved an address was real, which Google tells us for nothing.
  google_sub  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS accounts_google_sub ON accounts(google_sub);

-- The row every deleted account's published submissions point at, so the credit on the website
-- still resolves while the person behind it is gone. Not an account anybody can sign in to:
-- its google_sub is NULL and there is no subject that matches NULL.
INSERT OR IGNORE INTO accounts (id, email, name, created_at)
VALUES ('deleted', 'deleted@invalid', 'A deleted account', 0);

-- One row per sign-in attempt, written before the token is checked and counted across
-- everybody. Counting attempts rather than accounts is the whole point: a failed sign-in and
-- a returning person both create no account, so an accounts-per-day ceiling never fires.
CREATE TABLE IF NOT EXISTS sign_in_attempts (
  id TEXT PRIMARY KEY,
  at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sign_in_attempts_at ON sign_in_attempts(at);

-- Bearer tokens held on a phone. Deleting a row signs that device out.
CREATE TABLE IF NOT EXISTS tokens (
  token      TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL
);

-- The token is the primary key, so a session lookup is already covered. This is for the three
-- statements that go the other way: the five-device prune, the delete, and the cascade.
CREATE INDEX IF NOT EXISTS tokens_account_id ON tokens(account_id);

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
