"""Precompute "how many threats can the rival still be holding" into a literal.

    python tools/build_threat_table.py            # rewrites src/cptcg/learn/threats.py

Why a table and not a lookup
----------------------------
``learn/features.py`` costs about 49 us and is called millions of times in a fit. Walking 151 cards
and a 1,347-edge graph inside it is not affordable, and a lazily-loaded data file that degrades to
zeros when it is missing is exactly the failure that left the website's card guide showing no
connections for a day — nothing raised, the page rendered, the numbers looked plausible.

The collapse that makes a table possible: the number of threat-carrying cards of colour X the rival
could still hold depends **only** on colour X's largest still-possible cumulative RAM, and that is
one of {0, 2, 4, 6} because every Legend is 2 RAM and there are three of them. So the whole answer
is ``THREATS[threat][colour][cap // 2]`` — a few dozen integers, no file, no graph, O(1).

The generated module is committed, like ``data/strategy/graph.json`` is. A test regenerates it in
memory and fails if the committed copy disagrees, so editing the interaction map without rebuilding
cannot pass unnoticed — the map has already been wrong once, at Chrome Reverie, in a way nothing
detected.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.enums import Color  # noqa: E402
from cptcg.learn.opponent import LEGEND_SLOTS, THREATS, legend_ram  # noqa: E402

GRAPH = ROOT / "data" / "strategy" / "graph.json"
OUT = ROOT / "src" / "cptcg" / "learn" / "threats.py"


def build(reg, graph: dict) -> tuple[dict, int]:
    """``{threat: [[count per cap] per colour]}`` plus the size of the unrestricted pool.

    Index the inner list by ``cap // ram``, so 0 RAM (the colour is impossible) is index 0 and
    reads zero by construction rather than by a special case.
    """
    ram = legend_ram(reg)
    caps = [ram * k for k in range(LEGEND_SLOTS + 1)]          # 0, 2, 4, 6
    cards = graph["cards"]
    table: dict[str, list[list[int]]] = {}
    for t in THREATS:
        per_colour = []
        for c in range(len(Color)):
            row = []
            for cap in caps:
                n = 0
                if cap > 0:
                    for d in reg.defs:
                        if d.is_legend or int(d.color) != c or d.ram > cap:
                            continue
                        if t in ((cards.get(d.id) or {}).get("produces") or ()):
                            n += 1
                row.append(n)
            per_colour.append(row)
        table[t] = per_colour
    # Same collapse for the pool itself: how many non-Legend cards of this colour fit under a cap.
    pool_rows = []
    for c in range(len(Color)):
        pool_rows.append([sum(1 for d in reg.defs
                              if not d.is_legend and int(d.color) == c and d.ram <= cap) if cap else 0
                          for cap in caps])
    pool = sum(1 for d in reg.defs if not d.is_legend)
    return table, pool, pool_rows


def render(table: dict, pool: int, ram: int, pool_rows: list) -> str:
    lines = [
        '"""Threat counts over the rival\'s still-possible card pool. **Generated — do not edit.**',
        "",
        "Rebuild with ``python tools/build_threat_table.py`` after any change to",
        "``data/strategy/graph.json``; ``tests/learn/test_opponent.py`` fails if this disagrees with",
        "the graph. See that tool's docstring for why this is a literal rather than a lookup.",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        f"#: Non-Legend cards in the set. The denominator for 'how much of their deck is still open'.",
        f"POOL = {pool}",
        "",
        "#: RAM on a Legend, and so the step between caps. Index a row with ``cap // RAM``.",
        f"RAM = {ram}",
        "",
        "#: ``THREAT_TABLE[token][colour][cap // RAM]`` — cards of that colour carrying that threat",
        "#: whose RAM fits under that cap. Colour index is ``core.enums.Color``.",
        "THREAT_TABLE = {",
    ]
    for t, rows in table.items():
        lines.append(f"    {t!r}: [")
        for c, row in enumerate(rows):
            lines.append(f"        {row},    # {Color(c).name}")
        lines.append("    ],")
    lines.append("}")
    lines.append("")
    lines.append("#: ``POOL_TABLE[colour][cap // RAM]`` — non-Legend cards of that colour that fit")
    lines.append("#: under that cap. Summed over colours this is the size of the rival's live pool.")
    lines.append("POOL_TABLE = [")
    for c, row in enumerate(pool_rows):
        lines.append(f"    {row},    # {Color(c).name}")
    lines.append("]")
    lines.append("")
    lines.append("#: The order the feature vector emits them in. Fixed here so a dict reordering")
    lines.append("#: cannot silently permute fifteen features under a fitted model.")
    lines.append("THREAT_ORDER = (" + ", ".join(repr(t) for t in table) + ",)")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    reg = load_default()
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    table, pool, pool_rows = build(reg, graph)
    OUT.write_text(render(table, pool, legend_ram(reg), pool_rows), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(table)} threats x {len(Color)} colours, pool {pool}")
    for t, rows in table.items():
        print(f"  {t:20s} open board {sum(r[-1] for r in rows):3d}  "
              f"mono-colour best/worst {max(r[-1] for r in rows)}/{min(r[-1] for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
