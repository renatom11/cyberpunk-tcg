"""Evolve the value head against wins.

    python tools/evolve.py run --iters 40          # search, checkpointing every iteration
    python tools/evolve.py status                  # the curve so far
    python tools/evolve.py promote                 # copy the champion somewhere a gate can see it

One iteration: draw 16 perturbations, play each ``theta+sigma*e`` against its own mirror
``theta-sigma*e`` on a shared set of seeds, turn the 16 results into centred ranks, and take one
antithetic step. Every fifth iteration the current theta plays the frozen anchor on *unseen* seeds
— the only absolute number in the run, and the one that catches a search that has walked somewhere
only its own mirrors think is good.

Why a pair plays itself rather than an anchor: it is the most informative game available. Both
sides differ by exactly ``2*sigma*e``, the seeds are shared, and the result answers the only
question the step needs answered — which way along ``e`` is better. Playing an anchor instead
spends the same games to produce a noisier estimate of a quantity the step does not use.

Resumable by construction: the ledger holds seeds and the current weights are on disk, so a
container that dies mid-run costs one iteration.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.cards.registry import load_default                      # noqa: E402
from cptcg.learn import evolve                                     # noqa: E402
from cptcg.learn.arena import head_to_head, sampled_pairings       # noqa: E402

PAIRS = 16              # antithetic pairs per iteration
GPP = 4                 # games per deck pairing per side; 6 pairings x 4 = 24 games a pair
ANCHOR_EVERY = 5
ANCHOR_GPP = 16         # 6 pairings x 16 = 96 games against the anchor
SEARCH_BUDGET = 16      # search iterations while evolving; validate higher
DECK_SEED = 880011


def _agent(path: Path, budget: int = SEARCH_BUDGET) -> str:
    return f"ismcts:{budget}@{path}"


def iterate(reg, run: evolve.Run, theta: list[float], shape, template: dict, d: Path,
            *, workers: int) -> list[float]:
    """One antithetic step, played out."""
    n = len(run.iterations)
    seed = 500_000 + n
    eps = evolve.perturbations(PAIRS, len(theta), seed=seed)
    # A fresh deck sample per iteration, shared by every pair *within* it. Shared is what makes the
    # comparison paired; fresh is what stops the search fitting one deck sample.
    prs = sampled_pairings(reg, 6, deck_seed=DECK_SEED + n, label=f"evo{n}")
    rec = evolve.Iteration(n=n, seed=seed, sigma=run.sigma, alpha=run.alpha)
    plus_p, minus_p = d / "plus.json", d / "minus.json"
    for i, e in enumerate(eps):
        plus_p.write_text(json.dumps(evolve.unflatten(
            [t + run.sigma * x for t, x in zip(theta, e)], shape, template)))
        minus_p.write_text(json.dumps(evolve.unflatten(
            [t - run.sigma * x for t, x in zip(theta, e)], shape, template)))
        r = head_to_head(reg, _agent(plus_p), _agent(minus_p), prs, games_per_pairing=GPP,
                         seed=4242 + n, workers=workers, sprt=None, deck_seed=DECK_SEED + n)
        rec.pair_scores.append(r.a_wins / r.games if r.games else 0.5)
        print(f"    pair {i:2d}: {rec.pair_scores[-1]:.3f}", flush=True)
    run.iterations.append(rec)
    return evolve.step(theta, eps, rec.pair_scores, sigma=run.sigma, alpha=run.alpha)


def anchor_check(reg, run: evolve.Run, theta_p: Path, anchor: str, *, workers: int) -> float:
    """The only absolute measurement: theta against a frozen opponent, on seeds it never trained on."""
    n = len(run.iterations)
    prs = sampled_pairings(reg, 6, deck_seed=DECK_SEED + 9_000 + n, label=f"anchor{n}")
    r = head_to_head(reg, _agent(theta_p), anchor, prs, games_per_pairing=ANCHOR_GPP,
                     seed=7_000 + n, workers=workers, sprt=None, deck_seed=DECK_SEED + 9_000 + n)
    rate = r.a_wins / r.games
    rec = run.iterations[-1]
    rec.anchor, rec.anchor_games = rate, r.games
    rec.note = run.record_anchor(rate)
    return rate


def cmd_run(a) -> int:
    d = Path(a.dir)
    d.mkdir(parents=True, exist_ok=True)
    ledger, theta_p, best_p = d / "run.json", d / "theta.json", d / "best.json"
    run = evolve.Run.load(ledger)

    template = json.loads(Path(a.parent).read_text())
    if theta_p.exists():
        theta, shape = evolve.flatten(json.loads(theta_p.read_text()))
        print(f"resuming at iteration {len(run.iterations)}")
    else:
        theta, shape = evolve.flatten(template)
        theta_p.write_text(json.dumps(template))
        best_p.write_text(json.dumps(template))
    anchor = _agent(Path(a.parent))
    reg = load_default()

    for _ in range(a.iters):
        n = len(run.iterations)
        t0 = time.time()
        print(f"iteration {n}  sigma={run.sigma:.4f} alpha={run.alpha:.1e}", flush=True)
        theta = iterate(reg, run, theta, shape, template, d, workers=a.workers)
        theta_p.write_text(json.dumps(evolve.unflatten(theta, shape, template)))
        run.save(ledger)
        if (n + 1) % ANCHOR_EVERY == 0:
            rate = anchor_check(reg, run, theta_p, anchor, workers=a.workers)
            print(f"  anchor: {rate:.1%} vs the parent — {run.iterations[-1].note}", flush=True)
            if rate >= run.best_anchor:
                best_p.write_text(theta_p.read_text())
            run.save(ledger)
        print(f"  iteration {n} in {time.time() - t0:.0f}s", flush=True)
    return 0


def cmd_status(a) -> int:
    run = evolve.Run.load(Path(a.dir) / "run.json")
    if not run.iterations:
        print("no iterations yet")
        return 0
    print(f"{len(run.iterations)} iterations, sigma {run.sigma:.4f}, "
          f"best anchor {run.best_anchor:.1%} at iteration {run.best_iter}")
    print(f"{'iter':>5} {'sigma':>8} {'mean pair':>10} {'anchor':>8}  note")
    for r in run.iterations:
        m = sum(r.pair_scores) / len(r.pair_scores) if r.pair_scores else 0.0
        anc = f"{r.anchor:.1%}" if r.anchor is not None else "-"
        print(f"{r.n:>5} {r.sigma:>8.4f} {m:>10.3f} {anc:>8}  {r.note}")
    return 0


def cmd_promote(a) -> int:
    d = Path(a.dir)
    src, dst = d / "best.json", Path(a.out)
    if not src.exists():
        print("no champion yet", file=sys.stderr)
        return 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text())
    run = evolve.Run.load(d / "run.json")
    print(f"wrote {dst} (anchor {run.best_anchor:.1%} at iteration {run.best_iter}). "
          f"It still has to clear the ordinary gate before it is promoted anywhere.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dir", default="out/evolve")
    r.add_argument("--parent", default="out/learn/gen-001/weights.json")
    r.add_argument("--iters", type=int, default=5)
    r.add_argument("--workers", type=int, default=4)
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("status"); s.add_argument("--dir", default="out/evolve"); s.set_defaults(fn=cmd_status)
    q = sub.add_parser("promote")
    q.add_argument("--dir", default="out/evolve")
    q.add_argument("--out", default="out/evolve/champion.json")
    q.set_defaults(fn=cmd_promote)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
