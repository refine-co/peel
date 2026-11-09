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
import re
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

# Ready-made Dayleaf pages. One .webp each, no archive and no manifest: a template is a
# picture, and the only thing the app does with it is copy it behind a new page.
#
# These are listed in the site overlay and NOT in the bundled floor. The twelve that ship
# inside the app live in the app's own assets/dayleaf-templates/ and are named in
# DayleafTemplates.kt; putting them in the floor as well would be a second list of the same
# pictures, able to disagree with the first.
TEMPLATES_DIR = SITE / "dayleaf"

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
# Templates arrive with the release that can show them. 2.5.4 is versionCode 54 and is in
# review without the Dayleaf shelf, so the first build that can open a downloaded template is
# 55 — and an older phone must be told that rather than shown a tile that does nothing.
NEEDS = {"pack": 1, "scene": 15, "template": 55}

# One file that needs more than its kind's floor. A paid pack belongs here on the day it is
# published: FreeContent is compiled into the app, so a build released before the pack existed
# has never heard of its fingerprint and would hand it over for nothing. Naming the release
# that does know it means every older install greys the card out with "Update Peel to get
# this" instead -- which is the wrong-in-the-harmless-direction failure.
NEEDS_BY_ID: dict[str, int] = {
    "dead-honest": 23, "sir-crow": 23, "just-lurking": 25,
    # The Deepavali shelf needs Peel 2.5.0 (versionCode 50): that build carries their fingerprints
    # and the animated sheet previews and the price on the card that let them sell themselves.
    # Little Diya and Kolam Lights came off this list when they went free on 1 November 2026:
    # a free pack has no fingerprint to recognise, so an older build can have it.
    "lakshmi": 50, "divine-blessings": 50, "mayil": 50,
    "deepavali-doorstep": 50,
    # The Christmas paid packs, for the same reason as the Deepavali ones: 2.5.0 is the first build
    # that plays a locked pack's sheet and puts the price on its card.
    "cosy-windows": 50, "knitted-friends": 50, "velvet-tartan": 50, "sweet-season": 50,
    # Ho Ho Oops (9 November 2026), the sixth Christmas pack, for the same reason.
    "ho-ho-oops": 50,
    # First Lamp is free, and 2.5.3 (versionCode 53) is the release that can tell: it is
    # the first build that reads a scene's price from this list instead of only from the
    # compiled one. An older build has never heard of the scene, and an unknown scene is
    # paid, so without this it would offer the thing and then refuse it. Greyed out with
    # "Update Peel to get this" is the right failure.
    "first-lamp": 53,
    # Christmas Eve is free, and for the same reason as First Lamp needs 2.5.3: older builds treat
    # an unknown scene as sold.
    "christmas-eve": 53,
    # The six paid Christmas scenes: 2.5.0 is the first build that puts a scene's price on its card.
    "christmas-market": 50,
    "aurora-cabin": 50,
    "santas-workshop": 50,
    "last-tram-home": 50,
    "gingerbread-kitchen": 50,
    "rooftop-sleigh": 50,
}

# Packs that are sold. Peel 2.4.1 (versionCode 25) reads `paid` from the fetched list, so a paid
# pack published from now on needs only an entry here and `needs` of 25 in NEEDS_BY_ID: no new
# release has to add its fingerprint. Builds before 2.4.1 ignore the flag, which is why the new
# pack's `needs` must be 25 -- those builds then grey the card instead of importing it free.
# Dead Honest and Sir Crow are also compiled into the app (FreeContent.PAID_PACKS) and stay so.
#
# Taking a pack off this list is not enough on its own, and that is the one thing to know here.
# The compiled list is consulted first and can only add to the price, never remove it: a build
# that carries a pack's fingerprint in FreeContent.PAID_PACKS locks it whatever this file says.
# So Little Diya and Kolam Lights were **reissued** on 1 November 2026 instead. Their manifests
# carry a `reissue` field, which moves the fingerprint, and an unrecognised pack is free by
# design -- so every install already out there hands them over for nothing as soon as it
# refreshes this list, with no release and no update. Their old fingerprints stay in
# FreeContent.PAID_PACKS, as that list is append-only: they now describe copies this site no
# longer serves.
PAID_IDS: set[str] = {
    "dead-honest", "sir-crow",
    "lakshmi", "divine-blessings", "mayil",
    "cosy-windows", "knitted-friends", "velvet-tartan", "sweet-season", "ho-ho-oops",
    # The two paid scenes. They were never listed here, because until 2.5.3 the app decided
    # a scene entirely from FreeContent.SCENES and an unknown scene was paid, so the flag
    # had nothing to do. 2.5.3 lets the catalogue say a scene is free -- which is what frees
    # a new scene without a release -- and the price of that is that a paid scene now has to
    # say so here. Leaving them out would hand them over.
    "knock-twice", "deepavali-doorstep",
    # Christmas 2026, six paid scenes (9 Nov). Named here and nowhere else: that is what sells a scene.
    "christmas-market", "aurora-cabin", "santas-workshop", "last-tram-home", "gingerbread-kitchen", "rooftop-sleigh",
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
    "first-lamp": "festivals",
    "christmas-eve": "festivals",
    "christmas-market": "festivals",
    "aurora-cabin": "festivals",
    "santas-workshop": "festivals",
    "last-tram-home": "festivals",
    "gingerbread-kitchen": "festivals",
    "rooftop-sleigh": "festivals",
    # Christmas 2026: one free greeting pack and four paid animated packs, 9 November 2026.
    "merry-bright": "festivals",
    "cosy-windows": "festivals",
    "ho-ho-oops": "festivals",
    "knitted-friends": "festivals",
    "velvet-tartan": "festivals",
    "sweet-season": "festivals",
}

# What leads More fun. The list's own order is the page's order: the app shows categories in the
# order it first meets them and cards in the order they are listed, so a shelf takes the top by
# being named first here and gives it back by moving down, with no release either way.
# Deepavali leads from 1 November 2026: Halloween is behind us, the festival is a week out, and
# the shelf now has two free sheets in it rather than one. Halloween keeps second place rather
# than going to the back, because its packs are the ones the listing screenshots show, and the
# cats follow. Categories left out of this list follow, in the order the packs happen to be in.
# Inside Deepavali the scene leads, then the paid hero, and the free greeting sits fourth, where
# the person who came for a free greeting still finds it without the first card being a free one.
CATEGORY_ORDER = ["festivals", "cats", "chat", "cosy", "halloween"]
# Christmas leads from 9 November 2026: the free scene, then the free greeting pack, then the four
# paid packs; Deepavali (8 November) is behind us and follows. Halloween went to the back of
# CATEGORY_ORDER the same day, behind the year-round shelves.
SHELF_ORDER = [
    "christmas-eve", "christmas-market", "aurora-cabin", "santas-workshop", "last-tram-home", "gingerbread-kitchen", "rooftop-sleigh",
    "merry-bright", "ho-ho-oops", "cosy-windows", "knitted-friends", "velvet-tartan",
    "sweet-season", "first-lamp", "deepavali-doorstep", "divine-blessings", "lakshmi", "happy-deepavali",
    "little-diya", "mayil", "kolam-lights",
]


# A paid pack's file does not sit at packs/<id>.peel, where anybody can type it. It sits in a
# directory nobody can guess, and no page on the site links to it -- the only place the path is
# published is this catalogue, which is what the app reads. That is as far as a static host can
# go: GitHub Pages serves a GET to the app and to a browser identically, so a real gate would
# need a host that can check something, and the gate that does hold is in Peel, at import,
# against the unlock on the phone. This only stops the file being one click or one guess away.
# A token here is permanent: change one and every install with the old list 404s on that pack
# until it refreshes. Which is also why a pack that stops being sold keeps its directory rather
# than moving back to packs/<id>.peel: Just Lurking, Little Diya and Kolam Lights are all free
# and all still in here. Nothing is gained by moving the file and a stale list would 404.
VAULT: dict[str, str] = {
    "dead-honest": "k7qf3xd92m",
    "sir-crow": "b4htz8rn51",
    "just-lurking": "w9vmc26pdj",
    # The Deepavali shelf (2.5.0). Permanent once published, like the three above.
    "lakshmi": "4czrg7tcz5",
    "divine-blessings": "lmmj3f1dbk",
    "little-diya": "mxacof091w",
    "mayil": "0sxrvxrdjl",
    "kolam-lights": "lvt40sbtfy",
    # Christmas 2026. Permanent once published.
    "cosy-windows": "qx85gxsztu",
    "knitted-friends": "itxy9f7tsw",
    "velvet-tartan": "3kw1ftjsvc",
    "sweet-season": "md7udw71bs",
    "ho-ho-oops": "o8pn3ip0sl",
}

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


# A template tile is a third of the sheet's width, not half a phone like a More fun card, so
# it needs less picture than INLINE_MAX. Forty of them at 192 px put the list at 441 KB
# against the 512 KB the app accepts, which is too little room for the next pack; at 132 px
# they are legible at the size they are actually drawn and the list has somewhere to grow.
TEMPLATE_INLINE_MAX = 132


def inline_picture(path: pathlib.Path) -> str:
    """Like [inline_thumb], for a picture that is a file rather than an archive member."""
    im = Image.open(path)
    im.thumbnail((TEMPLATE_INLINE_MAX, TEMPLATE_INLINE_MAX), Image.LANCZOS)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "WEBP", quality=INLINE_QUALITY, method=6)
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
        "file": f"{BASE}/{path.relative_to(SITE).as_posix()}",
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


# What each ready-made page is called in the app.
#
# Written here rather than derived from the file name, because the file name is an id and a
# title is English somebody reads: "cat-donut-bed" is not a name for anything. These are not
# translated — the same is true of every pack title the catalogue carries, since the list is
# one file served to every language. The twelve bundled templates DO have translated names,
# because those are string resources in the app.
#
# A template with no title here stops the build rather than shipping as its own slug.
TEMPLATE_TITLES = {
    "alarm-clock": "Busy day",
    "autumn": "Autumn",
    "beach": "Beach",
    "books-lamp": "Reading",
    "bubble-tea": "Bubble tea",
    "burger": "Something good",
    "bus": "On the way",
    "cake-slice": "Cake",
    "camper-van": "Road trip",
    "cat-donut-bed": "Nap",
    "chocolate-box": "Date night",
    "christmas-fairy-lights": "Fairy lights",
    "christmas-gingerbread": "Gingerbread house",
    "christmas-santa": "Father Christmas",
    "christmas-tropical": "Christmas in the heat",
    "cupcake": "Baking day",
    "durian": "Fruit season",
    "family-day": "Family day",
    "graduation": "Graduation",
    "hills-trails": "Hills and trails",
    "laptop": "At the desk",
    "lazy-weekend": "Lazy weekend",
    "love-notes": "Love notes",
    "making-things": "Making things",
    "music": "Music",
    "new-baby": "New baby",
    "new-home": "New home",
    "new-year": "New year",
    "night-market": "Night market",
    "noodle-bowl": "Dinner at home",
    "open-house": "Open house",
    "raincoat-duck": "Monsoon",
    "shiba": "Dog day",
    "spring": "Spring",
    "tea-time": "Tea time",
    "thank-you": "Thank you",
    "travel": "Travel",
    "two-bears": "Friends",
    "wedding": "Wedding",
    "winged-envelope": "Miss you",
}

def template_entry(path: pathlib.Path) -> dict:
    """One ready-made Dayleaf page. No fingerprint: the app reads a template as free."""
    name = path.stem
    title = TEMPLATE_TITLES.get(name)
    if title is None:
        raise SystemExit(f"{name}: add a title to TEMPLATE_TITLES before publishing it")
    size = path.stat().st_size
    # The app fetches a template through PackDownloader.fetchImage, which refuses anything
    # over MAX_IMAGE_BYTES. Caught here, where it is a re-encode, rather than on a phone,
    # where it is a tap that does nothing.
    if size > 256 * 1024:
        raise SystemExit(f"{name}: {size // 1024} KB is over the 256 KB the app will fetch")
    return {
        "id": name,
        "kind": "template",
        "title": title,
        "pieces": 0,
        "animated": False,
        "bytes": size,
        "size": human(size),
        "file": f"{BASE}/dayleaf/{path.name}",
    }


# Moving parts for a downloadable template, written by export_site_fixtures.py in the
# peel-stickers repo. `file` stays the whole picture, because that is what every older build
# fetches; `plate` is the same picture with the moving pieces painted out, and the app reads it
# only together with the layers that fill those holes. Builds before moving pieces ignore both
# fields, so this needs no `needs` bump.
TEMPLATE_FX_DIR = TEMPLATES_DIR / "fx"
# PackDownloader.nameOf: at most 64 characters of letters, digits, '.', '_' and '-', no '..'.
# RemoteTemplateFixtures.SAFE_ID: the app keys a template's saved layers by its id.
TEMPLATE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
FIXTURE_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,58}\.webp")
FIXTURE_KEYS = ("pivotX", "pivotY", "sway", "bob", "breathe", "drift", "flicker", "additive")


def template_motion(name: str) -> dict:
    d = TEMPLATE_FX_DIR / name
    spec_file = d / "fixtures.json"
    if not spec_file.is_file():
        return {}
    spec = json.loads(spec_file.read_text())
    files = [spec["plate"]] + [f["file"] for f in spec["fixtures"]]
    # The app takes these all or nothing (Catalogue.motionOf): one name or number it refuses
    # and the whole template is offered still. So the build refuses first, here, loudly.
    if not TEMPLATE_ID.fullmatch(name):
        raise SystemExit(f"{name}: a moving template's id must match {TEMPLATE_ID.pattern}")
    for f in files:
        if not FIXTURE_NAME.fullmatch(f) or ".." in f:
            raise SystemExit(f"{name}/{f}: the app only fetches names like {FIXTURE_NAME.pattern}")
    for f in spec["fixtures"]:
        for k in ("pivotX", "pivotY", "sway", "bob", "breathe", "drift", "flicker"):
            v = f.get(k, 0)
            if not (isinstance(v, (int, float)) and 0 <= v <= 1):
                raise SystemExit(f"{name}/{f['file']}: {k}={v!r} is outside 0..1, which the app clamps")
    for f in files:
        size = (d / f).stat().st_size
        if size > 256 * 1024:
            raise SystemExit(f"{name}/{f}: {size // 1024} KB is over the 256 KB the app will fetch")
    lights = sum(1 for f in spec["fixtures"] if f.get("additive"))
    if lights > 3 or len(spec["fixtures"]) - lights > 3:
        raise SystemExit(f"{name}: the app reads at most three lights and three pieces")
    url = f"{BASE}/dayleaf/fx/{name}"
    return {
        "plate": f"{url}/{spec['plate']}",
        "fixtures": [
            {"file": f"{url}/{f['file']}", **{k: f[k] for k in FIXTURE_KEYS if k in f}}
            for f in spec["fixtures"]
        ],
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
    # Free packs sit in packs/; a paid one sits in its VAULT directory under it. Sorted by id so
    # the order is the one sorting packs/<name> gave before, so moving a pack cannot reorder the grid.
    pack_files = sorted(
        list(PACKS_DIR.glob("*.peel")) + list(PACKS_DIR.glob("*/*.peel")),
        key=lambda f: f.name,
    )
    sources = {f.stem: f for f in pack_files}
    # The one check that keeps a paid pack off the guessable path. Without it, rebuilding a paid
    # pack straight into packs/ would quietly publish it at packs/<id>.peel again.
    for pack_id, token in VAULT.items():
        found = sources.get(pack_id)
        if found is not None and found.parent.name != token:
            raise SystemExit(
                f"{pack_id} is a paid pack: move it to packs/{token}/ before publishing")
    # Packs only. A scene is sold by being named in PAID_IDS and nothing else: the .chill files
    # sit in scenes/ under their own names, there is no unguessable directory for them, and the
    # gate that holds for a scene is in Peel at import.
    for pack_id in (PAID_IDS & set(sources)) - set(VAULT):
        raise SystemExit(f"{pack_id} is sold but has no VAULT directory")
    for p in pack_files:
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

    # Written into the bundled floor as well as the overlay, since 2.5.3: the floor is what
    # the grid shows on first run and when the fetch fails, and a scene with no `paid` on it is
    # now read as free. Older builds read the field and already agree with it.
    for entry in items:
        if entry["id"] in PAID_IDS:
            entry["paid"] = True

    for entry in items:
        category = CATEGORY_BY_ID.get(entry["id"])
        if category:
            entry["category"] = category
        else:
            print(f"  note: {entry['id']} has no category, so Peel shows it under More")

    items.sort(key=lambda e: (
        CATEGORY_ORDER.index(e["category"]) if e.get("category") in CATEGORY_ORDER
        else len(CATEGORY_ORDER),
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
        src = (sources[entry["id"]] if entry["kind"] == "pack"
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

    # Templates, overlay only. They carry their own picture inline like everything else here,
    # because fetching forty thumbnails one at a time would be forty sockets and would tell the
    # host who opened the Dayleaf shelf and how often. The twelve bundled ones are deliberately
    # absent: the app already has those and listing them would make it download a copy.
    bundled_templates = {
        "birthday", "good-night", "rainy-day", "sunny-day", "garden", "study",
        "latte", "cat", "kopitiam", "sprout", "lantern", "christmas-tree",
    }
    templates = 0
    for p in sorted(TEMPLATES_DIR.glob("*.webp")):
        if p.stem in bundled_templates:
            raise SystemExit(f"{p.stem} ships inside the app; remove site/dayleaf/{p.name}")
        entry = template_entry(p)
        entry["needs"] = NEEDS["template"]
        entry["thumb"] = inline_picture(p)
        entry.update(template_motion(p.stem))
        overlay.append(entry)
        templates += 1
    if templates:
        print(f"  {templates} dayleaf templates")

    site_out = SITE / "catalogue.json"
    site_out.write_text(
        json.dumps({"v": VERSION, "categories": CATEGORIES, "items": overlay}, ensure_ascii=False) + "\n")
    size = site_out.stat().st_size
    print(f"\n{site_out}  ({len(overlay)} items, {size / 1024:.0f} KB)")
    if size > 512 * 1024:
        print("  OVER the 512 KB the app will accept -- drop INLINE_MAX or trim the list")


if __name__ == "__main__":
    main()
