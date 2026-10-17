-- Applied with:
--   npx wrangler d1 execute peel-submit --remote --file=migrations/0004-indexes.sql
--
-- Two index corrections, both found by reading every query rather than by a slow page.
--
-- `accounts_email` is dropped. It was built when an address was the identity and a sign-in
-- looked a row up by it. Identity is `google_sub` now and nothing filters, joins or orders by
-- email: the column is written on insert and on conflict, and read back only from a row
-- already found by id. An index nothing reads still costs a write on every sign-in.
--
-- `tokens_account_id` is added. `tokens.token` is the primary key, so finding a session by its
-- token is already indexed — but three statements go the other way, by account: the prune that
-- keeps a person to five devices, the delete during account deletion, and the cascade when an
-- account row goes. Without this each of them scans the table.
--
-- Both are safe to re-run and neither touches a row.

DROP INDEX IF EXISTS accounts_email;
CREATE INDEX IF NOT EXISTS tokens_account_id ON tokens(account_id);
