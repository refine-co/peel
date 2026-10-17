# Peel submission API

The server the app posts a pack to. `site/tools/submit_server.py` is the same contract as a
local script, and is what the Android client was built and tested against; this is the version
that runs on Cloudflare.

## State, 17 Oct 2026

This folder is published with the website, so it says what the Worker does and not which
account it runs under. The account details, the plan and the billing are in the vault notes.

**Running:**

- D1 database `peel-submit` and R2 bucket `peel-submissions`, both created.
- The Worker is deployed at `https://peel-submit.refineco.workers.dev`, which is the address
  the app posts to (`SUBMIT_BASE_URL` in `app/build.gradle.kts`).
- Workers Paid, because the free plan allows about 10 ms of CPU per request and opening a
  multi-megabyte zip to check it does not fit in that.

**Deploying a change:**

```
npx wrangler deploy                                   # the Worker
npx wrangler d1 execute peel-submit --remote --file=migrations/<file>.sql
./check.sh                                            # against `wrangler dev`, first
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

## Turning it on

The sender is `peel@refineco.app`, set as `SENDER` in `src/index.js`. It is **not** on
`peel.refineco.app`: that name is a CNAME to GitHub Pages, and a name carrying a CNAME can hold
neither MX nor TXT, so no sending domain can live there. `refineco.app` already runs Email
Routing — MX to `route1/2/3.mx.cloudflare.net` and `v=spf1 include:_spf.mx.cloudflare.net` — so
half of this is in place and a reply to the address reaches a person.

In the Cloudflare dashboard, on the `refineco.app` zone: **Email → Email Service → Sending**,
onboard the domain, and add the DKIM records it offers (it can add them itself, since the zone
is on Cloudflare). Then add `peel@refineco.app` as a verified sender.

**Check the first real message by hand.** `_dmarc.refineco.app` is `p=reject; sp=reject`, so a
send Cloudflare accepts can still be thrown away at the far end if DKIM is not aligned, and
nothing in the Worker can see that. A successful call is not proof of delivery.

### Working on it locally

The binding cannot deliver from `wrangler dev`, so for local work:

```
npx wrangler dev --local --port 8787 --var DEV:1   # prints the code instead of sending it
adb reverse tcp:8787 tcp:8787                      # the phone's localhost is this machine
./check.sh
```

and build the app's debug variant with `SUBMIT_BASE_URL` set to `http://localhost:8787` —
`SubmitClient` allows plain HTTP only in a debug build, and only for localhost, 127.0.0.1 and
the emulator's 10.0.2.2.

## What is still missing after that

- **A review queue.** Packs land in R2 with a row in `submissions` marked `waiting`, and there
  is no screen to look at them yet. Until there is: `npx wrangler d1 execute peel-submit
  --remote --command "SELECT id, credit, pack_name, stickers, created_at FROM submissions WHERE
  state = 'waiting'"`.
- **Voting.** The `votes` table exists; nothing writes to it. The app has no Community section
  to vote from yet.
- **Deletion.** PDPA says somebody must be able to remove their account and their data. There
  is no endpoint for it, and it should exist before real people use this.
- **The paperwork.** `site/privacy.html` still says "no server that holds your work" and
  "traffic only ever goes one way". Both stop being true the day this goes live, and the Play
  data-safety form has to say that name and email are collected.

## What it does

| | |
|---|---|
| `POST /account/code` | `{email, name}` → 204, and a six-digit code is emailed. One live code per address, 15 minutes, five tries. |
| `POST /account/verify` | `{email, code}` → `{token}`. The token goes in the phone's own storage and nowhere else. |
| `POST /packs` | multipart with a Bearer token → `{id}`. Ten a day per account. |

**Email addresses are normalised before anything else** — lowercased, `+suffix` dropped, and on
Gmail the dots removed — so one mailbox is one account and cannot become a hundred votes. The
client does the same thing in `AccountStore.normalise`; if the two ever disagree, they disagree
about who somebody is.

**Nothing is published by this.** Every pack waits for a person.

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
