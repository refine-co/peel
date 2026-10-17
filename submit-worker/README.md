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

**Email is the one thing still missing, and nothing works without it.** `/account/code` is how
every account is made, so until the Worker can send a message the feature is dead: with no
`RESEND_KEY` set it now answers 500 and the phone says it could not reach Peel. That is
deliberate. It used to print the code to the console and answer 204, with no check on where it
was running — on the deployed Worker that put every sign-in code into the log stream in plain
text while telling people a message was on its way that never came.

To switch it on, either `npx wrangler secret put RESEND_KEY` with a Resend key for a verified
`peel.refineco.app` sender, or move `sendCode` to Cloudflare Email Sending, which Workers Paid
includes. For local work, `wrangler dev` with `DEV=1` set prints the code as before.

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
