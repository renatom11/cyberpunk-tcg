"""Batch b03 — ``on_play`` across the whole pool: sides, counts, optionality and ordering.

The cross-cutting pass over the one mechanism. Its result was a *closed column* rather than a new
finding, so what it leaves behind is two pool-wide guards instead of a scenario: the sentence
"exactly one script in the set makes a bare printed imperative declinable, and none picks from the
wrong side" is only worth anything if a second one fails the suite the day it is written.

Both guards pass today. Both carry a self-test that plants violations, because the failure mode of a
guard like this is to go on reporting a comfortable zero while checking almost nothing — the same
trap ``tests/cards/test_script_lints.py`` documents for the ctx lint.

Reasoning, the full census and the three examined-and-not-filed items: out/audit/b03/findings.md.
"""
import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from cptcg.cards.registry import SETS_DIR  # noqa: E402

#: Words of permission. A printed one of these is the only thing that may put a decline on a menu.
OPTIONAL_WORDS = re.compile(r"\bmay\b|\bup to\b|any number", re.I)

#: One-target prompts: ``optional=True`` on any of them adds a decline option.
PICK_ONE = {"choose", "choose_gig", "defeat_one", "bottom_deck_one", "spend_one", "temp_power_one"}

#: Many-target prompts and the position of their ``lo`` bound; ``lo=0`` puts an empty pick on
#: the menu, which turns "Defeat a rival Unit" into "defeat up to one".
PICK_MANY = {"choose_many": 1, "search_top": 2}

#: Candidate-list position for the calls that take one.
CAND_POS = {"choose": 0, "choose_many": 0, "defeat_one": 1, "bottom_deck_one": 1,
            "spend_one": 1, "temp_power_one": 1}

#: The one open row of the optionality census, filed by another batch. Delete it with its fix.
DECLINABLE_IMPERATIVES_OPEN = {"sketchy-ripper"}

#: "Each player defeats one of their Units" names neither side and legitimately uses both lists.
#: The only genuinely two-sided phrasing in the set; without this the side lint reports noise.
TWO_SIDED_PHRASING = {"live-with-the-aftermath"}


def _script_defs(source: str) -> dict[str, ast.FunctionDef]:
    """``card id -> the @script-decorated factory``."""
    out = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and getattr(dec.func, "id", "") == "script":
                for a in dec.args:
                    if isinstance(a, ast.Constant):
                        out[a.value] = node
    return out


def _declinable_sites(fn: ast.AST) -> list[str]:
    """Every place this factory offers a decline: ``optional=True``, or a literal ``lo=0``."""
    out = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if name in PICK_ONE:
            for kw in node.keywords:
                if kw.arg == "optional" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    out.append(f"{name}(optional=True) at line {node.lineno}")
        elif name in PICK_MANY:
            i = PICK_MANY[name]
            if i < len(node.args) and isinstance(node.args[i], ast.Constant) and node.args[i].value == 0:
                out.append(f"{name}(lo=0) at line {node.lineno}")
    return out


def _declinable(pool, source: str) -> list[str]:
    defs = _script_defs(source)
    bad = []
    for d in pool.defs:
        fn = defs.get(d.id)
        if fn is None:
            continue
        sites = _declinable_sites(fn)
        if sites and not OPTIONAL_WORDS.search(d.text or ""):
            bad.append(f"{d.id}: {', '.join(sites)} — the text prints no 'may' / 'up to' / 'any number'")
    return bad


def test_no_bare_imperative_is_declinable(pool):
    """A decline on the menu is a printed word, and only one card in the set disagrees.

    "Defeat a rival Unit" with a legal target is not a choice; ``optional=True`` and
    ``choose_many(vals, 0, n, …)`` both put "pick nothing" on the menu and turn it into one. Four
    cards were filed for exactly this shape in three unrelated batches (Bonnie and Clyde, Unlikely
    Bond, Shattered Memories, Sketchy Ripper), which is what a per-card reader can find; what a
    per-card reader cannot say is whether there is a fifth.

    Over all 151 cards there is exactly one open row, ``AUD-sketchy-ripper-1``: "Reveal a Gear and
    add it to your hand" carries ``search_top(3, GEAR, 0, 1)``. This guard pins that set so a
    *second* card acquiring the shape fails today rather than waiting to be assigned an auditor,
    and goes green when that finding is fixed and its entry deleted.
    """
    src = (SETS_DIR / "wnc.py").read_text(encoding="utf-8")
    found = {line.split(":")[0] for line in _declinable(pool, src)}
    assert found <= DECLINABLE_IMPERATIVES_OPEN, (
        "a card newly makes a bare printed imperative declinable: "
        + ", ".join(sorted(found - DECLINABLE_IMPERATIVES_OPEN)))


def test_the_declinable_lint_can_actually_fire():
    """Control for the guard above: it reports one card, not zero, because it is looking.

    A guard that has never fired is worth nothing unless it is shown to be able to. Each planted
    factory below is a shape that really occurs in ``wnc.py`` — a keyword ``optional=True``, a
    positional ``lo=0`` on ``choose_many``, and the same on ``search_top`` — and the clean one is
    the common correct spelling.
    """
    clean = "def _():\n    return CardScript(on_play=lambda c: defeat_one(c, c.rival_units()))\n"
    assert not _declinable_sites(ast.parse(clean))

    violations = [
        "def _():\n    return CardScript(on_play=lambda c: defeat_one(c, c.rival_units(), optional=True))\n",
        "def _():\n    def play(c):\n        c.choose_many(c.rival_units(), 0, 2, lambda c2, us: None)\n",
        "def _():\n    return CardScript(on_play=lambda c: c.search_top(3, None, 0, 1))\n",
    ]
    for src in violations:
        assert _declinable_sites(ast.parse(src)), f"the guard failed to catch:\n{src}"


def _wrong_side(pool, source: str) -> list[str]:
    """Candidate lists that pick from a side the printed text never names."""
    defs = _script_defs(source)
    bad = []
    for d in pool.defs:
        fn = defs.get(d.id)
        if fn is None or d.id in TWO_SIDED_PHRASING:
            continue
        text = d.text or ""
        says_rival = bool(re.search(r"\brivals?\b", text, re.I))
        says_friendly = bool(re.search(r"\bfriendly\b", text, re.I))
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            i = CAND_POS.get(name)
            if i is None or i >= len(node.args):
                continue
            expr = ast.unparse(node.args[i])
            if "rival_units(" in expr and not says_rival:
                bad.append(f"{d.id}: picks from rival_units but the text never says 'rival' — {expr[:70]}")
            if re.search(r"\.units\(\)", expr) and not says_friendly:
                bad.append(f"{d.id}: picks from the bare friendly units() but the text never says "
                           f"'friendly' — {expr[:70]}")
    return bad


def test_a_targeting_prompt_offers_the_side_the_card_names(pool):
    """Control for the side column of the b03 census: the pool has no wrong-sided prompt.

    This set says *friendly* when it means friendly and *rival* when it means rival, and an
    unqualified noun means either player's — Gilded Maton prints "a **friendly** Gear" and uses
    ``c.all_gear()``, Detonate prints "a **rival** Gear" and uses ``c.all_gear(c.rival)``, and
    Heywood Ripperdoc prints a bare "a Gear" and offers both. So a script that narrows to one side
    must be able to point at the printed word that told it to.

    The claim in out/audit/b03/findings.md is that no card in the set breaks that, which is a
    negative result and therefore worth exactly as much as the check behind it. This is the check.
    """
    src = (SETS_DIR / "wnc.py").read_text(encoding="utf-8")
    bad = _wrong_side(pool, src)
    assert not bad, "prompts offering a side the card never names:\n  " + "\n  ".join(bad)


def test_the_side_lint_can_actually_fire(pool):
    """Control for the guard above: with its one exclusion removed it reports that card.

    ``live-with-the-aftermath`` ("Each player defeats one of their Units") names neither side and
    uses both lists, which is correct and is why it is excluded. Reinstating it is the cheapest
    honest proof that the detector reads real scripts rather than returning an empty list.
    """
    src = (SETS_DIR / "wnc.py").read_text(encoding="utf-8")
    TWO_SIDED_PHRASING.discard("live-with-the-aftermath")
    try:
        fired = _wrong_side(pool, src)
    finally:
        TWO_SIDED_PHRASING.add("live-with-the-aftermath")
    assert any("live-with-the-aftermath" in line for line in fired), \
        "the side lint reports nothing even on the card it is excluding"
