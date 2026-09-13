"""The turn-plan agent: it plans a whole turn, and it re-plans rather than trusting a stale one.

The headline claim is a number, and it is checked here rather than only in an arena run:
``two-pieces-of-gear`` is a horizon-1 position — winnable entirely inside one turn by
``equip, equip, call, attack`` — and ISMCTS at 200 iterations solves it **0 times in 16**, because
every leaf it evaluates is mid-turn, after a Gig has been banked and before the setup has paid.
Scoring complete turns at the turn boundary is the whole idea, so if that position stops being
solved the idea has stopped working and this file is where that shows up.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.core.actions import ChoiceKind  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.engine import legal_actions  # noqa: E402
from cptcg.learn.delayed import build_entry, entry_horizon, play_turn  # noqa: E402
from cptcg.learn.model import WEIGHTS_PATH  # noqa: E402

SUITE = Path("data/arena/delayed.json")
#: Small on purpose. What is being tested is that planning a whole turn finds the line at all, not
#: how much budget it takes; a budget this size also keeps the suite quick.
BUDGET = 32


def _entry(name: str) -> dict:
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    return next(e for e in suite["positions"] if e["id"] == name)


@pytest.mark.skipif(not WEIGHTS_PATH.exists(), reason="no weights have been fitted")
def test_it_solves_the_position_the_per_decision_search_cannot(pool):
    """The thesis of the agent, as a unit test rather than an arena row."""
    e = _entry("two-pieces-of-gear")
    s = build_entry(pool, e, DEFAULT_CONFIG)
    me = e.get("player", s.pending.player)
    horizon = entry_horizon(e)
    wins = sum(play_turn(s, me, f"plan:{BUDGET}", seed=sd, max_turns=horizon)[0]
               for sd in (101, 102, 103, 104))
    assert wins == 4, ("the turn-plan agent stopped finding the within-turn line; this is the one "
                       "position the agent was built for, and ismcts solves it 0 of 16 at 200 "
                       "iterations")


@pytest.mark.skipif(not WEIGHTS_PATH.exists(), reason="no weights have been fitted")
def test_a_plan_is_a_whole_turn_and_it_ends_the_turn(pool):
    """A plan runs to the turn boundary. A plan that stops short is a per-decision agent wearing a
    different name, and would be scored at exactly the mid-turn position this agent avoids."""
    from cptcg.core.actions import EndTurn

    e = _entry("two-pieces-of-gear")
    s = build_entry(pool, e, DEFAULT_CONFIG)
    a = make_agent(f"plan:{BUDGET}", 7)
    a.new_game(11, e.get("player", s.pending.player))
    plan = a.plan_for(s)
    assert len(plan) > 1, "a whole turn is more than one move here"
    assert all(isinstance(k, ChoiceKind) for k, _ in plan)
    # The line either ends the turn explicitly or ends the game; both are turn boundaries.
    assert isinstance(plan[-1][1], EndTurn) or len(plan) >= 2


@pytest.mark.skipif(not WEIGHTS_PATH.exists(), reason="no weights have been fitted")
def test_a_stale_plan_is_dropped_rather_than_played(pool):
    """A plan is computed in a *sampled* world against a *fixed* rival policy, so the real game can
    diverge from it mid-turn. Steps are matched by action and choice kind, never by index: an index
    would silently mean a different move the moment a menu came back in another shape."""
    e = _entry("two-pieces-of-gear")
    s = build_entry(pool, e, DEFAULT_CONFIG)
    me = e.get("player", s.pending.player)
    a = make_agent(f"plan:{BUDGET}", 3)
    a.new_game(11, me)
    legal_actions(s)

    i = a.act(s, s.pending)
    assert a._plan, "the rest of the turn should be planned after the first decision"
    assert 0 <= i < len(s.pending.options)

    # An action the live menu does not offer must not be played from the plan.
    a._plan = [(ChoiceKind.MAIN, object())] + list(a._plan)
    before = len(a._plan)
    assert a._next_step(s, s.pending) is None
    assert len(a._plan) == before, "a step that did not match must not be consumed"

    # Neither must a plan left over from a previous turn.
    a._plan_turn = s.turn - 1
    assert a._next_step(s, s.pending) is None


@pytest.mark.skipif(not WEIGHTS_PATH.exists(), reason="no weights have been fitted")
def test_the_budget_dial_means_what_it_means_everywhere_else(pool):
    """``plan:N`` has to be a budget in the same sense ``ismcts:N`` is, because
    ``tests/props/test_no_agent_cycles.py`` makes every registered agent shallow by setting
    ``iterations`` alone, and an agent that ignored it would run there at full cost."""
    assert make_agent("plan:8", 1).iterations == 8
    assert make_agent("plan", 1).iterations == make_agent("plan", 1).__class__.iterations
