"""Turn structure, economy, Legends and win conditions."""
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, CallLegend, EndTurn, GoSolo, Play, Sell, TakeGigDie
from cptcg.core.enums import EndReason, F_GO_SOLO, Zone
from cptcg.core.ops import available


def test_sell_once_per_turn_worth_one_eddie(reg):
    s = board(reg, Side(hand=["T-U4", "T-U8"]), Side())
    do(s, Sell(find(s, "T-U8")))                          # a 5-cost card is still 1 €$
    assert available(s, 0) == 1
    assert not any(isinstance(a, Sell) for a in s.pending.options)


def test_no_sell_tag_cannot_be_sold(reg):
    s = board(reg, Side(hand=["T-U9"]), Side())
    assert not any(isinstance(a, Sell) for a in s.pending.options)


def test_play_unit_costs_eddies_and_enters_with_lag(reg):
    s = board(reg, Side(hand=["T-U3"], eddies=3), Side())
    u = find(s, "T-U3")
    do(s, Play(u))
    assert s.i_zone[u] == Zone.FIELD and s.i_lag[u] == 1 and available(s, 0) == 0
    assert not any(isinstance(a, Attack) for a in s.pending.options)


def test_cannot_afford(reg):
    s = board(reg, Side(hand=["T-U3"], eddies=2), Side())
    assert not any(isinstance(a, Play) for a in s.pending.options)


def test_legends_pay_one_eddie_each(reg):
    s = board(reg, Side(hand=["T-U3"], eddies=1, legends=["T-L2", "T-L5", "T-L6"]), Side())
    do(s, Play(find(s, "T-U3")))
    assert sum(s.i_spent[i] for i in s.legends(0)) == 2


def test_gear_equips_to_unit_or_faceup_legend_only(reg):
    s = board(reg, Side(hand=["T-G1"], eddies=1, field=["T-U1"],
                        legends=[("T-L2", {"faceup": True}), "T-L5"]), Side())
    hosts = {a.host for a in s.pending.options if isinstance(a, Play)}
    assert hosts == {find(s, "T-U1"), find(s, "T-L2")}


def test_call_legend_costs_one_flips_and_is_once_per_turn(reg):
    s = board(reg, Side(eddies=2, legends=["T-L2", "T-L5", "T-L6"]), Side())
    l = s.legends(0)[0]
    do(s, CallLegend(l))
    assert s.i_faceup[l] == 1
    assert available(s, 0) == 4                           # 1 of 2 Eddies spent; 3 Legends still count
    assert sum(s.i_spent[i] for i in s.zone(0, Zone.EDDIES)) == 1
    assert not any(isinstance(a, CallLegend) for a in s.pending.options)


def test_go_solo_plays_legend_as_ready_unit_that_can_attack(reg):
    s = board(reg, Side(eddies=5, legends=[("T-L1", {"faceup": True}), "T-L5", "T-L6"]),
              Side(gig=[(6, 3)]))
    l = find(s, "T-L1")
    do(s, GoSolo(l))
    assert s.i_zone[l] == Zone.FIELD and s.i_lag[l] == 0 and s.i_flags[l] & F_GO_SOLO
    assert Attack(l) in s.pending.options
    do(s, Attack(l))
    assert s.gig[0] == [(6, 3)]


def test_go_solo_legend_is_removed_from_game_when_defeated(reg):
    s = board(reg, Side(field=["T-U8"]),
              Side(field=[("T-L1", {"spent": True, "flags": F_GO_SOLO})]))
    from cptcg.core.actions import Target
    from cptcg.core.enums import TARGET_UNIT
    do(s, Attack(find(s, "T-U8")))
    do(s, Target(TARGET_UNIT, find(s, "T-L1")))
    assert s.i_zone[find(s, "T-L1")] == Zone.REMOVED


def test_end_turn_readies_next_player_draws_and_gains_a_gig(reg):
    s = board(reg, Side(), Side(deck=["T-U1"] * 5, eddies=2, spent_eddies=2,
                                field=[("T-U2", {"spent": True})]))
    do(s, EndTurn())
    # Player 1's start phase: ready, draw, then a gig-die choice (d20 excluded).
    assert s.pending.player == 1
    assert {a.sides for a in s.pending.options} == {4, 6, 8, 10, 12}
    assert available(s, 1) == 2 and s.i_spent[find(s, "T-U2")] == 0
    assert len(s.zone(1, Zone.HAND)) == 1
    do(s, TakeGigDie(6))
    assert len(s.gig[1]) == 1 and s.gig[1][0][0] == 6 and 6 not in s.fixer[1]


def test_d20_is_always_last(reg):
    s = board(reg, Side(), Side(deck=["T-U1"] * 5, fixer=[20]))
    do(s, EndTurn())
    assert s.gig[1][0][0] == 20 and s.fixer[1] == []


def test_empty_fixer_skips_gig_gain(reg):
    s = board(reg, Side(), Side(deck=["T-U1"] * 5, fixer=[]))
    do(s, EndTurn())
    assert s.gig[1] == [] and s.pending.player == 1


def test_seven_gigs_at_start_of_turn_wins(reg):
    dice = [(4, 1), (6, 1), (8, 1), (10, 1), (12, 1), (20, 1), (4, 2)]
    s = board(reg, Side(), Side(deck=["T-U1"] * 5, gig=dice, fixer=[]))
    do(s, EndTurn())
    assert s.over and s.winner == 1 and s.end_reason == EndReason.SEVEN_GIGS


def test_deckout_loses_immediately(reg):
    s = board(reg, Side(), Side(deck=[]))
    do(s, EndTurn())
    assert s.over and s.winner == 0 and s.end_reason == EndReason.DECKOUT


def test_overtime_majority_wins_instantly(reg):
    s = board(reg, Side(field=["T-U3"], gig=[(4, 1), (6, 1)]), Side(gig=[(8, 1), (10, 1)]),
              overtime=True, turns_taken=[7, 7])
    do(s, Attack(find(s, "T-U3")))
    from cptcg.core.actions import Pick
    do(s, Pick((0,)))
    assert s.over and s.winner == 0 and s.end_reason == EndReason.OVERTIME


def test_lag_clears_at_end_of_turn_and_units_can_attack_next_turn(reg):
    s = board(reg, Side(hand=["T-U3"], eddies=3, deck=["T-U1"] * 5), Side(deck=["T-U1"] * 5, gig=[(6, 3)]))
    u = find(s, "T-U3")
    do(s, Play(u))
    do(s, EndTurn())
    do(s, TakeGigDie(4))
    do(s, EndTurn())
    do(s, TakeGigDie(4))
    assert Attack(u) in s.pending.options
