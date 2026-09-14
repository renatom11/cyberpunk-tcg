"""Batch b01 confirmations — suspected, tested, and the engine was right.

These are the ``on_event`` hooks in the b01 card list that the cross-cutting pass put under
suspicion and could not break: the scope of "a friendly Unit" on a ``blocked`` trigger, the "or
Legend" half of the four Gear ``spent`` triggers, and the end-of-turn / start-of-turn bookkeeping.
They pass, which is why they live here and not in test_b01.py. See out/audit/b01/findings.md §3.

Every assertion is a printed-text outcome — zones, hand size, ready Eddies, Gig faces, and
``view.knows_identity`` for what a look reveals.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from conftest import Side, board, do, find                      # noqa: E402
from cptcg.core.actions import (Attack, Block, ChoiceKind, EndTurn, Play,  # noqa: E402
                                Target)
from cptcg.core.enums import F_GO_SOLO, Zone                     # noqa: E402
from cptcg.core.ops import available                             # noqa: E402
from cptcg.core.view import knows_identity                       # noqa: E402

E = 9
TARGET_GIG = 1
VANILLA_GEAR = "mantis-blades"           # cost 1, power 2, no rules text


def _resolve(s, limit=6):
    """Answer every queued prompt with its first option until the main menu comes back."""
    for _ in range(limit):
        if s.pending is None or s.pending.kind is ChoiceKind.MAIN:
            return
        do(s, s.pending.options[0])


# --------------------------------------------- goro-takemura-vengeful-bodyguard
def test_goro_fires_when_a_go_solo_legend_uses_blocker(pool):
    """'When a friendly Unit uses BLOCKER, you may discard 1. If you do, draw 1.'

    Goro's hook is the only ``blocked`` hook in the set that names *a friendly Unit* rather than
    *this Unit*, and it gates on owner only — no ``CardDef.type is UNIT``. That is the right way
    round: Goro *Hands Unclean* on the field via GO SOLO is a Unit (ruling 015), carries BLOCKER,
    and is the only kind of card ``legal.py`` will ever offer a Block for.
    """
    s = board(pool, Side(field=["psycho-squad"], eddies=E, gig=[(6, 3)]),
              Side(field=[("goro-takemura-hands-unclean", {"faceup": True, "flags": F_GO_SOLO})],
                   legends=[("goro-takemura-vengeful-bodyguard", {"faceup": True})],
                   eddies=E, hand=["floor-it"], deck=["psycho-squad"], gig=[(6, 3)]))
    do(s, Attack(find(s, "psycho-squad", Zone.FIELD, 0)))
    do(s, Target(TARGET_GIG, 0))
    do(s, Block(find(s, "goro-takemura-hands-unclean")))
    assert s.pending.player == 1                         # the offer goes to Goro's controller
    _resolve(s, limit=3)                                 # yes, discard Floor It
    assert s.i_zone[find(s, "floor-it", player=1)] == Zone.TRASH
    assert find(s, "psycho-squad", player=1) in s.zone(1, Zone.HAND)      # ... and drew 1


def test_goro_fires_when_a_plain_unit_uses_blocker(pool):
    """The same trigger for an ordinary BLOCKER Unit, so the Legend case above is not the only
    path that works."""
    s = board(pool, Side(field=["psycho-squad"], eddies=E, gig=[(6, 3)]),
              Side(field=["augmented-negotiators"],
                   legends=[("goro-takemura-vengeful-bodyguard", {"faceup": True})],
                   eddies=E, hand=["floor-it"], deck=["psycho-squad"], gig=[(6, 3)]))
    do(s, Attack(find(s, "psycho-squad", Zone.FIELD, 0)))
    do(s, Target(TARGET_GIG, 0))
    do(s, Block(find(s, "augmented-negotiators")))
    assert s.pending.player == 1
    _resolve(s, limit=4)
    assert s.i_zone[find(s, "floor-it", player=1)] == Zone.TRASH
    assert find(s, "psycho-squad", player=1) in s.zone(1, Zone.HAND)


# ------------------------------------------ alt-cunningham-mother-of-daemons
def test_alt_cunningham_draws_when_an_equipped_legend_is_spent_to_pay(pool):
    """'When a friendly equipped Unit or Legend is spent, draw 1.'

    ``ops.spend`` dispatches ``spent`` only for FIELD/LEGENDS cards that are not Gear, so the
    hook's bare owner-and-equipped test cannot pick up a spent Eddie or a spent Gear. The "or
    Legend" half is live: with no ready Eddies, paying 1 €$ for a Gear spends the equipped face-up
    Legend (CR 5.7.2.2 — face-up Legends are payable when they carry a sell tag) and Alt draws.
    """
    s = board(pool, Side(field=["alt-cunningham-mother-of-daemons"],
                         legends=[("hanako-arasaka-daughter-of-the-emperor",
                                   {"faceup": True, "gear": [VANILLA_GEAR]})],
                         hand=[VANILLA_GEAR], eddies=0, deck=["floor-it"]), Side())
    hanako = find(s, "hanako-arasaka-daughter-of-the-emperor")
    do(s, Play(find(s, VANILLA_GEAR, Zone.HAND),
               find(s, "alt-cunningham-mother-of-daemons")))
    assert s.i_spent[hanako]                              # the Legend paid for the Gear
    assert find(s, "floor-it") in s.zone(0, Zone.HAND)    # ... and Alt drew 1

    without = board(pool, Side(field=["psycho-squad"],
                               legends=[("hanako-arasaka-daughter-of-the-emperor",
                                         {"faceup": True, "gear": [VANILLA_GEAR]})],
                               hand=[VANILLA_GEAR], eddies=0, deck=["floor-it"]), Side())
    do(without, Play(find(without, VANILLA_GEAR, Zone.HAND),
                     find(without, "psycho-squad")))
    assert without.zone(0, Zone.HAND) == []               # no Alt, no draw


# ---------------------------------------------------------- netwatch-netdriver
def test_netwatch_netdriver_draws_when_its_legend_host_is_spent(pool):
    """'When this Unit or Legend is spent, draw 1.' Four Gear in this set carry a host-spent
    trigger and all four share ``_host_spent``; this pins the Legend half of "this Unit or
    Legend" for the plainest of them."""
    s = board(pool, Side(legends=[("hanako-arasaka-daughter-of-the-emperor",
                                   {"faceup": True, "gear": ["netwatch-netdriver"]})],
                         field=["psycho-squad"], hand=[VANILLA_GEAR], eddies=0,
                         deck=["floor-it"]), Side())
    do(s, Play(find(s, VANILLA_GEAR, Zone.HAND), find(s, "psycho-squad")))
    assert find(s, "floor-it") in s.zone(0, Zone.HAND)


# -------------------------------------------------- arasaka-emergency-radioport
def test_radioport_calls_a_go_solo_legend_for_free_when_its_host_is_spent(pool):
    """'When this Unit or Legend is spent, you may look at a friendly face-down Legend. If that
    Legend is ARASAKA or has GO SOLO, you may Call it for free.'

    V *Corporate Exile* is neither ARASAKA nor anything else — it is the GO SOLO half of the
    conditional — and the free Call turns it face-up in the Legends area.
    """
    s = board(pool, Side(legends=[("hanako-arasaka-daughter-of-the-emperor",
                                   {"faceup": True, "gear": ["arasaka-emergency-radioport"]}),
                                  ("v-corporate-exile", {"spent": True})],
                         field=["psycho-squad"], hand=[VANILLA_GEAR], eddies=0,
                         deck=["floor-it"]), Side())
    v = find(s, "v-corporate-exile")
    assert not knows_identity(s, 1, v)                    # face-down: the Rival cannot read it
    do(s, Play(find(s, VANILLA_GEAR, Zone.HAND), find(s, "psycho-squad")))
    _resolve(s, limit=4)                                  # look at it, then Call it for free
    assert s.i_faceup[v] and s.i_zone[v] == Zone.LEGENDS
    assert knows_identity(s, 1, v)                        # Called: now public


def test_radioport_only_looks_when_the_legend_is_neither_arasaka_nor_go_solo(pool):
    """The other side of the printed conditional: Judy Alvarez *Braindance Maestro* is a Blue
    Legend with no ARASAKA tag and no GO SOLO, so the look happens — the controller learns it —
    and no Call is offered."""
    s = board(pool, Side(legends=[("hanako-arasaka-daughter-of-the-emperor",
                                   {"faceup": True, "gear": ["arasaka-emergency-radioport"]}),
                                  ("judy-alvarez-braindance-maestro", {"spent": True})],
                         field=["psycho-squad"], hand=[VANILLA_GEAR], eddies=0,
                         deck=["floor-it"]), Side())
    judy = find(s, "judy-alvarez-braindance-maestro")
    do(s, Play(find(s, VANILLA_GEAR, Zone.HAND), find(s, "psycho-squad")))
    _resolve(s, limit=4)
    assert not s.i_faceup[judy]                           # not Called
    assert knows_identity(s, 0, judy)                     # but its controller looked at it
    assert not knows_identity(s, 1, judy)


# ----------------------------------------------------------------- delamain-cab
def test_delamain_cab_readies_an_eddie_only_after_it_stole(pool):
    """'At the end of your turn, if this Unit stole a Gig this turn, ready 1 Eddie.'

    The marker is ``("stole", inst)``, recorded by ``steps.do_steal`` for the thief, and
    ``s.used`` is cleared in EndTurnCleanupStep which sits *below* the ``end_turn`` dispatch — so
    it is still there when the hook runs.
    """
    s = board(pool, Side(field=["delamain-cab"], eddies=4, spent_eddies=4), Side(gig=[(6, 2)]))
    do(s, Attack(find(s, "delamain-cab")))
    do(s, Target(TARGET_GIG, 0))
    assert s.gig[0] == [(6, 2)] and available(s, 0) == 0
    do(s, EndTurn())
    assert available(s, 0) == 1

    idle = board(pool, Side(field=["delamain-cab"], eddies=4, spent_eddies=4), Side(gig=[(6, 2)]))
    do(idle, EndTurn())
    assert available(idle, 0) == 0


# ------------------------------------------------------ panam-palmer-nomad-cavalry
def test_panam_readies_five_equipped_units_and_legends(pool):
    """'At the end of your turn, if 5 or more friendly Units and/or Legends are equipped, ready
    them.' Four equipped Units plus the equipped Panam herself is five; ``s.units()`` excludes
    attached Gear and a solo'd Legend is in ``units()`` and not in ``legends()``, so the count
    cannot double."""
    units = [(u, {"spent": True, "gear": [VANILLA_GEAR]}) for u in
             ("psycho-squad", "emergency-atlus", "psycho-squad", "emergency-atlus")]
    s = board(pool, Side(field=units,
                         legends=[("panam-palmer-nomad-cavalry",
                                   {"faceup": True, "spent": True, "gear": [VANILLA_GEAR]})],
                         eddies=E), Side())
    panam = find(s, "panam-palmer-nomad-cavalry")
    assert all(s.i_spent[u] for u in s.units(0)) and s.i_spent[panam]
    do(s, EndTurn())
    assert not any(s.i_spent[u] for u in s.units(0))
    assert not s.i_spent[panam]


def test_panam_does_nothing_with_only_four_equipped(pool):
    """One short of five: the printed threshold is 5 or more."""
    units = [(u, {"spent": True, "gear": [VANILLA_GEAR]}) for u in
             ("psycho-squad", "emergency-atlus", "psycho-squad")]
    s = board(pool, Side(field=units,
                         legends=[("panam-palmer-nomad-cavalry",
                                   {"faceup": True, "spent": True, "gear": [VANILLA_GEAR]})],
                         eddies=E), Side())
    do(s, EndTurn())
    assert all(s.i_spent[u] for u in s.units(0))


# ----------------------------------- hanako-arasaka-daughter-of-the-emperor
def test_hanako_draws_one_per_friendly_value_pair_at_the_start_of_the_turn(pool):
    """'At the start of your turn, draw 1 for each friendly value-pair of Gigs.'

    Four dice showing 3, 3, 5, 5 are two value-pairs, so the turn's own draw is joined by two
    more; four distinct values are no pairs at all and only the turn draw happens.
    """
    pairs = board(pool, Side(legends=[("hanako-arasaka-daughter-of-the-emperor", {"faceup": True})],
                             gig=[(6, 3), (8, 3), (10, 5), (12, 5)], eddies=E,
                             deck=["floor-it"] * 10), Side(eddies=E), active=1)
    do(pairs, EndTurn())
    none = board(pool, Side(legends=[("hanako-arasaka-daughter-of-the-emperor", {"faceup": True})],
                            gig=[(6, 3), (8, 4), (10, 5), (12, 6)], eddies=E,
                            deck=["floor-it"] * 10), Side(eddies=E), active=1)
    do(none, EndTurn())
    assert len(none.zone(0, Zone.HAND)) == 1
    assert len(pairs.zone(0, Zone.HAND)) == 3
