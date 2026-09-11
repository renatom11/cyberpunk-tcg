"""The value model: exact round-trip, refusal to load anything ambiguous, and numpy agreement.

The last one is the load-bearing test of this stage. Training happens in numpy in ``tools/`` and
inference happens in hand-written Python in ``src/cptcg`` — two implementations of the same
arithmetic, and nothing but a test keeps them the same arithmetic. Every refusal is checked for
*naming the offender*, because the failure this file exists to prevent is not a crash: it is a
model that loads, scores plausibly, and is not the model that was measured.
"""

import json
import math

import pytest

from cptcg.core.config import DEFAULT_CONFIG
from cptcg.learn import model as M
from cptcg.learn.features import FEATURE_NAMES, NFEAT, features
from cptcg.learn.model import FORMAT, ValueModel, load_weights

WEIGHTS = M.WEIGHTS_PATH


def make(hidden: int = 6, seed: int = 5) -> ValueModel:
    import random

    rng = random.Random(seed)
    return ValueModel(
        hidden=hidden,
        w1=tuple(tuple(rng.uniform(-0.8, 0.8) for _ in range(NFEAT)) for _ in range(hidden)),
        b1=tuple(rng.uniform(-0.3, 0.3) for _ in range(hidden)),
        w2=tuple(rng.uniform(-1.2, 1.2) for _ in range(hidden)),
        b2=rng.uniform(-0.5, 0.5),
        header={"run": {"name": "test"}})


def xs(n: int = 25, seed: int = 1):
    import random

    rng = random.Random(seed)
    return [[rng.uniform(-1.0, 1.0) for _ in range(NFEAT)] for _ in range(n)]


# ------------------------------------------------------------------ arithmetic
def test_forward_is_the_logistic_of_raw():
    m = make()
    for x in xs(8):
        assert m.forward(x) == M._logistic(m.raw(x))


def test_the_logistic_does_not_overflow_on_a_saturated_unit():
    """``exp(1000)`` raises. A saturated unit is a normal thing for a fitted model to produce, so
    it must not be an exception."""
    assert M._logistic(1e6) == 1.0
    assert M._logistic(-1e6) == 0.0
    assert M._logistic(0.0) == 0.5


def test_both_sumprod_implementations_agree(monkeypatch):
    """``math.sumprod`` exists from 3.12. The fallback is what actually runs on 3.11, so the file
    must be correct under either — and the two must not disagree in the last bits."""
    from operator import mul

    m = make()
    fallback = (lambda a, b: sum(map(mul, a, b)))
    base = [m.raw(x) for x in xs(6)]
    monkeypatch.setattr(M, "_SUMPROD", fallback)
    assert [m.raw(x) for x in xs(6)] == pytest.approx(base, rel=1e-12, abs=1e-12)
    monkeypatch.setattr(M, "_SUMPROD", getattr(math, "sumprod", fallback))
    assert [m.raw(x) for x in xs(6)] == pytest.approx(base, rel=1e-12, abs=1e-12)


def test_forward_agrees_with_a_numpy_reference():
    """The stdlib forward pass against the arithmetic the trainer used, to 1e-12 relative.

    If this drifts, every Brier number in ``docs/learning.md`` describes a different model from
    the one the agent runs.
    """
    np = pytest.importorskip("numpy")
    m = make(hidden=32, seed=9)
    W1 = np.array(m.w1, dtype=np.float64)
    B1 = np.array(m.b1, dtype=np.float64)
    W2 = np.array(m.w2, dtype=np.float64)
    X = np.array(xs(64, seed=4), dtype=np.float64)
    want = 1.0 / (1.0 + np.exp(-(np.tanh(X @ W1.T + B1) @ W2 + m.b2)))
    got = [m.forward(x) for x in X.tolist()]
    assert got == pytest.approx(want.tolist(), rel=1e-12, abs=1e-15)


def test_value_and_score_read_a_real_position(pool):
    from cptcg.core.engine import new_game
    from cptcg.core.rng import Pcg32
    from cptcg.learn.decks import sample_pair

    m = make()
    s = new_game(pool, sample_pair(pool, Pcg32(4)), 11)
    for me in (0, 1):
        assert m.score(s, me) == m.raw(features(s, me))
        assert m.value(s, me) == m.forward(features(s, me))
        assert 0.0 <= m.value(s, me) <= 1.0


# ------------------------------------------------------------------ round trip
def test_json_round_trip_is_exact(tmp_path):
    """Not ``approx``: the weights are written at full ``repr`` precision precisely so that a
    reload is the same model bit for bit."""
    m = make(hidden=9)
    p = m.save(tmp_path / "w.json")
    back = ValueModel.load(p)
    assert back.w1 == m.w1 and back.b1 == m.b1 and back.w2 == m.w2 and back.b2 == m.b2
    assert [back.forward(x) for x in xs(10)] == [m.forward(x) for x in xs(10)]


def test_load_weights_caches_by_path(tmp_path):
    p = make().save(tmp_path / "c.json")
    assert load_weights(p) is load_weights(p)


# ------------------------------------------------------------------ refusals
def good(tmp_path) -> dict:
    return json.loads(make().save(tmp_path / "g.json").read_text(encoding="utf-8"))


def refuses(d, needle):
    with pytest.raises(ValueError, match=needle):
        ValueModel.from_json(d, where="w")


def test_a_future_format_is_refused(tmp_path):
    d = good(tmp_path)
    d["format"] = FORMAT + 1
    refuses(d, str(FORMAT))


def test_another_activation_is_refused(tmp_path):
    d = good(tmp_path)
    d["activation"] = "relu"
    refuses(d, "relu")


def test_a_different_feature_list_names_the_first_difference(tmp_path):
    d = good(tmp_path)
    d["features"] = list(FEATURE_NAMES)
    d["features"][17] = "cred_meh"
    with pytest.raises(ValueError) as e:
        ValueModel.from_json(d, where="w")
    assert "17" in str(e.value) and "cred_meh" in str(e.value) and FEATURE_NAMES[17] in str(e.value)


def test_a_shorter_feature_list_names_both_lengths(tmp_path):
    d = good(tmp_path)
    d["features"] = list(FEATURE_NAMES)[:-3]
    with pytest.raises(ValueError) as e:
        ValueModel.from_json(d, where="w")
    assert str(NFEAT - 3) in str(e.value) and str(NFEAT) in str(e.value)


@pytest.mark.parametrize("key", ["w1", "b1", "w2"])
def test_a_shape_mismatch_is_refused(tmp_path, key):
    d = good(tmp_path)
    d[key] = d[key][:-1]
    refuses(d, "hidden=")


def test_a_short_w1_row_names_the_row(tmp_path):
    d = good(tmp_path)
    d["w1"][3] = d["w1"][3][:-2]
    with pytest.raises(ValueError) as e:
        ValueModel.from_json(d, where="w")
    assert "row 3" in str(e.value)


def test_another_ruleset_is_refused_and_rules_none_escapes(tmp_path):
    """Same convention as ``experience.GameRecord.from_json``: the digest is demanded by default,
    and ``rules=None`` is the deliberate escape a refit needs."""
    d = good(tmp_path)
    d["rules"] = "0" * 16
    refuses(d, "refit")
    assert ValueModel.from_json(d, rules=None).hidden == 6
    assert ValueModel.from_json(d, rules="0" * 16).hidden == 6


# ------------------------------------------------------------------ the shipped file
@pytest.mark.skipif(not WEIGHTS.exists(), reason="no weights have been fitted")
def test_the_shipped_weights_load_under_this_build_and_ruleset():
    m = load_weights()
    assert m.header["rules"] == DEFAULT_CONFIG.digest()
    assert len(m.w1) == m.hidden and all(len(r) == NFEAT for r in m.w1)


@pytest.mark.skipif(not WEIGHTS.exists(), reason="no weights have been fitted")
def test_the_shipped_weights_name_their_own_feature_list_and_digest():
    d = json.loads(WEIGHTS.read_text(encoding="utf-8"))
    assert d["features"] == list(FEATURE_NAMES)
    assert d["feature_digest"] == M.feature_digest()
    assert d["kind"] == "value" and d["activation"] == "tanh"
    assert d["run"]["games"] > 0 and d["train"]["holdout_games"] > 0
