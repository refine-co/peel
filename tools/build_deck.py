#!/usr/bin/env python3
"""Write the pack rail into packs.html, between the deck markers.

The page used to lay every sticker of every pack out at once: 35,821 px, eighty sticker boxes,
and on a 400 px phone each of those boxes rendered about 176 px wide because `.sheet-grid` is a
`minmax(118px, 1fr)` that fits two tracks and stretches them. Eight sections in, reaching the
scenes meant scrolling past all of it.

The rail is the index that was missing. One card per pack and per scene, swiped sideways, and
whichever card is in the middle is the section open underneath it.

**Where the card's facts come from.** `catalogue.json` — the same file the app fetches, built out
of the archives themselves — carries the title, the piece count, whether it is animated, and a
192 px WebP thumbnail already inlined as base64. Reading those from the rendered page instead
would mean sniffing the word "animated" out of a prose subtitle and stripping a chip out of an
`<h3>`; the catalogue has them typed. What the catalogue does not carry is the two sheet colours
and the paid flag, so those are imported from the builders that own them.
"""

import base64
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from build_scenes import SCENES          # noqa: E402  (sys.path is set just above)
from build_sheets import PACKS           # noqa: E402

SITE = pathlib.Path(__file__).resolve().parent.parent
PAGE = SITE / "packs.html"
CATALOGUE = SITE / "catalogue.json"

START = "<!-- deck:start -->"
END = "<!-- deck:end -->"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def cards():
    """Every pack then every scene, in the order the sections appear on the page."""
    cat = {item["id"]: item for item in json.loads(CATALOGUE.read_text())["items"]}
    out = []

    for pack in PACKS:
        item = cat.get(pack["slug"])
        if item is None:
            raise SystemExit(f"{pack['slug']} is on the page but not in catalogue.json — "
                             "run build_catalogue.py first")
        out.append({
            "slug": pack["slug"],
            "title": item["title"],
            "pieces": item["pieces"],
            "unit": "sticker",
            "animated": item["animated"],
            "scene": False,
            "paid": bool(pack.get("paid")),
            "c1": pack["c1"], "c2": pack["c2"],
            "thumb": item["thumb"],
        })

    for scene in SCENES:
        item = cat.get(scene["slug"])
        if item is None:
            raise SystemExit(f"{scene['slug']} is on the page but not in catalogue.json — "
                             "run build_catalogue.py first")
        out.append({
            "slug": scene["slug"],
            "title": item["title"],
            "pieces": item["pieces"],
            "unit": "piece",
            "animated": item["animated"],
            "scene": True,
            "paid": bool(scene.get("paid")),
            "c1": scene["c1"], "c2": scene["c2"],
            "thumb": item["thumb"],
        })

    return out


def card_html(card, first):
    pieces = f"{card['pieces']} {card['unit']}" + ("s" if card["pieces"] != 1 else "")

    marks = []
    if card["scene"]:
        marks.append('<span class="mark">Scene</span>')
    if card["animated"]:
        marks.append('<span class="mark">Animated</span>')
    # Before the download button, never after it. A file that downloads and then will not open
    # is the worst possible way to learn the price.
    if card["paid"]:
        marks.append('<span class="mark paid">Needs the unlock</span>')

    # A full description for the screen reader, because the visible text is three fragments and
    # the thumbnail carries no name of its own.
    spoken = ", ".join(
        [esc(card["title"]), pieces]
        + (["a scene"] if card["scene"] else [])
        + (["animated"] if card["animated"] else [])
        + (["needs the unlock"] if card["paid"] else [])
    )

    return (
        f'<button class="pcard{" is-on" if first else ""}" type="button" '
        f'role="tab" id="tab-{card["slug"]}" data-for="{card["slug"]}" '
        f'aria-controls="{card["slug"]}" aria-selected="{"true" if first else "false"}" '
        f'tabindex="{"0" if first else "-1"}" '
        f'style="--c1:{card["c1"]};--c2:{card["c2"]}">'
        f'<span class="pcard-art"><img src="data:image/webp;base64,{card["thumb"]}" alt="" '
        f'width="96" height="96" decoding="async"></span>'
        f'<span class="pcard-body">'
        f'<span class="pcard-title">{esc(card["title"])}</span>'
        f'<span class="pcard-meta">{pieces}</span>'
        f'<span class="pcard-marks">{"".join(marks)}</span>'
        f'</span>'
        f'<span class="sr">{spoken}</span>'
        f'</button>'
    )


def build():
    items = cards()
    body = "\n".join(card_html(c, i == 0) for i, c in enumerate(items))

    # The rail is the page's navigation, so it says so. The spacers let the first and last card
    # reach the middle of the track: scroll-snap-align centre cannot centre a card the track
    # cannot scroll far enough to put there.
    sheets = sum(1 for c in items if not c["scene"])
    scenes = len(items) - sheets
    lead = (f'  <p class="rail-lead">{sheets} sticker sheets and {scenes} scenes. '
            f'<span>Swipe to see them all.</span></p>')

    deck = (
        f'<nav class="rail-wrap" id="packs" aria-label="Packs and scenes">\n'
        f'{lead}\n'
        '  <button class="rail-arrow prev" type="button" aria-label="Previous pack" hidden>‹</button>\n'
        f'  <div class="rail" id="rail" role="tablist" aria-label="Packs and scenes" tabindex="0">\n'
        '    <span class="rail-end" aria-hidden="true"></span>\n'
        f'{body}\n'
        '    <span class="rail-end" aria-hidden="true"></span>\n'
        '  </div>\n'
        '  <button class="rail-arrow next" type="button" aria-label="Next pack" hidden>›</button>\n'
        '</nav>'
    )

    src = PAGE.read_text()
    if START not in src:
        raise SystemExit(f"{PAGE.name} has no {START} marker")
    src = re.sub(
        re.escape(START) + ".*?" + re.escape(END),
        lambda _: f"{START}\n{deck}\n{END}",
        src,
        flags=re.S,
    )
    PAGE.write_text(src)
    print(f"deck: {len(items)} cards")


if __name__ == "__main__":
    build()
