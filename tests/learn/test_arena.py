"""The gate itself: the statistics, the balanced design, the frozen panel, the cheating variant.

A measuring instrument that is not itself measured is decoration, so these tests check the three
things the arena's numbers rest on: that the sequential test stops when it should and rarely when
it should not, that the interval brackets the truth, and that the design cannot mistake a strong
deck for a strong agent.
"""

import json
import random

import pytest

from cptcg.agents.base import CHEAT_PREFIX, Agent, make_agent, register
from cptcg.core.enums import NZONE, Zone
from cptcg.core.view import determinize
from cptcg.learn import arena
from cptcg.learn import decks as D
from cptcg.learn.decks import holdout_decks, is_holdout
from cptcg.sim.stats import SPRT, cluster_interval, welch_interval, wilson

# The frozen panel, pinned here as well as in its own file. Locks a deliberate edit must turn: the
# two digests in data/arena/panel.json and these constants. The first pairing is pinned card for
# card as well, because that is the assertion that fails loudly if the panel ever goes back to
# redrawing its decks from the sampler — a retuned sampler would change it, and a stored decklist
# cannot.
PANEL_DIGEST = "a1832d477c27193f"
PANEL_DECKS_DIGEST = "1b1799dbc029a6b7"
PANEL_MEMBERS = [("random", "random"), ("heuristic", "heuristic"), ("gen0", "gen0")]
PANEL_FIRST_DECK = ("built", ("jackie-welles-pour-one-out-for-me",
                              "judy-alvarez-braindance-maestro",
                              "evelyn-parker-beautiful-enigma"), 40)


# ------------------------------------------------------------------ the statistics
def sequential(p: float, rng: random.Random, sprt: SPRT, cap: int) -> tuple[str, int]:
    """Feed Bernoulli(p) outcomes to the SPRT one at a time; return (verdict, observations)."""
    k = 0
    for n in range(1, cap + 1):
        k += rng.random() < p
        v = sprt.test(k, n)
        if v != "continue":
            return v, n
    return "continue", cap


def test_sprt_stops_early_on_a_lopsided_pair():
    """A 90% agent must be settled in a few dozen paired games, almost every time."""
    rng = random.Random(4242)
    sprt = SPRT(delta=0.05)
    stops = [sequential(0.9, rng, sprt, 400) for _ in range(200)]
    settled = [n for v, n in stops if v == "high"]
    assert len(settled) >= 195                       # essentially always resolves
    assert max(settled) <= 120                       # and quickly
    assert sorted(settled)[len(settled) // 2] <= 40  # median well under the cap
    assert not [v for v, _ in stops if v == "low"]   # never the wrong way


def test_sprt_rarely_stops_on_a_coin_flip():
    """Two equal agents must not be declared different. The test's own error rate is the bound."""
    rng = random.Random(1234)
    sprt = SPRT(delta=0.05)
    stops = [sequential(0.5, rng, sprt, 2000) for _ in range(200)]
    wrong = [v for v, _ in stops if v in ("high", "low")]
    assert len(wrong) <= 30                          # alpha is 0.05 per direction
    assert sum(1 for v, _ in stops if v == "h0") >= 150   # it settles on "no difference" instead


def clustered(rng: random.Random, k: int, n: int, p: float, sd: float) -> list[float]:
    """k deck pairings of n games each, where the pairing shifts the win rate by N(0, sd).

    This is the arena's actual sampling model: a deck pairing is drawn, then games are played on
    it. The games inside a pairing are not independent draws from ``p``.
    """
    out = []
    for _ in range(k):
        q = min(0.99, max(0.01, p + rng.gauss(0, sd)))
        out.append(sum(rng.random() < q for _ in range(n)) / n)
    return out


def test_wilson_misses_the_truth_under_clustering_and_the_cluster_interval_does_not():
    """The finding, as a test: a binomial interval over clustered games is not a 95% interval.

    Six pairings of sixty games with a modest deck effect is exactly the arena's design. The
    Wilson interval over all 360 games covers the true rate far less than 95% of the time, because
    the deck term is missing from it; the between-pairing interval covers it about right. If this
    ever fails the other way — cluster coverage collapsing — the reports are lying again.
    """
    rng = random.Random(7)
    p, wil, clu = 0.75, 0, 0
    for _ in range(400):
        rates = clustered(rng, 6, 60, p, 0.10)
        k = round(sum(rates) * 60)
        lo, hi = wilson(k, 360)
        wil += lo <= p <= hi
        m, clo, chi = cluster_interval(rates)
        clu += clo <= p <= chi
    assert wil / 400 < 0.80                      # nowhere near the 95% it advertises
    assert clu / 400 >= 0.88                     # and the honest one is close to nominal


def test_the_cluster_interval_refuses_a_single_observation():
    assert cluster_interval([0.7]) is None and cluster_interval([]) is None
    assert welch_interval([0.7], [0.5, 0.6]) is None
    m, lo, hi = cluster_interval([0.5, 0.5, 0.5])
    assert (m, lo, hi) == (0.5, 0.5, 0.5)        # no scatter, no width — and no crash


def test_the_welch_interval_finds_a_real_difference_and_not_a_fake_one():
    rng = random.Random(11)
    d, lo, hi = welch_interval(clustered(rng, 6, 60, 0.80, 0.05),
                               clustered(rng, 6, 60, 0.50, 0.05))
    assert lo > 0 and d > 0.2
    same = [welch_interval(clustered(rng, 6, 60, 0.6, 0.08), clustered(rng, 6, 60, 0.6, 0.08))
            for _ in range(200)]
    assert sum(lo <= 0 <= hi for _, lo, hi in same) >= 180      # ~95%, and not much worse


def test_wilson_brackets_the_truth():
    """A 95% interval must contain the true rate about 95% of the time, at both ends of [0, 1]."""
    rng = random.Random(99)
    for p, n, floor in ((0.5, 100, 0.90), (0.9, 100, 0.90), (0.98, 200, 0.90)):
        covered = 0
        for _ in range(400):
            k = sum(rng.random() < p for _ in range(n))
            lo, hi = wilson(k, n)
            covered += lo <= p <= hi
        assert covered / 400 >= floor, (p, n, covered)


# ------------------------------------------------------------------ the design
def test_the_same_agent_on_both_sides_is_exactly_even(pool):
    """The balancing must be exact, not merely unbiased on average.

    With one agent name on both sides the two swapped matches are the *same games*, so every pair
    is decided by the deck and by nothing else: the headline rate is exactly 50% and there are no
    decisive pairs at all. That is the whole point — deck strength cannot leak into an agent
    number — and it is checked to the game rather than to a confidence interval.
    """
    pairings = arena.sampled_pairings(pool, 2, deck_seed=5)
    res = arena.head_to_head(pool, "random", "random", pairings, games_per_pairing=8, seed=3,
                             workers=1, sprt=None)
    assert res.games == 16 and res.a_wins * 2 == res.games
    assert res.discordant == 0
    assert res.pairs * 2 == res.games


def test_seats_are_mirrored_exactly(pool):
    """Each agent sits in each seat in exactly half the games.

    Note that this is the seat, not who goes first: the d20 winner *chooses* the order (ruling
    028), so first-player share is an agent decision and belongs in the report as description
    rather than as a balance check.
    """
    pairings = arena.sampled_pairings(pool, 2, deck_seed=6)
    res = arena.head_to_head(pool, "heuristic", "random", pairings, games_per_pairing=8, seed=11,
                             workers=1, sprt=None)
    assert res.a_seat0_games * 2 == res.games
    assert sum(r.games for r in res.per_pairing) == res.games
    assert sum(r.a_wins for r in res.per_pairing) == res.a_wins


def test_a_report_labels_the_wilson_interval_as_conditional_on_the_decks(pool):
    """The headline bracket is not an error bar for the agent, and the report has to say so.

    A reader quotes whatever number is printed next to the win rate. If that is a binomial interval
    over clustered games with no qualifier, every future claim about the AI inherits an error bar
    several points too narrow — the same protocol on five deck samples moves further than the
    printed interval is wide.
    """
    pairings = arena.sampled_pairings(pool, 3, deck_seed=6)
    res = arena.head_to_head(pool, "heuristic", "random", pairings, games_per_pairing=8, seed=11,
                             workers=1, sprt=None)
    assert len(res.pairing_rates) == 3
    m, lo, hi = res.cluster
    assert lo <= m <= hi and m == pytest.approx(sum(res.pairing_rates) / 3)
    text = arena.render_head_to_head(res)
    assert "95% Wilson (these decks)" in text
    assert "conditional on these 3 deck pairings" in text
    assert "generation-over-generation claim has to clear it" in text
    d = res.to_json()
    assert d["pairings"] == 3 and d["cluster_low"] == pytest.approx(lo)


def test_one_pairing_gets_no_between_pairing_interval(pool):
    """With one deck pairing there is no deck-level variance, so none is invented."""
    one = arena.sampled_pairings(pool, 1, deck_seed=6)
    res = arena.head_to_head(pool, "heuristic", "random", one, games_per_pairing=8, seed=11,
                             workers=1, sprt=None)
    assert res.cluster is None and res.to_json()["cluster_mean"] is None
    assert "no deck-level spread to estimate" in arena.render_head_to_head(res)


def test_an_unswapped_run_is_labelled_as_unbalanced(pool):
    pairings = arena.sampled_pairings(pool, 1, deck_seed=6)
    res = arena.head_to_head(pool, "heuristic", "random", pairings, games_per_pairing=8, seed=11,
                             workers=1, sprt=None, swap_decks=False)
    assert res.balanced is False and res.games == 8
    assert "not** swapped" in arena.render_head_to_head(res)


def test_sprt_stopping_shortens_a_lopsided_match(pool):
    """The instrument, not just the statistic: a hopeless matchup ends before the budget does."""
    pairings = arena.sampled_pairings(pool, 8, deck_seed=7)
    res = arena.head_to_head(pool, "heuristic", "random", pairings, games_per_pairing=40, seed=13,
                             workers=1, sprt=SPRT(delta=0.05))
    assert res.verdict == "high" and res.stopped_early
    assert len(res.per_pairing) < 8


def test_head_to_head_refuses_an_unknown_agent(pool):
    with pytest.raises(KeyError):
        arena.head_to_head(pool, "heuristic", "no-such-agent",
                           arena.sampled_pairings(pool, 1, deck_seed=1), workers=1)


# ------------------------------------------------------------------ the frozen panel
def test_the_panel_is_frozen():
    """Fails if the panel definition changes without a deliberate edit *here* as well.

    A win rate against the panel is only comparable across generations because the panel never
    moves. Changing it is allowed; changing it silently is not.
    """
    panel = arena.load_panel()
    assert arena.panel_digest(panel) == PANEL_DIGEST == panel["digest"]
    assert arena.decks_digest(panel) == PANEL_DECKS_DIGEST == panel["decks_digest"]
    assert [(m["id"], m["agent"]) for m in panel["members"]] == PANEL_MEMBERS
    assert panel["protocol"] == {"deck_pairs": 6, "games_per_pair": 60, "seed": 4242,
                                 "sprt": False, "note": panel["protocol"]["note"]}


def test_the_panels_decks_are_stored_not_redrawn(pool):
    """The decks are the benchmark, so they must live in the file and not in the sampler.

    A panel that regenerates its decklists from ``learn.decks`` at run time is not frozen: retuning
    ``DEFAULT_MIX``, either builder, or the set of ``data/decks/sample_*.json`` files would re-base
    every future score while the panel's digest still matched. So this pins the first pairing card
    for card, and then checks that the pairings really are read from the file by mutating the
    sampler's mix and demanding that the panel does not move.
    """
    panel = arena.load_panel()
    pairings = arena.panel_pairings(pool, panel)
    assert len(pairings) == panel["protocol"]["deck_pairs"] == 6
    d = pairings[0].deck_a
    assert (d.name, d.legends, len(d.main)) == PANEL_FIRST_DECK

    before = [(p.deck_a.name, p.deck_a.legends, p.deck_a.main) for p in pairings]
    mix = dict(D.DEFAULT_MIX)
    try:
        D.DEFAULT_MIX.clear()
        D.DEFAULT_MIX.update({"random": 1.0})
        after = [(p.deck_a.name, p.deck_a.legends, p.deck_a.main)
                 for p in arena.panel_pairings(pool, arena.load_panel())]
    finally:
        D.DEFAULT_MIX.clear()
        D.DEFAULT_MIX.update(mix)
    assert after == before


def test_a_tampered_panel_is_refused(tmp_path):
    panel = arena.load_panel()
    panel["protocol"]["games_per_pair"] = 2
    p = tmp_path / "panel.json"
    p.write_text(json.dumps(panel), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen"):
        arena.load_panel(p)


def test_a_swapped_panel_deck_is_refused(tmp_path):
    """One card changed in one of the twelve stored lists must stop the run, not shift the score."""
    panel = arena.load_panel()
    main = dict(panel["decks"][0]["a"]["main"])
    swap = sorted(main)[0]
    main[swap] -= 1
    main["floor-it"] = main.get("floor-it", 0) + 1
    panel["decks"][0]["a"]["main"] = main
    panel["digest"] = arena.panel_digest(panel)          # the outer lock turned, the inner one not
    p = tmp_path / "panel.json"
    p.write_text(json.dumps(panel), encoding="utf-8")
    with pytest.raises(ValueError, match="decklists do not match"):
        arena.load_panel(p)


def test_a_panel_without_its_decks_is_refused(tmp_path):
    """The old seed-only shape has to be rejected outright: it is a benchmark that can drift."""
    panel = arena.load_panel()
    del panel["decks"]
    del panel["decks_digest"]
    panel["digest"] = arena.panel_digest(panel)
    p = tmp_path / "panel.json"
    p.write_text(json.dumps(panel), encoding="utf-8")
    with pytest.raises(ValueError, match="not frozen"):
        arena.load_panel(p)


def test_a_panel_deck_playing_an_unknown_card_is_refused(pool, tmp_path):
    panel = arena.load_panel()
    panel["decks"][0]["a"]["main"] = {"no-such-card": 40}
    with pytest.raises(ValueError, match="card pool does not have"):
        arena.panel_pairings(pool, panel)


def test_the_panel_reports_a_missing_member_rather_than_skipping_it(pool):
    """Generation 0 does not exist yet; the row has to say so, not vanish."""
    panel = arena.load_panel()
    small = dict(panel, decks=panel["decks"][:1],
                 protocol=dict(panel["protocol"], deck_pairs=1, games_per_pair=4))
    out = arena.run_panel(pool, "random", small, workers=1)
    rows = {m["id"]: m for m in out["members"]}
    assert rows["gen0"]["available"] is False and rows["gen0"]["note"]
    assert rows["random"]["available"] and rows["heuristic"]["result"]["games"] == 4
    assert "not available yet" in arena.render_panel(out)


# ------------------------------------------------- the cheating variant (exploit)
@register
class _PeekAgent(Agent):
    """A stub that consults ``core/view.py``, so that ``cheat:`` has something to take away.

    Honest, it decides from a *sampled* world; cheating, from the true one. It is not meant to
    play well — it exists so the exploit harness can be exercised end to end while no search agent
    exists yet.
    """

    name = "test-peek"
    uses_determinization = True

    def act(self, s, choice):
        world = s if self.cheating else determinize(s, self.me, self.rng)
        rival = 1 - self.me
        hidden = world.z[rival * NZONE + Zone.HAND] + world.z[self.me * NZONE + Zone.DECK]
        return sum(world.i_card[i] for i in hidden) % len(choice.options)


def test_cheat_prefix_only_applies_to_an_agent_that_samples():
    peek = make_agent(CHEAT_PREFIX + "test-peek")
    assert peek.cheating is True and make_agent("test-peek").cheating is False
    with pytest.raises(ValueError, match="nothing for"):
        make_agent(CHEAT_PREFIX + "heuristic")       # one-ply greedy reads the true state already
    with pytest.raises(KeyError):
        make_agent(CHEAT_PREFIX + "no-such-agent")


def test_exploit_measures_honest_against_cheating(pool):
    out = arena.run_exploit(pool, "test-peek", deck_pairs=1, games_per_pairing=8, workers=1)
    d = out["direct"]
    assert d["agent_a"] == CHEAT_PREFIX + "test-peek" and d["agent_b"] == "test-peek"
    assert d["games"] == 8 and 0 <= d["rate"] <= 1
    assert "ceiling for this agent" in out["caveat"]
    assert "not an upper bound" in arena.render_exploit(out)


def test_exploit_refuses_an_agent_with_nothing_to_cheat_with(pool):
    with pytest.raises(ValueError):
        arena.run_exploit(pool, "heuristic", deck_pairs=1, games_per_pairing=4, workers=1)


# ------------------------------------------------------------- the generalisation gap
def test_generalisation_reports_three_populations_including_the_holdout(pool):
    out = arena.run_generalisation(pool, "random", baseline="random", deck_pairs=1,
                                   games_per_pairing=4, workers=1)
    names = [p["name"] for p in out["populations"]]
    assert names == ["training", "holdout", "unseen-random"]
    holdout = next(p for p in out["populations"] if p["name"] == "holdout")
    decks = holdout["result"]["per_pairing"][0]
    assert {decks["deck_a"], decks["deck_b"]} == {d.name for d in holdout_decks()}
    assert out["gap_holdout"] == pytest.approx(
        out["populations"][0]["result"]["rate"] - holdout["result"]["rate"])
    assert "memorised matchups" in arena.render_generalisation(out)


def test_the_holdout_gap_carries_no_test_statistic(pool):
    """One matchup is not a sample of a deck population, and the report must not pretend it is.

    The old report printed a two-proportion z here as though 360 games on ``the_heist`` vs
    ``embracing_power`` were 360 draws from a deck distribution. There is exactly one holdout
    matchup, so the honest reading is the gap beside the training row's own pairing-to-pairing
    scatter — which is worth several points, more than the gap usually is.
    """
    out = arena.run_generalisation(pool, "random", baseline="random", deck_pairs=3,
                                   games_per_pairing=4, workers=1)
    assert "z_holdout" not in out and "z_unseen" not in out
    assert out["holdout_pairings"] == 1
    assert len(out["training_pairing_rates"]) == 3
    text = arena.render_generalisation(out)
    assert "no test statistic" in text and "z =" not in text
    assert "not a sample of a deck population" in text
    # training and unseen have pairings to spare, so that comparison does get an interval
    lo, hi = out["gap_unseen_interval"][1], out["gap_unseen_interval"][2]
    assert lo <= out["gap_unseen"] <= hi or lo <= 0 <= hi


def test_the_unseen_row_does_not_claim_to_be_out_of_distribution():
    """`random` is 30% of the training mix, so a fresh random draw is not held-out anything."""
    note = dict(arena.POPULATIONS)["unseen-random"]
    assert "Not** out of distribution" in note or "not** out of distribution" in note.lower()
    assert "0.30" in note and D.DEFAULT_MIX["random"] == 0.30


def test_a_training_sample_never_contains_a_holdout_deck(pool):
    """The gap is only honest if the training population really excludes the starters."""
    for pr in arena.sampled_pairings(pool, 40, deck_seed=21):
        assert not is_holdout(pr.deck_a) and not is_holdout(pr.deck_b)


# ------------------------------------------------------------------ reporting
def test_a_section_is_appended_not_overwritten(tmp_path):
    p = tmp_path / "learning.md"
    p.write_text("# Learning\n", encoding="utf-8")
    arena.append_section(p, "### one\n")
    arena.append_section(p, "### two\n")
    text = p.read_text(encoding="utf-8")
    assert text.startswith("# Learning\n") and "### one" in text and text.index("### one") < text.index("### two")


def test_the_json_result_carries_the_ruleset_and_the_seeds(pool, tmp_path):
    pairings = arena.sampled_pairings(pool, 1, deck_seed=6)
    res = arena.head_to_head(pool, "random", "random", pairings, games_per_pairing=4, seed=2,
                             workers=1, sprt=None, deck_seed=6)
    d = json.loads(arena.write_json(tmp_path / "r.json", res.to_json()).read_text())
    assert d["rules"] and d["seed"] == 2 and d["deck_seed"] == 6
    assert d["wilson_low"] <= d["rate"] <= d["wilson_high"]
