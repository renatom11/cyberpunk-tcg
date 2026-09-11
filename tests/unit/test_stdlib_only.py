"""``src/cptcg`` imports nothing but the standard library. The Pyodide constraint, as a test.

``tools/build_site.py`` zips this package and Pyodide unzips it in a phone browser. There is no
pip there and no wheel to fetch, so a single ``import numpy`` anywhere under ``src/cptcg`` does not
fail at review — it fails silently in CI (where numpy *is* installed, for the trainer) and then
breaks the site for every visitor. That asymmetry is exactly why this is a test and not a rule in a
document.

The training half of the loop is allowed numpy and uses it: it lives in ``tools/``, which is never
shipped.
"""

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "cptcg"

#: Everything the package may import. ``cptcg`` is itself; the rest is the standard library as
#: this interpreter defines it, so the list never has to be maintained by hand.
ALLOWED = set(sys.stdlib_module_names) | {"cptcg"}


def modules():
    for p in sorted(SRC.rglob("*.py")):
        yield p, ast.parse(p.read_text(encoding="utf-8"), filename=str(p))


def imported_roots(tree):
    """Top-level package name of every import, wherever it sits — including inside a function,
    which is where a lazy dependency would hide."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                yield n.name.split(".")[0], node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:                       # a relative import is inside the package
                continue
            yield (node.module or "").split(".")[0], node.lineno


def test_every_import_under_src_is_stdlib_or_cptcg():
    bad = []
    for path, tree in modules():
        for root, lineno in imported_roots(tree):
            if root and root not in ALLOWED:
                bad.append(f"{path.relative_to(SRC.parent.parent)}:{lineno}: import {root}")
    assert not bad, ("src/cptcg must be pure stdlib — it runs under Pyodide in a phone browser "
                     "with no package manager:\n  " + "\n  ".join(bad))


def test_numpy_is_not_importable_from_the_shipped_package():
    """The specific case worth naming: numpy is what the trainer uses, so it is the one that would
    drift across the line."""
    hits = [str(p) for p, tree in modules()
            if any(root == "numpy" for root, _ in imported_roots(tree))]
    assert not hits, hits


def test_the_package_really_does_import_with_nothing_installed():
    """A cheap end-to-end: import every module and let a missing dependency raise here rather
    than in a browser console."""
    import importlib

    failed = {}
    for p, _tree in modules():
        rel = p.relative_to(SRC.parent)
        name = ".".join(rel.with_suffix("").parts)
        if name.endswith(".__init__"):
            name = name[: -len(".__init__")]
        try:
            importlib.import_module(name)
        except Exception as e:                   # pragma: no cover - the assert is the report
            failed[name] = repr(e)
    assert not failed, failed
