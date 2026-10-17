# Peel submission API

The server the app posts a pack to, and the only contract there is: the local reference server
that used to sit beside this is gone, because a reference that cannot verify a Google
signature specifies nothing.

## State, 18 Oct 2026

This folder is published with the website, so it says what the Worker does and not which
account it runs under. Account details and billing are in the vault notes.

**Running:**

- D1 database `peel-submit` and R2 bucket `peel-submissions`.
- Deployed at `https://peel-submit.refineco.workers.dev`, which is the address the app posts
  to (`SUBMIT_BASE_URL` in `app/build.gradle.kts`).
- **Workers Free.** An earlier note here said Paid; Billing says otherwise. Free allows about
  10 ms of CPU per request, and `/packs` hashes up to 8 MiB and walks a zip inside that
  budget — a 5.4 MB pack went through on 17 Oct, so it fits, but not with much room. Large
  packs answering 500 would point here first.
- `caches.default` does nothing on a `workers.dev` subdomain. Google's signing keys are
  therefore held in a module global, not the edge cache. Relying on the cache meant the keys
  were never retained, and the refetch throttle then refused honest sign-ins.

**Deploying a change:**

```
./check.sh                                            # first, against `wrangler dev`
npx wrangler deploy
npx wrangler d1 execute peel-submit --remote --file=migrations/<file>.sql
```

## Signing in

Google, and nothing else. The app gets an ID token through Credential Manager and posts it to
`/account/google`; this Worker checks the signature against Google's published keys and hands
back Peel's own bearer token, which is what every other endpoint already takes.

There is no password, no emailed code and no reset. That is the point. The code-and-password
machinery is where all three authentication defects found on 17 Oct lived — an account
takeover through a type confusion in `verify`, and two rate limits that were queries which
could never fire — and the code only ever proved an address was real, which Google tells us
for nothing. Nothing is emailed now, so there is no provider, no API key and no sending domain.

`GOOGLE_WEB_CLIENT_ID` in `wrangler.toml` is the audience every token must carry. It is not a
secret — the same value ships inside the APK — but it is load-bearing: if it is missing the
endpoint throws rather than falling back, because an undefined audience compares equal to a
token that has none, which would accept anything Google ever signed.

What the audience check does *not* prove is that the Peel app sent the token. Any app can ask
Google for one with this client id as its audience. The worst that buys is an account created
as the person themselves, which is what the real app does, and every pack is read by a person
before it is published. The `iat` age bound and the sign-in ceiling carry the rest.

The three OAuth clients — web, Android release, Android debug — live in the Google Cloud
project `peel-511906`, whose consent screen is published in production, so any Google account
works and not only listed test users.

### Working on it locally

```
./check.sh                                    # claim unit tests, then the HTTP surface
npx wrangler dev --local --port 8787          # a local Worker
adb reverse tcp:8787 tcp:8787                 # the phone's localhost becomes this machine
./check.sh                                    # again, now against the running Worker
```

and build the app's debug variant with `SUBMIT_BASE_URL` set to `http://localhost:8787` —
`SubmitClient` allows plain HTTP only in a debug build, and only for localhost, 127.0.0.1 and
the emulator's 10.0.2.2.

`check.sh` runs `node --test test/claims.test.js` first, and that is where the audience, the
expiry and `email_verified` are really tested. Every token the HTTP cases can build is refused
by the signature long before a claim is compared, so those cases alone stayed green with the
audience comparison deleted outright. A real sign-in still cannot be tested without a device,
and there is deliberately no bypass that would accept an unsigned token.

## What it does

| | |
|---|---|
| `POST /account/google` | `{idToken}` → `{token}`. A Google ID token in, Peel's own bearer token out. The only way an account is made. |
| `POST /account/delete` | Bearer → `{published}`. Removes the account, its tokens and every pack still waiting, files and rows. Published packs survive, pointed at a tombstone row, and the count comes back so the person can be told. |
| `POST /packs` | multipart with a Bearer token → `{id}`. Ten a day per account. |

Identity is Google's `sub`, not an address — so somebody changing their Google email keeps
their account, and there is no address normalising to keep in step between two codebases.

**Nothing is published by this.** Every pack waits for a person. `site/tools/peel_review.py`
is how they are read and published.

## Still missing

- **A review queue with a screen.** `peel_review.py list / show / publish / refuse` is it.
- **Voting.** The `votes` table exists; nothing writes to it, and the app has no Community
  section to vote from.
- **Telling somebody their pack was refused.** `peel_review.py refuse` marks the row and says
  so; the message is still one you write by hand.
- **The Play data-safety form**, which has to declare name, email address and a user ID.

## The zip check

An unauthenticated upload endpoint is where a zip bomb arrives first, so the archive is read
through its central directory rather than decompressed: entry names against a fixed pattern,
a cap on the number of entries, and compressed-versus-uncompressed totals compared before
anything is inflated. Only `manifest.json` is ever decompressed.

Both of those totals are numbers the sender wrote, so they catch a careless archive rather than
a crafted one: the protection that does not depend on the sender is the output cap inside
`inflateEntry`, which reads the inflated stream in chunks and gives up past 256 KB instead of
buffering whatever comes out. The entry pattern is `PackArchive.kt`'s exactly —
`manifest.json`, `tray.png`, `stickers/NN.webp` — and the manifest's sticker count has to match
the number of sticker files actually in the archive, because nothing looks again before a pack
is published.
