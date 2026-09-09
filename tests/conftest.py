import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

from cptcg.cards.registry import Registry  # noqa: E402
from cptcg.deck.decklist import Decklist  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def reg():
    return Registry.from_files(FIXTURES / "cards_test.json")


def red_deck():
    return Decklist.from_counts("red", ["T-L1", "T-L2", "T-L5"], {
        "T-U1": 3, "T-U2": 3, "T-U3": 3, "T-U4": 3, "T-U8": 3, "T-U5": 3,
        "T-G2": 3, "T-U9": 3, "T-P1": 3, "T-U6": 3, "T-G1": 3, "T-U10": 3, "T-P2": 4})


def blue_deck():
    return Decklist.from_counts("blue", ["T-L3", "T-L4", "T-L6"], {
        "T-U6": 3, "T-U7": 3, "T-U10": 3, "T-U1": 3, "T-U2": 3, "T-U3": 3,
        "T-G1": 3, "T-G3": 3, "T-P1": 3, "T-P2": 3, "T-U9": 3, "T-U4": 3, "T-U5": 4})


@pytest.fixture
def decks():
    return (red_deck(), blue_deck())


# ---------------------------------------------------------------- board builder
from cptcg.core.actions import Choice, ChoiceKind  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.core.enums import DICE, NZONE, Zone  # noqa: E402
from cptcg.core.legal import main_menu  # noqa: E402
from cptcg.core.state import GameState  # noqa: E402
from cptcg.core.steps import EndTurnStep  # noqa: E402


class Side:
    """One player's board for ``board()``. Card ids or (id, opts) tuples where opts is a dict
    with any of: spent, lag, faceup, gear=[ids], flags."""

    def __init__(self, hand=(), field=(), legends=(), eddies=0, deck=(), trash=(),
                 gig=(), fixer=None, spent_eddies=0):
        self.hand, self.field, self.legends = hand, field, legends
        self.eddies, self.deck, self.trash = eddies, deck, trash
        self.gig = list(gig)
        self.fixer = list(DICE) if fixer is None else list(fixer)
        self.spent_eddies = spent_eddies


def _place(s, reg, p, spec, zone):
    if isinstance(spec, tuple):
        cid, opts = spec
    else:
        cid, opts = spec, {}
    inst = s.new_instance(reg.get(cid).idx, p, zone)
    s.i_spent[inst] = 1 if opts.get("spent") else 0
    s.i_lag[inst] = 1 if opts.get("lag") else 0
    s.i_faceup[inst] = 1 if opts.get("faceup") else 0
    s.i_flags[inst] = opts.get("flags", 0)
    for gid in opts.get("gear", ()):
        g = s.new_instance(reg.get(gid).idx, p, zone)
        s.i_host[g] = inst
    return inst


def board(reg, p0: Side, p1: Side, active=0, turn=3, cfg=DEFAULT_CONFIG, seed=1,
          turns_taken=None, overtime=False):
    """Hand-build a mid-game state at the start of ``active``'s main phase."""
    s = GameState(cfg, reg, seed)
    s.turn, s.active, s.first_player = turn, active, 0
    s.turns_taken = list(turns_taken) if turns_taken else [turn // 2, turn // 2]
    s.overtime = overtime
    for p, side in ((0, p0), (1, p1)):
        for spec in side.deck:
            _place(s, reg, p, spec, Zone.DECK)
        for spec in side.hand:
            _place(s, reg, p, spec, Zone.HAND)
        for spec in side.field:
            _place(s, reg, p, spec, Zone.FIELD)
        for spec in side.legends:
            _place(s, reg, p, spec, Zone.LEGENDS)
        for spec in side.trash:
            _place(s, reg, p, spec, Zone.TRASH)
        for k in range(side.eddies):
            e = s.new_instance(reg.get("T-P1").idx, p, Zone.EDDIES)
            s.i_spent[e] = 1 if k < side.spent_eddies else 0
        s.gig[p] = list(side.gig)
        s.fixer[p] = list(side.fixer)
    s.stack.append(EndTurnStep())
    s.pending = Choice(ChoiceKind.MAIN, active, tuple(main_menu(s)))
    return s


def find(s, cid, zone=None, player=None):
    """First instance of card id ``cid`` (optionally in a zone / owned by a player)."""
    for inst in range(len(s.i_card)):
        if s.card(inst).id != cid:
            continue
        if zone is not None and s.i_zone[inst] != zone:
            continue
        if player is not None and s.i_owner[inst] != player:
            continue
        return inst
    raise KeyError(cid)


def do(s, action):
    """Apply ``action`` (must be legal) and return the state."""
    from cptcg.core.engine import apply
    apply(s, s.pending.index_of(action))
    return s
