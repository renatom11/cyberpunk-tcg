"""The policy head: what it may read, what it refuses, and that the search actually uses it."""
import json

import pytest
from conftest import Side, board, find

from cptcg.agents.base import make_agent
from cptcg.core.actions import EndTurn, Play, Sell
from cptcg.core.engine import legal_actions
from cptcg.core.enums import Zone
from cptcg.core.rng import Pcg32
from cptcg.learn.policy import (
    ACTION_FEATURE_NAMES, NAFEAT, PolicyModel, action_features, policy_in, write_beside, zeros,
)


def _table(reg):
    s = board(reg, Side(eddies=5, hand=["T-U4", "T-U8", "T-P2"], field=["T-U1"],
                        legends=[("T-L1", {"faceup": True}), "T-L5", "T-L6"]),
              Side(field=["T-U3"], gig=[(6, 3)]))
    legal_actions(s)
    return s


def test_every_legal_move_gets_a_full_vector_in_range(reg):
    s = _table(reg)
    assert len(ACTION_FEATURE_NAMES) == NAFEAT
    for a in s.pending.options:
        v = action_features(s, 0, a)
        assert len(v) == NAFEAT
        assert all(-1.0 <= x <= 1.0 for x in v), a


def test_different_kinds_of_move_look_different(reg):
    s = _table(reg)
    seen = {}
    for a in s.pending.options:
        seen.setdefault(type(a).__name__, action_features(s, 0, a))
    assert len(seen) > 3
    assert len(set(seen.values())) == len(seen)         # no two kinds collide


def test_the_same_card_played_and_sold_differ_in_more_than_the_kind(reg):
    """A move ordering that cannot tell 'play this' from 'sell this' is not ordering anything."""
    s = _table(reg)
    inst = find(s, "T-U4")
    play = next(a for a in s.pending.options if isinstance(a, Play) and a.inst == inst)
    sell = next(a for a in s.pending.options if isinstance(a, Sell) and a.inst == inst)
    p, q = action_features(s, 0, play), action_features(s, 0, sell)
    differ = [ACTION_FEATURE_NAMES[i] for i, (x, y) in enumerate(zip(p, q)) if x != y]
    assert "act_cost" in differ                          # selling is free, playing is not
    assert len(differ) > 2


def test_it_does_not_read_a_face_down_legend(reg):
    """The same mask features.py obeys: permuting what this seat may not see disturbs nothing."""
    s = board(reg, Side(eddies=5, legends=["T-L1", "T-L5", "T-L6"]), Side())
    legal_actions(s)
    calls = [a for a in s.pending.options if type(a).__name__ == "CallLegend"]
    assert calls
    before = [action_features(s, 0, a) for a in calls]
    # swap the identities behind two of my own face-down slots; nothing visible has changed
    slots = s.legends(0)
    s.i_card[slots[0]], s.i_card[slots[1]] = s.i_card[slots[1]], s.i_card[slots[0]]
    after = [action_features(s, 0, a) for a in calls]
    assert before == after
    i = ACTION_FEATURE_NAMES.index("act_unknown_card")
    assert all(v[i] == 1.0 for v in before)              # and it says so rather than reading zeros


def test_a_called_legend_is_readable_because_it_is_face_up(reg):
    s = board(reg, Side(eddies=5, legends=[("T-L1", {"faceup": True}), "T-L5", "T-L6"]), Side())
    legal_actions(s)
    solo = next(a for a in s.pending.options if type(a).__name__ == "GoSolo")
    v = action_features(s, 0, solo)
    assert v[ACTION_FEATURE_NAMES.index("act_unknown_card")] == 0.0
    assert v[ACTION_FEATURE_NAMES.index("act_card_legend")] == 1.0
    assert v[ACTION_FEATURE_NAMES.index("act_card_gosolo")] == 1.0


def test_cost_is_measured_against_what_is_actually_available(reg):
    rich = board(reg, Side(eddies=6, hand=["T-U8"], legends=["T-L1", "T-L5", "T-L6"]), Side())
    poor = board(reg, Side(eddies=2, hand=["T-U8"], legends=["T-L1", "T-L5", "T-L6"]), Side())
    legal_actions(rich); legal_actions(poor)
    i = ACTION_FEATURE_NAMES.index("act_cost_share")
    pr = next(a for a in rich.pending.options if isinstance(a, Play))
    pp = next((a for a in poor.pending.options if isinstance(a, Play)), None)
    if pp is not None:                                   # only if it is affordable at all
        assert action_features(poor, 0, pp)[i] > action_features(rich, 0, pr)[i]


# ---------------------------------------------------------------------- the head
def test_an_untrained_head_is_a_uniform_prior(reg):
    s = _table(reg)
    m = zeros(8)
    pri = m.prior(s, 0, list(s.pending.options))
    assert pytest.approx(sum(pri.values())) == 1.0
    assert len(set(round(v, 12) for v in pri.values())) == 1


def test_a_trained_looking_head_makes_a_distribution_that_still_sums_to_one(reg):
    s = _table(reg)
    rng = Pcg32(4)
    h = 6
    w1 = tuple(tuple((rng.next_u32() / 2**31) - 1.0 for _ in range(NAFEAT)) for _ in range(h))
    m = PolicyModel(h, w1, tuple(0.1 for _ in range(h)),
                    tuple((rng.next_u32() / 2**31) - 1.0 for _ in range(h)), 0.0)
    pri = m.prior(s, 0, list(s.pending.options))
    assert pytest.approx(sum(pri.values())) == 1.0
    assert len(set(round(v, 9) for v in pri.values())) > 1
    assert all(v >= 0.0 for v in pri.values())


def test_a_huge_logit_does_not_overflow_the_softmax(reg):
    """exp(1000) raises, and a badly scaled head is not a crash."""
    s = _table(reg)
    h = 2
    m = PolicyModel(h, tuple(tuple(50.0 for _ in range(NAFEAT)) for _ in range(h)),
                    (0.0, 0.0), (1e6, -1e6), 0.0)
    pri = m.prior(s, 0, list(s.pending.options))
    assert pytest.approx(sum(pri.values())) == 1.0


def test_no_moves_is_an_empty_prior_not_a_crash(reg):
    assert zeros(4).prior(_table(reg), 0, []) == {}


# ----------------------------------------------------------------------- on disk
def test_round_trip(tmp_path):
    m = zeros(5)
    p = m.save(tmp_path / "pol.json")
    back = PolicyModel.load(p)
    assert back.hidden == 5 and len(back.w1[0]) == NAFEAT


def test_it_refuses_a_value_head_wearing_the_same_shape():
    d = json.loads((__import__("pathlib").Path("src/cptcg/agents/weights.json")).read_text())
    with pytest.raises(ValueError, match="not a policy head"):
        PolicyModel.from_json(d)


def test_it_refuses_a_stale_move_feature_list(tmp_path):
    d = zeros(3).to_json()
    d["features"] = list(d["features"])
    d["features"][4] = "act_something_else"
    with pytest.raises(ValueError, match="move feature 4"):
        PolicyModel.from_json(d)


def test_it_refuses_another_ruleset(tmp_path):
    d = zeros(3).to_json()
    d["rules"] = "0000000000000000"
    with pytest.raises(ValueError, match="fitted under ruleset"):
        PolicyModel.from_json(d)


# ------------------------------------------------- one file, two heads
def test_a_policy_lives_inside_the_value_file(tmp_path):
    """A generation is a player, and a player is both halves; two files invites them to come apart."""
    src = __import__("pathlib").Path("src/cptcg/agents/weights.json")
    dst = tmp_path / "weights.json"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    assert policy_in(dst) is None                        # a plain value head has no policy in it

    write_beside(dst, zeros(4))
    got = policy_in(dst)
    assert got is not None and got.hidden == 4

    # ... and the value half is untouched and still loads
    from cptcg.learn.model import ValueModel
    assert ValueModel.load(dst).hidden == 16


def test_a_missing_file_is_no_policy_rather_than_an_error(tmp_path):
    assert policy_in(tmp_path / "nothing-here.json") is None


def test_the_search_uses_the_policy_when_the_file_carries_one(tmp_path, reg):
    """The fallback is a real opinion, so 'no policy' must mean the old prior and not a uniform one."""
    src = __import__("pathlib").Path("src/cptcg/agents/weights.json")
    dst = tmp_path / "weights.json"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    plain = make_agent(f"ismcts@{dst}", 3)
    assert plain.policy is None
    s = _table(reg)
    plain.new_game(1, 0)
    idxs = list(range(len(s.pending.options)))
    by_value = plain._priors(s, s.pending, idxs)

    write_beside(dst, zeros(4))
    withpol = make_agent(f"ismcts@{dst}", 3)
    withpol.new_game(1, 0)
    assert withpol.policy is not None
    by_policy = withpol._priors(s, s.pending, idxs)

    assert set(by_value) == set(by_policy)
    assert pytest.approx(sum(by_policy.values())) == 1.0
    # an untrained policy is uniform; the value-head prior is not, which is the point of the
    # fallback being the *old* prior rather than nothing
    assert len(set(round(v, 9) for v in by_policy.values())) == 1
    assert len(set(round(v, 9) for v in by_value.values())) > 1
