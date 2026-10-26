#!/usr/bin/env python3
"""Write the pack rail into packs.html, between the deck markers.

The page used to lay every sticker of every pack out at once: 35,821 px, eighty sticker boxes,
and on a 400 px phone each of those boxes rendered about 176 px wide because `.sheet-grid` is a
`minmax(118px, 1fr)` that fits two tracks and stretches them. Eight sections in, reaching the
scenes meant scrolling past all of it.

The rail is the index that was missing. One card per pack and per scene, swiped sideways, and
whichever card is in the middle is the section open underneath it. Since 16 Oct 2026 there are
two of them, one under a Sticker packs heading and one under Scenes, each a wheel of its own kind.

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
SCENE_START = "<!-- scenedeck:start -->"
SCENE_END = "<!-- scenedeck:end -->"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def cards(likes):
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
            # Set by peel_review.py when a submission is published; the catalogue carries it
            # and both the app and this page group by it.
            "community": bool(item.get("community")),
            "credit": item.get("credit"),
            "likes": likes.get(pack["slug"], 0),
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
            "community": False,
            "credit": None,
            "likes": 0,
            "c1": scene["c1"], "c2": scene["c2"],
            "thumb": item["thumb"],
        })

    return out


def likes_now():
    """Like counts from the Worker, or nothing.

    The build asks once and writes the numbers into the page; peel.js asks again when somebody
    opens it, so a stale build shows stale numbers for a moment rather than none. A build with
    no network still produces a page — the counts are decoration on a catalogue, and refusing
    to build the site because a count was unavailable would be the wrong trade.
    """
    import urllib.error
    import urllib.request
    try:
        request = urllib.request.Request(
            LIKES_URL, data=b"{}", method="POST",
            # Cloudflare answers Python's default agent with a 1010 and nothing else, so the
            # build says who it is. Not a disguise: it is a real name for a real caller.
            headers={
                "Content-Type": "application/json",
                "User-Agent": "peel-build (+https://peel.refineco.app)",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as answer:
            return json.loads(answer.read()).get("likes", {})
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        print(f"  likes unavailable ({e.__class__.__name__}), building without them")
        return {}


def card_html(card, first):
    pieces = f"{card['pieces']} {card['unit']}" + ("s" if card["pieces"] != 1 else "")

    # Only a community card carries a count, and the slug rides along so peel.js can put a
    # fresher number in without knowing how the card was built. Empty at nought: a pack nobody
    # has got to yet should not wear a zero.
    hearts = ""
    if card["community"]:
        shown = f"&#9829; {card['likes']}" if card["likes"] else ""
        hearts = f'<span class="pcard-likes" data-likes-for="{card["slug"]}">{shown}</span>'

    marks = []
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

    still = f'<img src="data:image/webp;base64,{card["thumb"]}" alt="" width="96" height="96" decoding="async">'
    card_file = SITE / "packs" / "img" / card["slug"] / "card.webp"
    if card["animated"] and not card["scene"] and card_file.exists():
        # The rail card moves when its pack moves. A visitor who asks for less motion gets the
        # catalogue's own still, which is already inlined, so nothing extra is fetched for them.
        art = (
            f'<picture><source media="(prefers-reduced-motion: reduce)" '
            f'srcset="data:image/webp;base64,{card["thumb"]}">'
            f'<img src="packs/img/{card["slug"]}/card.webp" alt="" width="96" height="96" '
            f'decoding="async"></picture>'
        )
    else:
        art = still

    return (
        f'<button class="pcard{" is-on" if first else ""}" type="button" '
        f'role="tab" id="tab-{card["slug"]}" data-for="{card["slug"]}" '
        f'aria-controls="{card["slug"]}" aria-selected="{"true" if first else "false"}" '
        f'tabindex="{"0" if first else "-1"}" '
        f'style="--c1:{card["c1"]};--c2:{card["c2"]}">'
        f'<span class="pcard-art">{art}</span>'
        f'<span class="pcard-body">'
        f'<span class="pcard-title">{esc(card["title"])}</span>'
        f'<span class="pcard-meta">{pieces}</span>'
        f'{hearts}'
        f'<span class="pcard-marks">{"".join(marks)}</span>'
        f'</span>'
        f'<span class="sr">{spoken}</span>'
        f'</button>'
    )


def rail_html(items, kind):
    """One wheel: a lead line, its own arrows, and one card per item of [kind].

    [kind] is "packs", "community" or "scenes". The rail carries it in `data-kind` and the id of the
    thing the page should scroll to in `data-anchor`, so peel.js can run the same code for both
    without knowing which is which. Each rail owns its own arrows, inside its own nav, because
    peel.js finds them from the rail and not from the page.
    """
    body = "\n".join(card_html(c, i == 0) for i, c in enumerate(items))
    scenes = kind == "scenes"
    noun, label = {
        "scenes": ("scene", "Scenes"),
        "community": ("pack", "Packs from the community"),
    }.get(kind, ("pack", "Sticker packs"))
    count = len(items)
    thing = "scene" if scenes else ("pack from the community" if kind == "community" else "sticker pack")
    # What "scroll back to the wheel" means for this rail: its own section, never a
    # neighbour's. Getting this wrong sends a reader to the top of a different section.
    anchor = {"scenes": "scenes", "community": "community"}.get(kind, "packs")
    lead = (f'  <p class="rail-lead">{count} {thing}{"" if count == 1 else "s"}. '
            f'<span>Swipe to see {"them all" if count != 1 else "it"}.</span></p>')
    return (
        f'<nav class="rail-wrap" aria-label="{label}">\n'
        f'{lead}\n'
        f'  <button class="rail-arrow prev" type="button" aria-label="Previous {noun}" hidden>\u2039</button>\n'
        f'  <div class="rail" id="rail-{kind}" data-kind="{kind}" data-anchor="{anchor}" '
        f'role="tablist" aria-label="{label}" tabindex="0">\n'
        '    <span class="rail-end" aria-hidden="true"></span>\n'
        f'{body}\n'
        '    <span class="rail-end" aria-hidden="true"></span>\n'
        '  </div>\n'
        f'  <button class="rail-arrow next" type="button" aria-label="Next {noun}" hidden>\u203a</button>\n'
        '</nav>'
    )


def fill(src, start, end, html):
    """[html] between the two markers, or a clear message about which builder writes them."""
    if start not in src or end not in src:
        raise SystemExit(f"{PAGE.name} has no {start} marker"
                         + (" -- run build_scenes.py first, it writes this one" if "scenedeck" in start else ""))
    return re.sub(re.escape(start) + ".*?" + re.escape(end),
                  lambda _: f"{start}\n{html}\n{end}", src, flags=re.S)


LIKES_URL = "https://peel-submit.refineco.workers.dev/packs/likes"

COMMUNITY_START = "<!-- community-rail:start -->"
COMMUNITY_END = "<!-- community-rail:end -->"


def build():
    likes = likes_now()
    items = cards(likes)
    packs = [c for c in items if not c["scene"] and not c["community"]]
    # Most-liked first, title under that. The order is fixed when the site is built — peel.js
    # refreshes the numbers but never moves the cards, because the rail measures itself from
    # their order at startup and reshuffling behind it desynchronises the wheel.
    community = sorted(
        (c for c in items if not c["scene"] and c["community"]),
        key=lambda c: (-c["likes"], c["title"]),
    )
    scenes = [c for c in items if c["scene"]]

    # The packs section is a heading and its rail inside one element, so the "See the sheets"
    # button (#packs) lands on the heading and not on the rail below it. The scenes section's
    # heading and note come from build_scenes.py, so only its rail is written here.
    packs_html = (
        '<section class="rail-section" id="packs" aria-labelledby="packs-h">\n'
        '<h2 id="packs-h">Sticker packs</h2>\n'
        f'{rail_html(packs, "packs")}\n'
        '</section>'
    )
    # Packs people sent in, in a wheel of their own directly under Peel's. Written into the
    # same region as the packs rail rather than behind new markers in the page: one fewer
    # thing to keep in step, and the section simply is not there on a site with no
    # submissions published yet.
    src = PAGE.read_text()
    src = fill(src, START, END, packs_html)
    src = fill(src, SCENE_START, SCENE_END, rail_html(scenes, "scenes"))
    # The community rail goes where build_sheets.py left room for it: under that section's
    # own heading, directly above the sheets it turns through. The markers are absent on a
    # site with nothing published yet, and fill() then leaves the page alone.
    if community and COMMUNITY_START in src:
        src = fill(src, COMMUNITY_START, COMMUNITY_END, rail_html(community, "community"))
    PAGE.write_text(src)
    total_likes = sum(c["likes"] for c in community)
    print(f"deck: {len(packs)} sticker packs, {len(community)} community "
          f"({total_likes} likes), {len(scenes)} scenes")


if __name__ == "__main__":
    build()
