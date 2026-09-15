"""Turn the verbatim FAQ text into data/faq.json, resolving headings to card ids.

data/faq.txt is the authority, kept exactly as published. This turns it into something the engine,
the tests and the client can read, and it is the only place a heading is matched to a card id -- so
a renamed or removed card fails here, loudly, instead of quietly dropping that card's rulings.

The icons are the known defect. The game prints keywords as symbols and they did not survive
transcription, so a question can read "If a Unit has , can I use its  the turn it's played?". Those
entries are marked ``icons_missing`` rather than repaired: an icon guessed wrong becomes a test
asserting the wrong rule, which is worse than no test. Everything downstream skips them until the
symbols are supplied.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402

#: A gap where a symbol was: two spaces, or a space before punctuation that should follow a word.
GAP = re.compile(r"  +|\s+[?.,]|^\s|\s$")


#: Headings the FAQ spells differently from the card data. Kept explicit rather than folded into
#: norm(), so the disagreement is visible: the card face is the tie-breaker and neither source is
#: silently "corrected" to match the other.
#:   MT0D12 / MTOD12 -- the FAQ writes a digit zero, data/cards/wnc.json writes a letter O. One of
#:   the two transcriptions is wrong about a glyph on the printed card; until the image settles it,
#:   the alias keeps the card's rulings attached rather than dropping them.
ALIASES = {"MT0D12 FLATHEAD": "mtod12-flathead"}


def norm(s: str) -> str:
    """Compare names loosely: case, punctuation and accents are all transcription hazards."""
    s = s.lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"),
                 ("ú", "u"), ("ñ", "n"), ("à", "a"), ("è", "e")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "", s)


def parse(text: str) -> tuple[list[dict], dict[str, list[dict]]]:
    general: list[dict] = []
    cards: dict[str, list[dict]] = {}
    heading = None
    pending: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("#") or not line.strip():
            continue
        # A heading is a line in caps that is not a question and not an answer.
        if line == line.upper() and not line.endswith("?") and len(line) < 70 and not pending:
            heading = line.strip()
            continue
        pending.append(line)
        if len(pending) == 2:
            q, a = pending
            pending = []
            entry = {"q": q.strip(), "a": a.strip()}
            if GAP.search(q) or GAP.search(a):
                entry["icons_missing"] = True
            if heading == "GENERAL":
                general.append(entry)
            else:
                cards.setdefault(heading, []).append(entry)
    if pending:
        raise SystemExit(f"dangling question with no answer under {heading!r}: {pending}")
    return general, cards


def resolve(cards: dict[str, list[dict]], reg) -> tuple[dict[str, list[dict]], list[str]]:
    by_name = {}
    for d in reg.defs:
        full = f"{d.name}: {d.subtitle}" if d.subtitle else d.name
        by_name.setdefault(norm(full), d.id)
        by_name.setdefault(norm(d.name), d.id)
    out, missing = {}, []
    for heading, entries in cards.items():
        cid = ALIASES.get(heading) or by_name.get(norm(heading))
        if cid is None:
            missing.append(heading)
            continue
        out[cid] = entries
    return out, missing


def main() -> None:
    reg = load_default()
    general, cards = parse((ROOT / "data" / "faq.txt").read_text(encoding="utf-8"))
    resolved, missing = resolve(cards, reg)
    flagged = sum(1 for e in general if e.get("icons_missing")) + \
        sum(1 for v in resolved.values() for e in v if e.get("icons_missing"))
    n = len(general) + sum(len(v) for v in resolved.values())
    print(f"general {len(general)} | cards {len(resolved)} | entries {n} | icons missing {flagged}")
    if missing:
        print(f"UNRESOLVED HEADINGS ({len(missing)}):")
        for m in missing:
            print("   ", m)
        raise SystemExit(1)
    (ROOT / "data" / "faq.json").write_text(
        json.dumps({"general": general, "cards": resolved}, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print("wrote data/faq.json")


if __name__ == "__main__":
    main()
