from pathlib import Path

from cptcg.deck.decklist import Decklist
from cptcg.sim.runner import run_match

ROOT = Path(__file__).resolve().parents[2]


def _decks():
    return (Decklist.load(ROOT / "tests/fixtures/decks/sample_arasaka.json"),
            Decklist.load(ROOT / "tests/fixtures/decks/sample_mercs.json"))


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


def test_external_executor_gives_identical_results(monkeypatch):
    """The browser build hands chunks to an external executor as JSON; results must round-trip
    exactly and match the in-process run."""
    import json
    from cptcg.deck.decklist import Decklist
    from cptcg.sim import runner
    a = Decklist.load("data/decks/the_heist.json")
    b = Decklist.load("data/decks/embracing_power.json")
    ref = runner.run_match(a, b, "random", "random", 12, seed=3, workers=1, record=True)

    def executor(jobs_json):
        return json.dumps([json.loads(runner.run_chunk_json(json.dumps(j))) for j in json.loads(jobs_json)])
    monkeypatch.setattr(runner, "EXECUTOR", executor)
    before = runner.GAMES_PLAYED
    got = runner.run_match(a, b, "random", "random", 12, seed=3, workers=4, record=True)
    assert [(r.seed, r.deck_a_seat, r.winner_deck, r.turns, r.replay.actions, r.drawn_a) for r in got.results] == \
           [(r.seed, r.deck_a_seat, r.winner_deck, r.turns, r.replay.actions, r.drawn_a) for r in ref.results]
    assert runner.GAMES_PLAYED - before == 12


def test_jackie_mamas_favorite_save_when_the_last_eddie_is_gone():
    """Jackie Welles (Mama's Favorite) offers 'pay 1 to defeat Jackie instead' while 1 €$ is
    available; the heuristic agent's lookahead can spend that Eddie before the pick is applied.
    The replacement must then fall back to the normal defeat instead of raising in pay()."""
    a = Decklist.load(ROOT / "tests/fixtures/decks/jackie_pay_a.json")
    b = Decklist.load(ROOT / "tests/fixtures/decks/jackie_pay_b.json")
    m = run_match(a, b, "heuristic", "heuristic", 1, seed=720003, workers=1)
    assert m.n == 2 and all(r.winner_deck in ("A", "B") for r in m.results)
