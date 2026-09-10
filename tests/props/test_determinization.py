"""Hidden information is honest: sampled worlds match what a seat knows, and nothing more.

Property-style over whole games. ``core/view.py`` claims four things and each gets a test here:
a determinized world is indistinguishable from the real one *to the seat it was sampled for*
(``info_key`` is unchanged), it is a permutation of that seat's unknowns and never an invention,
it disturbs nothing public (including the ``_active`` cache), and it is a legal state that plays
to the end of a game.

Those four are not enough on their own, and the second half of this file exists because of it.
``info_key(d, me) == info_key(s, me)`` can only catch a *disagreement* between the key and the
sampler; where both preserve the same hidden thing — a menu built from the rival's hand, a prompt
naming a card, the rival's Legend triple — it passes by construction. So the tests below never
mention ``info_key``: they sample for the seat whose decision it is **not** and re-derive the menu
from the world that came back, they count how often a hidden thing actually varies across
resamples, and they read the key as text and look for card names that should not be in it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import pytest
from smoke_random import reg  # noqa: F401

from cptcg.core import invariants, ops
from cptcg.core.actions import (Attack, CallLegend, ChoiceKind, EndTurn, Pass, Pick, Play, Target)
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.enums import NZONE, TARGET_GIG, CardType, Zone
from cptcg.core.legal import attack_targets, main_menu, reaction_menu
from cptcg.core.rng import Pcg32
from cptcg.core.steps import HookStep, StealOneStep
from cptcg.core.view import (HIDDEN_CARD, _pinned, determinize, info_key, knows_identity, redact,
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
            # Per-group multisets: my deck, the rival's hand+deck pool, each side's Legend slots.
            # The rival's Legend multiset belongs here only because ``known_opponent_deck`` (on by
            # default) says I have seen their list, Legends included — and because ``info_key``
            # records that same multiset, so key and sampler agree. See the dedicated test below.
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


# =====================================================================================
# Leaks info_key cannot see
# =====================================================================================
# Everything above compares a sampled world to the real one *through* info_key. That check is
# blind to anything both sides preserve, which is exactly the shape every leak found in this
# module has had. Nothing below uses info_key as its detector.

def _other_card(pool, idx, card_type):
    """Some card index of ``card_type`` that is not ``idx`` — a genuinely different card."""
    return next(d.idx for d in pool.defs if d.type is card_type and d.idx != idx)


# ------------------------------------------- the sampled world agrees with its own menu
@pytest.mark.parametrize("seed", range(4))
def test_a_rival_menu_is_re_derived_from_the_sampled_world(pool, seed):
    """Sample for the seat whose decision it is NOT, and ask the world for its own menu.

    ``legal.reaction_menu`` offers ``Play`` for each quick Program the defender actually holds and
    ``main_menu`` reads the active player's hand, so a menu copied out of the real state both
    states how many hidden cards match and offers actions that are illegal where those cards moved.
    The measured symptom was the engine putting a Blocker onto the field from a hand that, in that
    world, held no such card.
    """
    seen = {ChoiceKind.REACTION: 0, ChoiceKind.MAIN: 0}
    for k, s in _real_pool_decisions(pool, seed, stride=1):
        ch = s.pending
        me = 1 - ch.player
        d = determinize(s, me, Pcg32(seed * 977 + k))
        if ch.kind is ChoiceKind.REACTION:
            seen[ChoiceKind.REACTION] += 1
            assert tuple(d.pending.options) == tuple(reaction_menu(d))
        elif ch.kind is ChoiceKind.MAIN:
            seen[ChoiceKind.MAIN] += 1
            assert tuple(legal_actions(d)) == tuple(main_menu(d))
        elif ch.kind is ChoiceKind.TARGET:
            fresh = tuple(attack_targets(d, d.atk.attacker))
            # empty means the attack fizzles in this world, which is not this decision at all
            assert not fresh or tuple(d.pending.options) == fresh
        elif ch.kind is ChoiceKind.PICK:
            # A PICK's list is built by a card script and cannot be re-derived from outside
            # ``effects``. What must hold is that its options are indices into that script's own
            # list — never instance ids — so every one of them applies in every sampled world.
            assert all(isinstance(o, Pick) for o in d.pending.options)
    assert seen[ChoiceKind.MAIN] > 20 and seen[ChoiceKind.REACTION] > 0, seen


def test_the_defenders_reaction_menu_is_that_worlds_menu(pool):
    """The concrete case: the defender holds three quick Programs and a deck of Corpo Security.

    The attacker's sampled world must not be told there are three, and must not be handed the
    three ``Play`` actions — in a world where those hand slots hold Units, playing one puts a
    Blocker on the field during the attacker's own reaction window.
    """
    s = board(pool,
              Side(field=["animals-wrecker"], eddies=4, deck=["corpo-security"] * 6,
                   legends=["johnny-silverhand-rocking-renegade"], gig=[(6, 3)]),
              Side(hand=["detonate", "floor-it", "synapse-burnout"], eddies=6,
                   deck=["corpo-security"] * 9, legends=["adam-smasher-ender-of-legends"],
                   gig=[(8, 4)]),
              active=0)
    do(s, Attack(find(s, "animals-wrecker", zone=Zone.FIELD, player=0)))
    do(s, Target(TARGET_GIG))
    assert s.pending.kind is ChoiceKind.REACTION and s.pending.player == 1
    quick = [o for o in s.pending.options if isinstance(o, Play)]
    assert len(quick) == 3, "the real menu offers one Play per quick Program held"

    sizes = set()
    for n in range(12):
        d = determinize(s, 0, Pcg32(n))                    # sampled by the ATTACKER
        assert tuple(d.pending.options) == tuple(reaction_menu(d))
        for o in d.pending.options:                        # nothing offered that is not playable
            if isinstance(o, Play):
                c = d.card(o.inst)
                assert c.type is CardType.PROGRAM and "QUICK" in {k.name for k in c.keywords}
        sizes.add(len(d.pending.options))
    assert len(sizes) > 1, "every sampled world still shows the real menu's size"


@pytest.mark.parametrize("seed", range(3))
def test_a_world_sampled_by_the_other_seat_plays_to_the_end(pool, seed):
    """The playability test that matters: ``determinize(s, 1 - s.pending.player)`` is the only one
    that permutes the cards the pending menu was built from."""
    played = 0
    for k, s in _real_pool_decisions(pool, seed, stride=40):
        d = determinize(s, 1 - s.pending.player, Pcg32(seed * 101 + k))
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


# ----------------------------------------------------- what the key must never contain
@pytest.mark.parametrize("seed", range(2))
def test_no_hidden_card_name_ever_reaches_the_key(pool, seed):
    """Read the key as text and look for names of cards the seat may not see.

    Five shipped scripts build a prompt by formatting a card name — ``f"Trash {name}?"`` for the
    top card of a deck, ``f"Call {name} for free?"`` for a Legend just looked at — and the key used
    to carry the prompt for every seat. This is the one-line check that catches that, and equally
    catches a pinned instance whose identity leaked into a zone key.
    """
    named_a_hidden_card = 0
    for _k, s in _real_pool_decisions(pool, seed, stride=1):
        prompt = s.pending.prompt if s.pending is not None else ""
        for me in (0, 1):
            key = str(info_key(s, me))
            for i in unknown_to(s, me):
                name = s.card(i).name
                if len(name) < 4:
                    continue
                assert name not in key, f"{name!r} (inst {i}) is in player {me}'s key"
                if name in prompt:
                    named_a_hidden_card += 1
    assert named_a_hidden_card, "no decision in this walk named a hidden card: test is vacuous"


def test_the_key_does_not_depend_on_whether_the_menu_was_materialised(reg):  # noqa: F811
    """``engine.legal_actions`` mutates the state to materialise the lazy main menu. That is not an
    observation, so the key must not move — otherwise one position occupies two search nodes."""
    s = new_game(reg, (red_deck(), blue_deck()), 11)
    r = Pcg32(4)
    while s.pending is None or s.pending.kind is not ChoiceKind.MAIN:
        apply(s, _random_index(r, legal_actions(s)))       # never asks the main menu for its options
    assert s.pending.lazy, "the main menu is supposed to be computed on first request"
    before = (info_key(s, 0), info_key(s, 1))
    legal_actions(s)
    assert not s.pending.lazy
    assert (info_key(s, 0), info_key(s, 1)) == before


def test_two_queued_steps_that_do_different_things_do_not_share_a_key(pool):
    """The stack used to enter the key as class names, so a position about to steal one die and a
    position about to steal another were the same position."""
    s = _legend_board(pool)
    a, b = s.clone(), s.clone()
    a.stack.append(StealOneStep(s.legends(0)[0], 0, 0))
    b.stack.append(StealOneStep(s.legends(0)[0], 0, 1))
    assert info_key(a, 0) != info_key(b, 0), "two different dice, one key"
    c, d = s.clone(), s.clone()
    c.stack.append(HookStep(lambda ctx: None, s.legends(0)[0]))
    d.stack.append(HookStep(lambda ctx: None, s.legends(0)[1]))
    assert info_key(c, 0) != info_key(d, 0), "two different cards' triggers, one key"


# --------------------------------------------------- the rival's face-down Legends
def test_the_rivals_face_down_legends_are_resampled_and_the_key_agrees(pool):
    """``known_opponent_deck`` covers the Legend triple, and the sampler and the key say so together.

    A ``Decklist`` is a main deck *and* three Legends, so "I have seen their list" means I know
    which three are face down — a multiset, never a slot. With the flag set that multiset is in the
    key and the sampler preserves it; with the flag clear the key is blind to it. What must never
    happen is the sampler preserving something the key refuses to record: every sampled world would
    then hand the search the rival's true Legends, and the moment one is Called the search knew it
    in advance.
    """
    s = _legend_board(pool)
    for me in (0, 1):
        rival = 1 - me
        fd = [i for i in s.legends(rival) if not s.i_faceup[i]]
        assert len(fd) == 3 and len({s.i_card[i] for i in fd}) == 3
        worlds = {tuple(determinize(s, me, Pcg32(n)).i_card[i] for i in fd) for n in range(30)}
        assert len(worlds) > 1, "the rival's face-down Legend slots never move"
        assert all(sorted(w) == sorted(s.i_card[i] for i in fd) for w in worlds), \
            "the sampler invented a Legend that is not on their list"
        swapped = s.clone()
        swapped.i_card = s.i_card[:]
        swapped.i_card[fd[0]] = _other_card(pool, s.i_card[fd[0]], CardType.LEGEND)
        assert info_key(swapped, me) != info_key(s, me), \
            "the key forgets a Legend list I have seen, while the sampler assumes it"
        assert info_key(swapped, me, known_opponent_deck=False) == \
            info_key(s, me, known_opponent_deck=False), \
            "the game-one key knows which Legends they brought"
        mine = [i for i in s.legends(me) if not s.i_faceup[i]]
        swapped = s.clone()
        swapped.i_card = s.i_card[:]
        swapped.i_card[mine[0]] = _other_card(pool, s.i_card[mine[0]], CardType.LEGEND)
        for flag in (True, False):
            assert info_key(swapped, me, known_opponent_deck=flag) != \
                info_key(s, me, known_opponent_deck=flag), "I know which three I brought"


# ------------------------------------------------- pinning is declared, never guessed
def test_a_choice_pins_only_the_instances_it_declares(pool):
    """``v-roamer-of-the-badlands`` offers plain amounts (1..5) to increase a stolen Gig by.

    Introspecting a continuation's closure read those as instance ids — and instances 1..5 are
    player 0's opening deck — so three of the opponent's deck cards became *known* to the seat
    holding the roamer, dropped out of ``unknown_to``, were frozen by the sampler and were written
    into that seat's key. A choice now pins what it declares and nothing else.
    """
    s = board(pool,
              Side(eddies=4, deck=["corpo-security"] * 3 + ["chrome-fang"] * 3,
                   gig=[(6, 3), (8, 2)], legends=["johnny-silverhand-rocking-renegade"]),
              Side(field=["v-roamer-of-the-badlands"], eddies=4, deck=["corpo-security"] * 4,
                   legends=["adam-smasher-ender-of-legends"], gig=[(10, 1)]),
              active=1)
    do(s, Attack(find(s, "v-roamer-of-the-badlands", zone=Zone.FIELD, player=1)))
    do(s, Target(TARGET_GIG))
    for _ in range(20):                                   # through the reaction window and the steal
        legal_actions(s)
        if s.pending is None or s.pending.prompt == "Increase the stolen Gig":
            break
        apply(s, s.pending.index_of(Pass()) if s.pending.kind is ChoiceKind.REACTION else 0)
    assert s.pending is not None and s.pending.prompt == "Increase the stolen Gig"
    assert s.pending.kind is ChoiceKind.PICK and s.pending.player == 1
    assert _pinned(s, 1) == (), "a choice over plain numbers pinned instances"

    deck0 = s.zone(0, Zone.DECK)
    assert deck0 and all(i in unknown_to(s, 1) for i in deck0), "the rival's deck is not mine to see"
    assert not any(knows_identity(s, 1, i) for i in deck0)
    moved = {tuple(determinize(s, 1, Pcg32(n)).i_card[i] for i in deck0) for n in range(20)}
    assert len(moved) > 1, "the rival's deck is frozen at its true order"


def test_a_pick_over_deck_cards_resamples_for_the_seat_that_did_not_see_them(pool):
    """The complement of the pinning test above: an open peek is pinned for the seat it was shown
    to, and stays hidden — and resampled — for the other one."""
    deck = ["corpo-security"] * 4 + ["chrome-fang"] * 4
    s = board(pool, Side(hand=["three-mouths-one-desire"], eddies=6, deck=deck,
                         legends=["johnny-silverhand-rocking-renegade"]),
              Side(eddies=2, deck=deck, legends=["adam-smasher-ender-of-legends"]))
    do(s, Play(find(s, "three-mouths-one-desire", zone=Zone.HAND, player=0)))
    assert s.pending.kind is ChoiceKind.PICK and s.pending.player == 0
    top = s.z[0 * NZONE + Zone.DECK][-3:]
    assert set(s.pending.revealed) >= set(top), "the choice does not declare what it showed"
    assert _pinned(s, 0) == s.pending.revealed and _pinned(s, 1) == ()
    for n in range(10):                                    # pinned for the searcher
        assert [determinize(s, 0, Pcg32(n)).i_card[i] for i in top] == [s.i_card[i] for i in top]
    worlds = {tuple(determinize(s, 1, Pcg32(n)).i_card[i] for i in top) for n in range(25)}
    assert len(worlds) > 1, "the rival's seat treats a peek it never saw as knowledge"
