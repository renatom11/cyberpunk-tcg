"""Attacking, fights, stealing and Blocker — docs/rules.md 'Attacking'."""
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, Block, Pass, Pick, Target
from cptcg.core.enums import TARGET_GIG, TARGET_UNIT, Zone
from cptcg.core.ops import steal_count


def test_steal_count_table():
    assert [steal_count(p) for p in (0, 1, 9, 10, 19, 20, 30)] == [0, 1, 1, 2, 2, 3, 4]


def test_ready_units_cannot_be_attacked_only_spent_ones(reg):
    s = board(reg, Side(field=["T-U3"]), Side(field=["T-U1", ("T-U2", {"spent": True})], gig=[(6, 3)]))
    do(s, Attack(find(s, "T-U3")))
    kinds = {(t.kind, s.card(t.inst).id if t.inst >= 0 else None) for t in s.pending.options}
    assert kinds == {(TARGET_UNIT, "T-U2"), (TARGET_GIG, None)}


def test_empty_gig_area_is_not_a_valid_target(reg):
    """CR 9.3.2.2. With one spent Unit and no Gigs there is exactly one target: the engine declares it."""
    s = board(reg, Side(field=["T-U3"]), Side(field=["T-U1", ("T-U2", {"spent": True})]))
    do(s, Attack(find(s, "T-U3")))
    assert s.i_zone[find(s, "T-U2")] == Zone.TRASH


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


def test_spent_blocker_cannot_block_but_a_lagged_one_can(reg):
    s = board(reg, Side(field=["T-U3"]), Side(field=[("T-U6", {"spent": True})], gig=[(6, 3)]))
    do(s, Attack(find(s, "T-U3")))
    do(s, Target(TARGET_GIG))
    assert s.gig[0] == [(6, 3)]                          # no reaction window opened at all
    s = board(reg, Side(field=["T-U3"]), Side(field=[("T-U6", {"lag": True})], gig=[(6, 3)]))
    do(s, Attack(find(s, "T-U3")))
    do(s, Target(TARGET_GIG))
    assert Block(find(s, "T-U6")) in s.pending.options   # CR 11.3.1: Lag only stops attacking and ⊡


def test_defender_may_block_again_after_a_redirect(reg):
    """CR 9.7 / 9.9.1: as many reactions as the defender wants; each BLOCKER replaces the target."""
    s = board(reg, Side(field=["T-U3"]), Side(field=["T-U6", "T-U6"], gig=[(6, 3)]))
    do(s, Attack(find(s, "T-U3")))
    do(s, Target(TARGET_GIG))
    first, second = [a.inst for a in s.pending.options if isinstance(a, Block)]
    do(s, Block(first))
    assert Block(second) in s.pending.options
    do(s, Block(second))                                 # only Pass is left, so the attack resolves
    assert s.i_zone[second] == Zone.TRASH and s.i_zone[first] == Zone.FIELD and s.gig[1] == [(6, 3)]


def test_zero_power_units_cannot_defeat_each_other(reg):
    """CR 9.19.2: a tie at 0 power is a loss for both, but neither can defeat the other."""
    from cptcg.core.ops import add_temp_power
    s = board(reg, Side(field=["T-U1"]), Side(field=[("T-U1", {"spent": True})]))
    a, t = find(s, "T-U1", player=0), find(s, "T-U1", player=1)
    add_temp_power(s, a, -99)
    add_temp_power(s, t, -99)
    do(s, Attack(a))
    do(s, Target(TARGET_UNIT, t))
    assert s.i_zone[a] == Zone.FIELD and s.i_zone[t] == Zone.FIELD


def test_gear_goes_with_defeated_host(reg):
    s = board(reg, Side(field=["T-U4"]), Side(field=[("T-U1", {"spent": True, "gear": ["T-G1"]})]))
    do(s, Attack(find(s, "T-U4")))
    do(s, Target(TARGET_UNIT, find(s, "T-U1")))
    assert s.i_zone[find(s, "T-G1")] == Zone.TRASH


def test_lagged_unit_cannot_attack_but_adrenaline_can(reg):
    s = board(reg, Side(field=[("T-U3", {"lag": True}), ("T-U5", {"lag": False})]), Side(gig=[(6, 3)]))
    attacks = {a.inst for a in s.pending.options if isinstance(a, Attack)}
    assert attacks == {find(s, "T-U5")}


def test_target_is_declared_before_the_attacker_is_spent(pool):
    """CR 9.3-9.5: choose the target, then spend the attacker; a 'when this Unit is spent' Gear
    effect (Zetatech Faceplate) resolves after the declaration and must survive dice moving."""
    from cptcg.core.actions import ChoiceKind
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["zetatech-faceplate"]})], gig=[(4, 2)]),
              Side(field=[("corpo-security", {"spent": True})], gig=[(6, 3)]))
    do(s, Attack(find(s, "psycho-squad")))
    assert s.pending.kind is ChoiceKind.TARGET                                       # target first
    do(s, Target(TARGET_GIG))
    assert s.pending.kind is ChoiceKind.PICK and "Adjust" in s.pending.prompt      # then the Faceplate
    do(s, Pick((len(s.pending.options) - 2,)))                                       # adjust the rival's die
    assert len(s.gig[0]) == 2
