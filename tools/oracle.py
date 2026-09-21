"""The oracle set (Stage 0, Step 4): reference positions with expensive labels.

    python tools/oracle.py sample  CORPUS... --n 2000 --seed 20260924 --out data/arena/oracle.json
    python tools/oracle.py label   data/arena/oracle.json [--workers 4] [--budget 2000] [--resume]
    python tools/oracle.py agree   data/arena/oracle.json [--weights W.json | --cards W.npz [--ablate]]
                                  [--agent NAME] [--out J]

``sample`` draws ``--n`` decisions uniformly over all decisions of the given corpora (every
decision of every game is a ticket; a MAIN decision of the mover with more than one option is
kept, others are skipped and redrawn), rebuilds each and stores it as a board spec
(``learn.delayed.spec_from_state``) with the ruleset and cards digests, so the set survives a
change of action index and is refused, visibly, by a change of rules.

``label`` gives each position two labels from the position's mover's seat: ``cheat_value``, the
root win probability of ``cheat:ismcts:BUDGET`` (the true state searched, so hidden
information is not a source of noise), and ``plan_score`` / ``plan_line``, the replay score of
``plan-deep:32``'s best line (``PlanAgent.best_line_score``). Labels are written back into the
file per position, so ``--resume`` continues an interrupted run.

``agree`` scores a value head against the oracle: Spearman rank correlation and Brier score of
the head's win probability against ``cheat_value``, and, for the plan label, Spearman against
``plan_score``. The 114-feature head (``--weights``), the card-aware numpy model (``--cards``,
``--ablate``) or any registered agent exposing ``model.value`` (``--agent``) can be scored.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.cards.registry import cards_digest, load_default  # noqa: E402
from cptcg.core.actions import ChoiceKind  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.learn.delayed import build_position, spec_from_state  # noqa: E402
from cptcg.learn.experience import read_games  # noqa: E402

FORMAT = 1


# ----------------------------------------------------------------------------- sample
def _index_corpus(paths: list[str]) -> list[tuple[int, int, int]]:
    """(file index, game index, decisions) per game — the ticket counts."""
    out = []
    for fi, p in enumerate(paths):
        for gi, rec in enumerate(read_games(p)):
            out.append((fi, gi, rec.n_decisions))
    return out


def cmd_sample(a) -> None:
    reg = load_default()
    games = _index_corpus(a.corpus)
    total = sum(g[2] for g in games)
    rng = Pcg32(a.seed, seq=17)
    wanted: dict[tuple[int, int], list[int]] = {}
    # draw ticket numbers, map to (game, ply), with 3x oversampling for the skipped kinds
    draws = a.n * 8                       # MAIN decisions with a choice are about a third of all plies
    cum = []
    c = 0
    for fi, gi, n in games:
        cum.append(c)
        c += n
    import bisect
    for _ in range(draws):
        t = rng.below(total)
        k = bisect.bisect_right(cum, t) - 1
        fi, gi, n = games[k]
        wanted.setdefault((fi, gi), []).append(t - cum[k])
    positions = []
    by_file: dict[int, dict[int, list[int]]] = {}
    for (fi, gi), plies in wanted.items():
        by_file.setdefault(fi, {})[gi] = sorted(set(plies))
    for fi, want in sorted(by_file.items()):
        for gi, rec in enumerate(read_games(a.corpus[fi])):
            plies = want.get(gi)
            if not plies:
                continue
            s = new_game(reg, rec.replay().decklists(), rec.seed, DEFAULT_CONFIG)
            pset = set(plies)
            for ply, idx in enumerate(rec.actions):
                legal_actions(s)
                ch = s.pending
                if ply in pset and ch.kind is ChoiceKind.MAIN and len(ch.options) > 1:
                    positions.append({"id": f"oracle-{fi}-{gi}-{ply}", "kind": "board",
                                      "source": f"{Path(a.corpus[fi]).name} game {gi} ply {ply}",
                                      "mover": ch.player, "spec": spec_from_state(s)})
                apply(s, idx)
    # the draw order is by file/game; shuffle by the same generator and cut to n
    order = list(range(len(positions)))
    rng.shuffle(order)
    positions = [positions[i] for i in order[:a.n]]
    out = {"format": FORMAT, "rules": DEFAULT_CONFIG.digest(), "cards": cards_digest(), "seed": a.seed,
           "corpora": [str(p) for p in a.corpus], "drawn_from_decisions": total, "positions": positions}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"{len(positions)} positions from {total} decisions in {len(games)} games -> {a.out}")


# ----------------------------------------------------------------------------- label
def _label_one(job: tuple) -> tuple[str, dict]:
    pid, spec, mover, budget, plan_spec, seed = job
    reg = load_default()
    s = build_position(reg, spec, DEFAULT_CONFIG)
    legal_actions(s)
    t0 = time.perf_counter()
    cheat = make_agent(f"cheat:ismcts:{budget}", seed)
    cheat.new_game(seed, mover)
    cheat.act(s.clone(), s.pending)
    cv = cheat.last_value
    t1 = time.perf_counter()
    plan = make_agent(plan_spec, seed)
    plan.new_game(seed, mover)
    score, line = plan.best_line_score(s.clone())
    t2 = time.perf_counter()
    return pid, {"cheat_value": cv, "plan_score": score,
                 "plan_line": [[int(k), repr(act)] for k, act in line],
                 "cheat_visits": {repr(k): v for k, v in cheat.last_visits.items()},
                 "seconds": [round(t1 - t0, 2), round(t2 - t1, 2)]}


def _playout_one(job: tuple) -> tuple[str, dict]:
    """The independent label: the mean outcome for the mover over ``n`` playouts of the true
    state by the frozen heuristic on both seats, each with its own seed (tie-break noise and
    the Gig die differ per seed). No learned head anywhere. Also the split-half agreement:
    the mean of the odd seeds against the mean of the even seeds, so the noise of the label
    is measured rather than assumed."""
    pid, spec, mover, n, seed = job
    reg = load_default()
    from cptcg.learn.experience import outcome  # noqa: F401
    wins = []
    for k in range(n):
        s = build_position(reg, spec, DEFAULT_CONFIG)
        legal_actions(s)
        sd = seed * 1000 + k
        s.rng = Pcg32(sd, seq=3)
        ags = [make_agent("heuristic", sd * 2 + i) for i in (0, 1)]
        for p, ag in enumerate(ags):
            ag.new_game(sd, p)
        guard = 0
        while not s.over and guard < 4000:
            guard += 1
            legal_actions(s)
            ch = s.pending
            if ch is None:
                break
            apply(s, ags[ch.player].act(s, ch))
        wins.append(1.0 if s.winner == mover else (0.0 if s.winner is not None else 0.5))
    odd = [w for i, w in enumerate(wins) if i % 2]
    even = [w for i, w in enumerate(wins) if not i % 2]
    return pid, {"playout_value": sum(wins) / len(wins), "playouts": n,
                 "half_a": sum(even) / len(even), "half_b": sum(odd) / len(odd)}


def cmd_playouts(a) -> None:
    path = Path(a.oracle)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["rules"] != DEFAULT_CONFIG.digest():
        raise SystemExit(f"oracle set is for ruleset {data['rules']}, this build is {DEFAULT_CONFIG.digest()}")
    todo = [p for p in data["positions"] if not (a.resume and p.get("playout"))]
    jobs = [(p["id"], p["spec"], p["mover"], a.n, a.seed + i) for i, p in enumerate(todo)]
    by_id = {p["id"]: p for p in data["positions"]}
    print(f"playout-labelling {len(todo)} positions, {a.n} heuristic playouts each", file=sys.stderr)
    t0 = time.time()
    done = 0

    def flush():
        data["playout_labels"] = {"agent": "heuristic vs heuristic from the true state", "playouts": a.n,
                                  "seed": a.seed, "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        path.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")

    from multiprocessing import Pool
    with Pool(a.workers) as pool:
        for pid, lab in pool.imap_unordered(_playout_one, jobs, chunksize=2):
            by_id[pid]["playout"] = lab
            done += 1
            if done % 50 == 0 or done == len(jobs):
                flush()
                print(f"  {done}/{len(jobs)}, {(time.time() - t0) / done:.1f} s each", file=sys.stderr)
    flush()
    # the label's own noise: split-half agreement and the binomial standard error
    halves = [(p["playout"]["half_a"], p["playout"]["half_b"]) for p in data["positions"] if p.get("playout")]
    xs = [h[0] for h in halves]; ys = [h[1] for h in halves]
    rho = _spearman(xs, ys)
    import statistics
    pv = [p["playout"]["playout_value"] for p in data["positions"] if p.get("playout")]
    se = statistics.fmean(math.sqrt(max(v * (1 - v), 1e-9) / a.n) for v in pv)
    print(json.dumps({"positions": len(pv), "playouts": a.n, "split_half_spearman": rho,
                      "mean_binomial_se": se, "mean_value": statistics.fmean(pv),
                      "seconds": round(time.time() - t0)}, indent=1))


def cmd_label(a) -> None:
    path = Path(a.oracle)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["rules"] != DEFAULT_CONFIG.digest():
        raise SystemExit(f"oracle set is for ruleset {data['rules']}, this build is {DEFAULT_CONFIG.digest()}")
    todo = [p for p in data["positions"] if not (a.resume and p.get("labels"))]
    print(f"labelling {len(todo)} of {len(data['positions'])} positions with cheat:ismcts:{a.budget} and {a.plan}",
          file=sys.stderr)
    jobs = [(p["id"], p["spec"], p["mover"], a.budget, a.plan, a.seed) for p in todo]
    by_id = {p["id"]: p for p in data["positions"]}
    done = 0
    t0 = time.time()

    def flush():
        data["labels"] = {"cheat": f"cheat:ismcts:{a.budget}", "plan": a.plan, "seed": a.seed,
                          "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")

    if a.workers > 1:
        from multiprocessing import Pool
        with Pool(a.workers) as pool:
            for pid, lab in pool.imap_unordered(_label_one, jobs, chunksize=1):
                by_id[pid]["labels"] = lab
                done += 1
                if done % 25 == 0 or done == len(jobs):
                    flush()
                    print(f"  {done}/{len(jobs)} labelled, {(time.time() - t0) / done:.1f} s each", file=sys.stderr)
    else:
        for job in jobs:
            pid, lab = _label_one(job)
            by_id[pid]["labels"] = lab
            done += 1
            if done % 25 == 0 or done == len(jobs):
                flush()
    flush()
    print(f"done: {done} labelled in {time.time() - t0:.0f} s")


# ----------------------------------------------------------------------------- agree
def _spearman(x: list[float], y: list[float]) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = ranks(x), ranks(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    sxx = sum((rx[i] - mx) ** 2 for i in range(n))
    syy = sum((ry[i] - my) ** 2 for i in range(n))
    return sxy / math.sqrt(sxx * syy) if sxx and syy else 0.0


def _bootstrap(f, xs, ys, seed=1, n=1000):
    import random
    rng = random.Random(seed)
    m = len(xs)
    vals = []
    for _ in range(n):
        idx = [rng.randrange(m) for _ in range(m)]
        vals.append(f([xs[i] for i in idx], [ys[i] for i in idx]))
    vals.sort()
    return vals[int(0.025 * n)], vals[int(0.975 * n) - 1]


def _valuer(a):
    """A function (state, mover) -> win probability for the chosen head."""
    if a.cards:
        os.environ.setdefault("CPTCG_AGENT_PLUGINS", "cards_agents")
        import cards_agents as CA
        m = CA.load_cards_model(a.cards, a.ablate)
        return lambda s, me: float(CA._value_batch(m, [s], me)[0] and (1.0 / (1.0 + math.exp(-float(CA._value_batch(m, [s], me)[0])))))
    name = a.agent or ("neural" + (f"@{a.weights}" if a.weights else ""))
    ag = make_agent(name, 1)
    return lambda s, me: float(ag.model.value(s, me))


def cmd_agree(a) -> None:
    reg = load_default()
    data = json.loads(Path(a.oracle).read_text(encoding="utf-8"))
    val = _valuer(a)
    xs, cheat, plan, play = [], [], [], []
    for p in data["positions"]:
        lab = p.get("labels")
        po = p.get("playout")
        if a.independent:
            if not po:
                continue
        elif not lab or lab.get("cheat_value") is None:
            continue
        s = build_position(reg, p["spec"], DEFAULT_CONFIG)
        legal_actions(s)
        xs.append(val(s, p["mover"]))
        cheat.append(float(po["playout_value"]) if a.independent else float(lab["cheat_value"]))
        plan.append((lab or {}).get("plan_score"))
    if not xs:
        raise SystemExit("no labelled positions")
    brier = sum((x - c) ** 2 for x, c in zip(xs, cheat)) / len(xs)
    rho = _spearman(xs, cheat)
    lo, hi = _bootstrap(_spearman, xs, cheat)
    out = {"oracle": a.oracle, "head": a.cards or a.agent or a.weights or "shipped", "ablate": bool(a.ablate),
           "label": "heuristic playouts (independent)" if a.independent else "cheat:ismcts root value",
           "positions": len(xs), "spearman_vs_cheat": rho, "spearman_ci95": [lo, hi],
           "brier_vs_cheat": brier, "brier_const": sum((0.5 - c) ** 2 for c in cheat) / len(cheat)}
    pl = [(x, p) for x, p in zip(xs, plan) if p is not None]
    if pl:
        px, py = [x for x, _ in pl], [p for _, p in pl]
        out["spearman_vs_plan"] = _spearman(px, py)
        out["spearman_vs_plan_ci95"] = list(_bootstrap(_spearman, px, py))
    print(json.dumps(out, indent=1))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sample")
    p.add_argument("corpus", nargs="+")
    p.add_argument("--n", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20260924)
    p.add_argument("--out", default="data/arena/oracle.json")
    p.set_defaults(fn=cmd_sample)
    p = sub.add_parser("label")
    p.add_argument("oracle")
    p.add_argument("--budget", type=int, default=2000)
    p.add_argument("--plan", default="plan-deep:32")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--resume", action="store_true")
    p.set_defaults(fn=cmd_label)
    p = sub.add_parser("playouts", help="the independent label: heuristic playouts from the true state")
    p.add_argument("oracle")
    p.add_argument("--n", type=int, default=128)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--resume", action="store_true")
    p.set_defaults(fn=cmd_playouts)
    p = sub.add_parser("agree")
    p.add_argument("oracle")
    p.add_argument("--independent", action="store_true", help="score against the playout label")
    p.add_argument("--weights", default=None)
    p.add_argument("--cards", default=None)
    p.add_argument("--ablate", action="store_true")
    p.add_argument("--agent", default=None)
    p.add_argument("--out", default=None)
    p.set_defaults(fn=cmd_agree)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
