"""probe scratch"""
import pytest
from conftest import Side, board, do, find, options

from cptcg.core.actions import Attack, Pick, Play, Target
from cptcg.core.enums import TARGET_GIG, TARGET_UNIT, Zone
from cptcg.core.legal import attack_permission, attack_targets
from cptcg.core.ops import play_cost, has_keyword
from cptcg.core.enums import Keyword

E = 12


def play(s, cid):
    do(s, Play(find(s, cid, Zone.HAND)))
    return s


def test_probe_sandayu_and_nadia(pool):
    # Sandayu: "can attack rival Units the turn it's played"
    s = board(pool, Side(hand=["sandayu-oda-hanakos-guardian"], eddies=E, gig=[(4, 2), (6, 2)]),
              Side(field=[("corpo-security", {"spent": True})], gig=[(6, 3), (8, 4), (10, 5)]))
    play(s, "sandayu-oda-hanakos-guardian")
    # resolve the PLAY spend choice if any
    while s.pending is not None and s.pending.kind.name == "PICK":
        do(s, s.pending.options[0])
    i = find(s, "sandayu-oda-hanakos-guardian", Zone.FIELD)
    print("SANDAYU perm", attack_permission(s, i), "targets", attack_targets(s, i))

    s2 = board(pool, Side(hand=["nadia-fighting-through-grief"], eddies=E, gig=[(4, 2)]),
               Side(field=[("corpo-security", {"spent": True})], gig=[(6, 3), (8, 4), (10, 5)]))
    play(s2, "nadia-fighting-through-grief")
    j = find(s2, "nadia-fighting-through-grief", Zone.FIELD)
    print("NADIA perm", attack_permission(s2, j), "targets", attack_targets(s2, j))


def test_probe_costs(pool):
    s = board(pool, Side(hand=["maxtac-heavy", "octant"], eddies=E, gig=[(10, 9), (8, 8)]),
              Side(field=["psycho-squad", "corpo-security"]))
    print("maxtac-heavy cost", play_cost(s, 0, find(s, "maxtac-heavy", Zone.HAND)))
    print("octant cost", play_cost(s, 0, find(s, "octant", Zone.HAND)))


def test_probe_adrenaline_converter(pool):
    s = board(pool, Side(hand=["adrenaline-converter"], eddies=E, field=["psycho-squad"], gig=[(4, 1)]),
              Side(gig=[(6, 3), (8, 4), (10, 5)], field=[("corpo-security", {"spent": True})]))
    u = find(s, "psycho-squad", Zone.FIELD)
    s.i_lag[u] = 1
    s.invalidate()
    play(s, "adrenaline-converter")
    while s.pending is not None and s.pending.kind.name == "PICK":
        do(s, s.pending.options[0])
    print("host has ADR", has_keyword(s, u, Keyword.ADRENALINE), "perm", attack_permission(s, u))


def test_probe_flathead(pool):
    print("cards ok")
