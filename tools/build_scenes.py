#!/usr/bin/env python3
"""Build the scene cards on packs.html.

A scene is not a sheet. A sheet is stickers you peel off and send to someone; a scene is a
picture with its own stickers taken out of it, and the point is putting them back. So the card
does not borrow the peel interaction — it shows the empty board and lets you drop the pieces in.

Everything on the card comes out of the .chill itself: the board is the scene's own background,
the pieces are its own sticker files, and each piece is positioned from the `home` x/y/scale the
app would place it at. That is the same guarantee the sheets have — the page cannot show
something the file does not contain — and it is also a check, because a wrong home would be
visible on the page.

    python3 site/tools/build_scenes.py

No Chrome and no PNG render: the board picture is already in the archive.
"""

import html
import json
import pathlib
import re
import zipfile

SITE = pathlib.Path(__file__).resolve().parent.parent
SCENES_DIR = SITE / "scenes"

# Where the .chill files are authored. Copied in rather than read in place, so the site repo
# holds everything it serves.
SOURCE = pathlib.Path.home() / "Documents/refineco/projects/sticker-app/scenes"

# Chill is not in a released build yet: the shipped Peel's importer has no .chill type, so a
# download today ends in a rejection toast. The cards go up without a download until it ships.
# Flip this to True on the day Chill is on Play and re-run; nothing else needs to change.
DOWNLOADS_LIVE = False

# Same deep link the sheets use. MainActivity's PACK_FILE_TYPES already accepts the chill type,
# so this button needs no app change once Chill is out.
PEEL_IMPORT_LINK = (
    "intent://import#Intent;scheme=peel;package=my.refineco.peel;"
    "S.browser_fallback_url=https%3A%2F%2Fplay.google.com%2Fstore%2Fapps%2Fdetails"
    "%3Fid%3Dmy.refineco.peel;end"
)

SCENES = [
    {
        "slug": "village-night",
        "c1": "#2b2d6e", "c2": "#f0a868",
        "sub": "37 pieces · a valley after dark, seven cottages and a stream",
        "blurb": "The furthest things first — the clouds, the mountains, the forest — then the "
                 "village, then the stones, then the flowers and the butterflies. The picture "
                 "comes back in the order it was painted.",
    },
    {
        "slug": "lantern-alley",
        "c1": "#5b2c6f", "c2": "#ffb347",
        "sub": "20 pieces · a wet alley, paper lanterns and the light on the ground",
        "blurb": "Five chapters, far to near: the end of the alley, then the walls, then what "
                 "hangs over the street, then what stands on it, and the sleeping cat last. "
                 "Rain falls while you work, and the puddles catch whatever you have lit.",
        "after": "Also built into Peel. This file is for sharing it with someone who has not "
                 "installed the app yet.",
    },
    {
        "slug": "firefly-jar",
        "c1": "#1f4037", "c2": "#4fc9a0",
        "sub": "14 pieces · a jar on a porch rail and the garden it lights",
        "blurb": "The smallest of the three, and the one to start with. Every firefly you put "
                 "back starts drifting on its own.",
    },
]

SECTION_INTRO = (
    "A scene is a picture with its own stickers lifted out of it. You get the empty place and "
    "the things that belong in it, and you put them back — the far ones first, so the near ones "
    "land on top. Tap a piece below to put it down, or press <strong>Fill it in</strong> and "
    "watch the picture come back."
)

# A scene whose stickers carry no `home` is not a puzzle: nothing has a place to go back to, so
# the card shows the picture and the stickers and says so, rather than faking a fill.
def is_puzzle(manifest):
    return all(s.get("home") for s in manifest["stickers"])


def read_scene(slug):
    """Copy the .chill into the site, unpack what the page needs, return its manifest."""
    src = SOURCE / slug / f"{slug}.chill"
    dest = SCENES_DIR / f"{slug}.chill"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())

    img = SCENES_DIR / "img" / slug
    (img / "stickers").mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest) as z:
        manifest = json.loads(z.read("scene.json"))
        (img / "board.jpg").write_bytes(z.read(manifest["background"]))
        for s in manifest["stickers"]:
            (img / "stickers" / pathlib.Path(s["file"]).name).write_bytes(z.read(s["file"]))
    return manifest, dest.stat().st_size


def piece_html(slug, sticker, i, puzzle=True):
    """One sticker in the tray.

    In a puzzle it is a button carrying the position it belongs at: the home is the centre of
    the piece and the scale is its longest side as a fraction of the board's width, which is
    exactly what the square sticker file is letterboxed to — so the ghost is placed by centring
    that square on the home at that width, same as the app. In a free scene it is just the
    sticker, because there is nowhere in particular for it to go.
    """
    name = pathlib.Path(sticker["file"]).name
    alt = html.escape(sticker.get("accessibilityText", ""))
    img = (f'        <img src="scenes/img/{slug}/stickers/{name}" alt="{"" if puzzle else alt}" '
           f'loading="lazy" decoding="async">')
    if not puzzle:
        return f'      <div class="piece still">\n{img}\n      </div>'
    home = sticker["home"]
    return (
        f'      <button class="piece reveal" type="button" data-i="{i}"\n'
        f'              style="--x:{home["x"]};--y:{home["y"]};--s:{home["scale"]}"\n'
        f'              aria-label="Put this in place: {alt}">\n'
        f'{img}\n'
        f'      </button>'
    )


def ghost_html(slug, sticker, i):
    name = pathlib.Path(sticker["file"]).name
    return (
        f'      <img class="ghost" data-i="{i}" src="scenes/img/{slug}/stickers/{name}"\n'
        f'           style="--x:{sticker["home"]["x"]};--y:{sticker["home"]["y"]};'
        f'--s:{sticker["home"]["scale"]}" alt="" loading="lazy" decoding="async">'
    )


def scene_html(scene, manifest, size):
    slug = scene["slug"]
    stickers = manifest["stickers"]
    puzzle = is_puzzle(manifest)

    # The authored order is the order the picture is built in, back to front. Keep it: it is
    # what makes the fill read as depth rather than as a shuffle.
    pieces = "\n".join(piece_html(slug, s, i, puzzle) for i, s in enumerate(stickers))
    ghosts = ("\n".join(ghost_html(slug, s, i) for i, s in enumerate(stickers))
              if puzzle else "")

    size_txt = f"{size / 1024 / 1024:.1f} MB" if size > 1024 * 1024 else f"{size // 1024} KB"
    # Scenes written before the completion line existed fall back to Peel's own.
    done = html.escape(manifest.get("completion", {}).get("en", "")
                       or "Everything is where it belongs.")

    tools = (
        f'    <div class="scene-tools">\n'
        f'      <button class="btn small fill" type="button">Fill it in</button>\n'
        f'      <button class="btn small ghost clear" type="button" hidden>Empty it</button>\n'
        f'      <span class="done" role="status" aria-live="polite" hidden>{done}</span>\n'
        f'    </div>\n'
    ) if puzzle else ""

    note = scene.get("after", "Download first — <strong>Open in Peel</strong> then picks it "
                              "up from your Downloads folder.")

    if DOWNLOADS_LIVE:
        foot = (
            f'    <a class="btn" href="scenes/{slug}.chill" download>'
            f'Download the scene · {size_txt}</a>\n'
            f'    <a class="btn ghost" href="{PEEL_IMPORT_LINK}">Open in Peel</a>\n'
            f'    <p class="how">{note}</p>'
        )
    else:
        # The "after" line is deliberately dropped here. It describes what the downloaded file
        # is for — Lantern Alley's reads "Also built into Peel. This file is for sharing it
        # with someone who has not installed the app yet" — and printed under "needs a version
        # of Peel that is not out yet" it contradicts itself twice over: the scene is not in
        # the shipping app, and there is no file to share. It comes back with the downloads.
        foot = (
            f'    <span class="soon">Coming with the next update</span>\n'
            f'    <p class="how">Scenes need a version of Peel that is not out yet. '
            f'The file is {size_txt} when it lands.</p>'
        )

    return f"""<section class="scene" id="{slug}" style="--c1:{scene['c1']};--c2:{scene['c2']}">
  <div class="sheet-head">
    <h3 class="sheet-title">{html.escape(manifest['name'])}</h3>
    <p class="sheet-sub">{scene['sub']}</p>
  </div>
  <div class="scene-body">
    <div class="board" aria-hidden="true">
      <img class="plate" src="scenes/img/{slug}/board.jpg" alt="" loading="lazy" decoding="async">
{ghosts}
    </div>
    <p class="scene-blurb">{scene['blurb']}</p>
{tools}    <div class="tray">
{pieces}
    </div>
  </div>
  <div class="sheet-foot">
{foot}
  </div>
</section>"""


def main():
    cards = []
    for scene in SCENES:
        manifest, size = read_scene(scene["slug"])
        cards.append(scene_html(scene, manifest, size))
        kind = "puzzle" if is_puzzle(manifest) else "free placement"
        print(f"{scene['slug']}: {len(manifest['stickers'])} stickers, {size // 1024} KB, {kind}")

    body = (
        '<h2 id="scenes">Scenes</h2>\n'
        f'<p class="note">{SECTION_INTRO}</p>\n\n' + "\n\n".join(cards)
    )

    page = SITE / "packs.html"
    src = page.read_text()
    if "<!-- scenes:start -->" not in src:
        raise SystemExit("packs.html has no <!-- scenes:start --> marker")
    src = re.sub(
        r"<!-- scenes:start -->.*?<!-- scenes:end -->",
        lambda _: "<!-- scenes:start -->\n" + body + "\n<!-- scenes:end -->",
        src, flags=re.S,
    )
    # The hero chip counts them, so it cannot be left behind when a scene is added.
    src = re.sub(
        r'(<span class="chip"><a href="#scenes">)\d+ scenes(</a></span>)',
        lambda m: f"{m.group(1)}{len(cards)} scenes{m.group(2)}",
        src,
    )

    page.write_text(src)
    total = sum(c.count('class="piece') for c in cards)
    print(f"\npacks.html: {len(cards)} scenes, {total} pieces"
          f"{'' if DOWNLOADS_LIVE else ', downloads held back'}")


if __name__ == "__main__":
    main()
