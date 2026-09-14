"""``after=``: the hook that runs when the prompt does not.

Six cards in this set print two sentences where the second has its own board condition — "Adjust a
Gig by up to 1. **Then, if you control** 3 or more Gigs with different values, draw 1" — and
implement the second inside the continuation of the first. Every one of those first clauses can
decline to happen: "up to N" includes zero and the engine offers the decline explicitly, and a die
already showing the face it would move to cannot move at all (ruling 037). When it declines, the
printed second sentence never runs, and nothing raises.

``cont`` and ``after`` are the two shapes, and the difference is which sentence is being
implemented. ``cont`` talks about the Gig that moved and must not run when nothing moved. ``after``
is a separate sentence about the board and must run regardless. These tests pin all three paths for
each of the two prompting helpers — a real pick, a decline, and no legal candidate at all — because
the third is the one nobody writes a test for and is how ``industrial-assembly`` was found.

This is the plumbing only. No card uses it yet: it lands on its own so that ``bench.py check``
proves it changes nothing before any card moves onto it, which keeps the golden attribution clean
when the card fixes follow.
"""
from conftest import Side, board, do, find

from cptcg.core.actions import Pick
from cptcg.core.effects import EffectCtx
from cptcg.core.enums import Zone


def _ctx(s, player=0):
    """A ctx anchored on a real instance, which every EffectCtx needs for its call-site tags."""
    inst = s.zone(player, Zone.HAND)[0]
    return EffectCtx(s, inst)


def _run(s):
    """Let the engine settle on whatever the effect just asked.

    ``board()`` hands back a state already parked on the main menu, and ``EffectCtx.ask`` pushes its
    question onto the stack rather than into ``pending`` — so without dropping the menu first,
    ``advance`` sees a pending choice, returns immediately, and the test reads the main menu while
    believing it is reading the effect's prompt.
    """
    from cptcg.core.engine import advance, legal_actions
    s.pending = None
    advance(s)
    legal_actions(s)
    return s


def test_after_runs_on_a_real_adjustment_and_cont_runs_too(pool):
    s = board(pool, Side(hand=["floor-it"], gig=[(6, 3)], fixer=[4, 8, 10, 12, 20]), Side())
    seen = []
    c = _ctx(s)
    c.adjust_up_to([0], -1, 1, cont=lambda c2, o, i: seen.append(("cont", o, i)),
                   after=lambda c2: seen.append("after"))
    _run(s)
    do(s, Pick((1,)))                                    # take an adjustment
    assert s.gig[0] != [(6, 3)], "the die did not move, so this is not testing the pick path"
    assert seen == [("cont", 0, 0), "after"], seen


def test_after_runs_on_a_decline_and_cont_does_not(pool):
    s = board(pool, Side(hand=["floor-it"], gig=[(6, 3)], fixer=[4, 8, 10, 12, 20]), Side())
    seen = []
    c = _ctx(s)
    c.adjust_up_to([0], -1, 1, cont=lambda c2, o, i: seen.append("cont"),
                   after=lambda c2: seen.append("after"))
    _run(s)
    do(s, Pick(()))                                      # "up to 1" includes zero
    assert s.gig[0] == [(6, 3)] and seen == ["after"], seen


def test_after_runs_when_no_adjustment_is_legal_at_all(pool):
    """A d4 already showing 1 cannot be decreased; there is no question to ask (ruling 037).

    This is the path the six cards were found on, and the one a test written from the card's happy
    case never reaches: the engine skips the prompt entirely, so a continuation hung off it is not
    declined — it is never scheduled.
    """
    s = board(pool, Side(hand=["floor-it"], gig=[(4, 1)], fixer=[6, 8, 10, 12, 20]), Side())
    seen = []
    c = _ctx(s)
    c.adjust_up_to([0], -3, -1, cont=lambda c2, o, i: seen.append("cont"),
                   after=lambda c2: seen.append("after"))
    assert s.gig[0] == [(4, 1)] and seen == ["after"], seen


def test_choose_gig_after_covers_the_same_three_paths(pool):
    fixer = [4, 8, 10, 12, 20]
    # a real pick
    s = board(pool, Side(hand=["floor-it"], gig=[(6, 3)], fixer=fixer), Side())
    seen = []
    _ctx(s).choose_gig([0], lambda c2, o, i: seen.append("cont"), optional=True,
                       after=lambda c2: seen.append("after"))
    _run(s)
    do(s, Pick((0,)))
    assert seen == ["cont", "after"], seen

    # a decline
    s = board(pool, Side(hand=["floor-it"], gig=[(6, 3)], fixer=fixer), Side())
    seen = []
    _ctx(s).choose_gig([0], lambda c2, o, i: seen.append("cont"), optional=True,
                       after=lambda c2: seen.append("after"))
    _run(s)
    do(s, Pick(()))
    assert seen == ["after"], seen

    # nothing to choose
    s = board(pool, Side(hand=["floor-it"], fixer=list(range(0))), Side())
    seen = []
    _ctx(s).choose_gig([0], lambda c2, o, i: seen.append("cont"), optional=True,
                       after=lambda c2: seen.append("after"))
    assert seen == ["after"], seen


def test_cont_still_sees_the_gig_that_moved(pool):
    """``after`` must not have displaced ``cont``'s arguments — a clause that says "it" needs the
    owner and index of the die that actually moved, and that is the whole reason both hooks exist
    rather than one."""
    s = board(pool, Side(hand=["floor-it"], gig=[(6, 3), (8, 5)], fixer=[4, 10, 12, 20]), Side())
    got = []
    _ctx(s).adjust_up_to([0], 1, 1, cont=lambda c2, o, i: got.append((o, i, c2.gigs(o)[i])))
    _run(s)
    opts = [tuple(o.picks) for o in s.pending.options]
    do(s, Pick(opts[1]))                                 # the second listed adjustment
    assert len(got) == 1 and got[0][0] == 0 and got[0][2][1] in (4, 6), got
