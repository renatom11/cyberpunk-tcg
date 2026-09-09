"""Determinism, clone equivalence and invariants across many random games."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import pytest
from smoke_random import play_random, reg  # noqa: F401

from cptcg.core import invariants
from cptcg.core.actions import EndTurn
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.rng import Pcg32
from conftest import blue_deck, red_deck


def _snapshot(s):
    return (s.turn, s.active, list(s.i_zone), bytes(s.i_spent), bytes(s.i_lag), bytes(s.i_faceup),
            list(s.i_host), list(s.i_flags), [list(z) for z in s.z], s.fixer, s.gig,
            s.over, s.winner, s.rng.state)


def _random_index(r, opts):
    if len(opts) > 1 and isinstance(opts[0], EndTurn) and r.below(10) < 9:
        return 1 + r.below(len(opts) - 1)
    return r.below(len(opts))


@pytest.mark.parametrize("seed", range(5))
def test_same_seed_same_game(seed):
    a, _ = play_random(seed, record=True)
    b, _ = play_random(seed, record=True)
    assert a.actions == b.actions and a.log == b.log and _snapshot(a) == _snapshot(b)


@pytest.mark.parametrize("seed", range(40))
def test_invariants_hold_after_every_action(seed):
    s = new_game(reg, (red_deck(), blue_deck()), seed)
    r = Pcg32(seed)
    invariants.check(s)
    while not s.over:
        apply(s, _random_index(r, legal_actions(s)))
        invariants.check(s)


@pytest.mark.parametrize("seed", range(20))
def test_clone_then_same_action_gives_identical_state(seed):
    s = new_game(reg, (red_deck(), blue_deck()), seed)
    r = Pcg32(seed + 99)
    while not s.over:
        idx = _random_index(r, legal_actions(s))
        c = s.clone()
        apply(s, idx)
        apply(c, idx)
        assert _snapshot(s) == _snapshot(c)
        assert legal_actions(s) == legal_actions(c)


def test_every_game_terminates_and_all_end_reasons_reachable():
    reasons = set()
    for seed in range(300):
        s, _ = play_random(seed)
        assert s.over
        reasons.add(s.end_reason.name)
    assert {"SEVEN_GIGS", "OVERTIME"} <= reasons
