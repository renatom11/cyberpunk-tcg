"""One scenario per scripted static / event / Gear card (batch 3)."""
from conftest import Side, board, defeat_now, do, during_main, find

from cptcg.core.actions import Activate, Attack, Block, EndTurn, Pass, Pick, Play, TakeGigDie, Target
from cptcg.core.enums import NO_INST, TARGET_GIG, TARGET_UNIT, Keyword, Zone
from cptcg.core.ops import (ATTACKING, FIGHTING, VS_LEGEND, VS_UNIT, available, has_keyword,
                            play_cost, power)

E = 9
L3 = ["padre-man-of-the-cross", "wakako-okada-peace-and-harmony", "muamar-reyes-el-capitan"]


def attacks(s):
    return {a.inst for a in s.pending.options if isinstance(a, Attack)}


def test_corpo_security_cannot_attack_but_blocks(pool):
    s = board(pool, Side(field=["corpo-security"]), Side(gig=[(4, 1)]))
    assert attacks(s) == set()


def test_misty_end_of_turn_reveal(pool):
    s = board(pool, Side(field=["misty-olszewski-mender-of-broken-spirits"], eddies=1, spent_eddies=1, deck=["psycho-squad", "floor-it"]),
              Side(deck=["floor-it"]))
    assert attacks(s) == set()
    do(s, EndTurn())
    do(s, Pick((0,)))                                       # choose Unit; top is Floor It (Program) -> trashed
    assert len(s.zone(0, Zone.TRASH)) == 1


def test_ruthless_lowlife_cant_attack_gigs(pool):
    s = board(pool, Side(field=["ruthless-lowlife"]), Side(field=[("psycho-squad", {"spent": True})], gig=[(4, 1)]))
    do(s, Attack(find(s, "ruthless-lowlife")))              # only target: the spent Unit (auto)
    assert s.i_zone[find(s, "ruthless-lowlife")] == Zone.TRASH    # 4 < 6
    s = board(pool, Side(field=["ruthless-lowlife"]), Side(gig=[(4, 1)]))
    assert attacks(s) == set()


def test_valentino_guerrera_hits_ready_blockers_with_more_cred(pool):
    s = board(pool, Side(field=["valentino-guerrera"], gig=[(6, 5)]), Side(field=["corpo-security"], gig=[(4, 1)]))
    do(s, Attack(find(s, "valentino-guerrera")))
    assert Target(TARGET_UNIT, find(s, "corpo-security")) in s.pending.options


def test_mtod12_unblockable_when_behind(pool):
    s = board(pool, Side(field=["mtod12-flathead"], gig=[(4, 1)]), Side(field=["corpo-security"], gig=[(6, 5)]))
    do(s, Attack(find(s, "mtod12-flathead")))               # no Block offered -> auto-resolves
    assert len(s.gig[0]) == 2


def test_maxtac_suppression_stops_adrenaline(pool):
    s = board(pool, Side(hand=["riding-nomad"], eddies=E), Side(field=["maxtac-suppression-team"], gig=[(4, 1)]))
    do(s, Play(find(s, "riding-nomad", Zone.HAND)))
    assert attacks(s) == set()


def test_jacked_in_needs_a_program(pool):
    s = board(pool, Side(field=["jacked-in-voodoo-boy"], hand=["floor-it"], eddies=E, deck=["floor-it"]), Side(field=["psycho-squad"], gig=[(4, 1)]))
    assert attacks(s) == set()
    do(s, Play(find(s, "floor-it", Zone.HAND)))
    assert attacks(s) == {find(s, "jacked-in-voodoo-boy")}


def test_nadia_attacks_gigs_when_behind(pool):
    s = board(pool, Side(hand=["nadia-fighting-through-grief"], eddies=E, gig=[(4, 1)]), Side(gig=[(4, 1), (6, 1)]))
    do(s, Play(find(s, "nadia-fighting-through-grief", Zone.HAND)))
    assert attacks(s) == {find(s, "nadia-fighting-through-grief")}


def test_self_cost_reductions(pool):
    s = board(pool, Side(hand=["octant", "maxtac-heavy", "trauma-team-operatives", "zetatech-berserk"], eddies=E,
                         gig=[(10, 9), (12, 8)], trash=["psycho-squad", "corpo-security"],
                         legends=[(l, {"faceup": True}) for l in L3], field=["psycho-squad"]),
              Side(field=["psycho-squad", "corpo-security", "mox-inciters"]))
    assert play_cost(s, 0, find(s, "octant", Zone.HAND)) == 5                  # 7 - 2
    assert play_cost(s, 0, find(s, "maxtac-heavy", Zone.HAND)) == 4            # 7 - 3
    assert play_cost(s, 0, find(s, "trauma-team-operatives", Zone.HAND)) == 4  # 6 - 2
    assert play_cost(s, 0, find(s, "zetatech-berserk", Zone.HAND)) == 3        # 6 - 3


def test_viktor_first_cyberware_discount_once_per_turn(pool):
    s = board(pool, Side(hand=["gorilla-arms", "mantis-blades"], eddies=E, field=["viktor-vektor-drop-your-illusions"]), Side())
    v = find(s, "viktor-vektor-drop-your-illusions")
    assert play_cost(s, 0, find(s, "gorilla-arms", Zone.HAND)) == 1
    do(s, Play(find(s, "gorilla-arms", Zone.HAND), v))
    assert available(s, 0) == E - 1
    assert play_cost(s, 0, find(s, "mantis-blades", Zone.HAND)) == 1           # printed 1, no discount left


def test_riot_shield_taxes_rival_go_solo(pool):
    s = board(pool, Side(legends=[("v-streetkid", {"faceup": True}), "padre-man-of-the-cross", "wakako-okada-peace-and-harmony"], eddies=E),
              Side(field=[("psycho-squad", {"gear": ["riot-shield"]})]))
    assert play_cost(s, 0, find(s, "v-streetkid"), go_solo=True) == 7
    from cptcg.core.enums import Keyword
    from cptcg.core.ops import has_keyword
    assert has_keyword(s, find(s, "psycho-squad"), Keyword.BLOCKER)


def test_saul_bright_aura_and_end_turn_ready(pool):
    s = board(pool, Side(field=["saul-bright-stormrider", ("corpo-security", {"spent": True}), ("psycho-squad", {"spent": True})]), Side(deck=["floor-it"]))
    u = find(s, "psycho-squad")
    assert power(s, u) == 6 and power(s, u, ATTACKING) == 8 and power(s, find(s, "saul-bright-stormrider"), ATTACKING) == 14
    do(s, EndTurn())
    do(s, Pick((0, 1)))
    assert not s.i_spent[u]


def test_saburo_arasaka_aura(pool):
    s = board(pool, Side(field=["minotaur", "psycho-squad"], legends=[("saburo-arasaka-stubborn-patriarch", {"faceup": True})]), Side())
    assert power(s, find(s, "minotaur"), ATTACKING) == 10 and power(s, find(s, "psycho-squad"), ATTACKING) == 6


def test_meredith_vs_legend_and_gig_change(pool):
    s = board(pool, Side(field=["meredith-stout-stone-cold-corpo"], gig=[(6, 3)], trash=["floor-it"]),
              Side(hand=["trust-no-one"], eddies=E))
    m = find(s, "meredith-stout-stone-cold-corpo")
    assert power(s, m, FIGHTING | VS_LEGEND) == 7 and power(s, m, FIGHTING | VS_UNIT) == 5
    s.active = 1
    during_main(s, lambda st: None)
    do(s, Play(find(s, "trust-no-one", Zone.HAND)))
    do(s, Pick((0,)))                                       # (Meredith's owner's d6, -2)
    assert s.pending.player == 0                            # Meredith: add a card from trash?
    do(s, Pick((0,)))
    assert len(s.zone(0, Zone.HAND)) == 1


def test_royce_power_per_gear_on_own_turn(pool):
    s = board(pool, Side(field=[("royce-psycho-on-the-edge", {"faceup": True, "gear": ["mantis-blades", "satori-sword-of-saburo"]})]), Side())
    r = find(s, "royce-psycho-on-the-edge")
    assert power(s, r) == 6 + 4 + 4
    s.active = 1
    assert power(s, r) == 6 + 4


def test_johnny_beats_corpo_and_readies(pool):
    s = board(pool, Side(field=["johnny-silverhand-never-stop-fighting"]), Side(field=[("minotaur", {"spent": True})]))
    j = find(s, "johnny-silverhand-never-stop-fighting")
    do(s, Attack(j))                                        # 8 vs 9; Minotaur isn't CORPO
    do(s, Target(TARGET_UNIT, find(s, "minotaur")))
    assert s.i_zone[j] == Zone.TRASH
    s = board(pool, Side(field=["johnny-silverhand-never-stop-fighting"]), Side(field=[("meredith-stout-stone-cold-corpo", {"spent": True, "gear": ["gorilla-arms", "gorilla-arms", "gorilla-arms"]})]))
    j = find(s, "johnny-silverhand-never-stop-fighting")
    do(s, Attack(j))                                        # 8 vs 14 but CORPO: Johnny wins and readies
    do(s, Target(TARGET_UNIT, find(s, "meredith-stout-stone-cold-corpo")))
    assert s.i_zone[find(s, "meredith-stout-stone-cold-corpo")] == Zone.TRASH and not s.i_spent[j]


def test_modded_kusanagi_returns(pool):
    s = board(pool, Side(field=["modded-kusanagi"]), Side(deck=["floor-it"]))
    do(s, EndTurn())
    assert s.i_zone[find(s, "modded-kusanagi")] == Zone.HAND


def test_modded_muramasa_readies_when_behind(pool):
    s = board(pool, Side(field=[("modded-muramasa", {"spent": True})], gig=[(4, 1)]), Side(gig=[(6, 5)], deck=["floor-it"]))
    do(s, EndTurn())
    assert not s.i_spent[find(s, "modded-muramasa")]


def test_maxtac_squadron_readies_legend(pool):
    s = board(pool, Side(field=[("maxtac-squadron", {"spent": True})], legends=[("padre-man-of-the-cross", {"faceup": True, "spent": True})]), Side(deck=["floor-it"]))
    do(s, EndTurn())
    assert not s.i_spent[find(s, "padre-man-of-the-cross")]


def test_delamain_cab_readies_eddie_after_stealing(pool):
    s = board(pool, Side(field=["delamain-cab"], eddies=1, spent_eddies=1), Side(gig=[(4, 1)], deck=["floor-it"]))
    do(s, Attack(find(s, "delamain-cab")))
    do(s, EndTurn())
    assert available(s, 0) == 1


def test_v_roamer_end_turn_draw(pool):
    s = board(pool, Side(field=["v-roamer-of-the-badlands"], gig=[(10, 9), (12, 8)], deck=["floor-it"]), Side(deck=["floor-it"]))
    do(s, EndTurn())
    assert len(s.zone(0, Zone.HAND)) == 1


def test_wraith_marauders_readies_matching_power(pool):
    s = board(pool, Side(field=["wraith-marauders", ("psycho-squad", {"spent": True})]), Side(gig=[(6, 6)]))
    do(s, Attack(find(s, "wraith-marauders")))
    assert not s.i_spent[find(s, "psycho-squad")]


def test_maelstrom_goons_equipped_discard(pool):
    s = board(pool, Side(field=[("maelstrom-goons", {"gear": ["mantis-blades"]})]), Side(gig=[(4, 1)], hand=["floor-it"]))
    do(s, Attack(find(s, "maelstrom-goons")))
    assert len(s.zone(1, Zone.HAND)) == 0


def test_maelstrom_zealots_trade_on_loss(pool):
    s = board(pool, Side(field=["animals-wrecker"]), Side(field=[("maelstrom-zealots", {"spent": True})]))
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Target(TARGET_UNIT, find(s, "maelstrom-zealots")))
    assert s.i_zone[find(s, "animals-wrecker")] == Zone.TRASH


def test_la_llorona_blocks_and_pumps_gig(pool):
    s = board(pool, Side(field=["corpo-security"], gig=[(6, 2)]), Side(field=["la-llorona-ghost-of-the-past"], gig=[(4, 1)]))
    # give corpo security a way to attack: use Animals Wrecker instead
    s = board(pool, Side(field=["animals-wrecker"], gig=[(6, 2)]), Side(field=["la-llorona-ghost-of-the-past"], gig=[(4, 1)]))
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Block(find(s, "la-llorona-ghost-of-the-past")))
    do(s, Pick((2,)))                                       # (own d4, +3)
    assert s.gig[1] == [(4, 4)]


def test_augmented_negotiators_block_discard(pool):
    s = board(pool, Side(field=["animals-wrecker"], hand=["floor-it"]), Side(field=["augmented-negotiators"], gig=[(4, 1)]))
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Block(find(s, "augmented-negotiators")))
    assert len(s.zone(0, Zone.HAND)) == 0


def test_rita_wheeler_loots_on_first_spend(pool):
    s = board(pool, Side(field=["rita-wheeler-no-stupid-questions"], hand=["floor-it"], deck=["psycho-squad"]), Side(gig=[(4, 1)]))
    do(s, Attack(find(s, "rita-wheeler-no-stupid-questions")))
    do(s, Pick((0,)))                                       # discard Floor It
    assert [s.card(i).id for i in s.zone(0, Zone.HAND)] == ["psycho-squad"]


def test_alt_mother_of_daemons_prevents_steal_and_draws(pool):
    s = board(pool, Side(field=["animals-wrecker"]),
              Side(field=[("alt-cunningham-mother-of-daemons", {"gear": ["mantis-blades"]})], gig=[(4, 3)], hand=["chrome-reverie"], deck=["floor-it"]))
    do(s, Attack(find(s, "animals-wrecker")))
    assert s.pending.player == 1
    do(s, Pick((0,)))                                       # discard Chrome Reverie (cost 3 == d4 value)
    assert s.gig[1] == [(4, 3)] and s.gig[0] == []


def test_gorilla_arms_extra_steal(pool):
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["gorilla-arms"]})], gig=[(4, 2)]), Side(gig=[(6, 2), (8, 5)]))
    do(s, Attack(find(s, "psycho-squad")))
    do(s, Pick((0,)))                                       # steal the d6=2
    assert len(s.gig[0]) == 3                               # then the 5 (not shared) automatically


def test_adrenaline_converter_grants_adrenaline_only_when_2_gigs_behind(pool):
    def equipped(rival_gigs):
        s = board(pool, Side(hand=["adrenaline-converter"], eddies=E, gig=[(4, 1)],
                             field=[("psycho-squad", {"lag": True})]),
                  Side(gig=rival_gigs))
        host = find(s, "psycho-squad")
        do(s, Play(find(s, "adrenaline-converter", Zone.HAND), host))
        return s, host

    s, host = equipped([(4, 1), (6, 2), (8, 3)])            # 3 rival Gigs to my 1
    assert has_keyword(s, host, Keyword.ADRENALINE) and Attack(host) in s.pending.options
    s, host = equipped([(4, 1), (6, 2)])                    # only 1 more: no ADRENALINE
    assert not has_keyword(s, host, Keyword.ADRENALINE) and Attack(host) not in s.pending.options


def test_zetatech_faceplate_on_spend(pool):
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["zetatech-faceplate"]})], gig=[(4, 1), (6, 2), (10, 7)], deck=["floor-it"]),
              Side(gig=[(8, 3)]))
    do(s, Attack(find(s, "psycho-squad")))
    do(s, Pick((2,)))                                       # (d6, +1) -> values 1,3,7 -> draw
    assert len(s.zone(0, Zone.HAND)) == 1


def test_tetratronic_rippler_may_trash_top(pool):
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["tetratronic-rippler"]})], deck=["floor-it"]), Side(gig=[(4, 1)]))
    do(s, Attack(find(s, "psycho-squad")))
    do(s, Pick((0,)))
    assert len(s.zone(0, Zone.TRASH)) == 1


def test_netwatch_netdriver_draws_on_spend(pool):
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["netwatch-netdriver"]})], deck=["floor-it"]), Side(gig=[(4, 1)]))
    do(s, Attack(find(s, "psycho-squad")))
    assert len(s.zone(0, Zone.HAND)) == 1


def test_arasaka_radioport_calls_arasaka_legend(pool):
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["arasaka-emergency-radioport"]})],
                         legends=["saburo-arasaka-stubborn-patriarch", "padre-man-of-the-cross", "wakako-okada-peace-and-harmony"]), Side(gig=[(4, 1)]))
    do(s, Attack(find(s, "psycho-squad")))
    do(s, Pick((0,)))                                       # look at Saburo
    do(s, Pick((0,)))                                       # call it free
    assert s.i_faceup[find(s, "saburo-arasaka-stubborn-patriarch")]


def test_sandevistan_readies_host(pool):
    s = board(pool, Side(field=[("psycho-squad", {"spent": True, "gear": ["sandevistan"]})]), Side(deck=["floor-it"]))
    do(s, EndTurn())
    assert not s.i_spent[find(s, "psycho-squad")]


def test_satori_draws_on_fight_win(pool):
    s = board(pool, Side(field=[("animals-wrecker", {"gear": ["satori-sword-of-saburo"]})], deck=["floor-it"]), Side(field=[("corpo-security", {"spent": True})]))
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Target(TARGET_UNIT, find(s, "corpo-security")))
    assert len(s.zone(0, Zone.HAND)) == 1


def test_deadman_transmitter_saves_host(pool):
    s = board(pool, Side(field=["animals-wrecker"]), Side(field=[("corpo-security", {"spent": True, "gear": ["deadman-transmitter"]})]))
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Target(TARGET_UNIT, find(s, "corpo-security")))
    assert s.i_zone[find(s, "corpo-security")] == Zone.FIELD and s.i_zone[find(s, "deadman-transmitter")] == Zone.TRASH


def test_overwatch_quick_ability(pool):
    s = board(pool, Side(field=["animals-wrecker", ("psycho-squad", {"spent": True})]),
              Side(field=[("corpo-security", {"gear": ["overwatch-panams-gift"]})], eddies=1, hand=["towerfall"], gig=[(4, 1)]))
    do(s, Attack(find(s, "animals-wrecker")))
    g = find(s, "overwatch-panams-gift")
    assert Activate(g, 0) in s.pending.options
    do(s, Activate(g, 0))
    do(s, Pick((0,)))                                       # discard Towerfall (auto); defeat the attacker (cost 6)
    assert s.i_zone[find(s, "animals-wrecker")] == Zone.TRASH and s.i_spent[g]
