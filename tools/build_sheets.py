#!/usr/bin/env python3
"""Build the sticker sheets on packs.html, and render each one to a PNG.

The stickers come out of the .peel archives themselves, so the page and the
picture can never show something the pack does not contain. Run from anywhere:

    python3 site/tools/build_sheets.py

Needs Google Chrome for the PNG render; pass --no-png to skip it.
"""

import colorsys
import datetime
import html
import io
import json
import pathlib
import re
import subprocess
import sys
import zipfile
from urllib.parse import quote

SITE = pathlib.Path(__file__).resolve().parent.parent
SPECS = pathlib.Path.home() / "Projects/android-peel/tools/packs/site"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# "Open in Peel", which since Peel 2.0.0 means what it says: the link carries the file's own
# URL and Peel fetches it (PackDownloader — HTTPS, this host only, downloads only). Before
# 2.0.0 Peel had no network permission, so the same link could only open its file picker and
# hope the person found what the browser had just downloaded, which felt as bad as it sounds.
#
# Older installs ignore the query and still get the picker, so this is safe to publish ahead of
# 2.0.0 reaching Play. What is NOT safe yet is promoting this to the primary button and
# dropping the "download first" line — do that once 2.0.0 is live, or people on 1.7.1 get the
# picker with no instructions.
#
# The package is pinned to the release application id, so a debug build can never receive it,
# and browser_fallback_url sends anyone without Peel to the listing.
SITE_URL = "https://peel.refineco.app"
OTHER_SHELF = "Other packs"
COMMUNITY_SHELF = "From the community"


def shelf_of(slug):
    """Where the app lists this pack, and whether it is sold, read from catalogue.json.

    The website no longer hands out the files: Peel downloads them itself from More fun, so a
    sheet says where to find its pack in the app instead. The catalogue is the file the app
    reads, so the page cannot send anyone to a shelf the app does not have.
    """
    file = SITE / "catalogue.json"
    data = json.loads(file.read_text()) if file.exists() else {}
    names = {c["id"]: c.get("en", c["id"]) for c in data.get("categories", [])}
    for item in data.get("items", []):
        if item["id"] == slug:
            key = item.get("category")
            if COMMUNITY.get(slug):
                return COMMUNITY_SHELF, bool(item.get("paid"))
            return (names.get(key) if key else None) or OTHER_SHELF, bool(item.get("paid"))
    return OTHER_SHELF, False

PLAY_URL = "https://play.google.com/store/apps/details?id=my.refineco.peel"


def pack_file(slug):
    """Where a pack's archive actually is.

    A free pack sits at packs/<slug>.peel. A paid one sits in the directory build_catalogue.py
    keeps it in, so the file is not one guessed URL away from anybody on the web. Both are read
    the same way here: this page is built from the archives, whatever their path.
    """
    direct = SITE / "packs" / f"{slug}.peel"
    if direct.exists():
        return direct
    found = sorted((SITE / "packs").glob(f"*/{slug}.peel"))
    if not found:
        raise SystemExit(f"no archive for {slug} under packs/")
    return found[0]


def peel_import_link(path):
    """The intent link that hands Peel the file at `path` on this site."""
    url = quote(f"{SITE_URL}/{path}", safe="")
    return (
        f"intent://import?url={url}#Intent;scheme=peel;package=my.refineco.peel;"
        "S.browser_fallback_url=https%3A%2F%2Fplay.google.com%2Fstore%2Fapps%2Fdetails"
        "%3Fid%3Dmy.refineco.peel;end"
    )


# What a paid pack's page says in place of the "download first" line. Same promise as a paid
# scene (build_scenes.py): one purchase, once, and the file downloads either way.
UNLOCK_NOTE = ("This one needs Peel unlocked \u2014 a single purchase, once, that opens every paid "
               "pack and scene. Open Peel and tap More fun: the sheet downloads onto the phone "
               "that owns the unlock, and is not handed out from this page.")

PACKS = [
    # The Deepavali shelf leads, hero first (see build_catalogue.SHELF_ORDER). Taken off the front
    # again after the festival by moving these below the Halloween packs.
    {
        "slug": "divine-blessings",
        "title": "Divine Blessings",
        "spec": None,
        "c1": "#4a1d6e", "c2": "#ffb347",
        "sub": "12 animated stickers \u00b7 twelve deities, each in a glow of its own colour, with a blessing to send",
        "section": "Deepavali",
    },
    {
        "slug": "lakshmi",
        "title": "Lakshmi",
        "spec": None,
        "c1": "#7a1f3d", "c2": "#ffc857",
        "sub": "19 animated stickers \u00b7 Lakshmi on her lotus, with coins, elephants and lamps, for good wishes",
        "section": None,
    },
    {
        "slug": "happy-deepavali",
        "title": "Happy Deepavali",
        "spec": None,
        "c1": "#8a3b12", "c2": "#ffd166",
        "sub": "16 stickers \u00b7 greetings in English and Tamil: Happy Deepavali, Sending love, Welcome home",
        "section": None,
    },
    {
        "slug": "little-diya",
        "title": "Little Diya",
        "spec": None,
        "c1": "#5a2a0c", "c2": "#ff9f1c",
        "sub": "12 animated stickers \u00b7 a clay lamp whose flame is its mood: Happy Deepavali, Ring the bell, So shy",
        "section": None,
    },
    {
        "slug": "mayil",
        "title": "Mayil",
        "spec": None,
        "c1": "#0b4f6c", "c2": "#2ec4b6",
        "sub": "12 animated stickers \u00b7 a peacock whose tail opens and feather eyes light up: Welcome, Dance with me, Hooray!",
        "section": None,
    },
    {
        "slug": "kolam-lights",
        "title": "Kolam Lights",
        "spec": None,
        "c1": "#1b1f4a", "c2": "#f7b32b",
        "sub": "8 animated stickers \u00b7 kolam drawn in light, dot by dot: Light it up, Deepavali glow, Sparkle ring",
        "section": None,
    },
    {
        "slug": "halloween",
        "title": "Peel Halloween",
        "spec": "halloween-captions.json",
        "c1": "#7b5ea7", "c2": "#ff6b35",
        "sub": "20 stickers · a ghost, a black cat, a bat, a pumpkin and a one-eyed monster",
        "after": 'Download first — <strong>Open in Peel</strong> then picks it up from your Downloads folder.',
        "section": None,
    },
    {
        "slug": "halloween-night",
        "title": "Halloween Night",
        "spec": "halloween-night.json",
        "c1": "#3f3d7a", "c2": "#c084fc",
        "sub": "20 stickers \u00b7 a mummy, a skeleton, a spider, a werewolf pup and a potion cauldron",
        "after": 'Download first \u2014 <strong>Open in Peel</strong> then picks it up from your Downloads folder.',
        "section": None,
    },
    {
        "slug": "midnight-replies",
        "title": "Midnight Replies",
        "spec": "midnight-replies.json",
        "c1": "#2b1b4a", "c2": "#ff8a3d",
        "sub": "18 stickers · a black witch cat for the moments only a chat has: Seen, Typing, Still waiting",
        "after": 'Download first — <strong>Open in Peel</strong> then picks it up from your Downloads folder.',
        "section": None,
    },
    {
        "slug": "ghost-says",
        "title": "Ghost Says",
        "spec": "ghost-says.json",
        "c1": "#8b7bd8", "c2": "#f4a6c8",
        "sub": "12 animated stickers · one small ghost, from Boo! to Haunting you",
        "after": 'Download first — <strong>Open in Peel</strong> then picks it up from your Downloads folder.',
        "section": None,
    },
    {
        "slug": "moth-lights",
        "title": "Moth Lights",
        "spec": "moth-lights.json",
        "c1": "#1f3b3a", "c2": "#7dffb0",
        "sub": "12 animated stickers · a moth whose wings glow, for the late-night messages: Thinking of you, Can't sleep, Goodnight",
        "after": 'Download first — <strong>Open in Peel</strong> then picks it up from your Downloads folder.',
        "section": None,
    },
    {
        "slug": "dead-honest",
        "title": "Dead Honest",
        "spec": "dead-honest.json",
        "c1": "#3a2a2a", "c2": "#ff4d5e",
        "sub": "12 animated stickers · a deadpan skeleton for the dry replies: Dead tired, Bored to death, I'm fine",
        "after": UNLOCK_NOTE,
        "section": None,
    },
    {
        "slug": "sir-crow",
        "title": "Sir Crow",
        "spec": "sir-crow.json",
        "c1": "#2a2f45", "c2": "#a9c4ff",
        "sub": "12 animated stickers · a top-hatted crow for the polite replies: Good evening, Much obliged, How dare you",
        "after": UNLOCK_NOTE,
        "section": None,
    },
    {
        "slug": "low-light",
        "title": "Low Light",
        "c1": "#3a2410", "c2": "#ffb13d",
        "sub": "12 animated stickers · a jack-o'-lantern lit from inside, whose candle is its mood: Fully charged, Running on empty, Lights out",
        "story": "There is a candle inside him and some days it is barely there. He is not sad about it. He slumps, he flickers, he goes out altogether and sits in the dark with a wisp of smoke — and then something small works, and he is blazing again.",
        "new_until": "2026-12-01",
        "after": 'Download first — <strong>Open in Peel</strong> then picks it up from your Downloads folder.',
        "section": None,
    },
    {
        "slug": "just-lurking",
        "title": "Just Lurking",
        "c1": "#15151c", "c2": "#c6f24a",
        "sub": "12 animated stickers · a black cat who is never more than two glowing eyes in the dark: I'm watching, I saw that, No comment",
        "story": "She has read every message. She has replied to none of them. All you ever see is two eyes in the dark, and they are definitely still open.",
        "new_until": "2026-12-01",
        "after": UNLOCK_NOTE,
        "section": "Halloween",
    },
    {
        "slug": "reactions",
        "title": "Reactions",
        "spec": "humans-captions.json",
        "c1": "#ff4d8d", "c2": "#38bdf8",
        "sub": "10 animated stickers · the faces people actually pull, moving",
        "after": 'Download first — <strong>Open in Peel</strong> then picks it up from your Downloads folder.',
        "section": "From the makers",
    },
    {
        "slug": "say-it",
        "title": "Say it",
        "spec": "say-it.json",
        "c1": "#2ec4b6", "c2": "#ffc93c",
        "sub": "30 stickers · the words people actually send, from LOL to Good night",
        "after": "Also built into Peel. This file is for sharing it with someone who has not installed the app yet.",
        "section": None,
    },
]

# the sheet looks printed, not laid out: every sticker sits at its own slight angle
TILTS = (-2.6, 1.8, -1.1, 2.4, -3.0, 0.9, -1.9, 2.8, -0.6, 1.4, -2.2, 3.0)


def captions_of(pack):
    """The captions for one pack, from its spec file or, failing that, from its own manifest.

    Peel's own packs are written as a spec in the Android repo and the archive is built from
    it, so the spec is the source. A pack somebody sent in has no spec and never will — but
    its manifest carries the same three things, because `accessibilityText` and `emojis` are
    what the app writes into every pack it exports. So the sheet is built from the archive,
    which also means the page cannot show a caption the pack does not contain.
    """
    if pack.get("spec"):
        return captions(SPECS / pack["spec"])
    with zipfile.ZipFile(pack_file(pack["slug"])) as z:
        return captions_from(json.loads(z.read("manifest.json")))


def captions(spec_path):
    return captions_from(json.load(open(spec_path)))


def captions_from(data):
    items = data["stickers"] if isinstance(data, dict) else data
    out = []
    for s in items:
        cap = s.get("caption")
        if not cap:
            text = s.get("accessibilityText", "")
            # "text that reads "Boo!"" for most packs; "with text "Ganesha's grace"" and
            # "the Tamil call Vetrivel" for the Deepavali ones. A sticker whose words are Tamil
            # script and described only as "the Tamil word for blessing" gets no caption: the
            # picture carries the word, and a made-up English label under it would be wrong.
            m = (re.search(r'reads "([^"]+)"', text)
                 or re.search(r'with text "([^"]+)"', text)
                 or re.search(r'Tamil (?:call|mantra) ([^.]+)\.$', text))
            cap = m.group(1) if m else ""
        out.append((cap, s.get("accessibilityText", ""), "".join(s.get("emojis", []))))
    return out


def shades(slug, files):
    """Two colours for the sheet's banner, taken from the pack's own stickers.

    A pack somebody sent in brings no palette with it, and picking one by hand does not scale.
    The hue comes from the stickers themselves so the sheet looks like what is in it; the
    lightness does not, because the banner carries white text over the gradient and a colour
    sampled straight out of a drawing is as likely to be pale yellow as it is navy. Fixing the
    two lightnesses is what keeps every sent-in sheet readable without anybody checking.
    """
    from PIL import Image

    hues, weights = [], []
    for name in files[:6]:
        im = Image.open(SITE / "packs" / "img" / slug / "stickers" / name).convert("RGBA")
        im.thumbnail((48, 48))
        for r, g, b, a in im.getdata():
            if a < 128:
                continue
            h, l, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            # Grey pixels have a meaningless hue, and an outline is mostly grey.
            if sat < 0.25 or l < 0.12 or l > 0.93:
                continue
            hues.append(h)
            weights.append(sat)

    if not hues:
        return "#2b2440", "#8b7bd8"          # Peel's own purple, for a pack with no colour in it

    # Hue is an angle, so the mean has to go round the circle rather than along a line —
    # averaging 0.02 and 0.98 the ordinary way gives cyan out of two reds.
    import math
    x = sum(w * math.cos(2 * math.pi * h) for h, w in zip(hues, weights))
    y = sum(w * math.sin(2 * math.pi * h) for h, w in zip(hues, weights))
    hue = (math.atan2(y, x) / (2 * math.pi)) % 1.0

    def hex_at(lightness, saturation):
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))

    return hex_at(0.22, 0.42), hex_at(0.58, 0.72)


# The heading the community sheets sit under, and the place build_deck.py puts their rail.
# Spelled once: build_deck.py fills the markers this file writes, and a mismatch would leave
# the rail nowhere.
COMMUNITY_SECTION = "From the community"
COMMUNITY_NOTE = ("Packs people made in Peel and sent in. Each one is credited to whoever "
                  "made it.")
RAIL_START = "<!-- community-rail:start -->"
RAIL_END = "<!-- community-rail:end -->"

_community_file = SITE / "community.json"
COMMUNITY = json.loads(_community_file.read_text()) if _community_file.exists() else {}


def sent_in():
    """Every pack in site/packs/ that is not one of ours, described well enough to render.

    Publishing a pack somebody sent in writes it here and into catalogue.json, and the app
    then finds it. The website would not: PACKS above is hand-written, build_deck.py walks the
    same list, and a pack missing from it is missing from both the rail and the sheets — which
    is exactly what happened to the first one. Deriving an entry from the archive closes that
    by construction, so no pack can reach the app and not the site.
    """
    known = {p["slug"] for p in PACKS}
    out = []
    for path in sorted(
        list((SITE / "packs").glob("*.peel")) + list((SITE / "packs").glob("*/*.peel")),
        key=lambda f: f.name,
    ):
        if path.stem in known:
            continue
        with zipfile.ZipFile(path) as z:
            manifest = json.loads(z.read("manifest.json"))
            files = sorted(
                pathlib.Path(n).name for n in z.namelist() if n.startswith("stickers/")
            )
        kind = "animated stickers" if manifest.get("animated") else "stickers"
        title = manifest.get("name") or path.stem
        sent = COMMUNITY.get(path.stem)
        # The credit, when it says something the title has not. A pack of ours carries its own
        # name here, and "Oyen Kampung · by Oyen Kampung" helps nobody.
        #
        # "Sent in by" is only said when community.json says so. The old note here was right
        # that the archive alone cannot tell a submission from one of ours published the same
        # way — so the wording now follows the file that knows, and a pack missing from it
        # still gets the quieter "by".
        credit = (sent or {}).get("credit") or (manifest.get("publisher") or "").strip()
        if credit and credit != title:
            byline = f" · {'sent in by' if sent else 'by'} {html.escape(credit)}"
        else:
            byline = ""
        out.append({
            "slug": path.stem,
            "title": title,
            "spec": None,
            "sub": f"{len(files)} {kind}{byline}",
            "after": 'Download first — <strong>Open in Peel</strong> then picks it up from your Downloads folder.',
            # The first one carries the heading, and the rest fall under it — the same way
            # "Festive" and "From the makers" work above. Sorted by slug, so which pack is
            # first does not wander between builds.
            "section": COMMUNITY_SECTION if sent and not any(p.get("section") == COMMUNITY_SECTION for p in out) else None,
            "files": files,
        })
    return out


# Animated stickers go on the page smaller than they ship: the pack's 512 px files run 300-400 KB
# each, and a twelve-sticker sheet of them is the heaviest thing on the site. 256 px is what the
# sheet draws them at (twice that on a dense screen), and every second frame is dropped with its
# time added to the one before, so the motion keeps its pace at about a quarter of the weight.
SLIM_SIDE = 256
SLIM_QUALITY = 70
CARD_SIDE = 128
CARD_QUALITY = 60


def slim_animated(raw, side=SLIM_SIDE, quality=SLIM_QUALITY, step=2):
    """An animated WebP at `side` px, or None when the file is a single frame."""
    from PIL import Image, ImageSequence

    im = Image.open(io.BytesIO(raw))
    if getattr(im, "n_frames", 1) < 2:
        return None
    frames, times = [], []
    for k, frame in enumerate(ImageSequence.Iterator(im)):
        ms = frame.info.get("duration", 40)
        if k % step:
            times[-1] += ms
            continue
        f = frame.convert("RGBA")
        f.thumbnail((side, side), Image.LANCZOS)
        frames.append(f.copy())
        times.append(ms)
    out = io.BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=times,
                   loop=0, quality=quality, method=4)
    return out.getvalue()


def still_of(raw, side=SLIM_SIDE):
    from PIL import Image

    im = Image.open(io.BytesIO(raw))
    im.seek(0)
    f = im.convert("RGBA")
    f.thumbnail((side, side), Image.LANCZOS)
    out = io.BytesIO()
    f.save(out, "WEBP", quality=72, method=4)
    return out.getvalue()


def extract(slug):
    """Unpack the .peel into the site so the page serves the real stickers.

    An animated pack's stickers are written slimmed, with a still of each beside them in
    `stills/` for visitors who ask their device for less motion, and one small animated
    `card.webp` for the rail. Still packs are written exactly as they ship.
    """
    dest = SITE / "packs" / "img" / slug / "stickers"
    dest.mkdir(parents=True, exist_ok=True)
    stills = dest.parent / "stills"
    with zipfile.ZipFile(pack_file(slug)) as z:
        names = sorted(n for n in z.namelist() if n.startswith("stickers/"))
        animated = bool(json.loads(z.read("manifest.json")).get("animated"))
        for i, n in enumerate(names):
            raw = z.read(n)
            base = pathlib.Path(n).name
            slim = slim_animated(raw) if animated else None
            if slim is None:
                (dest / base).write_bytes(raw)
                continue
            (dest / base).write_bytes(slim)
            stills.mkdir(exist_ok=True)
            (stills / base).write_bytes(still_of(raw))
            if i == 0:
                card = slim_animated(raw, CARD_SIDE, CARD_QUALITY, step=3)
                if card:
                    (dest.parent / "card.webp").write_bytes(card)
    return [pathlib.Path(n).name for n in names]


def is_animated_pack(slug):
    return (SITE / "packs" / "img" / slug / "stills").is_dir()


def sticker(slug, base, cap, alt, emo, i, lazy=True):
    src = f"packs/img/{slug}/stickers/{base}"
    load = ' loading="lazy"' if lazy else ""

    def face(cls, hidden=""):
        img = f'<img class="{cls}" src="{src}" alt=""{hidden}{load} decoding="async">'
        if not is_animated_pack(slug):
            return img
        # A visitor who asks for less motion gets the first frame: a WebP cannot be paused, so
        # the still is a different file chosen by the same media query the rest of the page uses.
        return (f'<picture><source media="(prefers-reduced-motion: reduce)" '
                f'srcset="packs/img/{slug}/stills/{base}">{img}</picture>')

    return (
        f'      <div class="peel reveal" style="--tilt:{TILTS[i % len(TILTS)]}deg" tabindex="0" '
        f'role="img" aria-label="{html.escape(alt)}">\n'
        f'        {face("ghost", " aria-hidden=" + chr(34) + "true" + chr(34))}\n'
        f'        {face("face")}\n'
        f'        <span class="curl"></span>\n'
        f'        <span class="label">{html.escape(cap)} {emo}</span>\n'
        f'      </div>'
    )


# A pack published recently gets its own billing above the wheel, with a few words about who
# the character is rather than what the pack contains. `new_until` is a date and not a flag,
# so the block empties itself: a "new" that has to be cleared by hand is how a page ends up
# announcing something that shipped a month ago.
NEW_START = "<!-- new:start -->"
NEW_END = "<!-- new:end -->"


def just_landed(packs, today):
    """The billing block for packs still inside their `new_until` date, newest first."""
    cards = []
    for pack in sorted((p for p in packs if p.get("story") and p.get("new_until", "") >= today),
                       key=lambda p: p["new_until"], reverse=True):
        slug = pack["slug"]
        shots = sorted((SITE / "packs" / "img" / slug / "stickers").glob("*.webp"))[:4]
        tiles = "".join(
            f'<img src="packs/img/{slug}/stickers/{f.name}" alt="" width="120" height="120" loading="lazy">'
            for f in shots)
        kind = pack["sub"].split("\u00b7")[0].strip()
        cards.append(
            f'<section class="sheet" style="--c1:{pack["c1"]};--c2:{pack["c2"]}">\n'
            f'  <div class="sheet-head">\n'
            f'    <h3 class="sheet-title">{html.escape(pack["title"])}</h3>\n'
            f'    <p class="sheet-sub">{kind}</p>\n'
            f'  </div>\n'
            f'  <div class="sheet-body">\n'
            f'    <p class="scene-blurb" style="margin-bottom:.9rem">{html.escape(pack["story"])}</p>\n'
            f'    <div class="sheet-grid">{tiles}</div>\n'
            f'  </div>\n'
            f'  <div class="sheet-foot">\n'
            f'    <a class="btn" href="#{slug}">See all twelve</a>\n'
            f'  </div>\n'
            f'</section>')
    if not cards:
        return ""
    return ('<section class="rail-section" id="just-landed" aria-labelledby="just-landed-h">\n'
            '<h2 id="just-landed-h">Just landed</h2>\n' + "\n".join(cards) + '\n</section>')


def sheet_html(pack, files, caps, size_kb):
    slug = pack["slug"]
    cells = "\n".join(
        sticker(slug, f, c, a, e, i) for i, (f, (c, a, e)) in enumerate(zip(files, caps))
    )
    head = ""
    # The community heading carries its wheel, the way the packs and scenes headings carry
    # theirs. Written as an empty region here and filled by build_deck.py, which is the only
    # file that knows how to draw a rail. Putting the rail beside the packs rail instead left
    # two wheels stacked at the top of the page with neither one's sheets under it.
    if pack["section"] and pack["section"] != COMMUNITY_SECTION and slug != FIRST_SHELF:
        # Halloween, Deepavali, From the makers: a heading and a wheel of that group's packs,
        # directly above the sheets the wheel turns through. Written as an empty region and
        # filled by build_deck.py, the only file that knows how to draw a rail -- the same
        # arrangement the community shelf below uses, and for the same reason. Every pack sheet
        # has to belong to exactly one wheel: a sheet no wheel owns is never collapsed, and the
        # page grows back the 30,000 px the rail exists to remove.
        head = (
            f'<section class="rail-section" id="shelf-{slug}" aria-labelledby="{slug}-h">\n'
            f'<h2 id="{slug}-h">{pack["section"]}</h2>\n'
            f'<!-- rail-{slug}:start -->\n<!-- rail-{slug}:end -->\n'
            '</section>\n'
        )
    if pack["section"] == COMMUNITY_SECTION:
        # Heading, note and wheel inside one element with an id, exactly like #packs. peel.js
        # scrolls to the element a rail's data-anchor names when a card is opened; without one
        # of its own, the community rail borrowed "packs" and every community card scrolled
        # the reader back to the top of somebody else's section.
        head = (
            '<section class="rail-section" id="community" aria-labelledby="community-h">\n'
            f'<h2 id="community-h">{COMMUNITY_SECTION}</h2>\n'
            f'<p class="note">{COMMUNITY_NOTE}</p>\n'
            f'{RAIL_START}\n{RAIL_END}\n'
            '</section>\n'
        )
    shelf, paid = shelf_of(slug)
    return f"""{head}<section class="sheet" id="{slug}" style="--c1:{pack['c1']};--c2:{pack['c2']}">
  <div class="sheet-head">
    <h3 class="sheet-title">{html.escape(pack['title'])}</h3>
    <p class="sheet-sub">{pack['sub']}</p>
  </div>
  <div class="sheet-body">
    <div class="sheet-grid">
{cells}
    </div>
  </div>
{in_peel_foot("pack", shelf, paid)}
</section>"""


def in_peel_foot(kind, shelf, paid):
    """The footer of a sheet or scene: where to find it in the app, and what it costs.

    No download button. Peel fetches these files itself from More fun, so a button here only
    sent people through a file picker to do by hand what the app does in one tap. The files
    still sit at their addresses for the app to fetch.
    """
    mark = ('<span class="mark paid">Needs the unlock</span>' if paid
            else '<span class="mark free">Free</span>')
    where = "More fun"
    note = (
        '<p class="how">One unlock, once, opens every paid pack and scene. The price is shown in '
        "Peel by Google Play.</p>"
    ) if paid else ""
    return (
        '  <div class="sheet-foot in-peel">\n'
        f'    <p class="path"><span class="where">In Peel</span> {where} &rarr; {html.escape(shelf)} {mark}</p>\n'
        f'    {note}\n'
        '  </div>'
    )


def standalone(pack, files, caps):
    """A self-contained page for the PNG render: no peel, no lazy loading, fixed width."""
    slug = pack["slug"]
    cells = "\n".join(
        f'      <div class="cell"><img src="stickers/{f}" alt=""></div>'
        for f in files
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Fredoka:wght@600;700&family=Nunito:wght@600&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; }}
  /* magenta is a sentinel: Chrome only screenshots the window, so we shoot tall and crop it off */
  body {{ width: 1000px; background: #f0f; font-family: Nunito, sans-serif; }}
  .sheet {{ background: #fffdf8; }}
  .head {{ padding: 42px 48px 36px; color: #fff;
           background: linear-gradient(120deg, {pack['c1']}, {pack['c2']}); position: relative; }}
  .head h1 {{ font-family: Fredoka, sans-serif; font-size: 58px; line-height: 1.04; }}
  .head p {{ font-size: 22px; opacity: .93; margin-top: 10px; }}
  .head::after {{ content: ""; position: absolute; left: 0; right: 0; bottom: -16px; height: 32px;
                  background: radial-gradient(circle at 16px 16px, #fffdf8 13px, transparent 13.5px);
                  background-size: 40px 32px; }}
  .body {{ padding: 54px 40px 46px; display: grid;
           grid-template-columns: repeat({5 if len(files) > 12 else 4}, 1fr); gap: 10px; }}
  .cell {{ aspect-ratio: 1; border: 2px dashed rgba(90,70,120,.3); border-radius: 18px;
           padding: 8px; display: grid; place-items: center; }}
  .cell img {{ width: 100%; height: 100%; object-fit: contain; }}
  .foot {{ padding: 0 48px 42px; display: flex; justify-content: space-between;
           align-items: baseline; font-size: 22px; color: #6f6480; }}
  .foot b {{ font-family: Fredoka, sans-serif; color: #221a2e; font-size: 26px; }}
</style></head>
<body><div class="sheet">
  <div class="head"><h1>{html.escape(pack['title'])}</h1><p>{pack['sub']}</p></div>
  <div class="body">
{cells}
  </div>
  <div class="foot"><span><b>Peel</b> · free sticker sheets</span><span>refine-co.github.io/peel</span></div>
</div></body></html>"""


def render_png(src_html, out_png, width=1000, tall=3400):
    """Headless Chrome screenshots the window, not the document, so shoot tall
    on a magenta page and cut the leftover off."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
         f"--screenshot={out_png}", f"--window-size={width},{tall}",
         "--force-device-scale-factor=1", "--virtual-time-budget=8000",
         src_html.as_uri()],
        check=True, capture_output=True,
    )

    from PIL import Image, ImageChops
    img = Image.open(out_png).convert("RGB")
    sentinel = Image.new("RGB", img.size, (255, 0, 255))
    box = ImageChops.difference(img, sentinel).getbbox()
    if box is None:
        raise SystemExit(f"{out_png.name}: nothing rendered")
    img.crop(box).save(out_png, optimize=True)


def main():
    want_png = "--no-png" not in sys.argv
    sections, strip = [], []

    for pack in PACKS:
        files = extract(pack["slug"])
        caps = captions_of(pack)
        assert len(files) == len(caps), f"{pack['slug']}: {len(files)} files, {len(caps)} captions"

        size = pack_file(pack["slug"]).stat().st_size
        size_kb = f"{size / 1024 / 1024:.1f} MB" if size > 1024 * 1024 else f"{size // 1024} KB"
        sections.append(sheet_html(pack, files, caps, size_kb))

        # a few from each pack for the marquee
        for f in files[::4][:5]:
            where = "stills" if is_animated_pack(pack["slug"]) else "stickers"
            strip.append(f'<img src="packs/img/{pack["slug"]}/{where}/{f}" alt="" loading="lazy">')

        if want_png:
            page = SITE / "packs" / "img" / pack["slug"] / "_sheet.html"
            page.write_text(standalone(pack, files, caps))
            out = SITE / "packs" / "img" / pack["slug"] / "sheet.png"
            render_png(page, out)
            page.unlink()
            print(f"{pack['slug']}: {len(files)} stickers, sheet.png {out.stat().st_size // 1024} KB")
        else:
            print(f"{pack['slug']}: {len(files)} stickers")

    page = SITE / "packs.html"
    src = page.read_text()
    # No submissions published yet: the section is still worth having, as the invitation it
    # used to be by hand at the bottom of the page. Generated from here so it disappears on
    # its own the day the first pack goes up, which the hand-written one did not.
    if not any(p.get("section") == COMMUNITY_SECTION for p in PACKS):
        sections.append(
            f'<h2 id="community-h">{COMMUNITY_SECTION}</h2>\n'
            f'<p class="note">{COMMUNITY_NOTE}</p>\n'
            '<div class="empty">\n'
            '  Nothing here yet. If you have made a pack in Peel you are happy to share,\n'
            '  <a href="submit.html">send it in</a> and it goes up with your name on it.\n'
            '</div>'
        )
    body = "\n\n".join(sections)
    today = datetime.date.today().isoformat()
    src = re.sub(
        re.escape(NEW_START) + r".*?" + re.escape(NEW_END),
        NEW_START + "\n" + just_landed(PACKS, today) + "\n" + NEW_END,
        src, flags=re.S,
    )
    src = re.sub(
        r"<!-- sheets:start -->.*?<!-- sheets:end -->",
        "<!-- sheets:start -->\n" + body + "\n<!-- sheets:end -->",
        src, flags=re.S,
    )
    # the marquee needs the list twice so the loop has no seam
    src = re.sub(
        r'(<div class="track" id="marquee">).*?(</div>)',
        r"\1" + "".join(strip) * 2 + r"\2",
        src, flags=re.S,
    )
    page.write_text(src)
    total = src.count('class="peel')
    print("packs.html: %d peelable stickers" % total)

    # The hero counts are prose — "Ten full sticker sheets", "two of them behind the unlock" —
    # so they are written by hand and cannot be regenerated without flattening them. They can
    # still be checked. Publishing a pack used to leave them saying nine sheets and 146
    # stickers while the page carried ten and 158, which is the kind of wrong a reader spots
    # before we do.
    chip = re.search(r'<span class="chip">(\d+) stickers</span>', src)
    if chip and int(chip.group(1)) != total:
        print(f"  CHECK  packs.html hero chip says {chip.group(1)} stickers, the page has {total}")
    print(f"  (hero copy is hand-written: {len(PACKS)} sheets, {total} stickers. index.html "
          f"spells both out in words and is not checked — read it when either changes.)")


# The order the page shows the packs in, which is not the catalogue's order. Halloween and
# Deepavali are two sections rather than one "Festive" shelf, Halloween first while the night is
# still coming; the app's More fun is ordered by build_catalogue.py (CATEGORY_ORDER) and is a
# separate decision. Inside each section the animated packs come first: a sticker that moves is
# the thing a first-time reader did not expect from a free app, and it only does its work if it
# is on screen before the scrolling stops. The still sheets follow, and they are the larger ones,
# so nothing is hidden by being second. Anything not listed, such as a pack somebody sent in,
# goes after these in the order it was found. Sorted in place: build_deck already holds this
# list.
PAGE_ORDER = [
    # Halloween: animated first.
    "just-lurking", "low-light", "ghost-says", "moth-lights", "dead-honest", "sir-crow",
    "halloween", "halloween-night", "midnight-replies",
    # Deepavali: animated first. The one free sheet, Happy Deepavali, is also the one that does
    # not move, so it lands last here -- worth a second look if the free greeting is the thing
    # the page is meant to hand out.
    "divine-blessings", "lakshmi", "little-diya", "mayil", "kolam-lights", "happy-deepavali",
    "reactions", "say-it", "oyen-kampung",
]


# At import, not inside main(), because build_deck.py imports PACKS and builds the rail from
# it — a sent-in pack has to be in the list before either script walks it. extend() rather than
# a rebind so the list build_deck already holds is the one that grows.
for _entry in sent_in():
    extract(_entry["slug"])                       # shades() reads the unpacked stickers
    _entry["c1"], _entry["c2"] = shades(_entry["slug"], _entry.pop("files"))
    PACKS.append(_entry)
PACKS.sort(key=lambda p: PAGE_ORDER.index(p["slug"]) if p["slug"] in PAGE_ORDER else len(PAGE_ORDER))

# The pack that opens the first shelf. Its heading and wheel are the ones at the top of the
# page, inside the deck markers, so sheet_html() writes no region of its own for it.
FIRST_SHELF = next((p["slug"] for p in PACKS if p["section"]), None)


if __name__ == "__main__":
    main()
