"""Stage 0 timing table: per-decision and per-game wall time for every agent, n games each.

    python tools/timing.py --games 20 --agents heuristic,neural,ismcts:32,ismcts:200,plan:32,plan-deep:32
    python tools/timing.py --micro                  # clone / determinize / apply / features+forward
    python tools/timing.py --parallel 200 --workers 4   # harvest throughput, 1 worker vs N

Each agent plays ``--games`` games as seat 0 against the frozen heuristic on the design's sampled
pairings (deck seed 20260910, the panel's provenance), single process, and every decision of the
timed agent is stopwatched by ChoiceKind. Reported per row: median, interquartile range, min and
max of the per-game time, the median per-decision time by kind, and decisions per game. The
design document's table was n = 1; this is the re-measurement the task asked for (Step 2).

Numpy is not used here so the numbers are the engine's own; the parallel run reports how many
games per second ``tools/harvest.py play`` reaches with ``--workers`` against one worker, which
is the efficiency the Stage 1 projection needs.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
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
from cptcg.learn.arena import sampled_pairings  # noqa: E402

DECK_SEED = 20260910


def _q(xs: list[float]) -> dict:
    xs = sorted(xs)
    if not xs:
        return {}
    qs = statistics.quantiles(xs, n=4) if len(xs) >= 4 else [xs[0], statistics.median(xs), xs[-1]]
    return {"n": len(xs), "median": statistics.median(xs), "q1": qs[0], "q3": qs[-1],
            "min": xs[0], "max": xs[-1], "mean": statistics.fmean(xs)}


def time_agent(reg, name: str, games: int, seed: int, opponent: str = "heuristic") -> dict:
    pairings = sampled_pairings(reg, games, deck_seed=DECK_SEED)
    per_game, per_dec = [], {}
    decisions = 0
    for g, pr in enumerate(pairings):
        decks = (pr.deck_a, pr.deck_b) if g % 2 == 0 else (pr.deck_b, pr.deck_a)
        agents = [make_agent(name, seed * 2 + g), make_agent(opponent, seed * 2 + g + 1)]
        s = new_game(reg, decks, seed + g, DEFAULT_CONFIG)
        for p, a in enumerate(agents):
            a.new_game(seed + g, p)
        t0 = time.perf_counter()
        while not s.over:
            legal_actions(s)
            ch = s.pending
            if ch.player == 0:
                t1 = time.perf_counter()
                i = agents[0].act(s, ch)
                dt = time.perf_counter() - t1
                per_dec.setdefault(ch.kind.name, []).append(dt)
                decisions += 1
            else:
                i = agents[1].act(s, ch)
            apply(s, i)
        per_game.append(time.perf_counter() - t0)
    return {"agent": name, "games": games, "game_s": _q(per_game),
            "decisions_per_game": decisions / games,
            "decision_ms": {k: {kk: vv * 1000 for kk, vv in _q(v).items()} for k, v in per_dec.items()}}


def micro(reg, n: int = 10_000) -> dict:
    from cptcg.core.rng import Pcg32
    from cptcg.core.view import determinize
    from cptcg.learn.features import features
    from cptcg.learn.model import load_weights
    pr = sampled_pairings(reg, 1, deck_seed=DECK_SEED)[0]
    s = new_game(reg, (pr.deck_a, pr.deck_b), 5, DEFAULT_CONFIG)
    h = make_agent("heuristic", 1)
    h.new_game(5, 0)
    for _ in range(40):                      # a mid-game position
        legal_actions(s)
        apply(s, h.act(s, s.pending))
    legal_actions(s)
    model = load_weights()
    out = {}
    t0 = time.perf_counter()
    for _ in range(n):
        s.clone()
    out["clone_us"] = (time.perf_counter() - t0) / n * 1e6
    rng = Pcg32(9)
    t0 = time.perf_counter()
    for _ in range(n):
        determinize(s, 0, rng)
    out["determinize_us"] = (time.perf_counter() - t0) / n * 1e6
    t0 = time.perf_counter()
    for _ in range(n):
        c = s.clone()
        apply(c, 0)
    out["clone_apply_us"] = (time.perf_counter() - t0) / n * 1e6
    t0 = time.perf_counter()
    for _ in range(n):
        model.raw(features(s, 0))
    out["features_forward_us"] = (time.perf_counter() - t0) / n * 1e6
    t0 = time.perf_counter()
    for _ in range(n):
        features(s, 0)
    out["features_us"] = (time.perf_counter() - t0) / n * 1e6
    return out


def parallel(games: int, workers: int, agent: str, tmp: Path) -> dict:
    res = {}
    for w in (1, workers):
        out = tmp / f"timing-w{w}"
        for ext in (".jsonl.gz", ".jsonl.gz.harvest.json"):
            p = Path(str(out) + ext)
            if p.exists():
                p.unlink()
        t0 = time.perf_counter()
        subprocess.run([sys.executable, str(ROOT / "tools" / "harvest.py"), "play", "--games", str(games),
                        "--agent", agent, "--seed", "424242", "--workers", str(w), "--out", str(out), "--fresh"],
                       check=True, capture_output=True)
        dt = time.perf_counter() - t0
        res[f"workers_{w}"] = {"seconds": dt, "games_per_s": games / dt}
    res["efficiency"] = res[f"workers_{workers}"]["games_per_s"] / (res["workers_1"]["games_per_s"] * workers)
    return res


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--agents", default="heuristic,neural,ismcts:32,ismcts:200,plan:32,plan-deep:32")
    ap.add_argument("--seed", type=int, default=20260921)
    ap.add_argument("--micro", action="store_true")
    ap.add_argument("--parallel", type=int, default=0, help="harvest this many games with 1 and --workers workers")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--parallel-agent", default="ismcts:32")
    ap.add_argument("--out", default="out/s0/timing.json")
    a = ap.parse_args(argv)
    reg = load_default()
    result: dict = {"seed": a.seed, "rows": []}
    if a.micro:
        result["micro"] = micro(reg)
        print(json.dumps(result["micro"], indent=1))
    for name in [x for x in a.agents.split(",") if x]:
        row = time_agent(reg, name, a.games, a.seed)
        result["rows"].append(row)
        g = row["game_s"]
        main_ms = row["decision_ms"].get("MAIN", {})
        print(f"{name:14s} game median {g['median']:6.2f}s  IQR {g['q1']:.2f}-{g['q3']:.2f}  "
              f"min {g['min']:.2f} max {g['max']:.2f}  MAIN median {main_ms.get('median', 0):.1f} ms  "
              f"decisions/game {row['decisions_per_game']:.0f}")
    if a.parallel:
        tmp = ROOT / "out" / "s0"
        tmp.mkdir(parents=True, exist_ok=True)
        result["parallel"] = parallel(a.parallel, a.workers, a.parallel_agent, tmp)
        print(json.dumps(result["parallel"], indent=1))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
