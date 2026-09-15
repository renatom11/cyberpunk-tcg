"""Every board requirement a card's printed text names must hold on that card's sandbox.

This is the detector, and it exists because hand-reading 151 cards is how the gaps got there in the
first place. Alt Cunningham — Mother of Daemons has two clauses; the table entry written for her by
hand covered the first ("when a friendly equipped Unit is spent") and silently ignored the second
("discard 1 with cost equal to that Gig's value"), which needs a card in hand priced at one of your
Gig values. Nothing said so. A rule that reads the text and checks the board does.

It is deliberately conservative about what counts as a requirement, because a false positive here
is a board contorted for no reason:

* a card that HAS BLOCKER supplies the BLOCKER its own text talks about;
* "Decrease a Gig ... Then, if you control a min Gig" is an *outcome* the card produces, not a
  precondition — what the board owes it is a Gig low enough to be decreased into one;
* a d20 you *roll* comes out of the fixer area, so it must be unrolled, not already a Gig;
* "unequipped" contains "equipped", and "GO SOLO" contains the tag name SOLO.

Each of those was a real false positive during the first run; the comments are there so the next
person to widen the table does not reintroduce them.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.core.enums import CardType, Keyword, Zone  # noqa: E402
from cptcg.learn.delayed import build_position  # noqa: E402
from cptcg.sim.sandbox import load_overrides, sandbox_spec  # noqa: E402

OVERRIDES = load_overrides(ROOT / "data" / "sandbox.json")


def zone(s, p, z):
    return list(s.zone(p, z))


def cards(s, insts):
    return [s.reg.defs[s.i_card[i]] for i in insts]


def gear_on(s, p):
    hosts = {s.i_host[g] for g in range(len(s.i_card)) if s.i_host[g] != -1}
    return [u for u in (s.units(p) + s.legends(p)) if u in hosts]


def my_gig_values(s):
    return {v for _k, v in s.gig[0]}


REQS = []


def req(pattern, name, check, flags=re.I):
    REQS.append((re.compile(pattern, flags), name, check))


def req(pattern, name, check, flags=re.I):
    REQS.append((re.compile(pattern, flags), name, check))

req(r"(?<!un)equipped (Unit|Legend|Gear)|its equipped|are equipped", "an equipped friendly Unit/Legend",
    lambda s, d: bool(gear_on(s, 0)))
# "a friendly Gig" is any of yours, so one matching card in hand is enough...
req(r"cost equals the value of a friendly Gig",
    "a card in hand whose cost equals one of my Gig values",
    lambda s, d: any((c.cost or -1) in my_gig_values(s) for c in cards(s, zone(s, 0, Zone.HAND))))
# ...but "THAT Gig's value" is a Gig somebody else picked, so the hand has to cover every value it
# could be. Alt Cunningham — Mother of Daemons reads the Gig a rival Unit is stealing; with one
# matching card the offer appeared only if the Rival happened to take that Gig, and the clause
# looked unimplemented on every other steal.
req(r"cost equal to that Gig's value",
    "a card in hand for EVERY Gig value, since someone else chooses which Gig",
    lambda s, d: my_gig_values(s) <= {c.cost for c in cards(s, zone(s, 0, Zone.HAND))})
req(r"\bdiscard\b", "a non-empty hand to discard from",
    lambda s, d: len(zone(s, 0, Zone.HAND)) >= 2)
req(r"discard (1|2|\d) Programs?", "Programs in hand",
    lambda s, d: sum(1 for c in cards(s, zone(s, 0, Zone.HAND)) if c.type is CardType.PROGRAM) >= 1)
req(r"from your trash|in your trash", "cards in my trash",
    lambda s, d: len(zone(s, 0, Zone.TRASH)) >= 1)
req(r"([A-Z]{2,}) Program from your trash", "a Program of the named kind in my trash",
    lambda s, d: any(c.type is CardType.PROGRAM
                     and re.search(r"([A-Z]{2,}) Program from your trash", d.text).group(1) in c.tags
                     for c in cards(s, zone(s, 0, Zone.TRASH))))
req(r"defeat a (friendly )?Gear|a friendly Gear", "a Gear on the board to defeat",
    lambda s, d: bool(gear_on(s, 0)))
req(r"rival Unit with power (\d+) or less", "a rival Unit weak enough",
    lambda s, d: any((c.power or 99) <= int(re.search(r"rival Unit with power (\d+) or less", d.text, re.I).group(1))
                     for c in cards(s, s.units(1))))
req(r"rival Unit with cost (\d+) or less", "a rival Unit cheap enough",
    lambda s, d: any((c.cost or 99) <= int(re.search(r"rival Unit with cost (\d+) or less", d.text, re.I).group(1))
                     for c in cards(s, s.units(1))))
req(r"face-up Legend", "a face-up Legend",
    lambda s, d: any(s.i_faceup[i] for i in s.legends(0) + s.legends(1)))
req(r"face-down Legend", "a face-down friendly Legend",
    lambda s, d: any(not s.i_faceup[i] for i in s.legends(0)))
def _outcome(d, phrase):
    """True when the card creates the state itself: '... Then, if you control X' or '... becomes X'."""
    import re as _re
    return bool(_re.search(rf"(Then, if [^.]*|becomes a ){phrase}", d.text or "", _re.I))

req(r"min Gig", "a friendly min Gig, or a Gig low enough to be decreased into one",
    lambda s, d: any(v == 1 for _k, v in s.gig[0])
    or (_outcome(d, "min Gig") and any(v <= 4 for _k, v in s.gig[0])))
req(r"max Gig", "a friendly max Gig", lambda s, d: any(v == k for k, v in s.gig[0]))
req(r"value-pair", "a friendly value-pair",
    lambda s, d: len(my_gig_values(s)) < len(s.gig[0])
    or (_outcome(d, "a value-pair") and len(s.gig[0]) >= 2))
req(r"(\d+) or more Gigs with 8\+ value", "two or more friendly Gigs with 8+ value",
    lambda s, d: sum(1 for _k, v in s.gig[0] if v >= 8)
    >= int(re.search(r"(\d+) or more Gigs with 8\+ value", d.text, re.I).group(1)))
req(r"8\+ value", "a friendly Gig with 8+ value", lambda s, d: any(v >= 8 for _k, v in s.gig[0]))
req(r"\bd20\b", "a d20 to read — rolled into my Gigs, or still in the fixer to be rolled",
    lambda s, d: any(k == 20 for k, _v in s.gig[0]) or 20 in s.fixer[0])
req(r"more ★ \(Street Cred\) than a Rival|more ★ than a Rival", "more Street Cred than the Rival",
    lambda s, d: s.street_cred(0) > s.street_cred(1))
req(r"less ★ \(Street Cred\) than a Rival|less ★ than a Rival", "less Street Cred than the Rival",
    lambda s, d: s.street_cred(0) < s.street_cred(1))
req(r"spent rival Unit", "a spent rival Unit",
    lambda s, d: any(s.i_spent[u] for u in s.units(1)))
req(r"unequipped (friendly )?Unit|rival unequipped Unit", "an unequipped Unit",
    lambda s, d: any(u not in gear_on(s, 1) for u in s.units(1)))
req(r"fixer area is empty", "an empty fixer area", lambda s, d: not s.fixer[0])
# A card that HAS BLOCKER supplies the BLOCKER its own text talks about, once it is played.
req(r"(with|uses|has) BLOCKER", "a Unit with BLOCKER already on the board",
    lambda s, d: Keyword.BLOCKER in d.keywords
    or any(Keyword.BLOCKER in c.keywords for c in cards(s, s.units(0) + s.units(1))))

TAGS = ["ARASAKA", "MERC", "ROCKER", "NETRUNNER", "BRAINDANCE", "QUICKHACK", "DRONE", "VEHICLE",
        "AI", "SOLO", "NOMAD", "MAELSTROM", "ANIMAL", "VOODOO", "TYGER", "VALENTINO", "MOX", "SCAV"]

ALT_GROUPS = [("AI", "DRONE", "VEHICLE")]

def tag_reqs(s, d):
    out = []
    text = d.text or ""
    for group in ALT_GROUPS:
        if all(re.search(rf"\b{g}\b", text) for g in group):
            on = any(set(group) & c.tags for c in cards(
                s, s.units(0) + s.units(1) + s.legends(0) + s.legends(1) + zone(s, 0, Zone.HAND)))
            if not on:
                out.append("a " + "/".join(group) + " card on the board")
            return out
    for tag in TAGS:
        if any(tag in g for g in ALT_GROUPS):
            continue
        pat = rf"(?<!GO ){tag}\b" if tag == "SOLO" else rf"\b{tag}\b"
        if re.search(pat, d.text or ""):
            on_board = any(tag in c.tags for c in cards(
                s, s.units(0) + s.units(1) + s.legends(0) + s.legends(1) + zone(s, 0, Zone.HAND)))
            if not on_board:
                out.append(f"a {tag} card on the board or in hand")
    return out



# --- deck searches -------------------------------------------------------------------------
# "Search the top 5 cards of your deck. Reveal up to 2 Gears with cost 2 or less" finds nothing in a
# deck of filler Units, and a search that matches nothing is the one case the engine resolves
# without asking — so the card appeared to do nothing at all. The same shape covers "Trash N. Add a
# <type> from among them", which also reads off the top of the deck.
TYPE_WORD = {"Unit": CardType.UNIT, "Gear": CardType.GEAR, "Program": CardType.PROGRAM}
DECK_LOOK = re.compile(
    r"(?:[Ss]earch|[Rr]eveal|[Tt]rash) the top (\d+) cards?|[Tt]rash (\d+)\.|"
    r"(?:[Ss]earch|[Rr]eveal|[Tt]rash) the top card", re.M)


def _looks_at_top(d):
    """How many cards off the top this card sees, and which type it is hunting for (if any)."""
    text = d.text or ""
    m = DECK_LOOK.search(text)
    if not m:
        return None
    n = int(m.group(1) or m.group(2) or 1)
    # Only the clause that says what to take — up to the next sentence end. A wider window reaches
    # into unrelated text: Sketchy Ripper hunts for a Gear, and a 140-character look-ahead ran on
    # into a later sentence containing the word "Unit", so the check passed against the wrong type
    # while the card it was supposed to protect was still broken.
    tail = text[m.end():]
    after = re.split(r"(?<=[.])\s", tail, maxsplit=2)
    after = " ".join(after[:2])
    # ...and the NEAREST type word wins, not whichever happens to come first in the table.
    best = None
    for word, kind in TYPE_WORD.items():
        w = re.search(rf"\b{word}s?\b", after)
        if w and (best is None or w.start() < best[0]):
            best = (w.start(), word, kind)
    if best is None or "BRAINDANCE" in after[:40]:
        return n, None, None
    _at, word, kind = best
    cap = re.search(rf"{word}s? with cost (\d+) or less", after)
    return n, kind, int(cap.group(1)) if cap else None


def test_a_deck_search_finds_something_to_reveal(pool):
    """Whatever a card hunts for off the top of the deck is actually there.

    Without this the card is not merely weaker on the sandbox board — it is untestable, because the
    engine resolves an empty search without a prompt and nothing appears on screen at all.
    """
    from cptcg.core import ops
    bad = []
    for d in pool.defs:
        look = _looks_at_top(d)
        if look is None:
            continue
        n, kind, maxcost = look
        if kind is None:
            continue                       # no filter: anything off the top satisfies it
        s = build_position(pool, sandbox_spec(pool, d.id, OVERRIDES))
        top = [pool.defs[s.i_card[i]] for i in ops.top_cards(s, 0, n)]
        ok = [c for c in top if c.type is kind and (maxcost is None or (c.cost or 99) <= maxcost)]
        if not ok:
            want = kind.name + (f" with cost <= {maxcost}" if maxcost else "")
            bad.append(f"{d.id}: top {n} holds no {want} — the search resolves silently")
    assert not bad, "\n".join(bad)


def test_every_printed_requirement_is_met_on_its_own_sandbox(pool):
    rows = []
    for d in pool.defs:
        s = build_position(pool, sandbox_spec(pool, d.id, OVERRIDES))
        missing = [name for pat, name, check in REQS
                   if pat.search(d.text or "") and not check(s, d)]
        missing += tag_reqs(s, d)
        if missing:
            rows.append(f"{d.id}: " + "; ".join(missing))
    assert not rows, "\n".join(rows)
