"""Pool-wide lints over the card scripts — the checks ``needs_script`` could never make.

``CardDef.needs_script`` is derived from "the printed text implies an effect and there is no
script", so it detects a card with **no** script and is structurally blind to one that is wrong or
partial. It reads 0 for every card in the pool, and that 0 says nothing about correctness.

These are the class of check that scales: each reads the whole pool mechanically rather than by
someone looking. That matters because the repo has already been bitten by a hand-written
classification that was wrong — Chrome Reverie and MaxTac Suppression Team both said "a rival Unit
can't attack" in their printed text and carried no such token in the interaction map, and nothing
raised for weeks. The durable fix there was not correcting two entries; it was adding a test that
reads the printed text and fails on any card that says so. Same idea here.

Three of them pass over all 151 cards. The fourth, added last, does not: it reads the printed text
for a second sentence with its own board condition and finds six cards that implement it inside the
first sentence's continuation, where a declined or impossible first sentence skips it. Five of those
six were found by hand first, in two unrelated audit batches; the detector then found the sixth,
which is the whole argument for writing detectors instead of filing fixes.

A lint that has never fired is only worth having if it *can* fire, so each one's docstring says what
it would catch, the ctx lint has an explicit self-test that plants violations, and the tail-clause
lint has one pinning the exclusions that keep it from reporting noise.
"""
import ast
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cptcg.cards.registry import SETS_DIR  # noqa: E402
from cptcg.core.enums import CardType  # noqa: E402

#: EffectCtx calls that take a continuation, and where it sits.
CONT_POS = {"choose": [1], "choose_many": [3], "maybe": [0], "later": [0], "adjust_up_to": [3],
            "discard": [2], "search_top": [4], "choose_gig": [1]}
CONT_KW = {"cont", "otherwise", "then"}

#: The four printed timing labels and the CardScript hook each one requires.
TRIGGER_HOOK = {"PLAY": "on_play", "ATTACK": "on_attack",
                "DEFEATED": "on_defeated", "CALL": "on_call"}


def _labels(text: str) -> set[str]:
    """Timing words from a printed trigger label. ``PLAY / ATTACK:`` is two of them, not zero."""
    out = set()
    for lab in re.findall(r"^([A-Z][A-Z /]*):", text or "", re.M):
        out.update(w for w in re.split(r"\s*/\s*", lab.strip()) if w in TRIGGER_HOOK)
    return out


def test_a_printed_timing_trigger_has_the_hook_that_implements_it(pool):
    """PLAY:/ATTACK:/DEFEATED:/CALL: in the text must mean the matching hook in the script.

    This is exactly the check ``needs_script`` cannot make: it asks only whether *a* script exists,
    so a card with an on_play and a printed DEFEATED: clause it never implements looks identical to
    a fully correct one.
    """
    missing = []
    for d in pool.defs:
        said = _labels(d.text)
        for word, hook in TRIGGER_HOOK.items():
            if word in said and not (d.script and getattr(d.script, hook, None)):
                missing.append(f"{d.id}: text says {word}: but the script has no {hook}")
    assert not missing, "printed triggers with no implementation:\n  " + "\n  ".join(missing)


def test_a_timing_hook_corresponds_to_a_printed_label(pool):
    """The other direction: a hook the printed text never asks for.

    Programs are the deliberate exception — a Program's whole text *is* its on-play effect and it
    carries no ``PLAY:`` label, so the rule would be wrong for all 34 of them.
    """
    extra = []
    for d in pool.defs:
        said = _labels(d.text)
        for word, hook in TRIGGER_HOOK.items():
            if not (d.script and getattr(d.script, hook, None)):
                continue
            if word in said or (word == "PLAY" and d.type is CardType.PROGRAM):
                continue
            extra.append(f"{d.id} ({d.type.name}): has {hook} but the text has no {word}: label")
    assert not extra, "hooks with no printed trigger:\n  " + "\n  ".join(extra)


# ------------------------------------------------------------------ the one rule
def _ctx_name(fn):
    if isinstance(fn, (ast.Lambda, ast.FunctionDef)):
        a = fn.args.args
        return a[0].arg if a else None
    return None


class _Leaks(ast.NodeVisitor):
    """Continuations that use an enclosing ctx instead of the one they are handed.

    Resolving a continuation passed **by name** is the whole difficulty. Most of wnc.py is written
    as ``def play(c): def then(c2, u): ...; c.choose(xs, then)``, so a version that only inspects
    inline lambdas silently passes on the majority of real scripts — which is how a lint like this
    ends up reporting a comfortable zero while checking almost nothing.
    """

    def __init__(self):
        self.stack, self.bad = [], []

    def _resolve(self, node):
        if isinstance(node, (ast.Lambda, ast.FunctionDef)):
            return node
        if isinstance(node, ast.Name):
            for _, defs in reversed(self.stack):
                if node.id in defs:
                    return defs[node.id]
        return None

    def _check(self, arg, line):
        cont = self._resolve(arg)
        inner = _ctx_name(cont) if cont is not None else None
        if inner is None:
            return
        outer = {n for n, _ in self.stack if n and n != inner}
        used = {n.id for n in ast.walk(cont) if isinstance(n, ast.Name)}
        leaked = sorted(used & outer)
        if leaked:
            self.bad.append((line, getattr(cont, "name", "<lambda>"), inner, leaked))

    def visit_Call(self, node):
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in CONT_POS and isinstance(f.value, ast.Name):
            for i in CONT_POS[f.attr]:
                if i < len(node.args):
                    self._check(node.args[i], node.lineno)
            for kw in node.keywords:
                if kw.arg in CONT_KW:
                    self._check(kw.value, node.lineno)
        self.generic_visit(node)

    def _scope(self, node):
        defs = {n.name: n for n in ast.walk(node) if isinstance(n, ast.FunctionDef)}
        self.stack.append((_ctx_name(node), defs))
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _scope
    visit_Lambda = _scope


def _leaks(source: str):
    d = _Leaks()
    d.visit(ast.parse(source))
    return d.bad


def test_no_continuation_closes_over_the_enclosing_ctx():
    """docs/effects-authoring.md calls this "the one rule" and nothing checked it until now.

    A continuation must use the ctx it is *given*. The enclosing one is bound to whichever state
    existed when the question was asked, and a search agent resolves the same question on cloned
    states — so a continuation that reaches for the outer ctx mutates the wrong clone. It is
    invisible in ordinary play and wrong under every searching agent, which is the worst possible
    shape for a bug in a project whose strongest agents all search.
    """
    bad = []
    for path in sorted(SETS_DIR.glob("*.py")):
        for line, name, inner, leaked in _leaks(path.read_text(encoding="utf-8")):
            bad.append(f"{path.name}:{line} continuation {name!r} takes {inner!r} but uses {leaked}")
    assert not bad, "continuations using an enclosing ctx:\n  " + "\n  ".join(bad)


def test_that_lint_can_actually_fire():
    """A lint that has never fired is worth nothing unless it is shown to be able to.

    The nested-`def` case below is the one that matters: it is how most real scripts are written,
    and the first version of this detector missed it entirely while reporting zero over the pool.
    """
    import textwrap

    clean = "def play(c):\n    def then(c2, u):\n        c2.defeat(u)\n    c.choose(c.units(), then)\n"
    assert not _leaks(textwrap.dedent(clean))

    violations = [
        "def play(c):\n    c.choose(c.units(), lambda c2, u: c.defeat(u))\n",
        "def play(c):\n    def then(c2, u):\n        c.defeat(u)\n    c.choose(c.units(), then)\n",
        "def play(c):\n    c.choose(c.units(), lambda c2, u: c2.spend(u), otherwise=lambda c2: c.draw(1))\n",
        "def play(c):\n    def a(c2, u):\n        def b(c3, v):\n            c.defeat(v)\n        c2.choose(c2.units(), b)\n    c.choose(c.units(), a)\n",
    ]
    for src in violations:
        assert _leaks(textwrap.dedent(src)), f"lint failed to catch:\n{src}"


# ------------------------------------------------- the second sentence that never runs
#: Effects a tail clause can name, as (printed phrasing -> the EffectCtx methods that perform it).
#: Deliberately a short, explicit table rather than a guess: a phrasing that is not here is not
#: checked, and the coverage assertion below pins how many of the pool's tail clauses that leaves.
TAIL_EFFECT = {
    ("draw",): r"\bdraw \d",
    ("discard",): r"\bdiscards? \d",
    ("offer_call_free", "call_free"): r"Call a Legend for free",
}

#: A sentence that opens a *state-based* condition: "If you control ...", "Then, if your ★ ...".
_COND = re.compile(r"^(?:then,?\s*)?if\b", re.I)

#: ... unless its subject refers back to what the previous sentence did. "If **it** becomes a min
#: Gig" and "If **its** cost equals ..." genuinely have nothing to test when the first sentence did
#: nothing, so nesting them in its continuation is correct. Getting this exclusion wrong in either
#: direction is how this detector turns into noise: too loose and Jackie Welles and the Heywood
#: Ripperdoc are false positives, too tight and the six real ones are missed.
_BACKREF = re.compile(r"^(?:then,?\s*)?if\s+(?:it|its|it's|that|the card'?s?|they|those|this|these)\b",
                      re.I)

#: ... and a clause that *modifies* the first sentence rather than adding to it belongs inside it.
_MODIFIES = re.compile(r"\b(you do|you did|you don'?t|this way|you trash them|you add them|"
                       r"instead|also|(?:\d+|a|an|one) more)\b", re.I)


def _sentences(text: str) -> list[str]:
    """Printed sentences, with the timing label ("PLAY:") stripped off the front of each line."""
    t = re.sub(r"^[A-Z][A-Z /]*:\s*", "", text or "", flags=re.M)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t.replace("\n", " ")) if s.strip()]


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


def _method_calls(node: ast.AST, name: str) -> list[ast.Call]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)
            and (n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")) == name]


def _continuation_bodies(fn: ast.FunctionDef) -> list[ast.AST]:
    """Every lambda or nested def this factory hands to a prompting call as its continuation.

    Continuations passed **by name** are the common case in these scripts and were what an earlier
    detector in this file missed entirely, so they are resolved through a scope-local map of nested
    ``def``s rather than only matching inline lambdas.
    """
    named = {n.name: n for n in ast.walk(fn) if isinstance(n, ast.FunctionDef)}
    out = []
    for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
        base = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
        cands = [call.args[i] for i in CONT_POS.get(base, []) if i < len(call.args)]
        cands += [kw.value for kw in call.keywords if kw.arg in CONT_KW]
        for c in cands:
            if isinstance(c, ast.Lambda):
                out.append(c)
            elif isinstance(c, ast.Name) and c.id in named:
                out.append(named[c.id])
    return out


def _trapped(pool, source: str) -> list[str]:
    """Cards whose state-based tail clause is implemented *only* inside a continuation."""
    defs = _script_defs(source)
    bad = []
    for d in pool.defs:
        fn = defs.get(d.id)
        if fn is None:
            continue
        for sentence in _sentences(d.text)[1:]:
            if not _COND.match(sentence) or _BACKREF.match(sentence) or _MODIFIES.search(sentence):
                continue
            for methods, phrasing in TAIL_EFFECT.items():
                if not re.search(phrasing, sentence, re.I):
                    continue
                calls = [c for m in methods for c in _method_calls(fn, m)]
                if not calls:
                    continue                  # unimplemented is a different finding, not this one
                nested = {id(c) for body in _continuation_bodies(fn) for m in methods
                          for c in _method_calls(body, m)}
                if all(id(c) in nested for c in calls):
                    bad.append(f"{d.id}: {sentence}")
    return bad


#: The six open findings, each with its own scenario test under ``tests/cards/audit/``. Listed here
#: so that a *seventh* card acquiring this shape fails loudly today rather than waiting for the six
#: to be fixed. Delete an entry with its fix.
TRAPPED_TAIL_CLAUSES_OPEN = {
    "afterparty-at-lizzies", "industrial-assembly", "trust-no-one", "peace-offering",
    "memory-relapse", "zetatech-faceplate",
}


def test_no_new_card_traps_a_state_based_tail_clause(pool):
    """Nothing beyond the six already found. This one passes today and guards the boundary."""
    src = (SETS_DIR / "wnc.py").read_text(encoding="utf-8")
    found = {line.split(":")[0] for line in _trapped(pool, src)}
    assert found <= TRAPPED_TAIL_CLAUSES_OPEN, \
        "a card newly traps its tail clause in a continuation: " + ", ".join(sorted(found - TRAPPED_TAIL_CLAUSES_OPEN))


@pytest.mark.xfail(strict=True, reason="AUD-tail-clause: six cards implement a separate, state-based printed clause inside the continuation of the previous one, so declining that clause (or having no legal way to perform it) skips this one entirely")
def test_a_state_based_tail_clause_is_not_trapped_in_a_continuation(pool):
    """A card prints "Adjust a Gig by up to 1. **Then, if you control ... , draw 1.**"

    Those are two sentences. The second has its own condition, tested against the board, and "Then"
    sequences them rather than making the draw conditional on a die having moved. But the scripts
    implement the second inside the continuation of the first, and every one of these first clauses
    can decline to happen — "up to N" includes zero, "you may" can be refused, and a prompt with no
    legal candidate is skipped. So the printed second sentence never runs at all.

    This is the detector the Chrome Reverie rule demands: the same error was found by hand on five
    cards in two unrelated audit batches, and running it over all 151 turned up a sixth that no
    auditor had been assigned. It goes green when the last of the six is fixed.
    """
    src = (SETS_DIR / "wnc.py").read_text(encoding="utf-8")
    bad = _trapped(pool, src)
    assert not bad, "state-based tail clauses trapped in a continuation:\n  " + "\n  ".join(bad)


def test_the_tail_clause_lint_separates_back_references_from_state_conditions():
    """The exclusions are the whole detector; without them it reports noise.

    "If **it** becomes a min Gig" has nothing to test when no Gig was decreased, so nesting it is
    right. "If **you control** a min Gig" is about the board and is wrong to nest. Both live in
    this pool — Jackie Welles and Trust No One — and only the second is a bug.
    """
    assert _BACKREF.match("If it becomes a min Gig, draw 1.")
    assert _BACKREF.match("If its cost equals the value of a friendly Gig, draw 1.")
    assert _BACKREF.match("If the card's cost equals the value of a friendly Gig, draw 1.")
    assert not _BACKREF.match("If you control a min Gig, draw 1.")
    assert not _BACKREF.match("Then, if you control a value-pair, draw 1.")
    assert not _BACKREF.match("If your ★ (Street Cred) is an even number, draw 1.")
    assert _MODIFIES.search("that Rival discards 1 more.")
    assert _MODIFIES.search("If you have less ★ than a Rival, choose both instead.")
    assert not _MODIFIES.search("If you control a Gig with 8+ value, draw 1.")
