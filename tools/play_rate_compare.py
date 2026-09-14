"""Does a stronger agent play the cards the heuristic refuses?

    python tools/play_rate_compare.py --cards chrome-reverie cyberpsychosis --b ismcts:8 --seeds 40

The coverage sweep produced one number nobody expected and nobody can act on without this question
answered. Chrome Reverie was drawn 2,424 times and played 62 — a 2.6% play rate. Cyberpsychosis was
drawn 7,548 times and played 8%. Those are not coverage failures; the agent had the card in hand and
chose something else, every single time.

Two readings, and they point opposite ways:

* **the card is bad** — a 3-cost Program that removes one attacker for a turn is genuinely worse
  than spending three Eddies on a body, and the agent is right;
* **the agent is bad** — a one-ply greedy evaluator scores the board at the end of its own turn,
  and a card whose entire value is what the *rival* cannot do next turn is invisible to it by
  construction.

The second is not a hypothesis invented to be charitable: it is the same blind spot the delayed
suite exists to measure, and Chrome Reverie is the worked example the opponent-reading module was
written around.

So this pairs them. Same decks, same seeds, same opponents; only the agent differs. If the searching
agent's play rate for a card is materially higher, the low number was a fact about the evaluator. If
it is the same, the card really is a trap and the written strategy note for it should say so.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.enums import CardType  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.deck.decklist import Decklist  # noqa: E402
from cptcg.deck.validate import validate  # noqa: E402
from cptcg.sim.runner import run_match  # noqa: E402
from cptcg.sim.stats import binomial_p_two_sided  # noqa: E402

DECK_SIZE = 40

#: The cards the coverage sweep could not drive to target, plus the rest of the tail it found.
DEFAULT_CARDS = ["chrome-reverie", "unlikely-bond", "reboot-optics", "appetite-for-destruction",
                 "cyberpsychosis", "safety-override", "gunpoint-diplomacy", "take-control"]


def build_around(reg, cards: list[str], rng: Pcg32, name: str) -> Decklist | None:
    """A legal 40-card deck holding three copies of every card in ``cards`` that can share a deck.

    Colour RAM is what decides whether they can. Three Legends give at most 6 RAM to one colour and
    0 to a colour they do not cover, so a list spanning three colours at high RAM simply has no
    legal deck — the caller is told by getting ``None`` rather than by a silently dropped card.
    """
    want = [reg.get(c) for c in cards]
    legends = [d for d in reg.defs if d.type is CardType.LEGEND and d.verified and not d.needs_script]
    need = {}
    for d in want:
        if d.ram:
            need[d.color] = max(need.get(d.color, 0), -(-d.ram // 2))
    if sum(need.values()) > 3:
        return None
    chosen = []
    for colour, slots in sorted(need.items(), key=lambda kv: -kv[1]):
        pool = [l for l in legends if l.color is colour and l not in chosen]
        rng.shuffle(pool)
        chosen += pool[:slots]
    rest = [l for l in legends if l not in chosen and l.name not in {c.name for c in chosen}]
    rng.shuffle(rest)
    chosen += rest[:3 - len(chosen)]
    if len(chosen) != 3:
        return None
    limits = {}
    for l in chosen:
        limits[l.color] = limits.get(l.color, 0) + l.ram

    def legal(d):
        return d.ram <= limits.get(d.color, 0)

    if not all(legal(d) for d in want):
        return None
    filler = [d for d in reg.defs
              if d.type is not CardType.LEGEND and d.verified and not d.needs_script
              and legal(d) and d not in want]
    rng.shuffle(filler)
    counts = {d.id: 3 for d in want}
    total = 3 * len(want)
    for d in filler:
        if total >= DECK_SIZE:
            break
        take = min(2, DECK_SIZE - total)
        counts[d.id] = take
        total += take
    if total < DECK_SIZE:
        return None
    deck = Decklist.from_counts(name, [l.id for l in chosen], counts, context="play-rate probe")
    return deck if validate(deck, reg).ok else None


def rates(results, cards: set[str]) -> dict[str, tuple[int, int]]:
    """Per card, (games where some deck drew it, games where that deck then played it)."""
    out = {c: [0, 0] for c in cards}
    for r in results:
        for drawn, played in ((r.drawn_a, r.played_a), (r.drawn_b, r.played_b)):
            for c in cards & set(drawn):
                out[c][0] += 1
                out[c][1] += int(c in played)
    return {c: tuple(v) for c, v in out.items()}


def run(a) -> int:
    reg = load_default()
    cards = list(a.cards)
    rng = Pcg32(a.seed, seq=77)
    decks = []
    for k in range(a.decks):
        d = build_around(reg, cards, rng, f"probe{k}")
        if d is None:
            print("no legal deck holds all of those cards together — their colours need more than "
                  "three Legend slots. Split the list and run it twice.")
            return 1
        decks.append(d)
    want = set(cards)
    totals = {ag: {c: [0, 0] for c in cards} for ag in (a.a, a.b)}
    for ag in (a.a, a.b):
        t0 = time.perf_counter()
        games = 0
        for i in range(0, len(decks) - 1, 2):
            m = run_match(decks[i], decks[i + 1], ag, ag, a.seeds, seed=a.seed + 991 * i,
                          workers=a.workers)
            games += len(m.results)
            for c, (drawn, played) in rates(m.results, want).items():
                totals[ag][c][0] += drawn
                totals[ag][c][1] += played
        print(f"{ag:14s} {games:>5} games in {time.perf_counter() - t0:6.1f}s", flush=True)

    print(f"\n{'card':34s} {a.a:>18s} {a.b:>18s}   delta      p")
    rows = []
    for c in cards:
        da, pa = totals[a.a][c]
        db, pb = totals[a.b][c]
        ra = pa / da if da else None
        rb = pb / db if db else None
        # Two independent proportions; the two-sided binomial on the pooled play count is a coarse
        # but honest screen, and with a handful of cards it needs no multiplicity correction beyond
        # reading it as a screen rather than a result.
        p = binomial_p_two_sided(pa, pa + pb) if (pa + pb) else 1.0
        rows.append({"card": c, "a_drawn": da, "a_played": pa, "b_drawn": db, "b_played": pb,
                     "a_rate": ra, "b_rate": rb,
                     "delta": (rb - ra) if (ra is not None and rb is not None) else None, "p": p})
        def fmt(r, pl, dr):
            return f"{pl:>4}/{dr:<4} {100 * r:5.1f}%" if r is not None else "     n/a"
        d = rows[-1]["delta"]
        dtxt = "      " if d is None else f"{100 * d:+5.1f}pp"
        star = "  *" if p < 0.05 else ""
        print(f"{c:34s} {fmt(ra, pa, da):>18s} {fmt(rb, pb, db):>18s}   {dtxt}  {p:6.3f}{star}")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps({"a": a.a, "b": a.b, "seeds": a.seeds,
                                           "decks": [d.name for d in decks], "rows": rows},
                                          indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/play_rate_compare.py",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("--cards", nargs="+", default=DEFAULT_CARDS)
    ap.add_argument("--a", default="heuristic", help="the baseline agent")
    ap.add_argument("--b", default="ismcts:8", help="the agent to compare it against")
    ap.add_argument("--decks", type=int, default=4, help="probe decks (played as pairs)")
    ap.add_argument("--seeds", type=int, default=40, help="games per deck pair")
    ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--out", default="")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
