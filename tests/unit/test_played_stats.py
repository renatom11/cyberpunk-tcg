"""What a card *did*, not what it was next to.

Every per-card number this project has ever produced — ``out/knowledge.json``, every league report,
every IWD ranking — was conditioned on **drawing** a card. That statistic counts a game where an
expensive card sat in hand all game exactly like a game where it was cast for value, and it cannot
speak about a Legend at all, because a Legend is never drawn: ``record_game`` iterates ``deck.main``,
which excludes them by construction.

So the engine now logs what was actually played, and these tests pin the whole chain: the log itself,
its survival through ``clone()`` (a search that shared it with the real game would corrupt the
record), its arrival in ``GameResult`` **keyed by owner**, and its arrival in ``CardStat`` including
Legends. The last test is about a bug found while wiring this up rather than about play rates.
"""
from pathlib import Path

from cptcg.deck.decklist import Decklist
from cptcg.sim.runner import result_from_json, result_to_json, run_match
from cptcg.sim.tournament import CardStat, Tournament, run_tournament

ROOT = Path(__file__).resolve().parents[2]


def _decks():
    return (Decklist.load(ROOT / "tests/fixtures/decks/sample_arasaka.json"),
            Decklist.load(ROOT / "tests/fixtures/decks/sample_mercs.json"))


def test_played_log_records_plays_and_is_not_shared_with_clones():
    """A cloned state may not write into the real game's record, and vice versa.

    Search clones millions of states per decision and plays cards in all of them. A shared list
    would make the log a record of everything the *agent imagined*, which is both wrong and
    unbounded — and would look plausible in aggregate, which is the dangerous part.
    """
    from cptcg.cards.registry import load_default
    from cptcg.core.engine import apply, legal_actions
    from cptcg.sim.runner import new_game

    reg = load_default()
    a, b = _decks()
    s = new_game(reg, (a, b), 4242)
    from cptcg.agents.base import make_agent
    ags = [make_agent("heuristic", 7) for _ in (0, 1)]
    for i, ag in enumerate(ags):
        ag.new_game(7, i)
    n = 0
    while not s.over and n < 400 and not s.played_log:
        legal_actions(s)
        ch = s.pending
        if ch is None:
            break
        apply(s, ags[ch.player].act(s, ch))
        n += 1
    assert s.played_log, "a heuristic game with no card ever played is not a game"
    inst, by = s.played_log[0]
    assert by in (0, 1) and s.i_card[inst] >= 0

    before = list(s.played_log)
    c = s.clone()
    c.played_log.append((0, 0))
    assert s.played_log == before                     # the clone's play did not reach the real game
    s.played_log.append((1, 1))
    assert len(c.played_log) == len(before) + 1       # nor the other way


def test_results_carry_played_cards_by_owner_and_round_trip():
    a, b = _decks()
    m = run_match(a, b, "heuristic", "heuristic", 6, seed=17, workers=1)
    assert all(r.played_a for r in m.results) and all(r.played_b for r in m.results)
    a_ids, b_ids = set(a.main) | set(a.legends), set(b.main) | set(b.legends)
    for r in m.results:
        # by owner: a card is deck A's play even if a rival effect is what put it on the table.
        assert r.played_a <= a_ids and r.played_b <= b_ids
    r = m.results[0]
    assert result_from_json(result_to_json(r)).played_a == r.played_a

    # a file written before play was instrumented has neither key and must still load
    old = result_to_json(r)
    del old["played_a"], old["played_b"]
    assert result_from_json(old).played_a == frozenset()


def test_legends_get_numbers_for_the_first_time():
    """The point of the whole exercise: ``deck.main`` has no Legends in it."""
    t = run_tournament(_decks(), agent="heuristic", games_per_pair=8, seed=3, workers=1)
    a = t.decks[0]
    stats = t.card_stats[0]
    legends = [stats.get(cid) for cid in a.legends]
    assert all(s is not None for s in legends), "every Legend has a row"
    assert any(s.played_games for s in legends), "and at least one of them was Called or GO SOLO'd"
    assert all(s.drawn_games == 0 and s.other_games == 0 for s in legends), \
        "a Legend is never drawn; only its play counters are meaningful"
    # a main-deck card that was played was, by construction, also counted as present
    for cid, s in stats.items():
        if cid in a.legends:
            continue
        assert s.played_games <= s.drawn_games + s.other_games


def test_card_stat_rates():
    s = CardStat(drawn_games=10, drawn_wins=6, other_games=10, other_wins=4,
                 played_games=4, played_wins=3)
    assert s.gih == 0.6 and s.gnd == 0.4 and abs(s.iwd - 0.2) < 1e-12
    assert s.gip == 0.75 and s.play_rate == 0.4
    assert CardStat().gip is None and CardStat().play_rate is None


def test_tournament_json_keeps_both_the_digest_and_the_card_stats(tmp_path):
    """Found while wiring play stats in: ``to_json`` spelled the cards *digest* and the cards
    *statistics* with the same key, so the later one won and the digest silently vanished from
    every league file — the exact failure the digest exists to prevent."""
    t = run_tournament(_decks(), agent="random", games_per_pair=4, seed=5, workers=1)
    d = t.to_json()
    from cptcg.cards.registry import cards_digest
    assert d["cards_digest"] == cards_digest()
    assert isinstance(d["cards"], list) and d["cards"]

    back = Tournament.from_json(d)
    for i, stats in enumerate(t.card_stats):
        for cid, s in stats.items():
            assert back.card_stats[i][cid].played_games == s.played_games
            assert back.card_stats[i][cid].played_wins == s.played_wins

    # and a file from before the counters existed loads with them at zero rather than raising
    for stats in d["cards"]:
        for row in stats.values():
            del row["played_games"], row["played_wins"]
    assert all(s.played_games == 0 for stats in Tournament.from_json(d).card_stats
               for s in stats.values())
