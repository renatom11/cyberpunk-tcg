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

Three of them pass over all 151 cards. The fourth, added last, did not: it reads the printed text
for a second sentence with its own board condition and found six cards that implement it inside the
first sentence's continuation, where a declined or impossible first sentence skips it. Five of those
six were found by hand first, in two unrelated audit batches; the detector then found the sixth,
which is the whole argument for writing detectors instead of filing fixes. All six are fixed and it
passes now.

Two more read the ``events=`` filter against the hook it guards: a kind the engine never dispatches
is a trigger that is dead for the life of the card, and a filter narrower than the branches its body
handles is half a card. Neither has a runtime signal — no exception, no warning, the script loads —
so the only place either can be caught is a scan like this one. Both report zero over the pool
today, and the self-test plants one of each to show they would not.

A lint that has never fired is only worth having if it *can* fire, so each one's docstring says what
it would catch, the ctx lint has an explicit self-test that plants violations, and the tail-clause
lint has one pinning the exclusions that keep it from reporting noise.
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


#: Keyword slots whose callable runs **only if the prompt was answered affirmatively**. A tail
#: clause hung here is the bug.
_ONLY_IF_KW = {"cont", "then"}
#: Keyword slots whose callable runs **whatever happens** — after a decline, and when the prompt was
#: never offered. A tail clause hung here is the fix.
_ANYWAY_KW = {"after", "otherwise"}


def _continuation_bodies(fn: ast.FunctionDef, kinds=None) -> list[ast.AST]:
    """Every lambda or nested def this factory hands to a prompting call as a continuation.

    ``kinds`` selects which keyword slots count; the positional continuation of a prompting call is
    always an "only if" slot. Continuations passed **by name** are the common case in these scripts
    and were what an earlier detector in this file missed entirely, so they are resolved through a
    scope-local map of nested ``def``s rather than only matching inline lambdas.
    """
    kinds = CONT_KW if kinds is None else kinds
    named = {n.name: n for n in ast.walk(fn) if isinstance(n, ast.FunctionDef)}
    out = []
    for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
        base = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
        cands = [call.args[i] for i in CONT_POS.get(base, [])
                 if i < len(call.args) and kinds is not _ANYWAY_KW]
        cands += [kw.value for kw in call.keywords if kw.arg in kinds]
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
                trapped = {id(c) for body in _continuation_bodies(fn, _ONLY_IF_KW) for m in methods
                           for c in _method_calls(body, m)}
                # A tail clause reached through an ``after=``/``otherwise=`` hook is correctly
                # sequenced, not trapped, even though it is lexically inside a continuation. Peace
                # Offering has to be written that way: its set is two nested questions, so the tail
                # belongs on the inner one and ``after`` on the outer would fire too early.
                freed = {id(c) for body in _continuation_bodies(fn, _ANYWAY_KW) for m in methods
                         for c in _method_calls(body, m)}
                if all(id(c) in trapped for c in calls) and not (freed & {id(c) for c in calls}):
                    bad.append(f"{d.id}: {sentence}")
    return bad


#: Empty: all six are fixed. It stays here because the *other* test in this pair -- the one that
#: passes today -- asserts the flagged set is a subset of this, so a seventh card acquiring the
#: shape fails immediately rather than waiting for anything.
TRAPPED_TAIL_CLAUSES_OPEN: set[str] = set()


def test_no_new_card_traps_a_state_based_tail_clause(pool):
    """Nothing beyond the six already found. This one passes today and guards the boundary."""
    src = (SETS_DIR / "wnc.py").read_text(encoding="utf-8")
    found = {line.split(":")[0] for line in _trapped(pool, src)}
    assert found <= TRAPPED_TAIL_CLAUSES_OPEN, \
        "a card newly traps its tail clause in a continuation: " + ", ".join(sorted(found - TRAPPED_TAIL_CLAUSES_OPEN))


def test_a_state_based_tail_clause_is_not_trapped_in_a_continuation(pool):
    """A card prints "Adjust a Gig by up to 1. **Then, if you control ... , draw 1.**"

    Those are two sentences. The second has its own condition, tested against the board, and "Then"
    sequences them rather than making the draw conditional on a die having moved. But the scripts
    implement the second inside the continuation of the first, and every one of these first clauses
    can decline to happen — "up to N" includes zero, "you may" can be refused, and a prompt with no
    legal candidate is skipped. So the printed second sentence never runs at all.

    This is the detector the Chrome Reverie rule demands: the same error was found by hand on five
    cards in two unrelated audit batches, and running it over all 151 turned up a sixth that no
    auditor had been assigned.

    Fixed: AUD-tail-clause. All six are done, and `EffectCtx.adjust_up_to`, `choose_gig`,
    `spend_one` and `maybe` grew an ``after=`` hook that runs whatever happens -- including when
    the prompt was never offered, which is the case none of the six handled.
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


# ----------------------------------------------- a trigger that filters out its own event
#: Every event kind `ops.dispatch` can deliver, read off the dispatch sites rather than kept by
#: hand — a vocabulary kept by hand is the thing that goes stale. `_dispatched_kinds` fails loudly
#: if the scan finds nothing, because an empty vocabulary would make the lint below vacuous.
def _dispatched_kinds() -> set[str]:
    kinds = set()
    for path in sorted((SETS_DIR.parents[1] / "core").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and getattr(n.func, "id", "") == "dispatch"
                    and len(n.args) >= 2 and isinstance(n.args[1], ast.Tuple)
                    and n.args[1].elts and isinstance(n.args[1].elts[0], ast.Constant)):
                kinds.add(n.args[1].elts[0].value)
    assert kinds, "found no dispatch sites: the scan is broken, not the pool"
    return kinds


def _event_hooks(source: str):
    """(card id, the events= filter, the kinds the hook body tests e[0] against) for every card.

    The hook is usually a named inner ``def``, so a version that only reads inline lambdas would
    check almost nothing — the same trap the ctx lint above fell into first.
    """
    tree = ast.parse(source)
    out = []
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        card = next((d.args[0].value for d in fn.decorator_list
                     if isinstance(d, ast.Call) and getattr(d.func, "id", "") == "script"), None)
        if card is None:
            continue
        events, hook = None, None
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "CardScript":
                for kw in n.keywords:
                    if kw.arg == "events":
                        events = {c.value for c in ast.walk(kw.value)
                                  if isinstance(c, ast.Constant) and isinstance(c.value, str)}
                    elif kw.arg == "on_event":
                        hook = kw.value
        if events is None and hook is None:
            continue
        if isinstance(hook, ast.Name):
            hook = next((n for n in ast.walk(fn)
                         if isinstance(n, ast.FunctionDef) and n.name == hook.id), None)
        tested = set()
        for n in ast.walk(hook) if hook is not None else ():
            if not isinstance(n, ast.Compare):
                continue
            left = n.left
            if (isinstance(left, ast.Subscript) and isinstance(left.slice, ast.Constant)
                    and left.slice.value == 0):
                for op, cmp in zip(n.ops, n.comparators):
                    if isinstance(op, (ast.Eq, ast.In)):
                        tested |= {c.value for c in ast.walk(cmp)
                                   if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        out.append((card, events or set(), tested))
    return out


def _pool_hooks():
    rows = []
    for path in sorted(SETS_DIR.glob("*.py")):
        rows += _event_hooks(path.read_text(encoding="utf-8"))
    return rows


def test_every_event_kind_a_card_listens_for_is_one_the_engine_dispatches():
    """A typo'd kind never fires and nothing errors — the trigger is simply dead for the life of
    the card, and every test that does not exercise that trigger passes.

    `dispatch` filters on ``kinds`` before calling the hook, so ``events=frozenset({"defated"})``
    is a card whose DEFEATED clause silently does not exist. There is no runtime signal at all:
    no exception, no warning, and the script still loads.
    """
    kinds = _dispatched_kinds()
    bad = [f"{card} listens for {sorted(ev - kinds)}" for card, ev, _ in _pool_hooks() if ev - kinds]
    assert not bad, ("cards listening for an event the engine never dispatches:\n  "
                     + "\n  ".join(bad) + f"\n(the engine dispatches {sorted(kinds)})")


def test_no_hook_body_tests_for_an_event_its_filter_screens_out():
    """The narrower failure, and the one that survives review: the filter is a subset of what the
    body handles, so one branch of a two-branch hook is unreachable.

    ``events=frozenset({"end_turn"})`` on a hook whose body reads
    ``if e[0] == "start_turn": ... elif e[0] == "end_turn": ...`` implements half the card. The
    body looks complete to a reader, the filter looks harmless, and only the pair is wrong — which
    is exactly the shape no single-card review catches.
    """
    bad = [f"{card}: body tests {sorted(t - ev)} but events= is {sorted(ev)}"
           for card, ev, t in _pool_hooks() if t - ev]
    assert not bad, "hooks with an unreachable branch:\n  " + "\n  ".join(bad)


def test_the_event_filter_lints_can_fire_and_read_named_hooks():
    """Both lints above report zero over the pool, so they are only worth having if shown to bite —
    and the census is part of the claim: 38 cards carry a hook, 32 of them re-test ``e[0]``, which
    is what the second lint reads. A detector that quietly matched nothing would report the same
    zero."""
    import textwrap

    rows = _pool_hooks()
    assert len(rows) >= 30, f"only {len(rows)} hooks found; the scan is broken"
    assert sum(1 for _, _, t in rows if t) >= 25, "almost no hook bodies were parsed"

    planted = textwrap.dedent('''
        @script("typo-card")
        def _():
            def ev(c, e):
                if e[0] == "defated":
                    c.draw(1)
            return CardScript(on_event=ev, events=frozenset({"defated"}))


        @script("half-dead-card")
        def _():
            def ev(c, e):
                if e[0] == "start_turn":
                    c.draw(1)
                elif e[0] == "end_turn":
                    c.draw(2)
            return CardScript(on_event=ev, events=frozenset({"end_turn"}))
        ''')
    rows = {card: (ev, t) for card, ev, t in _event_hooks(planted)}
    assert rows["typo-card"][0] - _dispatched_kinds() == {"defated"}
    ev, tested = rows["half-dead-card"]
    assert tested - ev == {"start_turn"}, "the named-hook body was not read"


# ------------------------------------------- "the next time ... this turn" must be spent
#: The printed wording that promises a ONE-SHOT: it fires once and is gone, whether or not the
#: turn ends first. Four cards in the set say it, and two of them were wrong in different ways --
#: Gunpoint Diplomacy granted its permission for the whole turn, and Reboot Optics' shield was
#: consumed only by a fight it actually saved a Unit from, so a fight it could not have saved
#: anyone from left it standing for the next one.
_NEXT_TIME = re.compile(r"the next time\b.*\bthis turn", re.I | re.S)


def _mods_written(source: str, card: str) -> set[str]:
    """Every ``c.mod("kind", ...)`` the named card's script writes."""
    tree = ast.parse(source)
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        if not any(isinstance(d, ast.Call) and getattr(d.func, "id", "") == "script"
                   and d.args and d.args[0].value == card for d in fn.decorator_list):
            continue
        return {n.args[0].value for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "mod"
                and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)}
    return set()


def test_every_one_shot_effect_has_something_that_spends_it(pool):
    """A "the next time ... this turn" effect that nothing removes lasts the whole turn.

    There is no runtime signal for this either: the mod is written, it is read, the effect works —
    it simply keeps working. The bug is the *absence* of a removal, which is the hardest kind of
    thing to see in a card script, because there is nothing on the screen to be wrong.

    So: for each such card, either the script registers a ``listener`` that removes itself, or it
    writes a mod kind that some site under `src/cptcg/core` removes. The removal idiom in this
    engine is a list comprehension over ``s.mods`` testing ``m[0] == "kind"``, and that is what is
    searched for.
    """
    core = "\n".join(p.read_text(encoding="utf-8")
                     for p in sorted((SETS_DIR.parents[1] / "core").glob("*.py")))
    sources = {p.stem: p.read_text(encoding="utf-8") for p in sorted(SETS_DIR.glob("*.py"))}
    bad, checked = [], []
    for d in pool.defs:
        if not _NEXT_TIME.search(d.text or ""):
            continue
        checked.append(d.id)
        written = set()
        for src in sources.values():
            written |= _mods_written(src, d.id)
        if not written:
            bad.append(f"{d.id}: says 'the next time ... this turn' and writes no mod at all")
            continue
        spent = []
        for kind in written:
            if kind == "listener":
                # a self-removing listener: the body drops the entry whose value is itself
                spent.append(any('m[2] is listen' in src or "m[2] is not listen" in src
                                 for src in sources.values()))
            else:
                spent.append(f'm[0] == "{kind}"' in core)
        if not any(spent):
            bad.append(f"{d.id}: writes {sorted(written)}, and nothing removes any of them")
    assert len(checked) >= 4, f"the wording scan found only {checked}; the pool has four such cards"
    assert not bad, "one-shot effects nothing spends:\n  " + "\n  ".join(bad)


def test_the_one_shot_lint_would_have_caught_gunpoint_diplomacy():
    """It is not a lint that has never fired: it fires on the tree as it stood this morning.

    Four cards print the wording and each is spent by a different mechanism — a self-removing
    listener (Appetite for Destruction), and three engine-side removals. Before
    `ResolveAttackStep` learned to retire it, `attack_ready_units` had no removal site anywhere in
    `src/cptcg/core`, which is exactly what this check looks for and exactly what was wrong.
    """
    core = "\n".join(p.read_text(encoding="utf-8")
                     for p in sorted((SETS_DIR.parents[1] / "core").glob("*.py")))
    wnc = (SETS_DIR / "wnc.py").read_text(encoding="utf-8")
    expect = {"gunpoint-diplomacy": "attack_ready_units",
              "reboot-optics": "next_fight_no_defeat",
              "safety-override": "next_loss_defeats_winner"}
    for card, kind in expect.items():
        assert _mods_written(wnc, card) == {kind}, card
        assert f'm[0] == "{kind}"' in core, f"{card}: nothing spends {kind}"
    assert _mods_written(wnc, "appetite-for-destruction") == {"listener"}
    assert "m[2] is listen" in wnc, "the self-removing listener idiom is gone"

    # and the check is not vacuous: a kind nothing removes is reported as unspent
    assert 'm[0] == "no_such_mod_kind"' not in core


# ------------------------------------------------- a steal that no protection effect can see
def _steal_sites(source: str) -> list[tuple[str, int]]:
    """``(card id, line)`` for every ``push_steals`` call in a card script whose candidate indices
    did not come from ``stealable``.

    ``steps.stealable`` is where the two protection effects in this set are applied — Chrome Fang's
    "rival Units can't steal friendly Gigs with value higher than their power" and Westbrook
    Netrunner's mirror of it for Legends. The attack path goes through it. An effect that pushes a
    steal of its own has to as well, or the prohibition is enforced on one path out of several and
    the printed text is simply false on the others.

    The check is deliberately crude: within each ``@script`` block, if ``push_steals`` is called and
    ``stealable`` is never called, the card steals without consulting protection. A card that calls
    both and then ignores the result would slip through, but nothing in the set does that, and a
    lint that is easy to read is worth more here than one that is hard to fool.
    """
    out = []
    for cid, fn in _script_defs(source).items():
        pushes = _method_calls(fn, "push_steals")
        if pushes and not _method_calls(fn, "stealable"):
            out.append((cid, pushes[0].lineno))
    return out


def test_every_effect_driven_steal_goes_through_the_protection_gate(pool):
    """A prohibition is a claim about every path that could break it.

    "Rival Units can't steal friendly Gigs with value higher than their power" is not verifiable
    from Chrome Fang's own script — that script only *records* the protection. Whether it is
    *consulted* is a fact about the cards that steal, and this is the check that asks them.

    The set contains exactly two effect-driven steals and they disagree with each other:
    ``appetite-for-destruction`` routes its candidates through ``stealable`` and
    ``gorilla-arms`` does not. Nothing in either printed text distinguishes them, and no row of
    docs/rulings.md covers it, which is why the inconsistency is read as a bug rather than a
    ruling.

    Fixed: AUD-gorilla-arms-2. Both effect-driven steals route through the gate now, and this lint
    is what will catch the third one on the day it is written.
    """
    src = (SETS_DIR / "wnc.py").read_text(encoding="utf-8")
    bad = _steal_sites(src)
    assert not bad, ("cards that steal without consulting the protection gate:\n  "
                     + "\n  ".join(f"{cid} (wnc.py:{line})" for cid, line in bad))
