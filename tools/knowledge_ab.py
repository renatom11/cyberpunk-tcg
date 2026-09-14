"""Does a bigger card-value store build better decks? Paired by construction.

    python tools/knowledge_ab.py --slots 48 --games 60 \
        --old out/knowledge.json --new data/strategy/knowledge.json

For each slot both builders get the **same Legends, the same RNG seed and the same strategy**
(Explorer). The only difference between the two decks is the store they consult for a card's
learned value, so the match that follows is a paired comparison of the stores rather than of two
deck-building ideas.

Read the slot-level interval, not the game-level one. Sixty games inside one slot are sixty samples
of one deck pair, not sixty independent samples of "decks built this way": the game-level interval
treats them as independent and comes out roughly twice as tight as the evidence supports. The unit
of evidence here is the slot.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default      # noqa: E402
from cptcg.core.rng import Pcg32                   # noqa: E402
from cptcg.deck.builder import random_legends      # noqa: E402
from cptcg.deck.knowledge import Knowledge         # noqa: E402
from cptcg.deck.strategies import Explorer         # noqa: E402
from cptcg.deck.validate import validate           # noqa: E402
from cptcg.sim.runner import run_match             # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/knowledge_ab.py", description=__doc__.split("\n")[0])
    ap.add_argument("--slots", type=int, default=48, help="deck pairs; the unit of evidence")
    ap.add_argument("--games", type=int, default=60, help="games per slot, mirrored seats")
    ap.add_argument("--old", default="out/knowledge.json")
    ap.add_argument("--new", default="data/strategy/knowledge.json")
    ap.add_argument("--agent", default="heuristic")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args(argv)

    reg = load_default()
    old, new = Knowledge.load(a.old, reg), Knowledge.load(a.new, reg)
    print(f"old {a.old}: {len(old.cards)} cards; new {a.new}: {len(new.cards)} cards")

    wins = games = 0
    rates, lines = [], []
    for i in range(a.slots):
        legs = random_legends(reg, Pcg32(5000 + i, seq=2))
        decks = {}
        for tag, kn in (("old", old), ("new", new)):
            d = Explorer().build(reg, legs, Pcg32(7000 + i, seq=3), knowledge=kn, name=f"{tag}{i:02d}")
            if not validate(d, reg).ok:
                decks = None
                break
            decks[tag] = d
        if not decks:
            lines.append(f"{i}:invalid")
            continue
        if decks["old"].main == decks["new"].main and decks["old"].legends == decks["new"].legends:
            lines.append(f"{i}:identical")       # the stores disagreed about nothing here
            continue
        m = run_match(decks["new"], decks["old"], a.agent, a.agent, a.games,
                      seed=31_000 + i * 97, workers=a.workers)
        wins += m.a_wins
        games += m.n
        rates.append(m.a_wins / m.n)
        lines.append(f"{i}:{m.a_wins}/{m.n}")

    p = wins / games
    se = (p * (1 - p) / games) ** 0.5
    print(f"\nnew-store decks won {wins} of {games} games ({p:.3f})")
    print(f"  game-level 95% interval {p - 1.96 * se:.3f} .. {p + 1.96 * se:.3f}"
          f"   <- too tight: games inside a slot share one deck pair")
    if len(rates) > 2:
        m_ = sum(rates) / len(rates)
        var = sum((x - m_) ** 2 for x in rates) / (len(rates) - 1)
        se2 = (var / len(rates)) ** 0.5
        t = 2.13 if len(rates) < 20 else 2.01
        print(f"  slot-level mean {m_:.3f}, sd {var ** 0.5:.3f}, "
              f"95% interval {m_ - t * se2:.3f} .. {m_ + t * se2:.3f}   <- the honest one")
        print(f"  slots won {sum(1 for x in rates if x > 0.5)}, "
              f"lost {sum(1 for x in rates if x < 0.5)}, of {len(rates)} played")
    print("per slot: " + ", ".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
