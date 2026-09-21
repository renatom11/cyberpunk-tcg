"""Kill test 2's instrument: residual RMS against a transitive null, and the Nash support."""

import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import meta_report as MR  # noqa: E402


def _data(rates, n=40):
    k = len(rates)
    cells = []
    for i in range(k):
        for j in range(i + 1, k):
            cells.append({"i": i, "j": j, "wins_i": int(round(rates[i][j] * n)), "n": n})
    return {"decks": [{"name": f"d{i}"} for i in range(k)], "cells": cells}


def test_a_transitive_field_is_inside_the_null_and_has_a_one_deck_support():
    pi = [4.0, 2.0, 1.0, 0.5]
    rates = [[pi[i] / (pi[i] + pi[j]) for j in range(4)] for i in range(4)]
    d = _data(rates)
    w, g = MR.wins_matrix(d)
    obs = MR.residual_rms(w, g)
    null = MR.null_draws(w, g, 200, 1)
    assert (null >= obs).mean() > 0.05
    x, support = MR.nash_support(w, g)
    assert support == [0]


def test_rock_paper_scissors_is_outside_the_null_with_a_three_deck_support():
    rates = [[0.5, 0.9, 0.1], [0.1, 0.5, 0.9], [0.9, 0.1, 0.5]]
    d = _data(rates, n=60)
    w, g = MR.wins_matrix(d)
    obs = MR.residual_rms(w, g)
    null = MR.null_draws(w, g, 200, 1)
    assert (null >= obs).mean() < 0.05
    x, support = MR.nash_support(w, g)
    assert len(support) == 3
    assert all(abs(v - 1 / 3) < 0.05 for v in x)
