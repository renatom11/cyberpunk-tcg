"""The policy trainer's grouping arithmetic, and that a fitted head is actually better than none.

The loss here is a cross-entropy *inside a decision*, not across the whole matrix, and that is the
part a loss curve would happily hide being wrong: a softmax over the wrong rows still goes down.
So the grouping is tested directly, and then a small end-to-end fit is asked to beat the uniform
head it started from — on held-out decisions, split by game.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import fit_policy  # noqa: E402

from cptcg.learn.policy import NAFEAT  # noqa: E402

np = pytest.importorskip("numpy")


def test_the_softmax_normalises_inside_each_decision_and_not_across_them():
    group = np.array([0, 0, 0, 1, 1])
    logits = np.array([1.0, 2.0, 3.0, 10.0, 10.0])
    p = fit_policy._group_softmax(logits, group)
    assert pytest.approx(p[:3].sum()) == 1.0
    assert pytest.approx(p[3:].sum()) == 1.0
    assert pytest.approx(p[3]) == pytest.approx(p[4])       # equal logits, equal share
    assert p[2] > p[1] > p[0]


def test_it_survives_logits_that_would_overflow_a_naive_exp():
    group = np.array([0, 0])
    p = fit_policy._group_softmax(np.array([1000.0, 999.0]), group)
    assert pytest.approx(p.sum()) == 1.0
    assert np.isfinite(p).all()


def test_the_softmax_does_not_care_what_order_the_rows_arrive_in():
    """Rows come off games interleaved; a grouping that assumes they are sorted is a silent bug."""
    group = np.array([1, 0, 1, 0, 2])
    logits = np.array([0.5, 2.0, 1.5, 1.0, 7.0])
    p = fit_policy._group_softmax(logits, group)
    for g in (0, 1, 2):
        assert pytest.approx(p[group == g].sum()) == 1.0


def test_agreement_counts_decisions_not_rows():
    group = np.array([0, 0, 1, 1, 1])
    target = np.array([0.9, 0.1, 0.2, 0.7, 0.1])
    same = np.array([0.8, 0.2, 0.1, 0.8, 0.1])
    other = np.array([0.1, 0.9, 0.1, 0.8, 0.1])
    assert fit_policy._agree(same, target, group) == 1.0
    assert fit_policy._agree(other, target, group) == 0.5    # one of two decisions


def test_the_split_is_by_game_so_one_decision_cannot_straddle_it():
    head = {"game": [0, 0, 0, 1, 1, 2, 2]}
    group = np.array([0, 0, 1, 2, 2, 3, 3])
    is_train = fit_policy._split(head, group, holdout=0.4)
    games = np.asarray(head["game"])
    for g in np.unique(games):
        assert len(set(is_train[games == g].tolist())) == 1, "a game landed on both sides"
    assert is_train.any() and (~is_train).any()


def _toy(rows_per_group=4, groups=400, seed=0):
    """A learnable toy: one feature decides the answer, the rest is noise."""
    rs = np.random.RandomState(seed)
    n = rows_per_group * groups
    X = rs.rand(n, NAFEAT)
    group = np.repeat(np.arange(groups), rows_per_group)
    logits = 6.0 * X[:, 0]
    y = fit_policy._group_softmax(logits, group)
    head = {"game": list(np.repeat(np.arange(groups // 4), rows_per_group * 4))}
    return head, group, y, X


def test_a_fitted_head_beats_the_uniform_one_it_started_from():
    head, group, y, X = _toy()
    is_train = fit_policy._split(head, group, holdout=0.25)
    parts, loss, agree = fit_policy.train(X, y, group, is_train, hidden=4, l2=1e-4,
                                          epochs=120, patience=20, seed=1, log=lambda *_: None)
    # what a head that knows nothing would score on the same held-out decisions
    ho = ~is_train
    flat = fit_policy._group_softmax(np.zeros(ho.sum()), group[ho])
    base = float(-(y[ho] * np.log(np.clip(flat, 1e-12, 1))).sum()
                 / max(1, len(np.unique(group[ho]))))
    assert loss < base
    assert agree > 0.5


def test_a_linear_head_fits_too_and_is_a_real_model():
    head, group, y, X = _toy(groups=200, seed=3)
    is_train = fit_policy._split(head, group, holdout=0.25)
    parts, loss, agree = fit_policy.train(X, y, group, is_train, hidden=0, l2=1e-4,
                                          epochs=120, patience=20, seed=1, log=lambda *_: None)
    W1, b1, w2, b2 = parts
    assert W1.shape == (1, NAFEAT)
    assert agree > 0.5
    # and it turns into a PolicyModel the engine can actually load
    m = fit_policy._model(parts, 0)
    assert m.hidden == 1 and len(m.w1[0]) == NAFEAT
