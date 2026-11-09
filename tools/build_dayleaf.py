#!/usr/bin/env python3
"""Write dayleaf.html: every ready-made page Peel has, as one gallery.

A dayleaf template is one picture with a blank middle. That is the whole thing — there is no
sticker list to open underneath it and no board to put back together, so the swipeable rail
that packs.html uses for packs and scenes has nothing to do here. A plain grid of pictures is
the honest shape, and at fifty-two items it is also the only one somebody can scan.

**Two sources, and the difference matters to a reader.** Twelve ship inside the app and are
there the moment it is installed; forty are fetched from the catalogue the first time somebody
taps one. The page says which is which, because "in the app" and "downloads when you tap it"
are different promises on a phone with no signal.

The pictures are the same files the app uses: `dayleaf/*.webp` are what the catalogue serves,
and `dayleaf/in-app/*.webp` are display copies of the bundled twelve, which otherwise exist
only inside the APK. `build_catalogue.py` globs the top level only, so the in-app copies can
never be mistaken for something to download.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from build_catalogue import TEMPLATE_TITLES  # noqa: E402  (sys.path is set just above)

SITE = pathlib.Path(__file__).resolve().parent.parent
PAGE = SITE / "dayleaf.html"
DIR = SITE / "dayleaf"

# The pages that move, shown first and moving. Rendered by render_previews.py in the
# peel-stickers repo from the same plate, pieces and light layers the app draws, so the tile
# on this page and the page in the app cannot disagree about what moves.
#
# Only true from the release that carries moving pieces. A 2.5.5 phone that downloads one of
# these gets the still picture, so this section must not go live before that release does.
ANIMATED = [
    ("christmas-fairy-lights", "Fairy lights", "the puppy rocks, the bulbs twinkle"),
    ("christmas-tree", "Christmas", "the lights twinkle, the robin hops"),
    ("christmas-santa", "Father Christmas", "the lantern glows, the robin hops"),
    ("christmas-gingerbread", "Gingerbread house", "the windows glow, the gingerbread man rocks"),
    ("christmas-tropical", "Christmas in the heat", "the cat breathes, the parrot sways"),
    # Christmas first, then the rest. These are downloads, not bundled, and move only because
    # the catalogue gives them a plate and layers (site/dayleaf/fx/<id>/).
    ("night-market", "Night market", "the cat breathes, the moth bobs, the bulbs twinkle"),
]

# The twelve that ship inside the app, in the order DayleafTemplates.kt lists them: the six
# framed ones and then the six shaped ones, which is also roughly plainest-first.
IN_APP = [
    ("birthday", "Birthday"),
    ("good-night", "Good night"),
    ("rainy-day", "Rainy day"),
    ("sunny-day", "Sunny day"),
    ("garden", "Garden"),
    ("study", "Study"),
    ("latte", "Coffee"),
    ("kopitiam", "Kopitiam"),
    ("cat", "Cat"),
    ("sprout", "Fresh start"),
    ("lantern", "Quiet evening"),
    ("christmas-tree", "Christmas"),
]

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dayleaf — Peel</title>
<meta name="description" content="Dayleaf in Peel: pick one of {count} ready-made pictures, peel your stickers onto it, write one line. Free, no account, nothing leaves your phone.">
<meta property="og:type" content="website">
<meta property="og:title" content="Dayleaf: a sticker journal — Peel">
<meta property="og:description" content="{count} ready-made pictures to stick on. Open Dayleaf in Peel, tap one, and start sticking.">
<meta property="og:image" content="https://peel.refineco.app/dayleaf/in-app/good-night.webp">
<meta property="og:url" content="https://peel.refineco.app/dayleaf.html">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="https://peel.refineco.app/dayleaf.html">
<link rel="icon" href="icon/favicon-32.png" sizes="32x32" type="image/png">
<link rel="icon" href="icon/favicon-192.png" sizes="192x192" type="image/png">
<link rel="apple-touch-icon" href="icon/apple-touch-icon.png">
<link rel="stylesheet" href="style.css">
<script type="application/ld+json">
{schema}
</script>
</head>
<body>

<header class="topbar">
  <div class="row">
    <a class="brand" href="index.html"><span class="dot"></span>Peel</a>
    <nav>
      <a href="index.html">Home</a>
      <a href="packs.html">Packs</a>
      <a href="scenes.html">Scenes</a>
      <a href="dayleaf.html" aria-current="page">Dayleaf</a>
    </nav>
  </div>
</header>

<main class="wrap">

<section class="hero">
  <div>
    <p class="eyebrow">Dayleaf</p>
    <h1>A dayleaf that is<br><span class="wave">already somewhere.</span></h1>
    <p class="lede">Pick a picture, peel stickers onto it, write one line.</p>
    <div class="cta">
      <a class="btn" href="https://play.google.com/store/apps/details?id=my.refineco.peel">Get Peel on Google Play</a>
      <a class="btn ghost" href="#pages">See all {count}</a>
    </div>
    <div class="chips">
      <span class="chip">{count} ready-made</span>
      <span class="chip">All free</span>
      <span class="chip">No account</span>
      <span class="chip">Your photos work too</span>
    </div>
  </div>
  <div class="hero-art">
    <video class="phone-shot" src="video/dayleaf-v2.mp4" poster="video/dayleaf-v2.jpg" width="540" height="960"
      controls playsinline preload="none"
      aria-label="Making a dayleaf in Peel: pick a night-market picture, stick stickers, write a line, then turn the book"></video>
  </div>
</section>
"""

# Three pages actually made in Peel on a phone (S22, Play build, 9 Nov 2026), so a visitor sees
# what a dayleaf turns into rather than only the empty backgrounds. Yow asked for them to tell a
# story; Mochi is the puppy drawn on the Fairy lights page, carried through as a sticker.
STORY = """
<section class="story" aria-labelledby="story-h">
  <h2 id="story-h">One December, three dayleafs</h2>
  <p class="note">Made in Peel: a picture, a few stickers, one line.</p>
  <div class="story-pages">
    <figure><img src="dayleaf/examples/story-1.webp" width="774" height="1082" loading="lazy" decoding="async"
      alt="A fairy-lights dayleaf with Merry Christmas, a bear, a reindeer and Ho Ho Ho stickers, and the line: Tree is up! Mochi helped, sort of"><figcaption>The tree</figcaption></figure>
    <figure><img src="dayleaf/examples/story-2.webp" width="774" height="1082" loading="lazy" decoding="async"
      alt="A gingerbread-house dayleaf with a gingerbread man, a fox with cocoa and a puppy in lights, and the line: Baked with Grandma. Mochi ate the roof"><figcaption>The baking</figcaption></figure>
    <figure><img src="dayleaf/examples/story-3.webp" width="774" height="1082" loading="lazy" decoding="async"
      alt="A tropical Christmas dayleaf with Let it snow, a puppy and an owl in earmuffs, and the line: 33 degrees in KL. Mochi still wants snow"><figcaption>The heat</figcaption></figure>
  </div>
</section>
"""

SECTION = """
<section class="tiles-section" id="{anchor}" aria-labelledby="{anchor}-h">
  <h2 id="{anchor}-h">{heading}</h2>
  <p class="note">{note}</p>
  <ul class="tiles">
{tiles}
  </ul>
</section>
"""

TILE = """    <li class="tile">
      <img src="{src}" alt="{alt}" width="1008" height="1344" loading="lazy" decoding="async">
      <span class="tile-name">{title}</span>
    </li>"""

MOVING_TILE = """    <li class="tile moving">
      <span class="tile-art">
        <picture>
          <!-- CSS cannot pause an animated WebP, so somebody who has asked their system for
               less motion is served a still frame instead of the loop. -->
          <source srcset="{still}" media="(prefers-reduced-motion: reduce)">
          <img src="{src}" alt="{alt}" width="432" height="576" loading="lazy" decoding="async">
        </picture>
        <span class="tile-badge">Animated</span>
      </span>
      <span class="tile-name">{title}</span>
      <span class="tile-how">{how}</span>
    </li>"""

TAIL = """
<section class="get-peel" aria-labelledby="get-peel-h">
  <h2 id="get-peel-h">Where these live</h2>
  <p>Peel → <strong>Dayleaf</strong> → <strong>New dayleaf</strong> → <strong>Ready-made</strong>.</p>
  <div class="cta">
    <a class="btn" href="https://play.google.com/store/apps/details?id=my.refineco.peel">Get Peel on Google Play</a>
    <a class="btn ghost" href="packs.html">Sticker packs to put on them</a>
  </div>
</section>

<footer>
<a href="how-to-install.html">How to use</a> · <a href="submit.html">Share your pack</a> · <a href="ios.html">iPhone</a> · <a href="privacy.html">Privacy</a> · <a href="terms.html">Terms</a> · <a href="delete-account.html">Delete your account</a> · <a href="mailto:refine.co.my@gmail.com">Contact</a>
</footer>

</main>
<script src="peel.js" defer></script>
</body>
</html>
"""


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def tiles(rows: list[tuple[str, str, str]]) -> str:
    return "\n".join(
        TILE.format(src=src, title=esc(title),
                    # The name alone, not "a picture of": the tile below it says the name and a
                    # screen reader would otherwise hear it twice.
                    alt=esc(f"{title}, a ready-made dayleaf picture"))
        for src, title, _ in rows)


def main() -> None:
    downloadable = []
    for p in sorted(DIR.glob("*.webp")):
        title = TEMPLATE_TITLES.get(p.stem)
        if title is None:
            raise SystemExit(f"{p.stem}: add a title to TEMPLATE_TITLES")
        downloadable.append((f"dayleaf/{p.name}", title, p.stem))

    in_app = []
    for slug, title in IN_APP:
        f = DIR / "in-app" / f"{slug}.webp"
        if not f.is_file():
            raise SystemExit(f"{slug}: no display copy at dayleaf/in-app/{slug}.webp")
        in_app.append((f"dayleaf/in-app/{f.name}", title, slug))

    moving_ids = {slug for slug, _, _ in ANIMATED}
    moving = []
    for slug, title, how in ANIMATED:
        f = DIR / "anim" / f"{slug}.webp"
        if not f.is_file():
            raise SystemExit(f"{slug}: no animated tile at dayleaf/anim/{slug}.webp")
        moving.append((f"dayleaf/anim/{f.name}", title, how))
    # A moving page appears once, in the moving section, rather than again as a still.
    in_app = [row for row in in_app if row[2] not in moving_ids]
    downloadable = [row for row in downloadable if row[2] not in moving_ids]

    total = len(moving) + len(in_app) + len(downloadable)
    schema = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Peel ready-made dayleaf pictures",
        "numberOfItems": total,
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": title}
            for i, (_, title, _) in enumerate(moving + in_app + downloadable)
        ],
    }

    body = HEAD.format(count=total, schema=json.dumps(schema, indent=1, ensure_ascii=False))
    body += STORY
    body += '\n<div id="pages"></div>\n'
    body += SECTION.format(
        anchor="moving", heading="Ready-made that move",
        note="Lights twinkle, cats breathe. Christmas first.",
        tiles="\n".join(MOVING_TILE.format(src=src, still=src.replace(".webp", "-still.webp"),
                                            title=esc(t), how=esc(h),
                                            alt=esc(f"{t}, an animated ready-made dayleaf picture"))
                        for src, t, h in moving))
    body += SECTION.format(
        anchor="in-app", heading="In the app",
        # Counted, not written: the bundled Christmas pages sit in the moving section above,
        # so "twelve" was wrong the day they moved there.
        note=f"{len(in_app)} more, ready offline.",
        tiles=tiles(in_app))
    body += SECTION.format(
        anchor="more", heading="A tap away",
        note=f"{len(downloadable)} more, free, one tap to download.",
        tiles=tiles(downloadable))
    body += TAIL

    PAGE.write_text(body)
    print(f"{PAGE}  ({total} pages: {len(in_app)} in the app, {len(downloadable)} downloadable, "
          f"{PAGE.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
