"""The official FAQ, as data: it must stay attached to real cards and stay faithful to the source.

``data/faq.txt`` is the authority, rebuilt from the published PDF by ``tools/faq_from_pdf.py``
so the keyword icons survive. ``data/faq.json`` is generated from it and
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


#: Every keyword the FAQ prints as an icon. They were absent from the first capture, which was a
#: text paste; tools/faq_from_pdf.py recovers them from the PDF by measuring each chip.
ICONS = ("BLOCKER", "QUICK", "ADRENALINE", "GO SOLO", "PLAY", "ATTACK", "DEFEATED", "\u22a1")


def test_no_entry_is_still_missing_an_icon():
    """The gap where a keyword symbol was is gone, and must not come back.

    ``icons_missing`` used to be the flag that told the triage which 69 answers to skip. It reads 0
    now, and this is the guard: a hand-edit that reintroduces a gap fails here rather than quietly
    producing a test that asserts the wrong rule.
    """
    flagged = [(cid, e["q"]) for cid, entries in
               [("general", FAQ["general"])] + list(FAQ["cards"].items())
               for e in entries if e.get("icons_missing")]
    assert not flagged, flagged[:6]


def test_the_keyword_icons_are_actually_present():
    """A floor under the recovery, so a regression that drops the icons again is loud.

    Counted against the published document: 80 chips and 17 Spend Icons over its 47 pages.
    """
    blob = "\n".join(e["q"] + " " + e["a"] for cid, entries in
                     [("general", FAQ["general"])] + list(FAQ["cards"].items()) for e in entries)
    missing = [k for k in ICONS if k not in blob]
    assert not missing, f"the FAQ no longer mentions {missing}"
    assert sum(blob.count(k) for k in ICONS) >= 90


def test_the_client_serves_each_card_its_own_faq():
    """The answers have to reach the card sheet, which is where the question comes up."""
    from cptcg.web import backend
    assert backend.faq()["cards"], "backend.faq() found nothing"
    d = backend.reg().get("detonate")
    j = backend.card_json_static(d)
    assert j["faq"], "detonate's FAQ entries did not reach card_json_static"
    assert any("face-up Legend" in e["q"] for e in j["faq"])
    status, body = backend.dispatch("GET", "/api/faq", {}, {})
    assert status == 200 and len(body["general"]) >= 20
