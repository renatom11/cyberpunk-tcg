"""One scenario per scripted Program."""
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, Pick, Play, Target
from cptcg.core.enums import TARGET_GIG, TARGET_UNIT, Zone
from cptcg.core.ops import available, power

E = 9  # plenty of eddies


def play(s, cid):
    do(s, Play(find(s, cid, Zone.HAND)))
    return s


def test_wild_in_the_streets_defeats_a_spent_unit(pool):
    s = board(pool, Side(hand=["wild-in-the-streets"], eddies=E),
              Side(field=["psycho-squad", ("animals-wrecker", {"spent": True})]))
    play(s, "wild-in-the-streets")
    assert s.i_zone[find(s, "animals-wrecker")] == Zone.TRASH and s.i_zone[find(s, "psycho-squad")] == Zone.FIELD


def test_bonnie_and_clyde_defeats_two_when_behind_on_gigs(pool):
    s = board(pool, Side(hand=["bonnie-and-clyde"], eddies=E),
              Side(field=["corpo-security", "mox-inciters", "animals-wrecker"], gig=[(4, 1), (6, 1)]))
    play(s, "bonnie-and-clyde")
    assert max(len(o.picks) for o in s.pending.options) == 2
    do(s, Pick((0, 1)))
    assert len(s.units(1)) == 1


def test_carnage_costs_less_per_8plus_gig_and_kills_weaker_unit(pool):
    s = board(pool, Side(hand=["carnage-at-the-colosseum"], field=["animals-wrecker"], eddies=4,
                         gig=[(10, 9), (12, 8)]), Side(field=["psycho-squad"]))
    play(s, "carnage-at-the-colosseum")                      # cost 6 - 2 = 4
    assert available(s, 0) == 0 and s.i_zone[find(s, "psycho-squad")] == Zone.TRASH


def test_over_the_edge_uses_friendly_d20(pool):
    s = board(pool, Side(hand=["over-the-edge"], eddies=E, gig=[(20, 6)]),
              Side(field=["psycho-squad", "animals-wrecker"]))
    play(s, "over-the-edge")
    assert s.i_zone[find(s, "psycho-squad")] == Zone.TRASH             # power 6 <= 6, only option


def test_dont_fear_the_reaper_spends_all_then_defeats_one(pool):
    s = board(pool, Side(hand=["dont-fear-the-reaper"], eddies=E), Side(field=["psycho-squad", "corpo-security"]))
    play(s, "dont-fear-the-reaper")
    assert all(s.i_spent[u] for u in s.units(1)) and len(s.pending.options) == 2
    do(s, Pick((0,)))
    assert len(s.units(1)) == 1


def test_live_with_the_aftermath_each_player_defeats_one(pool):
    s = board(pool, Side(hand=["live-with-the-aftermath"], eddies=E, field=["psycho-squad"]),
              Side(field=["corpo-security"]))
    play(s, "live-with-the-aftermath")
    assert s.units(0) == [] and s.units(1) == []


def test_les_elemens_bottom_decks_lowest_power(pool):
    s = board(pool, Side(hand=["les-elemens"], eddies=E), Side(field=["animals-wrecker", "corpo-security"], deck=["floor-it"]))
    play(s, "les-elemens")
    assert s.zone(1, Zone.DECK)[0] == find(s, "corpo-security")


def test_unlikely_bond(pool):
    s = board(pool, Side(hand=["unlikely-bond"], eddies=E, field=["psycho-squad"]),
              Side(field=[("corpo-security", {"spent": True})]))
    play(s, "unlikely-bond")
    do(s, Pick((0,)))
    assert s.i_zone[find(s, "psycho-squad")] == Zone.DECK and s.i_zone[find(s, "corpo-security")] == Zone.DECK


def test_corporate_surveillance_spends_cheap_unit(pool):
    s = board(pool, Side(hand=["corporate-surveillance"], eddies=E), Side(field=["corpo-security", "animals-wrecker"]))
    play(s, "corporate-surveillance")
    assert s.i_spent[find(s, "corpo-security")] and not s.i_spent[find(s, "animals-wrecker")]


def test_memory_relapse_spends_and_locks_and_draws_on_even_cred(pool):
    s = board(pool, Side(hand=["memory-relapse"], eddies=E, gig=[(6, 4)], deck=["floor-it"]),
              Side(field=["psycho-squad"], deck=["floor-it"] * 3))
    play(s, "memory-relapse")
    u = find(s, "psycho-squad")
    assert s.i_spent[u] and len(s.zone(0, Zone.HAND)) == 1
    do(s, __import__("cptcg.core.actions", fromlist=["EndTurn"]).EndTurn())
    from cptcg.core.actions import TakeGigDie
    do(s, TakeGigDie(4))
    assert s.i_spent[u] == 1                              # didn't ready on the rival's turn


def test_chrome_reverie_locks_attacker_and_may_call(pool):
    s = board(pool, Side(hand=["chrome-reverie"], eddies=E, gig=[(6, 1)], legends=["saburo-arasaka-stubborn-patriarch", "kerry-eurodyne-axe-attitude-audience", "river-ward-detective-on-the-hunt"]),
              Side(field=["psycho-squad"]))
    play(s, "chrome-reverie")
    do(s, Pick((0,)))                                       # call a legend for free (min gig)
    assert sum(s.i_faceup[i] for i in s.legends(0)) == 1 and available(s, 0) == E   # paid 3, +3 Legends
    assert s.has_mod("cant_attack", find(s, "psycho-squad"))


def test_all_is_lost(pool):
    s = board(pool, Side(hand=["all-is-lost"], eddies=E, deck=["floor-it", "psycho-squad", "floor-it", "corpo-security"]), Side())
    play(s, "all-is-lost")
    do(s, Pick((0,)))
    assert len(s.zone(0, Zone.HAND)) == 1 and len(s.zone(0, Zone.TRASH)) == 3


def test_the_heist_free_play_when_cost_matches_gig(pool):
    s = board(pool, Side(hand=["the-heist"], eddies=2, field=["psycho-squad"], gig=[(4, 2)],
                         deck=["floor-it", "satori-sword-of-saburo", "floor-it", "floor-it"]), Side())
    play(s, "the-heist")                                    # trash 4; Satori (cost 2) matches the d4=2
    do(s, Pick((0,)))                                       # only one Gear: taken automatically; yes, play it free
    assert s.i_host[find(s, "satori-sword-of-saburo")] == find(s, "psycho-squad") and available(s, 0) == 0


def test_fool_on_the_hill_rival_chooses(pool):
    s = board(pool, Side(hand=["fool-on-the-hill"], eddies=E, deck=["floor-it"] * 4), Side())
    play(s, "fool-on-the-hill")
    assert s.pending.player == 1
    do(s, Pick((1,)))                                       # trash them -> draw 2
    assert len(s.zone(0, Zone.TRASH)) == 3 and len(s.zone(0, Zone.HAND)) == 2


def test_shattered_memories(pool):
    s = board(pool, Side(hand=["shattered-memories", "floor-it"], eddies=E, gig=[(4, 3)], deck=["floor-it"] * 7),
              Side(hand=["floor-it", "floor-it"], deck=["floor-it"] * 5))
    play(s, "shattered-memories")                           # 1 + 2 discarded = 3 = friendly gig -> draw 2 more
    assert len(s.zone(0, Zone.HAND)) == 7 and len(s.zone(1, Zone.HAND)) == 5


def test_three_mouths_extra_per_min_gig(pool):
    s = board(pool, Side(hand=["three-mouths-one-desire"], eddies=E, gig=[(4, 1)], deck=["floor-it"] * 5), Side())
    play(s, "three-mouths-one-desire")
    assert max(len(o.picks) for o in s.pending.options) == 2


def test_towerfall_both_when_behind(pool):
    s = board(pool, Side(hand=["towerfall"], eddies=E, gig=[(4, 1)]),
              Side(field=["psycho-squad", "corpo-security"], gig=[(20, 20)], deck=["floor-it"]))
    play(s, "towerfall")
    assert power(s, find(s, "psycho-squad")) == 1 and s.i_zone[find(s, "corpo-security")] == Zone.DECK


def test_pyramid_song(pool):
    s = board(pool, Side(hand=["pyramid-song"], eddies=E, gig=[(6, 3)]), Side(field=["psycho-squad"]))
    play(s, "pyramid-song")
    do(s, Pick((0,)))                                       # -4 power
    assert power(s, find(s, "psycho-squad")) == 2


def test_gunpoint_diplomacy_rival_chooses_when_behind(pool):
    s = board(pool, Side(hand=["gunpoint-diplomacy"], eddies=E, field=["psycho-squad"], gig=[(4, 1)]),
              Side(gig=[(20, 20)]))
    play(s, "gunpoint-diplomacy")
    assert s.pending.player == 1
    do(s, Pick((1,)))
    assert power(s, find(s, "psycho-squad")) == 9


def test_nocturne_costs_one_with_empty_fixer(pool):
    s = board(pool, Side(hand=["nocturne-op55n1"], eddies=1, fixer=[], deck=["floor-it"] * 2), Side())
    play(s, "nocturne-op55n1")
    do(s, Pick((0,)))
    assert len(s.zone(0, Zone.HAND)) == 2


def test_we_gotta_live_together(pool):
    s = board(pool, Side(hand=["we-gotta-live-together"], eddies=3, gig=[], trash=["corpo-security", "psycho-squad", "jacked-in-voodoo-boy"]),
              Side(gig=[(4, 1), (6, 1)]))
    play(s, "we-gotta-live-together")                       # rival 2+ gigs ahead: costs 3
    do(s, Pick((0, 1)))
    assert len(s.units(0)) == 2 and available(s, 0) == 0


def test_appetite_for_destruction_steals_on_big_win(pool):
    s = board(pool, Side(hand=["appetite-for-destruction"], eddies=E, field=["animals-wrecker"]),
              Side(field=[("corpo-security", {"spent": True})], gig=[(6, 3)]))
    play(s, "appetite-for-destruction")
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Target(TARGET_UNIT, find(s, "corpo-security")))
    assert s.gig[0] == [(6, 3)]


def test_bootleg_black_sapphire_show(pool):
    s = board(pool, Side(hand=["bootleg-black-sapphire-show"], eddies=E, gig=[(4, 2), (6, 3)], deck=["floor-it"] * 3), Side())
    play(s, "bootleg-black-sapphire-show")
    assert len(s.zone(0, Zone.EDDIES)) == E + 1 and len(s.zone(0, Zone.HAND)) == 2


def test_floor_it_quick_in_reaction_window(pool):
    s = board(pool, Side(field=["animals-wrecker"]), Side(hand=["floor-it"], eddies=1, gig=[(6, 3)], deck=["floor-it"]))
    do(s, Attack(find(s, "animals-wrecker")))
    assert any(isinstance(a, Play) for a in s.pending.options) and s.pending.player == 1
    play(s, "floor-it")
    assert power(s, find(s, "animals-wrecker")) == 9 and len(s.zone(1, Zone.HAND)) == 1


def test_detonate(pool):
    s = board(pool, Side(hand=["detonate"], eddies=E), Side(field=[("psycho-squad", {"gear": ["mantis-blades"]})]))
    play(s, "detonate")
    assert s.i_zone[find(s, "mantis-blades")] == Zone.TRASH


def test_synapse_burnout_only_while_fighting_units(pool):
    s = board(pool, Side(hand=["synapse-burnout"], eddies=E, field=["corpo-security"],
                         legends=[("padre-man-of-the-cross", {"faceup": True}), ("dum-dum-maelstrom-triggerman", {"faceup": True}), "muamar-reyes-el-capitan"]), Side())
    play(s, "synapse-burnout")
    from cptcg.core.ops import FIGHTING, VS_UNIT
    u = find(s, "corpo-security")
    assert power(s, u) == 2 and power(s, u, FIGHTING | VS_UNIT) == 4


def test_take_control(pool):
    s = board(pool, Side(field=["animals-wrecker"]), Side(hand=["take-control"], eddies=2, gig=[(6, 3), (8, 4)], deck=["floor-it"]))
    do(s, Attack(find(s, "animals-wrecker")))               # power 10 would steal 2
    play(s, "take-control")                                 # only reaction left: window auto-closes
    do(s, Pick((0,)))
    assert len(s.gig[0]) == 1


def test_reboot_optics_saves_defender(pool):
    s = board(pool, Side(field=["animals-wrecker"]), Side(hand=["reboot-optics"], eddies=2, field=[("corpo-security", {"spent": True})]))
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Target(TARGET_UNIT, find(s, "corpo-security")))
    play(s, "reboot-optics")
    assert s.i_zone[find(s, "corpo-security")] == Zone.FIELD


def test_safety_override_trades(pool):
    s = board(pool, Side(field=["animals-wrecker"]), Side(hand=["safety-override"], eddies=2, field=[("corpo-security", {"spent": True})]))
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Target(TARGET_UNIT, find(s, "corpo-security")))
    play(s, "safety-override")
    assert s.i_zone[find(s, "corpo-security")] == Zone.TRASH and s.i_zone[find(s, "animals-wrecker")] == Zone.TRASH


def test_cyberpsychosis_buffs_then_kills_at_end_of_turn(pool):
    s = board(pool, Side(hand=["cyberpsychosis"], eddies=E, field=[("corpo-security", {"gear": ["mantis-blades"]})], deck=["floor-it"]),
              Side(gig=[(6, 3)], deck=["floor-it"]))
    play(s, "cyberpsychosis")
    u = find(s, "corpo-security")
    assert power(s, u) == 2 + 2 + 3
    # Corpo Security can't attack, so simulate the trigger via a fight is impossible; use steal event directly.
    from cptcg.core.steps import do_steal
    do_steal(s, u, 0, 0)
    from cptcg.core.actions import EndTurn
    do(s, EndTurn())
    assert s.i_zone[u] == Zone.TRASH


def test_program_is_outside_every_area_while_it_resolves(pool):
    """CR 4.14.2: not in the trash until its effect has resolved."""
    from cptcg.core.actions import Play
    s = board(pool, Side(hand=["wild-in-the-streets"], eddies=E,
                         field=[("corpo-security", {"spent": True})]),
              Side(field=[("ruthless-lowlife", {"spent": True})]))
    prog = find(s, "wild-in-the-streets")
    do(s, Play(prog))
    assert s.pending is not None and s.i_zone[prog] == Zone.LIMBO
    assert prog not in s.z[Zone.TRASH]
    do(s, Pick((0,)))
    assert s.i_zone[prog] == Zone.TRASH
