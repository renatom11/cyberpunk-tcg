"""Plan regret (Stage 0 instrument): what a per-decision search leaves on the table against a
whole-turn plan, in the value head's own units.

    python tools/plan_regret.py GAMES [--turns 500] [--seed 9] [--search ismcts:32] [--plan plan-deep:32]
                                      [--weights W.json] [--workers 4] [--out J]

Turn-start MAIN decisions are sampled uniformly from the corpus. From each, the search agent
plays the mover's decisions through the turn (the rival on the frozen policy) and the plan agent
returns its best line, replayed the same way; both end-of-turn boards are scored by the value
head (the shipped 114-feature head by default) for the mover, and the regret is
plan − search in win-probability points. Reported: mean and median regret, the share of turns
where the search's turn scored at least the plan's, and the per-turn cost of each agent.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core.actions import ChoiceKind  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.learn.delayed import _materialise, build_position, fixed_policy, spec_from_state  # noqa: E402
from cptcg.learn.experience import read_games  # noqa: E402


def sample_turn_starts(reg, path, n, seed):
    rng = Pcg32(seed, seq=29)
    games = list(read_games(path))
    out = []
    tries = 0
    while len(out) < n and tries < n * 30:
        tries += 1
        rec = games[rng.below(len(games))]
        s = new_game(reg, rec.replay().decklists(), rec.seed, DEFAULT_CONFIG)
        starts = []
        seen_turn = -1
        for k, idx in enumerate(rec.actions):
            legal_actions(s)
            ch = s.pending
            if ch is not None and ch.kind is ChoiceKind.MAIN and s.turn != seen_turn and s.turn >= 3:
                seen_turn = s.turn
                starts.append(k)
            apply(s, idx)
        if not starts:
            continue
        ply = starts[rng.below(len(starts))]
        s = new_game(reg, rec.replay().decklists(), rec.seed, DEFAULT_CONFIG)
        for k, idx in enumerate(rec.actions):
            legal_actions(s)
            if k == ply:
                break
            apply(s, idx)
        legal_actions(s)
        out.append(spec_from_state(s))
    return out


def _search_turn(s, me, agent_name, seed):
    policy = fixed_policy()
    c = s.clone()
    ag = make_agent(agent_name, seed)
    ag.new_game(seed, me)
    start = c.turn
    guard = 0
    while not c.over and c.pending is not None and c.turn == start and guard < 400:
        guard += 1
        ch = _materialise(c)
        apply(c, ag.act(c, ch) if ch.player == me else policy(c, ch))
    return c


def _replay_plan(s, me, line):
    """Play the plan's ``(ChoiceKind, Action)`` steps back; where a step is no longer legal the
    turn is finished by the frozen policy (scored where it breaks, as the plan agent scores)."""
    policy = fixed_policy()
    c = s.clone()
    start = c.turn
    steps = iter(line)
    guard = 0
    while not c.over and c.pending is not None and c.turn == start and guard < 400:
        guard += 1
        ch = _materialise(c)
        if ch.player != me:
            apply(c, policy(c, ch))
            continue
        nxt = next(steps, None)
        if nxt is None:
            apply(c, policy(c, ch))
            continue
        _, act = nxt
        if act in ch.options:
            apply(c, ch.options.index(act))
        else:
            apply(c, policy(c, ch))
    return c


def one(job):
    spec, search, plan, weights, seed = job
    reg = load_default()
    s = build_position(reg, spec, DEFAULT_CONFIG)
    legal_actions(s)
    me = s.pending.player
    head = make_agent("neural" + (f"@{weights}" if weights else ""), 1).model
    t0 = time.perf_counter()
    end_s = _search_turn(s, me, search, seed)
    t1 = time.perf_counter()
    pl = make_agent(plan, seed)
    pl.new_game(seed, me)
    line = pl.plan_for(s.clone())
    end_p = _replay_plan(s, me, line)
    t2 = time.perf_counter()

    def score(c):
        if c.over:
            return 1.0 if c.winner == me else (0.0 if c.winner is not None else 0.5)
        return head.value(c, me)
    return {"search": score(end_s), "plan": score(end_p), "t_search": t1 - t0, "t_plan": t2 - t1}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("games")
    ap.add_argument("--turns", type=int, default=500)
    ap.add_argument("--seed", type=int, default=9)
    ap.add_argument("--search", default="ismcts:32")
    ap.add_argument("--plan", default="plan-deep:32")
    ap.add_argument("--weights", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    reg = load_default()
    specs = sample_turn_starts(reg, a.games, a.turns, a.seed)
    jobs = [(sp, a.search, a.plan, a.weights, a.seed + i) for i, sp in enumerate(specs)]
    from multiprocessing import Pool
    with Pool(a.workers) as pool:
        rows = list(pool.imap_unordered(one, jobs, chunksize=2))
    reg_ = [r["plan"] - r["search"] for r in rows]
    out = {"games": a.games, "turns": len(rows), "search": a.search, "plan": a.plan,
           "head": a.weights or "shipped",
           "mean_regret": statistics.fmean(reg_), "median_regret": statistics.median(reg_),
           "search_at_least_plan": sum(1 for r in reg_ if r <= 1e-9) / len(reg_),
           "mean_search_score": statistics.fmean(r["search"] for r in rows),
           "mean_plan_score": statistics.fmean(r["plan"] for r in rows),
           "seconds_per_turn": {"search": statistics.fmean(r["t_search"] for r in rows),
                                "plan": statistics.fmean(r["t_plan"] for r in rows)}}
    print(json.dumps(out, indent=1))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
