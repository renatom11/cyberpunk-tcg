"""Does the model actually use what it now knows about the rival?

    python tools/opponent_influence.py --games 200 --weights out/learn/v3/weights.json

A panel score that moves proves something changed. It does not prove the *new features* changed it,
and this project has already been fooled once by a number that looked like evidence: the gear-aware
vector improved held-out Brier, accuracy **and** calibration, and played 4.4 points worse. So before
a panel row is believed, this asks a question the score cannot answer.

The measurement is an ablation at inference time. For each sampled position, score it twice: once as
it is, and once with the fifteen rival-facing features replaced by their **"nothing known"** values —
the vector the model sees on turn one, before the rival has played anything. The difference is, in
logits, exactly what knowing the rival's colours is worth to this model at this position.

Three outcomes, and each says something different:

* **Near zero everywhere** — the model ignored the features. Whatever the panel did, it was not this,
  and the honest report is a seventh flat result rather than a win.
* **Large and signed the same way everywhere** — the model learned a constant, not a contingency. It
  is reading "the rival has played some cards" as a proxy for "the game is late", which the turn
  counter already told it.
* **Large and varying with the board** — the model is doing the thing the features were added for.
  The tail is the interesting part: the positions where it moves most should be the ones where a
  live threat actually matters.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.engine import apply, legal_actions  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.learn.decks import sample_pair  # noqa: E402
from cptcg.learn.features import FEATURE_NAMES, _derive, features  # noqa: E402
from cptcg.learn.model import load_weights  # noqa: E402
from cptcg.sim.runner import new_game  # noqa: E402

#: The block appended in learn/features.py. Located by name so a reordering cannot silently shift it.
FIRST = FEATURE_NAMES.index("rival_legend_red")
LAST = FEATURE_NAMES.index("lone_attacker_exposed")


def blind(vec: tuple) -> tuple:
    """``vec`` with the rival-facing block reset to what turn one looks like: nothing proven."""
    known, _ = _derive((0, 0, 0, 0))
    out = list(vec)
    out[FIRST:FIRST + len(known)] = known
    out[LAST] = 0.0                       # no board is exposed to a threat you have not seen
    return tuple(out)


def sample(reg, games: int, seed: int, agent_name: str):
    """Positions from real games, at every decision, both seats."""
    for g in range(games):
        decks = sample_pair(reg, Pcg32(seed ^ (g * 0x9E3779B1), seq=909))
        s = new_game(reg, decks, (seed * 1000003 + g) & 0x7FFFFFFF)
        ags = [make_agent(agent_name, seed + i) for i in (0, 1)]
        for a, i in zip(ags, (0, 1)):
            a.new_game(seed + i, i)
        n = 0
        while not s.over and n < 2000:
            legal_actions(s)
            ch = s.pending
            if ch is None:
                break
            yield s, ch.player
            apply(s, ags[ch.player].act(s, ch))
            n += 1


def run(a) -> int:
    reg = load_default()
    model = load_weights(Path(a.weights))
    deltas, by_turn = [], {}
    n = 0
    for s, me in sample(reg, a.games, a.seed, a.agent):
        v = features(s, me)
        d = model.raw(v) - model.raw(blind(v))
        deltas.append(d)
        by_turn.setdefault(min(s.turn, 20), []).append(d)
        n += 1
        if a.limit and n >= a.limit:
            break

    mags = [abs(d) for d in deltas]
    mags.sort()
    print(f"{n:,} positions from {a.games} games, weights {a.weights}\n")
    print("How much the model's opinion moves when it can read the rival, in logits:")
    print(f"  mean signed   {statistics.fmean(deltas):+.4f}   "
          f"(a large constant here would mean it learned a bias, not a contingency)")
    print(f"  mean |delta|  {statistics.fmean(mags):.4f}")
    print(f"  median |delta|{statistics.median(mags):.4f}")
    for q in (0.5, 0.9, 0.99):
        print(f"  p{int(q * 100):<3d} |delta|  {mags[min(len(mags) - 1, int(q * len(mags)))]:.4f}")
    print(f"  max |delta|   {mags[-1]:.4f}")
    zero = sum(1 for m in mags if m < 0.01) / max(1, len(mags))
    print(f"  share under 0.01 logits: {zero:.1%}")

    print("\nBy turn (mean |delta|) — it should grow as the rival reveals more:")
    for t in sorted(by_turn):
        row = [abs(x) for x in by_turn[t]]
        if len(row) < 50:
            continue
        print(f"  turn {t:>2}  n={len(row):>7,}  {statistics.fmean(row):.4f}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tools/opponent_influence.py",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--agent", default="heuristic")
    ap.add_argument("--weights", default="out/learn/v3/weights.json")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many positions")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
