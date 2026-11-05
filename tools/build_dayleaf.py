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
<title>Ready-made pages — Peel</title>
<meta name="description" content="{count} ready-made pages for Peel's Dayleaf: a drawn border and a blank middle to peel your stickers onto. Free, no account, nothing leaves your phone.">
<meta property="og:type" content="website">
<meta property="og:title" content="Free ready-made journal pages — Peel">
<meta property="og:description" content="{count} drawn pages with a blank middle. Open Dayleaf in Peel, tap one, and start sticking.">
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
      <a href="index.html">The app</a>
      <a href="packs.html">Sticker packs</a>
      <a href="scenes.html">Scenes</a>
      <a href="dayleaf.html" aria-current="page">Ready-made pages</a>
      <a href="how-to-install.html">How to install</a>
      <a href="submit.html">Share yours</a>
    </nav>
  </div>
</header>

<main class="wrap">

<section class="hero">
  <div>
    <p class="eyebrow">Dayleaf</p>
    <h1>A page that is<br><span class="wave">already somewhere.</span></h1>
    <p class="lede">A dayleaf is a page you peel stickers onto — no writing, no account, nothing
      leaves your phone. These {count} are drawn with a border and a blank middle, so the page is
      somewhere before you put anything on it. Open <strong>Dayleaf</strong> in Peel, tap
      <strong>New dayleaf</strong>, and pick one.</p>
    <div class="cta">
      <a class="btn" href="https://play.google.com/store/apps/details?id=my.refineco.peel">Get Peel on Google Play</a>
      <a class="btn ghost" href="#pages">See all {count}</a>
    </div>
    <div class="chips">
      <span class="chip">{count} pages</span>
      <span class="chip">All free</span>
      <span class="chip">No account</span>
      <span class="chip">Your photos work too</span>
    </div>
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

TAIL = """
<section class="get-peel" aria-labelledby="get-peel-h">
  <h2 id="get-peel-h">Where these live</h2>
  <p>In Peel, open <strong>Dayleaf</strong> and tap <strong>New dayleaf</strong>. The ready-made
    pages are under <strong>Ready-made</strong>, and your own photos are the row above them.</p>
  <div class="cta">
    <a class="btn" href="https://play.google.com/store/apps/details?id=my.refineco.peel">Get Peel on Google Play</a>
    <a class="btn ghost" href="packs.html">Sticker packs to put on them</a>
  </div>
</section>

<footer>
<a href="index.html">Peel</a> · <a href="privacy.html">Privacy policy</a> · <a href="delete-account.html">Delete your account</a> · <a href="terms.html">Terms of use</a> · <a href="mailto:refine.co.my@gmail.com">Contact</a>
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
                    alt=esc(f"{title}, a ready-made page"))
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

    total = len(in_app) + len(downloadable)
    schema = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Peel ready-made dayleaf pages",
        "numberOfItems": total,
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": title}
            for i, (_, title, _) in enumerate(in_app + downloadable)
        ],
    }

    body = HEAD.format(count=total, schema=json.dumps(schema, indent=1, ensure_ascii=False))
    body += '\n<div id="pages"></div>\n'
    body += SECTION.format(
        anchor="in-app", heading="In the app",
        note="These twelve are inside Peel already. They are there the first time you open "
             "Dayleaf, with or without a signal.",
        tiles=tiles(in_app))
    body += SECTION.format(
        anchor="more", heading="A tap away",
        note=f"Another {len(downloadable)} that come down when you tap one. They are free, and "
             "the page is yours once it is made — deleting the app's cache cannot take it back.",
        tiles=tiles(downloadable))
    body += TAIL

    PAGE.write_text(body)
    print(f"{PAGE}  ({total} pages: {len(in_app)} in the app, {len(downloadable)} downloadable, "
          f"{PAGE.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
