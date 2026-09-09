"""Attacking, fights, stealing and Blocker — docs/rules.md 'Attacking'."""
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, Block, Pass, Pick, Target
from cptcg.core.enums import TARGET_GIG, TARGET_UNIT, Zone
from cptcg.core.ops import steal_count


def test_steal_count_table():
    assert [steal_count(p) for p in (0, 1, 9, 10, 19, 20, 30)] == [0, 1, 1, 2, 2, 3, 4]


def test_ready_units_cannot_be_attacked_only_spent_ones(reg):
    s = board(reg, Side(field=["T-U3"]), Side(field=["T-U1", ("T-U2", {"spent": True})]))
    do(s, Attack(find(s, "T-U3")))
    kinds = {(t.kind, s.card(t.inst).id if t.inst >= 0 else None) for t in s.pending.options}
    assert kinds == {(TARGET_UNIT, "T-U2"), (TARGET_GIG, None)}


def test_fight_higher_power_wins_tie_defeats_both(reg):
    # Solo (5) attacks spent Bruiser (7): Solo is defeated.
    s = board(reg, Side(field=["T-U3"]), Side(field=[("T-U4", {"spent": True})]))
    solo, bruiser = find(s, "T-U3"), find(s, "T-U4")
    do(s, Attack(solo))
    do(s, Target(TARGET_UNIT, bruiser))
    assert s.i_zone[solo] == Zone.TRASH and s.i_zone[bruiser] == Zone.FIELD
    # Tie: Thug (3) vs Thug (3) -> both defeated.
    s = board(reg, Side(field=["T-U2"]), Side(field=[("T-U2", {"spent": True})]))
    a, b = find(s, "T-U2", player=0), find(s, "T-U2", player=1)
    do(s, Attack(a))
    do(s, Target(TARGET_UNIT, b))
    assert s.i_zone[a] == Zone.TRASH and s.i_zone[b] == Zone.TRASH


def test_attacker_is_spent_and_cannot_attack_twice(reg):
    s = board(reg, Side(field=["T-U3"]), Side(gig=[(6, 4)]))
    u = find(s, "T-U3")
    do(s, Attack(u))
    assert s.i_spent[u] == 1
    assert Attack(u) not in s.pending.options


def test_gig_attack_steals_one_die_and_keeps_its_value(reg):
    s = board(reg, Side(field=["T-U3"]), Side(gig=[(8, 7)]))
    do(s, Attack(find(s, "T-U3")))          # single target (gig area) auto-declared
    assert s.gig[0] == [(8, 7)] and s.gig[1] == []
    assert s.street_cred(0) == 7


def test_gig_attack_lets_attacker_choose_which_die(reg):
    s = board(reg, Side(field=["T-U3"]), Side(gig=[(4, 1), (12, 11)]))
    do(s, Attack(find(s, "T-U3")))
    assert [o.picks for o in s.pending.options] == [(0,), (1,)]
    do(s, Pick((1,)))
    assert s.gig[0] == [(12, 11)] and s.gig[1] == [(4, 1)]


def test_power_10_steals_two_gigs(reg):
    s = board(reg, Side(field=["T-U8"]), Side(gig=[(4, 2), (6, 3), (8, 5)]))
    do(s, Attack(find(s, "T-U8")))
    assert len(s.pending.options) == 3                   # C(3,2)
    do(s, Pick((0, 2)))
    assert sorted(s.gig[0]) == [(4, 2), (8, 5)] and s.gig[1] == [(6, 3)]


def test_power_0_steals_nothing(reg):
    s = board(reg, Side(field=["T-U9"]), Side(gig=[(6, 3)]))
    do(s, Attack(find(s, "T-U9")))
    assert s.gig[1] == [(6, 3)] and s.gig[0] == []


def test_gear_adds_power(reg):
    s = board(reg, Side(field=[("T-U3", {"gear": ["T-G2", "T-G3"]})]), Side(gig=[(4, 2), (6, 3)]))
    do(s, Attack(find(s, "T-U3")))                       # 5 + 2 + 3 = 10 -> steals both
    assert len(s.gig[0]) == 2 and s.gig[1] == []


def test_blocker_redirects_gig_attack_and_no_gig_is_stolen(reg):
    s = board(reg, Side(field=["T-U3"]), Side(field=["T-U6"], gig=[(6, 3)]))
    solo, guard = find(s, "T-U3"), find(s, "T-U6")
    do(s, Attack(solo))
    assert set(s.pending.options) == {Pass(), Block(guard)}
    do(s, Block(guard))
    assert s.i_zone[guard] == Zone.TRASH                 # Guard (2) lost to Solo (5)
    assert s.i_zone[solo] == Zone.FIELD
    assert s.gig[1] == [(6, 3)]                          # redirected: nothing stolen


def test_pass_lets_the_steal_through(reg):
    s = board(reg, Side(field=["T-U3"]), Side(field=["T-U6"], gig=[(6, 3)]))
    do(s, Attack(find(s, "T-U3")))
    do(s, Pass())
    assert s.gig[0] == [(6, 3)]


def test_spent_or_lagged_blocker_cannot_block(reg):
    s = board(reg, Side(field=["T-U3"]),
              Side(field=[("T-U6", {"spent": True}), ("T-U7", {"lag": True})], gig=[(6, 3)]))
    do(s, Attack(find(s, "T-U3")))
    do(s, Target(TARGET_GIG))
    assert s.gig[0] == [(6, 3)]                          # no reaction window opened at all


def test_gear_goes_with_defeated_host(reg):
    s = board(reg, Side(field=["T-U4"]), Side(field=[("T-U1", {"spent": True, "gear": ["T-G1"]})]))
    do(s, Attack(find(s, "T-U4")))
    do(s, Target(TARGET_UNIT, find(s, "T-U1")))
    assert s.i_zone[find(s, "T-G1")] == Zone.TRASH


def test_lagged_unit_cannot_attack_but_adrenaline_can(reg):
    s = board(reg, Side(field=[("T-U3", {"lag": True}), ("T-U5", {"lag": False})]), Side(gig=[(6, 3)]))
    attacks = {a.inst for a in s.pending.options if isinstance(a, Attack)}
    assert attacks == {find(s, "T-U5")}
