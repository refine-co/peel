#!/usr/bin/env python3
"""Build the sticker sheets on packs.html, and render each one to a PNG.

The stickers come out of the .peel archives themselves, so the page and the
picture can never show something the pack does not contain. Run from anywhere:

    python3 site/tools/build_sheets.py

Needs Google Chrome for the PNG render; pass --no-png to skip it.
"""

import html
import json
import pathlib
import re
import subprocess
import sys
import zipfile

SITE = pathlib.Path(__file__).resolve().parent.parent
SPECS = pathlib.Path.home() / "Projects/android-peel/tools/packs/site"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Opens Peel straight on its pack picker, in Downloads, where the browser just put the file.
# Peel has no internet permission, so it cannot fetch the pack itself — the browser does that
# first and Peel reads it from storage. Falls back to the Play listing when Peel is missing.
PEEL_IMPORT_LINK = (
    "intent://import#Intent;scheme=peel;package=my.refineco.peel;"
    "S.browser_fallback_url=https%3A%2F%2Fplay.google.com%2Fstore%2Fapps%2Fdetails"
    "%3Fid%3Dmy.refineco.peel;end"
)

PACKS = [
    {
        "slug": "halloween",
        "title": "Peel Halloween",
        "spec": "halloween-captions.json",
        "c1": "#7b5ea7", "c2": "#ff6b35",
        "sub": "20 stickers · a ghost, a black cat, a bat, a pumpkin and a one-eyed monster",
        "after": 'Download first — <strong>Open in Peel</strong> then picks it up from your Downloads folder.',
        "section": "Festive",
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


def captions(spec_path):
    data = json.load(open(spec_path))
    items = data["stickers"] if isinstance(data, dict) else data
    out = []
    for s in items:
        cap = s.get("caption")
        if not cap:
            m = re.search(r'reads "([^"]+)"', s.get("accessibilityText", ""))
            cap = m.group(1) if m else ""
        out.append((cap, s.get("accessibilityText", ""), "".join(s.get("emojis", []))))
    return out


def extract(slug):
    """Unpack the .peel into the site so the page serves the real stickers."""
    dest = SITE / "packs" / "img" / slug / "stickers"
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SITE / "packs" / f"{slug}.peel") as z:
        names = sorted(n for n in z.namelist() if n.startswith("stickers/"))
        for n in names:
            (dest / pathlib.Path(n).name).write_bytes(z.read(n))
    return [pathlib.Path(n).name for n in names]


def sticker(slug, base, cap, alt, emo, i, lazy=True):
    src = f"packs/img/{slug}/stickers/{base}"
    load = ' loading="lazy"' if lazy else ""
    return (
        f'      <div class="peel reveal" style="--tilt:{TILTS[i % len(TILTS)]}deg" tabindex="0" '
        f'role="img" aria-label="{html.escape(alt)}">\n'
        f'        <img class="ghost" src="{src}" alt="" aria-hidden="true"{load} decoding="async">\n'
        f'        <img class="face" src="{src}" alt=""{load} decoding="async">\n'
        f'        <span class="curl"></span>\n'
        f'        <span class="label">{html.escape(cap)} {emo}</span>\n'
        f'      </div>'
    )


def sheet_html(pack, files, caps, size_kb):
    slug = pack["slug"]
    cells = "\n".join(
        sticker(slug, f, c, a, e, i) for i, (f, (c, a, e)) in enumerate(zip(files, caps))
    )
    head = f'<h2 id="{slug}-h">{pack["section"]}</h2>\n' if pack["section"] else ""
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
  <div class="sheet-foot">
    <a class="btn" href="packs/{slug}.peel" download>Download the sheet · {size_kb}</a>
    <a class="btn ghost" href="{PEEL_IMPORT_LINK}">Open in Peel</a>
    <p class="how">{pack['after']}</p>
  </div>
</section>"""


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
        caps = captions(SPECS / pack["spec"])
        assert len(files) == len(caps), f"{pack['slug']}: {len(files)} files, {len(caps)} captions"

        size = (SITE / "packs" / f"{pack['slug']}.peel").stat().st_size
        size_kb = f"{size / 1024 / 1024:.1f} MB" if size > 1024 * 1024 else f"{size // 1024} KB"
        sections.append(sheet_html(pack, files, caps, size_kb))

        # a few from each pack for the marquee
        for f in files[::4][:5]:
            strip.append(f'<img src="packs/img/{pack["slug"]}/stickers/{f}" alt="" loading="lazy">')

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
    body = "\n\n".join(sections)
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
    print("packs.html: %d peelable stickers" % src.count('class="peel'))


if __name__ == "__main__":
    main()
