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
from cptcg.core.enums import CardType  # noqa: E402
from cptcg.core.legal import main_menu  # noqa: E402
from cptcg.learn.delayed import build_position  # noqa: E402
from cptcg.sim.sandbox import load_overrides, sandbox_spec  # noqa: E402

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
        if len(calls) != 1:
            wrong.append(f"{d.id}: {len(calls)} Call options")
        elif d.type is CardType.LEGEND:
            called = pool.defs[s.i_card[calls[0].inst]].id
            if called != d.id:
                wrong.append(f"{d.id}: the only Call turns over {called}")
    assert not wrong, wrong


def test_overrides_only_name_real_cards(pool):
    """A typo'd id in data/sandbox.json would silently do nothing, which is the worst outcome."""
    unknown = [cid for cid in OVERRIDES if cid not in pool.by_id]
    assert not unknown, f"data/sandbox.json names cards that do not exist: {unknown}"
