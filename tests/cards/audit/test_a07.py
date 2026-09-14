"""Batch A07 — Units: ATTACK / DEFEATED triggers.

Audit of src/cptcg/cards/sets/wnc.py lines 616-693 against the printed text in
data/cards/wnc.json. Every assertion below is a printed-text outcome — a zone, a hand, an
effective power — never a script internal.
"""
import pytest
from conftest import Side, board, do, find

from cptcg.core.actions import Attack
from cptcg.core.actions import Pick
from cptcg.core.enums import Zone
from cptcg.core.ops import power


def test_el_sombreron_gains_the_value_of_a_max_gig_not_the_largest_value(pool):
    """'ATTACK: You may pay 2 €$. If you do, this Unit gains power equal to a friendly max Gig
    this turn.'

    'max Gig' is set terminology, the mirror of the 'min Gig' that six other cards in wnc.json
    use (Alt Cunningham, Chrome Reverie, Jackie Welles *Pour One Out For Me*, Pyramid Song,
    Three Mouths One Desire, Trust No One). A min Gig is a die showing its *minimum* face —
    `EffectCtx.min_gigs` is documented as "indices of dice showing their minimum face (1)", and
    every one of those six scripts reads it (wnc.py:111, 179, 361, 1320, 1331). A max Gig is
    therefore a die showing its *maximum* face: exactly `EffectCtx.max_gigs` (effects.py:124,
    `v == k`), the one Gig helper no script in the repo calls.

    Board: a d12 showing 9 and a d4 showing 4. The only max Gig is the d4, so El Sombrerón
    (printed power 4+) should end at 4 + 4 = 8. wnc.py:675 uses `max(c2.gig_values())`, the
    largest *value* in the area, and gives 4 + 9 = 13.

    Fixed: AUD-el-sombreron-la-venganza-lenta-1.
    """
    s = board(pool, Side(field=["el-sombreron-la-venganza-lenta"], eddies=2, gig=[(12, 9), (4, 4)]),
              Side(gig=[(4, 1)]))
    u = find(s, "el-sombreron-la-venganza-lenta")
    do(s, Attack(u))
    do(s, Pick((0,)))                                       # pay the 2 €$
    assert power(s, u) == 8


def test_sketchy_ripper_must_take_the_gear_it_finds(pool):
    """'ATTACK: Search the top 3 cards of your deck. Reveal a Gear and add it to your hand.
    Bottom-deck the rest.'

    The clause is imperative and singular. The set says so explicitly when a search is optional
    or open-ended — Viktor Vektor reads 'Reveal **up to 2** Gears ... and add them', Hanako
    reads 'Reveal **any number** of cards ... and add them', and Three Mouths One Desire's
    mandatory half ('Add 1 to your hand') is scripted with `lo=1` (wnc.py:179). Sketchy Ripper
    has neither hedge, so a Gear among the top 3 must go to hand.

    Top 3 of the deck hold exactly one Gear (Mantis Blades). With `lo=1` that pick is the only
    option and auto-resolves, leaving the Gear in hand as the attack continues. wnc.py:627 asks
    with `lo=0`, so the engine offers `Pick(())` — decline — and the Gear is still in the deck.

    Fixed: AUD-sketchy-ripper-1.
    """
    s = board(pool, Side(field=["sketchy-ripper"], deck=["floor-it", "mantis-blades", "floor-it"]),
              Side(gig=[(4, 1)]))
    do(s, Attack(find(s, "sketchy-ripper")))
    assert s.i_zone[find(s, "mantis-blades")] == Zone.HAND


@pytest.mark.xfail(strict=True, reason="AUD-goro-takemura-losing-his-way-1: with an empty Legends area 'all friendly Legends are face-up' is vacuously true, but the script requires at least one Legend")
def test_goro_gets_the_bonus_with_an_empty_legends_area(pool):
    """'ATTACK: If all friendly Legends are face-up, this Unit has +5 power this turn.'

    An empty Legends area satisfies a universal over no members. Ruling 015's default
    (`go_solo_vacates_slot` = true) is what makes the state reachable: a Legend that GOES SOLO
    leaves its slot empty, so a player who Go-Solos all three Legends controls none. Nothing in
    the text asks for a Legend to exist — contrast Panam Palmer's 'for each friendly face-up
    Legend', which simply counts 0.

    Goro's printed power is 4+, so with no Legends at all he should attack at 4 + 5 = 9;
    wnc.py:683's `c.legends() and ...` guard makes the condition false and leaves him at 4.
    """
    s = board(pool, Side(field=["goro-takemura-losing-his-way"], legends=[]), Side(gig=[(4, 1)]))
    u = find(s, "goro-takemura-losing-his-way")
    do(s, Attack(u))
    assert power(s, u) == 9
