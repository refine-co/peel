#!/usr/bin/env python3
"""Build a 1000x1500 Pinterest pin for a Peel pack.

Reads the shipped art straight out of site/packs/<id>.peel (or the copy under a
hashed directory) so a pin can never drift from what the pack actually contains.

    python3 site/pins/make-pin.py midnight-replies "Cat reply stickers" "for WhatsApp"

Writes site/packs/img/<pack>/pin.png.
"""
import glob
import os
import sys
import zipfile

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PACKS = os.path.join(ROOT, "site", "packs")
IMG = os.path.join(PACKS, "img")

W, H = 1000, 1500
CREAM = (253, 247, 236)
INK = (36, 28, 19)
TANGERINE = (242, 118, 46)
MUTED = (138, 128, 112)

BAR = 14
MARGIN = 70
HEAD_TOP = 112
HEAD_SIZE = 76
HEAD_LEAD = 95
SUB_SIZE = 34
GRID_TOP = 490
CELL = 250
GAP = 8
FOOT_NAME = 1318
FOOT_LINE = 1372
FOOT_URL = 1412

FONTS = os.path.join(ROOT, "play-listing", "promo-2026-10", "public", "fonts")
BOLD = os.path.join(FONTS, "baloo_2_extrabold.ttf")
ROUND = os.path.join(FONTS, "fredoka_bold.ttf")
BODY = "/System/Library/Fonts/Supplemental/Arial.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def pack_archive(pack):
    hits = glob.glob(os.path.join(PACKS, f"{pack}.peel"))
    hits += glob.glob(os.path.join(PACKS, "*", f"{pack}.peel"))
    if not hits:
        raise SystemExit(f"no .peel found for {pack}")
    return hits[0]


def stickers(pack, picks):
    """Return the chosen stickers as RGBA, read from the shipped archive."""
    z = zipfile.ZipFile(pack_archive(pack))
    names = sorted(n for n in z.namelist() if n.startswith("stickers/"))
    out = []
    for i in picks:
        with z.open(names[i - 1]) as fh:
            im = Image.open(fh)
            im.seek(0)
            out.append(im.convert("RGBA"))
    return out


def wrap(draw, text, fnt, width):
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = (line + " " + w).strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def build(pack, title, subtitle, pack_name, picks, out_path=None):
    im = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, BAR], fill=TANGERINE)

    # Shrink the heading until it fits three lines, so a long title can never
    # push the subtitle down into the first row of stickers.
    size = HEAD_SIZE
    while size > 48:
        f_head = font(BOLD, size)
        lines = wrap(d, title, f_head, W - 2 * MARGIN - 380)
        if len(lines) <= 3:
            break
        size -= 4
    lead = int(size * 1.25)

    y = HEAD_TOP
    for line in lines:
        d.text((MARGIN, y), line, font=f_head, fill=INK)
        y += lead

    d.text((MARGIN, y + 18), subtitle, font=font(BODY, SUB_SIZE), fill=MUTED)
    grid_top = max(GRID_TOP, y + 18 + SUB_SIZE + 40)
    if grid_top + 3 * CELL + 2 * GAP > FOOT_NAME - 30:
        grid_top = FOOT_NAME - 30 - (3 * CELL + 2 * GAP)

    art = stickers(pack, picks)
    grid_w = 3 * CELL + 2 * GAP
    x0 = (W - grid_w) // 2
    for i, s in enumerate(art[:9]):
        r, c = divmod(i, 3)
        s = s.copy()
        s.thumbnail((CELL - 10, CELL - 10), Image.LANCZOS)
        x = x0 + c * (CELL + GAP) + (CELL - s.width) // 2
        yy = grid_top + r * (CELL + GAP) + (CELL - s.height) // 2
        im.paste(s, (x, yy), s)

    d.text((MARGIN, FOOT_NAME), pack_name, font=font(ROUND, 36), fill=TANGERINE)
    d.text((MARGIN, FOOT_LINE), "Free download · Peel, the sticker maker for Android",
           font=font(BODY, 28), fill=INK)
    d.text((MARGIN, FOOT_URL), "peel.refineco.app", font=font(BODY, 26), fill=MUTED)

    out_path = out_path or os.path.join(IMG, pack, "pin.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 5:
        raise SystemExit("usage: make-pin.py <pack> <title> <subtitle> <pack name> [piece,piece,...]")
    pack, title, subtitle, name = sys.argv[1:5]
    picks = [int(x) for x in sys.argv[5].split(",")] if len(sys.argv) > 5 else list(range(1, 10))
    print(build(pack, title, subtitle, name, picks))
