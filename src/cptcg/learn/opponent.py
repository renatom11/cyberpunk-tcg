"""What the rival's own plays prove about the deck they are holding.

This is the skill a person picks up in an evening and no agent in this project has ever had. You do
not know a rival's Legends at the start, or any of their cards. Then they play something, and its
colour and RAM give the Legends away — and once you know the Legends you know the *pool* the rest of
their deck can be drawn from, which is what tells you whether the thing that beats you is live.

The worked example, which is a real card: **Chrome Reverie** is Blue, 1 RAM, and reads "A rival Unit
can't attack until your next turn." If the rival has shown any Blue at all, then in a close late
game you do not win on exactly one attacker, because one Blue card takes it off the table on the
turn it mattered. If they have shown no Blue, that entire class of disaster is off the board and
playing around it is pure loss.

The deduction is exact, not a guess
-----------------------------------
Every Legend in the game is **2 RAM** — all twenty-seven of them — and a Legend's RAM counts only
toward its own colour (CR, "Deck building & RAM"). Three Legends, so a colour's cumulative RAM limit
is 0, 2, 4 or 6. Therefore:

    a rival card of colour X and RAM r  =>  they hold at least ceil(r / 2) Legends of colour X

r of 1 or 2 proves one, 3 or 4 proves two, 5 or 6 proves all three. And because there are only three
Legends, the bounds *compete*: two proven Blue leaves room for exactly one other colour, and three
proven Blue rules out every other colour in the game. The non-Legend pool is an even **31 cards per
colour, 124 in all**, so each colour excluded removes a quarter of everything they could draw, and a
demonstrated mono-Blue deck narrows their possible pool from 124 cards to 31.

The second half of that is sharper than it looks and is the part a human tends to miss: proving two
Blue does not merely make Red *less likely*, it caps Red's cumulative RAM at 2, which makes every
Red card of 3 RAM or more **impossible** — not unlikely, impossible. :func:`possible_pool` applies
the RAM cap, not just the colour filter.

What this module may read
-------------------------
Only what this seat may legitimately see. Every instance is tested with ``view.knows_identity``, so
a rival card in hand or deck is invisible here exactly as it is to ``learn/features.py``, and a
permuted world (``view.determinize``) cannot move any number this module returns. That last property
is the one worth stating plainly, because determinization preserves the rival's true deck *multiset*
— a sampled world knows their decklist, which is more than a person gets. Reading the sampled world
would be a leak dressed up as a feature and would not generalise to an opponent whose deck the agent
has never seen. So the bounds come from the public record and nothing else, and a test pins it.

Pure stdlib, like everything under ``src/cptcg``: this package is shipped into the browser.
"""

from __future__ import annotations

from cptcg.core.enums import Color, Zone
from cptcg.core.state import GameState
from cptcg.core.view import knows_identity

#: Legends a player has. Every colour bound is capped by this, and the caps are what make one
#: colour's evidence into another colour's exclusion.
LEGEND_SLOTS = 3

#: RAM on a Legend card. Every Legend in the set carries this, which is what makes the bound exact
#: rather than a lower bound on a lower bound; ``legend_ram`` re-derives it from the registry so a
#: future card with a different value fails loudly instead of quietly weakening every deduction.
LEGEND_RAM = 2

NCOLOR = len(Color)


def legend_ram(reg) -> int:
    """The RAM every Legend carries, from the registry rather than from this file's memory.

    Raises if the set ever ships Legends with differing RAM. The whole deduction below divides by
    this number, so a silent change would not break anything visibly — it would just make every
    bound wrong, which is the failure mode worth an exception.
    """
    seen = {d.ram for d in reg.defs if d.is_legend}
    if len(seen) != 1:
        raise ValueError(f"Legends no longer share one RAM value ({sorted(seen)}); the colour "
                         f"deduction in learn/opponent.py divides by it and must be revisited")
    return seen.pop()


def _public_cards(s: GameState, me: int, rival: int):
    """Every rival instance this seat may read the identity of, as ``CardDef``.

    Their hand and deck are excluded by ``knows_identity`` rather than by a zone list here, so an
    open peek that legitimately showed me a card in hand counts — it is information I have — and a
    face-down Legend does not.
    """
    for zone in (Zone.FIELD, Zone.TRASH, Zone.EDDIES, Zone.LEGENDS, Zone.REMOVED, Zone.LIMBO,
                 Zone.HAND, Zone.DECK):
        for i in s.z[rival * len(Zone) + zone]:
            if knows_identity(s, me, i):
                yield s.reg.defs[s.i_card[i]]


def colour_bounds(s: GameState, me: int) -> list[int]:
    """Per colour, the fewest Legends of that colour the rival can possibly hold.

    Two independent sources, and the stronger wins: a face-up Legend of colour X is direct evidence
    of one, and a played card of colour X and RAM r is indirect evidence of ``ceil(r / 2)``. Indexed
    by ``Color``.
    """
    rival = 1 - me
    ram = legend_ram(s.reg)
    by_ram = [0] * NCOLOR
    faceup = [0] * NCOLOR
    for d in _public_cards(s, me, rival):
        c = int(d.color)
        if d.is_legend:
            faceup[c] += 1
        elif d.ram:
            by_ram[c] = max(by_ram[c], -(-d.ram // ram))      # ceil without importing math
    bounds = [max(by_ram[c], faceup[c]) for c in range(NCOLOR)]
    # The bounds compete for three slots. A set that demands more than three is not reachable, which
    # would mean the evidence is being read wrongly rather than that the rival broke a rule.
    if sum(bounds) > LEGEND_SLOTS:
        raise ValueError(f"colour bounds {bounds} need more than {LEGEND_SLOTS} Legends")
    return bounds


def max_ram(bounds: list[int], *, ram: int = LEGEND_RAM) -> list[int]:
    """Per colour, the largest cumulative RAM the rival could still have in it.

    Every Legend slot not already proven to be another colour is optimistically given to this one.
    This is the cap that turns "they have shown two Blue" into "a 3-RAM Red card is impossible",
    which is a stronger statement than any colour filter can make.
    """
    others = [sum(b for c, b in enumerate(bounds) if c != k) for k in range(NCOLOR)]
    return [ram * (LEGEND_SLOTS - others[k]) for k in range(NCOLOR)]


def possible_pool(reg, bounds: list[int]) -> frozenset:
    """Card ids the rival could still legally be holding, given what they have shown.

    A card survives when its colour has a Legend slot left *and* its RAM fits under that colour's
    largest still-possible cumulative RAM. Legends themselves are excluded: this is the pool of
    things that can be played at you.
    """
    caps = max_ram(bounds, ram=legend_ram(reg))
    return frozenset(d.id for d in reg.defs
                     if not d.is_legend and d.ram <= caps[int(d.color)] and caps[int(d.color)] > 0)


def excluded_colours(bounds: list[int]) -> frozenset:
    """Colours the rival provably cannot hold a Legend of, because the slots are already spoken for."""
    caps = max_ram(bounds)
    return frozenset(Color(c) for c in range(NCOLOR) if caps[c] == 0)


def summary(s: GameState, me: int) -> dict:
    """The whole reading of the rival, for a card guide, a report, or a human looking at a board."""
    bounds = colour_bounds(s, me)
    return {"bounds": {Color(c).name: bounds[c] for c in range(NCOLOR)},
            "max_ram": {Color(c).name: r for c, r in enumerate(max_ram(bounds, ram=legend_ram(s.reg)))},
            "excluded": sorted(c.name for c in excluded_colours(bounds)),
            "pool": len(possible_pool(s.reg, bounds))}


# ------------------------------------------------------------------ threats over the pool
#: Tokens from the interaction map that describe something the rival can do *to me*, paired with
#: the board condition that makes it hurt. The map (``data/strategy/graph.json``, 151 cards, 48
#: tokens) is what turns "these 97 cards are possible" into "one of them beats the board I am
#: about to build", which is the whole reason the map was drawn.
#:
#: ``unit.spend_rival`` is the Chrome Reverie case and the reason this list is checked against the
#: card text rather than trusted: the map originally *missed* it on Chrome Reverie and on MaxTac
#: Suppression Team, the two cards whose printed text says in as many words that a rival Unit
#: cannot attack. ``tests/cards/test_graph.py`` now reads the text and fails on a card that says so
#: without carrying the token.
THREATS = ("unit.spend_rival", "unit.defeat_rival", "unit.power_zero", "discard.rival",
           "gig.decrease")


def threat_pool(reg, graph: dict, bounds: list[int]) -> dict:
    """Per threat token, how many cards the rival could still be holding that carry it.

    Counted over :func:`possible_pool`, so a colour they have provably crowded out contributes
    nothing — which is the point. A rival with three Blue Legends cannot hold the Red removal, and
    an agent that keeps playing around it is paying a premium for nothing.
    """
    live = possible_pool(reg, bounds)
    cards = graph.get("cards") or {}
    out = {t: 0 for t in THREATS}
    for cid in live:
        produces = (cards.get(cid) or {}).get("produces") or ()
        for t in THREATS:
            if t in produces:
                out[t] += 1
    return out
