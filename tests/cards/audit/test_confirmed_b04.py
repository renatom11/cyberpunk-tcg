"""Batch B04 confirmations — activated abilities the audit suspected and found correct.

Coverage the pool did not have, paid for out of the audit. Each of these is a place where the
cross-cutting read of "costs, the ⊡ spend symbol, legality guards and QUICK" predicted a defect
and the engine turned out to be right; they pass, and they are here so that the next reader who
"knows" one of these cards is wrong has to explain a green test first.

Report: out/audit/b04/findings.md
"""
from conftest import Side, board, do, find, options

from cptcg.core.actions import Activate, Attack, Block, Pass, Pick
from cptcg.core.enums import Zone
from cptcg.core.ops import power


def test_rogue_quick_reacts_on_the_rivals_turn_and_reads_the_rival_side_correctly(pool):
    """"QUICK 2 €$, ⊡: A rival Unit loses power equal to this Unit's power this turn."

    QUICK means this resolves during the *rival's* turn, where "a rival Unit" has to mean the
    attacker's Units and not the controller's own. ``ops._ctx`` sets ``ctx.player`` from the
    card's owner rather than from ``s.active``, so it does. Rogue prints power 4 and a power-4
    attacker drops to 0, and a 0-power Unit steals 0 Gigs (rules table / ruling 010), so the
    reaction saves the die outright.
    """
    s = board(pool, Side(field=["rogue-amendiares-queen-of-the-afterlife"], eddies=4, gig=[(6, 3)]),
              Side(field=["emergency-atlus"]), active=1)
    atk, r = find(s, "emergency-atlus"), find(s, "rogue-amendiares-queen-of-the-afterlife")
    do(s, Attack(atk))
    assert Activate(r, 0) in options(s)          # offered as a reaction, on the rival's turn
    do(s, Activate(r, 0))
    assert power(s, atk) == 0
    assert s.gig[0] == [(6, 3)] and s.gig[1] == []     # nothing stolen
    assert s.i_spent[r]
    assert sum(1 for i in s.zone(0, Zone.EDDIES) if s.i_spent[i]) == 2    # the printed 2 €$


def test_the_same_attack_steals_when_rogue_does_not_react(pool):
    """Control for the reaction above: pass instead, and the d6 changes hands."""
    s = board(pool, Side(field=["rogue-amendiares-queen-of-the-afterlife"], eddies=4, gig=[(6, 3)]),
              Side(field=["emergency-atlus"]), active=1)
    do(s, Attack(find(s, "emergency-atlus")))
    do(s, Pass())
    assert s.gig[0] == [] and s.gig[1] == [(6, 3)]


def test_goro_quick_grants_blocker_inside_the_reaction_window(pool):
    """"QUICK 1 €$, ⊡: Give a friendly Unit with cost 4 or less BLOCKER this turn."

    The point of QUICK here is to buy a blocker after the attack is declared, so the window has to
    reopen with the new redirect legal. It does: ``Block`` on the granted Unit appears only after
    the ability resolves, and Goro's own "When a friendly Unit uses BLOCKER, you may discard 1. If
    you do, draw 1" then fires off the redirect.
    """
    s = board(pool, Side(legends=[("goro-takemura-vengeful-bodyguard", {"faceup": True})],
                         eddies=4, field=["emergency-atlus"], gig=[(6, 3)],
                         hand=["floor-it"], deck=["floor-it"] * 2),
              Side(field=["psycho-squad"]), active=1)
    g, a, ps = (find(s, "goro-takemura-vengeful-bodyguard"), find(s, "emergency-atlus"),
                find(s, "psycho-squad"))
    do(s, Attack(ps))
    assert Block(a) not in options(s)             # cost-3 Atlus has no BLOCKER of its own
    do(s, Activate(g, 0))
    assert Block(a) in options(s)
    do(s, Block(a))
    do(s, Pick((0,)))                             # "discard 1 to draw 1?" — yes
    assert len(s.zone(0, Zone.HAND)) == 1         # discarded floor-it, drew one back
    do(s, Pass())                                 # close the window; the fight resolves
    assert s.i_zone[a] is Zone.TRASH              # power 4 vs 6: the blocker loses the fight
    assert s.gig[0] == [(6, 3)]                   # a redirected attack steals nothing


def test_lag_stops_a_spend_ability_but_not_an_ability_without_the_spend_symbol(pool):
    """CR 11.3.1 and the glossary: "Units with Lag can't attack or activate self-spend effects."

    Judy *Nothing to Doubt* prints "1 €$, ⊡:" and cannot use it the turn she is played; Panam
    *Strength Through Family* prints "During your turn, you may Call a Legend for free" with no ⊡
    and can. The engine draws the line where the rule draws it, including the half of the rule
    that is a permission.
    """
    s = board(pool, Side(field=[("judy-alvarez-nothing-to-doubt", {"lag": True})],
                         eddies=4, deck=["floor-it"]), Side())
    j = find(s, "judy-alvarez-nothing-to-doubt")
    assert Activate(j, 0) not in options(s)

    s = board(pool, Side(field=["judy-alvarez-nothing-to-doubt"], eddies=4, deck=["floor-it"]),
              Side())
    j = find(s, "judy-alvarez-nothing-to-doubt")
    assert Activate(j, 0) in options(s)           # the same board without the Lag

    s = board(pool, Side(field=[("panam-palmer-strength-through-family", {"lag": True})],
                         legends=["goro-takemura-vengeful-bodyguard"]), Side())
    p = find(s, "panam-palmer-strength-through-family")
    assert Activate(p, 0) in options(s)           # no ⊡ printed, so Lag says nothing about it
    do(s, Activate(p, 0))
    do(s, Pick((0,)))                             # Call the face-down Legend, for free
    assert s.i_faceup[find(s, "goro-takemura-vengeful-bodyguard")]
    assert not s.zone(0, Zone.EDDIES)             # "for free": nothing was spent


def test_a_legend_may_not_pay_its_own_spend_ability_with_itself(pool):
    """Ruling 027: a Legend "may not spend itself toward its own cost". Face-up Goro is a payable
    source (ready, face-up, sell-tagged — CR 5.7.2.2), so with no Eddies his own "QUICK 1 €$, ⊡"
    would otherwise look affordable. It is not offered; add one Eddie and it is.
    """
    s = board(pool, Side(legends=[("goro-takemura-vengeful-bodyguard", {"faceup": True})],
                         eddies=0, field=["psycho-squad"]), Side())
    assert Activate(find(s, "goro-takemura-vengeful-bodyguard"), 0) not in options(s)

    s = board(pool, Side(legends=[("goro-takemura-vengeful-bodyguard", {"faceup": True})],
                         eddies=1, field=["psycho-squad"]), Side())
    g = find(s, "goro-takemura-vengeful-bodyguard")
    assert Activate(g, 0) in options(s)
    do(s, Activate(g, 0))
    assert s.i_spent[g]
    assert sum(1 for i in s.zone(0, Zone.EDDIES) if s.i_spent[i]) == 1
