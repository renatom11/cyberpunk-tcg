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
from cptcg.learn.decks import holdout_decks, is_holdout
from cptcg.sim.stats import SPRT, wilson

# The frozen panel, pinned here as well as in its own file. Two locks, both of which a deliberate
# edit must turn: the digest in data/arena/panel.json and this constant.
PANEL_DIGEST = "17064172ad6626e2"
PANEL_MEMBERS = [("random", "random"), ("heuristic", "heuristic"), ("gen0", "gen0")]


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
    assert [(m["id"], m["agent"]) for m in panel["members"]] == PANEL_MEMBERS
    assert panel["protocol"] == {"deck_pairs": 6, "games_per_pair": 60, "deck_seed": 20260910,
                                 "seed": 4242, "sprt": False, "note": panel["protocol"]["note"]}


def test_a_tampered_panel_is_refused(tmp_path):
    panel = arena.load_panel()
    panel["protocol"]["games_per_pair"] = 2
    p = tmp_path / "panel.json"
    p.write_text(json.dumps(panel), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen"):
        arena.load_panel(p)


def test_the_panel_reports_a_missing_member_rather_than_skipping_it(pool):
    """Generation 0 does not exist yet; the row has to say so, not vanish."""
    panel = arena.load_panel()
    small = dict(panel, protocol=dict(panel["protocol"], deck_pairs=1, games_per_pair=4))
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
