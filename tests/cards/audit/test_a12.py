"""Batch A12 — Gear: host-spent triggers and statics (wnc.py lines 1024-1114).

Two findings, each an ``xfail(strict=True)`` naming its id, per the convention in
``tests/cards/test_audit_shape.py``. The controls that isolate them — a two-Gig attack with no Gear,
and Overwatch reading "rival Unit" the other way — pass, so under that same convention they do not
belong in this directory; they are written out with their results in ``out/audit/a12/findings.md``
and are one file away (``test_confirmed_a12.py``) if this batch is allowed a third path.

The batch's third finding, zetatech-faceplate's tail clause, was already open when the batch started
and its id is already claimed by
``tests/cards/audit/test_lint.py::test_zetatech_faceplate_draws_when_the_adjust_is_declined``.
That test fails one assertion too early to actually reach the draw; findings.md carries the scenario
that does, which cannot be committed here without two tests claiming one finding id.
"""
import pytest
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, Pick
from cptcg.core.enums import F_GO_SOLO, Zone
from cptcg.core.ops import power


# ------------------------------------------------------------------ gorilla-arms
def test_gorilla_arms_steal_is_extra_not_a_replacement(pool):
    """'The first time this Unit steals 1 or more Gigs each turn, steal a rival Gig with a value
    not shared by a friendly Gig.'

    Animals Wrecker is 10 power, 13 with Gorilla Arms equipped; either way the attack steals 2 Gigs
    (``steal_count``: one, plus one per full 10 power), and it is aimed at a Gig area holding three
    dice of distinct value. Gorilla Arms triggers on the first of those two steals and adds a third
    die. Nothing in the text lets it cancel one of the attack's own steals, so all three dice change
    hands. The same board with no Gear at all keeps both of the attack's steals — see findings.md.

    Fixed: AUD-gorilla-arms-1.
    """
    s = board(pool, Side(field=[("animals-wrecker", {"gear": ["gorilla-arms"]})], gig=[]),
              Side(gig=[(4, 1), (6, 2), (8, 3)]))
    assert power(s, find(s, "animals-wrecker"), 1) == 13
    do(s, Attack(find(s, "animals-wrecker")))               # only target: the Gig area (auto)
    do(s, Pick((1, 2)))                                     # the attack takes the d6=2 and the d8=3
    do(s, Pick((0,)))                                       # Gorilla Arms takes the d4=1 (unshared)
    assert len(s.gig[0]) == 3 and s.gig[1] == []


# --------------------------------------------------------- satori-sword-of-saburo
@pytest.mark.xfail(strict=True, reason="AUD-satori-sword-of-saburo-1: the loser is tested with CardDef.type is UNIT, so a GO SOLO Legend on the field — a Unit per the GO SOLO reminder and ruling 015 — never triggers the draw")
def test_satori_draws_when_its_host_beats_a_go_solo_legend(pool):
    """'When this Unit wins a fight against a rival Unit, draw 1.'

    The rival's card is a Legend played to the field with GO SOLO — "play it as a ready Unit"
    (rules.md, Keywords; ruling 015: "it is a Unit now"). It is spent because only spent Units are
    legal attack targets, and V Corporate Exile's printed text is the GO SOLO reminder alone, so
    nothing else moves here. Animals Wrecker (10) beats its 8 power and it is removed from the game
    (ruling 034), which is what makes it a rival Unit defeated in a fight.
    """
    s = board(pool, Side(field=[("animals-wrecker", {"gear": ["satori-sword-of-saburo"]})],
                         deck=["floor-it"]),
              Side(field=[("v-corporate-exile", {"spent": True, "faceup": True,
                                                 "flags": F_GO_SOLO})]))
    do(s, Attack(find(s, "animals-wrecker")))               # only target: the spent Legend (auto)
    assert s.i_zone[find(s, "v-corporate-exile")] == Zone.REMOVED    # 10 beats 8: the fight is won
    assert len(s.zone(0, Zone.HAND)) == 1
