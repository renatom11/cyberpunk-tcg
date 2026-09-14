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
from cptcg.core.enums import DICE, CardType, Color, Keyword

#: Gigs both players start the sandbox with: three rolled dice, leaving three in the fixer. Enough
#: that a Gig-stealing card has something to steal and a Street Cred comparison is not 0 vs 0, and
#: far enough from 7 that nobody accidentally wins before they have played the card they came for.
DEFAULT_GIGS = 3

#: €$ over the card's cost. Four is enough to play the card and still do something else afterwards
#: (a second card, an ability, a Call) without being so much that cost stops being visible at all.
SLACK = 4

#: Cards drawn from, and sitting in, each deck. Only needs to outlast a try-out.
DECK_SIZE = 15


#: Script hooks that run without being asked: a card carrying one of these is doing something the
#: whole time it is on the board. Triggers (PLAY/CALL/ATTACK/DEFEATED) are not here — a Legend
#: sitting face-up in the Legends area is never played, Called or attacked with — and neither are
#: activated abilities, which only fire when a player spends something on them.
CONTINUOUS_HOOKS = ("on_event", "power_mod", "kw_mod", "cost_mod", "attack_perm",
                    "would_defeat", "would_steal", "unblockable")


def _is_inert(d, allow_abilities: bool = False) -> bool:
    """Can this card sit on the board doing nothing at all?

    ``verified`` is the first condition and the one that matters most. A card is unverified when
    its printed face was never captured, so every value on it is a placeholder — and because
    nobody could transcribe text for it, it also has no script, which made it look like the most
    inert card in the pool to any rule that asked only about behaviour. Exactly one card in 151 is
    in that state, and it was appearing on every board in the game as furniture.
    """
    if not d.verified:
        return False
    sc = d.script
    if sc is None:
        return True
    if any(getattr(sc, f, None) for f in CONTINUOUS_HOOKS) or sc.extra:
        return False
    return allow_abilities or not sc.abilities


def _vanilla_units(reg: Registry) -> dict[Color, str]:
    """The one inert, keywordless, textless Unit per colour — filler that cannot perturb a test."""
    out: dict[Color, str] = {}
    for d in reg.defs:
        if (d.type is CardType.UNIT and _is_inert(d) and not d.keywords
                and not d.needs_script and not d.text and d.color not in out):
            out[d.color] = d.id
    return out


def _filler_legends(reg: Registry, card_id: str, seed: int) -> list[str]:
    """Legends that can stand face-up in the Legends area without doing anything.

    Rotated by the card under test, so the same two faces do not appear behind all 151 cards. The
    bar is stricter than for a Unit, because these are face-up: no continuous hook (they would
    change the board under you) and no activated ability (it would put a button in your main menu
    that has nothing to do with the card you came to try).
    """
    pool = [d.id for d in reg.defs
            if d.type is CardType.LEGEND and _is_inert(d) and d.id != card_id]
    if not pool:
        return []
    k = seed % len(pool)
    return pool[k:] + pool[:k]


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
    # A stable seed per card: the same card always deals the same sandbox, so RESTART reproduces
    # what you were just looking at and a bug report names a board I can rebuild. zlib.crc32 rather
    # than hash(), which is salted per process and would make "restart" mean "reshuffle".
    d = reg.get(card_id)
    units = _vanilla_units(reg)
    seed = zlib.crc32(card_id.encode()) % 1_000_000
    legends = _filler_legends(reg, card_id, seed)
    if not units or not legends:
        raise ValueError("no inert filler in this registry: sandbox boards need at least one "
                         "inert Unit and one inert Legend to build around")
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
        "gig": _gigs(DEFAULT_GIGS),
        "fixer": list(_fixer(DEFAULT_GIGS)),
        "deck": _filler_deck(fill, DECK_SIZE, 0),
        "trash": [other],
    }
    rival: dict = {
        # The spent one is the attackable one (CR 9.3.2: a ready Unit is not a legal target without
        # help), and it wears the card's colour so rival-colour effects resolve. The ready one is
        # there so "a ready rival Unit" and blocker-style text are not looking at an empty field.
        "field": [[same, {"spent": True}], other],
        "eddies": 3,
        "gig": _gigs(DEFAULT_GIGS),
        "fixer": list(_fixer(DEFAULT_GIGS)),
        "hand": _filler_deck(fill, 3, 1),
        "deck": _filler_deck(fill, DECK_SIZE, 2),
        "trash": [same],
        # Six Legend slots are filled from a pool of three scriptless Legends (the whole supply),
        # so the rival's area repeats one. Duplicates are ordinary instances and nothing reads
        # identity across slots; a Legend that *did* something would be the worse trade.
        "legends": _filler_deck(legends, 3, 2),
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

    # The card's own condition first, then any hand-written override on top — so data/sandbox.json
    # can correct or extend a table entry rather than having to restate it.
    cond = CONDITIONS.get(card_id)
    if cond:
        _apply_condition(spec, cond, reg, card_id)
    patch = (overrides or {}).get(card_id)
    if patch:
        _apply_patch(spec, patch)
    _ensure_cost_match(spec, reg, card_id)
    return spec


def _ensure_cost_match(spec: dict, reg: Registry, card_id: str) -> None:
    """Guarantee a card in hand whose cost equals one of your Gig values.

    Several cards pay off that coincidence — "you may discard 1 with cost equal to that Gig's
    value", "if the card's cost equals the value of a friendly Gig" — and on a board where it does
    not hold, that half of the card cannot be reached at all. It was holding only by luck, and only
    for the Gig sets that happen to overlap the filler's costs.

    Applied last, after the conditions and any override, because those are what finally decide the
    Gig values it has to match.
    """
    mine = spec["sides"][0]
    values = {g[1] for g in mine["gig"]}
    have = set()
    for c in mine["hand"]:
        cid = c if isinstance(c, str) else c[0]
        if cid == card_id:
            continue          # the card under test is the one you are here to PLAY, not to discard
        cost = reg.get(cid).cost
        if cost is not None:
            have.add(cost)
    if values & have:
        return
    match = next((d.id for d in reg.defs
                  if d.cost in values and d.id != card_id and _is_inert(d, True)
                  and d.type is not CardType.LEGEND), None)
    if match:
        mine["hand"] = list(mine["hand"]) + [match]


#: Keys in an override entry that describe the entry rather than the board, and so are never
#: copied into the spec. ``why`` quotes the clause of the card the board exists to reach, and
#: ``expect`` is the assertion tests/web/test_sandbox.py checks once the card is in play — the
#: difference between a board that was *meant* to satisfy a condition and one that is known to.
META_KEYS = ("why", "expect")


def _apply_patch(spec: dict, patch: dict) -> None:
    """Merge one ``data/sandbox.json`` entry into a generated spec.

    Top-level keys replace; ``sides`` merges per side, one level deep, so an entry names only what
    it changes. ``gigs: [mine, rival]`` is sugar for the thing almost every condition turns on —
    a Gig count, and usually a Gig *difference* — because writing it out as die/value pairs is
    where a hand-tuned board gets quietly wrong.
    """
    for key, value in patch.items():
        if key in META_KEYS:
            continue
        if key == "gigs":
            for p, n in enumerate(value):
                spec["sides"][p]["gig"] = [list(g) for g in _gigs(n)]
                spec["sides"][p]["fixer"] = list(_fixer(n))
        elif key == "sides":
            for p, side_patch in enumerate(value):
                if side_patch:
                    spec["sides"][p].update(side_patch)
        else:
            spec[key] = value


def _gigs(n: int) -> list[list[int]]:
    """``n`` Gigs taken off the front of the standard six dice, each showing a plausible face.

    Values matter: Street Cred is their sum, so a card that compares Street Cred rather than Gig
    count reads these numbers, not the length of the list.
    """
    faces = {4: 4, 6: 5, 8: 7, 10: 8, 12: 10, 20: 15}
    return [[d, faces[d]] for d in DICE[:max(0, min(n, len(DICE)))]]


def _fixer(n: int) -> tuple[int, ...]:
    """The dice still unrolled once ``n`` of the six are Gigs."""
    return DICE[max(0, min(n, len(DICE))):]


def load_overrides(path: str | Path) -> dict:
    """``data/sandbox.json`` if it exists, else no overrides. Missing is the normal case."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- conditions
# Half the pool does something only when the board says so — "if a Rival controls at least 2 more
# Gigs than you", "if you control a min Gig", "for each friendly face-up Legend", "if your ★
# differs from a Rival's by 10+". On the generic board every one of those reads false, so the
# interesting half of 72 of the 151 cards was unreachable: Adrenaline Converter's whole text is a
# conditional, and on a 3-Gig-each board it is a vanilla piece of Gear.
#
# So each of those cards names the board it needs. The knobs below are written against the engine's
# own definitions, which are not guessable from the card text:
#   min Gig     a die showing 1              (EffectCtx.min_gigs)
#   max Gig     a die showing its own max    (EffectCtx.max_gigs)
#   value-pair  two dice sharing a value     (EffectCtx.value_pairs)
#   ★           the SUM of your Gig values   (GameState.street_cred)
# A card whose condition the *default* board already satisfies is deliberately absent: the default
# three Gigs are d4=4, d6=5, d8=7, which is ★ 16 (even, under 20), holds a max Gig, holds both an
# even and an odd value, and has three distinct values.

#: Gig layouts, as (mine, rival). Values matter as much as counts: ★ is their sum.
GIG_SETS = {
    # A Rival Gig lead of 3 — enough for both "more Gigs than you" and "at least 2 more".
    "rival_gig_lead": ([[4, 4], [6, 5]], [[4, 4], [6, 5], [8, 7], [10, 8], [12, 10]]),
    # ★ 18 against ★ 6: "more ★ than a Rival", and a difference of 12 for the "10+" cards.
    "more_cred": ([[4, 4], [6, 6], [8, 8]], [[4, 1], [6, 2], [8, 3]]),
    "less_cred": ([[4, 1], [6, 2], [8, 3]], [[4, 4], [6, 6], [8, 8]]),
    "min_gig": ([[4, 1], [6, 5], [8, 7]], [[4, 4], [6, 5], [8, 7]]),      # a d4 showing 1
    "value_pair": ([[4, 4], [6, 4], [8, 7]], [[4, 4], [6, 5], [8, 7]]),   # two dice showing 4
    "high_gig": ([[4, 4], [6, 5], [8, 8]], [[4, 4], [6, 5], [8, 7]]),     # a Gig with 8+ value
    # Two of them, for the cards that ask for "2 or more Gigs with 8+ value".
    "high_gigs2": ([[4, 4], [8, 8], [10, 9], [12, 11]], [[4, 4], [6, 5], [8, 7]]),
    # Every die rolled: the fixer area is empty AND a d20 is among your Gigs. Six Gigs is one short
    # of the seven that win, so this is still a position and not a victory screen.
    "all_rolled": ([[4, 4], [6, 5], [8, 7], [10, 8], [12, 10], [20, 15]], [[4, 4], [6, 5], [8, 7]]),
    # Gigs low enough that "decrease by up to 2" can reach 1 and make a min Gig.
    "reducible": ([[4, 3], [6, 5], [8, 7]], [[4, 4], [6, 5], [8, 7]]),
    # Values sitting on the cheap end, where most Gear costs live, for the cards that ask whether a
    # card's cost equals the value of one of your Gigs. The default 4/5/7 can only ever match the
    # handful of expensive Gear.
    "cheap_values": ([[4, 2], [6, 3], [8, 1]], [[4, 4], [6, 5], [8, 7]]),
}


def _pick(reg: Registry, n: int = 1, **want) -> list[str]:
    """The first ``n`` card ids matching every constraint, in registry order.

    By rule rather than by a hard-coded list, so the table below keeps working when the pool moves:
    a card that gains a tag becomes eligible, one that loses it drops out, and nothing silently
    points at an id that no longer exists.
    """
    out = []
    for d in reg.defs:
        if "type" in want and d.type is not want["type"]:
            continue
        if "tag" in want and not (set(want["tag"]) & d.tags if isinstance(want["tag"], (list, tuple, set))
                                  else want["tag"] in d.tags):
            continue
        if "kw" in want and want["kw"] not in d.keywords:
            continue
        if "maxcost" in want and (d.cost is None or d.cost > want["maxcost"]):
            continue
        if "maxpower" in want and (d.power is None or d.power > want["maxpower"]):
            continue
        if want.get("scriptless") and d.script is not None:
            continue
        out.append(d.id)
        if len(out) >= n:
            break
    return out


def _apply_condition(spec: dict, cond: dict, reg: Registry, card_id: str) -> None:
    """Shape the board so one card's printed condition reads true."""
    mine, rival = spec["sides"]

    if "gigs" in cond:
        m, r = GIG_SETS[cond["gigs"]]
        mine["gig"], rival["gig"] = [list(g) for g in m], [list(g) for g in r]
        mine["fixer"] = [d for d in DICE if d not in {g[0] for g in m}]
        rival["fixer"] = [d for d in DICE if d not in {g[0] for g in r}]

    if cond.get("legends_faceup"):
        # "all friendly Legends are face-up", "for each friendly face-up Legend". This is the one
        # knob that can cost you a move rather than grant one: with nothing face-down there is no
        # Call to make. That is the right trade for a card whose text asks for exactly that, but it
        # would silently destroy a *Legend*'s sandbox, whose only route into play is being Called —
        # so the card under test is never flipped by it.
        if reg.get(card_id).type is not CardType.LEGEND:
            mine["legends"] = [[c if isinstance(c, str) else c[0], {"faceup": True}]
                               for c in mine["legends"]]

    if "equip" in cond:
        # Gear on your own board, for the cards that count it, move it, or defeat it. The Gear is
        # picked cheap and scriptless where possible so it adds a count and not a second effect.
        gear = _pick(reg, 1, type=CardType.GEAR, maxcost=3)
        if gear:
            hosts = list(mine["field"])
            for k in range(min(cond["equip"], len(hosts))):
                host = hosts[k] if isinstance(hosts[k], str) else hosts[k][0]
                opts = dict(hosts[k][1]) if not isinstance(hosts[k], str) else {}
                opts["gear"] = list(opts.get("gear", ())) + gear
                hosts[k] = [host, opts]
            mine["field"] = hosts

    if "my_tag" in cond:
        mine["field"] = list(mine["field"]) + _pick(reg, 1, type=CardType.UNIT, tag=cond["my_tag"])

    if "rival_tag" in cond:
        # Spent, because a ready rival Unit is not a legal attack target (CR 9.3.2) and most cards
        # that ask about a rival Unit's tag are asking while doing something to it.
        got = _pick(reg, 1, type=CardType.UNIT, tag=cond["rival_tag"])
        rival["field"] = list(rival["field"]) + [[g, {"spent": True}] for g in got]

    if "weak_rival" in cond:
        # "Defeat a rival Unit with power 4 or less" and its family. The default rival board is two
        # big Units, so every one of those clauses fizzled for want of a legal target.
        got = _pick(reg, 2, type=CardType.UNIT, maxpower=cond["weak_rival"])
        rival["field"] = list(rival["field"]) + [[g, {"spent": True}] for g in got]

    if "rival_units" in cond:
        got = _pick(reg, cond["rival_units"], type=CardType.UNIT, scriptless=True)
        rival["field"] = list(rival["field"]) + [[g, {"spent": True}] for g in got]

    if "trash_units" in cond:
        # "-1 €$ for each Unit in your trash", "play up to 2 Units with cost 3 or less from your
        # trash": cheap ones, so both the counting and the replaying clauses have material.
        mine["trash"] = list(mine["trash"]) + _pick(reg, cond["trash_units"], type=CardType.UNIT, maxcost=3)

    if "hand_programs" in cond:
        mine["hand"] = list(mine["hand"]) + _pick(reg, cond["hand_programs"], type=CardType.PROGRAM, maxcost=3)

    if cond.get("hand_gear"):
        # A Gear you can equip *after* playing the card. Swordwise Huscle is printed at power 3 and
        # asks whether it has power 5+, so it cannot meet its own condition off the board alone —
        # pre-equipping is no help either, since the card under test starts in hand.
        mine["hand"] = list(mine["hand"]) + _pick(reg, 1, type=CardType.GEAR, maxcost=3)

    if "hand_tag" in cond:
        mine["hand"] = list(mine["hand"]) + _pick(reg, 1, tag=cond["hand_tag"])

    if "trash_programs" in cond:
        mine["trash"] = list(mine["trash"]) + _pick(reg, cond["trash_programs"], type=CardType.PROGRAM, maxcost=3)

    if "blocker" in cond:
        # A Unit that already has BLOCKER, for the cards that read one rather than grant one.
        # The rival's is left READY on purpose: "can attack ready Units with BLOCKER" is precisely
        # a permission to attack something you otherwise could not, so a spent one proves nothing.
        got = _pick(reg, 1, type=CardType.UNIT, kw=Keyword.BLOCKER)
        if got:
            side = mine if cond["blocker"] == "mine" else rival
            side["field"] = list(side["field"]) + got

    if "trash_tag" in cond:
        mine["trash"] = list(mine["trash"]) + _pick(reg, 1, tag=cond["trash_tag"])

    if cond.get("equip_cost_matches_gig"):
        # "Defeat a Gear. If its cost equals the value of a friendly Gig, draw 1." The Gear has to
        # be on the board AND priced at one of your Gig values, or the second half never fires.
        values = {g[1] for g in mine["gig"]}
        gear = next((d2.id for d2 in reg.defs
                     if d2.type is CardType.GEAR and d2.cost in values and _is_inert(d2, True)), None)
        if gear:
            host = mine["field"][0]
            hid = host if isinstance(host, str) else host[0]
            opts = {} if isinstance(host, str) else dict(host[1])
            opts["gear"] = list(opts.get("gear", ())) + [gear]
            mine["field"] = [[hid, opts]] + list(mine["field"][1:])

    if cond.get("facedown_go_solo"):
        # Arasaka Emergency Radioport looks at a friendly *face-down* Legend and asks whether it is
        # ARASAKA or has GO SOLO. Which Legend is face-down is otherwise just where the rotation
        # landed, so the one card that reads its identity says so instead of hoping.
        got = _pick(reg, 1, type=CardType.LEGEND, kw=Keyword.GO_SOLO)
        if got and got[0] != card_id:
            mine["legends"] = [got[0]] + list(mine["legends"][1:])

    if cond.get("rival_solo_legend"):
        # A Legend standing on the field as a Unit, for "while fighting a Legend". A GO SOLO Legend
        # is the only way one is ever there, so the board puts it there directly.
        got = _pick(reg, 1, type=CardType.LEGEND, kw=Keyword.GO_SOLO)
        rival["field"] = list(rival["field"]) + [[g, {"spent": True, "faceup": True}] for g in got]


#: card id -> the board its printed condition needs, and the clause that asked for it.
#: Cards whose condition the default board already satisfies are absent on purpose; the module
#: docstring above lists what the default already gives (★ 16, a max Gig, an even and an odd value,
#: three distinct values, a face-down GO SOLO Legend).
CONDITIONS = {
    # --- a Rival Gig lead -------------------------------------------------
    "adrenaline-converter":   {"gigs": "rival_gig_lead", "why": "at least 2 more Gigs than you -> ADRENALINE"},
    "nadia-fighting-through-grief": {"gigs": "rival_gig_lead", "why": "more Gigs than you -> can attack their Gig area"},
    "we-gotta-live-together": {"gigs": "rival_gig_lead", "trash_units": 2, "why": "2 more Gigs -> costs 3; Units in trash to replay"},
    "bonnie-and-clyde":       {"gigs": "rival_gig_lead", "weak_rival": 4, "why": "2 more Gigs -> defeat 2; targets with power 4 or less"},

    # --- Street Cred ------------------------------------------------------
    "evelyn-parker-scheming-siren": {"gigs": "more_cred", "why": "more ★ than a Rival -> discard"},
    "minotaur":               {"gigs": "more_cred", "weak_rival": 5, "why": "more ★ -> defeat a Unit with power 5 or less"},
    "valentino-guerrera":     {"gigs": "more_cred", "why": "more ★ -> can attack ready BLOCKERs"},
    "royce-dont-call-me-simon": {"gigs": "more_cred", "weak_rival": 3, "why": "more ★ -> the power 3 branch"},
    "dexter-deshawn-one-last-chance": {"gigs": "more_cred", "why": "★ differs by 10+ (18 against 6) -> draw 2"},
    "gunpoint-diplomacy":     {"gigs": "less_cred", "why": "less ★ -> the Rival chooses the effect for you"},
    "mtod12-flathead":        {"gigs": "less_cred", "why": "less ★ -> this Unit can't be blocked"},
    "towerfall":              {"gigs": "less_cred", "weak_rival": 5,
                               "why": "less ★ -> choose both; rival Units that -5 power can zero"},

    # --- Gig shapes -------------------------------------------------------
    "chrome-reverie":         {"gigs": "min_gig", "why": "control a min Gig -> Call a Legend for free"},
    "three-mouths-one-desire": {"gigs": "min_gig", "why": "one more card for each friendly min Gig"},
    # "Bottom-deck a rival Unit with power 0" — and nothing in the pool is *printed* at power 0.
    # It gets there because the card's other half gives -4 power first, which is exactly why both
    # halves have to be choosable: the board needs a rival Unit that -4 can actually reduce to 0.
    "pyramid-song":           {"gigs": "min_gig", "weak_rival": 4,
                               "why": "a friendly d4 is a min Gig -> choose both; a rival Unit -4 can zero"},
    "alt-cunningham-soulkiller-architect": {"gigs": "min_gig", "trash_programs": 2,
                                            "why": "-1 €$ per min Gig; a Program in the trash to play"},
    "jackie-welles-pour-one-out-for-me": {"gigs": "reducible", "why": "a d4 at 3 can be decreased to 1 and become a min Gig"},
    "goro-takemura-vengeful-bodyguard": {"gigs": "value_pair", "why": "control a value-pair -> also +1 power"},
    "hanako-arasaka-daughter-of-the-emperor": {"gigs": "value_pair", "why": "draw for each friendly value-pair"},
    "pepe-najarro-working-doubles": {"gigs": "value_pair", "why": "control a value-pair -> ready 2 MERC Legends"},
    "sandayu-oda-hanakos-guardian": {"gigs": "value_pair", "why": "spend a rival Unit for each friendly value-pair"},
    "industrial-assembly":    {"gigs": "high_gig", "why": "control a Gig with 8+ value -> draw 1"},
    "carnage-at-the-colosseum": {"gigs": "high_gig", "why": "-1 €$ for each Gig with 8+ value"},
    "octant":                 {"gigs": "high_gig", "why": "-1 €$ for each Gig with 8+ value"},
    "kerry-eurodyne-the-last-rockerboy": {"gigs": "high_gig", "why": "a Gig with 8+ value -> draw 2"},
    "johnny-silverhand-rocking-renegade": {"gigs": "high_gig", "my_tag": "ROCKER",
                                           "why": "-1 €$ per 8+ Gig, and a ROCKER Unit for the +2"},
    "over-the-edge":          {"gigs": "all_rolled", "why": "needs a friendly d20 among your Gigs"},
    "nocturne-op55n1":        {"gigs": "all_rolled", "why": "fixer area empty -> plays for 1 €$"},

    # --- Legends face-up --------------------------------------------------
    "goro-takemura-losing-his-way": {"legends_faceup": True, "why": "all friendly Legends face-up -> +5 power"},
    "panam-palmer-strength-through-family": {"legends_faceup": True, "why": "draw for each friendly face-up Legend"},
    "synapse-burnout":        {"legends_faceup": True, "why": "+1 power for each friendly face-up Legend"},
    "zetatech-berserk":       {"legends_faceup": True, "why": "-1 €$ for each friendly face-up Legend"},

    # --- Gear already on the board ---------------------------------------
    "cyberpsychosis":         {"equip": 2, "why": "+3 power for each equipped Gear on the Unit"},
    "dum-dum-maelstrom-triggerman": {"equip": 2, "why": "defeat a friendly Gear; +1 power per equipped Gear"},
    "gilded-maton":           {"equip": 1, "weak_rival": 3, "why": "defeat a friendly Gear -> defeat a rival Unit cost 3 or less"},
    "alt-cunningham-mother-of-daemons": {"equip": 2, "why": "draw when a friendly equipped Unit or Legend is spent"},
    "panam-palmer-nomad-cavalry": {"equip": 2, "why": "move Gear off this Legend; count equipped Units"},
    "royce-psycho-on-the-edge": {"equip": 2, "why": "+2 power for each Gear equipped to this Legend"},
    "deadman-transmitter":    {"weak_rival": 4, "why": "needs a fight it can replace the defeat in"},

    # --- cards in hand or trash ------------------------------------------
    "maman-brigitte-spirit-of-death": {"hand_programs": 2, "why": "discard 2 Programs -> bottom-deck a rival Unit"},
    "placide-voodoo-sentinel": {"hand_programs": 1, "why": "discard 1 Program -> bottom-deck a rival Unit"},
    "judy-alvarez-braindance-maestro": {"hand_tag": "BRAINDANCE", "why": "a BRAINDANCE Program to play"},
    "trauma-team-operatives": {"trash_units": 3, "why": "-1 €$ for each Unit in your trash"},

    # --- specific rival boards -------------------------------------------
    "maxtac-heavy":           {"rival_units": 3, "why": "-1 €$ for each of a Rival's Units"},
    "caliber-totentanzs-top-dog": {"weak_rival": 2, "why": "defeat a rival Unit with cost 2 or less"},
    "take-control":           {"rival_tag": ["AI", "DRONE", "VEHICLE"], "why": "that Unit is an AI/DRONE/VEHICLE -> draw 1"},
    "meredith-stout-stone-cold-corpo": {"rival_solo_legend": True, "why": "+2 power while fighting a Legend"},
    "les-elemens":            {"weak_rival": 3, "why": "a genuinely lowest-power rival Unit to choose"},
    "unlikely-bond":          {"weak_rival": 3, "why": "a spent rival Unit to bottom-deck alongside yours"},
    "saburo-arasaka-stubborn-patriarch": {"my_tag": "ARASAKA", "why": "friendly ARASAKA Units get +1 while attacking"},
    "yorinobu-arasaka-embracing-destruction": {"my_tag": "ARASAKA", "why": "a friendly ARASAKA Unit to attack; ★ 16 is under 20"},
    "overwatch-panams-gift":  {"weak_rival": 3, "why": "a spent rival Unit cheap enough for the discard to reach"},
    "arasaka-emergency-radioport": {"facedown_go_solo": True,
                               "why": "the face-down Legend it looks at has GO SOLO -> Call it for free"},
    "goro-takemura-vengeful-bodyguard": {"gigs": "value_pair", "blocker": "mine",
                               "why": "a value-pair for the +1, and a friendly BLOCKER for the discard trigger"},
    "valentino-guerrera":     {"gigs": "more_cred", "blocker": "rival",
                               "why": "more ★, and a READY rival BLOCKER that permission lets you attack"},
    "river-ward-detective-on-the-hunt": {"equip": 1, "hand_gear": True,
                               "why": "an equipped friendly Unit to be defeated; a cheap Gear in hand for the ⊡"},
    "modded-muramasa":        {"gigs": "less_cred", "why": "less ★ than a Rival -> ready this Unit at end of turn"},
    "v-roamer-of-the-badlands": {"gigs": "high_gigs2", "why": "2 or more Gigs with 8+ value -> draw 1"},
    "v-streetkid":            {"trash_tag": "BRAINDANCE", "why": "a BRAINDANCE Program in the trash for CALL to retrieve"},
    "heywood-ripperdoc":      {"equip_cost_matches_gig": True,
                               "why": "a Gear on the board priced at one of your Gig values -> draw 1"},
    "the-heist":              {"gigs": "cheap_values", "why": "Gig values 1-3, where Gear costs are, so the free-play clause can fire"},
    "swordwise-huscle":       {"hand_gear": True, "why": "printed power 3 needs Gear to reach the power 5+ clause"},
    "westbrook-netrunner":    {"rival_solo_legend": True, "why": "a rival Legend on the field for its steal to be stopped"},
}
