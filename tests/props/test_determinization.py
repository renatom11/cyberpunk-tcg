"""Hidden information is honest: sampled worlds match what a seat knows, and nothing more.

Property-style over whole games. ``core/view.py`` claims four things and each gets a test here:
a determinized world is indistinguishable from the real one *to the seat it was sampled for*
(``info_key`` is unchanged), it is a permutation of that seat's unknowns and never an invention,
it disturbs nothing public (including the ``_active`` cache), and it is a legal state that plays
to the end of a game.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import pytest
from smoke_random import reg  # noqa: F401

from cptcg.core import invariants, ops
from cptcg.core.actions import CallLegend, ChoiceKind, EndTurn, Play
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.enums import NZONE, Zone
from cptcg.core.rng import Pcg32
from cptcg.core.view import (HIDDEN_CARD, determinize, info_key, knows_identity, redact,
                             unknown_to)
from conftest import Side, blue_deck, board, do, find, red_deck

ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------- helpers
def _snapshot(s):
    """The clone-equivalence snapshot from tests/unit/test_preview_costs.py, which covers every
    mutable array. It deliberately excludes ``i_card``: that is the one list determinize may touch."""
    return (s.turn, s.active, list(s.i_zone), bytes(s.i_spent), bytes(s.i_lag), bytes(s.i_faceup),
            list(s.i_host), list(s.i_flags), list(s.i_known), [list(z) for z in s.z],
            [list(f) for f in s.fixer], [list(g) for g in s.gig], list(s.temp_power), list(s.mods),
            set(s.used), list(s.played), list(s.drawn), list(s.once), list(s.turns_taken),
            s.over, s.winner, s.rng.state, s.rng.inc)


def _random_index(r, opts):
    if len(opts) > 1 and isinstance(opts[0], EndTurn) and r.below(10) < 9:
        return 1 + r.below(len(opts) - 1)
    return r.below(len(opts))


def _decisions(seed, decks=None, registry=None, stride=1):
    """Walk a random game, yielding the state at every ``stride``-th decision."""
    registry = registry or reg
    s = new_game(registry, decks or (red_deck(), blue_deck()), seed)
    r = Pcg32(seed)
    k = 0
    while not s.over:
        legal_actions(s)
        if k % stride == 0:
            yield k, s
        apply(s, _random_index(r, legal_actions(s)))
        k += 1


def _real_pool_decisions(pool, seed, stride):
    """The same walk over the real 151-card pool, so scripts the test fixtures never hold — deck
    peeks, private Legend looks — are exercised too."""
    from cptcg.deck.decklist import Decklist
    decks = (Decklist.load(ROOT / "data" / "decks" / "the_heist.json"),
             Decklist.load(ROOT / "data" / "decks" / "embracing_power.json"))
    yield from _decisions(seed, decks=decks, registry=pool, stride=stride)


def _counts(s, insts):
    out = {}
    for i in insts:
        out[s.i_card[i]] = out.get(s.i_card[i], 0) + 1
    return out


# ------------------------------------------------------- the defining property
@pytest.mark.parametrize("seed", range(6))
def test_info_key_is_identical_in_every_sampled_world(seed):
    """The whole point: a determinized world is indistinguishable from the real one to the seat it
    was sampled for, at every decision of a game, for both seats."""
    for k, s in _decisions(seed):
        for me in (0, 1):
            d = determinize(s, me, Pcg32(seed * 977 + k))
            assert info_key(d, me) == info_key(s, me)


@pytest.mark.parametrize("seed", range(4))
def test_info_key_identical_over_the_real_card_pool(pool, seed):
    for k, s in _real_pool_decisions(pool, seed, stride=2):
        for me in (0, 1):
            d = determinize(s, me, Pcg32(seed * 31 + k))
            assert info_key(d, me) == info_key(s, me)
            assert info_key(d, me, known_opponent_deck=False) == \
                info_key(s, me, known_opponent_deck=False)


# ------------------------------------------------------- permutation, not invention
@pytest.mark.parametrize("seed", range(6))
def test_every_unknown_multiset_is_preserved(seed):
    for k, s in _decisions(seed, stride=2):
        for me in (0, 1):
            d = determinize(s, me, Pcg32(seed * 13 + k))
            rival = 1 - me
            unk = set(unknown_to(s, me))
            # per-group multisets: my deck, the rival's hand+deck pool, each side's Legend slots
            groups = [[i for i in s.z[me * NZONE + Zone.DECK] if i in unk],
                      [i for i in s.z[rival * NZONE + Zone.HAND] + s.z[rival * NZONE + Zone.DECK]
                       if i in unk],
                      [i for i in s.legends(0) if i in unk],
                      [i for i in s.legends(1) if i in unk]]
            for g in groups:
                assert _counts(s, g) == _counts(d, g)
            # ... and the whole game is still the same bag of cards
            assert sorted(s.i_card) == sorted(d.i_card)
            assert len(d.i_card) == len(s.i_card)


@pytest.mark.parametrize("seed", range(6))
def test_only_hidden_identities_move_and_public_state_is_byte_identical(seed):
    for k, s in _decisions(seed, stride=2):
        for me in (0, 1):
            unk = set(unknown_to(s, me))
            d = determinize(s, me, Pcg32(seed * 7 + k))
            # every mutable array except i_card is untouched
            assert _snapshot(d) == _snapshot(s)
            # i_card is a fresh list (clone() shares the original) that differs only inside `unk`
            assert d.i_card is not s.i_card
            differ = {i for i in range(len(s.i_card)) if d.i_card[i] != s.i_card[i]}
            assert differ <= unk
            # the active-card cache is not just valid, it is literally the same object
            assert d._active is s._active


@pytest.mark.parametrize("seed", range(4))
def test_unknown_to_never_includes_a_public_instance(seed):
    for _k, s in _decisions(seed, stride=3):
        for me in (0, 1):
            for i in unknown_to(s, me):
                zone = s.i_zone[i]
                assert zone in (Zone.DECK, Zone.HAND, Zone.LEGENDS)
                assert not (zone == Zone.HAND and s.i_owner[i] == me), "own hand is known"
                assert not (zone == Zone.LEGENDS and s.i_faceup[i]), "face-up Legends are public"
                assert not knows_identity(s, me, i)
            assert unknown_to(s, me) == sorted(set(unknown_to(s, me)))


# --------------------------------------------------------------------- playable
@pytest.mark.parametrize("seed", range(4))
def test_a_determinized_world_plays_to_the_end_of_a_game(seed):
    played = 0
    for k, s in _decisions(seed, stride=45):
        d = determinize(s, s.pending.player, Pcg32(seed * 101 + k))
        invariants.check(d)
        r = Pcg32(seed + 5)
        steps = 0
        while not d.over:
            apply(d, _random_index(r, legal_actions(d)))
            invariants.check(d)
            steps += 1
            assert steps < 5000, "runaway game"
        assert d.winner in (0, 1)
        played += 1
    assert played >= 2


@pytest.mark.parametrize("seed", range(3))
def test_a_determinized_world_plays_out_over_the_real_pool(pool, seed):
    for k, s in _real_pool_decisions(pool, seed, stride=50):
        d = determinize(s, s.pending.player, Pcg32(seed * 3 + k))
        r = Pcg32(seed + 17)
        steps = 0
        while not d.over:
            apply(d, _random_index(r, legal_actions(d)))
            invariants.check(d)
            steps += 1
            assert steps < 5000, "runaway game"


# ----------------------------------------------------------------- rng contract
def test_same_seed_same_world_different_seeds_different_worlds():
    states = [s for _k, s in _decisions(1, stride=20)]
    s = states[len(states) // 2]
    a = determinize(s, 0, Pcg32(42))
    b = determinize(s, 0, Pcg32(42))
    assert a.i_card == b.i_card
    worlds = {tuple(determinize(s, 0, Pcg32(n)).i_card) for n in range(12)}
    assert len(worlds) > 1, "the sampler ignores its rng"
    assert any(w != tuple(s.i_card) for w in worlds), "the sampler never leaves the true world"


def test_the_sampler_does_not_consume_the_states_own_rng():
    """Determinization must not disturb the game's future dice: it draws from the caller's rng."""
    _k, s = next(_decisions(3, stride=30))
    before = (s.rng.state, s.rng.inc)
    d = determinize(s, 0, Pcg32(9))
    assert (s.rng.state, s.rng.inc) == before
    assert (d.rng.state, d.rng.inc) == before


# ------------------------------------------------------------- info_key hides
@pytest.mark.parametrize("seed", range(4))
def test_two_worlds_that_differ_only_in_hidden_identities_share_a_key(seed):
    """The complement of the first property: the key must be blind to the swap, and the test must
    not be vacuous — at least one decision has to produce a genuinely different world."""
    differed = 0
    for k, s in _decisions(seed, stride=2):
        for me in (0, 1):
            d = determinize(s, me, Pcg32(seed * 65537 + k))
            assert info_key(d, me) == info_key(s, me)
            if d.i_card != s.i_card:
                differed += 1
    assert differed > 20


def test_info_key_changes_when_a_card_is_drawn(reg):  # noqa: F811
    _k, s = next(_decisions(2, stride=25))
    for me in (0, 1):
        before = (info_key(s, 0), info_key(s, 1))
        c = s.clone()
        ops.draw(c, me, 1)
        after = (info_key(c, 0), info_key(c, 1))
        assert after[me] != before[me], "the drawer learns a card"
        assert after[1 - me] != before[1 - me], "the rival sees the hand and deck counts move"


def test_info_key_changes_when_a_legend_is_called(pool):
    s = _legend_board(pool)
    leg = s.legends(0)[0]
    assert not s.i_faceup[leg]
    before = (info_key(s, 0), info_key(s, 1))
    assert leg in unknown_to(s, 0) and leg in unknown_to(s, 1)
    do(s, CallLegend(leg))
    assert s.i_faceup[leg] and s.i_known[leg] == 0b11
    assert leg not in unknown_to(s, 0) and leg not in unknown_to(s, 1)
    assert info_key(s, 0) != before[0] and info_key(s, 1) != before[1]


def test_a_private_look_reveals_the_slot_to_one_seat_only(pool):
    s = _legend_board(pool)
    leg = s.legends(0)[1]
    before = (info_key(s, 0), info_key(s, 1))
    s.i_known[leg] |= 1                       # what effects.look_at writes for player 0
    assert leg not in unknown_to(s, 0) and leg in unknown_to(s, 1)
    assert info_key(s, 0) != before[0]
    assert info_key(s, 1) == before[1], "the rival learns nothing from my private peek"
    # and the sampler stops moving that slot for player 0 while still moving it for player 1
    for n in range(8):
        assert determinize(s, 0, Pcg32(n)).i_card[leg] == s.i_card[leg]
    assert any(determinize(s, 1, Pcg32(n)).i_card[leg] != s.i_card[leg] for n in range(20))


def _legend_board(pool):
    legs0 = ["johnny-silverhand-rocking-renegade", "alt-cunningham-soulkiller-architect",
             "jackie-welles-mamas-favorite"]
    legs1 = ["adam-smasher-ender-of-legends", "goro-takemura-hands-unclean",
             "dexter-deshawn-off-the-grid"]
    deck = ["corpo-security"] * 8
    return board(pool, Side(eddies=4, deck=deck, legends=legs0),
                 Side(eddies=4, deck=deck, legends=legs1))


# ------------------------------------------------- open peeks and blind choices
def test_an_open_deck_search_pins_the_cards_it_showed(pool):
    """effects.search_top looks at the top N and then asks, so those cards are known while the
    choice is open and must survive determinization untouched."""
    deck = ["corpo-security"] * 4 + ["chrome-fang"] * 4
    s = board(pool, Side(hand=["three-mouths-one-desire"], eddies=6, deck=deck,
                         legends=["johnny-silverhand-rocking-renegade"]),
              Side(eddies=2, deck=deck, legends=["adam-smasher-ender-of-legends"]))
    do(s, Play(find(s, "three-mouths-one-desire", zone=Zone.HAND, player=0)))
    assert s.pending.kind is ChoiceKind.PICK and s.pending.player == 0
    top = s.z[0 * NZONE + Zone.DECK][-3:]
    assert all(i not in unknown_to(s, 0) for i in top), "the searcher has seen these"
    assert all(i in unknown_to(s, 1) for i in top), "the rival has not"
    for n in range(10):
        d = determinize(s, 0, Pcg32(n))
        assert [d.i_card[i] for i in top] == [s.i_card[i] for i in top]
        assert info_key(d, 0) == info_key(s, 0)


def test_a_blind_legend_choice_pins_nothing(pool):
    """'Look at a face-down Legend' asks you to pick a slot *without* knowing what is under it, so
    an open choice over Legend slots must not be mistaken for a reveal."""
    s = _legend_board(pool)
    legs = s.legends(0)
    from cptcg.core.actions import Choice, Pick
    s.pending = Choice(ChoiceKind.PICK, 0, tuple(Pick((i,)) for i in range(len(legs))),
                       _fake_cont(legs), prompt="Look at a face-down Legend")
    assert all(i in unknown_to(s, 0) for i in legs)
    assert any(determinize(s, 0, Pcg32(n)).i_card[legs[0]] != s.i_card[legs[0]] for n in range(20))


def _fake_cont(vals):
    """A continuation shaped exactly like effects.choose's, closing over ``vals``."""
    def _cont(_st, act):                      # pragma: no cover - never resolved
        return vals[act.picks[0]]
    return _cont


# --------------------------------------------------------------------- redact
@pytest.mark.parametrize("seed", range(3))
def test_redact_blanks_exactly_the_unknowns_and_makes_reading_them_an_error(seed):
    for _k, s in _decisions(seed, stride=30):
        for me in (0, 1):
            unk = set(unknown_to(s, me))
            r = redact(s, me)
            assert _snapshot(r) == _snapshot(s) and r.i_card is not s.i_card
            assert {i for i in range(len(s.i_card)) if r.i_card[i] != s.i_card[i]} == unk
            assert all(r.i_card[i] == HIDDEN_CARD for i in unk)
            for i in unk:
                with pytest.raises(IndexError):
                    r.card(i)
            for i in range(len(s.i_card)):     # everything else still reads normally
                if i not in unk:
                    assert r.card(i) is s.card(i)
