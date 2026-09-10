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

*My face-down Legends.* Unknown slot by slot, known as a **multiset**. A Legend is Called without
peeking (``engine.new_game`` shuffles the three Legend card indices into slots before the game
starts), so I know *which three cards* I brought but not which slot holds which — exactly the deck
situation, and the key records it the same way. ``ops.call_legend`` sets ``i_known`` to ``0b11``
when a Legend is flipped, and ``effects.look_at`` sets bit ``p`` when player ``p`` privately peeks.
``i_known`` is the authoritative ledger: nothing in the engine reads it, so it exists solely to
answer this question.

*The rival's hand.* Unknown. Only the **count** is public.

*The rival's deck, and their face-down Legends.* Unknown order and slot, and — unless
``known_opponent_deck`` — unknown contents. Their hand and their deck are one joint pool: I cannot
tell a card they are holding from a card they have yet to draw, so the two zones permute together.

*What ``known_opponent_deck`` means.* One thing, decided here and honoured by both ``info_key`` and
``determinize``: **I have seen their decklist** — its 40-odd main-deck cards *and* its three
Legends, since a ``Decklist`` is both. So with the flag set, the multiset of their hidden pool and
the multiset of their face-down Legend slots are knowledge and are part of the key; with it clear,
neither is, and the key is blind to both. The flag never touches slot or draw order: that is
unknown to everyone, always.

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

The one case that *is* modelled is the peek that is still open: a ``Choice`` **declares** what it
showed its player in ``Choice.revealed`` (``effects.choose(..., revealed=...)``), and while that
choice is pending those instances are pinned and never permuted. It is declared, never guessed —
an earlier version introspected the continuation's closure and treated any small int it found as an
instance id, which silently revealed three of the *rival's* deck cards whenever a card offered a
plain number to choose from (``v-roamer-of-the-badlands`` offers 1..5, an amount). A choice that
declares nothing reveals nothing, which is why "Look at a face-down Legend" needs no special case:
it is blind by design, and ``effects.look_at`` writes ``i_known`` once the slot is actually seen.

There is one leak this module cannot close from where it stands. A menu the engine materialised
from cards ``me`` cannot see states its own **size**: "the defender may play 2 of their hidden
cards", "the rival is choosing among 2 of the 3 they just looked at". ``info_key`` refuses to encode
it (``_pending_key`` drops a rival's options) and ``determinize`` rebuilds every menu it can derive
(below), but a ``PICK``'s option list is produced by a card script that cannot be re-run from here,
so its *length* survives into the sampled world. What survives is only a count: ``PICK`` options are
indices into the effect's own list, never instance ids, so no sampled world is ever handed a card it
should not have, and every option stays applicable in every world.

Erring toward forgetting is the safe direction: an agent built on this plays a strictly harder game
than it is entitled to, and never one that leaks.
"""

from __future__ import annotations

from dataclasses import replace
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
    """May ``me`` legitimately read ``inst``'s card identity? ``me=None`` is the omniscient view.

    Every zone is classified: an unclassified one raises rather than falling through to "public",
    so adding a face-down area later fails loudly here instead of leaking quietly.
    """
    zone = s.i_zone[inst]
    if zone == Zone.LEGENDS:
        if s.i_host[inst] != NO_INST:          # Gear equipped to a Legend: hosts are face-up, so public
            return True
        return legend_identity_known(s, me, inst)
    if zone == Zone.HAND:
        return me is None or s.i_owner[inst] == me or inst in _pinned(s, me)
    if zone == Zone.DECK:
        return me is None or inst in _pinned(s, me)
    if zone in PUBLIC_ZONES:
        return True
    raise AssertionError(f"view: zone {zone!r} is neither public nor hidden — classify it")


# --------------------------------------------------------- open peeks (pinned instances)
def _pinned(s: "GameState", me: int | None) -> tuple[int, ...]:
    """Instances the *pending* choice has already shown to ``me``, straight from the choice.

    An open peek is the one place the state still records that a player was shown a hidden card
    (``effects.search_top`` looks at the top ``n`` and then asks), and the effect that peeked is the
    only thing that knows it happened — so it says so, in ``Choice.revealed``. Nothing here guesses:
    a choice that declares nothing pins nothing, which over-hides and is safe.
    """
    ch = s.pending
    if me is None or ch is None or ch.player != me:
        return ()
    return ch.revealed


# ------------------------------------------------------------------ unknown instances
def _hidden_groups(s: "GameState", me: int) -> list[list[int]]:
    """The permutation groups: sets of instances whose identities ``me`` may not tell apart.

    Identities never cross a group boundary, so a permuted world preserves every multiset ``me``
    knows — each player's own cards stay their own, and a Legend stays in the Legends area.
    """
    pin = _pinned(s, me)                       # what an open peek has already shown me
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


def _legend_pool_key(s: "GameState", p: int, unk: set) -> tuple:
    """The multiset of a player's face-down Legend slots: which cards are down there, not where.

    Mine is knowledge (I brought them); the rival's is knowledge exactly when I have seen their
    list, which is what ``known_opponent_deck`` says. ``determinize`` permutes within this same
    group, so a sampled world never changes it and the key stays stable.
    """
    return tuple(sorted(s.i_card[i] for i in s.legends(p) if i in unk))


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
    """The pending decision, identified by ``kind`` and ``tag`` — never by ``prompt``.

    Prompts are player-facing text and shipped cards format a card name into them ("Trash Modded
    Muramasa?"), so a prompt in the key would hand that card to a seat that cannot see it. The tag
    (``actions.call_site``) says which card asked which question and nothing else.

    The option list is included only when it is ``me``'s decision: a rival's menu is derived from
    their hand and would leak it (``legal.reaction_menu`` offers ``Play`` for each quick Program
    they hold). MAIN is dropped even then — that menu is a pure function of what ``me`` already
    knows, so it is redundant, and keeping it would make the key depend on whether anything had
    called ``engine.legal_actions`` yet (it materialises the lazy menu in place).
    """
    ch = s.pending
    if ch is None:
        return None
    head = (int(ch.kind), ch.player, ch.tag)
    if ch.player != me or ch.kind is ChoiceKind.MAIN:
        return head
    return head + (ch.options,)


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

    With ``known_opponent_deck=False`` the multisets of the rival's hidden pool *and* of their
    face-down Legend slots drop out of the key, modelling game one of a match where their list has
    not been seen. Layout::

        ( me,
          turn, active, first_player, overtime, empty_starts,
          over, winner, end_reason,
          turns_taken, once,
          (player 0 key, player 1 key),          # see _player_key
          my hidden deck multiset,               # card indices, sorted
          rival hidden pool multiset or None,    # hand+deck, card indices, sorted
          my face-down Legend multiset,          # card indices, sorted
          rival face-down Legend multiset or None,
          pending key, attack key,
          stack step keys, temp_power, mods, used keys, played )
    """
    unk = set(unknown_to(s, me))
    rival = 1 - me
    my_pool = tuple(sorted(s.i_card[i] for i in s.z[me * NZONE + Zone.DECK] if i in unk))
    their_pool = None
    if known_opponent_deck:
        their = s.z[rival * NZONE + Zone.HAND] + s.z[rival * NZONE + Zone.DECK]
        their_pool = tuple(sorted(s.i_card[i] for i in their if i in unk))
    my_legends = _legend_pool_key(s, me, unk)
    their_legends = _legend_pool_key(s, rival, unk) if known_opponent_deck else None
    return (
        me,
        s.turn, s.active, s.first_player, int(s.overtime), s.empty_starts,
        int(s.over), s.winner, int(s.end_reason) if s.over else None,
        tuple(s.turns_taken), tuple(s.once),
        (_player_key(s, 0, unk), _player_key(s, 1, unk)),
        my_pool, their_pool,
        my_legends, their_legends,
        _pending_key(s, me), _atk_key(s),
        tuple(x.key() for x in s.stack),
        tuple(s.temp_power),
        tuple((k, sub, _hashable(v), e) for k, sub, v, e in s.mods),
        tuple(sorted(repr(k) for k in s.used)),
        tuple(s.played),
    )


# ------------------------------------------------------------------- determinization
#: Menus ``determinize`` can re-derive from a sampled world. MULLIGAN/ORDER/GIG_DIE read nothing
#: hidden; PICK options are built by a card script that cannot be re-run from outside ``effects``.
_REDERIVABLE = frozenset({ChoiceKind.MAIN, ChoiceKind.REACTION, ChoiceKind.TARGET})
def determinize(s: "GameState", me: int, rng, *, known_opponent_deck: bool = True) -> "GameState":
    """A world consistent with everything ``me`` knows, sampled uniformly.

    Clones ``s``, breaks the shared identity array, and permutes card indices within each hidden
    group (``_hidden_groups``). Only deck order, the rival's hand and face-down Legend slots move;
    ``info_key(determinize(s, me, rng), me) == info_key(s, me)`` holds exactly, every public zone is
    byte-identical, and ``s._active`` is still valid and still shared.

    **The world agrees with its own menu.** A menu the engine built from the true cards does not
    survive into a world where those cards moved: ``legal.reaction_menu`` offers ``Play`` for each
    quick Program the defender actually holds, so copying it over would both tell the sampler how
    many they hold and hand it actions that are illegal in the sampled world — the engine will
    happily play a Blocker out of the defender's hand during the attacker's reaction window. So a
    pending menu that belongs to the **rival** is re-derived here: REACTION from ``reaction_menu``,
    TARGET from ``attack_targets``, MAIN by returning the choice to its lazy form so that
    ``engine.legal_actions`` derives it from this world on demand.

    A menu that belongs to ``me`` is left exactly as it is. Those options are ``me``'s own
    information — nothing they can see moved — and leaving them is what makes
    ``info_key(d, me) == info_key(s, me)`` true by construction rather than by luck, since the key
    carries options only for ``me``'s own decision.

    Two boundaries. A re-derived menu is used only if it is non-empty: ``attack_targets`` can come
    back empty, meaning that in this world the attack fizzles and this decision does not exist at
    all, and a decision with no options is not a world anyone can play out — so the real menu
    stands. And a ``PICK``'s options come from a card script that cannot be re-run from here; they
    are indices into that script's own list, so they stay applicable in any world, but their
    *count* is the one thing a sampled world still inherits from the real one (module docstring).

    ``rng`` is anything with ``shuffle(list)`` — ``core.rng.Pcg32`` or ``random.Random``. Sampling
    is a pure function of that generator's state, so the same seed gives the same world.

    ``known_opponent_deck=False`` says the rival's list has not been seen. It coarsens the
    information set (see ``info_key``) but does not change the sampler: a world has to assign an
    identity to each instance that exists, and without a decklist there is no honest distribution
    over identities available inside ``core``. Permuting the pool is *consistent with* the coarser
    key, so the sampler stays sound — it is simply not yet exploiting the extra freedom. That is the
    hook for the difficulty knob.
    """
    ch = s.pending
    rebuild = ch is not None and ch.player != me and ch.kind in _REDERIVABLE
    if rebuild and ch.kind is not ChoiceKind.MAIN:
        from cptcg.core.ops import _active
        _active(s)                             # fill the shared cache before cloning, so that
        #                                        re-deriving the menu below leaves d._active is s._active
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
    if rebuild:
        if ch.kind is ChoiceKind.MAIN:
            c.pending = replace(ch, options=(), lazy=True)
        else:
            from cptcg.core.legal import attack_targets, reaction_menu
            opts = tuple(reaction_menu(c) if ch.kind is ChoiceKind.REACTION
                         else attack_targets(c, c.atk.attacker))
            if opts:
                c.pending = replace(ch, options=opts)
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
