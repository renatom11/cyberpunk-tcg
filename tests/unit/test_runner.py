from pathlib import Path

from cptcg.deck.decklist import Decklist
from cptcg.sim.runner import run_match

ROOT = Path(__file__).resolve().parents[2]


def _decks():
    return (Decklist.load(ROOT / "data/decks/sample_arasaka.json"),
            Decklist.load(ROOT / "data/decks/sample_mercs.json"))


def test_match_is_mirrored_and_reproducible():
    a, b = _decks()
    m1 = run_match(a, b, "random", "random", 8, seed=5, workers=1)
    m2 = run_match(a, b, "random", "random", 8, seed=5, workers=1)
    assert m1.n == 8 and [r.winner_deck for r in m1.results] == [r.winner_deck for r in m2.results]
    seats = [(r.seed, r.deck_a_seat) for r in m1.results]
    assert seats == sorted(seats) and sum(1 for r in m1.results if r.deck_a_seat == 0) == 4


def test_parallel_matches_serial():
    a, b = _decks()
    serial = run_match(a, b, "random", "random", 12, seed=11, workers=1)
    parallel = run_match(a, b, "random", "random", 12, seed=11, workers=3)
    assert [(r.seed, r.deck_a_seat, r.winner_deck, r.turns) for r in serial.results] == \
           [(r.seed, r.deck_a_seat, r.winner_deck, r.turns) for r in parallel.results]


def test_heuristic_beats_random_clearly():
    a, b = _decks()
    m = run_match(a, b, "heuristic", "random", 40, seed=1, workers=1)
    assert m.a_wins >= 32                                    # ~95% in practice; 80% is a safe floor


def test_replays_recorded_when_asked():
    a, b = _decks()
    m = run_match(a, b, "random", "random", 2, seed=2, workers=1, record=True)
    assert all(r.replay is not None and r.replay.actions for r in m.results)
