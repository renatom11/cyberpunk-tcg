"""Two knowledge stores, and whether they agree about anything.

    python tools/compare_knowledge.py out/knowledge.json out/playtest/knowledge.json

`Knowledge` is the deck builders' card prior: shrunk IWD per card, fed into the static score so the
next generation of builders starts smarter than the last. It is the cheapest feedback loop in the
project and it is only as good as the games behind it.

The store the builders have been reading holds **1,440 games and 76 cards**, and its effective
sample sizes are small enough to print: Peace Offering at n=10.8, Meredith Stout at n=13.1. Shrinkage
is supposed to handle that — ``iwd * n / (n + k)`` pulls a thin estimate toward zero — but shrinkage
controls the *magnitude* of a noisy number, not its sign, and the sign is what a builder reads when
it decides whether a card is worth a slot.

So this compares two stores card by card and reports three things: where they disagree most, how
often they disagree about the **direction**, and what sample size each opinion rests on. A large
sign-flip rate between a small store and a large one is not a curiosity — it means the smaller store
was feeding the builder noise dressed as a preference, for every card on the flipped side.

What it deliberately does not do is replace one store with the other. The newer store here was
measured on coverage-driven decks, which are built to reach the tail of the card pool rather than to
be good decks, and IWD differences out deck *shape* but not the field a deck faced. Whether the
bigger store makes better decks is a question for the builder, played head to head, not a question
this tool can answer.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.deck.knowledge import Knowledge  # noqa: E402


def run(a) -> int:
    reg = load_default()
    old = Knowledge.load(a.old, reg=reg)
    new = Knowledge.load(a.new, reg=reg)
    print(f"{a.old}: {old.games:,} games, {len(old.cards)} cards")
    print(f"{a.new}: {new.games:,} games, {len(new.cards)} cards")

    both = [c for c in old.cards if c in new.cards
            and old.value(c) is not None and new.value(c) is not None]
    if not both:
        print("\nno card has an opinion in both stores")
        return 0
    deltas = {c: new.value(c) - old.value(c) for c in both}
    flips = [c for c in both if (old.value(c) > 0) != (new.value(c) > 0)]

    print(f"\n{len(both)} cards carry an opinion in both.")
    print(f"  mean |delta|           {statistics.fmean(abs(v) for v in deltas.values()):.4f}")
    print(f"  disagree on direction  {len(flips)}/{len(both)} ({len(flips) / len(both):.0%})")
    print(f"  median n, old / new    {statistics.median(old.sample_size(c) for c in both):.1f}"
          f" / {statistics.median(new.sample_size(c) for c in both):.1f}")

    print(f"\nlargest disagreements (shrunk IWD, n is the effective sample):")
    for c in sorted(both, key=lambda c: -abs(deltas[c]))[:a.top]:
        print(f"  {c:44s} old {old.value(c):+.4f} (n={old.sample_size(c):7.1f})   "
              f"new {new.value(c):+.4f} (n={new.sample_size(c):8.1f})   "
              f"delta {deltas[c]:+.4f}{'  SIGN FLIP' if c in flips else ''}")

    only_new = sorted(set(new.cards) - set(old.cards))
    if only_new:
        print(f"\n{len(only_new)} cards the older store had never seen at all: "
              + ", ".join(only_new[:12]) + (" ..." if len(only_new) > 12 else ""))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/compare_knowledge.py",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--top", type=int, default=15)
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
