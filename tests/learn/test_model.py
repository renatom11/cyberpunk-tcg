"""The value head: does it compute what we think, and does it refuse what it should?

The refusal tests matter as much as the arithmetic one. A weights file fitted to a different
feature vector, or under a different ruleset, would still load and still return numbers — plausible
ones — and every result downstream would be quietly wrong. So each of those is a loud failure.
"""

from __future__ import annotations

import json
import math

import pytest

from cptcg.core.config import DEFAULT_CONFIG
from cptcg.learn import model as M
from cptcg.learn.features import FEATURE_NAMES, NFEAT


def _toy(hidden: int = 3, seed: int = 1) -> M.ValueModel:
    import random

    rng = random.Random(seed)
    return M.ValueModel(
        hidden=hidden,
        w1=tuple(tuple(rng.uniform(-0.5, 0.5) for _ in range(NFEAT)) for _ in range(hidden)),
        b1=tuple(rng.uniform(-0.2, 0.2) for _ in range(hidden)),
        w2=tuple(rng.uniform(-0.8, 0.8) for _ in range(hidden)),
        b2=0.15,
    )


def _x(seed: int = 5) -> tuple[float, ...]:
    import random

    rng = random.Random(seed)
    return tuple(rng.uniform(-1.0, 1.0) for _ in range(NFEAT))


def test_forward_matches_the_definition_written_out_longhand():
    m, x = _toy(), _x()
    out = m.b2
    for j in range(m.hidden):
        z = sum(m.w1[j][k] * x[k] for k in range(NFEAT)) + m.b1[j]
        out += m.w2[j] * math.tanh(z)
    assert m.forward(x) == pytest.approx(1.0 / (1.0 + math.exp(-out)), rel=1e-12)


def test_both_dot_product_implementations_agree():
    """math.sumprod on 3.12+, map/mul below it. The two must never disagree."""
    from operator import mul

    m, x = _toy(), _x()
    fast = m.forward(x)
    old = M._SUMPROD
    try:
        M._SUMPROD = lambda a, b: sum(map(mul, a, b))
        assert m.forward(x) == pytest.approx(fast, rel=1e-12)
    finally:
        M._SUMPROD = old


def test_the_logistic_does_not_overflow_at_the_extremes():
    m = M.ValueModel(hidden=1, w1=((1e3,) + (0.0,) * (NFEAT - 1),), b1=(0.0,), w2=(1e4,), b2=0.0)
    assert 0.0 < m.forward((1.0,) + (0.0,) * (NFEAT - 1)) <= 1.0
    assert 0.0 <= m.forward((-1.0,) + (0.0,) * (NFEAT - 1)) < 1.0


def test_an_untrained_model_says_it_does_not_know():
    assert M.zeros().forward(_x()) == pytest.approx(0.5)


def test_weights_round_trip_without_losing_precision(tmp_path):
    m = _toy(hidden=4)
    p = m.save(tmp_path / "w.json")
    back = M.ValueModel.load(p)
    x = _x(9)
    assert back.forward(x) == pytest.approx(m.forward(x), rel=1e-12)
    assert back.hidden == m.hidden and back.b2 == m.b2


def test_weights_fitted_to_a_different_feature_vector_are_refused(tmp_path):
    d = _toy().to_json()
    d["features"] = list(FEATURE_NAMES)
    d["features"][7] = "a_feature_that_no_longer_exists"
    p = tmp_path / "w.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError) as e:
        M.ValueModel.load(p)
    # The message has to name the offender, or nobody can fix it.
    assert "feature 7" in str(e.value) and "a_feature_that_no_longer_exists" in str(e.value)


def test_a_shorter_feature_list_is_refused_by_length(tmp_path):
    d = _toy().to_json()
    d["features"] = list(FEATURE_NAMES)[:-3]
    p = tmp_path / "w.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match=f"{NFEAT}"):
        M.ValueModel.load(p)


def test_weights_from_another_ruleset_are_refused(tmp_path):
    d = _toy().to_json()
    d["rules"] = "0000000000000000"
    p = tmp_path / "w.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="ruleset"):
        M.ValueModel.load(p)
    # ...and can still be read deliberately, which is what a refit needs.
    assert M.ValueModel.load(p, rules=None).hidden == 3


def test_a_wrong_shape_is_refused_rather_than_truncated(tmp_path):
    d = _toy(hidden=3).to_json()
    d["w1"] = d["w1"][:2]
    p = tmp_path / "w.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="hidden"):
        M.ValueModel.load(p)


def test_an_unknown_activation_is_refused(tmp_path):
    d = _toy().to_json()
    d["activation"] = "relu"
    p = tmp_path / "w.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="activation"):
        M.ValueModel.load(p)


def test_the_saved_ruleset_is_the_one_this_build_plays():
    assert _toy().to_json()["rules"] == DEFAULT_CONFIG.digest()


def test_value_scores_a_real_position(pool):
    from cptcg.core.engine import new_game
    from cptcg.deck.decklist import Decklist
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    decks = (Decklist.load(root / "data/decks/the_heist.json"),
             Decklist.load(root / "data/decks/embracing_power.json"))
    s = new_game(pool, decks, 3)
    v = _toy().value(s, 0)
    assert 0.0 <= v <= 1.0


def test_python_inference_matches_the_numpy_training_maths():
    """The shipped forward pass and the one the trainer optimises must be the same function.

    A silent disagreement here would mean the agent we ship is not the model we measured.
    """
    np = pytest.importorskip("numpy")
    m, x = _toy(hidden=6), _x(11)
    W1 = np.array(m.w1)
    H = np.tanh(W1 @ np.array(x) + np.array(m.b1))
    o = float(H @ np.array(m.w2) + m.b2)
    assert m.forward(x) == pytest.approx(1.0 / (1.0 + np.exp(-o)), rel=1e-12)
