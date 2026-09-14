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

All three currently pass over all 151 cards. A lint that has never fired is only worth having if it
*can* fire, so each one's docstring says what it would catch, and the ctx lint has an explicit
self-test below that plants violations and checks they are detected.
"""
import ast
import re
import sys
from pathlib import Path

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
