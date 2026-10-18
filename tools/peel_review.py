#!/usr/bin/env python3
"""Review what people have sent in, and publish the good ones.

The missing half of community packs. Submissions arrive in Cloudflare (D1 + R2); this is how
they are looked at and how an accepted one reaches both the app and the website.

    python3 peel_review.py list
    python3 peel_review.py show <id>        # unpacks it and opens a contact sheet
    python3 peel_review.py publish <id> --slug cool-cats
    python3 peel_review.py refuse  <id> "Characters you do not own."

WHY A LOCAL TOOL RATHER THAN A WEB PAGE

Publishing means the file has to end up where the app will fetch it. The app refuses every host
except peel.refineco.app and every path outside /packs/ and /scenes/ — both checked in
PackDownloader — and that host is GitHub Pages, not Cloudflare. So a pack becomes public by
landing in site/packs/ and being committed, exactly like Peel's own packs. Running the publish
step here means no DNS change, no new credential in the cloud, and no app release.

It uses the wrangler CLI you are already signed in to, so there is no admin endpoint on the
Worker and nothing new to attack.

AUTO-SYNC

`publish` does the whole chain: pulls the file out of R2, writes it into site/packs/, regenerates
the catalogue and the preview pictures with build_catalogue.py, builds the website's sheet and
rail with build_sheets.py and build_deck.py, and marks the row published. The
app and the website then agree because they read the same generated catalogue — the app fetches
catalogue.json, the website is built from it. The last step is a commit, which is left to you.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
SITE = HERE.parent
PACKS = SITE / "packs"
# Which published packs arrived as submissions, and who to credit. Read by build_catalogue.py
# and build_sheets.py; written only here.
COMMUNITY = SITE / "community.json"
WORKER = SITE.parent / "submit-worker"
DB = "peel-submit"
BUCKET = "peel-submissions"

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")

# A pack is at most 8 MiB compressed, so nothing honest comes near these.
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_UNPACKED_BYTES = 64 * 1024 * 1024


def d1(sql: str) -> list[dict]:
    """Runs one statement against the remote database through wrangler."""
    out = subprocess.run(
        ["npx", "wrangler", "d1", "execute", DB, "--remote", "--json", "--command", sql],
        cwd=WORKER, capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit(f"wrangler failed:\n{out.stderr.strip()}")
    # wrangler prints a banner before the JSON.
    text = out.stdout[out.stdout.index("[") :]
    return json.loads(text)[0]["results"]


def r2_delete(key: str) -> None:
    """Takes the file out of the bucket.

    Nothing else does. The Worker refuses a submission once the bucket holds 8 GiB, and it only
    counts rows still `waiting` — so a pack that has been published or refused has to actually
    leave, or the ceiling creeps up on its own until submissions stop with no error anybody
    sees. A published pack lives in site/packs/ from here on; a refused one is not kept.
    """
    out = subprocess.run(
        ["npx", "wrangler", "r2", "object", "delete", f"{BUCKET}/{key}", "--remote"],
        cwd=WORKER, capture_output=True, text=True,
    )
    if out.returncode != 0:
        print(f"  warning: {key} is still in the bucket:\n{out.stderr.strip()}")


def r2_get(key: str, into: pathlib.Path) -> None:
    out = subprocess.run(
        ["npx", "wrangler", "r2", "object", "get", f"{BUCKET}/{key}", "--file", str(into), "--remote"],
        cwd=WORKER, capture_output=True, text=True,
    )
    if out.returncode != 0 or not into.is_file():
        sys.exit(f"could not fetch {key}:\n{out.stderr.strip()}")


def cmd_list(_args) -> None:
    rows = d1(
        "SELECT s.id, s.credit, s.pack_name, s.stickers, s.bytes, s.created_at, a.email "
        "FROM submissions s JOIN accounts a ON a.id = s.account_id "
        "WHERE s.state = 'waiting' ORDER BY s.created_at"
    )
    if not rows:
        print("Nothing waiting.")
        return
    print(f"{len(rows)} waiting\n")
    for r in rows:
        mb = r["bytes"] / 1024 / 1024
        print(f"  {r['id']}")
        print(f"    {r['pack_name']!r} — {r['stickers']} stickers, {mb:.1f} MB")
        print(f"    credit: {r['credit']}   from: {r['email']}\n")


def cmd_show(args) -> None:
    out = pathlib.Path(tempfile.mkdtemp(prefix="peel-review-"))
    peel = out / f"{args.id}.peel"
    r2_get(f"{args.id}.peel", peel)
    with zipfile.ZipFile(peel) as z:
        # Not extractall: every size in a zip is a number the sender wrote, and this is the
        # first place the entries are actually inflated. A file that says it is 100 KB and
        # expands to 10 GB would fill the disk of the person reviewing it.
        written = 0
        for info in z.infolist():
            if info.file_size > MAX_ENTRY_BYTES or written + info.file_size > MAX_UNPACKED_BYTES:
                sys.exit(f"{info.filename} claims {info.file_size} bytes. Not unpacking this one.")
            z.extract(info, out / "unpacked")
            written += info.file_size
        manifest = json.loads(z.read("manifest.json"))
    print(f"name:      {manifest.get('name')}")
    print(f"publisher: {manifest.get('publisher')}")
    print(f"animated:  {manifest.get('animated')}")
    print(f"stickers:  {len(manifest.get('stickers', []))}")
    for s in manifest.get("stickers", []):
        print(f"   {s.get('file'):24} {' '.join(s.get('emojis', []))}  {s.get('accessibilityText','')[:60]}")
    print(f"\nunpacked to {out / 'unpacked'}")
    subprocess.run(["open", str(out / "unpacked" / "stickers")], check=False)


def sql_text(value: str) -> str:
    """A string literal for wrangler's --command, which takes no bound parameters."""
    return value.replace("'", "''")


def cmd_publish(args) -> None:
    if not SLUG.match(args.slug):
        sys.exit("A slug is lowercase letters, digits and hyphens: cool-cats")
    target = PACKS / f"{args.slug}.peel"
    if target.exists():
        sys.exit(f"{target.name} already exists. Pick another slug — a filename is a pack's id, "
                 "and overwriting one would repoint an id people already have.")

    rows = d1(f"SELECT id, credit, pack_name, state FROM submissions WHERE id = '{sql_text(args.id)}'")
    if not rows:
        sys.exit("No such submission.")
    row = rows[0]
    if row["state"] != "waiting":
        sys.exit(f"That one is already {row['state']}.")

    r2_get(f"{args.id}.peel", target)
    print(f"wrote {target}")

    # Three builders, not one. build_catalogue.py is what the app reads; build_sheets.py and
    # build_deck.py are what the website shows. Running only the first is how Oyen Kampung
    # ended up downloadable in More fun and absent from packs.html — the app and the site
    # disagreeing about what exists. Any of them failing leaves nothing published.
    for script in ("build_catalogue.py", "build_sheets.py", "build_deck.py"):
        build = subprocess.run(["python3", script], cwd=HERE, capture_output=True, text=True)
        if build.returncode != 0:
            target.unlink(missing_ok=True)
            sys.exit(f"{script} failed, nothing published:\n{build.stderr.strip()}")
        print(build.stdout.strip())

    # Who sent it, written down rather than guessed. The pack's own `publisher` field is typed
    # by the person submitting, so a pack claiming to be Peel's own would otherwise become
    # Peel's own by saying so. This file is the only thing that makes a pack community, and it
    # is written here, where we know it arrived as a submission.
    community = json.loads(COMMUNITY.read_text()) if COMMUNITY.exists() else {}
    community[args.slug] = {"credit": row["credit"], "at": now_ms()}
    COMMUNITY.write_text(json.dumps(community, indent=2, sort_keys=True) + "\n")
    print(f"recorded {args.slug} as community, credited to {row['credit']}")

    d1(f"UPDATE submissions SET state = 'published', reviewed_at = {now_ms()} WHERE id = '{sql_text(args.id)}'")
    r2_delete(f"{args.id}.peel")
    print(f"\n{row['pack_name']!r} by {row['credit']} is in the catalogue.")
    print("\nThe last step is one commit, in both repositories:")
    print(f"  cd {SITE}  &&  git add -A packs catalogue.json packs.html community.json  &&  git commit && git push")
    print("  cd ~/Projects/android-peel  &&  git add -A app/src/main/assets  &&  git commit && git push")
    print("\nThe app picks it up the next time somebody opens More fun or pulls it down.")


def cmd_refuse(args) -> None:
    reason = args.reason.replace("'", "''")
    rows = d1(f"SELECT state FROM submissions WHERE id = '{sql_text(args.id)}'")
    if not rows:
        sys.exit("No such submission.")
    d1(
        f"UPDATE submissions SET state = 'refused', reason = '{reason}', "
        f"reviewed_at = {now_ms()} WHERE id = '{sql_text(args.id)}'"
    )
    r2_delete(f"{args.id}.peel")
    print(f"Marked refused: {args.reason}")
    print("Nothing emails them yet — that is still a message you send by hand.")


def now_ms() -> int:
    import time

    return int(time.time() * 1000)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(func=cmd_list)
    show = sub.add_parser("show"); show.add_argument("id"); show.set_defaults(func=cmd_show)
    pub = sub.add_parser("publish")
    pub.add_argument("id"); pub.add_argument("--slug", required=True); pub.set_defaults(func=cmd_publish)
    ref = sub.add_parser("refuse")
    ref.add_argument("id"); ref.add_argument("reason"); ref.set_defaults(func=cmd_refuse)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
