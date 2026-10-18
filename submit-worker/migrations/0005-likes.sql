-- Likes, which need a published pack to be addressable by the name the app knows it by.
--
-- The votes table has existed since the first schema and nothing ever wrote to it: it is keyed
-- by submission id, and the app has never seen a submission id. What the app has is the
-- catalogue slug — "oyen-kampung", "s22-test-pack" — which is decided at publish time and
-- written nowhere the Worker could read.
--
-- So the slug comes back to the row it was published from. One column, set by peel_review.py
-- when it publishes, null for everything still waiting or refused.
ALTER TABLE submissions ADD COLUMN slug TEXT;

-- Unique because a slug is a filename on the site, and two rows claiming the same one would
-- make "how many likes has this pack" ambiguous. Partial, because every unpublished row has a
-- null slug and those must not collide with each other.
CREATE UNIQUE INDEX IF NOT EXISTS submissions_slug ON submissions(slug) WHERE slug IS NOT NULL;
