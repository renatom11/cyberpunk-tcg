"""Batch A02 — Programs: removal, card flow, tempo (part 2/3).

Audit of src/cptcg/cards/sets/wnc.py lines 106-219 against the printed ``text`` in
data/cards/wnc.json. Every test here is a finding: it asserts what the card *says*, so it fails
against the script as written. See out/audit/a02/findings.md for the clause maps.
"""
import pytest
from conftest import Side, board, do, during_main, find

from cptcg.core import legal, ops, view
from cptcg.core.actions import Attack, Play, Target
from cptcg.core.enums import TARGET_UNIT, Zone

E = 9  # plenty of eddies


def play(s, cid):
    do(s, Play(find(s, cid, Zone.HAND)))
    return s


# --------------------------------------------------------------------- AUD-shattered-memories-1
@pytest.mark.xfail(strict=True, reason=(
    "AUD-shattered-memories-1: 'may draw 5' is drawn unconditionally, so the Program can deck a "
    "player out against their will"))
def test_shattered_memories_draw_five_is_optional(pool):
    """"Each player discards their hand and may draw 5."

    The Rival owns their own 'may'. With 2 cards left in their deck they would decline; the script
    draws for them and ends the game by deckout (ops.draw -> end_game).
    """
    s = board(pool, Side(hand=["shattered-memories"], eddies=E, gig=[(4, 3)], deck=["floor-it"] * 7),
              Side(hand=["floor-it"], deck=["floor-it"] * 2))
    play(s, "shattered-memories")
    assert not s.over, "the Rival may decline the draw rather than deck out"


# ------------------------------------------------------------------------- AUD-fool-on-the-hill-1
def test_fool_on_the_hill_reveals_the_top_two_to_the_chooser(pool):
    """"Reveal the top 2 cards of your deck. A Rival chooses whether you add them to your hand..."

    The choice is handed to the Rival with no ``revealed=`` declaration, so ``core.view`` keeps
    both cards hidden from seat 1 — the Rival decides blind, which the reveal clause forbids.

    Fixed: AUD-fool-on-the-hill-1.
    """
    s = board(pool, Side(hand=["fool-on-the-hill"], eddies=E, deck=["floor-it", "psycho-squad"]),
              Side())
    play(s, "fool-on-the-hill")
    assert s.pending.player == 1
    top2 = [find(s, "psycho-squad", Zone.DECK, 0), find(s, "floor-it", Zone.DECK, 0)]
    assert all(view.knows_identity(s, 1, i) for i in top2), "the Rival was not shown the top 2"


# ----------------------------------------------------------------------- AUD-gunpoint-diplomacy-1
@pytest.mark.xfail(strict=True, reason=(
    "AUD-gunpoint-diplomacy-1: 'the next time this Unit attacks this turn' is granted as an "
    "until-end-of-turn mod, so every attack that turn may hit ready Units"))
def test_gunpoint_diplomacy_ready_attack_lasts_one_attack(pool):
    """"- The next time this Unit attacks this turn, it may attack ready Units."

    One attack, not all of them. The Unit here attacks a ready Unit (spending the grant), is made
    ready again by an effect, and must then be unable to target the second ready Unit.
    """
    s = board(pool, Side(hand=["gunpoint-diplomacy"], eddies=E, field=["psycho-squad"],
                         gig=[(20, 20)]),
              Side(field=["psycho-squad", "psycho-squad"], gig=[(4, 1)]))
    play(s, "gunpoint-diplomacy")                 # more Street Cred: both effects, only one target
    mine = s.units(0)[0]
    first, second = s.units(1)
    assert not s.i_spent[second]
    do(s, Attack(mine))
    do(s, Target(TARGET_UNIT, first))             # the "next time" is used up here
    assert s.i_zone[first] == Zone.TRASH
    during_main(s, lambda st: ops.ready(st, mine))
    assert Target(TARGET_UNIT, second) not in legal.attack_targets(s, mine), \
        "the grant was spent on the first attack"
