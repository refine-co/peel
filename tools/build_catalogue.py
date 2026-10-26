#!/usr/bin/env python3
"""Build the catalogue Peel's "More fun" screen reads.

Two files, same items.

**The floor** ships inside the APK and is what the screen shows the instant it opens — first
run, aeroplane mode, or a user who never pulls. Its thumbnails are asset paths.

**The overlay** is `catalogue.json` on the site, fetched only when someone pulls the grid down.
It carries the same items plus everything the app cannot already have: a thumbnail inlined as
base64 WebP, because fetching N thumbnails would be N sockets per screen and a log of who
opened what; and `needs`, the lowest versionCode that can open the item, so a file in a format
an older Peel cannot read is greyed with a reason instead of failing at import.

Fetched only on a pull, never at launch and never on a timer. That is what keeps the listing
sentence close to true: the request is a consequence of someone asking for it.

Everything here is read out of the archives themselves, exactly as `build_scenes.py` builds the
scene cards from the `.chill`. The catalogue therefore cannot describe something the file does
not contain, and the thumbnail in the grid is the file's own.

    python3 site/tools/build_catalogue.py

Writes catalogue.json and one thumbnail per item into the Android project's assets.
"""

import base64
import hashlib
import io
import json
import os
import pathlib
import zipfile

from PIL import Image

SITE = pathlib.Path(__file__).resolve().parent.parent
PACKS_DIR = SITE / "packs"

# Packs that arrived as submissions: {slug: {"credit": str, "at": ms}}. Written by
# peel_review.py at publish time. Absent file means nothing has been published from the
# queue yet, which is the state every install started in.
_community_file = SITE / "community.json"
COMMUNITY = json.loads(_community_file.read_text()) if _community_file.exists() else {}
SCENES_DIR = SITE / "scenes"

# The Android project, which is a separate repo. Written into rather than read from, because the
# site is where the downloadable files live and so the site is where the truth is.
ASSETS = pathlib.Path(os.environ.get("PEEL_ASSETS") or (pathlib.Path.home() / "Projects/android-peel/app/src/main/assets"))
THUMBS = ASSETS / "catalogue"
PREVIEWS = ASSETS / "previews"
# The same tiles, published beside the pack so the app can show a sheet for something that did
# not exist when it was built. Without this every community pack is picture-less for everyone
# until the next release bundles it — which for a section fed by submissions is always.
SITE_PREVIEWS = SITE / "packs" / "img"
PREVIEW_BASE = "https://peel.refineco.app/packs/img"

BASE = "https://peel.refineco.app"

# The lowest versionCode that can open each kind. Packs have been importable since the first
# release; `.chill` arrived with Peel 2.0.0, versionCode 15. This is per kind today because no
# file yet needs more than its kind's floor -- the day one does, it gets its own number here
# and every older install greys it out with a reason instead of downloading it and failing.
NEEDS = {"pack": 1, "scene": 15}

# One file that needs more than its kind's floor. A paid pack belongs here on the day it is
# published: FreeContent is compiled into the app, so a build released before the pack existed
# has never heard of its fingerprint and would hand it over for nothing. Naming the release
# that does know it means every older install greys the card out with "Update Peel to get
# this" instead -- which is the wrong-in-the-harmless-direction failure.
NEEDS_BY_ID: dict[str, int] = {
    "dead-honest": 23, "sir-crow": 23,
    # The Deepavali shelf needs Peel 2.5.0 (versionCode 50): that build carries their fingerprints
    # and the animated sheet previews and the price on the card that let them sell themselves.
    "lakshmi": 50, "divine-blessings": 50, "little-diya": 50, "mayil": 50, "kolam-lights": 50,
    "deepavali-doorstep": 50,
}

# Packs that are sold. Peel 2.4.1 (versionCode 25) reads `paid` from the fetched list, so a paid
# pack published from now on needs only an entry here and `needs` of 25 in NEEDS_BY_ID: no new
# release has to add its fingerprint. Builds before 2.4.1 ignore the flag, which is why the new
# pack's `needs` must be 25 -- those builds then grey the card instead of importing it free.
# Dead Honest and Sir Crow are also compiled into the app (FreeContent.PAID_PACKS) and stay so.
PAID_IDS: set[str] = {
    "dead-honest", "sir-crow",
    "lakshmi", "divine-blessings", "little-diya", "mayil", "kolam-lights",
}

# Categories. Peel groups packs by these on Home and in More fun. The list travels in the
# catalogue file, and each item names one by id, so adding a category or moving a pack between
# two needs no app release: an app that has no words for a category shows the name given here,
# and one that has never heard of the id shows the pack under "More". Ids are fixed once
# published -- the app keys the person's own filing on them. Peel 2.5.0 is the first to read
# them; older builds ignore the fields.
CATEGORIES = [
    {"id": "halloween", "en": "Halloween", "ms": "Halloween"},
    {"id": "cats", "en": "Cats", "ms": "Kucing"},
    {"id": "chat", "en": "Chat and reactions", "ms": "Sembang dan reaksi"},
    {"id": "cosy", "en": "Cosy nights", "ms": "Malam santai"},
    {"id": "festivals", "en": "Festivals", "ms": "Perayaan"},
]
CATEGORY_BY_ID: dict[str, str] = {
    "dead-honest": "halloween",
    "ghost-says": "halloween",
    "halloween-night": "halloween",
    "halloween": "halloween",
    "low-light": "halloween",
    "just-lurking": "cats",
    "midnight-replies": "cats",
    "oyen-kampung": "cats",
    "reactions": "chat",
    "say-it": "chat",
    "sir-crow": "halloween",
    "moth-lights": "halloween",
    # Scenes carry one too, for later; More fun keeps its single Scenes ring for now.
    "firefly-jar": "cosy",
    "lantern-alley": "cosy",
    "village-night": "cosy",
    "knock-twice": "halloween",
    # The Deepavali shelf. Not published until 2.5.0 is live: these ids exist here so the day
    # the files go into site/packs and site/scenes they come out filed and priced correctly.
    "happy-deepavali": "festivals",
    "lakshmi": "festivals",
    "divine-blessings": "festivals",
    "little-diya": "festivals",
    "mayil": "festivals",
    "kolam-lights": "festivals",
    "deepavali-doorstep": "festivals",
}

# What leads More fun. The list's own order is the page's order: the app shows categories in the
# order it first meets them and cards in the order they are listed, so the season's shelf goes
# first by being first here, and gives the top back by being removed from SHELF_FIRST. For
# Deepavali the paid hero leads and the free greeting sits third, where the person who came for
# a free greeting still finds it without the first card being a free one.
SHELF_FIRST = "festivals"
SHELF_ORDER = [
    "deepavali-doorstep", "divine-blessings", "lakshmi", "happy-deepavali",
    "little-diya", "mayil", "kolam-lights",
]

# The inline thumbnail. 192 px because a grid cell is 500-560 px on a 3x display and 96 would
# be a five-fold upscale; WebP with alpha because pack trays are cut-outs and a white box
# behind a sticker is the failure this is meant to avoid.
INLINE_MAX = 192
INLINE_QUALITY = 72

# Bumped only when the shape changes in a way an older Peel could not read. A build in the wild
# reads whatever it shipped with, so this is really a note to the next person.
VERSION = 1


def human(n: int) -> str:
    """The same size the web page shows, so the two never disagree in front of a user."""
    kb = n / 1024
    return f"{kb/1024:.1f} MB" if kb >= 1024 else f"{kb:.0f} KB"


def inline_thumb(path: pathlib.Path, inner: str, alpha: bool) -> str:
    """The item's own picture, small enough to travel inside the list."""
    with zipfile.ZipFile(path) as z:
        im = Image.open(io.BytesIO(z.read(inner)))
        im.thumbnail((INLINE_MAX, INLINE_MAX), Image.LANCZOS)
        buf = io.BytesIO()
        im.convert("RGBA" if alpha else "RGB").save(
            buf, "WEBP", quality=INLINE_QUALITY, method=6)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def pack_entry(path: pathlib.Path) -> dict:
    with zipfile.ZipFile(path) as z:
        raw = z.read("manifest.json")
        manifest = json.loads(raw)
    return {
        "id": path.stem,
        "kind": "pack",
        "title": manifest["name"],
        "pieces": len(manifest.get("stickers", [])),
        "animated": bool(manifest.get("animated", False)),
        "bytes": path.stat().st_size,
        "size": human(path.stat().st_size),
        "file": f"{BASE}/packs/{path.name}",
        "thumb": f"catalogue/{path.stem}.png",
        # Packs carry a fingerprint for the same reason scenes do, now that a pack can be sold:
        # the grid has to be able to say the price before the download rather than after it.
        # The app decides free or paid from this through FreeContent, never from what this file
        # claims — and a pack whose entry carries no fingerprint says nothing about price at
        # all, which is why this is not optional for a pack that is published.
        "manifestSha256": hashlib.sha256(raw).hexdigest(),
    }


def scene_entry(path: pathlib.Path) -> dict:
    with zipfile.ZipFile(path) as z:
        raw = z.read("scene.json")
        scene = json.loads(raw)
    return {
        "id": scene["id"],
        "kind": "scene",
        "title": scene["name"],
        "pieces": len(scene.get("stickers", [])),
        "animated": False,
        "bytes": path.stat().st_size,
        "size": human(path.stat().st_size),
        "file": f"{BASE}/scenes/{path.name}",
        "thumb": f"catalogue/{scene['id']}.jpg",
        # The app decides free from this, through FreeContent.sceneIsFree, rather than the
        # catalogue asserting it. One source of truth, and the gate still fails closed: a scene
        # this file calls free that FreeContent does not know is simply paid.
        "manifestSha256": hashlib.sha256(raw).hexdigest(),
    }


# A grid cell is never wider than half a phone, so anything past this is bytes in the APK that
# nobody can see. The scene thumbnails inside the archives are full board pictures — one was
# 105 KB on its own.
THUMB_MAX = 420

# One picture per sticker, for the sheet that opens under a pack's card in the app. 128 px
# because a sheet tile is about 48 dp, which is 144 px on a 3x display, and the sheet shows every
# sticker at once: at 128 px the whole catalogue is under a megabyte of APK, and at 256 px it
# would be four times that for a tile nobody can look at closely.
#
# Not on the site and not in catalogue.json. The app derives the paths from the directory
# (CatalogueStore.previews), so a pack published after a release simply has no pictures in that
# release and its card offers the download instead -- rather than this travelling in the fetched
# list, where the merge would drop it and the parser would have to cap it.
PREVIEW_MAX = 128
PREVIEW_QUALITY = 80


# An animated pack's first tiles move in the sheet, so its preview is an animated WebP rather than
# frame 0: a locked pack is judged from this sheet and nothing else, and a row of still pictures
# sold motion as something less than it is. Every second frame is kept (a 20-frame sticker plays as
# 10 at 5 fps), which is what keeps a tile near 30 KB at 128 px; the full-rate frames would be double
# for a movement nobody studies at 48 dp. Raise PREVIEW_FRAME_STEP's cost deliberately: the tiles
# ship in the APK and on the site, once per animated pack.
#
# PLAY_TILES mirrors MAX_PLAYING in StickerSheet.kt: the app plays only the first twelve tiles of a
# sheet, so a longer pack's later tiles are written still. Keep the two numbers equal.
PLAY_TILES = 12
PREVIEW_FRAME_STEP = 2
PREVIEW_ANIM_QUALITIES = (40, 32, 26, 20)
PREVIEW_ANIM_MAX_BYTES = 40 * 1024


def animated_preview(im: Image.Image, target: pathlib.Path) -> bool:
    """Write [im] as an animated tile; False when it is a single frame, so the caller writes a still."""
    frames = getattr(im, "n_frames", 1)
    if frames < 2:
        return False
    ms = (im.info.get("duration") or 100) * PREVIEW_FRAME_STEP
    tiles = []
    for i in range(0, frames, PREVIEW_FRAME_STEP):
        im.seek(i)
        f = im.convert("RGBA")
        f.thumbnail((PREVIEW_MAX, PREVIEW_MAX), Image.LANCZOS)
        tiles.append(f)
    data = b""
    for q in PREVIEW_ANIM_QUALITIES:
        buf = io.BytesIO()
        tiles[0].save(buf, "WEBP", save_all=True, append_images=tiles[1:], duration=ms, loop=0,
                      background=(255, 255, 255, 255), quality=q, alpha_quality=q, method=6)
        data = buf.getvalue()
        if len(data) <= PREVIEW_ANIM_MAX_BYTES:
            break
    target.write_bytes(data)
    return True


def previews_of(path: pathlib.Path, files: list[str], out: pathlib.Path) -> int:
    """Every sticker in the archive, scaled to a sheet tile. Returns the bytes written."""
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.webp"):
        stale.unlink()
    written = 0
    with zipfile.ZipFile(path) as z:
        for n, inner in enumerate(files, start=1):
            im = Image.open(io.BytesIO(z.read(inner)))
            target = out / f"{n:02d}.webp"
            # The tiles that play are animated files. Every other tile is frame 0, the frame
            # WhatsApp rests on and the one the app shows when it is not playing (reduced motion,
            # API < 28), so a still pack and the tail of a long animated one are unchanged.
            if n > PLAY_TILES or not animated_preview(im, target):
                im.seek(0)
                im = im.convert("RGBA")
                im.thumbnail((PREVIEW_MAX, PREVIEW_MAX), Image.LANCZOS)
                im.save(target, "WEBP", quality=PREVIEW_QUALITY, method=6)
            written += target.stat().st_size
    return written


def thumb_of(path: pathlib.Path, inner: str, out: pathlib.Path) -> None:
    """The item's own picture, taken straight out of its archive and scaled to the grid."""
    with zipfile.ZipFile(path) as z, z.open(inner) as src:
        im = Image.open(io.BytesIO(src.read()))
        im.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
        if out.suffix == ".jpg":
            im.convert("RGB").save(out, "JPEG", quality=82, optimize=True)
        else:
            # Trays are cut-outs; flattening one would put a white box behind the sticker.
            im.save(out, "PNG", optimize=True)


def main() -> None:
    THUMBS.mkdir(parents=True, exist_ok=True)
    items = []

    preview_bytes = 0
    for p in sorted(PACKS_DIR.glob("*.peel")):
        entry = pack_entry(p)
        thumb_of(p, "tray.png", THUMBS / f"{entry['id']}.png")
        with zipfile.ZipFile(p) as z:
            stickers = [s["file"] for s in json.loads(z.read("manifest.json")).get("stickers", [])]
        preview_bytes += previews_of(p, stickers, PREVIEWS / entry["id"])
        # Published as well as bundled. Named from the archive, like the bundled ones, so the
        # two sets cannot drift apart.
        site_dir = SITE_PREVIEWS / entry["id"] / "previews"
        preview_bytes += previews_of(p, stickers, site_dir)
        entry["previews"] = [
            f"{PREVIEW_BASE}/{entry['id']}/previews/{f.name}" for f in sorted(site_dir.glob("*.webp"))
        ]
        items.append(entry)

    for p in sorted(SCENES_DIR.glob("*.chill")):
        entry = scene_entry(p)
        with zipfile.ZipFile(p) as z:
            inner = json.loads(z.read("scene.json")).get("thumbnail", "thumb.jpg")
        thumb_of(p, inner, THUMBS / f"{entry['id']}.jpg")
        items.append(entry)

    for entry in items:
        category = CATEGORY_BY_ID.get(entry["id"])
        if category:
            entry["category"] = category
        else:
            print(f"  note: {entry['id']} has no category, so Peel shows it under More")

    items.sort(key=lambda e: (
        0 if e.get("category") == SHELF_FIRST else 1,
        SHELF_ORDER.index(e["id"]) if e["id"] in SHELF_ORDER else len(SHELF_ORDER),
    ))

    out = ASSETS / "catalogue.json"
    out.write_text(json.dumps({"v": VERSION, "categories": CATEGORIES, "items": items}, indent=2, ensure_ascii=False) + "\n")
    print(f"{out}  ({len(items)} items)")
    for i in items:
        print(f"  {i['kind']:5} {i['id']:18} {i['pieces']:3} pieces  {i['size']:>8}")
    print(f"{PREVIEWS}  ({preview_bytes / 1024:.0f} KB of sheet pictures)")

    # The overlay. Same items, plus what the app cannot already have.
    overlay = []
    for entry in items:
        src = (PACKS_DIR / f"{entry['id']}.peel" if entry["kind"] == "pack"
               else SCENES_DIR / pathlib.Path(entry["file"]).name)
        inner = "tray.png" if entry["kind"] == "pack" else (
            json.loads(zipfile.ZipFile(src).read("scene.json")).get("thumbnail", "thumb.jpg"))
        item = {k: v for k, v in entry.items() if k != "thumb"}
        item["needs"] = NEEDS_BY_ID.get(entry["id"], NEEDS[entry["kind"]])
        if entry["id"] in PAID_IDS:
            item["paid"] = True
        # A pack somebody sent in, and the name to credit it to. The app puts these in their
        # own "From the community" section; a pack of ours carries neither field. The source
        # is community.json, written by peel_review.py when a submission is published, never
        # the pack's own publisher field — that is typed by the submitter.
        sent_in = COMMUNITY.get(entry["id"])
        if sent_in:
            item["community"] = True
            if sent_in.get("credit"):
                item["credit"] = sent_in["credit"]
        item["thumb"] = inline_thumb(src, inner, alpha=entry["kind"] == "pack")
        overlay.append(item)

    site_out = SITE / "catalogue.json"
    site_out.write_text(
        json.dumps({"v": VERSION, "categories": CATEGORIES, "items": overlay}, ensure_ascii=False) + "\n")
    size = site_out.stat().st_size
    print(f"\n{site_out}  ({len(overlay)} items, {size / 1024:.0f} KB)")
    if size > 512 * 1024:
        print("  OVER the 512 KB the app will accept -- drop INLINE_MAX or trim the list")


if __name__ == "__main__":
    main()
