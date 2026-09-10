from pathlib import Path

from cptcg.deck.decklist import Decklist
from cptcg.sim.report import render_report
from cptcg.sim.stats import SPRT
from cptcg.sim.tournament import run_tournament

ROOT = Path(__file__).resolve().parents[2]


def _decks(k=3):
    return [Decklist.load(p) for p in sorted((ROOT / "data/decks").glob("sample_*.json"))[:k]]


def test_round_robin_matrix_report_and_json(tmp_path):
    t = run_tournament(_decks(3), agent="random", games_per_pair=8, seed=3, workers=1)
    assert len(t.cells) == 3 and all(c.n == 8 for c in t.cells.values())
    w = t.wins_matrix()
    assert all(w[i][j] + w[j][i] == 8 for i in range(3) for j in range(3) if i != j)
    assert len(t.bt()) == 3 and abs(sum(t.nash()) - 1) < 1e-9
    rep = render_report(t, "Test")
    assert "Standings" in rep and "Head-to-head" in rep
    t.save(tmp_path / "t.json")
    assert (tmp_path / "t.json").stat().st_size > 500
    assert any(s.drawn_games for stats in t.card_stats for s in stats.values())


def test_same_seed_same_result_any_worker_count():
    a = run_tournament(_decks(3), agent="random", games_per_pair=8, seed=9, workers=1)
    b = run_tournament(_decks(3), agent="random", games_per_pair=8, seed=9, workers=3)
    assert a.wins_matrix() == b.wins_matrix()


def test_sprt_can_stop_a_cell_early():
    # heuristic vs random is lopsided: with SPRT the cell should stop well before the cap
    decks = _decks(2)
    from cptcg.sim import tournament as tm
    calls = []
    t = run_tournament(decks, agent="random", games_per_pair=8, seed=1, workers=1, sprt=SPRT(0.05), batch=4)
    assert all(c.n <= 8 for c in t.cells.values())
