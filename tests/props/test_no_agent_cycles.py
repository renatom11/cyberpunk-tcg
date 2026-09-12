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


# ---------------------------------------------------------------- the key the guard is built on
def test_position_key_agrees_with_same_position_in_both_directions(pool):
    """``position_key`` is what lets the guard remember positions in a set instead of comparing
    them pairwise. It has to partition states *exactly* as ``_same_position`` does: coarser and the
    agent refuses legal moves, finer and the cycle guard stops working.

    It was wrong four times while being written — ``used`` is a set (unordered), ``mods`` and
    ``played`` hold lists, ``turns_taken`` reads like an int and is a list of two, and some index
    arrays are ``bytearray``. Every one of those produced either an unhashable key or a key that
    silently disagreed, so this checks the property rather than the field list.
    """
    from cptcg.agents.base import make_agent
    from cptcg.agents.neural import _same_position, position_key
    from cptcg.core.engine import apply, legal_actions, new_game
    from cptcg.learn.arena import sampled_pairings

    clones = unequal = 0
    for sd in range(20, 26):
        pr = sampled_pairings(pool, 6, deck_seed=5, label="t")[sd % 6]
        s = new_game(pool, (pr.deck_a, pr.deck_b), sd)
        a = make_agent("heuristic", sd)
        a.new_game(sd, 0)
        prev = []
        for _ in range(120):
            if s.over:
                break
            legal_actions(s)
            k = position_key(s)
            hash(k)                                     # must be usable as a set member
            c = s.clone()
            # The "same position" direction, deterministically: a clone always is one. Waiting for
            # a natural repeat is not a test, it is a coincidence — an earlier version asserted one
            # turned up and failed on a narrower seed range.
            assert position_key(c) == k and _same_position(c, s), "a clone is the same position"
            clones += 1
            for pk, ps in prev[-30:]:
                if (pk == k) != _same_position(ps, s):
                    raise AssertionError("position_key disagrees with _same_position")
                unequal += pk != k
            prev.append((k, s.clone()))
            apply(s, a.act(s, s.pending))
    assert unequal > 1000, "not enough comparisons to mean anything"
    assert clones > 200, "not enough same-position checks to mean anything"


@pytest.mark.skipif(not WEIGHTS_PATH.exists(), reason="no weights have been fitted")
def test_a_multi_step_cycle_does_not_hang_the_search(pool):
    """A two-step loop: A then B returns to A. The one-step guard explicitly did not catch this —
    its docstring said so and said it was not worth paying for until something demonstrated it was
    needed. Mutated weights, generated while probing an evolutionary search, demonstrated it: two
    ISMCTS agents walked a MAIN menu in a circle and hit runner's 50,000-action ceiling.

    The mutant is not checked in, so this plays the same shape — two searching agents on the deck
    pairing and seed that failed — and asserts termination rather than reproducing that exact file.
    """
    from cptcg.agents.base import make_agent
    from cptcg.core.engine import apply, legal_actions, new_game
    from cptcg.learn.arena import sampled_pairings

    prs = sampled_pairings(pool, 6, deck_seed=777001, label="evo")
    for pr in prs[:2]:
        s = new_game(pool, (pr.deck_a, pr.deck_b), 2004248)
        ags = [_agent("ismcts", 2004248 * 2 + i, i) for i in range(2)]
        n = 0
        while not s.over and n < CAP:
            legal_actions(s)
            ch = s.pending
            apply(s, ags[ch.player].act(s, ch))
            n += 1
        assert s.over, f"two searching agents did not finish in {CAP} actions on {pr.deck_a.name}"
