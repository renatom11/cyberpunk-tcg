"""The try-out boards: every card in the pool must be one decision away from being played.

This is the test the sandbox exists for. ``sandbox_spec`` can only be trusted as "tap any card and
play it" if that is checked for *every* card rather than the four somebody happened to try, and the
check is cheap: build the position, read the main menu, look for the card in it.

The second test is the one that keeps a position from being a diorama. A board that offers the card
but cannot survive the turn after it is not a game, and ``build_position`` says nothing about what
happens once ``EndTurnStep`` pops.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cptcg.agents.base import make_agent  # noqa: E402
from cptcg.core.actions import CallLegend, GoSolo, Play  # noqa: E402
from cptcg.core.engine import apply, legal_actions  # noqa: E402
from cptcg.core.enums import CardType, Zone  # noqa: E402
from cptcg.core.legal import main_menu  # noqa: E402
from cptcg.learn.delayed import build_position  # noqa: E402
from cptcg.sim.sandbox import CONDITIONS, load_overrides, sandbox_spec  # noqa: E402

OVERRIDES = load_overrides(ROOT / "data" / "sandbox.json")


def _tried(s, card_id):
    """The instance of the card under test, and the menu options that would put it into play."""
    ids = s.reg.defs
    return [o for o in main_menu(s)
            if isinstance(o, (Play, CallLegend, GoSolo)) and ids[s.i_card[o.inst]].id == card_id]


def test_every_card_in_the_pool_can_be_tried(pool):
    """151 of 151, or the test names the ones that cannot be reached.

    A Legend counts as reachable through ``CallLegend``: it starts face-down, which is the only
    orientation it can be Called from, and GO SOLO needs it face-up — so a GO SOLO Legend is two
    taps away, not one, which is the real sequence rather than a shortcut.
    """
    missed = []
    for d in pool.defs:
        s = build_position(pool, sandbox_spec(pool, d.id, OVERRIDES))
        if not _tried(s, d.id):
            missed.append(f"{d.id} ({d.type.name})")
    assert not missed, f"{len(missed)} cards cannot be played from their sandbox: {missed}"


def test_the_card_under_test_is_the_only_copy_on_the_board(pool):
    """Filler must never be the card being read against it.

    Four cards in the pool *are* the vanilla Units the filler is drawn from, so without the
    exclusion in ``_filler_ids`` those four would deal themselves as their own filler — two
    identical cards in hand and no way to tell which one the button was about.
    """
    wrong = []
    for d in pool.defs:
        side = sandbox_spec(pool, d.id, OVERRIDES)["sides"][0]
        seen = [x if isinstance(x, str) else x[0]
                for key in ("hand", "field", "legends", "deck", "trash")
                for x in side.get(key, ())]
        if seen.count(d.id) != 1:
            wrong.append((d.id, seen.count(d.id)))
    assert not wrong, f"cards appearing other than exactly once on their own board: {wrong}"


@pytest.mark.parametrize("kind", [CardType.UNIT, CardType.PROGRAM, CardType.GEAR, CardType.LEGEND])
def test_a_sandbox_is_a_game_and_not_a_diorama(pool, kind):
    """One card of each type: play the position out and it keeps running.

    ``build_position`` hands back a main phase with an ``EndTurnStep`` under it; the turn loop is
    re-pushed by ``EndTurnCleanupStep``, so a sandbox should play on indefinitely. Turn 9 is six
    turns past the start, which is past every one-turn artefact a hand-built board can have.
    """
    d = next(c for c in pool.defs if c.type is kind)
    s = build_position(pool, sandbox_spec(pool, d.id, OVERRIDES))
    me = make_agent("heuristic", 9)
    me.new_game(9, 0)
    rival = make_agent("heuristic", 7)
    rival.new_game(7, 1)
    guard = 0
    while not s.over and s.pending is not None and s.turn < 9 and guard < 4000:
        legal_actions(s)
        apply(s, (me if s.pending.player == 0 else rival).act(s, s.pending))
        guard += 1
    assert s.turn >= 9 or s.over, f"{d.id}: stalled at turn {s.turn} after {guard} actions"


def test_calling_a_legend_is_never_a_guess(pool):
    """One face-down Legend per sandbox, and for a Legend it is the card under test.

    This is the bug that made the feature useless for Legends on the first build. "Call a Legend"
    names no card — it cannot, since in a real game you do not know which of your face-down Legends
    you are turning over — so three face-down Legends gave three identical buttons and a one-in-
    three chance. Calling is once per turn, so picking wrong did not merely waste a tap: it closed
    the only route to the card for that turn, and the try-out was over before it started.
    """
    wrong = []
    for d in pool.defs:
        s = build_position(pool, sandbox_spec(pool, d.id, OVERRIDES))
        calls = [o for o in main_menu(s) if isinstance(o, CallLegend)]
        if len(calls) > 1:
            wrong.append(f"{d.id}: {len(calls)} Call options, so Calling is a guess")
        elif d.type is CardType.LEGEND:
            # A Legend's own sandbox must always offer its Call: that is the only way in.
            if not calls:
                wrong.append(f"{d.id}: a Legend with no way to Call it")
            elif pool.defs[s.i_card[calls[0].inst]].id != d.id:
                wrong.append(f"{d.id}: the only Call turns over "
                             f"{pool.defs[s.i_card[calls[0].inst]].id}")
    assert not wrong, wrong
    # Zero is legitimate only where the card itself asked for it: the four cards that need every
    # friendly Legend face-up have nothing left to Call, which is the condition working, not a gap.
    none_callable = [d.id for d in pool.defs
                     if not [o for o in main_menu(build_position(
                         pool, sandbox_spec(pool, d.id, OVERRIDES))) if isinstance(o, CallLegend)]]
    assert all(CONDITIONS.get(c, {}).get("legends_faceup") for c in none_callable), none_callable


# What each condition in CONDITIONS is supposed to have produced, expressed against the built
# board rather than against the table that built it. Written from the engine's own definitions —
# min Gig is a die showing 1, a max Gig is a die showing its own maximum, a value-pair is two dice
# sharing a value, and ★ is the sum of the values — because those are exactly the things a table of
# dice literals gets quietly wrong.
CONDITION_CHECKS = {
    "rival_gig_lead": lambda s: len(s.gig[1]) - len(s.gig[0]) >= 2,
    "more_cred": lambda s: s.street_cred(0) - s.street_cred(1) >= 10,
    "less_cred": lambda s: s.street_cred(1) - s.street_cred(0) >= 10,
    "min_gig": lambda s: any(v == 1 for _k, v in s.gig[0]),
    "value_pair": lambda s: len({v for _k, v in s.gig[0]}) < len(s.gig[0]),
    "high_gig": lambda s: any(v >= 8 for _k, v in s.gig[0]),
    "all_rolled": lambda s: not s.fixer[0] and any(k == 20 for k, _v in s.gig[0]),
    "reducible": lambda s: any(k == 4 and 1 < v <= 3 for k, v in s.gig[0]),
    # Every value low enough to be some Gear's cost, which is what "cost equals the value of a
    # friendly Gig" needs in order ever to be true.
    "cheap_values": lambda s: all(v <= 3 for _k, v in s.gig[0]),
}


def test_every_gig_condition_actually_holds_on_its_board(pool):
    """The board a card asked for is the board it got.

    A table of dice literals is the easiest thing in this change to get wrong — a Gig set that no
    longer sums to a 10-point Street Cred gap, or that loses its pair when a value is edited, fails
    silently and the card goes back to being untestable without anything saying so.
    """
    bad = []
    for card_id, cond in CONDITIONS.items():
        name = cond.get("gigs")
        if name is None:
            continue
        s = build_position(pool, sandbox_spec(pool, card_id, OVERRIDES))
        if not CONDITION_CHECKS[name](s):
            bad.append(f"{card_id}: gig set {name!r} does not satisfy {cond['why']!r}")
    assert not bad, bad


def test_board_conditions_put_real_material_on_the_board(pool):
    """The non-Gig knobs produced what they promise: Gear, tagged Units, trash, extra rival Units."""
    bad = []
    for card_id, cond in CONDITIONS.items():
        s = build_position(pool, sandbox_spec(pool, card_id, OVERRIDES))
        mine, rival = 0, 1
        if cond.get("equip"):
            geared = sum(1 for u in s.units(mine)
                         if any(s.i_host[g] == u for g in range(len(s.i_card))))
            if geared < cond["equip"]:
                bad.append(f"{card_id}: wanted {cond['equip']} equipped Units, got {geared}")
        if cond.get("legends_faceup") and not all(s.i_faceup[i] for i in s.legends(mine)):
            bad.append(f"{card_id}: not every friendly Legend is face-up")
        if "weak_rival" in cond and not any((pool.defs[s.i_card[u]].power or 99) <= cond["weak_rival"]
                                            for u in s.units(rival)):
            bad.append(f"{card_id}: no rival Unit with power <= {cond['weak_rival']}")
        if "rival_units" in cond and len(s.units(rival)) < cond["rival_units"]:
            bad.append(f"{card_id}: only {len(s.units(rival))} rival Units")
        if "trash_units" in cond:
            n = sum(1 for i in s.zone(mine, Zone.TRASH) if pool.defs[s.i_card[i]].type is CardType.UNIT)
            if n < cond["trash_units"]:
                bad.append(f"{card_id}: only {n} Units in trash")
        if "hand_programs" in cond:
            n = sum(1 for i in s.zone(mine, Zone.HAND)
                    if pool.defs[s.i_card[i]].type is CardType.PROGRAM)
            if n < cond["hand_programs"]:
                bad.append(f"{card_id}: only {n} Programs in hand")
        if "my_tag" in cond and not any(cond["my_tag"] in pool.defs[s.i_card[u]].tags
                                        for u in s.units(mine)):
            bad.append(f"{card_id}: no friendly {cond['my_tag']} Unit")
        if "rival_tag" in cond and not any(set(cond["rival_tag"]) & pool.defs[s.i_card[u]].tags
                                           for u in s.units(rival)):
            bad.append(f"{card_id}: no rival Unit tagged {cond['rival_tag']}")
    assert not bad, bad


def test_every_condition_says_which_clause_it_is_for(pool):
    """A board with no `why` is a magic number: nobody can later tell what it was reaching for."""
    missing = [c for c, cond in CONDITIONS.items() if not cond.get("why", "").strip()]
    assert not missing, missing
    unknown = [c for c in CONDITIONS if c not in pool.by_id]
    assert not unknown, unknown


def test_overrides_only_name_real_cards(pool):
    """A typo'd id in data/sandbox.json would silently do nothing, which is the worst outcome."""
    unknown = [cid for cid in OVERRIDES if cid not in pool.by_id]
    assert not unknown, f"data/sandbox.json names cards that do not exist: {unknown}"
