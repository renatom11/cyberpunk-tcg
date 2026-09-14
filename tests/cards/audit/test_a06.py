"""Batch A06 — Units: PLAY triggers (part 2/2).

Audit of src/cptcg/cards/sets/wnc.py lines 499-602 against the printed text in
data/cards/wnc.json. Every test here asserts a printed-text outcome only — zones, hand size,
and the set of legal actions — never script internals.
"""
import pytest
from conftest import Side, board, defeat_now, do, find

from cptcg.core.actions import Attack, ChoiceKind, EndTurn, Pick, Play
from cptcg.core.enums import NO_INST, Zone

E = 9  # plenty of eddies


def play(s, cid):
    do(s, Play(find(s, cid, Zone.HAND), NO_INST))
    return s


def test_mox_inciters_forces_the_named_rival_unit_to_attack(pool):
    """'PLAY: A rival Unit must attack next turn if it can.'

    Mox Inciters names Psycho Squad (the only rival Unit, so the pick auto-resolves). On the
    rival's next turn Psycho Squad is ready, unlagged, and there is a friendly Gig area holding
    a die — it *can* attack, so `Attack` is offered. 'Must attack' means the rival may not
    simply end the turn instead: with the obligation in force, ending the turn without having
    attacked is not a legal line.

    `c.mod("must_attack", u, until_my_next_turn=True)` (wnc.py:516) stores the mod with the
    right duration, but no code anywhere in `src/` ever reads it — `grep -rn must_attack src/`
    finds only the two cards that write it (wnc.py:516 and wnc.py:1251). The existing
    `tests/cards/test_units.py::test_mox_inciters_forces_attack` asserts
    `s.has_mod("must_attack", ...)`, i.e. that the bookkeeping happened, which is exactly the
    internal that hides this.

    Fixed: AUD-mox-inciters-1.
    """
    s = board(pool, Side(hand=["mox-inciters"], eddies=E, gig=[(4, 1)], deck=["floor-it"] * 4),
              Side(field=["psycho-squad"], deck=["floor-it"] * 4, fixer=[]))
    play(s, "mox-inciters")                                  # only one rival Unit: auto-resolved
    do(s, EndTurn())
    psycho = find(s, "psycho-squad", player=1)
    assert s.active == 1 and Attack(psycho) in s.pending.options      # it can attack ...
    assert EndTurn() not in s.pending.options                        # ... so it must


def test_yorinobu_draws_when_a_rival_arasaka_unit_is_defeated(pool):
    """'The first time an ARASAKA Unit is defeated each turn, draw 1.'

    The clause carries no side qualifier. Cards in this set say so when they mean one side —
    River Ward reads 'When a *friendly* equipped Unit is defeated', and Yorinobu's own first
    paragraph says 'rival Units' — so the unqualified 'an ARASAKA Unit' is any ARASAKA Unit,
    either player's. Minotaur (tags ARASAKA, DRONE, MILITECH) is defeated on the rival's field
    while Yorinobu is in play; Yorinobu's controller should draw 1.

    wnc.py:585 gates the hook on `e[2] == c.player`; `e[2]` is the *owner* of the defeated card
    (`ops.defeat` dispatches `("defeated", inst, owner, was_equipped)`), so only friendly
    ARASAKA deaths ever draw. The friendly half works — the same board with Minotaur on
    Yorinobu's own field does draw 1 — so this is scope, not a dead hook.

    Fixed: AUD-yorinobu-arasaka-steel-dragon-1.
    """
    s = board(pool, Side(field=["yorinobu-arasaka-steel-dragon"], deck=["floor-it"] * 3),
              Side(field=["minotaur"]))
    defeat_now(s, find(s, "minotaur", player=1))
    assert len(s.zone(0, Zone.HAND)) == 1


def test_placide_may_discard_a_program_with_no_rival_units(pool):
    """'PLAY / ATTACK: You may discard 1 Program. If you do, bottom-deck a rival Unit.'

    The permission is to discard; the bottom-deck is a rider hanging off 'If you do'. With a
    Program (Floor It) in hand and an empty rival field, the discard is still a legal thing to
    want: this set has three cards that play or retrieve a Program *from the trash* — Alt
    Cunningham ('1 €$, ⊡: Play a Program from your trash'), Lizzy Wizzy ('play a Program with
    cost 3 or less from your hand or trash for free') and V ('add 1 BRAINDANCE Program from
    your trash to your hand') — so loading the trash is a real line, not a null play.

    wnc.py:597 guards the whole offer with `if progs and c.rival_units()`, so with no rival
    Units the question is never asked and play returns straight to the main menu.

    Fixed: AUD-placide-voodoo-sentinel-1.
    """
    s = board(pool, Side(hand=["placide-voodoo-sentinel", "floor-it"], eddies=E, deck=["floor-it"]),
              Side())
    # The *hand* copy, named before it moves. `find` without a zone returns the first instance of
    # the id, which here is the one in the deck -- an earlier version of this test asserted on that
    # one and so failed for a reason its own docstring did not claim.
    in_hand = find(s, "floor-it", Zone.HAND, 0)
    play(s, "placide-voodoo-sentinel")
    assert s.pending.kind is ChoiceKind.PICK and s.pending.player == 0   # the 'you may' is offered
    do(s, Pick((0,)))                                                    # yes, discard Floor It
    assert s.i_zone[in_hand] == Zone.TRASH
