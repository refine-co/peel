#!/usr/bin/env python3
"""Build the catalogue Peel's "More fun" screen reads.

The catalogue ships **inside the APK**, not on the site. That is deliberate: `PackDownloader` is
the only code in Peel that opens a socket, and the listing says in writing that the one use is
fetching a pack or a scene you tapped. A screen that fetched a list when it opened would be a
second use and would make that sentence untrue as published. A bundled catalogue costs nothing
to the promise, and the price is only that a newly published item appears in the grid after an
app update — downloading it still works the moment it does.

Everything here is read out of the archives themselves, exactly as `build_scenes.py` builds the
scene cards from the `.chill`. The catalogue therefore cannot describe something the file does
not contain, and the thumbnail in the grid is the file's own.

    python3 site/tools/build_catalogue.py

Writes catalogue.json and one thumbnail per item into the Android project's assets.
"""

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

# Bumped only when the shape changes in a way an older Peel could not read. A build in the wild
# reads whatever it shipped with, so this is really a note to the next person.
VERSION = 1


def human(n: int) -> str:
    """The same size the web page shows, so the two never disagree in front of a user."""
    kb = n / 1024
    return f"{kb/1024:.1f} MB" if kb >= 1024 else f"{kb:.0f} KB"


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


if __name__ == "__main__":
    main()
