"""Rules conformance, checked once per card over the whole real pool.

Forty-four rules tests existed before this file and all but a handful ran on a thirteen-card toy
registry. That registry is the right tool for pinning a rule — its cards are simple enough that a
failure can only mean the rule broke — but it says nothing about the 151 cards the lab actually
plays with. A rule that holds for ``T-U4`` and quietly fails for one printed Unit out of sixty is
invisible to every test in the repository, and every measurement the project has produced sits on
top of that.

So these are the same rules, asserted per card across the pool. Each is one property that must hold
for **every** card of a kind, which makes each test a statement with a real denominator instead of
an example. Where a rule has a documented exception, the exception is named here rather than
excluded silently.
"""
import re

import pytest
from conftest import Side, board, do, find

from cptcg.core.actions import Attack, CallLegend, GoSolo, Play, Sell
from cptcg.core.enums import NO_INST, CardType, Keyword, Zone
from cptcg.core.ops import available, play_cost

#: Enough Eddies to buy anything in the set, and a host for any Gear.
RICH = 9
HOST = "psycho-squad"


def _to_menu(s, limit=60):
    """Answer whatever the card asks until the main menu comes back, or the game ends.

    Playing a card is not one action. Many cards open a prompt as they resolve, so reading
    ``s.pending.options`` straight after the Play reads that prompt — or ``None``, if the card
    ended the game. Every intervening question is answered with its **last** option, which is the
    decline where one exists, so these tests measure the rule rather than a card's side effects.
    """
    from cptcg.core.actions import ChoiceKind
    from cptcg.core.engine import apply, legal_actions
    n = 0
    while not s.over and s.pending is not None and n < limit:
        if s.pending.kind is ChoiceKind.MAIN and s.pending.player == 0:
            return s.pending
        opts = legal_actions(s)
        if not opts:
            return None
        apply(s, len(opts) - 1)
        n += 1
    return None


def _units(pool):
    return [d for d in pool.defs if d.type is CardType.UNIT]


def _legends(pool):
    return [d for d in pool.defs if d.type is CardType.LEGEND]


#: A card whose own text grants *itself* attacking the turn it is played, without carrying
#: ADRENALINE. "This Unit" is load-bearing: Valentino — Street Racer carries the same sentence as
#: reminder text for the ADRENALINE it hands to somebody else, and a looser pattern reads that
#: parenthetical as a claim about Valentino. Finding the exception by reading the text rather than
#: by listing ids is the point — a third such card would be caught the day it is printed.
_PRINTS_HASTE = re.compile(r"this Unit can attack[^.]*the turn it'?s played", re.I)


def test_every_unit_enters_lagged_and_cannot_attack_the_turn_it_is_played(pool):
    """CR: a Unit enters Lagged. ADRENALINE grants *attacking*, not freedom from Lag — so the
    keyword is one exception, and a card whose own text says so is the other.

    Both text exceptions were found by this test rather than assumed by it. Nadia — Fighting
    Through Grief reads "If a Rival controls more Gigs than you, this Unit can attack their Gig
    area the turn it's played", and Sandayu Oda — Hanako's Guardian reads "This Unit can attack
    rival Units the turn it's played"; neither carries a keyword. Card text outranks the general
    rule, so both are correct and the first version of this test was simply incomplete. Reading
    the exception off the printed text is the difference between a rule with two names hard-coded
    into it and a rule that still works on the next set.
    """
    wrong, by_text = [], []
    for d in _units(pool):
        # The rival's Unit is **spent**: a ready Unit is not a legal attack target at all, so a
        # board with a ready one would report "cannot attack" for every card here and the test
        # would pass by measuring nothing. The rival holds the only Gig, which is also what makes
        # Nadia's condition true.
        s = board(pool, Side(hand=[d.id], eddies=RICH),
                  Side(gig=[(4, 1)], field=[(HOST, {"spent": True})]))
        inst = find(s, d.id, Zone.HAND, player=0)
        if Play(inst) not in s.pending.options:
            continue                                   # unaffordable or illegal here; not this rule
        do(s, Play(inst))
        menu = _to_menu(s)
        if menu is None or s.i_zone[inst] != Zone.FIELD:
            continue                # the Unit left play on arrival, or the card ended the game
        can = Attack(inst) in menu.options
        adrenaline = Keyword.ADRENALINE in d.keywords
        printed = bool(_PRINTS_HASTE.search(d.text or ""))
        if printed and not adrenaline:
            by_text.append(d.id)
        if can != (adrenaline or printed):
            wrong.append(f"{d.id}: attack-on-arrival {can}, ADRENALINE {adrenaline}, "
                         f"text grants it {printed}")
    assert not wrong, "Lag on entry is not what the card says:\n  " + "\n  ".join(wrong)
    assert sorted(by_text) == ["nadia-fighting-through-grief", "sandayu-oda-hanakos-guardian"], \
        f"the set of cards that beat Lag by text alone changed: {sorted(by_text)}"


def test_every_sellable_card_is_worth_exactly_one_eddie_once_per_turn(pool):
    """A sale is worth one Eddie whatever the card cost, and there is one sale per turn."""
    wrong = []
    for d in pool.defs:
        if d.type is CardType.LEGEND:
            continue
        s = board(pool, Side(hand=[d.id, "floor-it"]), Side())
        inst = find(s, d.id, Zone.HAND, player=0)
        offered = Sell(inst) in s.pending.options
        if offered != d.sell_tag:
            wrong.append(f"{d.id}: Sell offered {offered}, sell_tag {d.sell_tag}")
            continue
        if not offered:
            continue
        do(s, Sell(inst))
        if available(s, 0) != 1:
            wrong.append(f"{d.id}: sold for {available(s, 0)} Eddies, not 1")
        menu = _to_menu(s)
        if menu is not None and any(isinstance(a, Sell) for a in menu.options):
            wrong.append(f"{d.id}: a second Sell was offered in the same turn")
    assert not wrong, "selling is not one Eddie once a turn:\n  " + "\n  ".join(wrong)


def test_every_card_costs_what_it_prints_when_nothing_modifies_it(pool):
    """On an empty board with no cost modifiers in play, ``play_cost`` is the printed number.

    Worth checking per card because cost modifiers are a static-effect family and a script that
    registers one unconditionally would make its own card cheaper for ever, which no example-based
    test would notice.
    """
    wrong = []
    for d in pool.defs:
        if d.type is CardType.LEGEND or d.cost is None:
            continue
        s = board(pool, Side(hand=[d.id], eddies=RICH), Side())
        inst = find(s, d.id, Zone.HAND, player=0)
        got = play_cost(s, 0, inst)
        if got != d.cost:
            wrong.append(f"{d.id}: play_cost {got}, printed {d.cost}")
    assert not wrong, "printed cost is not the cost:\n  " + "\n  ".join(wrong)


def test_calling_any_legend_costs_one_eddie_and_happens_once_a_turn(pool):
    """Every Legend, not one of them. The Call price is a rule, not a card."""
    wrong = []
    for d in _legends(pool):
        others = [x.id for x in _legends(pool) if x.name != d.name][:2]
        s = board(pool, Side(legends=[d.id] + others, eddies=RICH), Side(gig=[(4, 1)]))
        inst = find(s, d.id, Zone.LEGENDS, player=0)
        if CallLegend(inst) not in s.pending.options:
            wrong.append(f"{d.id}: cannot be Called with {RICH} Eddies on an empty board")
            continue
        before = available(s, 0)
        do(s, CallLegend(inst))
        # Some Legends spend Eddies of their own as they arrive; the floor is that the Call itself
        # cost one, so anything cheaper than that is the rule being broken.
        if available(s, 0) > before - 1:
            wrong.append(f"{d.id}: Call left {available(s, 0)} of {before} Eddies")
        menu = _to_menu(s)
        if menu is not None and any(isinstance(a, CallLegend) for a in menu.options):
            wrong.append(f"{d.id}: a second Call was offered in the same turn")
    assert not wrong, "Calling is not one Eddie once a turn:\n  " + "\n  ".join(wrong)


def test_go_solo_is_offered_exactly_to_the_legends_that_print_it(pool):
    """GO SOLO needs the keyword *and* a printed cost; a Legend with neither must never offer it."""
    wrong = []
    for d in _legends(pool):
        others = [x.id for x in _legends(pool) if x.name != d.name][:2]
        s = board(pool, Side(legends=[(d.id, {"faceup": True})] + others, eddies=RICH),
                  Side(gig=[(4, 1)]))
        inst = find(s, d.id, Zone.LEGENDS, player=0)
        offered = GoSolo(inst) in s.pending.options
        printed = Keyword.GO_SOLO in d.keywords and d.cost is not None
        if offered != printed:
            wrong.append(f"{d.id}: GO SOLO offered {offered}, printed {printed} (cost {d.cost})")
    assert not wrong, "GO SOLO is offered off the card text:\n  " + "\n  ".join(wrong)


def test_every_gear_needs_a_host_and_lands_on_the_one_it_was_given(pool):
    """Gear is the only type that cannot be played on its own, and the engine raises if it tries."""
    wrong = []
    for d in pool.defs:
        if d.type is not CardType.GEAR:
            continue
        s = board(pool, Side(hand=[d.id], eddies=RICH, field=[HOST]), Side(gig=[(4, 1)]))
        inst = find(s, d.id, Zone.HAND, player=0)
        host = find(s, HOST, Zone.FIELD, player=0)
        if Play(inst, host) not in s.pending.options:
            continue
        assert Play(inst, NO_INST) not in s.pending.options, f"{d.id}: offered a hostless Play"
        do(s, Play(inst, host))
        _to_menu(s)
        if s.i_zone[inst] == Zone.FIELD and s.i_host[inst] != host:
            wrong.append(f"{d.id}: equipped to {s.i_host[inst]}, not the chosen host {host}")
    assert not wrong, "Gear did not land on its host:\n  " + "\n  ".join(wrong)
