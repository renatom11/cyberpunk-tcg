"""The evolution strategy's arithmetic, and proof it can climb a hill at this problem's noise level.

None of this plays a game. That is the point: the optimiser takes fitness as *numbers*, so it can
be proven on a synthetic objective whose optimum is known, in seconds, before any compute is spent
on it. When the real run fails to improve — and it may — this is what separates "the optimiser is
broken" from "there is no hill here".
"""
import math
import random

import pytest

from cptcg.learn import evolve


# ---------------------------------------------------------------- the pieces
def test_centred_ranks_are_centred_and_ordered():
    r = evolve.centred_ranks([1.0, 2.0, 3.0, 4.0])
    assert pytest.approx(sum(r), abs=1e-12) == 0.0
    assert r == sorted(r)
    assert r[0] == -0.5 and r[-1] == 0.5


def test_all_ties_produce_no_step_at_all():
    """Sixteen pairs that could not be separated must not move the weights. Without this a run of
    dead-even results would still wander, and wandering looks exactly like progress for a while."""
    ranks = evolve.centred_ranks([0.5] * 8)
    assert ranks == [0.0] * 8
    theta = [1.0, 2.0, 3.0]
    eps = evolve.perturbations(8, 3, seed=3)
    assert evolve.step(theta, eps, [0.5] * 8) == theta


def test_the_step_moves_toward_the_better_half_of_a_pair():
    """A pair's score is the win rate of ``theta + sigma*e`` against its own mirror. Above 0.5 the
    plus direction won, so theta must move along +e; below 0.5, against it. A sign error here would
    optimise the wrong way and look like a flat search."""
    theta = [0.0, 0.0]
    eps = [[1.0, 0.0], [0.0, 1.0]]
    up = evolve.step(theta, eps, [1.0, 0.0])          # first pair's + side won
    assert up[0] > 0 and up[1] < 0
    down = evolve.step(theta, eps, [0.0, 1.0])        # and the other way round
    assert down[0] < 0 and down[1] > 0


def test_perturbations_are_reproducible_from_their_seed():
    """The ledger stores seeds, not vectors; a run has to be reconstructible from it."""
    assert evolve.perturbations(4, 50, seed=11) == evolve.perturbations(4, 50, seed=11)
    assert evolve.perturbations(4, 50, seed=11) != evolve.perturbations(4, 50, seed=12)


def test_flatten_round_trips_a_model():
    w = {"w1": [[1.0, 2.0], [3.0, 4.0]], "b1": [5.0, 6.0], "w2": [7.0, 8.0], "b2": 9.0, "x": "kept"}
    vec, shape = evolve.flatten(w)
    assert vec == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    back = evolve.unflatten([v * 2 for v in vec], shape, w)
    assert back["w1"] == [[2.0, 4.0], [6.0, 8.0]] and back["b2"] == 18.0
    assert back["x"] == "kept", "non-weight keys must survive"


# ---------------------------------------------------------------- the schedule
def test_sigma_halves_only_after_patience_runs_out(tmp_path):
    r = evolve.Run(sigma=0.02)
    assert "new best" in r.record_anchor(0.55)
    assert r.sigma == 0.02
    for _ in range(evolve.PATIENCE - 1):
        r.record_anchor(0.50)
        assert r.sigma == 0.02
    assert "sigma ->" in r.record_anchor(0.50)
    assert r.sigma == 0.01
    assert r.best_anchor == 0.55, "the champion is never lost to a bad check"


def test_a_run_round_trips_through_its_ledger(tmp_path):
    r = evolve.Run(sigma=0.01, alpha=1e-3, best_anchor=0.6)
    r.iterations.append(evolve.Iteration(n=0, seed=5, sigma=0.01, alpha=1e-3,
                                         pair_scores=[0.5, 0.6], anchor=0.6, anchor_games=200))
    p = tmp_path / "run.json"
    r.save(p)
    back = evolve.Run.load(p)
    assert back.sigma == 0.01 and back.best_anchor == 0.6
    assert back.iterations[0].pair_scores == [0.5, 0.6]
    assert evolve.Run.load(tmp_path / "absent.json").iterations == []


# ---------------------------------------------------------------- the whole optimiser
def _climb(signal, games, *, dim=400, pairs=16, iters=40, sigma=0.02, alpha=evolve.ALPHA, seed=7):
    """Run the ES on -||theta - target||^2, seen only through noisy pair win rates."""
    rnd = random.Random(seed)
    target = [rnd.gauss(0, 0.1) for _ in range(dim)]
    theta = [0.0] * dim
    f = lambda t: -sum((a - b) ** 2 for a, b in zip(t, target))
    start = f(theta)
    for it in range(iters):
        eps = evolve.perturbations(pairs, dim, seed=1000 + it)
        scores = []
        for e in eps:
            plus = [t + sigma * x for t, x in zip(theta, e)]
            minus = [t - sigma * x for t, x in zip(theta, e)]
            p = min(0.99, max(0.01, 0.5 + signal * (f(plus) - f(minus))))
            scores.append(sum(1 for _ in range(games) if rnd.random() < p) / games)
        theta = evolve.step(theta, eps, scores, sigma=sigma, alpha=alpha)
    return (f(theta) - start) / abs(start) * 100


def test_the_optimiser_climbs_a_known_hill():
    assert _climb(signal=2.0, games=10_000) > 5.0


def test_it_still_climbs_at_this_problem_s_measured_noise():
    """24 games give a standard error of 10.2 points on a pair's win rate, and the real advantage
    between two neighbouring weight vectors is small. This is the question the whole design turns
    on, and the answer has to come from here rather than from a night of games."""
    gains = [_climb(signal=2.0, games=24, seed=7 + k) for k in range(3)]
    assert min(gains) > 0.0, f"did not climb through realistic noise: {gains}"
    assert sum(gains) / 3 > 5.0, f"climbed, but not usefully: {gains}"


def test_too_large_a_step_walks_away_from_the_optimum():
    """The regression test for the bug that shipped in the first draft: alpha=0.03 made the
    objective twenty-five times worse with no noise at all. If a future tweak makes this pass
    without a divergence, the step scaling has changed and ALPHA needs re-deriving."""
    assert _climb(signal=2.0, games=10_000, alpha=0.03) < -100.0
