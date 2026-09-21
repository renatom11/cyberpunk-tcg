"""The ruling flags that no code reads — pinned to the behaviour they claim to describe.

``config.py`` promised that every ruling is "flippable in one place". Twelve of its fields are read
by no code at all: the behaviour is hard-coded, so flipping one changes ``RulesConfig.digest()`` —
invalidating every stored comparison, which is the whole point of the digest — while changing
nothing about play. A switch that appears to work and does not is worse than no switch.

They are kept, because each is a real ruling a future clarification could reopen and the field is
where that change would land. What changes here is that they are now honest: ``config.DESCRIPTIVE``
declares them, these tests pin the hard-coded behaviour each one describes, and the last test fails
if a flag joins or leaves that set without the declaration being updated.

Where a behaviour is not reachable from a board, the test says so and checks the structure instead
rather than pretending to a stronger check than it makes.
"""
import re
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import Side, board, find, options

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cptcg.core.actions import ChoiceKind, Sell  # noqa: E402
from cptcg.core.engine import apply  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG, DESCRIPTIVE, RulesConfig  # noqa: E402
from cptcg.core.enums import Zone  # noqa: E402
from cptcg.core.view import PUBLIC_ZONES, knows_identity  # noqa: E402

SRC = Path(__file__).resolve().parents[2] / "src"


# --------------------------------------------------------------- 002 perfect_eddie_memory
def test_002_the_eddie_area_is_public(reg):
    """"Eddie-area identities are a public multiset" — so the rival may read every one."""
    assert DEFAULT_CONFIG.perfect_eddie_memory is True
    assert Zone.EDDIES in PUBLIC_ZONES
    s = board(reg, Side(eddies=3), Side())
    for i in s.z[0 * len(Zone) + Zone.EDDIES]:
        assert knows_identity(s, 1, i), "a rival cannot read an Eddie the ruling says is public"


# --------------------------------------------------------------- 003 spent_legend_callable
def test_003_a_spent_legend_is_still_callable(reg):
    """Spending a face-down Legend for Eddies does not take it off the table as a Call target."""
    assert DEFAULT_CONFIG.spent_legend_callable is True
    s = board(reg, Side(legends=[("T-L1", {"spent": True}), "T-L2", "T-L5"], eddies=9), Side())
    spent = find(s, "T-L1", Zone.LEGENDS, 0)
    assert s.i_spent[spent], "fixture did not produce a spent Legend"
    calls = [o for o in options(s) if type(o).__name__ == "CallLegend"]
    assert any(getattr(o, "inst", None) == spent for o in calls), \
        "a spent Legend is not offered as a Call target"


# ------------------------------------------------------------ 027 go_solo_requires_ready
def test_027_go_solo_takes_a_spent_legend_and_returns_it_ready(reg):
    """Two questions the FAQ answers separately, and only one of them is a flag.

    *"Can I GO SOLO on a spent Legend? **Yes**"* is about **legality**, and is what
    ``go_solo_requires_ready`` gates — both branches exercised below, which is what keeps it a
    switch rather than decoration. What **orientation** it then arrives in is a different
    question: GO SOLO's own reminder plays it *as a ready Unit* (CR 11.25.1), while CR 4.5.1's
    "same orientation" belongs to the keyword-less play (ruling 047) — the distinction the FAQ
    draws by spelling it out only there. That half is settled and hard-coded, because a second
    field would move ``RulesConfig.digest()`` and every fitted artifact enforces it.

    Reusing the one flag for both was tried and is wrong: turning it on to get a ready arrival
    takes the spent Legend off the menu entirely, which is the opposite of what the FAQ says.
    """
    assert DEFAULT_CONFIG.go_solo_requires_ready is False

    def solo(cfg):
        s = board(reg, Side(legends=[("T-L1", {"faceup": True, "spent": True})], eddies=5),
                  Side(gig=[(6, 3)]), cfg=cfg)
        leg = find(s, "T-L1", Zone.LEGENDS, 0)
        # Ruling 047 offers the same Legend twice; this is about the KEYWORD play.
        go = next((o for o in options(s)
                   if type(o).__name__ == "GoSolo" and getattr(o, "keyword", True)), None)
        if go is None:
            return None
        apply(s, s.pending.index_of(go))
        return s.i_spent[leg]

    assert solo(DEFAULT_CONFIG) == 0, "a spent Legend could not GO SOLO, or did not arrive ready"
    assert solo(replace(DEFAULT_CONFIG, go_solo_requires_ready=True)) is None, \
        "go_solo_requires_ready=True should keep a spent Legend off the menu"


# ------------------------------------------------------------------- 046 trigger ordering
def test_046_the_controller_orders_their_own_simultaneous_triggers(pool):
    """The FAQ: *"When I have mulitple ATTACK effects that activate and go into pending at the
    same time. Can I choose any order to resolve them? **Yes**"*, and the same answer again for a
    trigger meeting a differently-worded one.

    The board that raised the ruling in play: two Gear on one Unit, each triggering when its host
    is spent. Attacking spends the host, both fire, and the controller is asked which first.
    """
    from cptcg.core.actions import Attack, Pass, Target
    from cptcg.core.enums import TARGET_GIG
    from cptcg.core.engine import apply, legal_actions

    s = board(pool, Side(field=[("psycho-squad",
                                {"gear": ["zetatech-faceplate", "netwatch-netdriver"]})],
                         gig=[(6, 3), (8, 5)], deck=["floor-it", "mantis-blades"]),
              Side(gig=[(4, 2)]))
    u = find(s, "psycho-squad", Zone.FIELD, 0)
    asked = None
    for _ in range(8):
        legal_actions(s)
        ch = s.pending
        if ch is None:
            break
        if ch.kind is ChoiceKind.PICK and (ch.tag or "").endswith("@order"):
            asked = ch
            break
        pick = 0
        for i, o in enumerate(ch.options):
            if isinstance(o, Attack) and o.inst == u:
                pick = i
                break
            if isinstance(o, Target) and o.kind == TARGET_GIG:
                pick = i
                break
            if isinstance(o, Pass):
                pick = i
        apply(s, pick)
    assert asked is not None, "two Gear triggering on one spend asked nobody which came first"
    assert asked.player == 0 and len(asked.options) == 2
    names = {s.card(i).name for i in (find(s, "zetatech-faceplate", Zone.FIELD, 0),
                                      find(s, "netwatch-netdriver", Zone.FIELD, 0))}
    assert names == {"Zetatech Faceplate", "NetWatch Netdriver"}


def test_046_two_copies_of_one_card_are_not_a_choice(pool):
    """The restriction, and it is measured rather than assumed — see ``ops.needs_ordering``.

    A third of the events with two of one player's triggers were two copies of the SAME card.
    Ordering two identical effects has no distinguishable branches, so asking would be a prompt
    that cannot matter, thousands of times a game set, and a branching factor the search pays for
    and learns nothing from.
    """
    from cptcg.core.ops import needs_ordering

    s = board(pool, Side(field=["psycho-squad", "corpo-security"]), Side())
    a, b = s.units(0)
    assert not needs_ordering(s, [(a, None)])                      # one trigger: nothing to order
    assert needs_ordering(s, [(a, None), (b, None)])               # two different cards: a choice
    assert not needs_ordering(s, [(a, None), (a, None)])           # the same instance twice
    other = board(pool, Side(field=["psycho-squad", "psycho-squad"]), Side())
    c, d = other.units(0)
    assert not needs_ordering(other, [(c, None), (d, None)]), "two copies of one card is not a choice"


# --------------------------------------------------------------- 004 empty_fixer_skips
def test_004_an_empty_fixer_skips_the_gig_step(reg):
    """With no dice left to roll there is nothing to ask, so the step must not stop for a choice."""
    assert DEFAULT_CONFIG.empty_fixer_skips is True
    s = board(reg, Side(fixer=[]), Side(), active=0)
    assert s.pending is not None and s.pending.kind is not ChoiceKind.GIG_DIE, \
        "an empty fixer still produced a Gig-die choice"


# --------------------------------------------------------------- 008 win_check_before_draw
def test_008_the_win_check_precedes_the_draw():
    """Structural: ``push_turn`` queues a turn LIFO, so the push order is the reverse of the run
    order. Reading it is the honest check — a board that would deck out *and* hold seven Gigs on
    the same turn boundary is not constructible with the current helpers."""
    assert DEFAULT_CONFIG.win_check_before_draw is True
    src = (SRC / "cptcg" / "core" / "steps.py").read_text(encoding="utf-8")
    body = src[src.index("def push_turn"):]
    body = body[:body.index("\ndef ", 1)]
    pushed = re.findall(r"(\w+Step)\(\)", body)
    run_order = list(reversed(pushed))
    assert run_order.index("WinCheckStep") < run_order.index("DrawStep"), \
        f"the win check no longer runs before the draw: {run_order}"


# --------------------------------------------------------------- 010 zero_power_fights
def test_010_a_zero_power_unit_still_fights(pool):
    """The half that is NOT wired. ``zero_power_cannot_defeat`` is read by the engine; "it fights
    at all" is hard-coded — a 0-power Unit is a legal attacker and a legal blocker."""
    assert DEFAULT_CONFIG.zero_power_fights is True
    from cptcg.core.ops import power
    from cptcg.core.ops import steal_count

    s = board(pool, Side(field=["delamain-rideshare-ai"]),
              Side(field=["corpo-security"], gig=[(6, 3)]))
    u = find(s, "delamain-rideshare-ai", Zone.FIELD, 0)
    assert power(s, u) == 0 and steal_count(power(s, u)) == 0, \
        "fixture unit is not a 0-power non-stealer"
    attacks = [o for o in options(s) if type(o).__name__ == "Attack"]
    assert any(o.inst == u for o in attacks), \
        "a 0-power Unit was not offered as an attacker — it steals nothing, but it still fights"


# --------------------------------------------------------------- 016 gear_reequip
def test_016_equipped_gear_cannot_be_moved(pool):
    """Nothing in any menu offers re-equipping, which is what the default says."""
    assert DEFAULT_CONFIG.gear_reequip is False
    s = board(pool, Side(field=[("rockn-rockerboy", {"gear": ["mantis-blades"]}),
                                "psycho-squad"], eddies=9), Side())
    gear = find(s, "mantis-blades", Zone.FIELD, 0)
    plays = [o for o in options(s) if type(o).__name__ == "Play"]
    assert not any(getattr(o, "inst", None) == gear for o in plays), \
        "an already-equipped Gear was offered for play again"


# --------------------------------------------------------------- 020 hand_limit
def test_020_there_is_no_hand_limit(reg):
    """No step enforces one, and the default records that as None rather than a number."""
    assert DEFAULT_CONFIG.hand_limit is None
    steps = (SRC / "cptcg" / "core" / "steps.py").read_text(encoding="utf-8")
    assert "hand_limit" not in steps, "a hand-limit step appeared; the flag is no longer descriptive"
    s = board(reg, Side(hand=["T-U1", "T-U2", "T-U3", "T-U4", "T-U5", "T-U6", "T-U7", "T-U8"]),
              Side())
    assert len(s.z[0 * len(Zone) + Zone.HAND]) == 8, "a hand over seven was trimmed by something"


# --------------------------------------------------------------- 021 sell_in_reactions
def test_021_you_cannot_sell_during_a_reaction():
    """Structural: ``legal.reaction_menu`` builds the reaction options and never offers a Sell."""
    assert DEFAULT_CONFIG.sell_in_reactions is False
    import ast

    src = (SRC / "cptcg" / "core" / "legal.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "reaction_menu")
    built = {n.func.id for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "Sell" not in built, \
        f"the reaction menu now builds a Sell; the flag is no longer descriptive ({sorted(built)})"
    # and the options it does build, for the record
    assert {"Pass", "Block"} <= built, f"reaction menu shape changed unexpectedly: {sorted(built)}"


# --------------------------------------------------------------- 025 explicit_payment
def test_025_eddies_pay_automatically_and_the_legend_choice_is_asked(pool):
    """Ruling 025 as revised by Stage 0 E12. The field keeps its recorded value (flipping it moves
    the ruleset digest and refuses every fitted artifact; see ``core.config``), and what it still
    describes holds: ready Eddies are spent first without a question. When Eddies do not cover
    the cost and more than one set of Legends could, the engine asks (``engine._with_payment``);
    ``tests/rules/test_stage0_engine.py`` pins the shape of that question."""
    assert DEFAULT_CONFIG.explicit_payment is False
    from cptcg.core.engine import apply, legal_actions
    s = board(pool, Side(hand=["mantis-blades"], field=["psycho-squad"], eddies=9,
                         legends=["goro-takemura-hands-unclean", "dexter-deshawn-off-the-grid"]), Side())
    legal_actions(s)
    play = next(i for i, o in enumerate(s.pending.options)
                if type(o).__name__ == "Play" and s.reg.defs[s.i_card[o.inst]].id == "mantis-blades")
    apply(s, play)
    assert not (s.pending is not None and s.pending.kind is ChoiceKind.PICK
                and (s.pending.tag or "").startswith("pay@")), "Eddies covered it: no question"
    assert not any(s.i_spent[i] for i in s.legends(0))


# --------------------------------------------------------------- the enforcement net
def _readers() -> dict[str, int]:
    """How many places outside config.py mention each ruling field."""
    fields = [f for f in RulesConfig.__dataclass_fields__]
    counts = dict.fromkeys(fields, 0)
    for path in list(SRC.rglob("*.py")) + list((SRC.parent / "tools").rglob("*.py")):
        if path.name == "config.py":
            continue
        text = path.read_text(encoding="utf-8")
        for f in fields:
            counts[f] += len(re.findall(rf"\b{f}\b", text))
    return counts


def test_every_unread_flag_is_declared_descriptive():
    """The permanent net: a flag that nothing reads must say so.

    This is the check that would have caught the original problem. Twelve fields documented a
    ruling, were hashed into every stored result, and were read by nothing — and the module
    docstring claimed all of them were "flippable in one place". Nothing failed, because nothing
    was looking.

    Adding a flag without wiring it now fails here until it is declared. Wiring one and forgetting
    to undeclare it fails here too.
    """
    counts = _readers()
    # 'rulings' fields only: the game constants above them are read everywhere and are not rulings.
    ruling_fields = [f for f in RulesConfig.__dataclass_fields__
                     if f not in ("gigs_to_win", "opening_hand", "deck_min", "deck_max",
                                  "max_copies", "max_turns")]
    unread = {f for f in ruling_fields if counts[f] == 0}
    undeclared = sorted(unread - DESCRIPTIVE)
    stale = sorted(DESCRIPTIVE - unread)
    assert not undeclared, (
        "these ruling flags are read by no code and are not declared in config.DESCRIPTIVE — "
        "either wire them or declare them: " + ", ".join(undeclared))
    assert not stale, (
        "these flags are declared descriptive but something now reads them — undeclare them and "
        "test both branches: " + ", ".join(stale))


def test_the_descriptive_set_names_only_real_fields():
    unknown = sorted(DESCRIPTIVE - set(RulesConfig.__dataclass_fields__))
    assert not unknown, f"DESCRIPTIVE names fields that do not exist: {unknown}"
