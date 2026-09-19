"""Rebuild data/faq.txt from the published FAQ PDF, keyword icons and all.

Why this exists: the FAQ was first captured by pasting the page as text, and that lost every
keyword icon -- the game prints BLOCKER, GO SOLO, PLAY and the rest as coloured chips, and the
Spend Icon as a small glyph, so questions came through reading "If a Unit has , can I use its  the
turn it's played?". 69 of the 269 answers had a hole in them and were unusable as tests.

The icons are not text and not images. Each chip is a filled vector rectangle with the word knocked
out of it, and the Spend Icon is a handful of filled paths, so no text extractor can see any of
them. But a chip's FILL COLOUR and WIDTH identify it exactly, because the box hugs the word: across
all 47 pages every chip falls into one of the seven buckets in CHIPS to within 6% of its measured
width, at either of the two font sizes the document uses. So the icons are *measured* here, not
guessed -- which was the whole objection to filling them in by hand.

Usage::

    python3 tools/faq_from_pdf.py <page-range.pdf> [more.pdf ...] > data/faq.txt

The PDFs are not in the repository: they are the publisher's, they are ~150 MB, and data/faq.txt is
the artifact worth keeping under version control. Pass them in the order the pages run.
"""

from __future__ import annotations

import re
import sys

try:
    import pymupdf
except ImportError:                                   # pragma: no cover - a developer tool
    raise SystemExit("this tool needs pymupdf: pip install pymupdf")

#: (fill colour, width at the 14.1pt size) -> the word the chip prints. Measured from the document.
CHIPS = {
    ((0.93, 0.19, 0.58), 58.38): "BLOCKER",
    ((0.93, 0.19, 0.58), 40.99): "QUICK",
    ((0.99, 0.93, 0.09), 77.43): "ADRENALINE",
    ((0.99, 0.93, 0.09), 56.31): "GO SOLO",
    ((0.99, 0.93, 0.09), 34.80): "PLAY",
    ((0.20, 0.66, 0.30), 50.13): "ATTACK",
    ((0.93, 0.11, 0.16), 63.39): "DEFEATED",
}
#: The Spend Icon, written the way data/cards/wnc.json writes it. The colon printed after it is a
#: drawing too, so it comes back the same way and the FAQ reads as the cards do: "⊡:".
SPEND = "⊡"
#: Ink colours: near-black for a question, grey for an answer. The icons come in both.
INKS = ((0.07, 0.07, 0.07), (0.2, 0.2, 0.2))

#: Span font -> what that line is. The document is rigidly styled, so this is exact rather than
#: heuristic: a question is Bold 11.7, an answer is Book 11.2, a card heading is Heavy 12.8.
ROLES = {("BlenderPro-Heavy", 12.8): "card", ("BlenderPro-Heavy", 18.1): "section",
         ("BlenderPro-Bold", 11.7): "q", ("BlenderPro-Book", 11.2): "a"}


def chip_word(fill, w: float, h: float) -> str | None:
    if fill is None:
        return None
    f = tuple(round(x, 2) for x in fill)
    if f in INKS:
        if 7.5 <= w <= 9.5 and 8.0 <= h <= 9.5:
            return SPEND
        if 1.0 <= w <= 2.0 and 4.0 <= h <= 5.2:
            return ":"
        return None
    best, score = None, 1e9
    for (cf, cw), word in CHIPS.items():
        if cf == f and (d := abs(w - cw * (h / 14.1)) / cw) < score:
            best, score = word, d
    return best if score < 0.06 else None


def page_rows(pg) -> list[tuple[str, str]]:
    """(role, text) per printed line, with the icons woven back in where they were drawn."""
    # Every glyph is drawn at least twice at identical coordinates (fill, then overprint), so
    # dedupe on the exact rectangle or each icon comes back doubled.
    icons, seen = [], set()
    for d in pg.get_drawings():
        r = d["rect"]
        word = chip_word(d.get("fill"), r.width, r.height)
        if word is None:
            continue
        key = (round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2), word)
        if key not in seen:
            seen.add(key)
            icons.append((r.y0 + r.height / 2, r.x0, word))
    runs = []
    for b in pg.get_text("dict")["blocks"]:
        if b["type"] == 1:                            # the card image printed beside each section
            continue
        for ln in b["lines"]:
            sp = ln["spans"][0]
            role = ROLES.get((sp["font"], round(sp["size"], 1)))
            txt = "".join(s["text"] for s in ln["spans"])
            if role and txt.strip():
                runs.append({"y": (ln["bbox"][1] + ln["bbox"][3]) / 2, "x": ln["bbox"][0],
                             "role": role, "t": txt})
    # One printed line is several runs: an icon breaks the text into a run either side of it. Group
    # them back by baseline BEFORE placing the icons, or an icon lands at the end of the first run
    # instead of between them -- which read as "If a Unit has ADRENALINE ⊡: , can I use its the
    # turn it's played?" for a line that prints the Spend Icon in the middle.
    runs.sort(key=lambda r: (r["y"], r["x"]))
    lines: list[dict] = []
    for r in runs:
        if lines and abs(lines[-1]["y"] - r["y"]) <= 5 and lines[-1]["role"] == r["role"]:
            lines[-1]["parts"].append((r["x"], r["t"]))
        else:
            lines.append({"y": r["y"], "x": r["x"], "role": r["role"], "parts": [(r["x"], r["t"])]})
    for cy, x, word in icons:
        near = [ln for ln in lines if abs(ln["y"] - cy) <= 9]
        if near:
            min(near, key=lambda ln: abs(ln["y"] - cy))["parts"].append((x, word))
    out = []
    for ln in lines:
        line = ""
        for _, t in sorted(ln["parts"], key=lambda p: p[0]):
            if line and not line.endswith(" ") and not t.startswith((" ", ",", ".", "?", ":", ";")):
                line += " "
            line += t
        out.append((ln["role"], tidy(line)))
    return out


def tidy(s: str) -> str:
    """A chip sits in its own run, so the fragment after it often begins with the space the layout
    put there: "does it still have ADRENALINE ?". Close those up."""
    return re.sub(r"\s+([?.,;:!])", r"\1", re.sub(r" +", " ", s)).strip()


HEADER = """\
# Official Cyberpunk TCG FAQ, rebuilt from the published PDF by tools/faq_from_pdf.py.
#
# Format: a heading line naming the card (or GENERAL), then alternating question and answer lines.
# A line beginning "#" is a comment. Blank lines separate entries and are ignored.
#
# The keyword icons are here. The game prints them as coloured chips and a Spend Icon glyph, all
# drawn as vector art rather than typed, so the first capture of this FAQ -- pasted as text -- lost
# every one of them and 69 answers read with a hole where a keyword should be. They are recovered
# from the PDF by the fill colour and width of each chip, which identify it exactly; see the tool
# for the measured table. Nothing here is a guess about which icon was meant.
"""


def _fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _same(a: str, b: str) -> bool:
    """Is one line the page-break reprint of the other?

    Not equality. The masked copy at the foot of a page is drawn through the clip, and what
    survives varies: sometimes only an apostrophe is lost, sometimes a keyword chip, and once most
    of the letters ("D th Gi I d ith th ff t..." for "Does the Gig I decrease with the effect...").
    So this asks whether the shorter reads as a subsequence of the longer, which every one of those
    is, and which a genuine continuation line -- different words entirely -- is not.
    """
    x, y = sorted((_fold(a), _fold(b)), key=len)
    if not x or len(x) < len(y) * 0.25:
        return False
    it = iter(y)
    return all(c in it for c in x)


def _run(rows: list, end: bool) -> tuple[int, str]:
    """The trailing (or leading) run of same-role lines, as one string plus its length."""
    if not rows:
        return 0, ""
    role = rows[-1][0] if end else rows[0][0]
    n = 0
    while n < len(rows) and rows[-1 - n if end else n][0] == role:
        n += 1
    part = rows[-n:] if end else rows[:n]
    return n, " ".join(t for _, t in part)


def main(paths: list[str]) -> None:
    rows: list[tuple[str, str]] = []
    for p in paths:
        for pg in pymupdf.open(p):
            fresh = page_rows(pg)
            # A paragraph broken by a page break is printed TWICE: once at the foot of the page,
            # where the layout masks it, and again in full at the head of the next. Both are in the
            # content stream, so one copy has to go here or the question comes out saying itself
            # twice. Compare whole runs, not single lines: an icon splits a printed line into
            # several rows, so the duplicate is never a row-for-row match.
            if rows and fresh and rows[-1][0] == fresh[0][0]:
                na, a = _run(rows, True)
                nb, b = _run(fresh, False)
                if _same(a, b):
                    if len(_fold(b)) > len(_fold(a)):
                        del rows[-na:]
                    else:
                        del fresh[:nb]
            rows += fresh
    # Merge wrapped lines: consecutive lines in the same role are one paragraph.
    merged: list[tuple[str, str]] = []
    for role, text in rows:
        if merged and merged[-1][0] == role and role in ("q", "a"):
            merged[-1] = (role, tidy(merged[-1][1] + " " + text))
        else:
            merged.append((role, text))
    out, heading, pending = [HEADER], None, None
    for role, text in merged:
        if role == "section":
            heading = "GENERAL" if text.upper().startswith("GENERAL") else None
            out.append(f"\n{heading}" if heading else "")
        elif role == "card":
            heading = text
            out.append(f"\n{heading}")
        elif role == "q":
            if pending is not None:
                raise SystemExit(f"two questions in a row under {heading!r}: {pending!r}")
            pending = text
        else:
            if pending is None:
                raise SystemExit(f"answer with no question under {heading!r}: {text!r}")
            out.append(pending)
            out.append(text)
            pending = None
    if pending is not None:
        raise SystemExit(f"dangling question under {heading!r}: {pending!r}")
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
