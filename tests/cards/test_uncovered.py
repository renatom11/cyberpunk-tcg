"""One scenario per scripted card that no test had ever named.

Eight cards reached this file — six of them Legends. That skew is not chance: a Legend is never
drawn and never sits in ``deck.main``, so it falls out of the draw-conditioned measurements too, and
nothing in the project was looking at it from any direction. ``tests/cards/test_coverage.py`` keeps
the floor from dropping back once these land.

Each test asserts a printed-text outcome — zones, hand size, Gig faces, ``power()``, ``has_keyword``
— and never a script internal, so a reader can check it against the card without reading the engine.
"""
from conftest import Side, board, defeat_now, do, find

from cptcg.core.actions import (Activate, Attack, Block, CallLegend, EndTurn, GoSolo, Pick,
                                Play)
from cptcg.core.enums import Keyword, Zone
from cptcg.core.ops import has_keyword, power

E = 9
#: Three Legends with no CALL trigger, so a board that needs Legends in reserve does not fire one.
NOCALL = ["saburo-arasaka-stubborn-patriarch", "kerry-eurodyne-axe-attitude-audience",
          "river-ward-detective-on-the-hunt"]


# ------------------------------------------------------------------------------- Units
def test_kerry_the_last_rockerboy_draws_two_only_with_an_eight_plus_gig(pool):
    """'⊡: If you control a Gig with 8+ value, draw 2.'"""
    s = board(pool, Side(field=["kerry-eurodyne-the-last-rockerboy"], gig=[(10, 8)],
                         deck=["floor-it"] * 3), Side())
    u = find(s, "kerry-eurodyne-the-last-rockerboy")
    do(s, Activate(u, 0))
    assert len(s.zone(0, Zone.HAND)) == 2 and s.i_spent[u]

    s = board(pool, Side(field=["kerry-eurodyne-the-last-rockerboy"], gig=[(10, 7)],
                         deck=["floor-it"] * 3), Side())
    u = find(s, "kerry-eurodyne-the-last-rockerboy")
    assert Activate(u, 0) not in s.pending.options          # 7 is not 8+, so the ability is not offered


def test_judy_alvarez_reveals_the_top_card_and_may_play_it_free(pool):
    """'1 €$, ⊡: Reveal the top card of your deck. You may play it for free. Otherwise, add it to
    your hand.' Either way the card leaves the deck, so the choice is only where it ends up."""
    s = board(pool, Side(field=["judy-alvarez-nothing-to-doubt"], eddies=E, deck=["psycho-squad"]),
              Side())
    u = find(s, "judy-alvarez-nothing-to-doubt")
    do(s, Activate(u, 0))
    do(s, Pick((0,)))                                       # take the free play
    assert s.i_zone[find(s, "psycho-squad")] == Zone.FIELD

    s = board(pool, Side(field=["judy-alvarez-nothing-to-doubt"], eddies=E, deck=["psycho-squad"]),
              Side())
    u = find(s, "judy-alvarez-nothing-to-doubt")
    do(s, Activate(u, 0))
    do(s, Pick(()))                                         # decline: it stays in hand
    assert s.i_zone[find(s, "psycho-squad")] == Zone.HAND


def test_rogue_queen_of_the_afterlife_readies_eddies_once_per_turn(pool):
    """'The first time another friendly Unit steals a Gig with value less than its power each turn,
    ready 2 Eddies.' Rogue's own steal does not count — the text says *another* friendly Unit."""
    s = board(pool, Side(field=["rogue-amendiares-queen-of-the-afterlife", "psycho-squad"],
                         eddies=4, spent_eddies=4),
              Side(gig=[(4, 1), (6, 2)]))
    assert sum(1 for i in s.zone(0, Zone.EDDIES) if not s.i_spent[i]) == 0
    do(s, Attack(find(s, "psycho-squad")))                  # power 6, so one steal
    do(s, Pick((0,)))                                       # take the d4 showing 1
    assert s.gig[0] == [(4, 1)]
    assert sum(1 for i in s.zone(0, Zone.EDDIES) if not s.i_spent[i]) == 2


def test_rogue_queen_drains_a_rival_unit_by_her_own_power(pool):
    """'QUICK 2 €$, ⊡: A rival Unit loses power equal to this Unit's power this turn.'"""
    s = board(pool, Side(field=["rogue-amendiares-queen-of-the-afterlife"], eddies=E),
              Side(field=["psycho-squad"]))
    u = find(s, "rogue-amendiares-queen-of-the-afterlife")
    rival = find(s, "psycho-squad")
    assert power(s, u) == 4 and power(s, rival) == 6
    do(s, Activate(u, 0))                                   # one rival Unit, so no question to ask
    assert power(s, rival) == 2                             # 6 - 4


# ----------------------------------------------------------------------------- Legends
def test_viktor_vektor_calls_up_two_cheap_gears_out_of_the_top_five(pool):
    """'CALL: Search the top 5 cards of your deck. Reveal up to 2 Gears with cost 2 or less and add
    them to your hand. Bottom-deck the rest in a random order.'"""
    deck = ["psycho-squad", "floor-it", "delamain-cab", "mantis-blades", "kiroshi-optics", "minotaur"]
    s = board(pool, Side(legends=["viktor-vektor-sit-down-and-relax"] + NOCALL[:2], eddies=E,
                         deck=deck), Side())
    v = find(s, "viktor-vektor-sit-down-and-relax")
    do(s, CallLegend(v))
    do(s, Pick((0, 1)))                                     # both Gears
    hand = {s.card(i).id for i in s.zone(0, Zone.HAND)}
    assert hand == {"mantis-blades", "kiroshi-optics"}
    assert len(s.zone(0, Zone.DECK)) == len(deck) - 2       # the rest went back, none were lost


def test_sasha_yakovleva_reveals_on_attack_and_makes_a_rival_discard_when_defeated(pool):
    """'GO SOLO / ATTACK: Reveal the top card of your deck and add it to your hand. This Unit gains
    power equal to that card's cost this turn. / DEFEATED: A Rival discards 1.'"""
    s = board(pool, Side(legends=[("sasha-yakovleva-wont-let-you-down", {"faceup": True})] + NOCALL[:2],
                         eddies=E, deck=["psycho-squad"]), Side(gig=[(4, 1)], hand=["floor-it"]))
    sasha = find(s, "sasha-yakovleva-wont-let-you-down")
    do(s, GoSolo(sasha))
    do(s, Attack(sasha))
    assert {s.card(i).id for i in s.zone(0, Zone.HAND)} == {"psycho-squad"}
    assert power(s, sasha) == 4                             # 0 base + psycho-squad's cost of 4
    defeat_now(s, sasha)
    assert len(s.zone(1, Zone.HAND)) == 0                   # DEFEATED: a Rival discards 1


def test_hanako_swaps_a_gig_with_a_rival(pool):
    """'⊡: Swap a friendly Gig with a rival Gig.'"""
    s = board(pool, Side(legends=[("hanako-arasaka-daughter-of-the-emperor", {"faceup": True})] + NOCALL[:2],
                         gig=[(6, 3)]), Side(gig=[(8, 5)]))
    h = find(s, "hanako-arasaka-daughter-of-the-emperor")
    do(s, Activate(h, 0))                                   # one Gig each side: nothing to ask
    assert s.gig[0] == [(8, 5)] and s.gig[1] == [(6, 3)]


def test_goro_vengeful_bodyguard_grants_blocker_and_adds_power_on_a_value_pair(pool):
    """'QUICK 1 €$, ⊡: Give a friendly Unit with cost 4 or less BLOCKER this turn. If you control a
    value-pair of Gigs, also give it +1 power this turn.'"""
    s = board(pool, Side(legends=[("goro-takemura-vengeful-bodyguard", {"faceup": True})] + NOCALL[:2],
                         field=["psycho-squad"], eddies=E, gig=[(6, 3), (8, 3)]), Side())
    g = find(s, "goro-takemura-vengeful-bodyguard")
    u = find(s, "psycho-squad")
    assert not has_keyword(s, u, Keyword.BLOCKER)
    do(s, Activate(g, 0))                                   # one Unit with cost 4 or less
    assert has_keyword(s, u, Keyword.BLOCKER) and power(s, u) == 7      # 6 + 1 for the pair


def test_panam_nomad_cavalry_moves_her_gear_and_readies_the_new_host(pool):
    """'2 €$, ⊡: Move a Gear from this Legend to an unequipped friendly Unit. If you do, ready that
    Unit.'"""
    s = board(pool, Side(legends=[("panam-palmer-nomad-cavalry", {"faceup": True, "gear": ["mantis-blades"]})] + NOCALL[:2],
                         field=[("psycho-squad", {"spent": True})], eddies=E), Side())
    p = find(s, "panam-palmer-nomad-cavalry")
    u = find(s, "psycho-squad")
    gear = find(s, "mantis-blades")
    assert s.i_host[gear] == p and s.i_spent[u]
    do(s, Activate(p, 0))                                   # one Gear, one unequipped Unit
    assert s.i_host[gear] == u and not s.i_spent[u]


def test_hanako_draws_at_the_start_of_your_turn_for_each_value_pair(pool):
    """'At the start of your turn, draw 1 for each friendly value-pair of Gigs.'

    Two pairs on the board — a 3/3 and a 5/5 — so two extra cards. Measured against a control board
    that is identical but for Hanako, because the turn also begins with the ordinary draw and an
    absolute count would be reading that as if it were her.
    """
    def hand_after_a_full_turn(legends):
        s = board(pool, Side(legends=legends, gig=[(6, 3), (8, 3), (10, 5), (12, 5)],
                             deck=["floor-it"] * 6),
                  Side(gig=[(4, 1)], deck=["floor-it"] * 6))
        do(s, EndTurn())
        while s.pending is not None and s.pending.player == 1:   # their turn, however it is spent
            do(s, s.pending.options[-1])
        return len(s.zone(0, Zone.HAND))

    her = [("hanako-arasaka-daughter-of-the-emperor", {"faceup": True})] + NOCALL[:2]
    assert hand_after_a_full_turn(her) - hand_after_a_full_turn(NOCALL) == 2


def test_goro_offers_a_discard_for_a_draw_when_a_friendly_unit_blocks(pool):
    """'When a friendly Unit uses BLOCKER, you may discard 1. If you do, draw 1.'

    Unlike the ability above, this half is a reaction to the rival's attack, so it has to be
    provoked from the other seat.
    """
    s = board(pool, Side(legends=[("goro-takemura-vengeful-bodyguard", {"faceup": True})] + NOCALL[:2],
                         field=["secondhand-bombus"], hand=["floor-it"], deck=["psycho-squad"],
                         gig=[(6, 2)]),
              Side(field=["psycho-squad"], gig=[(4, 1)]), active=1)
    do(s, Attack(find(s, "psycho-squad", player=1)))
    do(s, Block(find(s, "secondhand-bombus")))
    do(s, Pick((0,)))                                       # yes, discard 1 ...
    assert {s.card(i).id for i in s.zone(0, Zone.HAND)} == {"psycho-squad"}   # ... and draw 1
    assert s.card(s.zone(0, Zone.TRASH)[0]).id == "floor-it"


def test_panam_readies_a_fully_equipped_crew_at_the_end_of_your_turn(pool):
    """'At the end of your turn, if 5 or more friendly Units and/or Legends are equipped, ready
    them.' Panam herself is equipped and counts, so four equipped Units make five."""
    crew = [("psycho-squad", {"gear": ["mantis-blades"], "spent": True}) for _ in range(4)]
    s = board(pool, Side(legends=[("panam-palmer-nomad-cavalry", {"faceup": True, "gear": ["mantis-blades"], "spent": True})] + NOCALL[:2],
                         field=crew), Side(gig=[(4, 1)], deck=["floor-it"] * 4))
    spent = [i for i in s.zone(0, Zone.FIELD) if s.card(i).id == "psycho-squad"]
    assert len(spent) == 4 and all(s.i_spent[i] for i in spent)
    do(s, EndTurn())
    assert not any(s.i_spent[i] for i in spent)
    assert not s.i_spent[find(s, "panam-palmer-nomad-cavalry")]
