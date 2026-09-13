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

from cptcg.core.enums import NZONE, Color, Zone
from cptcg.core.state import NO_INST, GameState
from cptcg.core.view import PUBLIC_ZONES, knows_identity, legend_identity_known

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


def _public_instances(s: GameState, me: int, rival: int):
    """Every rival instance this seat may read, as ``(instance, is_a_face_up_Legend)``.

    Three sources, and they are split apart for speed rather than taste. The first version asked
    ``knows_identity`` about every instance the rival owns, including all forty cards of their deck,
    and cost **42.7 us against the whole feature vector's 46** — it would have doubled the price of
    every fit and every search leaf. The zones below are already ``PUBLIC_ZONES``, so the answer is
    known without asking; Legends need the face-up test; and hand or deck can only ever be visible
    through an open peek, which is a short tuple on the pending choice rather than a zone to scan.

    ``tests/learn/test_opponent.py`` pins the result against ``view.determinize``, so a shortcut
    that started reading something this seat may not see would fail there rather than here.
    """
    base = rival * NZONE
    for zone in (Zone.FIELD, Zone.TRASH, Zone.EDDIES, Zone.REMOVED, Zone.LIMBO):
        for i in s.z[base + zone]:
            yield i, False
    for i in s.z[base + Zone.LEGENDS]:
        if knows_identity(s, me, i):           # Gear on a Legend is public; the Legend may not be
            yield i, s.i_host[i] == NO_INST    # the Gear is not a Legend, so it proves by RAM
    ch = s.pending                              # an open peek, and nothing else, reveals hand/deck
    if ch is not None and ch.revealed and ch.player == me:
        owner, zones = s.i_owner, s.i_zone
        for i in ch.revealed:
            if owner[i] == rival and zones[i] in (Zone.HAND, Zone.DECK):
                yield i, False


#: ``(colour, Legends this card's RAM proves)`` per card index, built once per registry. The loop
#: below runs on every feature vector, so it reads two flat lists instead of touching four fields of
#: a dataclass per card — the difference is most of this function's cost.
_EVIDENCE: dict[int, tuple[tuple[int, ...], tuple[int, ...]]] = {}


def _evidence(reg) -> tuple[tuple[int, ...], tuple[int, ...]]:
    key = id(reg)
    got = _EVIDENCE.get(key)
    if got is None:
        ram = legend_ram(reg)
        colours = tuple(int(d.color) for d in reg.defs)
        # A Legend proves itself once it is face-up; anything else proves ceil(ram / 2).
        needs = tuple(1 if d.is_legend else (-(-d.ram // ram) if d.ram else 0) for d in reg.defs)
        got = _EVIDENCE[key] = (colours, needs)
    return got


def colour_bounds(s: GameState, me: int) -> list[int]:
    """Per colour, the fewest Legends of that colour the rival can possibly hold.

    Two independent sources, and the stronger wins: a face-up Legend of colour X is direct evidence
    of one, and a played card of colour X and RAM r is indirect evidence of ``ceil(r / 2)``. Indexed
    by ``Color``.

    Note that the two combine differently: RAM evidence is a **maximum** (one 4-RAM card proves two
    Legends; a second proves nothing more) while face-up Legends **count**. Getting that backwards
    would read three 1-RAM Blue cards as three Blue Legends, which is not what they prove.
    """
    rival = 1 - me
    colours, needs = _evidence(s.reg)
    idx = s.i_card
    by_ram = [0] * NCOLOR
    faceup = [0] * NCOLOR
    for inst, is_legend in _public_instances(s, me, rival):
        k = idx[inst]
        c = colours[k]
        if is_legend:
            faceup[c] += 1
        else:
            n = needs[k]
            if n > by_ram[c]:
                by_ram[c] = n
    bounds = [max(by_ram[c], faceup[c]) for c in range(NCOLOR)]
    total = sum(bounds)
    if total > LEGEND_SLOTS:
        # The deduction assumes the rival's deck is **legal**: RAM limits are a deck-building rule,
        # so in a real game the evidence can never demand a fourth Legend. Hand-built boards are not
        # bound by that — ``learn/delayed.build_position`` places cards directly, and the delayed
        # suite holds positions that would be illegal to actually construct. It found this by
        # killing an arena run mid-flight, which is the right answer for an engine invariant and the
        # wrong one for a feature vector: ``features()`` has to be total, or a synthetic position
        # takes the whole measurement down with it.
        #
        # So the impossible reading is clamped rather than raised on, weakest evidence first, which
        # keeps the strongest colour claim intact. Real games never reach this branch.
        order = sorted(range(NCOLOR), key=lambda c: bounds[c])
        for c in order:
            while bounds[c] > 0 and total > LEGEND_SLOTS:
                bounds[c] -= 1
                total -= 1
            if total <= LEGEND_SLOTS:
                break
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
