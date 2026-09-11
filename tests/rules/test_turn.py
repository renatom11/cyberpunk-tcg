"""Turn structure, economy, Legends and win conditions."""
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, CallLegend, EndTurn, GoSolo, Play, Sell, TakeGigDie
from cptcg.core.enums import EndReason, F_GO_SOLO, Zone
from cptcg.core.ops import available, play_cost


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
    assert s.i_zone[l] == Zone.FIELD and s.i_lag[l] == 1 and s.i_flags[l] & F_GO_SOLO   # CR 4.5.2: Lag
    assert Attack(l) in s.pending.options                                               # but GO SOLO attacks
    do(s, Attack(l))
    assert s.gig[0] == [(6, 3)]


def test_a_legend_may_not_spend_itself_toward_its_own_go_solo(reg):
    """Ruling 027 (CR 4.5): the Legend going solo is being played, not spent.

    The board this came off: two Eddies and three Legends, one of them the cost-5 GO SOLO Legend,
    already Called. Five ready sources of €$ are sitting on the table and the cost is five, so it
    reads like it should be payable — but one of those five is the card being played, and the
    menu is right to leave GO SOLO off it.
    """
    def table(eddies):
        s = board(reg, Side(eddies=eddies, legends=[("T-L1", {"faceup": True}), "T-L5", "T-L6"]),
                  Side())
        return s, find(s, "T-L1")

    s, l = table(2)
    assert play_cost(s, 0, l, go_solo=True) == 5
    assert available(s, 0) == 5                  # 2 Eddies + 2 face-down Legends + the face-up one
    assert available(s, 0, exclude=l) == 4       # ... but not the one going solo
    assert GoSolo(l) not in s.pending.options

    s, l = table(3)                              # one more Eddie and the same Legend can go
    assert available(s, 0, exclude=l) == 5
    assert GoSolo(l) in s.pending.options


def test_spent_legend_may_go_solo_and_arrives_spent(reg):
    """CR 4.5.1: a Legend played to the field keeps its orientation."""
    s = board(reg, Side(eddies=5, legends=[("T-L1", {"faceup": True, "spent": True}), "T-L5", "T-L6"]),
              Side(gig=[(6, 3)]))
    l = find(s, "T-L1")
    assert GoSolo(l) in s.pending.options
    do(s, GoSolo(l))
    assert s.i_zone[l] == Zone.FIELD and s.i_spent[l] == 1 and s.i_lag[l] == 1
    assert Attack(l) not in s.pending.options


def test_any_legend_leaving_play_is_removed_and_its_gear_stays_behind(reg):
    """CR 4.4.1 / 4.12.2."""
    from cptcg.core.ops import move
    s = board(reg, Side(field=[("T-L1", {"faceup": True, "gear": ["T-G1"]})]), Side())
    l, g = find(s, "T-L1"), find(s, "T-G1")
    move(s, l, Zone.TRASH)
    assert s.i_zone[l] == Zone.REMOVED and s.i_zone[g] == Zone.TRASH
    s = board(reg, Side(field=[("T-L1", {"faceup": True})]), Side())
    move(s, find(s, "T-L1"), Zone.HAND)
    assert s.i_zone[find(s, "T-L1")] == Zone.REMOVED


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


def test_overtime_seven_gigs_wins_instantly(reg):
    """CR 1.11: in Overtime, 7+ Gigs at any point wins on the spot."""
    s = board(reg, Side(field=["T-U3"], gig=[(4, 1), (6, 1), (8, 1), (10, 1), (12, 1), (20, 1)]),
              Side(gig=[(4, 2), (6, 2)]), overtime=True, turns_taken=[7, 7])
    do(s, Attack(find(s, "T-U3")))
    from cptcg.core.actions import Pick
    do(s, Pick((0,)))
    assert s.over and s.winner == 0 and s.end_reason == EndReason.OVERTIME


def test_six_gigs_is_not_enough_in_overtime(reg):
    s = board(reg, Side(field=["T-U3"], gig=[(4, 1), (6, 1), (8, 1), (10, 1), (12, 1)]),
              Side(gig=[(4, 2), (6, 2)]), overtime=True, turns_taken=[7, 7])
    do(s, Attack(find(s, "T-U3")))
    from cptcg.core.actions import Pick
    do(s, Pick((0,)))
    assert not s.over and len(s.gig[0]) == 6


def test_overtime_begins_once_both_players_started_a_turn_with_an_empty_fixer(reg):
    """CR 1.11.1 / 8.17."""
    s = board(reg, Side(deck=["T-U1"] * 5, fixer=[]), Side(deck=["T-U1"] * 5, fixer=[]), turns_taken=[6, 6])
    do(s, EndTurn())                 # player 1 begins with an empty fixer
    assert not s.overtime
    do(s, EndTurn())                 # player 0 begins with an empty fixer
    assert not s.overtime
    do(s, EndTurn())                 # ...and at the end of that turn Overtime begins
    assert s.overtime


def test_effect_sell_uses_the_sell_action(reg):
    """CR 11.9.2.2."""
    from cptcg.core.actions import Sell
    from cptcg.core.ops import _ctx
    s = board(reg, Side(hand=["T-P1", "T-P1"], field=["T-U1"]), Side())
    a, b = [i for i in s.z[Zone.HAND] if s.card(i).id == "T-P1"]
    assert Sell(a) in s.pending.options
    _ctx(s, find(s, "T-U1")).sell(a)
    from cptcg.core.engine import legal_actions
    s.pending = None
    from cptcg.core.steps import MainPhaseStep
    MainPhaseStep().run(s)
    assert Sell(b) not in legal_actions(s)


def test_adjusting_a_gig_off_its_faces_fails(reg):
    """CR 6.4.4 / 6.4.5."""
    from cptcg.core.ops import adjust_gig, set_gig
    s = board(reg, Side(gig=[(6, 3)]), Side())
    set_gig(s, 0, 0, 0, 8)
    assert s.gig[0] == [(6, 3)]
    adjust_gig(s, 0, 0, 0, +5)
    assert s.gig[0] == [(6, 3)]
    adjust_gig(s, 0, 0, 0, +2)
    assert s.gig[0] == [(6, 5)]
    set_gig(s, 0, 0, 0, 5)
    assert s.gig[0] == [(6, 5)]


def test_lag_clears_at_end_of_turn_and_units_can_attack_next_turn(reg):
    s = board(reg, Side(hand=["T-U3"], eddies=3, deck=["T-U1"] * 5), Side(deck=["T-U1"] * 5, gig=[(6, 3)]))
    u = find(s, "T-U3")
    do(s, Play(u))
    do(s, EndTurn())
    do(s, TakeGigDie(4))
    do(s, EndTurn())
    do(s, TakeGigDie(4))
    assert Attack(u) in s.pending.options
