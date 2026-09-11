"""Fit the value head, and measure whether it is worth shipping.

    python tools/fit_eval.py bench [--widths 16,24,32,48,64,96,128]   # forward-pass cost by width
    python tools/fit_eval.py demo --out FILE -n 2000                  # synthetic set, proves the fit
    python tools/fit_eval.py fit DATA... --out src/cptcg/agents/weights.json

``bench`` and ``demo`` are stdlib; ``fit`` imports numpy lazily, because numpy may never be a
dependency of anything under ``src/cptcg`` (that package ships into the browser). Training happens
here, inference happens there, and the two are checked against each other by test.

Three decisions worth knowing before reading the code:

**The split is by game, never by position.** The ~136 decisions of one game share two decks, one
shuffle and one outcome label. Splitting positions at random puts near-copies of the same labelled
situation on both sides of the split, so the held-out score measures memorisation and every number
it produces is inflated. Games go whole to one side or the other.

**The loss is Brier, not log-loss.** Squared error after the logistic keeps a confidently wrong
prediction from dominating the gradient, which matters when the label is one noisy sample of a
distribution: a good position genuinely loses sometimes, and the model should not be punished as
though it had been certain.

**Two baselines are always reported.** Predicting 0.5 forever, and the frozen heuristic's own
evaluation squashed through a fitted logistic. The second one is the honest comparison: it asks
whether the network beats the hand-written constants, rather than whether it beats a badly
calibrated version of them, so its scale and offset are fitted on the training split.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.learn.features import FEATURE_NAMES, NFEAT  # noqa: E402
from cptcg.learn.model import ValueModel, _logistic  # noqa: E402


# ------------------------------------------------------------------ benchmark
def _bench_width(hidden: int, x, reps: int) -> float:
    """Median microseconds per forward pass at this hidden width."""
    rng = random.Random(7)
    m = ValueModel(hidden=hidden,
                   w1=tuple(tuple(rng.uniform(-0.4, 0.4) for _ in range(NFEAT)) for _ in range(hidden)),
                   b1=tuple(rng.uniform(-0.1, 0.1) for _ in range(hidden)),
                   w2=tuple(rng.uniform(-0.4, 0.4) for _ in range(hidden)), b2=0.0)
    for _ in range(50):
        m.forward(x)
    times = []
    for _ in range(reps):
        t = time.perf_counter()
        m.forward(x)
        times.append((time.perf_counter() - t) * 1e6)
    times.sort()
    return times[len(times) // 2]


def cmd_bench(a) -> None:
    """The width decision, measured rather than guessed.

    The search agent gets roughly a second and a half per move under Pyodide, which runs about two
    to three times slower than CPython here, so the number that matters is how many leaf
    evaluations fit in that budget.
    """
    from cptcg.cards.registry import load_default
    from cptcg.deck.decklist import Decklist
    from cptcg.core.engine import new_game
    from cptcg.learn.features import features

    reg = load_default()
    decks = (Decklist.load(ROOT / "data/decks/the_heist.json"),
             Decklist.load(ROOT / "data/decks/embracing_power.json"))
    s = new_game(reg, decks, 3)
    x = features(s, 0)

    t = time.perf_counter()
    for _ in range(200):
        features(s, 0)
    feat_us = (time.perf_counter() - t) / 200 * 1e6

    widths = [int(w) for w in a.widths.split(",")]
    print(f"features(s, me): {feat_us:.1f} us  ({NFEAT} features)\n")
    print(f"{'hidden':>7} {'params':>8} {'forward us':>11} {'x features':>11} {'evals in 1.5s':>14}")
    rows = []
    for h in widths:
        us = _bench_width(h, x, a.reps)
        params = h * NFEAT + h + h + 1
        # Pyodide is ~2.5x slower, and a leaf costs the forward pass plus its own feature extraction.
        per_leaf_wasm = (us + feat_us) * 2.5
        rows.append((h, params, us, us / feat_us, int(1.5e6 / per_leaf_wasm)))
        print(f"{h:>7} {params:>8} {us:>11.1f} {us / feat_us:>11.2f} {int(1.5e6 / per_leaf_wasm):>14}")
    if a.markdown:
        print("\n| hidden | parameters | forward pass | vs feature cost | leaf evals in a 1.5 s wasm budget |")
        print("|---:|---:|---:|---:|---:|")
        for h, p, us, ratio, evals in rows:
            print(f"| {h} | {p:,} | {us:.1f} us | {ratio:.2f}x | {evals:,} |")


# ------------------------------------------------------------------ data
def _examples_from(paths, reg, cfg, *, stride: int, limit: int | None, progress=None):
    """Yield (game_index, features, heuristic_score, label) from stored experience.

    Features are recomputed here rather than stored: a replay reconstructs every state exactly, so
    keeping feature vectors on disk would multiply the size of the archive for nothing.
    """
    from cptcg.agents.heuristic import evaluate as heval
    from cptcg.learn.experience import outcome, read_games, replay_features
    from cptcg.learn.features import features

    g = 0
    n = 0
    for path in paths:
        for record in read_games(path):
            for k, (state, _chosen, _visits, _value) in enumerate(replay_features(record, reg, cfg)):
                if stride > 1 and k % stride:
                    continue
                me = state.pending.player
                yield g, features(state, me), heval(state, me), outcome(record, me)
                n += 1
                if limit and n >= limit:
                    return
            g += 1
            if progress and g % 500 == 0:
                progress(g, n)


def _split_by_game(rows, holdout: float, seed: int):
    """Whole games to one side or the other. See the module docstring for why."""
    games = sorted({r[0] for r in rows})
    rng = random.Random(seed)
    rng.shuffle(games)
    cut = int(len(games) * (1.0 - holdout))
    train_games = set(games[:cut])
    tr = [r for r in rows if r[0] in train_games]
    ho = [r for r in rows if r[0] not in train_games]
    return tr, ho, len(train_games), len(games) - len(train_games)


# ------------------------------------------------------------------ baselines
def _fit_squashed_heuristic(train):
    """Fit scale and offset so heuristic score -> probability is as good as that score can be.

    Without this the comparison would be against a straw man: the raw evaluate() number is on an
    arbitrary scale, and squashing it with arbitrary constants would lose to anything.
    """
    import numpy as np

    h = np.array([r[2] for r in train], dtype=np.float64)
    y = np.array([r[3] for r in train], dtype=np.float64)
    sd = h.std() or 1.0
    hz = (h - h.mean()) / sd
    a, b = 1.0, 0.0
    for _ in range(400):                      # plain gradient descent on Brier; two parameters
        p = 1.0 / (1.0 + np.exp(-(a * hz + b)))
        d = 2.0 * (p - y) * p * (1.0 - p) / len(y)
        a -= 2.0 * float((d * hz).sum())
        b -= 2.0 * float(d.sum())
    return (a, b, float(h.mean()), sd)


def _squashed(params, h):
    a, b, mean, sd = params
    return _logistic(a * ((h - mean) / sd) + b)


def _brier(pred, y) -> float:
    return sum((p - t) ** 2 for p, t in zip(pred, y)) / max(1, len(y))


def _calibration(pred, y, buckets: int = 10):
    """Predicted probability against what actually happened, so over-confidence is visible."""
    from cptcg.sim.stats import wilson

    rows = []
    for i in range(buckets):
        lo, hi = i / buckets, (i + 1) / buckets
        sel = [(p, t) for p, t in zip(pred, y) if (lo <= p < hi or (i == buckets - 1 and p == 1.0))]
        if not sel:
            continue
        k = sum(1 for _p, t in sel if t >= 0.5)
        wl, wh = wilson(k, len(sel))
        rows.append({"bucket": f"{lo:.1f}-{hi:.1f}", "n": len(sel),
                     "predicted": sum(p for p, _t in sel) / len(sel),
                     "actual": k / len(sel), "lo": wl, "hi": wh})
    return rows


# ------------------------------------------------------------------ training
def _train(train, holdout, *, hidden, l2, epochs, patience, seed, log=print):
    import numpy as np

    X = np.array([r[1] for r in train], dtype=np.float64)
    Y = np.array([r[3] for r in train], dtype=np.float64)
    XV = np.array([r[1] for r in holdout], dtype=np.float64)
    YV = np.array([r[3] for r in holdout], dtype=np.float64)

    rs = np.random.RandomState(seed)
    # Xavier-ish: keep the pre-activation in tanh's responsive range at init.
    W1 = rs.normal(0.0, math.sqrt(1.0 / NFEAT), (hidden, NFEAT))
    B1 = np.zeros(hidden)
    W2 = rs.normal(0.0, math.sqrt(1.0 / hidden), hidden)
    b2 = 0.0

    ms = [np.zeros_like(W1), np.zeros_like(B1), np.zeros_like(W2), 0.0]
    vs = [np.zeros_like(W1), np.zeros_like(B1), np.zeros_like(W2), 0.0]
    lr, beta1, beta2, eps = 3e-3, 0.9, 0.999, 1e-8
    step = 0

    def forward(Xb):
        H = np.tanh(Xb @ W1.T + B1)
        O = H @ W2 + b2
        return H, 1.0 / (1.0 + np.exp(-O))

    def brier(Xb, Yb):
        _H, P = forward(Xb)
        return float(((P - Yb) ** 2).mean())

    best = (brier(XV, YV), W1.copy(), B1.copy(), W2.copy(), b2)
    log(f"  init: held-out Brier {best[0]:.4f}")
    stale = 0
    batch = 4096
    for epoch in range(1, epochs + 1):
        order = rs.permutation(len(X))
        for i in range(0, len(order), batch):
            idx = order[i:i + batch]
            Xb, Yb = X[idx], Y[idx]
            H, P = forward(Xb)
            n = len(idx)
            dO = 2.0 * (P - Yb) * P * (1.0 - P) / n           # dBrier/d(logit)
            dW2 = H.T @ dO + 2.0 * l2 * W2
            db2 = float(dO.sum())
            dZ = np.outer(dO, W2) * (1.0 - H * H)
            dW1 = dZ.T @ Xb + 2.0 * l2 * W1
            dB1 = dZ.sum(axis=0)

            step += 1
            for j, (g, p) in enumerate(((dW1, W1), (dB1, B1), (dW2, W2), (db2, b2))):
                ms[j] = beta1 * ms[j] + (1 - beta1) * g
                vs[j] = beta2 * vs[j] + (1 - beta2) * (g * g)
                mh = ms[j] / (1 - beta1 ** step)
                vh = vs[j] / (1 - beta2 ** step)
                upd = lr * mh / (np.sqrt(vh) + eps if j != 3 else math.sqrt(vh) + eps)
                if j == 0:
                    W1 = W1 - upd
                elif j == 1:
                    B1 = B1 - upd
                elif j == 2:
                    W2 = W2 - upd
                else:
                    b2 = b2 - upd

        hv = brier(XV, YV)
        if hv < best[0] - 1e-6:
            best = (hv, W1.copy(), B1.copy(), W2.copy(), b2)
            stale = 0
        else:
            stale += 1
        if epoch % 10 == 0 or stale >= patience:
            log(f"  epoch {epoch:>3}: train {brier(X, Y):.4f}  held-out {hv:.4f}  best {best[0]:.4f}")
        if stale >= patience:
            log(f"  early stop at epoch {epoch} (no held-out gain for {patience} epochs)")
            break

    _hv, W1, B1, W2, b2 = best
    return ValueModel(hidden=hidden,
                      w1=tuple(tuple(float(v) for v in row) for row in W1),
                      b1=tuple(float(v) for v in B1),
                      w2=tuple(float(v) for v in W2), b2=float(b2))


# ------------------------------------------------------------------ commands
def cmd_demo(a) -> None:
    """A synthetic set with a known answer, to prove the pipeline before spending on a harvest."""
    rng = random.Random(a.seed)
    rows = []
    for g in range(a.n // 20):
        for _k in range(20):
            x = [rng.uniform(-1, 1) for _ in range(NFEAT)]
            # A deliberately non-linear target, so a linear model cannot reach the ceiling.
            z = 2.0 * x[0] * x[1] + 1.5 * x[2] - 1.0 * x[3]
            y = 1.0 if rng.random() < _logistic(z) else 0.0
            # The stand-in for the heuristic's score sees the linear part and misses the
            # interaction, which is what a hand-written evaluator does. Handing it the exact logit
            # would make the baseline an oracle and the comparison meaningless.
            h = 1.5 * x[2] - 1.0 * x[3] + rng.gauss(0.0, 0.3)
            rows.append((g, tuple(x), h, y))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps([[g, list(x), h, y] for g, x, h, y in rows]), encoding="utf-8")
    print(f"wrote {len(rows)} synthetic examples over {a.n // 20} games to {a.out}")


def _load_rows(a, log):
    if a.synthetic:
        raw = json.loads(Path(a.synthetic).read_text(encoding="utf-8"))
        return [(g, tuple(x), h, y) for g, x, h, y in raw]
    from cptcg.cards.registry import load_default
    from cptcg.core.config import DEFAULT_CONFIG

    reg = load_default()
    t = time.perf_counter()
    rows = list(_examples_from([Path(p) for p in a.data], reg, DEFAULT_CONFIG,
                               stride=a.stride, limit=a.limit,
                               progress=lambda g, n: log(f"  {g} games, {n} examples")))
    log(f"  {len(rows)} examples from {len({r[0] for r in rows})} games "
        f"in {time.perf_counter() - t:.1f}s")
    return rows


def cmd_fit(a) -> None:
    lines: list[str] = []

    def log(msg):
        print(msg)
        lines.append(msg)

    rows = _load_rows(a, log)
    if not rows:
        sys.exit("no examples: check the data paths")

    train, holdout, ng_tr, ng_ho = _split_by_game(rows, a.holdout, a.seed)
    log(f"split by game: {len(train)} train examples ({ng_tr} games), "
        f"{len(holdout)} held out ({ng_ho} games)")

    model = _train(train, holdout, hidden=a.hidden, l2=a.l2, epochs=a.epochs,
                   patience=a.patience, seed=a.seed, log=log)

    yv = [r[3] for r in holdout]
    pred = [model.forward(r[1]) for r in holdout]
    sq = _fit_squashed_heuristic(train)
    base_const = _brier([0.5] * len(yv), yv)
    base_heur = _brier([_squashed(sq, r[2]) for r in holdout], yv)
    mine = _brier(pred, yv)

    log("")
    log(f"held-out Brier   always 0.5: {base_const:.4f}")
    log(f"                 frozen heuristic, fitted squash: {base_heur:.4f}")
    log(f"                 this model: {mine:.4f}")
    verdict = ("beats both baselines" if mine < base_heur and mine < base_const else
               "does NOT beat the heuristic baseline" if mine >= base_heur else
               "does not beat predicting 0.5")
    log(f"                 -> {verdict}")

    cal = _calibration(pred, yv)
    log("")
    log("calibration on held-out games (predicted vs what actually happened)")
    log(f"  {'bucket':>9} {'n':>7} {'predicted':>10} {'actual':>8}  95% interval")
    for r in cal:
        log(f"  {r['bucket']:>9} {r['n']:>7} {r['predicted']:>10.3f} {r['actual']:>8.3f}  "
            f"{r['lo']:.3f}-{r['hi']:.3f}")

    header = {"run": {"name": a.name, "games": ng_tr + ng_ho, "seed": a.seed,
                      "examples": len(rows), "stride": a.stride},
              "train": {"brier": mine, "baseline_const": base_const, "baseline_heuristic": base_heur,
                        "hidden": a.hidden, "l2": a.l2, "holdout_games": ng_ho,
                        "calibration": cal}}
    m = ValueModel(hidden=model.hidden, w1=model.w1, b1=model.b1, w2=model.w2, b2=model.b2,
                   header=header)
    out = m.save(a.out)
    log(f"\nwrote {out}")

    if a.append_docs:
        from cptcg.learn.arena import append_section
        body = ["### Value head fitted — " + a.name, "", "```", *lines, "```", ""]
        append_section(ROOT / "docs" / "learning.md", "\n".join(body))
        print("appended a section to docs/learning.md")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("bench", help="forward-pass cost by hidden width")
    p.add_argument("--widths", default="16,24,32,48,64,96,128")
    p.add_argument("--reps", type=int, default=300)
    p.add_argument("--markdown", action="store_true")
    p.set_defaults(fn=cmd_bench)

    p = sub.add_parser("demo", help="write a synthetic training set")
    p.add_argument("--out", required=True)
    p.add_argument("-n", type=int, default=2000)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(fn=cmd_demo)

    p = sub.add_parser("fit", help="fit the value head")
    p.add_argument("data", nargs="*", help="experience files written by tools/harvest.py")
    p.add_argument("--synthetic", help="a file from `demo`, instead of real experience")
    p.add_argument("--out", default=str(ROOT / "src/cptcg/agents/weights.json"))
    p.add_argument("--name", default="bootstrap")
    p.add_argument("--hidden", type=int, default=32)
    p.add_argument("--l2", type=float, default=1e-5)
    p.add_argument("--epochs", type=int, default=400)
    p.add_argument("--patience", type=int, default=25)
    p.add_argument("--holdout", type=float, default=0.2)
    p.add_argument("--stride", type=int, default=1, help="keep every Nth decision of a game")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--append-docs", action="store_true")
    p.set_defaults(fn=cmd_fit)

    a = ap.parse_args()
    if getattr(a, "limit", None) == 0:
        a.limit = None
    a.fn(a)


if __name__ == "__main__":
    main()
