"""Stage 0, step 1a: the engine-versus-FAQ items from the unified design, reproduced before any fix.

Every test here asserts what the **FAQ** (``data/faq.json``) or the Comprehensive Rules say happens.
The ones the engine gets wrong today are marked ``xfail(strict=True)`` with the item's code, so the
suite stays green while the finding is open and the marker's removal is the record of red -> green.
A test without a marker documents an item that was classified as a deliberate approximation or a
confirmation: it passes today and is kept so the reading it records cannot drift silently.

Item codes (S0-*) follow the Stage 0 plan; the FAQ answers are quoted in each docstring.
"""
import pytest
from conftest import Side, board, defeat_now, do, during_main, find

from cptcg.core.actions import (Activate, Attack, Block, CallLegend, ChoiceKind, EndTurn, Pass,
                                Pick, Play, Target)
from cptcg.core.engine import apply, legal_actions, play_cost
from cptcg.core.enums import NO_INST, TARGET_GIG, TARGET_UNIT, Zone
from cptcg.core.ops import FIGHTING, VS_UNIT, power
from cptcg.core.view import knows_identity

E = 9
FILLER = ["floor-it", "mantis-blades", "psycho-squad", "corpo-security", "riot-shield"]


def play(s, cid, host=None):
    do(s, Play(find(s, cid, Zone.HAND), host if host is not None else NO_INST))
    return s


def drive(s, stop, limit=40):
    """Apply default answers (attack target: the Gig area; reactions: Pass; picks: the first
    option) until ``stop(s)`` holds or the menu is a main phase again. Returns stop(s)."""
    for _ in range(limit):
        legal_actions(s)
        if stop(s):
            return True
        ch = s.pending
        if ch is None or ch.kind is ChoiceKind.MAIN:
            return stop(s)
        pick = 0
        for i, o in enumerate(ch.options):
            if isinstance(o, Target) and o.kind == TARGET_GIG:
                pick = i
                break
            if isinstance(o, Pass):
                pick = i
        apply(s, pick)
    return stop(s)


def order_prompt(s):
    ch = s.pending
    return ch is not None and ch.kind is ChoiceKind.PICK and (ch.tag or "").endswith("@order")


def attack(s, unit):
    do(s, Attack(unit))
    return s


# ======================================================================= trigger ordering (E8)
@pytest.mark.xfail(strict=True, reason="S0-E8: FAQ grants the order of a Gear's spend trigger against the host's ATTACK; the engine fixes it")
def test_gear_spend_trigger_and_host_attack_trigger_are_ordered(pool):
    """Netwatch Netdriver: *"...and the Unit or Legend has an ATTACK effect, do I get Netwatch
    Netdriver's effect before or after the ATTACK effect? You can choose the order you resolve
    these effects."* Sketchy Ripper prints ATTACK; the Gear triggers when the host is spent."""
    s = board(pool, Side(field=[("sketchy-ripper", {"gear": ["netwatch-netdriver"]})],
                         deck=FILLER), Side(gig=[(6, 3)]))
    u = find(s, "sketchy-ripper", Zone.FIELD, 0)
    attack(s, u)
    assert drive(s, order_prompt), "no ordering prompt for a printed ATTACK meeting a spend trigger"
    assert s.pending.player == 0 and len(s.pending.options) == 2


@pytest.mark.xfail(strict=True, reason="S0-E8: host and Gear DEFEATED triggers land together; the engine runs the host's first without asking")
def test_host_and_gear_defeated_triggers_are_ordered(pool):
    """General FAQ: *"When I have multiple ATTACK effects that activate and go into pending at the
    same time. Can I choose any order to resolve them? Yes"* — and DEFEATED is the same kind of
    printed trigger. Screw and The Relic both print DEFEATED; the host's death fires both."""
    s = board(pool, Side(field=[("screw-lovelorn-fool", {"gear": ["the-relic-experimental-biochip"]})],
                         trash=["corpo-security"], deck=FILLER), Side())
    u = find(s, "screw-lovelorn-fool", Zone.FIELD, 0)
    defeat_now(s, u)
    assert drive(s, order_prompt), "two DEFEATED triggers on one death asked nobody which came first"
    assert s.pending.player == 0 and len(s.pending.options) == 2


@pytest.mark.xfail(strict=True, reason="S0-E8/E9: a PLAY trigger and the spend trigger of the Legend that paid for it land together; the engine resolves the spend trigger first, silently")
def test_play_trigger_and_payment_spend_trigger_are_ordered(pool):
    """General FAQ: *"I have a Unit with PLAY and a Unit with 'When a friendly Legend is spent.
    Draw 1'. Will I be able to choose the order to resolve them? Yes"*. Paying Chrome Fang's cost
    with a face-up Legend hosting Netwatch Netdriver is exactly that pair."""
    s = board(pool, Side(hand=["chrome-fang"], eddies=4,
                         legends=[("v-streetkid", {"faceup": True, "gear": ["netwatch-netdriver"]})],
                         deck=FILLER), Side())
    play(s, "chrome-fang")
    assert drive(s, order_prompt), "PLAY and a payment spend trigger were not offered for ordering"
    assert s.pending.player == 0 and len(s.pending.options) == 2


@pytest.mark.xfail(strict=True, reason="S0-E8: a temporary listener (Appetite for Destruction) never joins the ordering group")
def test_a_listener_and_a_hook_on_the_same_event_are_ordered(pool):
    """Johnny Silverhand *Never Stop Fighting* ("The first time this Unit wins a fight each turn,
    ready it") and Appetite for Destruction ("the next time a friendly Unit wins a fight by 3 or
    more...") both trigger on the same fight; the controller orders them (general FAQ, above)."""
    s = board(pool, Side(field=["johnny-silverhand-never-stop-fighting"], hand=["appetite-for-destruction"],
                         eddies=E, deck=FILLER),
              Side(field=[("ruthless-lowlife", {"spent": True})], gig=[(6, 3)]))
    play(s, "appetite-for-destruction")
    u = find(s, "johnny-silverhand-never-stop-fighting", Zone.FIELD, 0)
    do(s, Attack(u))
    do(s, Target(TARGET_UNIT, find(s, "ruthless-lowlife", Zone.FIELD, 1)))
    assert drive(s, order_prompt), "a listener and a hook on one event asked nobody which came first"
    assert s.pending.player == 0 and len(s.pending.options) == 2


# ================================================================ activation and payment (E9)
def _draws(s):
    return [e for e in s.log if e[0] == "draw"]


@pytest.mark.xfail(strict=True, reason="S0-E9: FAQ resolves an activated effect before the spend trigger of the card that was spent for it; the engine does the reverse")
def test_an_activated_effect_resolves_before_the_spend_trigger_it_caused(pool):
    """Netwatch Netdriver: *"If I spend a Unit or Legend equipped with Netwatch Netdriver to
    activate the Unit/Legend's ⊡: effect, do I resolve Netwatch Netdriver's effect before or after
    the activated effect? After. Resolve the activated ⊡: effect first."* Kerry Eurodyne *The Last
    Rockerboy* prints "⊡: draw 2 if you control an 8+ Gig"; the Gear draws 1 on the spend."""
    s = board(pool, Side(field=[("kerry-eurodyne-the-last-rockerboy", {"gear": ["netwatch-netdriver"]})],
                         gig=[(8, 8)], deck=FILLER), Side())
    s.log = []
    u = find(s, "kerry-eurodyne-the-last-rockerboy", Zone.FIELD, 0)
    do(s, Activate(u, 0))
    drive(s, lambda st: False)
    draws = _draws(s)
    assert [e[2] for e in draws] == [2, 1], f"the ⊡ effect's draw 2 must come before the Gear's draw 1: {draws}"


@pytest.mark.xfail(strict=True, reason="S0-E9: FAQ plays the card first, then the spend trigger of the Legend that paid; the engine pays (and triggers) before the play")
def test_paying_with_a_legend_resolves_its_spend_trigger_after_the_play(pool):
    """Netwatch Netdriver: *"If I spend a Legend equipped with Netwatch Netdriver to pay a card's
    cost, do I resolve Netwatch Netdriver's effect before or after I play the card? After."*"""
    s = board(pool, Side(hand=["psycho-squad"], eddies=3,
                         legends=[("v-streetkid", {"faceup": True, "gear": ["netwatch-netdriver"]})],
                         deck=FILLER), Side())
    s.log = []
    play(s, "psycho-squad")
    drive(s, lambda st: False)
    kinds = [e[0] for e in s.log if e[0] in ("play", "draw")]
    assert kinds == ["play", "draw"], f"the card must be played before the Gear draws: {kinds}"


# ============================================================ "the first time ... each turn" (E6)
@pytest.mark.xfail(strict=True, reason="S0-E6: 'first time each turn' is keyed per instance; a card entering mid-turn gets a fresh counter")
def test_yorinobu_steel_dragon_does_not_draw_for_the_second_arasaka_death_of_the_turn(pool):
    """Yorinobu Arasaka *Steel Dragon*: *"If a friendly Arasaka Unit was defeated previously
    during my turn and then play Yorinobu Arasaka. If another friendly Arasaka Unit is then
    defeated this turn. Will I draw 1 off Yorinobu's effect? No."*"""
    s = board(pool, Side(field=["field-operator", "augmented-negotiators"],
                         hand=["yorinobu-arasaka-steel-dragon"], eddies=E, deck=FILLER), Side())
    defeat_now(s, find(s, "field-operator", Zone.FIELD, 0))
    play(s, "yorinobu-arasaka-steel-dragon")
    if s.pending is not None and s.pending.kind is ChoiceKind.PICK:
        do(s, Pick(()))                                    # decline the free Unit
    deck_before = len(s.zone(0, Zone.DECK))
    defeat_now(s, find(s, "augmented-negotiators", Zone.FIELD, 0))
    assert len(s.zone(0, Zone.DECK)) == deck_before, "drew for a second ARASAKA death in the same turn"


@pytest.mark.xfail(strict=True, reason="S0-E6: 'first time each turn' is keyed per instance; a Legend Called mid-turn gets a fresh counter")
def test_yorinobu_embracing_destruction_does_not_draw_for_the_second_arasaka_attack(pool):
    """Yorinobu Arasaka *Embracing Destruction*: *"If I've already attacked with an ARASAKA Unit
    this turn before Yorinobu Arasaka is face-up, then flip Yorinobu, can I trigger Yorinobu's
    effect that turn by attacking with another ARASAKA Unit? No."*"""
    s = board(pool, Side(field=["field-operator", "augmented-negotiators"], eddies=2,
                         legends=["yorinobu-arasaka-embracing-destruction"], deck=FILLER),
              Side(gig=[(6, 3), (8, 5), (4, 2)]))
    attack(s, find(s, "field-operator", Zone.FIELD, 0))
    drive(s, lambda st: False)
    do(s, CallLegend(find(s, "yorinobu-arasaka-embracing-destruction", Zone.LEGENDS, 0)))
    deck_before = len(s.zone(0, Zone.DECK))
    attack(s, find(s, "augmented-negotiators", Zone.FIELD, 0))
    drive(s, lambda st: False)
    assert len(s.zone(0, Zone.DECK)) == deck_before, "drew for a second ARASAKA attack in the same turn"


@pytest.mark.xfail(strict=True, reason="S0-E6: 'first time each turn' is keyed per instance; Jackie flipped mid-turn triggers on the second Blue card")
def test_jackie_pour_one_out_does_not_trigger_on_the_second_blue_card_of_the_turn(pool):
    """Jackie Welles *Pour One Out For Me*: *"If I've already played a Blue Unit or Gear this turn
    before Jackie Welles is face-up, then flip Jackie, can I trigger Jackie's effect that turn by
    playing another Blue Gear or Unit? No."*"""
    s = board(pool, Side(hand=["jacked-in-voodoo-boy", "jacked-in-voodoo-boy"], eddies=E,
                         legends=["jackie-welles-pour-one-out-for-me"], gig=[(6, 3)], deck=FILLER),
              Side())
    play(s, "jacked-in-voodoo-boy")
    do(s, CallLegend(find(s, "jackie-welles-pour-one-out-for-me", Zone.LEGENDS, 0)))
    play(s, "jacked-in-voodoo-boy")
    assert s.pending.kind is ChoiceKind.MAIN, "Jackie asked to decrease a Gig for the turn's second Blue card"


# ================================================================ face-up Legends on the field (E5)
@pytest.mark.xfail(strict=True, reason="S0-E5: face-up Legend counts read the Legends area only; a solo'd Legend on the field is not counted")
def test_synapse_burnout_counts_a_legend_standing_on_the_field_including_itself(pool):
    """Synapse Burnout: *"Does this effect count friendly face-up Legends in the field area?
    Yes."* and *"...a friendly Legend in that field area that is now also a Unit, does the Legend
    count itself for a +1? Yes."*"""
    s = board(pool, Side(field=[("v-streetkid", {"faceup": True}), "psycho-squad"],
                         legends=[("padre-man-of-the-cross", {"faceup": True}), "wakako-okada-peace-and-harmony"],
                         hand=["synapse-burnout"], eddies=E), Side())
    v = find(s, "v-streetkid", Zone.FIELD, 0)
    play(s, "synapse-burnout")
    do(s, Pick((s.units(0).index(v),)))                    # the solo'd V itself
    assert power(s, v, FIGHTING | VS_UNIT) == 6 + 2, "Padre in the area and V on the field are two face-up Legends"


@pytest.mark.xfail(strict=True, reason="S0-E5: Zetatech Berserk's discount reads the Legends area only")
def test_zetatech_berserk_discount_counts_a_legend_on_the_field(pool):
    s = board(pool, Side(field=[("v-streetkid", {"faceup": True}), "psycho-squad"],
                         legends=[("padre-man-of-the-cross", {"faceup": True})],
                         hand=["zetatech-berserk"], eddies=E), Side())
    g = find(s, "zetatech-berserk", Zone.HAND, 0)
    assert play_cost(s, 0, g) == 6 - 2


@pytest.mark.xfail(strict=True, reason="S0-E5: MaxTac Squadron cannot ready a spent Legend standing on the field")
def test_maxtac_squadron_can_ready_a_spent_legend_on_the_field(pool):
    s = board(pool, Side(field=[("maxtac-squadron", {"spent": True}), ("v-streetkid", {"faceup": True, "spent": True})],
                         legends=["padre-man-of-the-cross"], deck=FILLER), Side(deck=FILLER))
    v = find(s, "v-streetkid", Zone.FIELD, 0)
    do(s, EndTurn())
    drive(s, lambda st: False)
    assert s.i_spent[v] == 0, "the only spent face-up Legend was the one on the field, and it stayed spent"


@pytest.mark.xfail(strict=True, reason="S0-E5: Panam's draw counts the Legends area only")
def test_panam_strength_draws_for_a_legend_on_the_field(pool):
    s = board(pool, Side(field=["panam-palmer-strength-through-family", ("v-streetkid", {"faceup": True})],
                         legends=[("padre-man-of-the-cross", {"faceup": True})],
                         hand=["floor-it"], deck=FILLER), Side(gig=[(6, 3)]))
    attack(s, find(s, "panam-palmer-strength-through-family", Zone.FIELD, 0))
    assert drive(s, lambda st: st.pending is not None and st.pending.kind is ChoiceKind.PICK)
    do(s, Pick((0,)))                                      # discard the one card
    drive(s, lambda st: False)
    assert len(s.zone(0, Zone.HAND)) == 2, "discarded one, then drew one per face-up Legend: two"


# ===================================================================== Take Control (E2)
@pytest.mark.xfail(strict=True, reason="S0-E2: 'steals 1 fewer' is applied on the attack path only; effect steals bypass it")
def test_take_control_applies_to_an_effect_steal(pool):
    """Take Control: *"Does this apply to Units stealing Gigs through effects outside of
    attacking? Yes."* Appetite for Destruction's bonus steal is such an effect."""
    s = board(pool, Side(field=["animals-wrecker"], hand=["appetite-for-destruction"], eddies=E, deck=FILLER),
              Side(field=[("ruthless-lowlife", {"spent": True})], gig=[(6, 3)]))
    play(s, "appetite-for-destruction")
    u = find(s, "animals-wrecker", Zone.FIELD, 0)
    during_main(s, lambda st: st.add_mod("steal_fewer", u, 1))      # the rival's Take Control
    do(s, Attack(u))
    do(s, Target(TARGET_UNIT, find(s, "ruthless-lowlife", Zone.FIELD, 1)))
    drive(s, lambda st: False)
    assert len(s.gig[1]) == 1 and s.pending.kind is ChoiceKind.MAIN, "an effect steal ignored 'steals 1 fewer'"


def test_take_control_at_zero_means_gorilla_arms_never_fires(pool):
    """Take Control: *"...a rival Unit that would normally steal 1 Gig but is equipped with
    Gorilla Arms, how many Gigs does it actually steal? 0 Gigs. ... Gorilla Arms does not
    activate."* Confirmed as the engine has it: no steal, no ``steal`` event."""
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["gorilla-arms"]})], gig=[(4, 1)], deck=FILLER),
              Side(gig=[(6, 3), (8, 5)]))
    u = find(s, "psycho-squad", Zone.FIELD, 0)
    during_main(s, lambda st: st.add_mod("steal_fewer", u, 1))
    attack(s, u)
    drive(s, lambda st: False)
    assert len(s.gig[1]) == 2 and len(s.gig[0]) == 1


# ================================================================== Bootleg's sold card (E7)
@pytest.mark.xfail(strict=True, reason="S0-E7: the sold top card lands face-up in the Eddies area; FAQ says nobody looks at it")
def test_bootleg_sells_the_top_card_unseen(pool):
    """Bootleg Black Sapphire Show: *"Do I reveal or get to look at the card I am selling? No."*"""
    s = board(pool, Side(hand=["bootleg-black-sapphire-show"], eddies=5, deck=["floor-it", "mantis-blades"]),
              Side())
    play(s, "bootleg-black-sapphire-show")
    sold = [i for i in s.zone(0, Zone.EDDIES) if s.card(i).id == "mantis-blades"]
    assert sold, "the top card was not sold"
    assert not knows_identity(s, 0, sold[0]) and not knows_identity(s, 1, sold[0])


# ============================================================== small script corrections (E1)
@pytest.mark.xfail(strict=True, reason="S0-E1: Sketchy Ripper must take a Gear if there is one; FAQ allows revealing none")
def test_sketchy_ripper_may_reveal_nothing(pool):
    """Sketchy Ripper: *"...can I choose not to reveal any cards and bottom-deck them all even
    if there's a Gear among them? Yes."*"""
    s = board(pool, Side(field=["sketchy-ripper"], deck=["floor-it", "mantis-blades", "psycho-squad", "corpo-security"]),
              Side(gig=[(6, 3)]))
    attack(s, find(s, "sketchy-ripper", Zone.FIELD, 0))
    assert drive(s, lambda st: st.pending is not None and st.pending.kind is ChoiceKind.PICK and st.pending.player == 0)
    assert Pick(()) in s.pending.options, "no way to decline the Gear"


@pytest.mark.xfail(strict=True, reason="S0-E1: Misty offers three card types; FAQ says Legend is a fourth")
def test_misty_may_name_legend(pool):
    """Misty Olszewski: *"Can I choose 'Legends' for this effect? Yes."*"""
    s = board(pool, Side(field=["misty-olszewski-mender-of-broken-spirits"], deck=FILLER), Side(deck=FILLER))
    do(s, EndTurn())
    assert s.pending.kind is ChoiceKind.PICK and s.pending.player == 0
    assert len(s.pending.options) == 4


@pytest.mark.xfail(strict=True, reason="S0-E1: El Sombrerón's pay is not offered without a max Gig; FAQ allows paying for nothing")
def test_el_sombreron_may_pay_with_no_max_gig(pool):
    """El Sombrerón: *"If I do not control a friendly max Gig can I still pay 2 €$ for El
    Sombrerón's effect? Yes, but El Sombrerón won't gain any power from it."*"""
    s = board(pool, Side(field=["el-sombreron-la-venganza-lenta"], eddies=2, gig=[(6, 3)]), Side(gig=[(6, 3)]))
    attack(s, find(s, "el-sombreron-la-venganza-lenta", Zone.FIELD, 0))
    assert drive(s, lambda st: st.pending is not None and st.pending.kind is ChoiceKind.PICK and st.pending.player == 0), \
        "no offer to pay"


@pytest.mark.xfail(strict=True, reason="S0-E1: El Sombrerón takes the largest max Gig; FAQ lets the player choose which")
def test_el_sombreron_chooses_which_max_gig(pool):
    """El Sombrerón: *"If I control multiple friendly max Gigs, can I choose which one El
    Sombrerón's effect uses? Yes."*"""
    s = board(pool, Side(field=["el-sombreron-la-venganza-lenta"], eddies=2, gig=[(4, 4), (6, 6)]), Side(gig=[(6, 3)]))
    u = find(s, "el-sombreron-la-venganza-lenta", Zone.FIELD, 0)
    attack(s, u)
    assert drive(s, lambda st: st.pending is not None and st.pending.kind is ChoiceKind.PICK and st.pending.player == 0)
    do(s, Pick((0,)))                                      # yes, pay
    assert s.pending.kind is ChoiceKind.PICK and len(s.pending.options) == 2, "which max Gig was not asked"
    do(s, Pick((0,)))                                      # the d4
    assert power(s, u) == 4 + 4


# ======================================================================= Dying Night (E4)
@pytest.mark.xfail(strict=True, reason="S0-E4: Dying Night's end-of-turn ready needs its host on the field; FAQ pays out after V died")
def test_dying_night_readies_eddies_even_if_v_died(pool):
    """Dying Night: *"If this Gear is attached to a Unit named 'V' and the Unit attacks but is
    defeated before the end of the turn, can I still ready 2 Eddies? Yes."*"""
    s = board(pool, Side(field=[("v-roamer-of-the-badlands", {"gear": ["dying-night-vs-pistol"]})],
                         eddies=2, spent_eddies=2, gig=[(6, 3)], deck=FILLER),
              Side(field=[("animals-wrecker", {"spent": True})], deck=FILLER))
    v = find(s, "v-roamer-of-the-badlands", Zone.FIELD, 0)
    attack(s, v)
    drive(s, lambda st: False)
    assert s.i_zone[v] is Zone.TRASH, "V should have lost the fight"
    do(s, EndTurn())
    drive(s, lambda st: False)
    assert all(not s.i_spent[i] for i in s.zone(0, Zone.EDDIES)), "the 2 Eddies did not ready"


# ===================================================================== Flathead (E3)
@pytest.mark.xfail(strict=True, reason="S0-E3: unblockability is re-read when the reaction menu is built; FAQ fixes it at declaration")
def test_flathead_stays_unblockable_when_cred_flips_after_declaration(pool):
    """MTOD12 Flathead: *"If I have lower Street Cred when I attack with MT0D12 Flathead, but
    triggered effects or reactions make my Rival's Street Cred lower than mine, can my Rival then
    block the MT0D12 Flathead's attack? No."* Dying Night's ATTACK decreases the rival's Gig."""
    s = board(pool, Side(field=[("mtod12-flathead", {"gear": ["dying-night-vs-pistol"]})], gig=[(6, 3)], deck=FILLER),
              Side(field=["corpo-security"], gig=[(6, 4)], deck=FILLER))
    attack(s, find(s, "mtod12-flathead", Zone.FIELD, 0))
    legal_actions(s)
    ch = s.pending
    assert ch.kind is ChoiceKind.PICK and ch.player == 0          # Dying Night: decrease a Gig
    apply(s, _pick_rival_decrease(s, ch))                          # the rival's d6, 4 -> 2
    legal_actions(s)
    while s.pending is not None and s.pending.kind is not ChoiceKind.REACTION and s.pending.kind is not ChoiceKind.MAIN:
        apply(s, 0)
        legal_actions(s)
    assert s.gig[1] == [(6, 2)], "the ATTACK trigger should have made the rival's cred lower"
    if s.pending is not None and s.pending.kind is ChoiceKind.REACTION:
        assert not any(isinstance(o, Block) for o in s.pending.options), "Flathead became blockable mid-attack"


def _pick_rival_decrease(s, ch):
    """Index of the adjust option that lowers the rival's first Gig by 2 (closure of adjust_up_to)."""
    vals = None
    for cell in (ch.cont.__closure__ or ()):
        v = cell.cell_contents
        if isinstance(v, list) and v and isinstance(v[0], tuple) and len(v[0]) == 3:
            vals = v
    assert vals is not None, "could not read the adjust options"
    for i, o in enumerate(ch.options):
        if o.picks and vals[o.picks[0]] == (1, 0, -2):
            return i
    raise AssertionError(f"no option decreases the rival's Gig by 2: {vals}")


# ====================================================================== engine tells (E10, E11)
@pytest.mark.xfail(strict=True, reason="S0-E10: the reaction window is skipped when the defender can only Pass, which tells the attacker the defender has nothing")
def test_the_reaction_window_opens_even_when_the_defender_can_only_pass(pool):
    s = board(pool, Side(field=["psycho-squad"], deck=FILLER), Side(gig=[(6, 3)], deck=FILLER))
    attack(s, find(s, "psycho-squad", Zone.FIELD, 0))
    assert drive(s, lambda st: st.pending is not None and st.pending.kind is ChoiceKind.REACTION), \
        "no reaction window: the attacker learns the defender has no reaction"
    assert [type(o) for o in s.pending.options] == [Pass]


@pytest.mark.xfail(strict=True, reason="S0-E11: root dedup keys on true identities of face-down slots the seat cannot tell apart")
def test_root_dedup_does_not_read_identities_the_seat_does_not_know(pool):
    """Two different face-down Legends whose slots the owner has not looked at are one choice
    from the owner's seat (the multiset is known, the slot order is not: ``view``)."""
    from cptcg.agents.base import make_agent
    s = board(pool, Side(legends=["padre-man-of-the-cross", "wakako-okada-peace-and-harmony"], eddies=2), Side())
    agent = make_agent("ismcts:8")
    agent.new_game(1, 0)
    legal_actions(s)
    kept = agent._root_actions(s, s.pending)
    calls = [a for a in (kept if kept is not None else s.pending.options) if isinstance(a, CallLegend)]
    assert len(calls) == 1, f"the seat cannot tell the two slots apart, yet the root offers {len(calls)} Calls"


# ============================================== documented approximations (category ii, no change)
def test_two_deadman_transmitters_on_one_host_are_not_asked_about(pool):
    """Deadman Transmitter: *"...with two or more Deadman Transmitters is defeated, do I have to
    defeat both? No, choose one of them."* Two copies of one card: the choice has no
    distinguishable branch (ruling 046's own argument), so the engine takes the first. Recorded,
    not changed; awaiting the ruling."""
    s = board(pool, Side(field=[("psycho-squad", {"gear": ["deadman-transmitter", "deadman-transmitter"]})]), Side())
    u = find(s, "psycho-squad", Zone.FIELD, 0)
    defeat_now(s, u)
    assert s.i_zone[u] is Zone.FIELD and s.pending.kind is ChoiceKind.MAIN
    assert sum(1 for i in s.zone(0, Zone.TRASH) if s.card(i).id == "deadman-transmitter") == 1


def test_kiroshi_optics_hosts_are_friendly_only(pool):
    """Kiroshi Optics prints "(Equip to a Unit or friendly face-up Legend.)"; the engine offers
    friendly Units only, as for every Gear (``legal.gear_hosts``). Whether "a Unit" reaches rival
    Units is a ruling for the owner of the project; recorded here so the reading cannot drift."""
    from cptcg.core.legal import gear_hosts
    s = board(pool, Side(field=["psycho-squad"], hand=["kiroshi-optics"], eddies=E), Side(field=["corpo-security"]))
    assert gear_hosts(s, 0) == [find(s, "psycho-squad", Zone.FIELD, 0)]


def test_null_street_cred_compares_as_zero(pool):
    """CR 11.2.3: Street Cred with no Gigs is Null. The engine compares Null as 0 in ``less_cred``
    / ``more_cred`` and honours Null only in ``cred_even``. With dice on the board Street Cred is
    at least 1, so the two readings differ only Null-versus-Null. Recorded as an approximation."""
    from cptcg.core.effects import EffectCtx
    s = board(pool, Side(field=["psycho-squad"]), Side())
    c = EffectCtx(s, find(s, "psycho-squad", Zone.FIELD, 0))
    assert not c.less_cred() and not c.more_cred() and not c.cred_even()
    s2 = board(pool, Side(field=["psycho-squad"]), Side(gig=[(4, 1)]))
    c2 = EffectCtx(s2, find(s2, "psycho-squad", Zone.FIELD, 0))
    assert c2.less_cred()


def test_search_leftovers_go_to_the_bottom_in_their_original_order(pool):
    """CR: bottom-decked cards may go in any order; the engine keeps the leftovers' top-to-bottom
    order and never asks. Recorded as an approximation (no card reads the bottom of a deck)."""
    s = board(pool, Side(field=["sketchy-ripper"], deck=["riot-shield", "floor-it", "psycho-squad", "corpo-security"]),
              Side(gig=[(6, 3)]))
    attack(s, find(s, "sketchy-ripper", Zone.FIELD, 0))
    drive(s, lambda st: False)
    deck = [s.card(i).id for i in s.zone(0, Zone.DECK)]      # index 0 is the bottom
    assert deck == ["floor-it", "psycho-squad", "corpo-security", "riot-shield"]
