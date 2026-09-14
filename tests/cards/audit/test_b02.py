"""Batch B02 — cross-cutting pass: the modifier family.

One mechanism read across the whole pool: every card that writes a mod and every engine site that
reads one (see `out/audit/b02/findings.md` for the census of all 14 mod names). The two findings
here are the ones a per-section reader could not have produced, because each is a claim about a
*read* site in `src/cptcg/core/` that lives nowhere near the card that prints the clause.

Every assertion is a printed-text outcome — which zone a card is in, which actions the board
offers — never a mods list or a flag.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from conftest import Side, board, do, find                    # noqa: E402
from cptcg.core.actions import Attack, Play, Target           # noqa: E402
from cptcg.core.enums import Zone                             # noqa: E402

TARGET_UNIT = 0
E = 9


def play(s, cid, player=0):
    do(s, Play(find(s, cid, Zone.HAND, player)))
    return s


# ------------------------------------------------------------------- memory-relapse / cant_ready
def _relapse_board(pool, rival_unit):
    """Memory Relapse spends the rival's only Unit and forbids it to ready. Our 0-power Unit then
    feeds it a fight it wins; Animals Wrecker (power 10) waits to attack whatever is still spent."""
    s = board(pool, Side(hand=["memory-relapse"], eddies=E,
                         field=["delamain-rideshare-ai", "animals-wrecker"], gig=[(6, 3)]),
              Side(field=[rival_unit], deck=["floor-it", "floor-it"]))
    play(s, "memory-relapse")                       # only one rival Unit: spent without a prompt
    do(s, Attack(find(s, "delamain-rideshare-ai")))
    do(s, Target(TARGET_UNIT, find(s, rival_unit)))
    return s


def test_memory_relapse_keeps_a_unit_spent_against_its_own_ready_trigger(pool):
    """'Spend a rival Unit. It can't ready until your next turn.'

    Johnny Silverhand *Never Stop Fighting* prints "The first time this Unit wins a fight each
    turn, ready it." Memory Relapse has just said he can't ready until our next turn, and this is
    still the turn Memory Relapse was played — a mid-turn ready, nowhere near the boundary. So
    Johnny must still be spent after winning, and a spent Unit is attackable (docs/rules.md:
    "Ready Units can't be attacked"), which is what Animals Wrecker at power 10 is for.

    Fixed: AUD-memory-relapse-2.
    """
    s = _relapse_board(pool, "johnny-silverhand-never-stop-fighting")
    johnny, wrecker = find(s, "johnny-silverhand-never-stop-fighting"), find(s, "animals-wrecker")
    assert Attack(wrecker) in s.pending.options     # Johnny is still spent, so still attackable
    do(s, Attack(wrecker))                          # his Gig area is empty: he is the only target
    assert s.i_zone[johnny] == Zone.TRASH


def test_memory_relapse_board_lets_the_wrecker_finish_a_unit_that_stays_spent(pool):
    """Control for the xfail above: the same board with a rival Unit that has no ready trigger.

    Psycho Squad wins the same fight and stays spent, so Animals Wrecker's attack is legal and
    trashes it — the observable ("is the spent Unit still attackable?") and the board are sound,
    and the only difference in the failing test is the ready that Memory Relapse forbade.
    """
    s = _relapse_board(pool, "psycho-squad")
    psycho, wrecker = find(s, "psycho-squad"), find(s, "animals-wrecker")
    assert Attack(wrecker) in s.pending.options
    do(s, Attack(wrecker))
    assert s.i_zone[psycho] == Zone.TRASH


def test_memory_relapse_is_honoured_by_the_rivals_ready_step(pool):
    """Control for AUD-memory-relapse-2: the prohibition is recorded, it is just not enforced
    against effects. The rival's start-of-turn Ready step does skip the named Unit, so it is still
    spent — and therefore cannot attack — on the rival's own turn.
    """
    from cptcg.core.actions import EndTurn, TakeGigDie
    s = board(pool, Side(hand=["memory-relapse"], eddies=E, gig=[(6, 3)]),
              Side(field=["psycho-squad"], deck=["floor-it", "floor-it"]))
    play(s, "memory-relapse")
    psycho = find(s, "psycho-squad")
    do(s, EndTurn())
    do(s, TakeGigDie(4))                            # the rival's start-of-turn Gig roll
    assert Attack(psycho) not in s.pending.options  # still spent: spent Units can't attack


# ----------------------------------------------------------------------------- safety-override
def test_safety_override_fires_on_a_tied_fight(pool):
    """'QUICK: The next time a friendly Unit loses a fight this turn, defeat the opposing rival
    Unit.'

    Ruling 010: "Ties: both lose and both are defeated (CR 9.17.3)" — so the defender lost this
    fight. The same ruling stops a 0-power Unit defeating anything (CR 9.19.2), which is why both
    0-power Units are still standing afterwards and why Safety Override's own defeat is the only
    thing that can send the attacker to the trash.

    Fixed: AUD-safety-override-1.
    """
    s = board(pool, Side(field=["delamain-rideshare-ai"], gig=[(4, 1)]),
              Side(hand=["safety-override"], eddies=4,
                   field=[("japantown-jonin", {"spent": True})], gig=[(4, 1)]))
    attacker, defender = find(s, "delamain-rideshare-ai"), find(s, "japantown-jonin")
    do(s, Attack(attacker))
    do(s, Target(TARGET_UNIT, defender))
    play(s, "safety-override", player=1)            # QUICK, in the defender's reaction window
    assert s.i_zone[defender] == Zone.FIELD         # 0 power: the tie itself defeats nobody
    assert s.i_zone[attacker] == Zone.TRASH         # ... so the card's own defeat is all there is


def test_safety_override_fires_on_a_decisive_loss(pool):
    """Control for the xfail above: the same card in the same reaction window does defeat the
    winner when the friendly Unit loses decisively, so the tie test is genuinely about ties.
    """
    s = board(pool, Side(field=["animals-wrecker"], gig=[(4, 1)]),
              Side(hand=["safety-override"], eddies=4,
                   field=[("corpo-security", {"spent": True})], gig=[(4, 1)]))
    attacker, defender = find(s, "animals-wrecker"), find(s, "corpo-security")
    do(s, Attack(attacker))
    do(s, Target(TARGET_UNIT, defender))
    play(s, "safety-override", player=1)
    assert s.i_zone[defender] == Zone.TRASH and s.i_zone[attacker] == Zone.TRASH
