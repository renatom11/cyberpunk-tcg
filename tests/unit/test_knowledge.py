import json

import pytest

from cptcg.cards.registry import load_default
from cptcg.core.rng import Pcg32
from cptcg.deck.builder import league
from cptcg.deck.decklist import Decklist
from cptcg.deck.hall_of_fame import HallOfFame, deck_signature
from cptcg.deck.knowledge import Evidence, Knowledge
from cptcg.deck.archetypes import ArchetypeStore
from cptcg.deck.strategies import Explorer, context_key
from cptcg.deck.validate import validate
from cptcg.sim.report import render_report
from cptcg.sim.tournament import run_tournament


@pytest.fixture(scope="module")
def reg():
    return load_default()


@pytest.fixture(scope="module")
def tourney(reg):
    rng = Pcg32(2)
    decks = [Explorer().build(reg, None, rng, name=f"x{i}") for i in range(4)]
    return run_tournament(decks, agent="random", games_per_pair=4, workers=1, seed=1)


def test_evidence_shrinks_toward_zero_by_effective_sample():
    e = Evidence(drawn_games=10, drawn_wins=8, other_games=10, other_wins=3)
    assert e.iwd == pytest.approx(0.5) and e.n_eff == pytest.approx(5.0)
    kn = Knowledge(k=30)
    kn.cards["x"] = e
    assert kn.value("x") == pytest.approx(0.5 * 5 / 35)
    kn.k = 1e9
    assert abs(kn.value("x")) < 1e-6
    assert kn.value("missing") is None
    assert Knowledge().value("x") is None
    assert Evidence(drawn_games=3, drawn_wins=1).iwd is None          # never seen undrawn


def test_context_shrinks_toward_global_estimate():
    kn = Knowledge(k=10)
    kn.cards["x"] = Evidence(100, 70, 100, 40)                          # global IWD +0.3, n_eff 50
    g = kn.value("x")
    assert g == pytest.approx(0.3 * 50 / 60)
    kn.contexts["RED"] = {"x": Evidence(4, 0, 4, 4)}                    # thin, contradicting evidence
    v = kn.value("x", "RED")
    assert -1.0 < v < g                                                 # pulled down, not all the way
    assert kn.value("x", "BLUE") == g                                   # unknown context = global
    assert kn.value("x", None) == g


def test_knowledge_accumulates_from_a_tournament_and_round_trips(reg, tourney, tmp_path):
    kn = Knowledge.load(tmp_path / "k.json", reg)
    assert kn.games == 0
    kn.update_from_tournament(tourney)
    n_games = sum(2 * c.n for c in tourney.cells.values())
    assert kn.games == n_games and kn.tournaments == 1
    ctx = context_key(reg, tourney.decks[0].legends)
    assert ctx in kn.contexts and "|" in ctx or ctx.isalpha()
    # every card of every deck has evidence, and its counts match the tournament's own CardStat
    for deck, stats in zip(tourney.decks, tourney.card_stats):
        for cid, s in stats.items():
            assert cid in kn.cards
            assert kn.cards[cid].drawn_games >= s.drawn_games
    for cid, e in kn.cards.items():
        v = kn.value(cid)
        if e.iwd is None:
            assert v is None
        else:
            assert abs(v) <= abs(e.iwd) + 1e-12 and (v >= 0) == (e.iwd >= 0)
    assert kn.pairs and all(g >= w for g, w in kn.pairs.values())
    a, b = next(iter(kn.pairs)).split("|")
    assert kn.synergy(a, b) is not None and kn.synergy(b, a) == kn.synergy(a, b)
    assert kn.top(3) and kn.top(3, worst=True)
    kn.save()
    back = Knowledge.load(tmp_path / "k.json", reg)
    assert back.to_json() == kn.to_json()
    assert "games" in kn.summary()


def test_update_from_results_and_card_stats_fallback(reg, tourney):
    kn = Knowledge(reg=reg)
    cell = next(iter(tourney.cells.values()))
    kn.update_from_results(tourney.decks[cell.i], cell.results, "A")
    assert kn.games == cell.n
    empty = Knowledge(reg=reg)
    saved = {k: c.results for k, c in tourney.cells.items()}
    try:
        for c in tourney.cells.values():
            c.results = []
        empty.update_from_tournament(tourney)
    finally:
        for k, c in tourney.cells.items():
            c.results = saved[k]
    full = Knowledge(reg=reg)
    full.update_from_tournament(tourney)
    assert {c: e.to_list() for c, e in empty.cards.items()} == {c: e.to_list() for c, e in full.cards.items()}


def test_builders_blend_knowledge_into_builds(reg, tourney):
    kn = Knowledge(reg=reg)
    kn.update_from_tournament(tourney)
    legends = list(tourney.decks[0].legends)
    d = Explorer().build(reg, legends, Pcg32(4), knowledge=kn)
    assert validate(d, reg).ok
    # a card the store rates highly gets pulled into a deck once its value dominates the noise
    b = Explorer()
    ctx = b.make_ctx(reg, legends)
    absent = [c for c in ctx.pool if c.id not in b.build(reg, legends, Pcg32(4)).main]
    target = absent[0]
    loud = Knowledge(reg=reg, k=0.0)
    loud.cards[target.id] = Evidence(50, 50, 50, 0)                     # IWD +1.0, unshrunk
    b.knowledge_w = 200.0
    assert target.id in b.build(reg, legends, Pcg32(4), knowledge=loud).main


def test_hall_of_fame_round_trips_and_ranks(reg, tourney, tmp_path):
    hof = HallOfFame.load(tmp_path / "hof.json", capacity=2)
    inducted = hof.update_from_tournament(tourney, generation=1, source="test")
    assert 1 <= len(inducted) <= 2 and len(hof.entries) <= 2
    assert hof.entries == sorted(hof.entries, key=lambda e: -e.bt)
    assert all(e.archetype == e.deck.meta["archetype"] == "exploring" for e in hof.entries)
    best = hof.entries[0]
    assert hof.add(best.deck, best.bt - 10)                             # re-offered worse: kept as is
    assert hof.entries[0].bt == best.bt and len(hof.entries) <= 2
    hof.save()
    back = HallOfFame.load(tmp_path / "hof.json", capacity=2)
    assert [e.to_json() for e in back.entries] == [e.to_json() for e in hof.entries]
    opps = back.opponents(2)
    assert opps and all(o.name.startswith("hof") and o.meta["hall_of_fame"] for o in opps)
    assert all(validate(o, reg).ok for o in opps)
    assert back.opponents(2, exclude={e.signature for e in back.entries}) == []
    assert deck_signature(opps[0]) == back.entries[0].signature
    assert sum(back.by_archetype().values()) == len(back.entries)
    assert opps[0].name == "hof1-exploring" and opps[0].meta["archetype"] == "exploring"


def test_league_learns_archetypes_knowledge_and_hall_of_fame(reg, tmp_path):
    """Cold start: with no store every builder explores; once eight distinct decks have played
    (a survivor that accepted no swap is the same deck), the store clusters them and the
    replaced builder is rebuilt toward a learned archetype."""
    gens = list(league(reg, n_builders=8, generations=2, steps=1, seed=1, agent="random", workers=1,
                       games_per_pair=4, knowledge_path=tmp_path / "k.json", hall_of_fame_path=tmp_path / "hof.json",
                       archetypes_path=tmp_path / "archetypes.json", seeds_per_batch=2, max_batches=1,
                       out_dir=tmp_path / "league"))
    assert [g for g, _, _ in gens] == [1, 2]
    _, t1, decks1 = gens[0]
    assert all(d.meta["archetype"] == "exploring" for d in decks1)
    store = ArchetypeStore.load(tmp_path / "archetypes.json", reg)
    assert store.tournaments == 2 and len(store.decks) >= 8 and store.archetypes
    _, t, decks = gens[-1]
    kinds = [d.meta["archetype"] for d in decks]
    assert sum(1 for k in kinds if k != "exploring") == 1          # gen 2's fresh builder targets a learned archetype
    learned = next(d for d in decks if d.meta["archetype"] != "exploring")
    target = store.get(learned.meta["archetype_id"])        # the group it aimed at, even if renamed since
    assert target is not None and (target.name == learned.meta["archetype"] or learned.meta["archetype"] in target.aliases)
    # every deck of the generation carries the nearest current archetype (Explorers included)
    assert len(t.info["nearest"]) == 8 and all(n is None or store.get(n) is not None for n in t.info["nearest"])
    assert all(validate(d, reg).ok for d in decks)
    kn = Knowledge.load(tmp_path / "k.json", reg)
    assert kn.tournaments == 2 and kn.games == sum(sum(2 * c.n for c in tt.cells.values()) for _, tt, _ in gens)
    hof = HallOfFame.load(tmp_path / "hof.json")
    assert hof.entries and all(e.archetype in set(kinds) for e in hof.entries)
    rep = render_report(t, "League", reg)
    assert "| Archetype |" in rep and "## Archetypes in this run" in rep and "exploring" in rep and learned.meta["archetype"] in rep
    assert (tmp_path / "league" / "gen2" / "report.md").exists()
    saved = Decklist.load(tmp_path / "league" / "gen2" / f"{learned.name}.json")
    assert saved.meta["archetype"] == learned.meta["archetype"] and saved.meta["generated"] == "learned"
    # the league context travels with the tournament and the cumulative series
    assert t.info["generation"] == 2 and t.info["generations"] == 2 and t.info["replaced"] is None
    assert len(t.info["climb"]) == 8 and all(isinstance(h, list) for h in t.info["climb"])
    gen1 = json.loads((tmp_path / "league" / "gen1" / "tournament.json").read_text())
    assert gen1["version"] == 2 and gen1["info"]["replaced"] in {d.name for d in decks}
    assert gen1["decks"][0]["meta"]["archetype"] == "exploring" and gen1["decks"][0]["path"].endswith("builder1.json")
    assert "program_share" in gen1["decks"][0]["profile"] and "colour_red" in gen1["decks"][0]["profile"]
    series = json.loads((tmp_path / "league" / "league.json").read_text())
    assert [g["gen"] for g in series["generations"]] == [1, 2]
    assert all(row["fresh"] for row in series["generations"][0]["standings"])
    assert sum(row["fresh"] for row in series["generations"][1]["standings"]) == 1
    assert {row["archetype"] for row in series["generations"][1]["standings"]} == set(kinds)


def test_league_with_named_archetypes_cycles_them(reg, tmp_path):
    rng = Pcg32(8)
    st = ArchetypeStore(path=tmp_path / "a.json", reg=reg)
    for i in range(10):
        st.add(Explorer().build(reg, None, rng, name=f"s{i}"), None, games=20, wins=6 + i, bt=1.0)
    st.refit()
    st.save()
    a = st.ranked()[0]
    gen, t, decks = next(league(reg, n_builders=2, generations=1, steps=0, seed=3, agent="random", workers=1,
                                games_per_pair=2, archetypes=[a.id, "explorer"], archetypes_path=tmp_path / "a.json"))
    assert [d.meta["archetype"] for d in decks] == [a.name, "exploring"]
    assert "| Archetype |" in render_report(t, reg=reg)


def test_legacy_league_still_builds_unopinionated_decks(reg):
    gen, t, decks = next(league(reg, n_builders=2, generations=1, steps=0, seed=3, agent="random",
                                workers=1, games_per_pair=2, archetypes="legacy"))
    assert all("archetype" not in d.meta for d in decks)
    assert "| Archetype |" not in render_report(t, reg=reg)
