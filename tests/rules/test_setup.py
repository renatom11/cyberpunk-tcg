"""Setup: play order, first-player handicap, opening hand and mulligan."""
from conftest import blue_deck, red_deck

from cptcg.core.actions import ChoiceKind, ChooseOrder, Mulligan
from cptcg.core.engine import apply, new_game
from cptcg.core.enums import F_NO_READY_NEXT, Zone


def _to_first_main_phase(reg, seed, go_first=True, keep=(True, True)):
    s = new_game(reg, (red_deck(), blue_deck()), seed)
    assert s.pending.kind == ChoiceKind.ORDER
    winner = s.pending.player
    apply(s, s.pending.index_of(ChooseOrder(go_first)))
    first = winner if go_first else 1 - winner
    assert s.first_player == first
    for k in keep:
        assert s.pending.kind == ChoiceKind.MULLIGAN
        apply(s, s.pending.index_of(Mulligan(k)))
    # Turn 1 start phase: ready, draw, then the Gig-die choice; take the d4 to reach the main phase.
    assert s.pending.kind == ChoiceKind.GIG_DIE and s.pending.player == first
    apply(s, 0)
    return s, first


def test_first_player_starts_with_two_leftmost_legends_spent_until_their_second_turn(reg):
    s, first = _to_first_main_phase(reg, seed=3)
    legs = s.legends(first)
    # Turn 1 (first player's start phase already ran): still spent, flag consumed.
    assert [s.i_spent[i] for i in legs] == [1, 1, 0]
    assert not any(s.i_flags[i] & F_NO_READY_NEXT for i in legs)
    second = 1 - first
    assert [s.i_spent[i] for i in s.legends(second)] == [0, 0, 0]


def test_opening_hands_and_mulligan(reg):
    s, first = _to_first_main_phase(reg, seed=5, keep=(False, True))
    # Each player drew 6, the mulliganer reshuffled and redrew 6, then the first player drew 1.
    assert len(s.zone(first, Zone.HAND)) == 7
    assert len(s.zone(1 - first, Zone.HAND)) == 6
    assert len(s.zone(first, Zone.DECK)) == len(red_deck().main if first == 0 else blue_deck().main) - 7


def test_choosing_to_go_second_flips_order(reg):
    s, first = _to_first_main_phase(reg, seed=8, go_first=False)
    assert s.active == first and s.turn == 1
    assert s.pending.kind == ChoiceKind.MAIN and s.pending.player == first


def test_turn_one_gains_a_gig_after_ready_and_draw(reg):
    s, first = _to_first_main_phase(reg, seed=11)
    assert len(s.gig[first]) == 1 and len(s.fixer[first]) == 5
