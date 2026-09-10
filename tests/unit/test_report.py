"""The words a reader sees: summary sentences, significance wording, names instead of ids,
no duplicated card rows, and old (version 1) files that still load and render."""
import json
from pathlib import Path

import pytest

from cptcg.cards.registry import load_default
from cptcg.deck.decklist import Decklist
from cptcg.sim.report import (card_name, deck_profile_json, render_report, sig_word, summarize,
                              top_and_bottom)
from cptcg.sim.tournament import CardStat, Cell, Tournament, run_tournament

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def reg():
    return load_default()


def _decks(k=3):
    return [Decklist.load(p) for p in sorted((ROOT / "data/decks").glob("sample_*.json"))[:k]]


def _cell(i, j, wins, n):
    return Cell(i, j, wins, n, "high" if wins > n / 2 else "continue", wins // 2, n // 2, 12 * n)


def synthetic(reg, n_cards=10):
    """Three decks with hand-set results: deck 0 crushes deck 1, edges deck 2 on few games,
    decks 1 and 2 split evenly. Deck 0 carries a personality label."""
    a, b, c = _decks(3)
    a = Decklist(a.name, a.legends, a.main, {"strategy": "aggro"})
    cells = {(0, 1): _cell(0, 1, 34, 40), (0, 2): _cell(0, 2, 14, 20), (1, 2): _cell(1, 2, 20, 40)}
    stats = {}
    for k, cid in enumerate(sorted(set(a.main))[:n_cards]):
        stats[cid] = CardStat(drawn_games=30, drawn_wins=25 - k, other_games=30, other_wins=15)
    return Tournament([a, b, c], "random", 7, cells, [stats, {}, {}])


def test_sig_word_thresholds_and_small_sample_note():
    assert sig_word(0.005, 100) == "very solid"
    assert sig_word(0.03, 100) == "solid"
    assert sig_word(0.1, 100) == "suggestive"
    assert sig_word(0.5, 100) == "not established"
    assert sig_word(0.005, 20) == "very solid (only 20 games)"
    assert sig_word(0.5, 29) == "not established (only 29 games)"
    assert sig_word(0.5, 30) == "not established"


def test_top_and_bottom_never_repeats_a_row():
    assert top_and_bottom(list(range(8))) == list(range(8))
    assert top_and_bottom(list(range(3))) == [0, 1, 2]
    assert top_and_bottom(list(range(9))) == [0, 1, 2, 3, 4, None, 6, 7, 8]
    assert top_and_bottom(list(range(20))) == [0, 1, 2, 3, 4, None, 17, 18, 19]


def test_summary_sentences_on_a_synthetic_tournament(reg):
    t = synthetic(reg)
    names = [d.name for d in t.decks]
    lines = summarize(t, reg)
    assert lines[0].startswith(f"{names[0]} (aggro) is the strongest deck in this run: it won 80% of its 60 games")
    assert lines[0].endswith("and beat every other deck.")
    text = "\n".join(lines)
    assert f"{names[1]} (85% of 40 games)" in text and "statistically very solid" in text
    assert f"{names[2]} (70% of 20 games)" in text and "could" in text            # 14/20 is not settled
    assert "bring" in text and names[0] in text.split("bring")[1]
    assert "small run (100 games in all, under 40 per matchup)" in text
    # the same sentences are what the JSON stores
    assert t.to_json(reg)["summary"] == lines


def test_report_uses_card_names_not_ids_and_has_every_section(reg):
    t = synthetic(reg)
    rep = render_report(t, "Synthetic", reg)
    for heading in ("## What was run", "## Summary", "## Standings", "## Head-to-head", "## The decks",
                    "## Cards that helped and hurt", "## How to read this report", "| Archetype |"):
        assert heading in rep
    for deck in t.decks:
        for cid in list(deck.main) + list(deck.legends):
            assert f"| {cid} |" not in rep and f"× {cid} " not in rep
            assert card_name(reg, cid) in rep
    leg = reg.get(t.decks[0].legends[0])
    assert leg.subtitle and f"{leg.name} — {leg.subtitle}" in rep
    assert "**85%** (40)" in rep                                              # significant cell in bold
    assert "aggro" in rep and "Strength" in rep and "Bring it?" in rep


def test_card_table_prints_each_card_once(reg):
    for n_cards, expect_ellipsis in ((8, False), (6, False), (10, True)):
        t = synthetic(reg, n_cards)
        rep = render_report(t, "Synthetic", reg)
        table = rep.split("## Cards that helped and hurt")[1].split("## How to read")[0]
        assert ("| … |" in table) is expect_ellipsis
        rows = [ln for ln in table.splitlines() if ln.startswith("| ") and not ln.startswith("| Card") and "…" not in ln]
        cards = [ln.split(" | ")[0][2:] for ln in rows]
        assert len(cards) == len(set(cards)) == (8 if n_cards > 8 else n_cards)


def test_profile_and_names(reg):
    d = _decks(1)[0]
    prof = deck_profile_json(d, reg)
    assert sum(prof["curve"]) == len(d.main) == prof["cards"] == sum(prof["types"].values())
    assert 0 <= prof["sell_share"] <= 1 and prof["sell_tags"] == round(prof["sell_share"] * len(d.main))
    assert card_name(reg, "no-such-card") == "no-such-card"
    assert deck_profile_json(Decklist("x", d.legends, ("no-such-card",)), reg) is None


def test_round_trip_and_info(reg, tmp_path):
    t = run_tournament(_decks(3), agent="random", games_per_pair=8, seed=3, workers=1)
    assert t.info["games_per_pair"] == 8 and t.info["sprt"] is None and t.info["total_games"] == 24
    t.info["title"] = "Round trip"
    t.paths = ["a.json", None, None]
    t.save(tmp_path / "t.json", reg)
    data = json.loads((tmp_path / "t.json").read_text())
    assert data["version"] == 2 and data["decks"][0]["path"] == "a.json" and data["decks"][1]["path"] is None
    assert data["decks"][0]["profile"]["cards"] == len(t.decks[0].main)
    back = Tournament.load(tmp_path / "t.json")
    assert back.info["title"] == "Round trip" and back.paths == t.paths
    assert back.wins_matrix() == t.wins_matrix() and back.bt() == t.bt() and back.standings() == t.standings()
    assert {c: (s.drawn_games, s.drawn_wins) for c, s in back.card_stats[0].items()} == \
        {c: (s.drawn_games, s.drawn_wins) for c, s in t.card_stats[0].items()}
    again = back.to_json(reg)
    for key in ("decks", "cells", "field", "bradley_terry", "nash", "standings", "summary", "cards"):
        assert again[key] == data[key], key
    assert render_report(back, reg=reg).startswith("# Round trip")


def test_version_1_file_loads_and_renders(reg):
    path = ROOT / "out/league_demo/gen1/tournament.json"
    raw = json.loads(path.read_text())
    assert "version" not in raw and "summary" not in raw
    t = Tournament.load(path)
    assert t.n() == 4 and t.info == {} and all(p is None for p in t.paths)
    assert all(c.n == 40 for c in t.cells.values()) and t.cells[(0, 1)].turns == round(40 * raw["cells"][0]["avg_turns"])
    rep = render_report(t, reg=reg)
    assert rep.startswith("# Tournament") and "Standings" in rep and "Head-to-head" in rep
    assert "Dexter DeShawn — Off the Grid" in rep and "| dexter-deshawn" not in rep
    data = t.to_json(reg)
    assert data["version"] == 2 and data["summary"][0].startswith("builder1 is the strongest deck")


def test_api_report_upgrades_a_version_1_file():
    from cptcg.web import backend
    data = backend.report_json(ROOT / "out/league_demo/gen1/tournament.json")
    assert data["version"] == 2 and data["summary"] and data["markdown"].startswith("#")
    d0 = data["decks"][0]
    assert d0["meta"]["generated"] == "heuristic"                    # pulled from the sibling builder1.json
    assert d0["path"] == "out/league_demo/gen1/builder1.json" and d0["profile"]["cards"] == 40
    assert data["file"] == "out/league_demo/gen1/tournament.json" and "league_series" not in data
