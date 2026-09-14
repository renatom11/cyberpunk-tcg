"""What a fresh clone must be able to run.

The suite was green on this machine for months while five tests in ``tests/unit/test_report.py``
read `out/league_demo/gen1/tournament.json` — a file in a **gitignored** directory, left behind by a
league someone ran once. On any fresh clone those five tests fail with `FileNotFoundError`, and
nobody found out until the suite was put in CI, because "it passes locally" is exactly the guarantee
a gitignored input quietly destroys.

So: no test may read from a path git does not track.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: A string literal that looks like a repository-relative path to a *file* under `out/`. The
#: extension is what makes it a file: `"out/lab/smoke-"` in tests/unit/test_web.py is a prefix the
#: test itself writes to, and a check that flagged it would be a check people learn to ignore.
_OUT_PATH = re.compile(r"""["'](out/[\w./-]+\.\w+)["']""")


def _tracked(path: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", path],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


def test_no_test_reads_a_file_git_does_not_track():
    """Every `out/...` path a test names must be tracked, or the test cannot run on a clone.

    Checked against `git ls-files` rather than against `.gitignore`, because what matters is
    whether the file arrives with the clone, not why it would not.
    """
    bad = []
    for p in sorted((ROOT / "tests").rglob("*.py")):
        if p.name == Path(__file__).name:
            continue
        text = p.read_text(encoding="utf-8")
        # A path named inside a `skipif` is declared optional: the file says out loud that it does
        # nothing without it. tests/learn/test_diagnose.py does this for the gen-1 weights, which
        # are a training output nobody wants in the repository.
        guarded = {m.group(1) for line in text.splitlines() if "skipif" in line
                   for m in _OUT_PATH.finditer(line)}
        for m in _OUT_PATH.finditer(text):
            if m.group(1) not in guarded and not _tracked(m.group(1)):
                bad.append(f"{p.relative_to(ROOT)}: reads untracked {m.group(1)!r}")
    assert not bad, ("tests that cannot run on a fresh clone:\n  " + "\n  ".join(bad)
                     + "\n(move the file under tests/fixtures/ and commit it)")


def test_the_committed_fixtures_are_actually_committed():
    """The positive half: the league fixture the report tests read is tracked, so the check above
    is testing a condition that can be met rather than one nothing satisfies."""
    for gen in ("gen1", "gen2"):
        assert _tracked(f"tests/fixtures/league_demo/{gen}/tournament.json")
