"""One scenario per scripted Unit/Gear trigger (batch 2)."""
from conftest import Side, board, defeat_now, do, find

from cptcg.core.actions import Activate, Attack, EndTurn, GoSolo, Pick, Play, TakeGigDie, Target
from cptcg.core.enums import TARGET_GIG, TARGET_UNIT, Keyword, Zone
from cptcg.core.ops import available, has_keyword, power

E = 9
L3 = ["padre-man-of-the-cross", "wakako-okada-peace-and-harmony", "muamar-reyes-el-capitan"]
NOCALL = ["saburo-arasaka-stubborn-patriarch", "kerry-eurodyne-axe-attitude-audience", "river-ward-detective-on-the-hunt"]


def play(s, cid, host=None):
    from cptcg.core.enums import NO_INST
    do(s, Play(find(s, cid, Zone.HAND), host if host is not None else NO_INST))
    return s


def test_afterparty_adjusts_then_draws_on_different_values(pool):
    s = board(pool, Side(hand=["afterparty-at-lizzies"], eddies=E, gig=[(6, 3), (8, 3)], deck=["floor-it"]), Side())
    play(s, "afterparty-at-lizzies")
    do(s, Pick((1,)))                                       # (d6, +1)
    assert s.gig[0] == [(6, 4), (8, 3)] and len(s.zone(0, Zone.HAND)) == 1


def test_industrial_assembly_caps_at_die_max(pool):
    s = board(pool, Side(hand=["industrial-assembly"], eddies=E, gig=[(10, 6)], deck=["floor-it"]), Side())
    play(s, "industrial-assembly")
    assert [o.picks for o in s.pending.options] == [(0,), (1,), (2,), (3,), ()]   # +1..+4, decline
    do(s, Pick((3,)))
    assert s.gig[0] == [(10, 10)] and len(s.zone(0, Zone.HAND)) == 1


def test_trust_no_one_to_min_draws(pool):
    s = board(pool, Side(hand=["trust-no-one"], eddies=E, gig=[(4, 3)], deck=["floor-it"]), Side())
    play(s, "trust-no-one")
    do(s, Pick((0,)))                                       # (d4, -2); can't go below 1
    assert s.gig[0] == [(4, 1)] and len(s.zone(0, Zone.HAND)) == 1


def test_peace_offering_copies_a_value_and_draws_on_pair(pool):
    s = board(pool, Side(hand=["peace-offering"], eddies=E, gig=[(6, 2), (8, 5)], deck=["floor-it"]), Side(gig=[(4, 4)]))
    play(s, "peace-offering")
    do(s, Pick((0,)))                                       # set the d6
    do(s, Pick((0,)))                                       # to the d8's 5
    assert s.gig[0] == [(6, 5), (8, 5)] and len(s.zone(0, Zone.HAND)) == 1


def test_caliber_play_and_defeated(pool):
    s = board(pool, Side(hand=["caliber-totentanzs-top-dog"], eddies=E, gig=[(4, 1)]),
              Side(field=["corpo-security", "animals-wrecker"], hand=["floor-it", "psycho-squad"]))
    play(s, "caliber-totentanzs-top-dog")
    assert s.i_zone[find(s, "corpo-security")] == Zone.TRASH
    defeat_now(s, find(s, "caliber-totentanzs-top-dog"))
    assert s.pending.player == 1
    do(s, Pick((0,)))                                       # discards Floor It (cost 1 == d4 value) -> 1 more (auto)
    assert len(s.zone(1, Zone.HAND)) == 0


def test_chrome_fang_protects_high_gigs(pool):
    s = board(pool, Side(hand=["chrome-fang"], eddies=E, gig=[(4, 2), (12, 11)], deck=["floor-it"]),
              Side(field=["psycho-squad"], deck=["floor-it"]))
    play(s, "chrome-fang")
    do(s, EndTurn())
    do(s, TakeGigDie(4))
    do(s, Attack(find(s, "psycho-squad")))                  # power 6: can only steal the 2
    assert s.gig[1][-1] == (4, 2) and (12, 11) in s.gig[0]


def test_westbrook_protects_from_legends(pool):
    s = board(pool, Side(hand=["westbrook-netrunner"], eddies=E, gig=[(4, 2), (12, 11)], deck=["floor-it"]),
              Side(field=[("v-streetkid", {"faceup": True})], deck=["floor-it"]))
    play(s, "westbrook-netrunner")
    do(s, EndTurn())
    do(s, TakeGigDie(4))
    do(s, Attack(find(s, "v-streetkid")))                   # Legend power 6: can't steal the 2
    assert s.gig[1][-1] == (12, 11)


def test_delamain_draws_two(pool):
    s = board(pool, Side(hand=["delamain-rideshare-ai"], eddies=E, deck=["floor-it"] * 2), Side())
    play(s, "delamain-rideshare-ai")
    assert len(s.zone(0, Zone.HAND)) == 2


def test_field_operator_even_cred(pool):
    s = board(pool, Side(hand=["field-operator"], eddies=E, gig=[(6, 4)], deck=["floor-it"]), Side())
    play(s, "field-operator")
    assert len(s.zone(0, Zone.HAND)) == 1


def test_gilded_maton(pool):
    s = board(pool, Side(hand=["gilded-maton"], eddies=E, field=[("psycho-squad", {"gear": ["mantis-blades"]})]),
              Side(field=["corpo-security"]))
    play(s, "gilded-maton")
    do(s, Pick((0,)))
    assert s.i_zone[find(s, "mantis-blades")] == Zone.TRASH and s.i_zone[find(s, "corpo-security")] == Zone.TRASH


def test_hacked_corpo(pool):
    s = board(pool, Side(hand=["hacked-corpo"], eddies=E, deck=["psycho-squad", "floor-it", "psycho-squad", "psycho-squad"]), Side())
    play(s, "hacked-corpo")
    assert s.card(s.zone(0, Zone.HAND)[0]).id == "floor-it"


def test_hanako_gilded_cage_takes_cost_matches(pool):
    s = board(pool, Side(hand=["hanako-arasaka-in-a-gilded-cage"], eddies=E, gig=[(4, 1), (6, 4)],
                         deck=["floor-it", "psycho-squad", "corpo-security", "floor-it", "floor-it"]), Side())
    play(s, "hanako-arasaka-in-a-gilded-cage")               # top 4: floor-it(1) floor-it(1) corpo(2) psycho(4)
    do(s, Pick((0, 1, 2)))                                    # all three matches
    assert len(s.zone(0, Zone.HAND)) == 3 and len(s.zone(0, Zone.DECK)) == 2


def test_heywood_ripperdoc(pool):
    s = board(pool, Side(hand=["heywood-ripperdoc"], eddies=E, gig=[(4, 1)], deck=["floor-it"]),
              Side(field=[("psycho-squad", {"gear": ["mantis-blades"]})]))
    play(s, "heywood-ripperdoc")
    do(s, Pick((0,)))
    assert s.i_zone[find(s, "mantis-blades")] == Zone.TRASH and len(s.zone(0, Zone.HAND)) == 1


def test_japantown_jonin(pool):
    s = board(pool, Side(hand=["japantown-jonin"], eddies=E, field=["corpo-security"]), Side())
    play(s, "japantown-jonin")
    do(s, Pick((0,)))
    assert power(s, find(s, "corpo-security")) == 4


def test_lizzy_wizzy_free_program_then_bottom_deck(pool):
    s = board(pool, Side(hand=["lizzy-wizzy-delicate-weapon", "floor-it"], eddies=E, deck=["psycho-squad"] * 2),
              Side(field=["psycho-squad"]))
    play(s, "lizzy-wizzy-delicate-weapon")
    do(s, Pick((0,)))                                       # Floor It free: -1 power (auto), draw 1
    assert s.card(s.zone(0, Zone.DECK)[0]).id == "floor-it" and power(s, find(s, "psycho-squad", player=1)) == 5


def test_maman_brigitte(pool):
    s = board(pool, Side(hand=["maman-brigitte-spirit-of-death", "floor-it", "detonate"], eddies=E),
              Side(field=["psycho-squad"], deck=["floor-it"]))
    play(s, "maman-brigitte-spirit-of-death")
    do(s, Pick((0,)))                                       # yes: both Programs, only rival Unit -> automatic
    assert s.i_zone[find(s, "psycho-squad", player=1)] == Zone.DECK


def test_maxtac_av_swaps(pool):
    s = board(pool, Side(hand=["maxtac-av"], eddies=E, gig=[(4, 1)]), Side(gig=[(20, 19)]))
    play(s, "maxtac-av")
    do(s, Pick((0,)))
    assert s.gig[0] == [(20, 19)] and s.gig[1] == [(4, 1)]


def test_minotaur_needs_more_cred(pool):
    s = board(pool, Side(hand=["minotaur"], eddies=E, gig=[(6, 5)]), Side(field=["corpo-security", "psycho-squad"], gig=[(4, 1)]))
    play(s, "minotaur")                                     # only Corpo Security (2) is power <= 5
    assert s.i_zone[find(s, "corpo-security")] == Zone.TRASH and s.i_zone[find(s, "psycho-squad")] == Zone.FIELD


def test_mox_inciters_forces_attack(pool):
    s = board(pool, Side(hand=["mox-inciters"], eddies=E), Side(field=["psycho-squad"]))
    play(s, "mox-inciters")
    assert s.has_mod("must_attack", find(s, "psycho-squad"))


def test_offduty_malfini(pool):
    s = board(pool, Side(hand=["offduty-malfini"], eddies=E), Side(field=["psycho-squad"]))
    play(s, "offduty-malfini")
    assert s.i_spent[find(s, "offduty-malfini")] and s.i_spent[find(s, "psycho-squad")]


def test_pacifica_netrunner_locks_on_even_cred(pool):
    s = board(pool, Side(hand=["pacifica-netrunner"], eddies=E, gig=[(6, 2)]), Side(field=[("psycho-squad", {"spent": True})]))
    play(s, "pacifica-netrunner")
    from cptcg.core.enums import F_NO_READY_NEXT
    assert s.i_flags[find(s, "psycho-squad")] & F_NO_READY_NEXT


def test_royce_simon_scales_with_cred(pool):
    s = board(pool, Side(hand=["royce-dont-call-me-simon"], eddies=E, gig=[(6, 5)]),
              Side(field=["la-llorona-ghost-of-the-past"], gig=[(4, 1)]))
    play(s, "royce-dont-call-me-simon")                      # power 3 target allowed with more cred
    assert s.i_zone[find(s, "la-llorona-ghost-of-the-past")] == Zone.TRASH


def test_tygers_whisper_free_call(pool):
    s = board(pool, Side(hand=["tygers-whisper"], eddies=E, legends=L3), Side())
    play(s, "tygers-whisper")
    do(s, Pick((0,)))
    assert sum(s.i_faceup[l] for l in s.legends(0)) == 1 and available(s, 0) == E - 2 + 3


def test_valentino_street_racer_grants_adrenaline(pool):
    s = board(pool, Side(hand=["valentino-street-racer", "corpo-security"], eddies=E), Side(gig=[(6, 3)]))
    play(s, "corpo-security")
    play(s, "valentino-street-racer")
    u = find(s, "corpo-security")
    assert has_keyword(s, u, Keyword.ADRENALINE)


def test_viktor_pinch_equips_only_other_units(pool):
    s = board(pool, Side(hand=["viktor-vektor-you-might-feel-a-little-pinch"], eddies=E, field=["psycho-squad"],
                         trash=["mantis-blades"]), Side())
    play(s, "viktor-vektor-you-might-feel-a-little-pinch")
    assert s.i_host[find(s, "mantis-blades")] == find(s, "psycho-squad")


def test_yorinobu_steel_dragon_free_unit_can_attack_units(pool):
    s = board(pool, Side(hand=["yorinobu-arasaka-steel-dragon"], eddies=E, trash=["corpo-security", "psycho-squad"]),
              Side(field=[("corpo-security", {"spent": True})]))
    play(s, "yorinobu-arasaka-steel-dragon")
    do(s, Pick((1,)))                                       # psycho-squad from trash
    u = find(s, "psycho-squad", player=0)
    assert Attack(u) in s.pending.options


def test_adam_smasher_metal_over_meat_defeats_every_other_unit(pool):
    s = board(pool, Side(hand=["adam-smasher-metal-over-meat"], eddies=E, field=["psycho-squad"],
                         legends=[("v-streetkid", {"faceup": True})]),
              Side(field=["corpo-security", ("animals-wrecker", {"gear": ["gorilla-arms"]})]))
    play(s, "adam-smasher-metal-over-meat")
    smasher = find(s, "adam-smasher-metal-over-meat")
    assert s.i_zone[smasher] == Zone.FIELD
    for cid in ("psycho-squad", "corpo-security", "animals-wrecker", "gorilla-arms"):
        assert s.i_zone[find(s, cid)] == Zone.TRASH, cid    # both sides, and Gear with its host
    assert s.i_zone[find(s, "v-streetkid")] == Zone.LEGENDS  # a Legend is not a Unit


def test_sandayu_oda(pool):
    s = board(pool, Side(hand=["sandayu-oda-hanakos-guardian"], eddies=E, gig=[(4, 2), (6, 2)]),
              Side(field=["psycho-squad", ("corpo-security", {"spent": True})]))
    play(s, "sandayu-oda-hanakos-guardian")
    do(s, Pick((0,)))
    assert s.i_spent[find(s, "psycho-squad")]
    assert Attack(find(s, "sandayu-oda-hanakos-guardian")) in s.pending.options


def test_placide_on_play(pool):
    s = board(pool, Side(hand=["placide-voodoo-sentinel", "floor-it"], eddies=E), Side(field=["psycho-squad"], deck=["floor-it"]))
    play(s, "placide-voodoo-sentinel")
    do(s, Pick((0,)))
    assert s.i_zone[find(s, "psycho-squad")] == Zone.DECK


def test_dexter_one_last_chance(pool):
    s = board(pool, Side(hand=["dexter-deshawn-one-last-chance"], eddies=E, gig=[(6, 3)], deck=["floor-it"] * 2),
              Side(gig=[(20, 20)]))
    play(s, "dexter-deshawn-one-last-chance")
    do(s, Pick((1,)))                                       # (d6, +1)
    assert s.gig[0] == [(6, 4)]
    defeat_now(s, find(s, "dexter-deshawn-one-last-chance"))
    assert len(s.zone(0, Zone.HAND)) == 2                   # cred differs by 16


def test_evelyn_siren_attack(pool):
    s = board(pool, Side(field=["evelyn-parker-scheming-siren"], gig=[(6, 5)], deck=["floor-it"]), Side(gig=[(4, 1)]))
    do(s, Attack(find(s, "evelyn-parker-scheming-siren")))
    assert len(s.zone(0, Zone.HAND)) == 0                   # drew 1 then discarded 1 (single option)


def test_sketchy_ripper_finds_gear(pool):
    s = board(pool, Side(field=["sketchy-ripper"], deck=["floor-it", "mantis-blades", "floor-it"]), Side(gig=[(4, 1)]))
    do(s, Attack(find(s, "sketchy-ripper")))
    do(s, Pick((0,)))
    assert s.card(s.zone(0, Zone.HAND)[0]).id == "mantis-blades"


def test_swordwise_huscle_draws_at_5_power(pool):
    s = board(pool, Side(field=[("swordwise-huscle", {"gear": ["mantis-blades"]})], deck=["floor-it"]), Side(gig=[(4, 1)]))
    do(s, Attack(find(s, "swordwise-huscle")))
    assert len(s.zone(0, Zone.HAND)) == 1


def test_panam_strength_call_ability_and_attack(pool):
    s = board(pool, Side(field=["panam-palmer-strength-through-family"], hand=["floor-it"], eddies=E, legends=NOCALL,
                         deck=["floor-it"] * 3), Side(gig=[(4, 1)]))
    u = find(s, "panam-palmer-strength-through-family")
    assert Activate(u, 0) in s.pending.options
    do(s, Activate(u, 0))
    do(s, Pick((0,)))
    assert sum(s.i_faceup[l] for l in s.legends(0)) == 1
    do(s, Attack(u))
    assert len(s.zone(0, Zone.HAND)) == 1                   # discarded 1, drew 1


def test_pepe_readies_merc_legends(pool):
    s = board(pool, Side(field=["pepe-najarro-working-doubles"], gig=[(4, 2), (6, 2)],
                         legends=[("v-streetkid", {"spent": True}), ("rogue-amendiares-preem-solo", {"spent": True}), "padre-man-of-the-cross"]),
              Side(gig=[(4, 1)]))
    do(s, Attack(find(s, "pepe-najarro-working-doubles")))
    do(s, Pick((0, 1)))
    assert not s.i_spent[find(s, "v-streetkid")] and not s.i_spent[find(s, "rogue-amendiares-preem-solo")]


def test_jackie_ride_or_die(pool):
    s = board(pool, Side(field=["jackie-welles-ride-or-die-choom"], gig=[(4, 2), (6, 4), (8, 3)], deck=["floor-it"] * 3),
              Side(gig=[(4, 1)]))
    u = find(s, "jackie-welles-ride-or-die-choom")
    do(s, Attack(u))
    assert power(s, u) == 8 + 4
    defeat_now(s, u)
    assert len(s.zone(0, Zone.HAND)) == 2                   # odd values: the 3 and the stolen 1


def test_el_sombreron_pays_for_power(pool):
    s = board(pool, Side(field=["el-sombreron-la-venganza-lenta"], eddies=2, gig=[(12, 9)]), Side(gig=[(4, 1)]))
    u = find(s, "el-sombreron-la-venganza-lenta")
    do(s, Attack(u))
    do(s, Pick((0,)))
    assert power(s, u) == 13 and available(s, 0) == 0 and len(s.gig[0]) == 2   # 13 power steals 2 (only 1 there)


def test_goro_losing_his_way(pool):
    s = board(pool, Side(field=["goro-takemura-losing-his-way"], legends=[(l, {"faceup": True}) for l in L3]), Side(gig=[(4, 1)]))
    u = find(s, "goro-takemura-losing-his-way")
    do(s, Attack(u))
    assert power(s, u) == 9


def test_screw_returns_unit(pool):
    s = board(pool, Side(field=["screw-lovelorn-fool"], trash=["psycho-squad"]), Side())
    defeat_now(s, find(s, "screw-lovelorn-fool"))
    assert s.card(s.zone(0, Zone.HAND)[0]).id == "psycho-squad"


def test_t_bug_looks_and_calls(pool):
    s = board(pool, Side(field=["t-bug-amateur-philosopher"], legends=L3), Side())
    defeat_now(s, find(s, "t-bug-amateur-philosopher"))
    assert all(s.i_known[l] & 1 for l in s.legends(0))
    do(s, Pick((2,)))
    assert s.i_faceup[s.legends(0)[2]]


def test_6th_street_recruits_only_fires_on_a_d6_steal(pool):
    s = board(pool, Side(field=["6th-street-recruits", "psycho-squad"]), Side(gig=[(6, 3)]))
    do(s, Attack(find(s, "psycho-squad")))                  # a friendly Unit steals the d6
    assert [o.picks for o in s.pending.options] == [(0,), (1,), (2,), ()]   # +1..+3 (caps at 6)
    do(s, Pick((2,)))
    assert s.gig[0] == [(6, 6)]
    s = board(pool, Side(field=["6th-street-recruits", "psycho-squad"]), Side(gig=[(8, 3)]))
    do(s, Attack(find(s, "psycho-squad")))                  # a d8: nothing to increase
    assert s.gig[0] == [(8, 3)] and isinstance(s.pending.options[0], EndTurn)


def test_dying_night_gear_attack_trigger_and_v_ready(pool):
    s = board(pool, Side(field=[("v-roamer-of-the-badlands", {"gear": ["dying-night-vs-pistol"]})], eddies=2, spent_eddies=2, deck=["floor-it"]),
              Side(gig=[(6, 3)], deck=["floor-it"]))
    do(s, Attack(find(s, "v-roamer-of-the-badlands")))      # Gear ATTACK trigger: decrease a Gig
    do(s, Pick((0,)))                                       # (rival d6, -2) -> 1
    do(s, Pick((4,)))                                       # V steals it: increase by +5 -> 6
    assert s.gig[0] == [(6, 6)]
    do(s, EndTurn())                                        # host is named "V": ready 2 Eddies
    assert available(s, 0) == 2

def test_kiroshi_optics_look(pool):
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["kiroshi-optics"]})], legends=L3), Side(gig=[(4, 1)]))
    do(s, Attack(find(s, "psycho-squad")))
    do(s, Pick((1,)))
    assert s.i_known[s.legends(0)[1]] & 1


def test_the_relic_recurs_a_unit_and_bottom_decks_host(pool):
    s = board(pool, Side(field=["animals-wrecker"]), Side(field=[("corpo-security", {"spent": True, "gear": ["the-relic-experimental-biochip"]})], trash=["psycho-squad"], deck=["floor-it"]))
    do(s, Attack(find(s, "animals-wrecker")))
    do(s, Target(TARGET_UNIT, find(s, "corpo-security")))
    assert s.i_zone[find(s, "psycho-squad")] == Zone.FIELD and s.i_zone[find(s, "corpo-security")] == Zone.DECK


def test_adam_smasher_ender_of_legends_defeats_a_unit_on_go_solo(pool):
    s = board(pool, Side(eddies=E, legends=[("adam-smasher-ender-of-legends", {"faceup": True}),
                                            "padre-man-of-the-cross", "wakako-okada-peace-and-harmony"]),
              Side(field=["la-llorona-ghost-of-the-past", "corpo-security"]))
    l = find(s, "adam-smasher-ender-of-legends")
    do(s, GoSolo(l))
    do(s, Pick((1,)))                                       # candidates in field order: La Llorona, Corpo Security
    assert s.i_zone[l] == Zone.FIELD and power(s, l) == 9
    assert s.i_zone[find(s, "corpo-security")] == Zone.TRASH
    assert s.i_zone[find(s, "la-llorona-ghost-of-the-past")] == Zone.FIELD


def test_null_street_cred_is_neither_even_nor_odd(pool):
    """CR 11.2.3: Field Operator draws on even Street Cred; with no Gigs there is no number."""
    s = board(pool, Side(hand=["field-operator"], eddies=E, deck=["corpo-security"] * 3), Side())
    play(s, "field-operator")
    assert len(s.z[Zone.HAND]) == 0
    s = board(pool, Side(hand=["field-operator"], eddies=E, deck=["corpo-security"] * 3, gig=[(4, 2)]), Side())
    play(s, "field-operator")
    assert len(s.z[Zone.HAND]) == 1
