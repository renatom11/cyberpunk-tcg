"""The words a reader sees: summary sentences, significance wording, names instead of ids,
no duplicated card rows, and old (version 1) files that still load and render."""
import json
from pathlib import Path

import pytest

from cptcg.cards.registry import load_default
from cptcg.deck.decklist import Decklist
from cptcg.sim.report import (card_name, deck_profile_json, profile_sentence, render_report, sig_word, summarize,
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
    deck 1 edges deck 2. Deck 0 carries a personality label."""
    a, b, c = _decks(3)
    a = Decklist(a.name, a.legends, a.main, {"strategy": "aggro"})
    cells = {(0, 1): _cell(0, 1, 34, 40), (0, 2): _cell(0, 2, 14, 20), (1, 2): _cell(1, 2, 24, 40)}
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
    # one thin result in the group: singular, and joined with a semicolon rather than a second dash
    assert "; it rests on fewer than 30 games, so keep some doubt" in text and "some of these rest" not in text
    assert "bring" in text and names[0] in text.split("bring")[1]
    assert "small run (100 games in all, under 40 per matchup)" in text
    # the same sentences are what the JSON stores
    assert t.to_json(reg)["summary"] == lines


def test_summary_flags_a_thin_count_once_and_never_twice(reg):
    """A count is printed once: "of only 20 games" replaces the separate "(only 20 games)" aside,
    and a one-result group says "it rests", not "some rest"."""
    a, b, c = _decks(3)
    cells = {(0, 1): _cell(0, 1, 12, 20), (0, 2): _cell(0, 2, 18, 20), (1, 2): _cell(1, 2, 11, 20)}
    text = "\n".join(summarize(Tournament([a, b, c], "random", 7, cells, [{}, {}, {}]), reg))
    assert "is not established (60% of only 20 games), so the top two could swap places" in text
    assert "(90% of 20 games) is statistically very solid — unlikely to be luck, though it rests on fewer than 30 games" in text
    assert "only 20 games)" not in text.replace("of only 20 games)", "")      # never a second aside
    # a loss names its own count, with the thin flag folded in
    text = "\n".join(summarize(Tournament([a, b, c], "random", 7, {(0, 1): Cell(0, 1, 8, 20, "low", 4, 10, 240),
                                                                   (0, 2): _cell(0, 2, 18, 20),
                                                                   (1, 2): _cell(1, 2, 4, 20)}, [{}, {}, {}]), reg))
    assert "of only 20 games) — a loss" in text


def test_league_header_labels_both_seeds_and_the_round_robin_time(reg):
    t = synthetic(reg)
    t.info.update(generation=2, generations=3, steps=2, league_seed=0, elapsed_s=2.4)
    head = render_report(t, reg=reg).split("## Summary")[0]
    assert "round-robin seed 7" in head and "(league seed 0, 2 improvement steps per builder)" in head
    assert "round robin 2 s" in head and "run time" not in head
    t.info["gen_elapsed_s"] = 75.2
    assert "round robin 2 s of 75 s for this generation" in render_report(t, reg=reg)
    # a plain tournament keeps the unlabelled seed and the whole run time
    t.info.pop("generation")
    head = render_report(t, reg=reg).split("## Summary")[0]
    assert "· seed 7 ·" in head and "run time 2 s" in head


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
    t = Tournament.load(path, siblings=False)
    assert t.n() == 4 and t.info == {} and all(p is None for p in t.paths)
    # By default the sibling builderK.json files complete each deck's meta and path.
    t = Tournament.load(path, rel_to=ROOT)
    assert t.paths == [f"out/league_demo/gen1/builder{i}.json" for i in (1, 2, 3, 4)]
    assert all(d.meta.get("generated") == "heuristic" for d in t.decks)
    assert all(c.n == 40 for c in t.cells.values()) and t.cells[(0, 1)].turns == round(40 * raw["cells"][0]["avg_turns"])
    rep = render_report(t, reg=reg)
    assert rep.startswith("# Tournament") and "Standings" in rep and "Head-to-head" in rep
    assert "Dexter DeShawn — Off the Grid" in rep and "| dexter-deshawn" not in rep
    data = t.to_json(reg)
    assert data["version"] == 2 and data["summary"][0].startswith("builder1 is rated highest in this run")
    assert "the order of the top two is not established" in data["summary"][1]
    assert all(d["shape"] == profile_sentence(d["profile"]) for d in data["decks"])


def test_api_report_upgrades_a_version_1_file():
    from cptcg.web import backend
    data = backend.report_json(ROOT / "out/league_demo/gen1/tournament.json")
    assert data["version"] == 2 and data["summary"] and data["markdown"].startswith("#")
    d0 = data["decks"][0]
    assert d0["meta"]["generated"] == "heuristic"                    # pulled from the sibling builder1.json
    assert d0["path"] == "out/league_demo/gen1/builder1.json" and d0["profile"]["cards"] == 40
    assert data["file"] == "out/league_demo/gen1/tournament.json" and "league_series" not in data
    # What the web page prints: the shape sentence per deck, the glossary, and a Markdown text
    # version re-rendered from the loaded run (the old report.md printed raw card ids).
    assert d0["shape"].endswith("sellable") or "% Units" in d0["shape"]
    assert [g["term"] for g in data["glossary"]][:2] == ["Win rate", "Strength"] and "**" not in data["glossary"][5]["text"]
    assert "## How to read this report" in data["markdown"] and "ruthless-lowlife" not in data["markdown"]


def test_every_rendered_report_discloses_who_played_the_games(reg):
    """The ranking is conditional on the agent, so the disclosure is part of the report: it names
    the agent, states the measured defects, and quotes only figures a shipped command re-derives,
    naming that command. The Markdown, the web report and the GUIDE all print the one Python
    string."""
    from cptcg.sim.report import disclosure
    text = disclosure("heuristic")
    for phrase in ("heuristic agent", "one ply ahead", "cannot plan across turns",
                   "almost never keeps a Blocker home", "largest Gig die", "mulligans by a fixed rule",
                   "tools/arena.py panel heuristic", "93.9%", "tools/arena.py delayed heuristic",
                   "data/arena/panel.json", "88% to 95%",
                   "No human games are recorded anywhere in this project"):
        assert phrase in text, phrase
    # The retired numbers: measured by a throwaway probe over three fixed curated pairings, never
    # reproduced by a shipped tool, and falsified over sampled decks by tools/arena.py. If one of
    # these comes back, it has to come back with a command that prints it.
    for gone in ("98.6%", "61.7%", "59.4%", "never holds a Blocker back"):
        assert gone not in text, gone
    assert "**" not in text and "`" not in text          # plain text: the page prints it verbatim
    assert disclosure("random").startswith("Both sides of every game here were played by the random agent")

    t = Tournament.load(ROOT / "out/league_demo/gen1/tournament.json", siblings=False)
    rep = render_report(t, reg=reg)
    assert "## Who played these games" in rep and text in rep
    assert rep.index(text) < rep.index("## Standings")    # ahead of the numbers it qualifies

    from cptcg.web import backend
    data = backend.report_json(ROOT / "out/league_demo/gen1/tournament.json")
    assert data["disclosure"] == text                      # the page prints the same words
    js = (ROOT / "src/cptcg/web/static/report.js").read_text(encoding="utf-8")
    assert "t.disclosure" in js
    guide = (ROOT / "src/cptcg/web/static/index.html").read_text(encoding="utf-8")
    assert text in guide                                   # the GUIDE entry, word for word


def test_the_disclosure_only_names_commands_that_exist():
    """Every 'tools/arena.py X' in any branch of the disclosure has to be a real arena subcommand,
    for the heuristic and for the agents that land later. A figure whose command was renamed is a
    figure the reader cannot re-derive, which is exactly the failure this paragraph is here to
    avoid."""
    import argparse
    import re

    from cptcg.cli.arena import add_arguments
    from cptcg.sim.report import disclosure

    ap = add_arguments(argparse.ArgumentParser())
    commands = set(ap._subparsers._group_actions[0].choices)
    for agent in ("heuristic", "random", "gen0", "search"):
        named = set(re.findall(r"tools/arena\.py ([a-z-]+)", disclosure(agent)))
        assert named <= commands, (agent, named - commands)


def test_the_generic_disclosure_says_no_less_than_the_heuristic_one():
    """An agent this text has no figures for must not disclose less than the heuristic does: it
    still names the agent, still carries the never-validated-against-humans line, and points at
    every arena command that would produce the missing figures — including the two the heuristic's
    own paragraph quotes."""
    from cptcg.sim.report import disclosure
    text = disclosure("gen0")
    assert text.startswith("Both sides of every game here were played by the gen0 agent")
    for phrase in ("tools/arena.py panel gen0", "tools/arena.py a-vs-b gen0 heuristic",
                   "tools/arena.py delayed gen0", "tools/arena.py exploit gen0", "docs/learning.md",
                   "No human games are recorded anywhere in this project"):
        assert phrase in text, phrase
    assert "quotes no strength figure" in text and "%" not in text   # no number without a run
    assert "**" not in text and "`" not in text


def test_the_panel_figure_in_the_disclosure_is_the_one_the_arena_printed():
    """The disclosure's numbers and the instrument's numbers cannot drift: every figure the
    heuristic paragraph quotes for the frozen panel is written in the arena section of
    docs/learning.md, which is where tools/arena.py appends what it measured."""
    from cptcg.sim.report import disclosure
    learning = (ROOT / "docs/learning.md").read_text(encoding="utf-8")
    text = disclosure("heuristic")
    for figure in ("93.9%", "90.9\u201395.9%", "91.7\u201395.0%", "50.0%"):
        assert figure in text and figure in learning, figure


def test_the_heuristic_almost_never_keeps_a_blocker_home(reg):
    """The disclosure says 'almost never', not 'never', and that word is a measurement: over
    heuristic self-play, count the turns in which a ready Blocker could have attacked and the turn
    ended without it attacking. Both ends matter — if it becomes never the sentence is an
    overstatement again, and if it becomes common the sentence is simply wrong."""
    from cptcg.agents.base import make_agent
    from cptcg.core import ops
    from cptcg.core.actions import Attack, ChoiceKind
    from cptcg.core.engine import apply, legal_actions, new_game
    from cptcg.core.enums import Keyword
    from cptcg.core.rng import Pcg32
    from cptcg.learn.decks import sample_pair

    rng = Pcg32(21, seq=5)
    chances = held = 0
    for g in range(12):
        s = new_game(reg, sample_pair(reg, rng), 900 + g)
        agents = [make_agent("heuristic", 31 + p) for p in range(2)]
        for p, a in enumerate(agents):
            a.new_game(g, p)
        turn, could, swung = None, False, False
        for _ in range(6000):
            if s.over:
                break
            legal_actions(s)
            choice = s.pending
            if choice is None:
                break
            i = agents[choice.player].act(s, choice)
            if choice.kind is ChoiceKind.MAIN:
                if (s.turn, s.active) != turn:
                    chances += could
                    held += could and not swung
                    turn, could, swung = (s.turn, s.active), False, False
                ready = [o for o in choice.options if isinstance(o, Attack)
                         and ops.has_keyword(s, o.inst, Keyword.BLOCKER)]
                could = could or bool(ready)
                chosen = choice.options[i]
                swung = swung or (isinstance(chosen, Attack)
                                  and ops.has_keyword(s, chosen.inst, Keyword.BLOCKER))
            apply(s, i)
        chances += could
        held += could and not swung

    assert chances > 50, chances                     # the sample has to contain the decision at all
    assert 0 < held, "it never keeps a Blocker home: the disclosure now overstates the other way"
    assert held / chances < 0.15, f"{held}/{chances} is not 'almost never' any more"


def test_glossary_entries_back_both_the_markdown_and_the_page():
    from cptcg.sim.report import GLOSSARY, GLOSSARY_ENTRIES, glossary_json
    assert GLOSSARY[0] == "## How to read this report" and len(GLOSSARY) == 2 + len(GLOSSARY_ENTRIES)
    for (term, text), line, entry in zip(GLOSSARY_ENTRIES, GLOSSARY[2:], glossary_json()):
        assert line == f"- **{term}** — {text}" and entry == {"term": term, "text": text.replace("**", "")}


def _cyclic(reg, games=200, rate=0.9):
    """Three decks in a perfect circle: A beats B, B beats C, C beats A."""
    a, b, c = _decks(3)
    w = int(games * rate)
    cells = {(0, 1): _cell(0, 1, w, games), (1, 2): _cell(1, 2, w, games), (0, 2): _cell(0, 2, games - w, games)}
    return Tournament([a, b, c], "random", 1, cells, [{}, {}, {}])


def test_rock_paper_scissors_is_asserted_only_beyond_two_standard_errors(reg):
    # A 40-game cell 14 points off the model's prediction is under two standard errors: hedged.
    t = Tournament.load(ROOT / "out/league_demo/gen2/tournament.json", siblings=False)
    text = "\n".join(summarize(t, reg))
    assert "more often than their strengths predict, but on 40 games that could still be noise" in text
    assert "rock–paper–scissors" not in text
    # A genuine circle on 200 games per cell is far beyond two standard errors: asserted.
    text = "\n".join(summarize(_cyclic(reg), reg))
    assert "a rock–paper–scissors pattern, so the best deck depends on what it faces" in text
    assert "bring" in text and "% of the time" in text          # and the blind pick is a mix


def test_top_deck_wording_reconciles_rating_and_blind_pick(reg):
    t = Tournament.load(ROOT / "out/league_demo/gen2/tournament.json", siblings=False)
    lines = summarize(t, reg)
    assert lines[0].startswith("builder1 is rated highest in this run") and "strongest" not in lines[0]
    assert lines[1].startswith("It is rated above builder4 despite losing to it (45% of 40 games)")
    bring = next(x for x in lines if x.startswith("If you had to pick"))
    assert "bring builder4 every time — builder1 is rated higher, but builder4 is the only deck that held at least even" in bring
    assert "(55% of 40 games, not established)" in bring
    # Established lead: the synthetic run's top deck beat the next-rated deck solidly.
    assert summarize(synthetic(reg), reg)[0].startswith("Sample Corpos (aggro) is the strongest deck in this run")


def test_how_played_is_computed_from_the_cells(reg):
    from cptcg.sim.report import how_played
    t = synthetic(reg)
    assert how_played(t) == ""                                    # no cap recorded: nothing to claim
    t.info.update(games_per_pair=40, batch=40, sprt={"delta": 0.08})
    assert how_played(t) == ("Every matchup played its full 40 games in one batch, so the early-stop test never had a "
                             "chance to shorten one.")
    t.info.update(games_per_pair=60, sprt=None)
    assert how_played(t) == "Every matchup played the full 60 games."
    t.info.update(sprt={"delta": 0.08})
    t.cells[(0, 1)].n = 60
    t.cells[(0, 2)].verdict, t.cells[(1, 2)].verdict = "high", "h0"
    s = how_played(t)
    assert s.startswith("Matchups were played in batches of 40 games and checked between batches: 2 of 3 stopped before the cap of 60 (at 20–40 games), ")
    assert "1 because one deck was clearly ahead and 1 because the two were clearly within 8 points of even; the other 1 ran to the cap." in s
    for c in t.cells.values():
        c.n, c.verdict = 60, "continue"
    assert how_played(t).endswith("none stopped before the cap of 60, so every matchup ran to the cap.")
    assert t.to_json(reg)["how_played"] == how_played(t)
    # the Markdown prints the same sentence
    assert how_played(t) in render_report(t, reg=reg)


def test_card_table_needs_both_sides_and_marks_thin_ones(reg):
    from cptcg.sim.report import card_rows
    t = synthetic(reg, 4)
    cid = sorted(set(t.decks[0].main))[0]
    t.card_stats[0][cid] = CardStat(drawn_games=106, drawn_wins=40, other_games=14, other_wins=1)   # +31 on 14 games
    t.card_stats[0]["never-left"] = CardStat(drawn_games=120, drawn_wins=60, other_games=0, other_wins=0)
    t.card_stats[0]["rarely-left"] = CardStat(drawn_games=115, drawn_wins=60, other_games=5, other_wins=0)
    rows = card_rows(t.card_stats[0])
    assert [c for c, _ in rows][0] == cid and "never-left" not in dict(rows) and "rarely-left" not in dict(rows)
    rep = render_report(t, reg=reg)
    assert "| Games drawn / not drawn |" in rep and f"| {card_name(reg, cid)} | 38% | 7% | +31 (thin) | 106 / 14 |" in rep
    assert "left in the deck in at least 10 are listed" in rep and "marked thin rests on fewer than 20 games" in rep


def test_strength_is_the_expected_win_rate_against_the_field(reg):
    t = synthetic(reg)
    bt = t.bt()
    exp = t.expected_rates(bt)
    assert abs(sum(exp) / len(exp) - 0.5) < 1e-9                 # the field averages exactly 50%
    assert exp[0] > exp[1] > exp[2]
    rep = render_report(t, reg=reg)
    assert f"{100 * exp[0]:.0f}% expected vs this field (rating {bt[0]:.2f})" in rep
    assert t.to_json(reg)["expected"] == exp
    assert "finished 2026-09-10 14:17 UTC" in render_report(
        Tournament(t.decks, "random", 1, t.cells, t.card_stats, {"finished_at": "2026-09-10T14:17:26+00:00"}), reg=reg)


def test_league_lines_fresh_replaced_and_one_archetype(reg):
    t = synthetic(reg)
    for d in t.decks[1:]:
        d.meta["strategy"] = "aggro"
    t.info.update(generation=2, generations=3, steps=2, league_seed=0, fresh=[t.decks[1].name], replaced=t.decks[2].name,
                  climb=[[{"step": 1, "proposal": {"out": "floor-it", "in": "detonate", "kind": "card"}, "games": 360,
                           "discordant": 16, "challenger_wins": 13, "verdict": "continue", "accepted": True}], [], []])
    rep = render_report(t, reg=reg)
    assert f"- Built fresh this generation, replacing last generation's {t.decks[1].name}." in rep
    assert "- This builder is replaced by a fresh deck next generation." in rep
    assert "the card-swap tests played another 360 challenger games" in rep and "360 games each side" in rep
    # one kind only: no pooled table, one honest line instead
    assert "## Archetypes in this run" not in rep and "All 3 decks are labelled aggro, so there is no second archetype" in rep
    t.decks[0].meta["strategy"] = "control"
    assert "## Archetypes in this run" in render_report(t, reg=reg)


def test_nearest_archetype_labels_hand_built_decks(reg):
    from cptcg.core.rng import Pcg32
    from cptcg.deck.archetypes import ArchetypeStore
    from cptcg.deck.strategies import Explorer
    from cptcg.sim.report import deck_label, label_nearest
    rng = Pcg32(31)
    st = ArchetypeStore(reg=reg)
    for i in range(12):
        st.add(Explorer().build(reg, None, rng, name=f"s{i}"), None, games=20, wins=6 + i, bt=1.0)
    assert st.refit()
    t = synthetic(reg)
    t.decks[1] = Decklist(t.decks[1].name, t.decks[1].legends, t.decks[1].main, {"archetype": "exploring", "generated": "explorer"})
    t.decks[2] = Decklist(t.decks[2].name, t.decks[2].legends, t.decks[2].main,
                          {"archetype": "Gone group", "archetype_id": "gone-group", "generated": "learned"})
    near = label_nearest(t, st)
    names = {a.name for a in st.archetypes}
    assert near == t.info["nearest"] and all(x in names for x in near)
    assert deck_label(t, 0) == f"aggro, nearest: {near[0]}"            # an old personality label, plus the nearest group
    assert deck_label(t, 1) == f"exploring, nearest: {near[1]}"
    assert deck_label(t, 2) == f"Gone group, now nearest: {near[2]}"
    data = t.to_json(reg)
    assert [d["nearest"] for d in data["decks"]] == near
    plain = Decklist("plain", t.decks[0].legends, t.decks[0].main)
    t.decks[0] = plain
    label_nearest(t, st)
    assert deck_label(t, 0).startswith("nearest: ") and f"| nearest: {t.info['nearest'][0]} |" in render_report(t, reg=reg)
    assert label_nearest(t, ArchetypeStore(reg=reg)) == [None, None, None]   # an empty store labels nothing
