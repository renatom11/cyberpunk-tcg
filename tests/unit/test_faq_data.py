"""The official FAQ, as data: it must stay attached to real cards and stay faithful to the source.

``data/faq.txt`` is the authority, transcribed verbatim. ``data/faq.json`` is generated from it and
committed, because everything downstream -- the triage, the tests it produces, the card guide --
reads the JSON. A committed generated file drifts the moment somebody edits one and not the other,
so the first test here regenerates and compares.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

FAQ = json.loads((ROOT / "data" / "faq.json").read_text(encoding="utf-8"))


def test_every_faq_names_a_card_that_exists(pool):
    """A heading that no longer matches a card silently drops that card's rulings."""
    unknown = [cid for cid in FAQ["cards"] if cid not in pool.by_id]
    assert not unknown, unknown


def test_the_json_still_matches_the_verbatim_source():
    """Regenerating must be a no-op, or the committed JSON has drifted from data/faq.txt."""
    before = (ROOT / "data" / "faq.json").read_text(encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "faq_to_json.py")],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    after = (ROOT / "data" / "faq.json").read_text(encoding="utf-8")
    assert before == after, "data/faq.json is stale — re-run tools/faq_to_json.py and commit it"


def test_every_entry_has_a_question_and_an_answer():
    bad = []
    for entry in FAQ["general"]:
        if not entry.get("q", "").strip() or not entry.get("a", "").strip():
            bad.append(("general", entry))
    for cid, entries in FAQ["cards"].items():
        for entry in entries:
            if not entry.get("q", "").strip() or not entry.get("a", "").strip():
                bad.append((cid, entry))
    assert not bad, bad


def test_entries_with_a_missing_icon_are_marked_rather_than_guessed():
    """The gap where a keyword symbol was must be flagged, never silently filled in.

    An icon guessed wrong here would become a test asserting the wrong rule — worse than no test.
    This pins the property that anything with a visible gap carries the flag, so the triage can
    skip exactly those and nothing else.
    """
    import re
    gap = re.compile(r"  +|\s+[?.,]")
    wrong = []
    for cid, entries in [("general", FAQ["general"])] + list(FAQ["cards"].items()):
        for e in entries:
            looks_gapped = bool(gap.search(e["q"]) or gap.search(e["a"]))
            if looks_gapped and not e.get("icons_missing"):
                wrong.append((cid, e["q"], "gapped but not flagged"))
            if e.get("icons_missing") and not looks_gapped:
                wrong.append((cid, e["q"], "flagged but no gap"))
    assert not wrong, wrong[:6]


def test_the_faq_covers_most_of_the_pool(pool):
    """A sanity floor, so a parser regression that drops half the file is loud rather than subtle."""
    assert len(FAQ["cards"]) >= 130, f"only {len(FAQ['cards'])} cards carry FAQ entries"
    assert len(FAQ["general"]) >= 20, f"only {len(FAQ['general'])} general entries"
