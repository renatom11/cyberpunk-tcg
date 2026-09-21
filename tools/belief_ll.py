"""Belief log-likelihood (Stage 0 instrument): how well the public-evidence belief predicts the
rival's hidden cards, against a uniform-pool baseline.

    python tools/belief_ll.py GAMES [--games 200] [--every 10] [--out J]

At every ``--every``-th decision of each game, for the mover ``me``, every rival instance ``me``
cannot identify (hand, deck, a card sold unseen; and the face-down Legend slots) is scored:
the belief's probability of its true identity is ``allow[card] / sum(allow)`` from
``learn.opponent.RivalPrior`` (copies the rival could still hold, over the possible pool from
the colour bounds), and for a Legend slot ``1 / |legend candidates|``. The baseline is uniform
over the whole non-Legend pool (124 cards) and over all 27 Legends. Reported as mean natural-log
likelihood per hidden card, with the gain over the baseline and a per-game bootstrap interval.
A truth the belief gives zero probability (it cannot happen if the bounds are sound) is counted
and floored at 1e-6.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.enums import CardType  # noqa: E402
from cptcg.learn.experience import read_games  # noqa: E402
from cptcg.learn.opponent import RivalPrior  # noqa: E402


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("games")
    ap.add_argument("--games", dest="n", type=int, default=200)
    ap.add_argument("--every", type=int, default=10)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    reg = load_default()
    n_nonleg = sum(1 for d in reg.defs if d.type is not CardType.LEGEND)
    n_leg = sum(1 for d in reg.defs if d.type is CardType.LEGEND)
    per_game = []
    zeros = 0
    cards = legs = 0
    for gi, rec in enumerate(read_games(a.games)):
        if gi >= a.n:
            break
        s = new_game(reg, rec.replay().decklists(), rec.seed, DEFAULT_CONFIG)
        ll_b = ll_u = 0.0
        k = 0
        for ply, idx in enumerate(rec.actions):
            legal_actions(s)
            if ply % a.every == 0 and s.pending is not None:
                me = s.pending.player
                pr = RivalPrior(s, me)
                tot = sum(pr.allow.values())
                for inst in pr.hidden:
                    c = s.i_card[inst]
                    p = pr.allow.get(c, 0) / tot if tot else 0.0
                    if p <= 0:
                        zeros += 1
                        p = 1e-6
                    ll_b += math.log(p)
                    ll_u += math.log(1.0 / n_nonleg)
                    k += 1
                    cards += 1
                for slot in pr.slots:
                    c = s.i_card[slot]
                    p = (1.0 / len(pr.legend_cands)) if c in pr.legend_cands else 0.0
                    if p <= 0:
                        zeros += 1
                        p = 1e-6
                    ll_b += math.log(p)
                    ll_u += math.log(1.0 / n_leg)
                    k += 1
                    legs += 1
            apply(s, idx)
        if k:
            per_game.append((ll_b / k, ll_u / k, k))
    if not per_game:
        raise SystemExit("no decisions scored")
    def mean(xs):
        return sum(xs) / len(xs)
    gains = [b - u for b, u, _ in per_game]
    rng = random.Random(1)
    boots = []
    for _ in range(1000):
        boots.append(mean([gains[rng.randrange(len(gains))] for _ in range(len(gains))]))
    boots.sort()
    out = {"games": len(per_game), "hidden_cards_scored": cards, "legend_slots_scored": legs,
           "belief_ll_per_card": mean([b for b, _, _ in per_game]),
           "uniform_ll_per_card": mean([u for _, u, _ in per_game]),
           "gain_nats_per_card": mean(gains), "gain_ci95": [boots[25], boots[974]],
           "zero_probability_truths": zeros}
    print(json.dumps(out, indent=1))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
