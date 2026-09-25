"""The leakage instrument (design Part 5, C3c denial): how much a player's play tells the rival.

    python tools/leakage.py CORPUS [CORPUS ...] [--games 500] [--out J]

For every game and each seat, at the end of each of that seat's turns the rival's public-evidence
reading of the seat is taken (``learn.opponent``: the colour bounds and the possible pool, exactly
what the rival's search and belief inputs see):

* **pool**: how many main-deck cards the seat could still be holding, in the rival's eyes;
* **entropy**: the entropy (bits) of the rival's belief over the seat's hidden cards — the
  copies-weighted distribution ``RivalPrior.allow``, i.e. what a sampled world draws from;
* **triple proven**: the first of the seat's turns after which all three Legend colours are proven
  (the bounds sum to three), or never.

Reported per agent and per colour class of the seat's deck (the class alone moves these numbers a
lot: a mono deck's first card proves little and its RAM-5 card proves everything), with
per-game bootstrap intervals. A denial-aware player shows a larger pool and a higher entropy after
the same turn, and proves its triple later, *on the same decks*; comparing agents on different
deck samples confounds the deck with the player, which is why the class split is reported and why
the design's paired control (same decks, same seeds) is the version to trust when it exists.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.learn.experience import read_games  # noqa: E402
from cptcg.learn.opponent import RivalPrior, colour_bounds, possible_pool  # noqa: E402

TURNS = 7          # own turns reported (the fixer empties after six, Overtime follows)


def colour_class(reg, legends) -> str:
    by = {d.id: d for d in reg.defs}
    cols = [by[l].color.name for l in legends]
    k = sorted((cols.count(c) for c in set(cols)), reverse=True)
    return {(3,): "mono", (2, 1): "two-plus-one", (1, 1, 1): "one-of-each"}[tuple(k)]


def reading(s, seat: int) -> tuple[int, float, bool]:
    """(pool, entropy bits, triple proven) of the rival's reading of ``seat``."""
    rival = 1 - seat
    bounds = colour_bounds(s, rival)
    pool = len(possible_pool(s.reg, bounds))
    allow = RivalPrior(s, rival).allow
    tot = sum(allow.values())
    ent = -sum((n / tot) * math.log2(n / tot) for n in allow.values() if n) if tot else 0.0
    return pool, ent, sum(bounds) >= 3


def game_readings(reg, rec) -> dict:
    """Per seat: list over its own turns of (pool, entropy), and the turn its triple was proven."""
    s = new_game(reg, rec.replay().decklists(), rec.seed, DEFAULT_CONFIG)
    out = {0: {"turns": [], "proven": None}, 1: {"turns": [], "proven": None}}
    last_active = None
    for idx in rec.actions:
        legal_actions(s)
        if last_active is not None and s.active != last_active:
            seat = last_active
            pool, ent, proven = reading(s, seat)
            rows = out[seat]["turns"]
            rows.append((pool, ent))
            if proven and out[seat]["proven"] is None:
                out[seat]["proven"] = len(rows)
        last_active = s.active
        apply(s, idx)
    return out


def _ci(values: list[float], rng: random.Random, n: int = 1000) -> list[float]:
    if not values:
        return [None, None]
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(n))
    return [means[int(0.025 * n)], means[int(0.975 * n) - 1]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpora", nargs="+")
    ap.add_argument("--games", type=int, default=500, help="per corpus")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    reg = load_default()
    # (agent, class) -> per game: pools by turn, entropies by turn, proven turn
    acc: dict = defaultdict(lambda: {"pool": defaultdict(list), "ent": defaultdict(list), "proven": []})
    for src in a.corpora:
        for gi, rec in enumerate(read_games(src)):
            if gi >= a.games:
                break
            r = game_readings(reg, rec)
            decks = rec.replay().decklists()
            for seat in (0, 1):
                key = (rec.agents[seat] if rec.agents else "?", colour_class(reg, decks[seat].legends))
                for k, (pool, ent) in enumerate(r[seat]["turns"][:TURNS], start=1):
                    acc[key]["pool"][k].append(pool)
                    acc[key]["ent"][k].append(ent)
                acc[key]["proven"].append(r[seat]["proven"])
    rng = random.Random(20260925)
    report = []
    for (agent, cls), d in sorted(acc.items()):
        proven = [p for p in d["proven"] if p is not None]
        row = {"agent": agent, "class": cls, "seats": len(d["proven"]),
               "never_proven": sum(1 for p in d["proven"] if p is None) / max(1, len(d["proven"])),
               "median_turn_proven": sorted(proven)[len(proven) // 2] if proven else None,
               "pool_by_turn": {k: sum(v) / len(v) for k, v in sorted(d["pool"].items())},
               "entropy_by_turn": {k: sum(v) / len(v) for k, v in sorted(d["ent"].items())},
               "pool_turn3_ci95": _ci(d["pool"].get(3, []), rng),
               "entropy_turn3_ci95": _ci(d["ent"].get(3, []), rng)}
        report.append(row)
        pb = row["pool_by_turn"]
        print(f"{agent:14s} {cls:13s} seats {row['seats']:5d}  pool t1/t3/t5 "
              f"{pb.get(1, float('nan')):.0f}/{pb.get(3, float('nan')):.0f}/{pb.get(5, float('nan')):.0f}  "
              f"entropy t3 {row['entropy_by_turn'].get(3, float('nan')):.2f}  "
              f"triple proven median turn {row['median_turn_proven']}  never {row['never_proven']:.0%}")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps({"corpora": a.corpora, "games": a.games, "rows": report}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
