"""Batch A15 — "Units with activated abilities" (wnc.py, the three scripts now at 1446-1478).

Cards: judy-alvarez-nothing-to-doubt, kerry-eurodyne-the-last-rockerboy,
rogue-amendiares-queen-of-the-afterlife.

One new finding (Kerry) carries a strict xfail naming its id. Rogue's defect is the one batch B01
already filed as AUD-rogue-amendiares-queen-of-the-afterlife-1; this batch reproduced it from a
different board and does **not** re-file the xfail — a finding id belongs to one test. What is left
here for Rogue is the boundary control B01 does not have, plus the clauses this audit cleared.

Every assertion is a printed-text outcome — zones, hand size, ``power()``, ready/spent Eddies, and
which actions the engine offers — never a script internal.

Report: out/audit/a15/findings.md
"""
import pytest
from conftest import Side, board, do, find, options

from cptcg.core.actions import Activate, Attack
from cptcg.core.enums import Zone
from cptcg.core.ops import power

E = 9


def ready_eddies(s, p=0):
    return sum(1 for i in s.zone(p, Zone.EDDIES) if not s.i_spent[i])


# ------------------------------------------------------ kerry-eurodyne-the-last-rockerboy
#: "⊡: If you control a Gig with 8+ value, draw 2."  The condition is printed inside the effect,
#: after the colon, not beside the cost — so spending Kerry is a legal play whatever the Gigs show;
#: it simply draws nothing.  Alt Cunningham *Mother of Daemons* ("When a friendly equipped Unit or
#: Legend is spent, draw 1") is what makes that line worth taking, and the script's ``legal=`` gate
#: removes it from the menu entirely.
@pytest.mark.xfail(strict=True,
                   reason="AUD-kerry-eurodyne-the-last-rockerboy-1: a printed resolution condition "
                          "is implemented as an activation restriction, so the ability cannot be used at all")
def test_kerry_may_be_spent_without_an_eight_plus_gig(pool):
    s = board(pool, Side(field=[("kerry-eurodyne-the-last-rockerboy", {"gear": ["kiroshi-optics"]}),
                                "alt-cunningham-mother-of-daemons"],
                         gig=[(10, 4)], deck=["floor-it"] * 3), Side())
    u = find(s, "kerry-eurodyne-the-last-rockerboy")
    assert Activate(u, 0) in options(s)
    do(s, Activate(u, 0))
    assert s.i_spent[u]
    assert len(s.zone(0, Zone.HAND)) == 1          # Alt's 1; Kerry's own "if" failed, so no draw 2


def test_braindance_judy_may_be_spent_with_nothing_to_find(pool):
    """Control for the xfail above: the same printed shape ("⊡: <do X>. If <X was Y>, ...") on a
    sibling card carries no activation gate — Judy *Braindance Maestro* may be spent with an empty
    deck, and simply does nothing. That is the house style Kerry departs from."""
    s = board(pool, Side(field=["judy-alvarez-braindance-maestro"]), Side())
    u = find(s, "judy-alvarez-braindance-maestro")
    assert Activate(u, 0) in options(s)
    do(s, Activate(u, 0))
    assert s.i_spent[u] and len(s.zone(0, Zone.HAND)) == 0


def test_kerry_draws_two_with_an_eight_plus_gig_and_only_counts_your_own(pool):
    """Control: Kerry's payload itself is right — 8+ on *your* Gigs draws 2, and a rival's 8+ does
    not count, so the defect is the gate and nothing else."""
    s = board(pool, Side(field=["kerry-eurodyne-the-last-rockerboy"], gig=[(10, 8)],
                         deck=["floor-it"] * 3), Side(gig=[(10, 9)]))
    do(s, Activate(find(s, "kerry-eurodyne-the-last-rockerboy"), 0))
    assert len(s.zone(0, Zone.HAND)) == 2

    s = board(pool, Side(field=["kerry-eurodyne-the-last-rockerboy"], gig=[(10, 4)],
                         deck=["floor-it"] * 3), Side(gig=[(10, 9)]))
    assert Activate(find(s, "kerry-eurodyne-the-last-rockerboy"), 0) not in options(s)


# ------------------------------------------------- rogue-amendiares-queen-of-the-afterlife
def test_rogue_does_not_ready_when_the_value_equals_the_thiefs_power(pool):
    """Control for AUD-rogue-amendiares-queen-of-the-afterlife-1 (filed by batch B01): the boundary
    the other direction. "value **less than** its power" — a d12 showing 6 stolen by a power-6 Unit
    is not less than 6, so the trigger stays silent and no Eddie readies."""
    s = board(pool, Side(field=["rogue-amendiares-queen-of-the-afterlife", "psycho-squad"],
                         eddies=4, spent_eddies=4),
              Side(gig=[(12, 6)]))
    do(s, Attack(find(s, "psycho-squad")))
    assert s.gig[0] == [(12, 6)] and ready_eddies(s) == 0


def test_rogues_own_steal_never_pays_out(pool):
    """Control: "**another** friendly Unit" — Rogue stealing for herself is not another Unit, so a
    d12 showing 3 (3 < her power of 4) readies nothing."""
    s = board(pool, Side(field=["rogue-amendiares-queen-of-the-afterlife"], eddies=4,
                         spent_eddies=4), Side(gig=[(12, 3)]))
    do(s, Attack(find(s, "rogue-amendiares-queen-of-the-afterlife")))
    assert s.gig[0] == [(12, 3)] and ready_eddies(s) == 0


def test_rogue_drain_works_as_a_quick_reaction_on_the_rivals_turn(pool):
    """Control: "QUICK 2 €$, ⊡: A rival Unit loses power equal to this Unit's power this turn."
    QUICK means the ability is offered in the reaction window when a rival Unit attacks, "a rival
    Unit" is read from Rogue's controller's seat, and the cost really is 2 €$ plus Rogue herself.
    Animals Wrecker attacks at 10, drops to 6, and ties with Psycho Squad's 6 — a tie defeats both
    (rules.md "Fight"; ruling 010)."""
    s = board(pool, Side(field=["rogue-amendiares-queen-of-the-afterlife",
                                ("psycho-squad", {"spent": True})], eddies=E),
              Side(field=["animals-wrecker"]), active=1)
    rogue = find(s, "rogue-amendiares-queen-of-the-afterlife")
    atk = find(s, "animals-wrecker")
    assert power(s, atk) == 10 and power(s, rogue) == 4
    do(s, Attack(atk))
    assert Activate(rogue, 0) in s.pending.options
    do(s, Activate(rogue, 0))
    assert s.i_zone[atk] == Zone.TRASH and s.i_zone[find(s, "psycho-squad")] == Zone.TRASH
    assert s.i_spent[rogue]
    assert sum(1 for i in s.zone(0, Zone.EDDIES) if s.i_spent[i]) == 2


def test_rogue_drain_counts_her_own_temporary_power(pool):
    """Control: "equal to **this Unit's** power" is her power as it stands when the effect resolves,
    buffs included, and ruling 029 floors the result at 0 rather than going negative."""
    from cptcg.core.ops import add_temp_power
    s = board(pool, Side(field=["rogue-amendiares-queen-of-the-afterlife"], eddies=E),
              Side(field=["psycho-squad"]))
    rogue = find(s, "rogue-amendiares-queen-of-the-afterlife")
    add_temp_power(s, rogue, 3)
    s.invalidate()
    assert power(s, rogue) == 7
    do(s, Activate(rogue, 0))                       # one rival Unit, so no question is asked
    assert power(s, find(s, "psycho-squad")) == 0   # 6 - 7, floored at 0


# -------------------------------------------------------- judy-alvarez-nothing-to-doubt
def test_judy_nothing_to_doubt_equips_a_revealed_gear_for_free(pool):
    """Control: "You may play it for free" covers a Gear — it is equipped, not merely held, and the
    1 €$ of the ability's cost is the only Eddie spent."""
    s = board(pool, Side(field=["judy-alvarez-nothing-to-doubt"], eddies=E, deck=["kiroshi-optics"]),
              Side())
    u = find(s, "judy-alvarez-nothing-to-doubt")
    do(s, Activate(u, 0))
    do(s, s.pending.options[0])                    # yes; Judy is the only host, so no second question
    g = find(s, "kiroshi-optics")
    assert s.i_zone[g] == Zone.FIELD and s.i_host[g] == u
    assert sum(1 for i in s.zone(0, Zone.EDDIES) if s.i_spent[i]) == 1


def test_judy_nothing_to_doubt_with_an_empty_deck_does_nothing(pool):
    """Control: "Reveal the top card of your deck" with no deck — the ability is still offered (no
    printed condition gates it) and simply finds nothing."""
    s = board(pool, Side(field=["judy-alvarez-nothing-to-doubt"], eddies=E), Side())
    u = find(s, "judy-alvarez-nothing-to-doubt")
    assert Activate(u, 0) in options(s)
    do(s, Activate(u, 0))
    assert s.i_spent[u] and len(s.zone(0, Zone.HAND)) == 0
