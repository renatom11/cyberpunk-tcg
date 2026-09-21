"""Kill test 2 (Stage 0): is the deck metagame non-transitive under a given agent?

    python tools/meta_report.py TOURNEY.json [--draws 1000] [--seed 1] [--out J]

Reads a ``cptcg tourney`` JSON (its ``cells`` carry wins and games per ordered pair) and reports:

* the Bradley–Terry fit's residual RMS — how far the observed pairwise rates sit from the rates a
  single strength per deck predicts (``sim.stats.bradley_terry``, ``bt_predicted``);
* the same statistic under a **transitive null**: each cell's wins redrawn as a binomial at the
  fitted rate, the fit re-run, ``--draws`` times. The fraction of null draws whose RMS reaches the
  observed one is the p-value; the null's mean and 95th percentile are printed beside the
  observed value so the reader sees the size, not only the verdict;
* the Nash support: the decks a fictitious-play equilibrium of the pairwise payoff matrix puts
  weight on (``sim.stats.nash_fictitious_play``), with a floor of 1% weight to count.

Part 6's criterion, verbatim: non-transitive if the residual RMS is above the null (p < 0.05
here, since "above the null" needs a threshold) and the Nash support holds at least 3 decks.
numpy is used only for the draws; the fit is the package's own.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.sim.stats import bradley_terry, bt_predicted, nash_fictitious_play  # noqa: E402


def wins_matrix(data: dict) -> tuple[np.ndarray, np.ndarray]:
    n = len(data["decks"])
    w = np.zeros((n, n), dtype=np.int64)
    g = np.zeros((n, n), dtype=np.int64)
    for c in data["cells"]:
        i, j = c["i"], c["j"]
        w[i, j] += c["wins_i"]
        w[j, i] += c["n"] - c["wins_i"]
        g[i, j] += c["n"]
        g[j, i] += c["n"]
    return w, g


def residual_rms(w: np.ndarray, g: np.ndarray) -> float:
    n = w.shape[0]
    pi = bradley_terry(w.tolist())
    pred = bt_predicted(pi)
    tot = 0.0
    k = 0
    for i in range(n):
        for j in range(n):
            if i != j and g[i, j]:
                r = w[i, j] / g[i, j] - pred[i][j]
                tot += r * r
                k += 1
    return (tot / k) ** 0.5 if k else 0.0


def null_draws(w: np.ndarray, g: np.ndarray, draws: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = w.shape[0]
    pi = bradley_terry(w.tolist())
    pred = np.array(bt_predicted(pi))
    out = np.zeros(draws)
    for d in range(draws):
        ww = np.zeros_like(w)
        for i in range(n):
            for j in range(i + 1, n):
                if g[i, j]:
                    k = rng.binomial(int(g[i, j]), float(pred[i, j]))
                    ww[i, j] = k
                    ww[j, i] = g[i, j] - k
        out[d] = residual_rms(ww, g)
    return out


def nash_support(w: np.ndarray, g: np.ndarray, floor: float = 0.01) -> tuple[list[float], list[int]]:
    n = w.shape[0]
    pay = [[(w[i, j] / g[i, j] - 0.5) if g[i, j] else 0.0 for j in range(n)] for i in range(n)]
    x = nash_fictitious_play(pay)
    return x, [i for i, v in enumerate(x) if v >= floor]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tourney")
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--support-floor", type=float, default=0.01)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    data = json.loads(Path(a.tourney).read_text(encoding="utf-8"))
    w, g = wins_matrix(data)
    obs = residual_rms(w, g)
    null = null_draws(w, g, a.draws, a.seed)
    p = float((null >= obs).mean())
    x, support = nash_support(w, g, a.support_floor)
    names = [d["name"] for d in data["decks"]]
    out = {"tourney": a.tourney, "agent": data.get("agent"), "decks": len(names), "games": int(g.sum() // 2),
           "residual_rms": obs, "null_mean": float(null.mean()), "null_p95": float(np.percentile(null, 95)),
           "null_max": float(null.max()), "p_value": p, "draws": a.draws,
           "nash": {names[i]: round(float(x[i]), 4) for i in range(len(names)) if x[i] >= a.support_floor},
           "nash_support": len(support),
           "non_transitive": bool(p < 0.05 and len(support) >= 3)}
    print(json.dumps(out, indent=1))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
