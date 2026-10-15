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
import pathlib
import zipfile

from PIL import Image

SITE = pathlib.Path(__file__).resolve().parent.parent
PACKS_DIR = SITE / "packs"
SCENES_DIR = SITE / "scenes"

# The Android project, which is a separate repo. Written into rather than read from, because the
# site is where the downloadable files live and so the site is where the truth is.
ASSETS = pathlib.Path.home() / "Projects/android-peel/app/src/main/assets"
THUMBS = ASSETS / "catalogue"

BASE = "https://peel.refineco.app"

# The lowest versionCode that can open each kind. Packs have been importable since the first
# release; `.chill` arrived with Peel 2.0.0, versionCode 15. This is per kind today because no
# file yet needs more than its kind's floor -- the day one does, it gets its own number here
# and every older install greys it out with a reason instead of downloading it and failing.
NEEDS = {"pack": 1, "scene": 15}

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
        manifest = json.loads(z.read("manifest.json"))
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

    for p in sorted(PACKS_DIR.glob("*.peel")):
        entry = pack_entry(p)
        thumb_of(p, "tray.png", THUMBS / f"{entry['id']}.png")
        items.append(entry)

    for p in sorted(SCENES_DIR.glob("*.chill")):
        entry = scene_entry(p)
        with zipfile.ZipFile(p) as z:
            inner = json.loads(z.read("scene.json")).get("thumbnail", "thumb.jpg")
        thumb_of(p, inner, THUMBS / f"{entry['id']}.jpg")
        items.append(entry)

    out = ASSETS / "catalogue.json"
    out.write_text(json.dumps({"v": VERSION, "items": items}, indent=2, ensure_ascii=False) + "\n")
    print(f"{out}  ({len(items)} items)")
    for i in items:
        print(f"  {i['kind']:5} {i['id']:18} {i['pieces']:3} pieces  {i['size']:>8}")

    # The overlay. Same items, plus what the app cannot already have.
    overlay = []
    for entry in items:
        src = (PACKS_DIR / f"{entry['id']}.peel" if entry["kind"] == "pack"
               else SCENES_DIR / pathlib.Path(entry["file"]).name)
        inner = "tray.png" if entry["kind"] == "pack" else (
            json.loads(zipfile.ZipFile(src).read("scene.json")).get("thumbnail", "thumb.jpg"))
        item = {k: v for k, v in entry.items() if k != "thumb"}
        item["needs"] = NEEDS[entry["kind"]]
        item["thumb"] = inline_thumb(src, inner, alpha=entry["kind"] == "pack")
        overlay.append(item)

    site_out = SITE / "catalogue.json"
    site_out.write_text(
        json.dumps({"v": VERSION, "items": overlay}, ensure_ascii=False) + "\n")
    size = site_out.stat().st_size
    print(f"\n{site_out}  ({len(overlay)} items, {size / 1024:.0f} KB)")
    if size > 512 * 1024:
        print("  OVER the 512 KB the app will accept -- drop INLINE_MAX or trim the list")


if __name__ == "__main__":
    main()
