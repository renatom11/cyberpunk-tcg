"""Everything under ``tests/cards/audit/`` is a finding, and a finding is red.

The audit directory has one job: hold a failing test per open finding, each marked
``xfail(strict=True)`` so the suite stays green while findings are open and pytest reports XPASS as
a failure the moment a fix makes one pass. That is the mechanism that makes a fix impossible to land
without deleting the marker, which is in turn the git record of red-before and green-after.

Two ways that quietly stops working, and both have happened while the audit was being written:

* a **probe** — an unmarked test someone left behind while exploring. It either fails, which turns
  the suite red for a reason unrelated to any finding, or passes, which puts a test asserting
  current behaviour into the directory that exists to assert *desired* behaviour;
* a **non-strict xfail**, which never reports XPASS and so lets a fix land silently, leaving a
  stale marker behind that the next reader takes for an open finding.

Neither is caught by running the tests, because both are green. So it is checked structurally.

Two kinds of unmarked test are legitimate, and both have to declare themselves.

A **control** is a passing test whose job is to show that the failing test beside it fails for the
reason claimed and not because its board was broken — Maelstrom Zealots losing a fight *decisively*
does defeat the winner, so the xfail about a tied fight is about ties. A control belongs next to the
finding it controls for, where a reader meets both at once, so it stays in the findings file and
declares itself in its docstring.

A **confirmation** is what an audit produces when it suspects a card, writes the test, and finds the
engine right: coverage the pool did not have, paid for out of the audit. The plan calls this class
S-SUSPICION and calls it the most dangerous to act on, since an agent that "knows" a card is wrong
and cannot make it fail will reach for the engine next — which is exactly why the passing test is
worth writing down. Those go in ``test_confirmed_*.py``, so that "this is how it behaves" and "this
is how it should behave" never sit unlabelled in the same directory.
"""
import ast
import sys
from pathlib import Path

AUDIT = Path(__file__).resolve().parent / "audit"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def _xfail(dec: ast.AST) -> ast.Call | None:
    """The ``pytest.mark.xfail(...)`` call in a decorator, or None."""
    if isinstance(dec, ast.Call) and ast.unparse(dec.func).endswith("mark.xfail"):
        return dec
    return None


def test_every_audit_test_is_a_strict_xfail_naming_its_finding():
    bad = []
    seen_ids = {}
    for path in sorted(AUDIT.glob("test_*.py")):
        if path.name.startswith("test_confirmed"):
            continue                 # passing scenarios, deliberately: see the module docstring
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            marks = [m for m in (_xfail(d) for d in node.decorator_list) if m is not None]
            where = f"{path.name}::{node.name}"
            if not marks:
                doc = (ast.get_docstring(node) or "").strip()
                if doc.lower().startswith("control") or "AUD-" in doc:
                    continue                  # a control for a finding: see the module docstring
                bad.append(f"{where}: no xfail marker, and the docstring neither starts with "
                           f"'Control' nor names an AUD- finding. If the finding was fixed, keep "
                           f"its id in the docstring; if the engine was right all along, move the "
                           f"test to test_confirmed_*.py.")
                continue
            kw = {k.arg: k.value for k in marks[0].keywords}
            strict = kw.get("strict")
            if not (isinstance(strict, ast.Constant) and strict.value is True):
                bad.append(f"{where}: xfail is not strict, so a fix would land silently")
            reason = kw.get("reason")
            try:
                text = ast.literal_eval(reason) if reason is not None else ""
            except ValueError:
                text = ast.unparse(reason)          # an f-string or a join; read what we can
            if not text.startswith("AUD-"):
                bad.append(f"{where}: reason does not start with a finding id (AUD-...)")
            else:
                fid = text.split(":")[0].strip()
                seen_ids.setdefault(fid, []).append(where)
    for fid, wheres in seen_ids.items():
        if len(wheres) > 1:
            bad.append(f"{fid} is claimed by {len(wheres)} tests: {', '.join(wheres)}")
    assert not bad, "the audit directory is not all findings:\n  " + "\n  ".join(bad)


def test_the_audit_directory_is_not_empty_and_says_what_it_is():
    """A guard that passes by finding nothing is the failure this whole workstream is about."""
    assert (AUDIT / "README.md").exists(), "the directory has to explain its own convention"
    files = [p for p in sorted(AUDIT.glob("test_*.py"))
             if not p.name.startswith("test_confirmed")]
    assert files, "no finding files — this test would otherwise pass by checking nothing"
