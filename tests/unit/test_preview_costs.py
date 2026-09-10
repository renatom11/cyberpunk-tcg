"""Per-preview fixed costs: the closed-form Pcg32 constructor, clone() copies, the shared lazy
main-menu placeholders and apply() skipping the legal_actions()/emit() hops."""
import random

import pytest

from conftest import Side, blue_deck, board, red_deck
from cptcg.core import steps
from cptcg.core.actions import Choice, ChoiceKind, Pass, Pick
from cptcg.core.engine import apply, legal_actions, new_game
from cptcg.core.rng import _MASK32, _MASK64, _MULT, Pcg32, _splitmix64
from cptcg.core.steps import AskStep, MainPhaseStep


# ------------------------------------------------------------------ Pcg32.__init__
def _ref_next_u32(state: int, inc: int) -> tuple[int, int]:
    """One reference PCG32 step: returns (output, new_state)."""
    old = state
    state = (old * _MULT + inc) & _MASK64
    xorshifted = (((old >> 18) ^ old) >> 27) & _MASK32
    rot = old >> 59
    return ((xorshifted >> rot) | (xorshifted << ((-rot) & 31))) & _MASK32, state


def _ref_init(seed: int, seq: int) -> tuple[int, int]:
    """The original two-step constructor, kept verbatim as the reference."""
    state = 0
    inc = ((seq << 1) | 1) & _MASK64
    _, state = _ref_next_u32(state, inc)
    state = (state + _splitmix64(seed)) & _MASK64
    _, state = _ref_next_u32(state, inc)
    return state, inc


_EDGE_SEEDS = [0, 1, 2**32 - 1, 2**63, 2**64 - 1, 0xDEADBEEF]
_SEQS = [0, 1, 3, 7, 11, 54]


def _seeds():
    r = random.Random(0x5EED)
    return _EDGE_SEEDS + [r.getrandbits(64) for _ in range(300)]


@pytest.mark.parametrize("seq", _SEQS)
def test_closed_form_constructor_matches_reference(seq):
    for seed in _seeds():
        state, inc = _ref_init(seed, seq)
        g = Pcg32(seed, seq)
        assert (g.state, g.inc) == (state, inc), (seed, seq)
        for _ in range(8):
            out, state = _ref_next_u32(state, inc)
            assert g.next_u32() == out, (seed, seq)


def test_default_seq_and_split_unchanged():
    assert (Pcg32(5).state, Pcg32(5).inc) == _ref_init(5, 54)
    child = Pcg32(5).split(3)
    assert (child.state, child.inc) == _ref_init(_splitmix64(Pcg32(5).state ^ (3 * 0x9E3779B97F4A7C15)), 7)


# ------------------------------------------------------------------------ clone()
def _snapshot(s):
    return (s.turn, s.active, list(s.i_zone), bytes(s.i_spent), bytes(s.i_lag), bytes(s.i_faceup),
            list(s.i_host), list(s.i_flags), list(s.i_known), [list(z) for z in s.z],
            [list(f) for f in s.fixer], [list(g) for g in s.gig], list(s.temp_power), list(s.mods),
            set(s.used), list(s.played), list(s.drawn), list(s.once), list(s.turns_taken),
            s.over, s.winner, s.rng.state, s.rng.inc)


def _mid_game(reg, seed=3, actions=40):
    s = new_game(reg, (red_deck(), blue_deck()), seed)
    r = Pcg32(seed)
    for _ in range(actions):
        if s.over:
            break
        apply(s, r.below(len(legal_actions(s))))
    assert not s.over
    return s


def test_clone_is_independent_of_the_original(reg):
    s = _mid_game(reg)
    before = _snapshot(s)
    c = s.clone()
    assert _snapshot(c) == before
    # the copies are real, mutable copies of the right types ...
    for name in ("i_spent", "i_lag", "i_faceup"):
        assert type(getattr(c, name)) is bytearray and getattr(c, name) is not getattr(s, name)
    assert all(a is not b for a, b in zip(c.z, s.z)) and len(c.z) == len(s.z)
    assert c.used is not s.used and type(c.used) is set
    assert c.rng is not s.rng and (c.rng.state, c.rng.inc) == (s.rng.state, s.rng.inc)
    assert c.i_card is s.i_card and c.i_owner is s.i_owner            # static: shared on purpose
    # ... and mutating them leaves the original untouched
    for z in c.z:
        z.append(999)
    c.i_spent[0] ^= 1
    c.i_lag[0] ^= 1
    c.i_faceup[0] ^= 1
    c.i_zone[0] = -1
    c.i_host[0] = -2
    c.i_flags[0] |= 0x100
    c.i_known[0] |= 0x100
    c.used.add(("probe",))
    c.rng.next_u32()
    c.fixer[0].append(99)
    c.gig[1].append((6, 6))
    c.stack.clear()
    c.played.append(1)
    c.drawn.append(1)
    c.mods.append(("probe", 0, None, 99))
    c.temp_power.append((0, 1, None))
    c.once[0] |= 4
    c.turns_taken[0] += 10
    assert _snapshot(s) == before
    assert s.stack


# ------------------------------------------------------- MainPhaseStep singletons
@pytest.mark.parametrize("active", [0, 1])
def test_main_phase_step_shares_the_lazy_placeholder(reg, active):
    s = board(reg, Side(hand=["T-U1"], eddies=3), Side(hand=["T-U1"], eddies=3), active=active)
    s.pending = None
    MainPhaseStep().run(s)
    assert s.pending is steps._MAIN_CHOICE[active]
    assert s.pending.lazy and s.pending.options == () and s.pending.player == active
    opts = legal_actions(s)
    assert opts and s.pending is not steps._MAIN_CHOICE[active]
    assert not s.pending.lazy and s.pending.options == opts
    assert s.pending.kind is ChoiceKind.MAIN and s.pending.player == active
    assert s.pending.prompt == steps._MAIN_CHOICE[active].prompt
    # the shared placeholder is untouched
    assert steps._MAIN_CHOICE[active].options == () and steps._MAIN_CHOICE[active].lazy is True
    # a clone shares the placeholder and materialises its own menu
    s.pending = steps._MAIN_CHOICE[active]
    c = s.clone()
    assert c.pending is s.pending
    legal_actions(c)
    assert c.pending is not s.pending and s.pending is steps._MAIN_CHOICE[active]


# ----------------------------------------------------- apply() on a materialised choice
def _forbid_main_menu(monkeypatch):
    import cptcg.core.legal as legal

    def boom(s):
        raise AssertionError("main_menu() must not run for a materialised choice")

    monkeypatch.setattr(legal, "main_menu", boom)


def test_apply_pick_does_not_touch_main_menu(reg, monkeypatch):
    s = board(reg, Side(hand=["T-U1"], eddies=3), Side(hand=["T-U1"], eddies=3))
    s.log, s.actions = [], []
    got = []
    nxt = Choice(ChoiceKind.PICK, 0, (Pick((7,)), Pick((8,))), cont=lambda st, a: got.append(("second", a)))

    def cont(st, a):
        got.append(("first", a))
        st.pending = nxt                      # stop advance() right here

    s.pending = Choice(ChoiceKind.PICK, 0, (Pick((1,)), Pick((2,))), cont=cont)
    _forbid_main_menu(monkeypatch)
    apply(s, 1)
    assert got == [("first", Pick((2,)))]
    assert s.pending is nxt
    assert s.actions == [1] and s.log[-1] == ("action", ChoiceKind.PICK, 0, Pick((2,)))


def test_apply_reaction_pass_does_not_touch_main_menu(reg, monkeypatch):
    s = board(reg, Side(hand=["T-U1"], eddies=3), Side(hand=["T-U1"], eddies=3))
    s.log, s.actions = [], []
    nxt = Choice(ChoiceKind.PICK, 1, (Pick((1,)), Pick((2,))), cont=lambda st, a: None)
    s.stack.append(AskStep(nxt))             # what advance() runs after the Pass
    s.pending = Choice(ChoiceKind.REACTION, 1, (Pass(),), prompt="React?")
    _forbid_main_menu(monkeypatch)
    apply(s, 0)
    assert s.pending is nxt
    assert s.actions == [0] and s.log[-1] == ("action", ChoiceKind.REACTION, 1, Pass())


def test_apply_without_pending_raises(reg):
    s = board(reg, Side(hand=["T-U1"], eddies=3), Side(hand=["T-U1"], eddies=3))
    s.pending = None
    with pytest.raises(RuntimeError):
        apply(s, 0)
