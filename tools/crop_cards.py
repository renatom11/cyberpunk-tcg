"""Cut card faces out of screenshots of cyberpunktcg.com/cards and save one JPEG per card id.

The card database renders a 4-column grid: each tile is the card face with its name (and
subtitle) printed underneath. We OCR every screenshot, take each caption that sits at a column's
left edge, and crop the fixed-size face above it. Captions are matched to card ids by name and
subtitle, so the order of the screenshots does not matter and overlapping screenshots simply
yield the same card twice (the first fully visible crop wins).

Requires Pillow and rapidocr-onnxruntime (pure offline OCR):
    pip install pillow rapidocr-onnxruntime
Usage:
    python tools/crop_cards.py SHOT.png [SHOT2.png ...] --out data/images [--back BACK.png]   (writes data/images/<id>.jpg)
The geometry below is for a 1920-wide browser window at 100% zoom; pass --scale to adjust.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]

# Tile geometry at 1920 px width: the face is 423x590; the caption starts 21 px right of the
# face's left edge and 31 px below its bottom edge.
FACE_W, FACE_H = 423, 590
NAME_DX, NAME_DY = 21, 31
HEADER_BOTTOM = 192          # the site's sticky header covers the top of the page
SUBTITLE_DY = 37             # a subtitle line sits this far below the name line
PAGE_BOTTOM = 1125           # Windows taskbar below this in the screenshots


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def load_cards() -> list[dict]:
    return json.loads((ROOT / "data/cards/wnc.json").read_text())["cards"]


def match(cards: list[dict], name: str, subtitle: str | None) -> tuple[dict | None, float, bool]:
    """Best card for an OCR'd caption: (card, score, matched_by_subtitle_only).

    Names are compared first and a subtitle breaks ties. A one-letter name such as "V" never
    survives OCR, so a caption whose only line is a subtitle is also tried against subtitles of
    cards with names of at most two characters."""
    n = norm(name)
    scored = []
    for c in cards:
        r = difflib.SequenceMatcher(None, n, norm(c["name"])).ratio()
        if subtitle and c.get("subtitle"):
            r = 0.5 * r + 0.5 * difflib.SequenceMatcher(None, norm(subtitle), norm(c["subtitle"])).ratio()
        elif subtitle or c.get("subtitle"):
            r -= 0.15                      # one side has a subtitle and the other doesn't
        scored.append((r, c, False))
        if subtitle is None and c.get("subtitle") and len(c["name"]) <= 2:
            scored.append((difflib.SequenceMatcher(None, n, norm(c["subtitle"])).ratio() - 0.02, c, True))
    scored.sort(key=lambda t: -t[0])
    return (scored[0][1], scored[0][0], scored[0][2]) if scored else (None, 0.0, False)


def captions(ocr_boxes, scale: float):
    """Yield (x0, y0, name, subtitle) for caption names: large text that another caption line
    (a subtitle, a type badge or the COST/RAM line) follows within the tile."""
    boxes = []
    for box, text, conf in ocr_boxes:
        x0 = min(p[0] for p in box); y0 = min(p[1] for p in box)
        x1 = max(p[0] for p in box); y1 = max(p[1] for p in box)
        boxes.append((x0 / scale, y0 / scale, x1 / scale, y1 / scale, text, conf))
    badges = {"UNIT", "GEAR", "PROGRAM", "LEGEND"}
    for x0, y0, x1, y1, text, conf in boxes:
        h = y1 - y0
        if not 20 <= h <= 34 or conf < 0.6 or text.upper() in badges or text.upper().startswith("COST"):
            continue
        # a caption name has a type badge ~90 px below it (or a subtitle ~37 px below and the badge
        # ~125 px below). A lone subtitle (one-letter names like "V" never OCR) has the badge ~52 px
        # below; a subtitle under a detected name is skipped so it isn't read as a second card.
        below = [b for b in boxes if abs(b[0] - x0) < 40 and b[1] > y1]
        badge = [b for b in below if b[4].upper() in badges and 45 < b[1] - y0 < 140]
        above = [b for b in boxes if abs(b[0] - x0) < 40 and 28 < y0 - b[1] < 50 and 20 <= b[3] - b[1] <= 34]
        if not badge or above:
            continue
        sub = [b for b in below if 28 < b[1] - y0 < 50 and 18 <= b[3] - b[1] <= 30 and b[4].upper() not in badges]
        yield x0, y0, text, (sub[0][4] if sub else None)


def legend_back(back: Image.Image, yellow=(255, 230, 0)) -> Image.Image:
    """Legend cards have the same back with the two colours swapped: yellow shapes on black.
    Map luminance onto the yellow so black areas become yellow and yellow areas become black.

    The two levels are read off the histogram, not from ``getextrema``. The back is two inks, so the
    yellow's own luminance (about 214 in ITU-R 601, not 255) is what has to land on black; measuring
    against the brightest pixel instead leaves the whole field at RGB(44, 39, 0), a dark olive rather
    than the black the printed Legend back actually is. Percentiles also ignore the few blown-out
    pixels and the JPEG ringing at the ink boundary, which extrema do not.
    """
    lum = back.convert("L")
    hist = lum.histogram()
    total = sum(hist)

    def level(frac: float) -> int:
        seen = 0
        for v, n in enumerate(hist):
            seen += n
            if seen >= frac * total:
                return v
        return 255

    lo, hi = level(0.05), level(0.95)            # the black ink and the yellow ink
    span = max(1, hi - lo)
    inv = lum.point(lambda v: max(0, min(255, 255 - round(255 * (v - lo) / span))))
    return Image.merge("RGB", [inv.point(lambda v, c=c: v * c // 255) for c in yellow])


def crop_all(paths: list[Path], out: Path, scale: float, back: Path | None) -> dict:
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()
    cards = load_cards()
    out.mkdir(parents=True, exist_ok=True)
    found: dict[str, tuple[Path, float]] = {}
    unmatched = []
    for path in paths:
        im = Image.open(path).convert("RGB")
        res, _ = ocr(str(path))
        for x0, y0, name, sub in captions(res or [], scale):
            card, score, by_subtitle = match(cards, name, sub)
            fx0 = int(round(x0 - NAME_DX))
            fy1 = int(round(y0 - NAME_DY - (SUBTITLE_DY if by_subtitle else 0)))
            fy0 = fy1 - FACE_H
            fx1 = fx0 + FACE_W
            if fy0 < HEADER_BOTTOM or fy1 > PAGE_BOTTOM or fx0 < 0 or fx1 > im.width:
                continue                                    # partly hidden: another screenshot has it
            if card is None or score < 0.6:
                unmatched.append((path.name, name, sub, round(score, 2)))
                continue
            if card["id"] in found and found[card["id"]][1] >= score:
                continue
            face = im.crop((int(fx0 * scale), int(fy0 * scale), int(fx1 * scale), int(fy1 * scale)))
            if scale != 1:
                face = face.resize((FACE_W, FACE_H), Image.LANCZOS)
            # Browser screenshots (often WebP) soften the card's fine text; a light unsharp mask
            # brings the edges back without inventing detail.
            face = face.filter(ImageFilter.UnsharpMask(radius=1.2, percent=90, threshold=2))
            dest = out / f"{card['id']}.jpg"
            face.save(dest, quality=93, optimize=True, subsampling=0)
            found[card["id"]] = (dest, score)
    if back is not None:
        bk = Image.open(back).convert("RGB").resize((FACE_W, FACE_H), Image.LANCZOS)
        bk.save(out / "_back.jpg", quality=93, optimize=True, subsampling=0)
        legend_back(bk).save(out / "_back_legend.jpg", quality=93, optimize=True, subsampling=0)
    missing = [c["id"] for c in cards if c["id"] not in found]
    return {"found": {k: (str(v[0]), v[1]) for k, v in found.items()}, "missing": missing, "unmatched": unmatched}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("shots", nargs="+")
    ap.add_argument("--out", default=str(ROOT / "data/images"))
    ap.add_argument("--scale", type=float, default=1.0, help="screenshot width / 1920")
    ap.add_argument("--back", help="card back image to store as _back.png")
    args = ap.parse_args()
    report = crop_all([Path(p) for p in args.shots], Path(args.out), args.scale, Path(args.back) if args.back else None)
    print(f"{len(report['found'])} cards cropped, {len(report['missing'])} missing")
    low = sorted((v[1], k) for k, v in report["found"].items())[:8]
    print("lowest-confidence matches:", [(k, round(s, 2)) for s, k in low])
    if report["missing"]:
        print("missing:", ", ".join(report["missing"]))
    if report["unmatched"]:
        print("unmatched captions:", report["unmatched"][:12])


if __name__ == "__main__":
    main()
