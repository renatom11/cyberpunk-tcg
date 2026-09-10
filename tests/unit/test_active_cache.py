"""The active-card cache (GameState._active) must always equal a fresh rebuild.

ops.move() skips the invalidation for moves that touch neither FIELD nor LEGENDS (draws, discards,
sells, mulligans, bottom-decking). These tests check, after every action of many random games,
that a cache kept across an action is identical to a rebuild from scratch, and that the specific
operations that must (or must not) invalidate it do so.
"""
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from smoke_random import reg as test_reg  # noqa: E402  (also puts tests/ on sys.path)
from conftest import Side, blue_deck, board, red_deck  # noqa: E402

from cptcg.cards.registry import load_default  # noqa: E402
from cptcg.core import invariants  # noqa: E402
from cptcg.core.actions import ChoiceKind, EndTurn  # noqa: E402
from cptcg.core.engine import apply, go_solo, legal_actions, new_game, play_card  # noqa: E402
from cptcg.core.enums import NO_INST, NZONE, Zone  # noqa: E402
from cptcg.core.ops import (_active, _rebuild_active, bottom_deck, call_legend, defeat,  # noqa: E402
                            discard, draw, move, shuffle_deck)
from cptcg.core.rng import Pcg32  # noqa: E402
from cptcg.deck.decklist import Decklist  # noqa: E402


def _random_index(r, opts):
    if len(opts) > 1 and isinstance(opts[0], EndTurn) and r.below(10) < 9:
        return 1 + r.below(len(opts) - 1)
    return r.below(len(opts))


def _play_checking(reg, decks, seed):
    """Random game; the cache is warmed before every action, and whatever cache is present after
    it must equal a rebuild (done on a clone so the game's own cache object is untouched).
    Returns (actions that kept the pre-action cache object, actions)."""
    s = new_game(reg, decks, seed)
    r = Pcg32(seed ^ 0x5EED)
    kept = actions = 0
    while not s.over:
        opts = legal_actions(s)
        before = _active(s)
        apply(s, _random_index(r, opts))
        actions += 1
        invariants.check(s)
        if s._active is not None:
            assert _rebuild_active(s.clone()) == s._active
            kept += s._active is before
        assert actions < 5000, "runaway game"
    return kept, actions


@pytest.mark.parametrize("seed", range(20))
def test_cache_matches_rebuild_test_registry(seed):
    kept, actions = _play_checking(test_reg, (red_deck(), blue_deck()), seed)
    assert 0 < kept < actions          # some actions keep the cache, some invalidate it


_POOL_DECKS = sorted((ROOT / "data" / "decks").glob("*.json"))


@pytest.fixture(scope="module")
def pool():
    return load_default()


@pytest.mark.parametrize("k", range(4))
def test_cache_matches_rebuild_card_pool(pool, k):
    r = random.Random(1000 + k)
    a, b = r.sample(_POOL_DECKS, 2)
    seed = r.randrange(1 << 30)
    kept, actions = _play_checking(pool, (Decklist.load(a), Decklist.load(b)), seed)
    assert 0 < kept < actions


def _warm(s):
    cache = _active(s)
    assert s._active is cache
    return cache


def _dropped_and_consistent(s, cache):
    """The old cache object is gone; if a hook already rebuilt one it equals a rebuild."""
    return s._active is not cache and (s._active is None or _rebuild_active(s.clone()) == s._active)


def test_moves_outside_play_keep_the_cache(reg):
    s = board(reg, Side(hand=["T-U1", "T-G1", "T-P1", "T-U9"], eddies=2, deck=["T-U3", "T-U4", "T-U5"],
                        field=["T-U2"], legends=["T-L1"]),
              Side(field=["T-U6"]))
    hand, deck = s.z[Zone.HAND], s.z[Zone.DECK]
    u1, g1, prog, u9 = list(hand)
    top = deck[-1]
    cache = _warm(s)

    draw(s, 0)                                       # deck -> hand, top card (the pop() fast path)
    assert s._active is cache and hand[-1] == top and top not in deck
    discard(s, prog)                                 # hand -> trash, from the middle of the list
    assert s._active is cache and hand == [u1, g1, u9, top] and s.z[Zone.TRASH] == [prog]
    bottom_deck(s, top)                              # hand -> bottom of the deck
    assert s._active is cache and deck[0] == top
    move(s, u9, Zone.EDDIES)                         # a sell
    assert s._active is cache and s.z[Zone.EDDIES][-1] == u9
    for i in list(hand):                             # a mulligan: hand -> deck, shuffle, redraw
        move(s, i, Zone.DECK)
    shuffle_deck(s, 0)
    draw(s, 0, 2)
    assert s._active is cache
    assert _rebuild_active(s.clone()) == cache
    invariants.check(s)


def test_play_zone_changes_drop_the_cache(reg):
    s = board(reg, Side(hand=["T-U1", "T-G1"], eddies=2, field=["T-U2"],
                        legends=["T-L1", ("T-L3", {"faceup": True})]),
              Side(field=["T-U6"]))
    u1, g1 = list(s.z[Zone.HAND])
    u2, = s.z[Zone.FIELD]
    l1, l3 = s.z[Zone.LEGENDS]

    cache = _warm(s)
    play_card(s, 0, u1, cost=0)                      # a Unit enters the field
    assert _dropped_and_consistent(s, cache) and u1 in _active(s)[0]
    cache = _warm(s)
    play_card(s, 0, g1, host=u2, cost=0)             # Gear attaches to a Unit in play
    assert _dropped_and_consistent(s, cache) and _active(s)[5][u2] == (g1,)
    cache = _warm(s)
    assert defeat(s, u2)                             # host leaves play: its Gear travels with it
    assert _dropped_and_consistent(s, cache)
    assert s.i_zone[g1] == Zone.TRASH and s.i_host[g1] == NO_INST and u2 not in _active(s)[5]
    cache = _warm(s)
    call_legend(s, 0, l1)                            # face-down -> face-up: now active
    assert _dropped_and_consistent(s, cache) and l1 in _active(s)[0]
    cache = _warm(s)
    go_solo(s, 0, l3, 0)                             # Legends area -> field
    assert _dropped_and_consistent(s, cache) and s.i_zone[l3] == Zone.FIELD
    # raw moves into and out of play invalidate without anything rebuilding behind them
    _warm(s)
    move(s, u1, Zone.TRASH)
    assert s._active is None
    _warm(s)
    move(s, u1, Zone.FIELD)
    assert s._active is None
    assert _rebuild_active(s.clone()) == _active(s)
    invariants.check(s)


def test_pop_fast_path_keeps_order(reg):
    s = board(reg, Side(hand=["T-U1", "T-U2", "T-U3"]), Side())
    hand = s.z[Zone.HAND]
    a, b, c = list(hand)
    discard(s, c)                                    # top of the list
    assert hand == [a, b]
    discard(s, a)                                    # not the top: the general path
    assert hand == [b] and s.z[Zone.TRASH] == [c, a]


def test_real_mulligan_keeps_a_warm_cache(reg):
    s = new_game(reg, (red_deck(), blue_deck()), 3)
    while s.pending.kind is not ChoiceKind.MULLIGAN:
        apply(s, 0)
    p = s.pending.player
    hand_before = list(s.zone(p, Zone.HAND))
    cache = _warm(s)
    apply(s, 1)                                      # Mulligan(False): hand -> deck, shuffle, redraw
    assert s._active is cache and s.zone(p, Zone.HAND) != hand_before
    assert _rebuild_active(s.clone()) == cache
