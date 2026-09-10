"""Honest hidden information: what one player may legitimately know, and worlds consistent with it.

A live ``GameState`` is a fully determined world. Legend identities are decided eagerly at setup
and the deck is already shuffled, so nothing in the state is *undecided* — hiding is a masking
problem for the agent, not a sampling problem for the engine. This module is the single definition
of that mask, and of how to resample the parts of the world a given seat cannot see.

What a seat ``me`` actually knows
---------------------------------

*My hand.* Exactly, card by card. It is in front of me.

*My deck.* I know the **multiset** — it is my own list minus everything that has left it — but not
the **order**. Ruling: decks are shuffled and never inspected, so the top card is as unknown to its
owner as to anyone. So every deck instance counts as an unknown identity even for its owner, while
the multiset of those identities is knowledge and is part of the key.

*My face-down Legends.* Unknown, slot by slot. A Legend is Called without peeking (``engine.new_game``
shuffles the three Legend card indices into slots before the game starts), so I know *which three
cards* I brought but not which slot holds which. ``ops.call_legend`` sets ``i_known`` to ``0b11``
when a Legend is flipped, and ``effects.look_at`` sets bit ``p`` when player ``p`` privately peeks.
``i_known`` is the authoritative ledger: nothing in the engine reads it, so it exists solely to
answer this question.

*The rival's hand.* Unknown. Only the **count** is public.

*The rival's deck.* Unknown order, and — unless ``known_opponent_deck`` — unknown contents. Their
hand and their deck are one joint pool: I cannot tell a card they are holding from a card they have
yet to draw, so the two zones permute together.

*Everything else is public.* Field, Gear and its host, Trash, Removed, Limbo, the Gig and Fixer
areas, the turn structure. The Eddies area is public as an **unordered multiset** (ruling 002: a
card is revealed as it is sold), so the key sorts it rather than recording its order.

Why permuting hidden identities is safe
---------------------------------------

``i_card`` is shared between clones, so ``determinize`` replaces the list (``c.i_card = s.i_card[:]``)
before touching it, then permutes card indices **within** each hidden group. Nothing else moves: the
zone lists, ``i_owner`` and every other ``i_*`` array are untouched, so a permuted world is still
structurally the state it came from.

* A deck instance carries no live text, so its identity is inert until it is drawn. Permuting deck
  identities *is* permuting deck order, and since ``ops.draw`` pops ``deck[-1]`` and consumes no
  randomness, that is a **complete** determinization of every future draw. The only remaining chance
  node in the game is the Gig die roll.
* A face-down Legend contributes no text at all (ruling 031 — ``ops._rebuild_active`` admits only
  face-up Legends), it is never a legal Gear host (``legal.gear_hosts``), and it is a payment source
  by slot and readiness rather than by identity (``ops.payable_sources``). Nothing in legal-move
  generation reads its card definition. Its identity is therefore causally inert and permuting slots
  disturbs nothing — in particular ``s._active`` stays valid and is still shared with the original.
* The rival's hand cards are inert until played, and ``legal.reaction_menu`` selects among them by
  type and cost, which is exactly the information a determinized world commits to.

What this module deliberately does *not* model
----------------------------------------------

The engine keeps no ledger for deck-position knowledge, so two kinds of knowledge are **over-hidden**
(the mask forgets something a player saw; it never invents something a player did not see):

* A card bottom-decked from a public zone (``effects.bottom_deck``) is a card everyone watched go to
  a known position. Here it becomes an anonymous deck instance again.
* A private peek that is not followed by a choice among the peeked cards — "look at the top card,
  you may draw it" — leaves no trace once the choice it produced has been answered.

The one case that *is* modelled is the peek that is still open: while a ``PICK`` choice belonging to
``me`` is pending, the deck and hand instances offered by that choice have been shown to ``me``
(``effects.search_top`` looks at the top ``n`` and then asks), so they are pinned and never permuted.
Choices among face-down Legends are excluded from that rule, because those are deliberately blind —
"Look at a face-down Legend" asks you to pick a slot precisely without knowing what is under it.

Erring toward forgetting is the safe direction: an agent built on this plays a strictly harder game
than it is entitled to, and never one that leaks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cptcg.core.actions import ChoiceKind
from cptcg.core.enums import NO_INST, NZONE, Zone

if TYPE_CHECKING:
    from cptcg.core.state import GameState

# Identity written over an unknown card by ``redact``. Out of range for ``reg.defs`` on purpose:
# any code that reads a hidden card's definition raises IndexError instead of quietly lying.
HIDDEN_CARD = 1 << 30

#: Zones whose contents are public to both seats. DECK, HAND and LEGENDS are handled case by case.
PUBLIC_ZONES = frozenset({Zone.FIELD, Zone.EDDIES, Zone.TRASH, Zone.REMOVED, Zone.LIMBO})


# --------------------------------------------------------------------- predicates
def hand_visible(s: "GameState", me: int | None, player: int) -> bool:
    """May ``me`` read player ``player``'s hand? ``me=None`` is the omniscient view."""
    return me is None or me == player


def legend_identity_known(s: "GameState", me: int | None, inst: int) -> bool:
    """May ``me`` read a Legend slot's identity? Face-up Legends are public; a face-down slot is
    known only to a seat whose ``i_known`` bit is set (``ops.call_legend``, ``effects.look_at``)."""
    if s.i_faceup[inst]:
        return True
    return me is None or bool(s.i_known[inst] & (1 << me))


def knows_identity(s: "GameState", me: int | None, inst: int) -> bool:
    """May ``me`` legitimately read ``inst``'s card identity? ``me=None`` is the omniscient view."""
    zone = s.i_zone[inst]
    if zone == Zone.LEGENDS:
        if s.i_host[inst] != NO_INST:          # Gear equipped to a Legend: hosts are face-up, so public
            return True
        return legend_identity_known(s, me, inst)
    if zone == Zone.HAND:
        return me is None or s.i_owner[inst] == me or inst in _pinned(s, me)
    if zone == Zone.DECK:
        return me is None or inst in _pinned(s, me)
    return True


# --------------------------------------------------------- open peeks (pinned instances)
def _pinned(s: "GameState", me: int | None) -> frozenset:
    """Deck and hand instances that the *pending* choice has already shown to ``me``.

    ``effects.choose``/``choose_many`` close over ``vals``, the list the player is choosing from, so
    an open ``PICK`` is the one place the state still records a private peek. Legend slots are
    excluded: those choices are blind by design. Any failure to introspect falls back to "nothing
    pinned", which over-hides and is safe.
    """
    ch = s.pending
    if me is None or ch is None or ch.kind is not ChoiceKind.PICK or ch.player != me:
        return frozenset()
    try:
        cells = ch.cont.__closure__ or ()
        names = ch.cont.__code__.co_freevars
        vals = dict(zip(names, cells))["vals"].cell_contents
    except Exception:                          # noqa: BLE001 - any shape we don't recognise pins nothing
        return frozenset()
    n = len(s.i_card)
    out = []
    for v in vals:
        if type(v) is int and 0 <= v < n and s.i_zone[v] in (Zone.DECK, Zone.HAND):
            out.append(v)
    return frozenset(out)


# ------------------------------------------------------------------ unknown instances
def _hidden_groups(s: "GameState", me: int) -> list[list[int]]:
    """The permutation groups: sets of instances whose identities ``me`` may not tell apart.

    Identities never cross a group boundary, so a permuted world preserves every multiset ``me``
    knows — each player's own cards stay their own, and a Legend stays in the Legends area.
    """
    pin = _pinned(s, me)
    rival = 1 - me
    groups = [
        # My own deck: I know the multiset, not the order.
        [i for i in s.z[me * NZONE + Zone.DECK] if i not in pin],
        # The rival's hand and deck are one pool: I cannot tell held from undrawn.
        [i for i in s.z[rival * NZONE + Zone.HAND] + s.z[rival * NZONE + Zone.DECK] if i not in pin],
    ]
    for p in (0, 1):                           # face-down Legend slots, per owner
        groups.append([i for i in s.legends(p) if not legend_identity_known(s, me, i)])
    return groups


def unknown_to(s: "GameState", me: int) -> list[int]:
    """Instances whose identity ``me`` may not legitimately know, in instance order."""
    out: list[int] = []
    for g in _hidden_groups(s, me):
        out += g
    out.sort()
    return out


# ------------------------------------------------------------------------ info key
def _hashable(v):
    try:
        hash(v)
    except TypeError:
        return repr(v)
    return v


def _gear_key(s: "GameState", host: int, unk: set) -> tuple:
    return tuple((g, None if g in unk else s.i_card[g], s.i_spent[g]) for g in s.gear_on(host))


def _zone_key(s: "GameState", insts: list[int], unk: set) -> tuple:
    """A hidden zone: its size, plus every instance in it whose identity ``me`` does know."""
    return (len(insts), tuple(sorted((i, s.i_card[i]) for i in insts if i not in unk)))


def _player_key(s: "GameState", p: int, unk: set) -> tuple:
    base = p * NZONE
    return (
        tuple((i, s.i_card[i], s.i_spent[i], s.i_lag[i], s.i_flags[i], _gear_key(s, i, unk))
              for i in s.units(p)),
        tuple((i, int(bool(s.i_faceup[i])), s.i_spent[i], s.i_flags[i], _gear_key(s, i, unk),
               None if i in unk else s.i_card[i]) for i in s.legends(p)),
        # Ruling 002: the Eddies area is public, but as an unordered multiset.
        tuple(sorted((s.i_card[i], s.i_spent[i]) for i in s.z[base + Zone.EDDIES])),
        tuple(s.i_card[i] for i in s.z[base + Zone.TRASH]),
        tuple(s.i_card[i] for i in s.z[base + Zone.REMOVED]),
        tuple((i, s.i_card[i]) for i in s.z[base + Zone.LIMBO]),
        _zone_key(s, s.z[base + Zone.HAND], unk),
        _zone_key(s, s.z[base + Zone.DECK], unk),
        tuple(s.gig[p]),
        tuple(s.fixer[p]),
    )


def _pending_key(s: "GameState", me: int) -> tuple | None:
    """The pending decision. The option list is included only when it is ``me``'s decision: the
    rival's menu is derived from their hand and would leak it (``legal.reaction_menu`` offers
    ``Play`` for each quick Program they hold)."""
    ch = s.pending
    if ch is None:
        return None
    head = (int(ch.kind), ch.player, ch.prompt)
    if ch.lazy or ch.player != me:
        return head + (ch.lazy,)
    return head + (False, ch.options)


def _atk_key(s: "GameState") -> tuple | None:
    a = s.atk
    if a is None:
        return None
    return (a.attacker, a.attacker_ctrl, a.target_kind, a.target, a.gig_steal_allowed,
            a.redirects, a.fizzled)


def info_key(s: "GameState", me: int, *, known_opponent_deck: bool = True) -> tuple:
    """A hashable digest of everything ``me`` legitimately knows, and nothing more.

    Two states that ``me`` cannot tell apart share a key; any observation ``me`` makes — a card
    drawn, a Legend Called, a die rolled — changes it. ``determinize`` never changes it, which is
    the defining property of a sampled world and is asserted over whole games in
    ``tests/props/test_determinization.py``.

    With ``known_opponent_deck=False`` the multiset of the rival's hidden pool drops out of the key,
    modelling game one of a match where their list has not been seen. Layout::

        ( me,
          turn, active, first_player, overtime, empty_starts,
          over, winner, end_reason,
          turns_taken, once,
          (player 0 key, player 1 key),          # see _player_key
          my hidden deck multiset,               # card indices, sorted
          rival hidden pool multiset or None,    # hand+deck, card indices, sorted
          pending key, attack key,
          stack step types, temp_power, mods, used keys, played )
    """
    unk = set(unknown_to(s, me))
    rival = 1 - me
    my_pool = tuple(sorted(s.i_card[i] for i in s.z[me * NZONE + Zone.DECK] if i in unk))
    their_pool = None
    if known_opponent_deck:
        their = s.z[rival * NZONE + Zone.HAND] + s.z[rival * NZONE + Zone.DECK]
        their_pool = tuple(sorted(s.i_card[i] for i in their if i in unk))
    return (
        me,
        s.turn, s.active, s.first_player, int(s.overtime), s.empty_starts,
        int(s.over), s.winner, int(s.end_reason) if s.over else None,
        tuple(s.turns_taken), tuple(s.once),
        (_player_key(s, 0, unk), _player_key(s, 1, unk)),
        my_pool, their_pool,
        _pending_key(s, me), _atk_key(s),
        tuple(type(x).__name__ for x in s.stack),
        tuple(s.temp_power),
        tuple((k, sub, _hashable(v), e) for k, sub, v, e in s.mods),
        tuple(sorted(repr(k) for k in s.used)),
        tuple(s.played),
    )


# ------------------------------------------------------------------- determinization
def determinize(s: "GameState", me: int, rng, *, known_opponent_deck: bool = True) -> "GameState":
    """A world consistent with everything ``me`` knows, sampled uniformly.

    Clones ``s``, breaks the shared identity array, and permutes card indices within each hidden
    group (``_hidden_groups``). Only deck order, the rival's hand and face-down Legend slots move;
    ``info_key(determinize(s, me, rng), me) == info_key(s, me)`` holds exactly, every public zone is
    byte-identical, and ``s._active`` is still valid and still shared.

    ``rng`` is anything with ``shuffle(list)`` — ``core.rng.Pcg32`` or ``random.Random``. Sampling
    is a pure function of that generator's state, so the same seed gives the same world.

    ``known_opponent_deck=False`` says the rival's list has not been seen. It coarsens the
    information set (see ``info_key``) but does not change the sampler: a world has to assign an
    identity to each instance that exists, and without a decklist there is no honest distribution
    over identities available inside ``core``. Permuting the pool is *consistent with* the coarser
    key, so the sampler stays sound — it is simply not yet exploiting the extra freedom. That is the
    hook for the difficulty knob.
    """
    c = s.clone()
    c.i_card = s.i_card[:]                     # break the array clone() shares
    i_card = c.i_card
    for g in _hidden_groups(s, me):
        if len(g) < 2:
            continue
        ids = [i_card[i] for i in g]
        rng.shuffle(ids)
        for inst, cid in zip(g, ids):
            i_card[inst] = cid
    return c


def redact(s: "GameState", me: int) -> "GameState":
    """A clone whose unknown identities are blanked to ``HIDDEN_CARD``.

    Reading a blanked card's definition raises ``IndexError`` rather than returning a plausible
    wrong answer, which is what makes it useful as a paranoid check: run an agent on a redacted
    state and any peek at hidden information is a crash, not a silent advantage.
    """
    c = s.clone()
    c.i_card = s.i_card[:]
    for i in unknown_to(s, me):
        c.i_card[i] = HIDDEN_CARD
    return c
