"""The card-behaviour fingerprint: recorded everywhere, enforced nowhere.

``RulesConfig.digest()`` exists so that changing a ruling *visibly* invalidates comparisons with
older runs instead of quietly shifting them, and ``Replay.load`` refuses a mismatch. Card behaviour
was never in that hash — so a card-script fix changed what the game is, every bit as much as
flipping a ruling does, and did it silently across every stored replay, league table, arena result
and fitted model.

These tests pin both halves of the fix: the digest moves when behaviour moves, and nothing compares
it yet, because enforcing it on the day it was introduced would reject every artifact already on
disk.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cptcg.cards import registry  # noqa: E402
from cptcg.cards.registry import cards_digest  # noqa: E402
from cptcg.core.config import DEFAULT_CONFIG  # noqa: E402
from cptcg.sim.record import Replay, _deck  # noqa: E402


def _fresh() -> str:
    registry._CARDS_DIGEST = None
    try:
        return cards_digest()
    finally:
        registry._CARDS_DIGEST = None


def test_it_is_stable_and_short():
    a, b = _fresh(), _fresh()
    assert a == b and len(a) == 16
    assert a == cards_digest()          # and the cached path agrees with the cold one


def test_changing_a_card_text_changes_it(tmp_path, monkeypatch):
    """The printed data is half of what a card *is*."""
    before = _fresh()
    src = registry.DATA_DIR
    copy = tmp_path / "cards"
    copy.mkdir()
    for f in src.glob("*.json"):
        raw = json.loads(f.read_text(encoding="utf-8"))
        cards = raw["cards"] if isinstance(raw, dict) else raw
        cards[0]["text"] = (cards[0].get("text") or "") + " (nudged)"
        (copy / f.name).write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(registry, "DATA_DIR", copy)
    assert _fresh() != before


def test_changing_a_script_changes_it(tmp_path, monkeypatch):
    """Behaviour is the other half, and the half nothing else fingerprints."""
    before = _fresh()
    copy = tmp_path / "sets"
    copy.mkdir()
    for f in registry.SETS_DIR.glob("*.py"):
        (copy / f.name).write_text(f.read_text(encoding="utf-8") + "\n# nudged\n", encoding="utf-8")
    monkeypatch.setattr(registry, "SETS_DIR", copy)
    assert _fresh() != before


def test_it_is_recorded_on_a_replay():
    r = Replay(seed=1, decks=({}, {}), actions=[0, 1, 2])
    assert r.cards == "" and Replay(seed=1, decks=({}, {}), actions=[], cards=cards_digest()).cards


def test_it_is_not_enforced_when_a_replay_is_walked(tmp_path, pool):
    """Recorded, not compared — deliberately, and this is the test that says so.

    Every replay, harvested game and fitted model already on disk predates the digest. Enforcing it
    now would reject all of them at once, including the committed experience sample and the shipped
    weights. A future decision to enforce should be a deliberate one-line change with a migration,
    not something that happens the moment this field appears.
    """
    from cptcg.deck.decklist import Decklist

    a = Decklist.load(Path("data/decks/sample_gangers.json"))
    b = Decklist.load(Path("data/decks/sample_netrunners.json"))
    r = Replay(seed=11, decks=(_deck(a), _deck(b)), actions=[], cards="deadbeefdeadbeef")
    p = tmp_path / "r.json"
    r.save(p)
    loaded = Replay.load(p)
    assert loaded.cards == "deadbeefdeadbeef"
    list(loaded.steps(pool, DEFAULT_CONFIG))        # a wrong cards digest must NOT raise


def test_a_wrong_rules_digest_still_does_raise(tmp_path, pool):
    """The control: the enforcement that already exists is untouched by adding a second field."""
    from cptcg.deck.decklist import Decklist

    a = Decklist.load(Path("data/decks/sample_gangers.json"))
    b = Decklist.load(Path("data/decks/sample_netrunners.json"))
    r = Replay(seed=11, decks=(_deck(a), _deck(b)), actions=[])
    r.rules = "notarealruleset"
    p = tmp_path / "r.json"
    r.save(p)
    with pytest.raises(ValueError, match="ruleset"):
        list(Replay.load(p).steps(pool, DEFAULT_CONFIG))
