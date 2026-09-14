"""What a Legend is worth, measured by swapping it out and replaying the same games.

    python tools/legend_swap.py --deck data/decks/the_heist.json --seeds 120
    python tools/legend_swap.py --all --seeds 80 --out out/legends.json

Why the obvious number is not the number
----------------------------------------
``tools/playtest.py`` finally gives every Legend a win rate when played, and for a Legend that
statistic is almost entirely a fact about the deck it was in. There is no "not drawn" arm to
difference it against — a Legend is never drawn — so unlike IWD it is a *level*, not a contrast.
The first sweep made that unmissable: the six Yellow Legends came back at .56-.62 and the six Blue
ones at .28-.32, in blocks, with near-identical sample sizes, because each block is the same handful
of decks played over and over. Reporting that as "Yellow Legends are twice as good" would be
reporting the decks.

The paired swap is the causal instrument the repo already uses for main-deck cards (``hill_climb``
accepts a swap only on the discordant games). This applies it to the Legend row:

1. play the deck against a fixed field on a fixed set of seeds;
2. replace **one** Legend, keeping every other card and the deck's legality, and replay the *same*
   seeds against the *same* field;
3. count only the **discordant** games — the ones exactly one arm won. Everything else is shared
   variance the pairing removes.

A swap is only offered when the deck stays legal afterwards. That constraint is not incidental: a
Legend carries 2 RAM of its colour, so removing it can put every card of that colour above the cap,
and the set of legal replacements for a given deck is often one or two Legends rather than twenty-
six. What comes out is therefore not a ranking of all Legends against each other — it is, per deck,
"this Legend against the Legends that could actually have taken its slot", which is the question a
deckbuilder is really asking.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.enums import CardType  # noqa: E402
from cptcg.deck.builder import FieldEvaluator  # noqa: E402
from cptcg.deck.decklist import Decklist  # noqa: E402
from cptcg.deck.validate import validate  # noqa: E402
from cptcg.sim.stats import binomial_p_two_sided, wilson  # noqa: E402

#: The gauntlet every arm is played against. Fixed, so two arms differ only in the Legend.
FIELD = ["sample_gangers", "sample_netrunners", "sample_arasaka", "sample_fixers"]
#: Decks whose Legend row gets tested under ``--all``.
SUBJECTS = FIELD + ["the_heist", "embracing_power", "sample_corpos", "sample_nomads"]


def _deck(name: str) -> Decklist:
    for folder in (ROOT / "data" / "decks", ROOT / "tests" / "fixtures" / "decks"):
        p = folder / f"{name}.json"
        if p.exists():
            return Decklist.load(p)
    return Decklist.load(name)


def candidates(reg, deck: Decklist, slot: int) -> list[str]:
    """Legends that could legally sit in ``slot`` of ``deck``, the incumbent excluded."""
    out = []
    for d in reg.defs:
        if d.type is not CardType.LEGEND or d.id == deck.legends[slot]:
            continue
        legends = list(deck.legends)
        legends[slot] = d.id
        if len({reg.get(c).name for c in legends}) != len(legends):
            continue                                  # Legend names must be unique
        cand = Decklist(deck.name, tuple(legends), deck.main, dict(deck.meta))
        if validate(cand, reg).ok:
            out.append(d.id)
    return out


def swap_test(reg, ev: FieldEvaluator, deck: Decklist, slot: int, other: str, seeds: list[int]) -> dict:
    legends = list(deck.legends)
    incumbent = legends[slot]
    legends[slot] = other
    cand = Decklist(deck.name, tuple(legends), deck.main, dict(deck.meta))
    base = ev.outcomes_parallel(deck, seeds)
    new = ev.outcomes_parallel(cand, seeds)
    disc = wins = 0
    for key, won in new.items():
        if key not in base:
            continue
        if won != base[key]:
            disc += 1
            wins += int(won)
    lo, hi = wilson(wins, disc) if disc else (0.0, 1.0)
    return {"slot": slot, "out": incumbent, "in": other, "games": len(new),
            "discordant": disc, "candidate_wins": wins,
            "delta": (2 * wins - disc) / len(new) if new else 0.0,
            "wilson": [lo, hi], "p": binomial_p_two_sided(wins, disc) if disc else 1.0}


def run(a) -> int:
    reg = load_default()
    names = SUBJECTS if a.all else [a.deck]
    seeds = [a.seed * 1000 + k for k in range(a.seeds)]
    out = []
    for name in names:
        deck = _deck(name)
        # Excluded by *file*, not by display name: two files can carry the same "name" field, and a
        # deck played against itself is a 50% mirror that dilutes every delta toward zero.
        opponents = [_deck(f) for f in FIELD if f != name]
        ev = FieldEvaluator(reg, opponents, a.agent, a.workers)
        print(f"\n=== {name}  ({len(seeds)} seeds x {len(ev.field)} opponents x 2 seats)")
        for slot, incumbent in enumerate(deck.legends):
            cands = candidates(reg, deck, slot)
            if not cands:
                print(f"  slot {slot}  {incumbent:46s} no legal replacement — the deck's cards "
                      f"need this colour's RAM")
                continue
            rows = [swap_test(reg, ev, deck, slot, c, seeds) for c in cands[:a.max_candidates]]
            rows.sort(key=lambda r: -r["delta"])
            print(f"  slot {slot}  {incumbent}  vs {len(rows)} legal replacement(s)")
            for r in rows:
                flag = "  *" if r["p"] < 0.05 else ""
                print(f"      {r['in']:46s} delta {r['delta']:+.3f}  "
                      f"discordant {r['candidate_wins']:>3}/{r['discordant']:<3} "
                      f"p={r['p']:.3f}{flag}")
            out.append({"deck": name, "slot": slot, "incumbent": incumbent, "swaps": rows})
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps({"seeds": len(seeds), "agent": a.agent, "field": FIELD,
                                           "results": out}, indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/legend_swap.py", description=__doc__.splitlines()[0])
    ap.add_argument("--deck", default="the_heist")
    ap.add_argument("--all", action="store_true", help="every deck in the standard field")
    ap.add_argument("--seeds", type=int, default=80)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--agent", default="heuristic")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--max-candidates", type=int, default=8)
    ap.add_argument("--out", default="")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
