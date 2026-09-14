"""Batch b01 — the cross-cutting pass over ``on_event`` hooks and their ``events=`` filters.

Every ``on_event`` script in src/cptcg/cards/sets/wnc.py was read as one mechanism (39 hooks) and
the printed trigger words of the 20 assigned cards were tabled against the event kind each hook
declares. Every declared kind is the right kind; both findings below are about the guard *inside*
the hook. See out/audit/b01/findings.md for the table and the sibling comparison that produced them.

Every assertion here is a printed-text outcome — Gig faces, hand size, ready Eddies, ``ops.power``.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from conftest import Side, board, do, find                      # noqa: E402
from cptcg.core.actions import Attack, ChoiceKind, GoSolo, Play, Target   # noqa: E402
from cptcg.core.enums import Zone                               # noqa: E402
from cptcg.core.ops import ATTACKING, available, power          # noqa: E402

E = 9
TARGET_GIG = 1


# ------------------------------------------------- jackie-welles-pour-one-out-for-me
@pytest.mark.xfail(strict=True, reason="AUD-jackie-welles-pour-one-out-for-me-1: GO SOLO dispatches "
                                       "'played' for a Legend, and GO SOLO is playing it as a Unit "
                                       "(ruling 032/015), but the hook gates on CardDef.type in "
                                       "(UNIT, GEAR) and so never fires for a Blue Legend")
def test_jackie_fires_when_a_blue_legend_goes_solo(pool):
    """'The first time you play a Blue Unit or Blue Gear each turn, you may decrease a friendly
    Gig by up to 2. If it becomes a min Gig, draw 1.'

    V *Corporate Exile* is a Blue Legend whose own printed reminder is GO SOLO: "Pay this Legend's
    cost to **play it as a ready Unit**." Ruling 032 settles that this is playing it ("Calling a
    Legend is not playing it" — GO SOLO is the other way round) and ruling 015 settles that it is a
    Unit now. ``engine.go_solo`` agrees on both counts: it pushes the PLAY trigger and dispatches
    ("played", inst, p). So playing it is playing a Blue Unit, and Jackie's first-of-the-turn
    trigger must offer the decrease.

    The same reading has already been accepted for three other event kinds — 6th Street Recruits on
    ``steal`` (a11), Satori on ``fight_won`` (a12), River Ward on ``defeated`` (a13). Jackie is the
    fourth kind, ``played``, and the only hook in the set that names a Unit there.
    """
    s = board(pool, Side(legends=[("jackie-welles-pour-one-out-for-me", {"faceup": True}),
                                  ("v-corporate-exile", {"faceup": True})],
                         eddies=E, gig=[(6, 3)], deck=["floor-it"]), Side())
    do(s, GoSolo(find(s, "v-corporate-exile")))
    assert s.pending.kind is ChoiceKind.PICK           # the decrease was offered
    do(s, s.pending.options[0])                        # take the largest: -2
    assert s.gig[0] == [(6, 1)]                        # the d6 is now a min Gig ...
    assert len(s.zone(0, Zone.HAND)) == 1              # ... so "draw 1" pays out


def test_jackie_fires_when_a_blue_unit_is_played_from_hand(pool):
    """Control for the xfail above: the identical board with an ordinary Blue Unit does offer the
    decrease, so the test beside it is about the Legend and not about a broken board."""
    s = board(pool, Side(hand=["psycho-squad"], eddies=E, gig=[(6, 3)],
                         legends=[("jackie-welles-pour-one-out-for-me", {"faceup": True})],
                         deck=["floor-it"]), Side())
    do(s, Play(find(s, "psycho-squad", Zone.HAND)))
    assert s.pending.kind is ChoiceKind.PICK
    do(s, s.pending.options[0])
    assert s.gig[0] == [(6, 1)]
    assert len(s.zone(0, Zone.HAND)) == 1


# -------------------------------------- rogue-amendiares-queen-of-the-afterlife
def test_rogue_queen_readies_when_the_thief_steals_on_its_attacking_power(pool):
    """'The first time another friendly Unit steals a Gig with value less than its power each turn,
    ready 2 Eddies.'

    The comparison is made at the instant of a steal, and a steal only happens while the thief is
    attacking. Saul Bright *Stormrider* gives "Other friendly Units have +2 power while attacking",
    so Emergency Atlus attacks at power 6 — and that 6 is the number the engine has already used
    twice on the way here: ``ops.steal_count(power(s, a, ATTACKING))`` decides it takes one die, and
    ``steps.stealable`` decides which dice it may take. The one printed rule in this set that
    compares a Gig's value against a thief Unit's power, Chrome Fang's "rival Units can't steal
    friendly Gigs with value **higher than their power**", is applied in that same ``stealable``
    with ATTACKING. The d6 it steals shows 5, and 5 < 6, so Rogue's trigger must pay out.

    Fixed: AUD-rogue-amendiares-queen-of-the-afterlife-1.
    """
    s = board(pool, Side(field=["rogue-amendiares-queen-of-the-afterlife",
                                "saul-bright-stormrider", "emergency-atlus"],
                         eddies=4, spent_eddies=4),
              Side(gig=[(6, 5)]))
    thief = find(s, "emergency-atlus")
    do(s, Attack(thief))
    do(s, Target(TARGET_GIG, 0))
    assert s.gig[0] == [(6, 5)] and s.gig[1] == []     # the d6 showing 5 was stolen
    assert available(s, 0) == 2                        # ... and 2 Eddies were readied


def test_rogue_queen_control_the_aura_is_on_and_a_plain_steal_pays_out(pool):
    """Control for the xfail above, in two halves.

    First: Saul Bright's aura really is in effect on that board — Emergency Atlus reads power 4 at
    rest and 6 while attacking — so the xfail is about which of those two numbers Rogue compares
    against, not about a Unit that never got the bonus.

    Second: the same trigger on a board with no aura does ready 2 Eddies, so the Eddie bookkeeping
    and the "another friendly Unit" test are both sound.
    """
    s = board(pool, Side(field=["rogue-amendiares-queen-of-the-afterlife",
                                "saul-bright-stormrider", "emergency-atlus"],
                         eddies=4, spent_eddies=4),
              Side(gig=[(6, 5)]))
    thief = find(s, "emergency-atlus")
    assert power(s, thief) == 4
    assert power(s, thief, ATTACKING) == 6

    s2 = board(pool, Side(field=["rogue-amendiares-queen-of-the-afterlife", "emergency-atlus"],
                          eddies=4, spent_eddies=4),
               Side(gig=[(6, 3)]))
    t2 = find(s2, "emergency-atlus")
    assert available(s2, 0) == 0
    do(s2, Attack(t2))
    do(s2, Target(TARGET_GIG, 0))
    assert s2.gig[0] == [(6, 3)]                       # 3 < its power of 4
    assert available(s2, 0) == 2
