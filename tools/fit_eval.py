"""Fit the value head, and measure whether it is worth shipping.

    python tools/fit_eval.py bench [--widths 8,16,24,32,48,64,96,128] [--reps N] [--markdown]
    python tools/fit_eval.py demo --out PATH -n 200 [--seed S]
    python tools/fit_eval.py fit DATA... --out src/cptcg/agents/weights.json [--hidden 32]
           [--l2 1e-4] [--epochs 400] [--patience 25] [--holdout 0.2] [--seed S] [--append-docs]
    python tools/fit_eval.py sweep DATA... --widths 8,16,24,32,48,64 [--frac 0.3]
    python tools/fit_eval.py diagnose --weights PATH --games N

``bench``, ``demo`` and ``diagnose`` are stdlib. ``fit`` and ``sweep`` import numpy **lazily,
inside the function**, because numpy may never be a dependency of anything under ``src/cptcg``:
that package is zipped into a phone browser. Training happens here, inference happens there, and
``tests/learn/test_model.py`` checks the two against each other to 1e-12.

Four decisions worth knowing before reading the code.

**The split is by game, never by position.** The ~140 decisions of one game share two decks, one
shuffle and one outcome label. Splitting positions at random puts near-copies of the same labelled
situation on both sides of the split, so the held-out score measures memorisation, and every number
it produces is inflated. Games go whole to one side or the other — and when several harvests are
read at once their game indices are renumbered first, because game 0 of one file is not game 0 of
another.

**The loss is Brier, not log-loss.** Squared error after the logistic keeps a confidently wrong
prediction from dominating the gradient, which matters when the label is one noisy sample of a
distribution: a good position genuinely loses sometimes, and the model should not be punished as
though it had claimed certainty. Log-loss and accuracy are *reported* — they are what a reader
expects — but nothing is selected on them.

**Four models are always scored, on the same rows.** Predicting 0.5 forever; the frozen
heuristic's own ``evaluate()`` squashed through a logistic whose scale and offset are fitted on the
*training* split; a no-hidden-layer logistic regression on the same 114 features; and the network.
The second is the honest comparison — it asks whether the network beats the hand-written constants
rather than whether it beats a badly calibrated version of them. The third says how much of any
gain is the hidden layer rather than the feature set.

**Model selection never sees an arena result.** The width is chosen on held-out Brier alone, by
``sweep``, before a single game is played against anything.
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
sys.path.insert(0, str(ROOT / "tools"))

from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.learn.features import FEATURE_NAMES, NFEAT  # noqa: E402
from cptcg.learn.model import ValueModel  # noqa: E402


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ==================================================================== benchmark
def bench(widths=(16, 32, 48, 64, 96, 128), reps: int = 300) -> list[dict]:
    """Forward-pass cost against hidden width, on this machine. Pure stdlib, callable in-process.

    The width decision is measured rather than guessed because the agent's real budget is a move,
    not a forward pass: a leaf costs ``features()`` *plus* the model, and under Pyodide both cost
    more. ``x_features`` is the ratio that matters — a model that costs several times its own input
    has stopped being a cheap scorer.
    """
    from cptcg.cards.registry import load_default
    from cptcg.core.engine import new_game
    from cptcg.deck.decklist import Decklist
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

    rng = random.Random(7)
    out = []
    for hidden in widths:
        m = ValueModel(
            hidden=hidden,
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
        us = times[len(times) // 2]
        out.append({"hidden": hidden, "params": hidden * NFEAT + 2 * hidden + 1,
                    "forward_us": us, "features_us": feat_us, "x_features": us / feat_us,
                    "leaf_us": us + feat_us, "leaves_per_s": 1e6 / (us + feat_us)})
    return out


def cmd_bench(a) -> int:
    rows = bench([int(w) for w in a.widths.split(",")], a.reps)
    print(f"features(s, me): {rows[0]['features_us']:.1f} us  ({NFEAT} features)\n")
    print(f"{'hidden':>7} {'params':>8} {'forward us':>11} {'x features':>11} {'leaves/s':>10}")
    for r in rows:
        print(f"{r['hidden']:>7} {r['params']:>8} {r['forward_us']:>11.1f} "
              f"{r['x_features']:>11.2f} {r['leaves_per_s']:>10.0f}")
    if a.markdown:
        print("\n| hidden | parameters | forward pass | vs feature cost | leaf evaluations/s |")
        print("|---:|---:|---:|---:|---:|")
        for r in rows:
            print(f"| {r['hidden']} | {r['params']:,} | {r['forward_us']:.1f} us | "
                  f"{r['x_features']:.2f}x | {r['leaves_per_s']:,.0f} |")
    return 0


# ==================================================================== demo data
def cmd_demo(a) -> int:
    """A few real games, written in the harvest's own format, so the pipeline can be exercised
    end to end without waiting on a harvest. Same calls ``tools/harvest.py play`` makes."""
    from cptcg.cards.registry import load_default
    from cptcg.core.rng import Pcg32
    from cptcg.learn import decks as D
    from cptcg.learn.experience import GameRecord, write_games
    from cptcg.sim import runner
    from cptcg.sim.record import Replay

    reg = load_default()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    recs = []
    for i in range(a.n):
        d0, d1 = D.sample_pair(reg, Pcg32((a.seed ^ (i * 0x9E3779B1)) & 0xFFFFFFFFFFFFFFFF, seq=909))
        gs = (a.seed * 1000003 + i) & 0x7FFFFFFF
        s = runner.play_game(reg, (d0, d1), ("heuristic", "heuristic"), gs, DEFAULT_CONFIG,
                             record=True)
        recs.append(GameRecord.from_replay(Replay.from_game(s, (d0, d1), ("heuristic", "heuristic")),
                                           meta={"i": i}))
    write_games(out, recs, append=False)
    print(f"wrote {len(recs)} games to {out}")
    return 0


# ==================================================================== reading the matrix
def _read_header(p: Path) -> tuple[Path, dict]:
    """Accept the prefix, the .json or the .f32; return (f32 path, header)."""
    s = str(p)
    for suffix in (".f32", ".json"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    head = json.loads(Path(s + ".json").read_text(encoding="utf-8"))
    return Path(s).parent / head["data"], head


def load_matrix(paths, *, log=print):
    """Read one or more ``harvest examples`` outputs into ``(X, y, game, ply, heads)``.

    Game indices are renumbered across files, because two harvests both start at game 0 and a
    by-game split that confused them would put the same game on both sides.
    """
    import numpy as np

    Xs, ys, gs, ps, heads = [], [], [], [], []
    base = 0
    for raw in paths:
        f32, head = _read_header(Path(raw))
        cols = head["cols"]
        if head["columns"] != list(FEATURE_NAMES) + ["label", "game", "ply"]:
            raise SystemExit(f"{f32}: column list is not this build's feature vector")
        if head["rules"] != DEFAULT_CONFIG.digest():
            raise SystemExit(f"{f32}: fitted under ruleset {head['rules']}, this build is "
                             f"{DEFAULT_CONFIG.digest()}")
        want = head["rows"] * cols * 4
        if f32.stat().st_size != want:
            raise SystemExit(f"{f32}: {f32.stat().st_size} bytes, header claims {want}")
        m = np.fromfile(f32, dtype="<f4").reshape(head["rows"], cols)
        g = m[:, NFEAT + 1].astype(np.int64) + base
        head["_offset"] = base
        head["_span"] = (int(g.max()) + 1 - base) if len(g) else 0
        base = base + head["_span"]
        Xs.append(m[:, :NFEAT])
        ys.append(m[:, NFEAT].astype(np.float64))
        gs.append(g)
        ps.append(m[:, NFEAT + 2].astype(np.int32))
        heads.append(head)
        log(f"  {f32.name}: {head['rows']:,} rows, {head['games']:,} games, "
            f"rate {head['rate']}, perspectives {head.get('perspectives', 'move')}")
    X = np.concatenate(Xs) if len(Xs) > 1 else Xs[0]
    return X, np.concatenate(ys), np.concatenate(gs), np.concatenate(ps), heads


def split_by_game(game, holdout: float, seed: int):
    """Whole games to one side or the other. See the module docstring for why."""
    import numpy as np

    ids = np.unique(game)
    rs = np.random.RandomState(seed)
    perm = rs.permutation(len(ids))
    cut = int(round(len(ids) * (1.0 - holdout)))
    train_ids = set(ids[perm[:cut]].tolist())
    mask = np.fromiter((int(g) in train_ids for g in game), dtype=bool, count=len(game))
    return mask, cut, len(ids) - cut


# ==================================================================== metrics
def _metrics(p, y):
    import numpy as np

    p = np.clip(np.asarray(p, dtype=np.float64), 1e-12, 1 - 1e-12)
    y = np.asarray(y, dtype=np.float64)
    brier = float(((p - y) ** 2).mean())
    logloss = float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())
    decided = y != 0.5
    acc = float(((p[decided] >= 0.5) == (y[decided] >= 0.5)).mean()) if decided.any() else None
    return {"brier": brier, "log_loss": logloss, "accuracy": acc, "n": int(len(y))}


def calibration(p, y, buckets: int = 10):
    """Predicted probability against what actually happened, with an interval, so
    over-confidence is visible rather than averaged away."""
    import numpy as np

    from cptcg.sim.stats import wilson

    p = np.asarray(p, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    rows = []
    for i in range(buckets):
        lo, hi = i / buckets, (i + 1) / buckets
        sel = (p >= lo) & ((p < hi) if i < buckets - 1 else (p <= hi))
        n = int(sel.sum())
        if not n:
            continue
        k = int((y[sel] >= 0.5).sum())
        wl, wh = wilson(k, n)
        rows.append({"bucket": f"{lo:.1f}-{hi:.1f}", "n": n,
                     "predicted": float(p[sel].mean()), "actual": k / n,
                     "lo": wl, "hi": wh, "gap": abs(float(p[sel].mean()) - k / n)})
    ece = sum(r["n"] * r["gap"] for r in rows) / max(1, sum(r["n"] for r in rows))
    worst = max((r["gap"] for r in rows), default=0.0)
    return rows, ece, worst


def render_calibration(rows) -> list[str]:
    out = [f"  {'bucket':>9} {'n':>9} {'predicted':>10} {'actual':>8}  95% interval",
           f"  {'-' * 9} {'-' * 9} {'-' * 10} {'-' * 8}  {'-' * 13}"]
    for r in rows:
        out.append(f"  {r['bucket']:>9} {r['n']:>9,} {r['predicted']:>10.3f} {r['actual']:>8.3f}  "
                   f"{r['lo']:.3f}-{r['hi']:.3f}")
    return out


# ==================================================================== the network
def train_network(X, y, mask, *, hidden, l2, epochs, patience, seed, batch=4096, log=print):
    """Adam on Brier, L2 on the two weight matrices only, early stopping on held-out Brier.

    Returns ``(ValueModel, best_epoch, history)``. The biases are deliberately unpenalised: a
    penalty on ``b2`` is a penalty on the base rate, which is not overfitting.
    """
    import numpy as np

    Xt, yt = X[mask], y[mask]
    Xv, yv = X[~mask], y[~mask]
    rs = np.random.RandomState(seed)
    W1 = rs.normal(0.0, math.sqrt(1.0 / NFEAT), (hidden, NFEAT))
    B1 = np.zeros(hidden)
    W2 = rs.normal(0.0, math.sqrt(1.0 / hidden), hidden)
    b2 = 0.0

    mW1 = np.zeros_like(W1); vW1 = np.zeros_like(W1)          # noqa: E702
    mB1 = np.zeros_like(B1); vB1 = np.zeros_like(B1)          # noqa: E702
    mW2 = np.zeros_like(W2); vW2 = np.zeros_like(W2)          # noqa: E702
    mb2 = 0.0; vb2 = 0.0                                      # noqa: E702
    lr, beta1, beta2, eps = 3e-3, 0.9, 0.999, 1e-8
    step = 0

    def probs(Xb, W1, B1, W2, b2):
        H = np.tanh(Xb @ W1.T + B1)
        return H, 1.0 / (1.0 + np.exp(-(H @ W2 + b2)))

    def val_brier(W1, B1, W2, b2):
        tot = 0.0
        for i in range(0, len(Xv), 200_000):                  # chunked: the matrix can be ~1 GB
            _H, P = probs(Xv[i:i + 200_000], W1, B1, W2, b2)
            tot += float(((P - yv[i:i + 200_000]) ** 2).sum())
        return tot / max(1, len(yv))

    best_v = val_brier(W1, B1, W2, b2)
    best = (W1.copy(), B1.copy(), W2.copy(), b2)
    best_epoch = 0
    history = [{"epoch": 0, "val_brier": best_v}]
    log(f"  epoch   0: held-out Brier {best_v:.5f}  (init)")
    stale = 0
    n = len(Xt)
    for epoch in range(1, epochs + 1):
        order = rs.permutation(n)
        for i in range(0, n, batch):
            idx = order[i:i + batch]
            Xb = Xt[idx]
            yb = yt[idx]
            H, P = probs(Xb, W1, B1, W2, b2)
            k = len(idx)
            dO = 2.0 * (P - yb) * P * (1.0 - P) / k           # dBrier/d(pre-logistic)
            dW2 = H.T @ dO + 2.0 * l2 * W2
            db2 = float(dO.sum())
            dZ = np.outer(dO, W2) * (1.0 - H * H)
            dW1 = dZ.T @ Xb + 2.0 * l2 * W1
            dB1 = dZ.sum(axis=0)

            step += 1
            c1 = 1 - beta1 ** step
            c2 = 1 - beta2 ** step
            mW1 = beta1 * mW1 + (1 - beta1) * dW1; vW1 = beta2 * vW1 + (1 - beta2) * dW1 * dW1  # noqa: E702,E501
            mB1 = beta1 * mB1 + (1 - beta1) * dB1; vB1 = beta2 * vB1 + (1 - beta2) * dB1 * dB1  # noqa: E702,E501
            mW2 = beta1 * mW2 + (1 - beta1) * dW2; vW2 = beta2 * vW2 + (1 - beta2) * dW2 * dW2  # noqa: E702,E501
            mb2 = beta1 * mb2 + (1 - beta1) * db2; vb2 = beta2 * vb2 + (1 - beta2) * db2 * db2  # noqa: E702,E501
            W1 -= lr * (mW1 / c1) / (np.sqrt(vW1 / c2) + eps)
            B1 -= lr * (mB1 / c1) / (np.sqrt(vB1 / c2) + eps)
            W2 -= lr * (mW2 / c1) / (np.sqrt(vW2 / c2) + eps)
            b2 -= lr * (mb2 / c1) / (math.sqrt(vb2 / c2) + eps)

        hv = val_brier(W1, B1, W2, b2)
        history.append({"epoch": epoch, "val_brier": hv})
        if hv < best_v - 1e-7:
            best_v, best, best_epoch, stale = hv, (W1.copy(), B1.copy(), W2.copy(), b2), epoch, 0
        else:
            stale += 1
        if epoch % 5 == 0 or stale >= patience:
            log(f"  epoch {epoch:>3}: held-out Brier {hv:.5f}   best {best_v:.5f} "
                f"(epoch {best_epoch})")
        if stale >= patience:
            log(f"  early stop: {patience} epochs with no held-out gain")
            break

    W1, B1, W2, b2 = best
    m = ValueModel(hidden=hidden,
                   w1=tuple(tuple(float(v) for v in row) for row in W1),
                   b1=tuple(float(v) for v in B1),
                   w2=tuple(float(v) for v in W2), b2=float(b2))
    return m, best_epoch, history


def model_probs(m: ValueModel, X):
    """The model's output over a whole matrix, through numpy. Agrees with ``forward`` to 1e-12;
    ``tests/learn/test_model.py`` is the check."""
    import numpy as np

    W1 = np.array(m.w1); B1 = np.array(m.b1); W2 = np.array(m.w2)      # noqa: E702
    out = np.empty(len(X))
    for i in range(0, len(X), 200_000):
        H = np.tanh(X[i:i + 200_000] @ W1.T + B1)
        out[i:i + 200_000] = 1.0 / (1.0 + np.exp(-(H @ W2 + m.b2)))
    return out


def train_logistic(X, y, mask, *, l2, epochs, seed, batch=4096, log=print):
    """The no-hidden-layer baseline: what these 114 features are worth without a hidden layer."""
    import numpy as np

    Xt, yt = X[mask], y[mask]
    rs = np.random.RandomState(seed)
    w = np.zeros(NFEAT)
    b = 0.0
    mw = np.zeros(NFEAT); vw = np.zeros(NFEAT); mb = 0.0; vb = 0.0     # noqa: E702
    lr, beta1, beta2, eps = 3e-3, 0.9, 0.999, 1e-8
    step = 0
    n = len(Xt)
    for _epoch in range(epochs):
        order = rs.permutation(n)
        for i in range(0, n, batch):
            idx = order[i:i + batch]
            Xb, yb = Xt[idx], yt[idx]
            P = 1.0 / (1.0 + np.exp(-(Xb @ w + b)))
            dO = 2.0 * (P - yb) * P * (1.0 - P) / len(idx)
            gw = Xb.T @ dO + 2.0 * l2 * w
            gb = float(dO.sum())
            step += 1
            c1 = 1 - beta1 ** step; c2 = 1 - beta2 ** step             # noqa: E702
            mw = beta1 * mw + (1 - beta1) * gw; vw = beta2 * vw + (1 - beta2) * gw * gw  # noqa: E702,E501
            mb = beta1 * mb + (1 - beta1) * gb; vb = beta2 * vb + (1 - beta2) * gb * gb  # noqa: E702,E501
            w -= lr * (mw / c1) / (np.sqrt(vw / c2) + eps)
            b -= lr * (mb / c1) / (math.sqrt(vb / c2) + eps)
    return w, b


def logistic_probs(w, b, X):
    import numpy as np

    out = np.empty(len(X))
    for i in range(0, len(X), 200_000):
        out[i:i + 200_000] = 1.0 / (1.0 + np.exp(-(X[i:i + 200_000] @ w + b)))
    return out


# ==================================================================== the heuristic baseline
def probe_rows(sources, game_ids, *, limit: int, perspectives: str, log=print):
    """Replay a set of games and return ``(features, heuristic score, label)`` per row.

    ``evaluate()`` is not a column of the training matrix — it is a *score*, and the matrix stores
    only the description — so the heuristic baseline has to be measured by replaying. A few hundred
    games is plenty for a Brier estimate and costs seconds.
    """
    from cptcg.agents.heuristic import evaluate as heval
    from cptcg.cards.registry import load_default
    from cptcg.learn.experience import outcome, read_games, replay_features
    from cptcg.learn.features import features

    reg = load_default()
    X, H, Y = [], [], []
    ngames = 0
    for fi, paths in enumerate(sources):           # sources[fi] is file fi's own source list
        ids = set(game_ids.get(fi) or ())
        if not ids:
            continue
        # ``limit`` is per source file, not per call: with a heuristic harvest and a random one,
        # a global cap would take every probe game from whichever file was listed first and the
        # baseline would be measured on one population only.
        taken = 0
        for path in paths:
            for rec in read_games(path):
                if rec.meta.get("i") not in ids:
                    continue
                for s, _c, _v, _val in replay_features(rec, reg):
                    me = s.pending.player
                    seats = (me, 1 - me) if perspectives == "both" else (me,)
                    for seat in seats:
                        X.append(features(s, seat))
                        H.append(heval(s, seat))
                        Y.append(outcome(rec, seat))
                taken += 1
                ngames += 1
                if taken >= limit:
                    break
            if taken >= limit:
                break
    log(f"  probed {ngames} games, {len(Y):,} rows")
    return X, H, Y


def fit_squash(h, y):
    """Scale and offset so ``evaluate() -> probability`` is as good as that score can be.

    Fitted on the *training* side only. Without this the comparison would be against a straw man:
    the raw number is on an arbitrary scale, and squashing it with arbitrary constants would lose
    to anything at all.
    """
    import numpy as np

    h = np.asarray(h, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    mean = float(h.mean())
    sd = float(h.std()) or 1.0
    hz = (h - mean) / sd
    a, b = 1.0, 0.0
    for _ in range(2000):
        p = 1.0 / (1.0 + np.exp(-(a * hz + b)))
        d = 2.0 * (p - y) * p * (1.0 - p) / len(y)
        a -= 4.0 * float((d * hz).sum())
        b -= 4.0 * float(d.sum())
    return {"a": a, "b": b, "mean": mean, "sd": sd}


def squash_probs(sq, h):
    import numpy as np

    z = (np.asarray(h, dtype=np.float64) - sq["mean"]) / sq["sd"]
    return 1.0 / (1.0 + np.exp(-(sq["a"] * z + sq["b"])))


# ==================================================================== fit
def _game_ids_per_file(game, heads, keep_mask):
    """Undo ``load_matrix``'s renumbering: which original game index, in which source file.

    ``load_matrix`` offsets each file's game column by the running maximum, and records that
    offset on the header, so this is a subtraction rather than a guess.
    """
    import numpy as np

    ids = np.unique(game[keep_mask])
    out: dict[int, list[int]] = {}
    for fi, head in enumerate(heads):
        lo = head["_offset"]
        hi = lo + head["_span"]
        sel = ids[(ids >= lo) & (ids < hi)]
        out[fi] = [int(v - lo) for v in sel]
    return out


def cmd_fit(a) -> int:
    lines: list[str] = []

    def log(msg=""):
        print(msg, flush=True)
        lines.append(msg)

    t0 = time.time()
    log(f"data ({len(a.data)} file(s)):")
    X, y, game, ply, heads = load_matrix(a.data, log=log)
    persp = heads[0].get("perspectives", "move")
    log(f"  total {len(y):,} rows x {NFEAT} features, {len(set(game.tolist())):,} games, "
        f"mean label {float(y.mean()):.4f}")

    mask, ng_tr, ng_ho = split_by_game(game, a.holdout, a.seed)
    log(f"split BY GAME (never by position): {int(mask.sum()):,} train rows / {ng_tr:,} games, "
        f"{int((~mask).sum()):,} held out / {ng_ho:,} games")
    log()

    log(f"fitting hidden={a.hidden} l2={a.l2} epochs<={a.epochs} patience={a.patience} "
        f"seed={a.seed}")
    model, best_epoch, history = train_network(
        X, y, mask, hidden=a.hidden, l2=a.l2, epochs=a.epochs, patience=a.patience,
        seed=a.seed, log=log)
    log()

    yv = y[~mask]
    pv = model_probs(model, X[~mask])
    m_net = _metrics(pv, yv)
    m_const = _metrics([0.5] * len(yv), yv)

    log("logistic baseline (same features, no hidden layer)")
    w, b = train_logistic(X, y, mask, l2=a.l2, epochs=a.logistic_epochs, seed=a.seed, log=log)
    m_log = _metrics(logistic_probs(w, b, X[~mask]), yv)

    # --- the heuristic baseline, measured on a replayed subsample of the same split ------------
    sources = [[Path(p) for p in h["sources"]] for h in heads]
    log(f"\nheuristic baseline: replaying {a.probe_games} train and {a.probe_games} held-out games")
    tr_ids = _game_ids_per_file(game, heads, mask)
    ho_ids = _game_ids_per_file(game, heads, ~mask)
    Xtr_p, Htr_p, Ytr_p = probe_rows(sources, tr_ids, limit=a.probe_games, perspectives=persp,
                                     log=log)
    Xho_p, Hho_p, Yho_p = probe_rows(sources, ho_ids, limit=a.probe_games, perspectives=persp,
                                     log=log)
    sq = fit_squash(Htr_p, Ytr_p)
    import numpy as np
    Xho_np = np.array(Xho_p, dtype=np.float64)
    probe = {
        "n": len(Yho_p),
        "const": _metrics([0.5] * len(Yho_p), Yho_p),
        "heuristic": _metrics(squash_probs(sq, Hho_p), Yho_p),
        "logistic": _metrics(logistic_probs(w, b, Xho_np), Yho_p),
        "network": _metrics(model_probs(model, Xho_np), Yho_p),
    }

    cal, ece, worst = calibration(pv, yv)

    log("")
    log(f"held-out, all {m_net['n']:,} rows")
    log(f"  {'model':<34} {'Brier':>8} {'log-loss':>9} {'accuracy':>9}")
    for name, m in (("always 0.5", m_const), ("logistic, same features", m_log),
                    (f"network, hidden={a.hidden}", m_net)):
        acc = "n/a" if m["accuracy"] is None else f"{m['accuracy']:.4f}"
        log(f"  {name:<34} {m['brier']:>8.5f} {m['log_loss']:>9.5f} {acc:>9}")
    log("")
    log(f"held-out subsample, {probe['n']:,} rows replayed so evaluate() can be scored too")
    log(f"  {'model':<34} {'Brier':>8} {'log-loss':>9} {'accuracy':>9}")
    for name, key in (("always 0.5", "const"), ("frozen heuristic, fitted squash", "heuristic"),
                      ("logistic, same features", "logistic"),
                      (f"network, hidden={a.hidden}", "network")):
        m = probe[key]
        acc = "n/a" if m["accuracy"] is None else f"{m['accuracy']:.4f}"
        log(f"  {name:<34} {m['brier']:>8.5f} {m['log_loss']:>9.5f} {acc:>9}")
    beat_h = probe["network"]["brier"] < probe["heuristic"]["brier"]
    log(f"  -> the network {'beats' if beat_h else 'does NOT beat'} the frozen heuristic's own "
        f"evaluation on held-out games")
    log("")
    log(f"calibration on held-out games (ECE {ece:.4f}, worst bucket gap {worst:.4f})")
    for line in render_calibration(cal):
        log(line)

    header = {
        "run": {"name": a.name, "utc": _now(),
                "games": int(sum(h["games"] for h in heads)), "seed": a.seed,
                "mix": a.mix, "agents": a.agents,
                "sources": [str(p) for ps in sources for p in ps], "perspectives": persp,
                "rows": int(len(y)), "rate": [h["rate"] for h in heads]},
        "train": {"n": int(len(y)), "train_rows": int(mask.sum()),
                  "holdout_rows": int((~mask).sum()), "train_games": ng_tr,
                  "holdout_games": ng_ho, "epochs": len(history) - 1, "best_epoch": best_epoch,
                  "l2": a.l2, "hidden": a.hidden, "batch": 4096, "optimiser": "adam",
                  "loss": "brier",
                  "holdout": {"const": m_const, "logistic": m_log, "network": m_net},
                  "probe": probe, "squash": sq,
                  "calibration": cal, "ece": ece, "worst_gap": worst,
                  "history": history[-1:] if a.slim_history else history},
    }
    m = ValueModel(hidden=model.hidden, w1=model.w1, b1=model.b1, w2=model.w2, b2=model.b2,
                   header=header)
    out = m.save(a.out)
    log(f"\nwrote {out} ({out.stat().st_size / 1024:.0f} KB) in {time.time() - t0:.0f}s")

    if a.append_docs:
        from cptcg.learn.arena import append_section
        body = [f"### Value head fitted — {a.name}", "", "```", *lines, "```", ""]
        append_section(ROOT / "docs" / "learning.md", "\n".join(body))
        print("appended a section to docs/learning.md")
    return 0


# ==================================================================== sweep
def cmd_sweep(a) -> int:
    """Every width on the *same* by-game split, selected on held-out Brier and nothing else."""
    import numpy as np

    def log(msg=""):
        print(msg, flush=True)

    X, y, game, ply, heads = load_matrix(a.data, log=log)
    if a.frac < 1.0:                      # a sweep on a fixed subsample of GAMES, not of rows
        ids = np.unique(game)
        rs = np.random.RandomState(a.seed ^ 0x5EED)
        keep = set(ids[rs.permutation(len(ids))[:int(len(ids) * a.frac)]].tolist())
        sel = np.fromiter((int(g) in keep for g in game), dtype=bool, count=len(game))
        X, y, game = X[sel], y[sel], game[sel]
        log(f"  sweep subsample: {len(y):,} rows over {len(keep):,} games ({a.frac:.0%})")
    mask, ng_tr, ng_ho = split_by_game(game, a.holdout, a.seed)
    log(f"  split by game: {int(mask.sum()):,} train / {int((~mask).sum()):,} held out")

    costs = {r["hidden"]: r for r in bench([int(w) for w in a.widths.split(",")], 120)}
    rows = []
    for h in [int(w) for w in a.widths.split(",")]:
        t = time.time()
        m, best_epoch, _hist = train_network(X, y, mask, hidden=h, l2=a.l2, epochs=a.epochs,
                                             patience=a.patience, seed=a.seed, log=lambda _m: None)
        met = _metrics(model_probs(m, X[~mask]), y[~mask])
        rows.append({"hidden": h, "brier": met["brier"], "log_loss": met["log_loss"],
                     "accuracy": met["accuracy"], "best_epoch": best_epoch,
                     "forward_us": costs[h]["forward_us"], "params": costs[h]["params"],
                     "seconds": round(time.time() - t, 1)})
        r = rows[-1]
        log(f"  hidden {h:>3}: held-out Brier {r['brier']:.5f}  log-loss {r['log_loss']:.5f}  "
            f"acc {r['accuracy']:.4f}  best epoch {best_epoch}  {r['forward_us']:.0f} us  "
            f"{r['seconds']}s")
    best = min(r["brier"] for r in rows)
    pick = min((r for r in rows if r["brier"] <= best * 1.01 and r["forward_us"] <= a.max_us),
               key=lambda r: r["hidden"])
    log(f"\nbest held-out Brier {best:.5f}; smallest width within 1% of it and under "
        f"{a.max_us:.0f} us: hidden={pick['hidden']}")
    Path(a.out).write_text(json.dumps({"rows": rows, "pick": pick["hidden"], "frac": a.frac,
                                       "utc": _now()}, indent=1), encoding="utf-8")
    log(f"wrote {a.out}")
    return 0


# ==================================================================== learning curve
def cmd_curve(a) -> int:
    """Held-out Brier against how much training data there is, on a **fixed** held-out set.

    The data-volume diagnosis, pre-registered: a curve still falling at 100% means more games would
    help; a curve flat from a quarter of the data onward means they would not, and the ceiling is
    somewhere else. Only the training side is subsampled, and it is subsampled by game.
    """
    import numpy as np

    def log(msg=""):
        print(msg, flush=True)

    X, y, game, _ply, heads = load_matrix(a.data, log=log)
    mask, ng_tr, ng_ho = split_by_game(game, a.holdout, a.seed)
    log(f"  fixed held-out: {int((~mask).sum()):,} rows over {ng_ho:,} games")
    train_ids = np.unique(game[mask])
    rs = np.random.RandomState(a.seed ^ 0xC0FFEE)
    order = rs.permutation(len(train_ids))
    rows = []
    for frac in [float(f) for f in a.fracs.split(",")]:
        keep = set(train_ids[order[:max(1, int(len(train_ids) * frac))]].tolist())
        sub = mask & np.fromiter((int(g) in keep for g in game), dtype=bool, count=len(game))
        use = sub | (~mask)                       # the model sees this subset plus the same val set
        m, best_epoch, _h = train_network(X[use], y[use], sub[use], hidden=a.hidden, l2=a.l2,
                                          epochs=a.epochs, patience=a.patience, seed=a.seed,
                                          log=lambda _m: None)
        met = _metrics(model_probs(m, X[~mask]), y[~mask])
        rows.append({"frac": frac, "train_games": len(keep), "train_rows": int(sub.sum()),
                     "brier": met["brier"], "log_loss": met["log_loss"],
                     "accuracy": met["accuracy"], "best_epoch": best_epoch})
        r = rows[-1]
        log(f"  {frac:>5.0%} of training games ({r['train_games']:>6,} games, "
            f"{r['train_rows']:>9,} rows): held-out Brier {r['brier']:.5f}  acc {r['accuracy']:.4f}")
    Path(a.out).write_text(json.dumps({"rows": rows, "hidden": a.hidden, "utc": _now()}, indent=1),
                           encoding="utf-8")
    log(f"wrote {a.out}")
    return 0


# ==================================================================== diagnose
def cmd_diagnose(a) -> int:
    """Does the learned value merely reproduce the teacher's ranking?

    Plays ``--games`` fresh games and, at every real decision, scores the *same* previews twice —
    once with ``heuristic.evaluate``, once with ``ValueModel.raw`` — and compares the two argmaxes.
    The previews are built with one local generator so both scorers see identical clones; this is
    the comparison the agents themselves make, minus the tie-break noise.

    Agreement near 100% is the diagnosis the plan pre-registered: a one-ply greedy agent on a value
    that ranks moves the way the teacher did cannot outplay the teacher, and no extra data or width
    changes that. It also prints the spread of ``raw`` across the options of a decision, which is
    what ``NeuralAgent.noise`` has to stay well under.
    """
    from cptcg.agents.base import make_agent
    from cptcg.agents.heuristic import _equiv_key, evaluate as heval
    from cptcg.agents.neural import WIN, NeuralAgent
    from cptcg.cards.registry import load_default
    from cptcg.core.engine import apply, legal_actions, new_game
    from cptcg.core.rng import Pcg32
    from cptcg.learn import decks as D
    from cptcg.learn.features import features
    from cptcg.learn.model import load_weights

    reg = load_default()
    model = load_weights(a.weights)
    print(f"weights: {a.weights}  hidden={model.hidden}  "
          f"run={model.header.get('run', {}).get('name')}")

    agree = total = 0
    spreads = []
    hspreads = []
    by_kind: dict[str, list[int]] = {}
    for gi in range(a.games):
        d0, d1 = D.sample_pair(reg, Pcg32((a.seed ^ (gi * 0x9E3779B1)) & 0xFFFFFFFFFFFFFFFF,
                                          seq=909))
        gs = (a.seed * 1000003 + gi) & 0x7FFFFFFF
        ags = [make_agent(a.driver, gs * 2 + p) for p in (0, 1)]
        for p, ag in enumerate(ags):
            ag.new_game(gs, p)
        s = new_game(reg, (d0, d1), gs, DEFAULT_CONFIG)
        probe = NeuralAgent(0)
        probe._model = model
        guard = 0
        while not s.over and guard < 4000:
            guard += 1
            legal_actions(s)
            ch = s.pending
            me = ch.player
            if len(ch.options) > 1 and ch.kind.name not in ("ORDER", "MULLIGAN", "GIG_DIE"):
                probe.me = me
                hs, ns, seen = [], [], set()
                rng = Pcg32(gs * 7919 + guard, seq=3)
                for i in range(len(ch.options)):
                    key = _equiv_key(s, ch.options[i])
                    if key in seen:
                        continue
                    seen.add(key)
                    c = s.clone()
                    c.rng = Pcg32(rng.next_u32(), seq=3)
                    apply(c, i)
                    probe._resolve(c, 1)
                    hs.append(heval(c, me) if not c.over else
                              (10_000.0 if c.winner == me else -10_000.0))
                    ns.append(WIN if c.over and c.winner == me else
                              -WIN if c.over else model.raw(features(c, me)))
                if len(hs) > 1:
                    total += 1
                    same = max(range(len(hs)), key=hs.__getitem__) == \
                        max(range(len(ns)), key=ns.__getitem__)
                    agree += same
                    finite = [v for v in ns if abs(v) < WIN / 2]
                    if len(finite) > 1:
                        spreads.append(max(finite) - min(finite))
                    fh = [v for v in hs if abs(v) < 9_000.0]
                    if len(fh) > 1:
                        hspreads.append(max(fh) - min(fh))
                    k = by_kind.setdefault(ch.kind.name, [0, 0])
                    k[0] += same
                    k[1] += 1
            apply(s, ags[me].act(s, ch))
    spreads.sort()
    hspreads.sort()

    def q(xs, f):
        return xs[min(len(xs) - 1, int(len(xs) * f))] if xs else float("nan")

    print(f"\nargmax agreement with the frozen heuristic over {total:,} multi-option decisions "
          f"in {a.games} {a.driver} games: {agree / max(1, total):.1%}")
    for kind, (k, n) in sorted(by_kind.items(), key=lambda kv: -kv[1][1]):
        print(f"  {kind:<12} {k:>7,}/{n:<7,} {k / n:.1%}")
    print(f"\nspread of the learned logit across a decision's options "
          f"(n={len(spreads):,}): median {q(spreads, 0.5):.4f}, "
          f"10th pct {q(spreads, 0.1):.4f}, 1st pct {q(spreads, 0.01):.5f}")
    print(f"spread of evaluate() across the same decisions: median {q(hspreads, 0.5):.3f}, "
          f"10th pct {q(hspreads, 0.1):.3f}, 1st pct {q(hspreads, 0.01):.4f}")
    print(f"the heuristic's own tie-break noise is up to 0.0999, i.e. "
          f"{0.0999 / max(1e-9, q(hspreads, 0.5)):.2%} of its median spread; the same ratio for "
          f"the learned logit would be a NeuralAgent.noise of "
          f"{0.0999 / max(1e-9, q(hspreads, 0.5)) * q(spreads, 0.5) / 999:.2e}")
    return 0


# ==================================================================== cli
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("bench", help="forward-pass cost by hidden width")
    p.add_argument("--widths", default="8,16,24,32,48,64,96,128")
    p.add_argument("--reps", type=int, default=300)
    p.add_argument("--markdown", action="store_true")
    p.set_defaults(fn=cmd_bench)

    p = sub.add_parser("demo", help="a few real games in the harvest's format")
    p.add_argument("--out", required=True)
    p.add_argument("-n", type=int, default=200)
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(fn=cmd_demo)

    for name, fn in (("fit", cmd_fit), ("sweep", cmd_sweep)):
        p = sub.add_parser(name, help="fit the value head" if name == "fit" else
                           "held-out Brier against hidden width")
        p.add_argument("data", nargs="+", help="example matrices from tools/harvest.py examples")
        p.add_argument("--l2", type=float, default=1e-4)
        p.add_argument("--holdout", type=float, default=0.2)
        p.add_argument("--seed", type=int, default=0)
        if name == "fit":
            p.add_argument("--out", default=str(ROOT / "src/cptcg/agents/weights.json"))
            p.add_argument("--name", default="bootstrap")
            p.add_argument("--hidden", type=int, default=32)
            p.add_argument("--epochs", type=int, default=400)
            p.add_argument("--patience", type=int, default=25)
            p.add_argument("--logistic-epochs", type=int, default=30)
            p.add_argument("--probe-games", type=int, default=400)
            p.add_argument("--mix", default=None)
            p.add_argument("--agents", default="heuristic,random")
            p.add_argument("--slim-history", action="store_true")
            p.add_argument("--append-docs", action="store_true")
        else:
            p.add_argument("--out", default=str(ROOT / "out" / "sweep.json"))
            p.add_argument("--widths", default="8,16,24,32,48,64")
            p.add_argument("--epochs", type=int, default=60)
            p.add_argument("--patience", type=int, default=8)
            p.add_argument("--frac", type=float, default=1.0)
            p.add_argument("--max-us", type=float, default=150.0)
        p.set_defaults(fn=fn)

    p = sub.add_parser("curve", help="held-out Brier against training-set size")
    p.add_argument("data", nargs="+")
    p.add_argument("--out", default=str(ROOT / "out" / "curve.json"))
    p.add_argument("--fracs", default="0.1,0.25,0.5,1.0")
    p.add_argument("--hidden", type=int, default=16)
    p.add_argument("--l2", type=float, default=1e-4)
    p.add_argument("--holdout", type=float, default=0.2)
    p.add_argument("--epochs", type=int, default=120)
    p.add_argument("--patience", type=int, default=12)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(fn=cmd_curve)

    p = sub.add_parser("diagnose", help="argmax agreement with the teacher policy")
    p.add_argument("--weights", default=str(ROOT / "src/cptcg/agents/weights.json"))
    p.add_argument("--games", type=int, default=40)
    p.add_argument("--seed", type=int, default=99)
    p.add_argument("--driver", default="heuristic")
    p.set_defaults(fn=cmd_diagnose)

    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    raise SystemExit(main())
