"""Dice regret (capability C5): how much value the chooser left on the table at every die decision.

    python tools/dice_regret.py GAMES.jsonl.gz [--weights W.json] [--rolls 16] [--max-games N] [--out J]

At every ``GIG_DIE`` decision ("take which die from the fixer area") and every steal ``Pick``
("steal which Gig(s)") in the corpus, each option is previewed with the shipped 114-feature value
head from the chooser's seat: the option is applied on a clone, the position is settled the way
the greedy agent settles a preview (rival answers by default policy, own follow-ups greedily),
and the head's win probability is read. A die's roll is a random outcome, so a ``GIG_DIE`` option
is averaged over ``--rolls`` seeded rolls (the expectation over faces); a steal is deterministic.
Regret is the best option's expectation minus the chosen option's, in win-probability points.

Reported: decisions, mean and median regret, the share of decisions where the chosen option was
the head's best, per kind — and by the heuristic's own dice rule ("take the biggest die") how
often the biggest die was also the head's best. The shipped head is the yardstick, not the
truth; this is the day-0 number the design asks for, and it moves when the head does.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.actions import ChoiceKind, TakeGigDie  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.learn.experience import read_games  # noqa: E402


def _settle_value(agent, s, i: int, me: int, seed: int) -> float:
    c = s.clone()
    c.rng = Pcg32(seed, seq=3)
    apply(c, i)
    agent._resolve(c, 1)
    if c.over:
        return 1.0 if c.winner == me else (0.0 if c.winner in (0, 1) else 0.5)
    return agent.model.value(c, me)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("games")
    ap.add_argument("--weights", default=None, help="value head (default: the shipped weights)")
    ap.add_argument("--rolls", type=int, default=16)
    ap.add_argument("--max-games", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    reg = load_default()
    agent = make_agent("neural" + (f"@{a.weights}" if a.weights else ""), 1)
    per_kind: dict = {"GIG_DIE": [], "steal": []}
    best_hits = {"GIG_DIE": 0, "steal": 0}
    biggest_best = biggest_n = 0
    n_games = 0
    for rec in read_games(a.games):
        if a.max_games and n_games >= a.max_games:
            break
        n_games += 1
        s = new_game(reg, rec.replay().decklists(), rec.seed, DEFAULT_CONFIG)
        for k, idx in enumerate(rec.actions):
            legal_actions(s)
            ch = s.pending
            kind = None
            if ch.kind is ChoiceKind.GIG_DIE and len(ch.options) > 1:
                kind = "GIG_DIE"
            elif ch.kind is ChoiceKind.PICK and (ch.tag or "").endswith("@steal") and len(ch.options) > 1:
                kind = "steal"
            if kind:
                me = ch.player
                agent.new_game(rec.seed, me)
                vals = []
                for i in range(len(ch.options)):
                    if kind == "GIG_DIE":
                        vs = [_settle_value(agent, s, i, me, 1000 * k + r) for r in range(a.rolls)]
                        vals.append(sum(vs) / len(vs))
                    else:
                        vals.append(_settle_value(agent, s, i, me, 1000 * k))
                best = max(vals)
                per_kind[kind].append(best - vals[idx])
                if vals[idx] >= best - 1e-9:
                    best_hits[kind] += 1
                if kind == "GIG_DIE":
                    biggest = max(range(len(ch.options)), key=lambda j: ch.options[j].sides)
                    biggest_n += 1
                    if vals[biggest] >= best - 1e-9:
                        biggest_best += 1
            apply(s, idx)
    out = {"games": n_games, "rolls": a.rolls, "weights": a.weights or "shipped"}
    for kind, regs in per_kind.items():
        if regs:
            out[kind] = {"decisions": len(regs), "mean_regret": statistics.fmean(regs),
                         "median_regret": statistics.median(regs),
                         "chosen_was_best": best_hits[kind] / len(regs)}
    if biggest_n:
        out["biggest_die_was_best"] = biggest_best / biggest_n
    print(json.dumps(out, indent=1))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
