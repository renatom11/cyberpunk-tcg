"""Batch B05 confirmations — replacement and permission effects.

Cross-cutting pass over `CardScript.attack_perm`, `CardScript.self_cost`,
`CardScript.unblockable` and the `script.extra` dict. Each of these was suspected, tested, and
found correct; they are kept because they are coverage the pool did not have. See
`out/audit/b05/findings.md`. Printed-text outcomes only — zones, Gig areas, legal attacks,
`ops.has_keyword`, `ops.available`.
"""
import pytest
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, Block, Play, Target
from cptcg.core.enums import TARGET_GIG, TARGET_UNIT, Keyword, Zone
from cptcg.core.ops import available, has_keyword

E = 12  # plenty of Eddies


def play(s, cid):
    """Play ``cid`` from hand, picking whatever host the engine offers for Gear."""
    inst = find(s, cid, Zone.HAND)
    for o in s.pending.options:
        if isinstance(o, Play) and o.inst == inst:
            do(s, o)
            return s
    raise AssertionError(f"{cid} is not playable here: {s.pending.options}")


# --------------------------------------------------------------- attack_perm: which half
def test_nadia_may_attack_the_gig_area_on_arrival_but_not_a_rival_unit(pool):
    """'If a Rival controls more Gigs than you, this Unit can attack their Gig area the turn it's
    played.' `attack_perm` returns the pair (may attack Units, may attack the Gig area) and Nadia
    sets only the second. The board gives her both a legal Gig area and a legal Unit target — the
    rival's Corpo Security is *spent*, and a spent rival Unit is what an unlagged attacker may
    attack — so the Gig area being the only thing she can reach is Nadia's text, not the board's.
    """
    s = board(pool, Side(hand=["nadia-fighting-through-grief"], eddies=E, gig=[(4, 2)]),
              Side(field=[("corpo-security", {"spent": True})], gig=[(6, 3), (8, 4), (10, 5)]))
    play(s, "nadia-fighting-through-grief")
    n = find(s, "nadia-fighting-through-grief", Zone.FIELD)
    assert Attack(n) in s.pending.options                 # she may attack the turn she is played
    do(s, Attack(n))                                      # one legal target: the engine declares it
    assert s.pending.prompt == "Steal which Gig(s)?"      # the target was the Gig area
    do(s, s.pending.options[0])
    assert len(s.gig[1]) == 2 and len(s.gig[0]) == 2      # a Gig changed hands
    assert s.i_zone[find(s, "corpo-security")] is Zone.FIELD   # the rival's Unit was never reachable


def test_sandayu_may_attack_a_rival_unit_on_arrival_but_not_the_gig_area(pool):
    """'This Unit can attack rival Units the turn it's played.' The mirror of Nadia: Sandayu sets
    only the first half of the pair. Gigs 2 and 3 are not a value-pair, so his PLAY clause spends
    nothing and asks nothing; the rival holds three Gigs and one spent Unit, so both target kinds
    are on offer to any Unit that may take them.
    """
    s = board(pool, Side(hand=["sandayu-oda-hanakos-guardian"], eddies=E, gig=[(4, 2), (6, 3)]),
              Side(field=[("corpo-security", {"spent": True})], gig=[(6, 3), (8, 4), (10, 5)]))
    play(s, "sandayu-oda-hanakos-guardian")
    o = find(s, "sandayu-oda-hanakos-guardian", Zone.FIELD)
    assert Attack(o) in s.pending.options
    do(s, Attack(o))                                      # one legal target: the rival's spent Unit
    assert s.i_zone[find(s, "corpo-security")] is Zone.TRASH    # power 8 beat power 2
    assert len(s.gig[1]) == 3 and s.gig[0] == [(4, 2), (6, 3)]  # no Gig changed hands


@pytest.mark.parametrize("cid,mygig", [("nadia-fighting-through-grief", [(4, 2)]),
                                       ("sandayu-oda-hanakos-guardian", [(4, 2), (6, 3)])])
def test_maxtac_suppression_team_beats_both_printed_attack_on_arrival_permissions(pool, cid, mygig):
    """'Rival Units can't attack the turn they're played.' A prohibition is a claim about every
    path, and the two cards in the set that print the opposite permission in so many words are the
    hardest case for it. `attack_permission` returns (False, False) for a suppressed Unit *before*
    it consults the Unit's own `attack_perm`, so the MaxTac player's prohibition wins — the same
    precedence that makes it beat ADRENALINE. Each board is the one above with a MaxTac Suppression
    Team added, so the attack that was legal there is illegal here for one reason.
    """
    s = board(pool, Side(hand=[cid], eddies=E, gig=mygig),
              Side(field=["maxtac-suppression-team", ("corpo-security", {"spent": True})],
                   gig=[(6, 3), (8, 4), (10, 5)]))
    play(s, cid)
    u = find(s, cid, Zone.FIELD)
    assert Attack(u) not in s.pending.options


# --------------------------------------------------------------------- unblockable
@pytest.mark.parametrize("target_kind", [TARGET_GIG, TARGET_UNIT])
def test_flathead_cannot_be_blocked_only_while_behind_on_street_cred(pool, target_kind):
    """'If you have less ★ (Street Cred) than a Rival, this Unit can't be blocked.' Blocking in
    this game exists only as the BLOCKER redirect, and ruling 012 lets a BLOCKER redirect an attack
    aimed at a spent Unit as well as one aimed at a Gig area — so the prohibition is checked
    against both target kinds. The two boards differ only in the value of the attacker's own die.
    """
    def run(mygig):
        s = board(pool, Side(field=["mtod12-flathead"], gig=mygig),
                  Side(field=["secondhand-bombus", ("corpo-security", {"spent": True})],
                       gig=[(10, 6)], eddies=3))
        f = find(s, "mtod12-flathead", Zone.FIELD)
        do(s, Attack(f))
        tgt = (Target(TARGET_GIG) if target_kind == TARGET_GIG
               else Target(TARGET_UNIT, find(s, "corpo-security", Zone.FIELD, player=1)))
        do(s, tgt)
        return any(isinstance(o, Block) for o in s.pending.options)

    assert run([(4, 1)]) is False        # 1 ★ against 6 ★: behind, so no Block is ever offered
    assert run([(20, 20)]) is True       # 20 ★ against 6 ★: ahead, so the BLOCKER may redirect


# ------------------------------------------------------------- kw_mod / conditional ADRENALINE
def test_adrenaline_converter_grants_adrenaline_only_while_two_gigs_behind(pool):
    """'If a Rival controls at least 2 more Gigs than you, this Unit has ADRENALINE.' The only
    conditional keyword grant in the set. It is re-read on every `has_keyword` call rather than
    granted once, so the host loses it the moment the Gig gap closes — and while it holds, it is
    enough to beat Lag on a Unit played earlier this turn.
    """
    s = board(pool, Side(hand=["adrenaline-converter"], eddies=E,
                         field=[("psycho-squad", {"lag": True})], gig=[(4, 1)]),
              Side(field=[("corpo-security", {"spent": True})], gig=[(6, 3), (8, 4), (10, 5)]))
    u = find(s, "psycho-squad", Zone.FIELD)
    assert not has_keyword(s, u, Keyword.ADRENALINE)
    assert Attack(u) not in s.pending.options            # lagged, and nothing grants an attack yet
    play(s, "adrenaline-converter")                      # 3 rival Gigs against 1: 2 more
    assert has_keyword(s, u, Keyword.ADRENALINE)
    assert Attack(u) in s.pending.options                # ... and ADRENALINE beats Lag
    s.gig[1] = [(6, 3), (8, 4)]                          # the gap closes to 1
    assert not has_keyword(s, u, Keyword.ADRENALINE)


# ------------------------------------------------------------------------- self_cost
def test_maxtac_heavy_and_octant_discounts_are_paid_and_floored_at_one(pool):
    """'Play this Unit for -1 €$ for each of a Rival's Units / for each friendly Gig with 8+ value,
    to a minimum of 1 €$.' Both print a cost of 7. The discount is measured at payment, not only in
    the menu: exactly five Eddies buy MaxTac Heavy against two rival Units and leave none.
    """
    s = board(pool, Side(hand=["maxtac-heavy"], eddies=5), Side(field=["psycho-squad", "corpo-security"]))
    assert available(s, 0) == 5
    play(s, "maxtac-heavy")                                    # 7 - 2 = 5
    assert s.i_zone[find(s, "maxtac-heavy")] is Zone.FIELD and available(s, 0) == 0

    s2 = board(pool, Side(hand=["maxtac-heavy"], eddies=1), Side(field=["psycho-squad"] * 8))
    play(s2, "maxtac-heavy")                                   # 7 - 8, floored at 1
    assert s2.i_zone[find(s2, "maxtac-heavy")] is Zone.FIELD and available(s2, 0) == 0

    # Octant: a d20 showing 8 and a d10 showing 10 count, a d6 showing 6 does not.
    s3 = board(pool, Side(hand=["octant"], eddies=5, gig=[(20, 8), (10, 10), (6, 6)]), Side())
    play(s3, "octant")                                         # 7 - 2 = 5
    assert s3.i_zone[find(s3, "octant")] is Zone.FIELD and available(s3, 0) == 0


# ------------------------------------------- extra: attack_ready_blockers_if_more_cred
def test_valentino_guerrera_reaches_a_ready_blocker_only_and_only_when_ahead(pool):
    """'If you have more ★ (Street Cred) than a Rival, this Unit can attack ready Units with
    BLOCKER.' Ready Units are not legal attack targets at all, so this `extra` key is a hole punched
    in that rule for exactly one kind of Unit. The rival fields one ready BLOCKER (Corpo Security)
    and one ready non-BLOCKER (Psycho Squad); only the first is ever reachable, and only while
    Valentino's controller is ahead on ★.
    """
    def targets(mygig):
        s = board(pool, Side(field=["valentino-guerrera"], gig=mygig),
                  Side(field=["corpo-security", "psycho-squad"], gig=[(6, 5)]))
        v = find(s, "valentino-guerrera", Zone.FIELD)
        do(s, Attack(v))
        opts = s.pending.options if s.pending.kind.name == "TARGET" else ()
        return sorted(s.card(t.inst).id if t.kind == TARGET_UNIT else "GIG" for t in opts)

    assert targets([(20, 20)]) == ["GIG", "corpo-security"]
    assert targets([(4, 1)]) == []          # behind: the Gig area is the only target, declared for you
