"""One-tap try-out boards: a playable position built around a single card.

The point of this module is that a person can look at any of the 151 cards and be *playing* it a
moment later, instead of building a deck that contains it and hoping to draw it. It exists because
that gap is why most of the pool had never been watched by a human: every client bug found by hand
so far (a Legend-naming leak, a card type that could not be chosen, a reveal that showed nothing)
was found by accident, because looking on purpose was too much work.

What it produces is a ``build_position`` spec — the same JSON board description the delayed-reward
suite is made of (:func:`cptcg.learn.delayed.build_position`), so the state that comes out is an
ordinary mid-game ``GameState`` whose turn stack continues normally. Nothing here is a special mode
inside the engine; the engine never learns that a game began this way.

Three things the board has to guarantee, and they are the whole design:

1. **The card is reachable.** It is in hand (or, for a Legend, face-down in the Legends area) with
   more €$ than it costs, a host Unit for Gear, and an empty-enough field. ``tests/web/test_sandbox``
   asserts this for every card in the pool, which is what makes "try any card" a fact rather than
   a hope.
2. **Its text has something to point at.** A rival Unit that can be attacked (so: spent), a rival
   Unit that cannot, Gigs on both sides, a face-up rival Legend, cards in both trashes and decks.
3. **Nothing else on the board does anything.** Every filler card is chosen as a *vanilla* card —
   no script, no keywords — so anything you see happen was your card. There are exactly four such
   Units and three such Legends in the pool, one per colour, and that is what they are used for.

Filler is picked by rule rather than by a hard-coded list of ids, so a card gaining a script drops
it out of the filler pool instead of silently turning the sandbox into a board with a surprise on it.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path

from cptcg.cards.registry import Registry
from cptcg.core.enums import CardType, Color, Keyword

#: Gigs both players start the sandbox with: three rolled dice, leaving three in the fixer. Enough
#: that a Gig-stealing card has something to steal and a Street Cred comparison is not 0 vs 0, and
#: far enough from 7 that nobody accidentally wins before they have played the card they came for.
GIGS = [[4, 4], [6, 5], [8, 7]]
FIXER = [10, 12, 20]

#: €$ over the card's cost. Four is enough to play the card and still do something else afterwards
#: (a second card, an ability, a Call) without being so much that cost stops being visible at all.
SLACK = 4

#: Cards drawn from, and sitting in, each deck. Only needs to outlast a try-out.
DECK_SIZE = 15


def _vanilla_units(reg: Registry) -> dict[Color, str]:
    """The one scriptless, keywordless Unit per colour — the filler that cannot perturb a test."""
    out: dict[Color, str] = {}
    for d in reg.defs:
        if (d.type is CardType.UNIT and d.script is None and not d.keywords
                and not d.needs_script and d.color not in out):
            out[d.color] = d.id
    return out


def _vanilla_legends(reg: Registry) -> list[str]:
    return [d.id for d in reg.defs if d.type is CardType.LEGEND and d.script is None]


def _filler_ids(units: dict[Color, str], tried: str) -> list[str]:
    """The filler pool with the card under test removed.

    Four of the 151 cards *are* the vanilla Units, and for those the generic board would otherwise
    deal the tried card as its own filler — two identical cards in hand, and no way to tell which
    one the button was about. The filler is what the card is being read against, so it must never
    be the card.
    """
    ids = [units[c] for c in sorted(units) if units[c] != tried]
    return ids or [units[c] for c in sorted(units)]


def _filler_deck(ids: list[str], n: int, start: int) -> list[str]:
    """``n`` filler cards, cycling the pool so a deck is not all one card."""
    return [ids[(start + k) % len(ids)] for k in range(n)]


def sandbox_spec(reg: Registry, card_id: str, overrides: dict | None = None) -> dict:
    """A ``build_position`` spec that puts ``card_id`` one decision away from being played.

    ``overrides`` is the contents of ``data/sandbox.json``: ``{card id: {spec patch}}``, merged one
    level deep into the generated spec (and two levels deep into ``sides``). It is the escape hatch
    for the cards whose text needs something this generic board does not have — a rival Unit wearing
    Gear, a full trash, a specific tag on the field. Hand-tuning one card is a line of JSON rather
    than a branch in this function, which is why the function stays readable as the pool grows.
    """
    d = reg.get(card_id)
    units = _vanilla_units(reg)
    legends = [c for c in _vanilla_legends(reg) if c != card_id]
    if not units or not legends:
        raise ValueError("no vanilla filler in this registry: sandbox boards need at least one "
                         "scriptless Unit and one scriptless Legend to build around")
    fill = _filler_ids(units, card_id)
    # The board Unit in the card's own colour, and one in another, neither ever the tried card.
    # Both fall back through `fill` rather than indexing `units` directly: the filler pool is
    # derived from "has no script and no keywords", so a colour drops out of it the day that card
    # gains a script, and a KeyError here would take every card of that colour down with it.
    same = units.get(d.color) or fill[0]
    if same == card_id:
        same = fill[0]
    other = units.get(Color((int(d.color) + 1) % 4)) or ""
    if other in (card_id, same, ""):
        other = next((i for i in fill if i != same), same)

    # A stable seed per card: the same card always deals the same sandbox, so RESTART reproduces
    # what you were just looking at and a bug report names a board I can rebuild. zlib.crc32 rather
    # than hash(), which is salted per process and would make "restart" mean "reshuffle".
    seed = zlib.crc32(card_id.encode()) % 1_000_000

    # Eddies: the card's cost plus slack. A Legend is reached by Calling it for 1 €$ first and only
    # then GO SOLO-ing it for its cost, so it needs both amounts, not the larger of them. All of it
    # is printed Eddies rather than leaning on the Legends area, because most of that area is face
    # up here and a face-up Legend is only €$ if it carries a Sell Tag (CR 5.7.2.2).
    cost = d.cost or 0
    eddies = cost + SLACK + (1 if d.type is CardType.LEGEND else 0)

    mine: dict = {
        # Two friendly Units: one in the card's own colour so "a friendly <colour> Unit" resolves,
        # one in another so "all friendly Units" is visibly more than one. Both ready and unlagged,
        # so they can attack and host Gear the moment the board appears.
        "field": [same, other],
        "eddies": eddies,
        "gig": GIGS,
        "fixer": FIXER,
        "deck": _filler_deck(fill, DECK_SIZE, 0),
        "trash": [other],
    }
    rival: dict = {
        # The spent one is the attackable one (CR 9.3.2: a ready Unit is not a legal target without
        # help), and it wears the card's colour so rival-colour effects resolve. The ready one is
        # there so "a ready rival Unit" and blocker-style text are not looking at an empty field.
        "field": [[same, {"spent": True}], other],
        "eddies": 3,
        "gig": GIGS,
        "fixer": FIXER,
        "hand": _filler_deck(fill, 3, 1),
        "deck": _filler_deck(fill, DECK_SIZE, 2),
        "trash": [same],
        # Six Legend slots are filled from a pool of three scriptless Legends (the whole supply),
        # so the rival's area repeats one. Duplicates are ordinary instances and nothing reads
        # identity across slots; a Legend that *did* something would be the worse trade.
        "legends": _filler_deck(legends, 3, 0),
    }

    # One rival Legend face-up, so "a face-up rival Legend" has a target; the other two stay
    # face-down, so effects that count or look at face-down cards do too.
    rival["legends"][0] = [rival["legends"][0], {"faceup": True}]

    # Exactly ONE of your Legends is face-down, and it is the card under test.
    #
    # This is the whole reason the rest of your Legends area is face-up. "Call a Legend" names no
    # card — it cannot, because in a real game you do not know which of your face-down Legends you
    # are turning over — so three face-down Legends produce three identical buttons and a one-in-
    # three chance of Calling the card you came to try. Calling is once per turn, so getting it
    # wrong does not just waste a tap: it ends your only route to the card for that turn.
    #
    # The card under test stays face-down rather than starting flipped, because Calling it *is*
    # part of playing it: the flip is what fires its CALL trigger, and GO SOLO needs it face-up
    # anyway, so a GO SOLO Legend is genuinely two steps (Call, then GO SOLO). With one face-down
    # Legend there is one Call button and it is unambiguously the right one.
    if d.type is CardType.LEGEND:
        mine["legends"] = [card_id, [legends[0], {"faceup": True}], [legends[1], {"faceup": True}]]
        mine["hand"] = _filler_deck(fill, 2, 0)
    else:
        # Still one face-down Legend, so Calling one is a move you can try alongside the card, and
        # still only one — so which Legend a Call turns over is never a guess.
        mine["legends"] = [legends[0], [legends[1], {"faceup": True}],
                           [legends[2 % len(legends)], {"faceup": True}]]
        mine["hand"] = [card_id] + _filler_deck(fill, 2, 0)

    spec = {"seed": seed, "turn": 3, "active": 0, "first_player": 0,
            "turns_taken": [1, 1], "overtime": False, "sides": [mine, rival]}

    patch = (overrides or {}).get(card_id)
    if patch:
        for key, value in patch.items():
            if key == "sides":
                for p, side_patch in enumerate(value):
                    if side_patch:
                        spec["sides"][p].update(side_patch)
            else:
                spec[key] = value
    return spec


def load_overrides(path: str | Path) -> dict:
    """``data/sandbox.json`` if it exists, else no overrides. Missing is the normal case."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
