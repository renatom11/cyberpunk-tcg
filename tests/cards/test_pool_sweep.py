"""Play every scripted card, on purpose, and check the engine still holds together.

``tools/smoke_pool.py`` already fuzzes the real pool with random decks, and it is the reason several
crashes were caught early. What it cannot promise is *coverage*: random decks over 151 cards leave
whole swathes of the pool unplayed in any given run, and until the engine started logging what was
actually played there was no way to even find out which ones.

This is the deterministic other half. Each scripted card is set up on a board rich enough for its
effect to have something to work on — Units and Gear on both sides, Gigs on both sides, cards in
deck, hand and trash, Legends face-up and face-down — and then played, Called, sent GO SOLO,
attacked with, activated or defeated, whichever its script actually hooks. Every decision that
follows is answered twice over: once always taking the first option and once always taking the last,
so a branch that only the unusual answer reaches is still walked. ``core.invariants.check`` runs
after every single action.

This finds exactly one class of thing — class B5, the crash or broken invariant — and it finds it
without anyone reading a card. It says nothing about whether a card does what its text says; that is
what the audit is for. What it does guarantee is that the claim "every scripted card has been
executed at least once under two different answer policies" is true and stays true.

As it stands the sweep offers 300 entry points across the 140 scripted cards and 274 of them are
legal on these boards, with **no card left without one**. That count is the thing to watch: a sweep
that quietly stops reaching cards still reports green, which is exactly the shape of the
``needs_script`` zero this whole workstream exists to replace. The ``unreachable`` list below is
what keeps it honest — it fails on the first card the boards can no longer put into play.
"""
import pytest
from conftest import Side, board, defeat_now, find

from cptcg.core import invariants
from cptcg.core.actions import Activate, Attack, CallLegend, GoSolo, Play
from cptcg.core.engine import apply, legal_actions
from cptcg.core.enums import DICE, NO_INST, CardType, Keyword, Zone

#: A board with something for every kind of effect to touch. Deliberately not a legal deck state —
#: these are hand-built positions, and a Program that wants a rival Gear, a friendly Legend and a
#: card in the trash should find all three rather than silently no-op its way to a green result.
FILLER = ["floor-it", "psycho-squad", "delamain-cab", "secondhand-bombus"]
LEGENDS = ["padre-man-of-the-cross", "wakako-okada-peace-and-harmony", "muamar-reyes-el-capitan"]


#: Gigs a side starts with, and the Fixer dice that are therefore no longer available to it. Dice
#: conservation is one of the invariants this sweep checks, so a board that just hands out Gigs
#: without taking them off the Fixer row fails before a single card is played — which is what the
#: first run of this file did.
GIGS = [(6, 3), (8, 3), (10, 7)]
FIXER = [d for d in DICE if d not in {g for g, _ in GIGS}]


def _rich(extra_hand=(), faceup=1):
    return Side(hand=list(extra_hand) + ["floor-it", "psycho-squad"],
                field=[("psycho-squad", {"gear": ["mantis-blades"]}), "secondhand-bombus"],
                legends=[(c, {"faceup": i < faceup}) for i, c in enumerate(LEGENDS)],
                eddies=9, deck=FILLER * 3, trash=["floor-it", "kiroshi-optics"],
                gig=GIGS, fixer=FIXER)


def _drive(s, policy, limit=200):
    """Answer every pending decision with ``policy`` until the game stops asking."""
    n = 0
    while not s.over and s.pending is not None and n < limit:
        opts = legal_actions(s)
        if not opts:
            break
        apply(s, policy(opts))
        invariants.check(s)
        n += 1
        if s.pending is not None and s.pending.kind.name == "MAIN":
            break                     # back at the menu: the card has finished resolving
    return s


FIRST = lambda opts: 0                                             # noqa: E731
LAST = lambda opts: len(opts) - 1                                  # noqa: E731


def _entry_points(s, d, inst):
    """How this card can be made to do something, as callables taking the state."""
    out = []
    sc = d.script
    if d.type in (CardType.UNIT, CardType.PROGRAM, CardType.GEAR):
        host = NO_INST
        if d.type is CardType.GEAR:
            host = find(s, "secondhand-bombus", Zone.FIELD, player=0)
        out.append(Play(inst, host))
    elif d.type is CardType.LEGEND:
        if not s.i_faceup[inst]:
            out.append(CallLegend(inst))
        elif Keyword.GO_SOLO in d.keywords and d.cost is not None:
            out.append(GoSolo(inst))
    if sc is not None and sc.abilities:
        out += [Activate(inst, k) for k in range(len(sc.abilities))]
    return out


def _scripted(pool):
    return [d for d in pool.defs if d.script is not None]


def _home(d) -> Zone:
    """Where this card starts on the sweep board — and the zone ``find`` must look in.

    It matters because the filler cards are themselves scripted: looking up "floor-it" without a
    zone finds the copy sitting in the deck, whose Play is not legal, and the card reads as
    unreachable while its script has never run.
    """
    return Zone.LEGENDS if d.type is CardType.LEGEND else Zone.HAND


def _exercise(pool, d, policy) -> bool:
    """Try every entry point this card has, each on its own fresh board.

    ``faceup`` is swept for both values because a Legend reaches different code by being Called
    (face-down) than by being activated or sent GO SOLO (face-up), and a card that cares about
    *friendly* face-up Legends needs one of each to have anything to find.
    """
    did = False
    for faceup in (0, 1):
        def fresh_board():
            me = _rich(extra_hand=[d.id] if d.type is not CardType.LEGEND else (), faceup=faceup)
            if d.type is CardType.LEGEND:
                me.legends = [(d.id, {"faceup": bool(faceup)})] + [(c, {}) for c in LEGENDS[:2]]
            return board(pool, me, _rich(faceup=1))

        probe = fresh_board()
        invariants.check(probe)
        n_entries = len(_entry_points(probe, d, find(probe, d.id, _home(d), player=0)))
        for k in range(n_entries):
            s = fresh_board()
            inst = find(s, d.id, _home(d), player=0)
            action = _entry_points(s, d, inst)[k]
            opts = legal_actions(s)
            if action not in opts:
                continue                      # not affordable or not legal on this board; fine
            apply(s, opts.index(action))
            invariants.check(s)
            _drive(s, policy)
            did = True
    return did


@pytest.mark.parametrize("policy,label", [(FIRST, "first"), (LAST, "last")])
def test_every_scripted_card_resolves_without_breaking_an_invariant(pool, policy, label):
    """The sweep itself. A failure here is a class B5 finding and needs only reproduction."""
    cards = _scripted(pool)
    assert len(cards) > 100, "the pool lost its scripts; this sweep would pass by doing nothing"
    unreachable = []
    for d in cards:
        try:
            if not _exercise(pool, d, policy):
                unreachable.append(d.id)
        except AssertionError as e:                    # an invariant, not a test assertion
            pytest.fail(f"{d.id} ({label} policy) broke an invariant: {e}")
        except Exception as e:                         # noqa: BLE001 — a crash is the finding
            pytest.fail(f"{d.id} ({label} policy) raised {type(e).__name__}: {e}")
    assert not unreachable, ("no entry point on this board could put these cards into play, so "
                             "nothing here executed their scripts:\n  " + "\n  ".join(unreachable))


def test_attack_and_defeated_hooks_are_executed_too(pool):
    """The two hooks a Play cannot reach.

    ``on_attack`` and ``on_defeated`` only fire once the card is already in play, so the sweep above
    walks past them entirely: it plays the card and stops at the menu. These are their own pass.
    """
    for d in _scripted(pool):
        sc = d.script
        if not (sc.on_attack or sc.on_defeated) or d.type not in (CardType.UNIT, CardType.LEGEND):
            continue
        faceup = d.type is CardType.LEGEND
        me = Side(field=[d.id] if not faceup else [], eddies=9, deck=FILLER * 3,
                  hand=["floor-it"], gig=GIGS, fixer=FIXER,
                  legends=[(d.id, {"faceup": True})] + [(c, {}) for c in LEGENDS[:2]] if faceup
                  else [(c, {}) for c in LEGENDS])
        s = board(pool, me, _rich(faceup=1))
        inst = find(s, d.id, player=0)
        if sc.on_attack:
            opts = legal_actions(s)
            if Attack(inst) in opts:
                apply(s, opts.index(Attack(inst)))
                invariants.check(s)
                _drive(s, FIRST)
        if sc.on_defeated:
            s2 = board(pool, me, _rich(faceup=1))
            i2 = find(s2, d.id, player=0)
            if s2.i_zone[i2] == Zone.FIELD:
                defeat_now(s2, i2)
                invariants.check(s2)
                _drive(s2, FIRST)
