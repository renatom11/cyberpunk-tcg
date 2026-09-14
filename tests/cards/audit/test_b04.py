"""Batch B04 — activated abilities read across the whole pool: costs, the ⊡ spend symbol,
QUICK, and ``legal=`` guards.

This is the cross-cutting pass, so the evidence is the population rather than the card. The set
holds 19 activated abilities on 18 cards. Every printed €$ number matches ``cost=``, every ability
printing ⊡ sets ``self_spend=True`` and the one that prints no ⊡ sets it ``False``, and the five
printing QUICK are exactly the five with ``quick=True`` — that axis is clean.

``legal=`` is not. Thirteen of the nineteen abilities carry no guard at all, and nine of those
thirteen are, on some legal board, an ability that can do nothing — Goro with no friendly Units,
Evelyn with no rival Units, River Ward with no Gear in hand, Padre/Wakako/Muamar/Dexter with no
dice anywhere. All nine are offered anyway: the pool's convention, and the engine's default, is
that you may pay the cost, spend the card, and have the effect find nothing. ``docs/rules.md``
states no "no legal target, no activation" rule. The tests below are the two cards in this batch
that depart from that convention without their printed text asking them to.

Report: out/audit/b04/findings.md
"""
import pytest
from conftest import Side, board, do, find, options

from cptcg.core.actions import Activate
from cptcg.core.enums import Zone

#: "When this Unit or Legend is spent, draw 1." — Netwatch Netdriver equips to a face-up Legend and
#: turns "may I spend this card?" into a printed-text outcome: a card in hand, or not.
NETDRIVER = "netwatch-netdriver"


def hand(s, p=0):
    return len(s.zone(p, Zone.HAND))


# ------------------------------------------------- alt-cunningham-soulkiller-architect
#: "⊡: Your next Program this turn plays for -1 €$ for each friendly min Gig, to a minimum of
#: 1 €$."  With no min Gig the discount is -0: the effect is fully defined and simply subtracts
#: nothing.  Nothing is printed beside the cost, there is no "if", and there is no target.  The
#: script's ``legal=lambda c: bool(c.min_gigs())`` nevertheless removes the ability from the menu,
#: so Alt cannot be spent at all.  Kerry *The Last Rockerboy* is the same shape one card family
#: over and was filed by the A15 section pass; Alt sits 300 lines away and was missed.
def test_alt_discount_is_activatable_without_a_min_gig(pool):
    """Fixed: AUD-alt-cunningham-soulkiller-architect-1."""
    s = board(pool, Side(legends=[("alt-cunningham-soulkiller-architect",
                                   {"faceup": True, "gear": [NETDRIVER]})],
                         gig=[(6, 3)], deck=["floor-it"] * 2), Side())
    a = find(s, "alt-cunningham-soulkiller-architect")
    assert Activate(a, 0) in options(s)
    do(s, Activate(a, 0))
    assert s.i_spent[a]                    # she is spent: the ⊡ was paid
    assert hand(s) == 1                    # ... so the Netdriver on her draws


def test_alt_discount_is_activatable_with_a_min_gig(pool):
    """Control for the board above: the only change is the die's face, so the fixture (a face-up
    Legend carrying a Netdriver, a deck to draw from) is sound and the finding is about the
    guard alone."""
    s = board(pool, Side(legends=[("alt-cunningham-soulkiller-architect",
                                   {"faceup": True, "gear": [NETDRIVER]})],
                         gig=[(6, 1)], deck=["floor-it"] * 2), Side())
    a = find(s, "alt-cunningham-soulkiller-architect")
    assert Activate(a, 0) in options(s)
    do(s, Activate(a, 0))
    assert s.i_spent[a] and hand(s) == 1


def test_alts_other_ability_is_offered_with_an_empty_trash(pool):
    """Control: the same Legend's second printed ability, "1 €$, ⊡: Play a Program from your
    trash", is exactly as useless with an empty trash — and carries no guard, so it is offered,
    paid for, and does nothing. One card, two abilities, two different answers to the same
    question."""
    s = board(pool, Side(legends=[("alt-cunningham-soulkiller-architect",
                                   {"faceup": True, "gear": [NETDRIVER]})],
                         eddies=3, gig=[(6, 3)], deck=["floor-it"] * 2), Side())
    a = find(s, "alt-cunningham-soulkiller-architect")
    assert Activate(a, 1) in options(s)
    do(s, Activate(a, 1))
    assert s.i_spent[a] and hand(s) == 1
    assert sum(1 for i in s.zone(0, Zone.EDDIES) if s.i_spent[i]) == 1   # the printed 1 €$


# --------------------------------------------- hanako-arasaka-daughter-of-the-emperor
#: "⊡: Swap a friendly Gig with a rival Gig."  Guarded by ``gigs() and gigs(rival)``.  Padre *Man
#: of the Cross* prints the same shape — "⊡: Set a player's Gig to the same value as another
#: player's Gig" also needs a die on each side of the table — and has no guard: with no dice at all
#: he is offered, spent, and does nothing.  Two Legends, one printed shape, opposite treatment.
def test_hanako_is_not_activatable_with_no_rival_gig(pool):
    """"⊡: Swap a friendly Gig with a rival Gig."

    **Withdrawn: AUD-hanako-arasaka-daughter-of-the-emperor-1**, and the engine's behaviour pinned
    instead. The finding was that `legal=lambda c: bool(c.gigs()) and bool(c.gigs(c.rival))` adds an
    activation condition the card does not print, and that Padre *Man of the Cross* prints the same
    two-sided shape with no guard. The killer conceded. The blind reader, which was never shown the
    finding, read the same lambda and called it the minimum for a swap to be performable at all —
    "it does not add a restriction the text lacks" — and a finding an independent reader contradicts
    is not a finding.

    The question it raises is real and larger than this card, so it went to `docs/rulings.md` row
    045 (may an ability with no legal target be activated?) rather than into a fix. This test now
    says what the engine does, so that a change of mind has to be deliberate.
    """
    s = board(pool, Side(legends=[("hanako-arasaka-daughter-of-the-emperor",
                                   {"faceup": True, "gear": [NETDRIVER]})],
                         gig=[(6, 3)], deck=["floor-it"] * 2), Side())
    h = find(s, "hanako-arasaka-daughter-of-the-emperor")
    assert Activate(h, 0) not in options(s)             # nothing to swap with: not offered
    assert hand(s) == 0                                 # ... so the Netdriver on her draws nothing


def test_padre_is_activatable_with_no_dice_on_the_board_at_all(pool):
    """Control: the sibling that prints the same "a Gig on each side" requirement carries no
    guard. This is the majority pattern the finding above departs from — and it shows the
    Netdriver fixture pays out on any Legend, not just Hanako."""
    s = board(pool, Side(legends=[("padre-man-of-the-cross",
                                   {"faceup": True, "gear": [NETDRIVER]})],
                         gig=[(6, 3)], deck=["floor-it"] * 2), Side())
    p = find(s, "padre-man-of-the-cross")
    assert Activate(p, 0) in options(s)
    do(s, Activate(p, 0))
    assert s.i_spent[p] and hand(s) == 1
    assert s.gig[0] == [(6, 3)] and s.gig[1] == []


def test_hanako_swaps_when_both_players_hold_a_gig(pool):
    """Control: the payload itself is right — the two dice change areas, keeping their faces
    (ruling 005: a moved die is not rerolled) — so the finding is about the guard, not the swap."""
    s = board(pool, Side(legends=[("hanako-arasaka-daughter-of-the-emperor", {"faceup": True})],
                         gig=[(6, 3)]), Side(gig=[(8, 5)]))
    do(s, Activate(find(s, "hanako-arasaka-daughter-of-the-emperor"), 0))
    assert s.gig[0] == [(8, 5)] and s.gig[1] == [(6, 3)]
