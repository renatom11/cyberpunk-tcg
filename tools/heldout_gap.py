"""Experiment 2 of the post-KT1 signal diagnostic (pre-registered in docs/stage0_decisions.md).

    python tools/heldout_gap.py --cards-seen A.npz --cards-train B.npz --h114-seen C.npz --h114-train D.npz \\
        [--holdout 0.2 --seed 0 --resamples 1000] --out out/s2/heldout_gap.json

Inputs are the per-row squared errors written by ``fit_cards.py eval --errors`` (card model) and
``fit_cards.py eval114 --errors`` (114 head): on set A (rows of games holding a held-out card, where
that card is visible or offered) and on the whole training subset, from which set B — the
subset's own by-game holdout, the same split the fits used — is selected here.

For each head, gap = Brier(A) - Brier(B). The registered quantity is gap(cards) - gap(114), with a
95% interval from resampling games (A's games and B's games independently, the same draws for both
heads, so the comparison is paired). "The embedding is doing work" if the interval lies wholly
above zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from fit_cards import split_by_game  # noqa: E402


def _per_game(path: str, games: np.ndarray | None = None) -> dict:
    z = np.load(path)
    se, g = z["se"].astype(np.float64), z["game"]
    if games is not None:
        m = np.isin(g, games)
        se, g = se[m], g[m]
    out: dict = {}
    for gi in np.unique(g):
        s = se[g == gi]
        out[int(gi)] = (float(s.sum()), int(len(s)))
    return out


def _brier(per: dict, games) -> float:
    tot = sum(per[g][0] for g in games)
    n = sum(per[g][1] for g in games)
    return tot / max(n, 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cards-seen", required=True)
    ap.add_argument("--cards-train", required=True)
    ap.add_argument("--h114-seen", required=True)
    ap.add_argument("--h114-train", required=True)
    ap.add_argument("--holdout", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--resamples", type=int, default=1000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    train_games = np.load(a.cards_train)["game"]
    _, hold_idx = split_by_game(train_games, a.holdout, a.seed)
    hold_games = np.unique(train_games[hold_idx])
    ca, cb = _per_game(a.cards_seen), _per_game(a.cards_train, hold_games)
    ha, hb = _per_game(a.h114_seen), _per_game(a.h114_train, hold_games)
    ga, gb = sorted(set(ca) & set(ha)), sorted(set(cb) & set(hb))

    def diff(A, B):
        return (_brier(ca, A) - _brier(cb, B)) - (_brier(ha, A) - _brier(hb, B))

    point = diff(ga, gb)
    rng = np.random.default_rng(20260925)
    draws = []
    for _ in range(a.resamples):
        A = rng.choice(ga, size=len(ga), replace=True)
        B = rng.choice(gb, size=len(gb), replace=True)
        draws.append(diff(A, B))
    lo, hi = np.percentile(draws, [2.5, 97.5])
    out = {"set_a_games": len(ga), "set_b_games": len(gb),
           "cards": {"brier_a": _brier(ca, ga), "brier_b": _brier(cb, gb), "gap": _brier(ca, ga) - _brier(cb, gb)},
           "h114": {"brier_a": _brier(ha, ga), "brier_b": _brier(hb, gb), "gap": _brier(ha, ga) - _brier(hb, gb)},
           "gap_difference": point, "ci95": [float(lo), float(hi)], "resamples": a.resamples,
           "embedding_doing_work": bool(lo > 0)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
