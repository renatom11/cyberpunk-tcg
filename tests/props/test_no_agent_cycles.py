"""No registered agent may fail to advance the game.

This test exists because the last two times it was needed it did not exist. The pool contains a
free no-op — ``panam-palmer-strength-through-family`` has a zero-cost ability with no spend and no
once-per-turn marker, whose optional pick can be declined for literally no effect, returning a
byte-identical position — and an agent that likes declining will decline for ever.

``neural`` hit it first and got a guard (``neural._same_position``, wired into ``_value``), and a
regression test that named ``neural``. Then ``ismcts`` was written, replaced ``_greedy`` with a
search whose three scoring paths all bypass ``_value``, imported ``_same_position`` without ever
calling it, and hung an ``arena generalisation`` run three hours in on the *same seed*.

So the test does not name an agent. It asks the registry, which means the next agent is covered on
the day it is written rather than on the day it costs a gate run. A guard living inside one agent's
scoring function was never a guard on the class of bug; this is.

The searching agents get a small iteration budget here. What is being tested is *which action is
returned*, not how well the search evaluates, and a shallow search reproduces the cycle — a claim
worth re-checking rather than assuming if this test ever goes quiet.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.core.engine import apply, legal_actions, new_game  # noqa: E402
from cptcg.learn.arena import known_agents, sampled_pairings  # noqa: E402
from cptcg.learn.model import WEIGHTS_PATH  # noqa: E402

#: The game that has now hung two different agents: seed 5005167 on training pairing 5 of
#: ``arena generalisation``, the rival holding the other half of the pairing.
HUNG_SEED = 5005167
#: Comfortably above a real game (a couple of hundred actions) and far below ``runner.play_game``'s
#: 50,000, so a cycling agent fails in seconds instead of hours.
CAP = 1500
#: Enough tree for the search to have an opinion, little enough that the whole suite stays quick.
ITERATIONS = 16


def _agent(name: str, seed: int, me: int):
    a = make_agent(name, seed)
    # An instance attribute over the class default: the registered agent is still the thing under
    # test, only shallower.
    if hasattr(type(a), "iterations"):
        a.iterations = ITERATIONS
    a.new_game(HUNG_SEED, me)
    return a


def _play(pool, names, cap=CAP):
    pr = sampled_pairings(pool, 6, deck_seed=31, label="train")[5]
    s = new_game(pool, (pr.deck_b, pr.deck_a), HUNG_SEED)
    ags = [_agent(n, HUNG_SEED * 2 + i, i) for i, n in enumerate(names)]
    n = 0
    while not s.over and n < cap:
        legal_actions(s)
        ch = s.pending
        apply(s, ags[ch.player].act(s, ch))
        n += 1
    return s, n


@pytest.mark.skipif(not WEIGHTS_PATH.exists(), reason="no weights have been fitted")
@pytest.mark.parametrize("name", sorted(known_agents()))
def test_no_registered_agent_cycles_on_the_free_no_op(pool, name):
    """Every agent the registry can build finishes the game that hung the last two."""
    s, n = _play(pool, (name, "heuristic"))
    assert s.over, (f"{name} was still going after {n} actions on seed {HUNG_SEED}: it is not "
                    f"advancing the game. The pool's free no-op is "
                    f"panam-palmer-strength-through-family's zero-cost 'Call a Legend for free', "
                    f"whose pick can be declined for no effect.")


@pytest.mark.skipif(not WEIGHTS_PATH.exists(), reason="no weights have been fitted")
@pytest.mark.parametrize("name", sorted(known_agents()))
def test_no_registered_agent_cycles_from_the_other_seat(pool, name):
    """The same game with the seats swapped. A cycle is a property of the agent and the position,
    not of which seat it happened to be sitting in, and the crash that prompted this was found in
    one ordering only because that is the one the arena happened to play first."""
    s, n = _play(pool, ("heuristic", name))
    assert s.over, f"{name} was still going after {n} actions from seat 1 on seed {HUNG_SEED}"
