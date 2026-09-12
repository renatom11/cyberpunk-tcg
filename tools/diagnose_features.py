"""Can the model's input tell a winning move from a losing one?

Three attempts to make the AI stronger all failed the same way — more data, more features, a better
optimiser — and the reading was that gen-1 sits at the ceiling of what 114 aggregate features can
express. That is an inference. This turns it into a measurement, and it costs no games.

``data/arena/delayed.json`` holds 8 hand-built positions with an **exhaustively verified winning
line**. Four the current agent solves 16/16; four it never solves. That split is the control: if the
ceiling story is right, the winning move should stand out in feature space on the solved positions
and vanish into the losers on the unsolved ones. If both groups look alike, the diagnostic is
measuring nothing and the story needs revisiting — which is why the test asserts the two groups
*differ* rather than asserting a direction.

Every option is **settled** before it is measured, exactly as ``ismcts._root_actions`` does, so a
compound action is judged on where it lands rather than on its first step.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.agents.base import make_agent                            # noqa: E402
from cptcg.agents.heuristic import _equiv_key                       # noqa: E402
from cptcg.cards.registry import load_default                       # noqa: E402
from cptcg.core.engine import apply, legal_actions                  # noqa: E402
from cptcg.learn.delayed import build_entry                          # noqa: E402
from cptcg.learn.features import FEATURE_NAMES, features            # noqa: E402
from cptcg.learn.model import load_weights                          # noqa: E402

SUITE = ROOT / "data" / "arena" / "delayed.json"


def option_states(reg, entry: dict, me: int, settler):
    """Every legal option at the position, settled, as (index, feature vector).

    ``build_entry`` handles both kinds the suite holds — a hand-built board spec and a mined replay
    prefix — so the diagnostic covers all eight rather than the three that carry a spec.
    """
    base = build_entry(reg, entry)
    legal_actions(base)
    # Dedup exactly as ismcts._root_actions does. Without this the diagnostic reports "the winning
    # move is feature-identical to another option" for two copies of the same card — which is true,
    # correct, and not a representational failure at all. Three of four apparent collapses in the
    # first run were that artefact.
    seen, keep = set(), []
    for i, a in enumerate(base.pending.options):
        k = _equiv_key(base, a)
        if k in seen:
            continue
        seen.add(k)
        keep.append(i)
    out = []
    for i in keep:
        c = build_entry(reg, entry)
        legal_actions(c)
        apply(c, i)
        settler(c, 1)
        out.append((i, features(c, me)))
    return out


def separation(win_vec, lose_vecs) -> tuple[float, float]:
    """How far the winning move's state sits from the losers, against the losers' own spread.

    Returned as (distance to the nearest loser, mean pairwise distance among losers). The ratio of
    the two is the number that matters: below 1 means the winning move is closer to a loser than
    losers typically are to each other — it is *inside* the cloud, and no evaluator reading these
    numbers can pick it out.
    """
    def d(a, b):
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    if not lose_vecs:
        return 0.0, 0.0
    nearest = min(d(win_vec, v) for v in lose_vecs)
    pairs = [d(a, b) for i, a in enumerate(lose_vecs) for b in lose_vecs[i + 1:]]
    return nearest, (statistics.mean(pairs) if pairs else 0.0)


def run(agent_name: str, weights: str | None) -> list[dict]:
    reg = load_default()
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    agent = make_agent(agent_name if not weights else f"{agent_name}@{weights}", 1)
    model = load_weights(weights) if weights else load_weights()
    rows = []
    for pos in suite["positions"]:
        v = pos.get("verified") or {}
        line = v.get("line") or []
        if not line:
            continue
        me = pos.get("player", 0)
        agent.me = me
        opts = option_states(reg, pos, me, agent._resolve)
        win_i = line[0]
        by_i = dict(opts)
        if win_i not in by_i:
            # The verified move was deduped away as a copy of another; its equivalent is in there.
            base = build_entry(reg, pos)
            legal_actions(base)
            wk = _equiv_key(base, base.pending.options[win_i])
            win_i = next(i for i, _ in opts
                         if _equiv_key(base, base.pending.options[i]) == wk)
        win_vec = by_i.get(win_i) or dict(opts)[win_i]
        lose = [vec for i, vec in opts if i != win_i]
        near, spread = separation(win_vec, lose)
        scores = {i: model.raw(vec) for i, vec in opts}
        order = sorted(scores, key=lambda i: -scores[i])
        rows.append({
            "id": pos["id"], "options": len(opts), "win_index": win_i,
            "value_rank": order.index(win_i) + 1,
            "nearest": near, "spread": spread,
            "ratio": (near / spread) if spread else float("inf"),
            "value_gap": scores[win_i] - max(s for i, s in scores.items() if i != win_i),
        })
    return rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--agent", default="ismcts")
    p.add_argument("--weights", default="out/learn/gen-001/weights.json")
    p.add_argument("--solved", default="gear-before-the-raid,sell-to-afford-the-raid,"
                                       "mined-23767-79,mined-166302-115",
                   help="positions the agent solves 16/16 — the control group")
    a = p.parse_args(argv)
    rows = run(a.agent, a.weights)
    solved = set(a.solved.split(","))

    print(f"{len(rows)} verified positions, {len(FEATURE_NAMES)} features, "
          f"weights {a.weights}\n")
    print(f"{'position':<26} {'solved':>7} {'opts':>5} {'rank':>5} {'nearest':>9} "
          f"{'spread':>8} {'ratio':>7} {'value gap':>10}")
    for r in sorted(rows, key=lambda r: r["id"] not in solved):
        print(f"{r['id']:<26} {'yes' if r['id'] in solved else 'NO':>7} {r['options']:>5} "
              f"{r['value_rank']:>5} {r['nearest']:>9.4f} {r['spread']:>8.4f} "
              f"{r['ratio']:>7.2f} {r['value_gap']:>+10.4f}")

    for label, keep in (("SOLVED", True), ("UNSOLVED", False)):
        g = [r for r in rows if (r["id"] in solved) == keep]
        if not g:
            continue
        print(f"\n{label}: {len(g)} positions | median ratio "
              f"{statistics.median(r['ratio'] for r in g):.2f} | "
              f"median rank {statistics.median(r['value_rank'] for r in g):.1f} of "
              f"{statistics.median(r['options'] for r in g):.0f} | "
              f"median value gap {statistics.median(r['value_gap'] for r in g):+.4f}")
    print("\nratio < 1: the winning move sits closer to a losing move than the losing moves sit to\n"
          "each other — inside the cloud, and invisible to anything reading these features.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
