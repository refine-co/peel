-- The iPhone waitlist, which measures whether an iOS Peel is worth building.
--
-- This is a waitlist and not a pre-order, deliberately. No iOS build exists, there is no date
-- and there is no Apple developer account, so taking money would be selling something that
-- cannot be delivered and would have to be refunded. An address answers the same question.
--
-- Nothing is emailed from here. The Worker has no mail provider and no API key, which is the
-- same state the rest of this schema is in; reaching these people means exporting the table
-- and sending from refine.co.my@gmail.com by hand, and that is fine for a list this size.
CREATE TABLE IF NOT EXISTS ios_waitlist (
  -- Lowercased on the way in, so two spellings of one address are one row rather than two
  -- votes. This is the whole dedupe: an INSERT OR IGNORE against this key costs one statement
  -- and has no window between a look and a write for a double tap to fit through.
  email       TEXT PRIMARY KEY,
  created_at  INTEGER NOT NULL,
  -- Where the person came from, read off `?from=` on the page: "share" for somebody who was
  -- sent a sticker pack and could not open it, "social" for a post, null for a direct visit.
  -- This is the column that makes the result actionable rather than just a number: if the
  -- share loop is where they come from, the next move is in the app, not on the website.
  source      TEXT,
  -- The country Cloudflare saw, which costs nothing to keep and decides whether a small list
  -- is small everywhere or concentrated somewhere worth serving first.
  country     TEXT
);

-- The per-day ceiling counts rows by day, so it needs this rather than a scan.
CREATE INDEX IF NOT EXISTS ios_waitlist_created ON ios_waitlist(created_at);
