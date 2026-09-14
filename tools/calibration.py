"""Is the value head's preference for attacking now a systematic bias, or one hard position?

``tools/diagnose_features.py`` found that on ``two-pieces-of-gear`` the head ranks the winning move
last of four, preferring ``Attack`` (+3.9026) to ``CallLegend`` (+3.0422) — a 0.86-logit preference
with the sign wrong. But the delayed suite is positions hand-picked *because* a greedy agent
fails them, so finding greedy failure there is close to circular.

This asks the same question of millions of real positions, using data already on disk: for rows
where it is my turn, split by whether I have already committed power this turn, and compare what
the model *predicted* against what actually happened. A model that is too greedy will over-predict
the bucket where the attack is already banked and under-predict the one where it is still to come.

The control comes first and the report leads with it. ``fit_eval`` recorded this model's holdout
ECE when it was fitted; if this tool cannot reproduce that number on the same split, it is wrong and
nothing it says about sub-buckets means anything. Both the split and the calibration function are
imported from ``fit_eval`` rather than reimplemented, so "reproduce" means reproduce.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np                                              # noqa: E402

from cptcg.learn.features import FEATURE_NAMES                  # noqa: E402
from cptcg.learn.model import load_weights                      # noqa: E402
from fit_eval import calibration, split_by_game                 # noqa: E402


def load(paths: list[str]):
    """Stack the example matrices: features, label, game id."""
    X, Y, G, base = [], [], [], 0
    for p in paths:
        head = json.loads(Path(p).with_suffix(".json").read_text(encoding="utf-8"))
        nf, cols, rows = head["nfeat"], head["cols"], head["rows"]
        m = np.fromfile(p, dtype="<f4").reshape(rows, cols)
        X.append(m[:, :nf])
        Y.append(m[:, nf])
        G.append(m[:, nf + 1] + base)          # keep game ids distinct across files
        base += float(m[:, nf + 1].max()) + 1
    return np.concatenate(X), np.concatenate(Y), np.concatenate(G)


def predict(model, X) -> np.ndarray:
    """The model's win probability, vectorised. Matches ValueModel.raw then a logistic."""
    w1 = np.array(model.w1); b1 = np.array(model.b1)
    w2 = np.array(model.w2); b2 = model.b2
    return 1.0 / (1.0 + np.exp(-(np.tanh(X @ w1.T + b1) @ w2 + b2)))


def report(label, p, y):
    n = len(y)
    if n < 500:
        print(f"  {label:<34} n={n:<8} too few rows to say anything")
        return None
    pred, act = float(p.mean()), float(y.mean())
    se = math.sqrt(max(act * (1 - act), 1e-9) / n)
    gap = pred - act
    flag = "" if abs(gap) < 1.96 * se else ("  OVER-predicted" if gap > 0 else "  UNDER-predicted")
    print(f"  {label:<34} n={n:<8} predicted {pred:.4f}  actual {act:.4f}  "
          f"gap {gap:+.4f} +/- {1.96*se:.4f}{flag}")
    return gap


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--weights", default="out/learn/gen-001/weights.json")
    ap.add_argument("--data", nargs="*", default=None,
                    help="example matrices; default is exactly what gen-1 was fitted on")
    ap.add_argument("--holdout", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)

    paths = a.data or (sorted(glob.glob("out/learn/seed/*.f32"))
                       + sorted(glob.glob("out/learn/gen-001/ex-*.f32")))
    X, Y, G = load(paths)
    model = load_weights(a.weights)
    P = predict(model, X)
    mask, _, _ = split_by_game(G, a.holdout, a.seed)
    ho = ~mask

    recorded = json.loads(Path(a.weights).read_text(encoding="utf-8"))["train"]
    print(f"{len(Y):,} rows from {len(paths)} files; holdout {int(ho.sum()):,} rows\n")
    print("CONTROL — this must reproduce what fit_eval recorded, or nothing below is trustworthy")
    _rows, got, _worst = calibration(P[ho], Y[ho])   # fit_eval computes ECE itself
    print(f"  holdout ECE      this tool {got:.5f}   recorded {recorded['ece']:.5f}   "
          f"difference {abs(got - recorded['ece']):.5f}")
    got_brier = float(((P[ho] - Y[ho]) ** 2).mean())
    rec_brier = recorded["holdout"]["network"]["brier"]
    print(f"  holdout Brier    this tool {got_brier:.5f}   recorded {rec_brier:.5f}   "
          f"difference {abs(got_brier - rec_brier):.5f}")
    if abs(got - recorded["ece"]) > 0.002 or abs(got_brier - rec_brier) > 0.002:
        print("\n  CONTROL FAILED — stopping. Fix the tool before reading anything into the splits.")
        return 1
    print("  control passed\n")

    i_turn = FEATURE_NAMES.index("my_turn")
    i_spent = FEATURE_NAMES.index("power_spent_me")
    i_t = FEATURE_NAMES.index("turn")
    mine = ho & (X[:, i_turn] > 0.5)
    fresh = mine & (X[:, i_spent] <= 0.0)
    spent = mine & (X[:, i_spent] > 0.0)

    print("THE QUESTION — on my own turn, is the head too fond of an attack already banked?")
    g_fresh = report("my turn, nothing spent yet", P[fresh], Y[fresh])
    g_spent = report("my turn, power already spent", P[spent], Y[spent])
    if g_fresh is not None and g_spent is not None:
        print(f"\n  A greedy bias predicts: 'nothing spent' UNDER-predicted (negative gap) and "
              f"'already spent' OVER-predicted (positive).")
        print(f"  observed: {g_fresh:+.4f} and {g_spent:+.4f}")

    print("\nSPLIT AGAIN BY GAME STAGE — a setup move is worth more with turns left to cash it in")
    early = X[:, i_t] <= float(np.median(X[ho][:, i_t]))
    for name, sel in (("early, nothing spent", fresh & early),
                      ("early, already spent", spent & early),
                      ("late,  nothing spent", fresh & ~early),
                      ("late,  already spent", spent & ~early)):
        report(name, P[sel], Y[sel])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
