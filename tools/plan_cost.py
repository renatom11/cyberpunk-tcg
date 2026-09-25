"""What the plan-candidate stage costs (Stage 1 plan §0.7): measured before it is switched on.

    python tools/plan_cost.py [--agent ismcts-plan:32@W] [--turns 200] [--seed 20260925] [--out J]

Plays the plan-stage agent against the frozen heuristic on sampled pairs until it has planned
``--turns`` turns, timing every ``act`` of the searching seat and, inside it, the whole-turn walk.
The registered rule: if the walk exceeds 15% of the searching seat's time the stage stays off and
the number is reported.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.learn.decks import sample_pair  # noqa: E402

THRESHOLD = 0.15


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", default="ismcts-plan:32")
    ap.add_argument("--turns", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    reg = load_default()
    rng = Pcg32(a.seed, seq=5)
    act_s = plan_s = 0.0
    planned = games = 0
    while planned < a.turns:
        decks = sample_pair(reg, rng)
        gs = a.seed + games
        ag = make_agent(a.agent, gs * 2)
        opp = make_agent("heuristic", gs * 2 + 1)
        ag.new_game(gs, 0)
        opp.new_game(gs, 1)
        inner = ag._plan_first_actions
        box = {"t": 0.0, "n": 0}

        def timed(s, ch, inner=inner, box=box):
            t0 = time.perf_counter()
            try:
                return inner(s, ch)
            finally:
                box["t"] += time.perf_counter() - t0
                box["n"] += 1

        ag._plan_first_actions = timed
        s = new_game(reg, decks, gs, DEFAULT_CONFIG)
        while not s.over:
            legal_actions(s)
            ch = s.pending
            if ch.player == 0:
                t0 = time.perf_counter()
                i = ag.act(s, ch)
                act_s += time.perf_counter() - t0
            else:
                i = opp.act(s, ch)
            apply(s, i)
        plan_s += box["t"]
        planned += box["n"]
        games += 1
        print(f"  game {games}: {planned} planned turns, walk share {plan_s / max(act_s, 1e-9):.1%}", flush=True)
    share = plan_s / act_s if act_s else 0.0
    out = {"agent": a.agent, "games": games, "planned_turns": planned, "act_seconds": act_s,
           "walk_seconds": plan_s, "share": share, "threshold": THRESHOLD, "switch_on": share <= THRESHOLD,
           "seconds_per_planned_turn": plan_s / max(planned, 1)}
    print(json.dumps(out, indent=1))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
