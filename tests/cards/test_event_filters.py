"""CardScript.events, the per-hook event-kind filter.

dispatch skips an on_event hook for every kind outside its declared set, so a declaration that
misses a kind the hook reacts to would silently change the game. Two checks: the declared set is
exactly the set of kinds the hook's source tests ``e[0]`` against, and calling the hook with any
undeclared kind is a no-op on a board where the card is in play.
"""
import inspect
import re

import pytest

from conftest import Side, board, find
from cptcg.core.effects import EffectCtx
from cptcg.core.enums import CardType, Zone

# docs/effects-authoring.md, "Events"
DOCUMENTED = frozenset({"steal", "fight_won", "fight_lost", "blocked", "spent", "played", "attack",
                        "defeated", "called", "gig_rolled", "gig_changed", "start_turn", "end_turn"})

_KIND_TEST = re.compile(r'e\[0\]\s*(?:==|!=)\s*"(\w+)"')


def _event_cards(pool):
    return [d for d in pool.defs if d.script is not None and d.script.on_event is not None]


def test_every_pool_hook_declares_exactly_the_kinds_it_tests(pool):
    cards = _event_cards(pool)
    assert cards, "no on_event scripts in the pool?"
    for d in cards:
        sc = d.script
        src = inspect.getsource(sc.on_event)
        found = set(_KIND_TEST.findall(src))
        if "_host_spent" in src:
            found.add("spent")
        assert sc.events is not None, f"{d.id}: on_event hook without an events= declaration"
        assert set(sc.events) == found, f"{d.id}: events={set(sc.events)} but the hook tests {found}"
        assert set(sc.events) <= DOCUMENTED, f"{d.id}: undocumented event kind in {set(sc.events)}"


def _board_with(pool, d):
    """A board with card ``d`` in play for player 0 (Units on the field, Legends face-up, Gear on
    a Unit), at player 0's main menu."""
    if d.type is CardType.UNIT:
        p0 = Side(field=[d.id], eddies=3, gig=[(20, 6)])
    elif d.type is CardType.LEGEND:
        p0 = Side(legends=[(d.id, {"faceup": True})], eddies=3, gig=[(20, 6)])
    elif d.type is CardType.GEAR:
        p0 = Side(field=[("psycho-squad", {"gear": [d.id]})], eddies=3, gig=[(20, 6)])
    else:
        pytest.skip(f"{d.id}: {d.type.name} is never in play")
    s = board(pool, p0, Side(field=["psycho-squad"], eddies=2, gig=[(12, 4)]))
    return s, find(s, d.id)


def _snapshot(s):
    return (s.turn, s.active, list(s.i_zone), bytes(s.i_spent), bytes(s.i_lag), bytes(s.i_faceup),
            list(s.i_host), list(s.i_flags), [list(z) for z in s.z],
            [list(g) for g in s.gig], list(s.temp_power), list(s.mods), set(s.used),
            len(s.stack), s.pending, s.over)


def test_undeclared_kinds_are_no_ops(pool):
    """For every declared hook, each documented kind it does not declare leaves the state alone
    (the 1-tuple event also fails any hook that reads e[1] before testing e[0])."""
    for d in _event_cards(pool):
        sc = d.script
        s, inst = _board_with(pool, d)
        assert s.i_zone[inst] in (Zone.FIELD, Zone.LEGENDS)
        before = _snapshot(s)
        for kind in sorted(DOCUMENTED - set(sc.events)):
            assert sc.on_event(EffectCtx(s, inst), (kind,)) is None, (d.id, kind)
            assert _snapshot(s) == before, f"{d.id}: hook reacted to undeclared {kind!r}"
