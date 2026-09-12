"""The gate: nothing about this project's AI may be claimed without a number from here.

Every instrument in this module answers one question about *play*, never about a deck, and every
one of them is designed so that a deck's strength cannot be mistaken for an agent's.

The balanced design
-------------------

``sim.runner.run_match`` already plays every seed from both seats, so first-player advantage and
shuffle luck cancel for free. That is not enough on its own: in ``run_match(a, b, A, B)`` agent A
always holds deck ``a``, so a strong deck would read as a strong agent. So every match here is
played **twice**, with the agents' deck assignments swapped::

    m0 = run_match(deck_a, deck_b, agent_a, agent_b, ...)     # agent A holds deck a
    m1 = run_match(deck_a, deck_b, agent_b, agent_a, ...)     # agent A holds deck b

Both matches use the same seeds, so ``m0.results[j]`` and ``m1.results[j]`` are the same seed, the
same decks and the same seats — the *only* difference is who is who. Four games per seed, and each
agent has held each deck in each seat. The headline win rate is then over a fully balanced sample.

Those two games also form a **pair**, and the pair is what the sequential test runs on, exactly as
``deck.builder.hill_climb`` pairs a champion against a challenger on shared seeds:

============================  =========================================================
same deck won both games      the *deck* decided the pair; it says nothing about play
different decks won           the *agent* decided; count it for whoever won both games
============================  =========================================================

The SPRT then runs on the discordant pairs only, which strips out most of the deck-and-shuffle
variance and is why a lopsided comparison settles in a few dozen games. The headline rate and its
Wilson interval are still reported over every game played, because that is the number a reader
wants and the paired count is not a win rate.

Decks come from ``learn.decks.sample_pair``, so a match is measured over many freshly sampled
decks rather than one matchup — an agent that is only good with one list has nowhere to hide.

The two error bars, and which one the gate uses
-----------------------------------------------

The games of one deck pairing share decks and shuffles, so they are **not** independent Bernoulli
trials and a binomial interval over all of them is an interval for the wrong question. Every report
therefore prints two:

===================  ==========================================================================
95% Wilson           over the games, **conditional on the deck pairings actually played**. The
                     right number for "how much more would more games on these decks tell me",
                     and the right number for the frozen panel, whose decks never change.
between-pairing      the mean of the per-pairing rates ± t(k-1)·s/√k over the k pairings. The
                     right number for "would this hold on another sample of decks", which is
                     what a claim about an *agent* means.
===================  ==========================================================================

The between-pairing term is the dominant one and it is not small: heuristic vs random over 360
games moves 88.3%–95.0% across five deck seeds while its Wilson intervals are ~5 points wide and
do not all overlap. **A generation-over-generation claim must clear the between-pairing interval**,
not the Wilson one; the renderers say so in the report rather than leaving it to be remembered.

The four instruments
--------------------

``a-vs-b``          two agents, paired seeds, mirrored seats, swapped decks, SPRT stopping.
``panel``           the frozen benchmark: fixed opponents, **decklists stored in the panel file**,
                    fixed seeds, no early stopping, so a win rate is comparable across every
                    future generation.
``exploit``         the same agent honest against itself cheating (determinization replaced by the
                    true state). The gap is the cost of hidden information — **a ceiling for that
                    agent at that budget, not an upper bound on play quality in general.**
``generalisation``  the same agent on training-distribution decks, on the held-out retail starters
                    and on fresh random decks. A growing gap means memorised matchups. The holdout
                    is **one** matchup — the game has exactly two retail starters — so it is
                    reported as a single matchup beside the training row's pairing-to-pairing
                    scatter, and never as a proportion test against a deck population.

The delayed-reward suite, the fifth instrument, is in :mod:`cptcg.learn.delayed`.

Every command writes machine-readable JSON and appends a human-readable section to
``docs/learning.md``, whether or not the numbers flatter the run.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cptcg.agents.base import AGENTS, BUDGET_SEP, CHEAT_PREFIX, WEIGHTS_SEP, make_agent
from cptcg.cards.registry import Registry
from cptcg.core.config import DEFAULT_CONFIG, RulesConfig
from cptcg.core.rng import Pcg32
from cptcg.deck.decklist import Decklist
from cptcg.learn.decks import holdout_pairs, sample_pair
from cptcg.sim.runner import run_match
from cptcg.sim.stats import SPRT, cluster_interval, welch_interval, wilson

ROOT = Path(__file__).resolve().parents[3]

#: The frozen benchmark panel lives in the data directory, not in code, so that freezing it is
#: visible in a diff and auditable in a review.
PANEL_PATH = ROOT / "data" / "arena" / "panel.json"

#: Where a run's machine-readable result goes by default.
OUT_DIR = ROOT / "out" / "arena"

#: The shipped record every run appends to.
DOCS_PATH = ROOT / "docs" / "learning.md"

#: Four games come out of every seed: two seats times two deck assignments.
GAMES_PER_SEED = 4


# --------------------------------------------------------------------- agents
def known_agents() -> list[str]:
    """Agent names ``make_agent`` can build, with the registry warmed."""
    make_agent("random")                       # imports every agent module as a side effect
    return sorted(AGENTS)


def agent_base(name: str) -> str:
    """The registered name inside a decorated one: ``cheat:ismcts@weights.json`` -> ``ismcts``.

    Both decorations travel inside the agent name on purpose, so that a worker process can rebuild
    the same agent from a string. That means every place that validates a name has to know how to
    undress one, and there is exactly one place that does: here.
    """
    if name.startswith(CHEAT_PREFIX):
        name = name[len(CHEAT_PREFIX):]
    # Weights first: a path may contain a colon, and stripping the budget first would eat it.
    # Every decoration ``make_agent`` understands has to be undressed here too — adding one there
    # and not here is how ``ismcts:32@weights.json`` came back as "unknown agent" after a
    # five-hour harvest, from the one function whose docstring promises it knows them all.
    return name.partition(WEIGHTS_SEP)[0].partition(BUDGET_SEP)[0]


def agent_exists(name: str) -> bool:
    base = agent_base(name)
    if base not in known_agents():
        return False
    weights = name.partition(WEIGHTS_SEP)[2]
    # A missing weights file is a typo that would otherwise surface as a stack trace inside a
    # worker, halfway through a run that has already cost an hour.
    return not weights or Path(weights).exists()


def require_agent(name: str) -> str:
    if not agent_exists(name):
        weights = name.partition(WEIGHTS_SEP)[2]
        if weights and agent_base(name) in known_agents():
            raise FileNotFoundError(f"agent {name!r}: no weights at {weights!r}")
        raise KeyError(f"unknown agent {name!r}; known: {known_agents()}")
    return name


# ------------------------------------------------------------------ pairings
@dataclass(frozen=True)
class Pairing:
    """One deck matchup a comparison is measured over."""

    label: str
    deck_a: Decklist
    deck_b: Decklist


def sampled_pairings(reg: Registry, n: int, *, deck_seed: int, mix: dict | None = None,
                     label: str = "sampled") -> list[Pairing]:
    """``n`` fresh deck pairs from the training sampler.

    A pure function of ``deck_seed`` **and of the sampler**: the same seed gives the same decks
    only for as long as ``learn.decks`` and ``deck.builder`` are unchanged. Retuning
    ``DEFAULT_MIX``, the size or curve constants, either builder, or even adding one
    ``data/decks/sample_*.json`` file changes what every seed draws. That is fine for an ad-hoc
    comparison, where both sides are drawn in the same process, and it is fatal for a benchmark
    that must stay comparable for years — which is why the frozen panel stores its decklists
    rather than a seed to redraw them from; see :func:`panel_pairings`.
    """
    rng = Pcg32(deck_seed, seq=101)
    out = []
    for i in range(n):
        a, b = sample_pair(reg, rng, mix=mix)
        out.append(Pairing(f"{label}-{i}", a, b))
    return out


def holdout_pairing(reg: Registry) -> Pairing:
    """The held-out retail starters. Seat order does not matter: the design mirrors seats."""
    (a, b), _ = holdout_pairs(reg)
    return Pairing("holdout", a, b)


# -------------------------------------------------------------------- results
@dataclass
class PairingResult:
    label: str
    deck_a: str
    deck_b: str
    games: int
    a_wins: int


@dataclass
class HeadToHead:
    """Agent A against agent B over a balanced sample. ``a_wins`` counts games, ``pair_wins``
    counts the discordant pairs the SPRT ran on."""

    agent_a: str
    agent_b: str
    games: int = 0
    a_wins: int = 0
    #: Paired comparisons: one per (seed, seat), so two per seed when the decks are swapped, and
    #: exactly half the games. Not the seed count.
    pairs: int = 0
    discordant: int = 0         # pairs the agents, not the decks, decided
    pair_wins: int = 0          # discordant pairs agent A won both games of
    verdict: str = "continue"   # SPRT: continue | high | low | h0
    stopped_early: bool = False
    a_first_wins: int = 0
    a_first_games: int = 0
    #: Games agent A sat in seat 0. Exactly half of them, by construction: the two swapped
    #: matches put each agent in each seat once per seed, whatever either of them then chooses.
    a_seat0_games: int = 0
    turns: int = 0
    reasons: dict = field(default_factory=dict)
    per_pairing: list = field(default_factory=list)
    seconds: float = 0.0
    seed: int = 0
    deck_seed: int = 0
    rules: str = DEFAULT_CONFIG.digest()
    #: False when the deck assignments were not swapped: agent A held deck A in every game, so a
    #: strong deck reads as a strong agent. Never the default; see ``head_to_head``.
    balanced: bool = True

    @property
    def rate(self) -> float:
        return self.a_wins / self.games if self.games else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson(self.a_wins, self.games)

    @property
    def pair_rate(self) -> float:
        return self.pair_wins / self.discordant if self.discordant else 0.5

    @property
    def pairing_rates(self) -> list[float]:
        """Agent A's win rate within each deck pairing — the cluster-level observations."""
        return [r.a_wins / r.games for r in self.per_pairing if r.games]

    @property
    def cluster(self) -> tuple[float, float, float] | None:
        """(mean, low, high): the 95% interval over the *deck pairings*, or ``None`` below two.

        This is the honest error bar for a claim about the agent, because the unit that was
        randomly sampled is the deck pairing and not the game. ``interval`` (Wilson) is the right
        number only conditional on the pairings that were actually played.

        Clamped to [0, 1] the way ``wilson`` is: a win rate cannot be 110%, and a report that
        prints one has stopped being read. Clamping is for *rates* only — a gap between two rates
        is unbounded and its interval is left alone.
        """
        c = cluster_interval(self.pairing_rates)
        return None if c is None else (c[0], max(0.0, c[1]), min(1.0, c[2]))

    @property
    def avg_turns(self) -> float:
        return self.turns / self.games if self.games else 0.0

    def to_json(self) -> dict:
        lo, hi = self.interval
        d = asdict(self)
        d.update(rate=self.rate, wilson_low=lo, wilson_high=hi, pair_rate=self.pair_rate,
                 avg_turns=self.avg_turns, pairings=len(self.per_pairing),
                 pairing_rates=self.pairing_rates)
        c = self.cluster
        d.update(cluster_mean=c[0] if c else None, cluster_low=c[1] if c else None,
                 cluster_high=c[2] if c else None)
        return d


def head_to_head(reg: Registry, agent_a: str, agent_b: str, pairings, *,
                 games_per_pairing: int = 60, seed: int = 4242, workers: int | None = None,
                 sprt: SPRT | None = None, min_games: int = 0, cfg: RulesConfig = DEFAULT_CONFIG,
                 progress=None, deck_seed: int = 0, swap_decks: bool = True) -> HeadToHead:
    """Play ``agent_a`` against ``agent_b`` over ``pairings``, balanced and paired.

    ``games_per_pairing`` is rounded up to a multiple of four, because a seed produces four games
    (two seats times two deck assignments) and a partial seed would unbalance the design.

    ``sprt`` stops the run as soon as the paired test settles, once ``min_games`` games have been
    played; pass ``None`` for a fixed sample, which is what the frozen panel needs.

    ``swap_decks=False`` drops the second match, so agent A holds deck A in **every** game. That is
    the older, unbalanced way of measuring — it credits an agent with the stronger half of every
    pairing — and it exists here only so the difference can be re-derived on demand
    (``--no-swap``). With it off there are no pairs, so the sequential test falls back to the raw
    game outcomes and is correspondingly noisier.
    """
    require_agent(agent_a)
    require_agent(agent_b)
    pairings = list(pairings)
    per_seed = GAMES_PER_SEED if swap_decks else GAMES_PER_SEED // 2
    seeds_per_pairing = max(1, (games_per_pairing + per_seed - 1) // per_seed)
    res = HeadToHead(agent_a, agent_b, seed=seed, deck_seed=deck_seed, rules=cfg.digest(),
                     balanced=swap_decks, verdict="continue" if sprt is not None else "off")
    t0 = time.perf_counter()
    for k, pr in enumerate(pairings):
        base = seed + k * 1_000_003
        n = seeds_per_pairing * 2                       # run_match plays each seed from both seats
        m0 = run_match(pr.deck_a, pr.deck_b, agent_a, agent_b, n, seed=base, cfg=cfg, workers=workers)
        m1 = None
        if swap_decks:
            m1 = run_match(pr.deck_a, pr.deck_b, agent_b, agent_a, n, seed=base, cfg=cfg,
                           workers=workers)
            if len(m0.results) != len(m1.results):      # pragma: no cover - run_match is deterministic
                raise RuntimeError("swapped matches came back with different lengths")
        row = PairingResult(pr.label, pr.deck_a.name, pr.deck_b.name, 0, 0)
        for j, r0 in enumerate(m0.results):
            r1 = m1.results[j] if m1 is not None else None
            if r1 is not None and (r0.seed, r0.deck_a_seat) != (r1.seed, r1.deck_a_seat):
                raise RuntimeError("swapped matches are not aligned")   # pragma: no cover
            a0 = r0.winner_deck == "A"                  # agent A held deck a in m0 ...
            games = [(r0, True)]
            if r1 is not None:
                a1 = r1.winner_deck == "B"              # ... and deck b in m1
                games.append((r1, False))
                res.pairs += 1
                if a0 == a1:                            # different decks won: the agents decided
                    res.discordant += 1
                    res.pair_wins += a0
            else:
                res.pairs += 1
                res.discordant += 1                     # no pairing available: test the raw games
                res.pair_wins += a0
            for r, agent_a_is_deck_a in games:
                a_won = (r.winner_deck == "A") == agent_a_is_deck_a
                # Agent A holds deck A in m0 and deck B in m1, and run_match seats deck A at
                # r.deck_a_seat, so agent A's seat flips between the two games of a pair.
                a_seat = r.deck_a_seat if agent_a_is_deck_a else 1 - r.deck_a_seat
                # Who goes first is a *decision* (ruling 028: the d20 winner chooses), so this is
                # descriptive and not a balance check; the seat count above is the balance check.
                a_first = (r.first_deck == "A") == agent_a_is_deck_a
                res.a_seat0_games += a_seat == 0
                res.games += 1
                row.games += 1
                res.a_wins += a_won
                row.a_wins += a_won
                res.a_first_games += a_first
                res.a_first_wins += a_first and a_won
                res.turns += r.turns
                res.reasons[r.end_reason] = res.reasons.get(r.end_reason, 0) + 1
        res.per_pairing.append(row)
        if sprt is not None and res.discordant:
            res.verdict = sprt.test(res.pair_wins, res.discordant)
        if progress:
            progress(res, row)
        if sprt is not None and res.verdict != "continue" and res.games >= min_games:
            res.stopped_early = k + 1 < len(pairings)
            break
    res.seconds = time.perf_counter() - t0
    return res


# ------------------------------------------------------------------ the panel
def panel_digest(panel: dict) -> str:
    """A digest of the panel definition, ignoring the stored digest itself.

    The point of a frozen panel is that a win rate against it is comparable across generations
    forever, so any change to the opponents, the decks, the seeds or the game count must be a
    deliberate, visible edit. This digest is checked on load and pinned by a test.
    """
    body = {k: v for k, v in panel.items() if k != "digest"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def _deck_from_json(d: dict) -> Decklist:
    return Decklist.from_counts(d["name"], list(d["legends"]), dict(d["main"]),
                                **dict(d.get("meta", {})))


def decks_digest(panel: dict) -> str:
    """A digest of the panel's stored decklists alone, by contents rather than by file layout.

    Over ``(name, legends, sorted(main))`` for every deck in pairing order, so it is blind to how
    the JSON happens to be formatted, to the order copies are written in and to any editing of the
    surrounding prose — and sensitive to a single card changing in a single list. ``panel_digest``
    covers the decks too, being a digest of the whole body; this one exists so that the *decks*
    can be quoted in a report and checked in one line, which is what makes the freezing auditable
    rather than merely asserted.
    """
    body = []
    for pr in panel["decks"]:
        row = [pr["label"]]
        for side in ("a", "b"):
            d = _deck_from_json(pr[side])
            row.append([d.name, list(d.legends), sorted(d.main)])
        body.append(row)
    return hashlib.sha256(json.dumps(body, separators=(",", ":")).encode()).hexdigest()[:16]


def panel_pairings(reg: Registry, panel: dict) -> list[Pairing]:
    """The panel's deck pairings, read from the file — never redrawn from the sampler.

    This is the whole difference between a benchmark and a moving target. The decklists are stored
    in ``data/arena/panel.json`` verbatim, so retuning ``learn.decks`` or ``deck.builder``, or
    adding a hand-built sample list, cannot silently re-base the benchmark: the panel plays the
    same twelve decks in 2027 that it played the day it was frozen, whatever the sampler has since
    become.

    Every card is looked up in ``reg`` here, so a card that leaves the pool fails loudly at load
    time with the deck and the id named, rather than confusingly in the middle of a game.
    """
    out = []
    for pr in panel["decks"]:
        sides = []
        for side in ("a", "b"):
            d = _deck_from_json(pr[side])
            for cid in d.legends + d.main:
                try:
                    reg.get(cid)
                except KeyError:
                    raise ValueError(
                        f"the frozen panel's deck {d.name!r} in pairing {pr['label']!r} plays "
                        f"{cid!r}, which this build's card pool does not have. The panel cannot be "
                        f"played as frozen, and a score from a repaired panel is not comparable "
                        f"with the ones already in docs/learning.md.") from None
            sides.append(d)
        out.append(Pairing(pr["label"], sides[0], sides[1]))
    return out


def load_panel(path: str | Path = PANEL_PATH) -> dict:
    """Read the frozen panel and refuse it unless it matches both of its digests.

    Two checks, because they fail on different mistakes: ``panel_digest`` catches any edit at all
    to the file, and ``decks_digest`` catches an edit to the decklists specifically, in a form that
    survives reformatting and can be quoted in a report.
    """
    panel = json.loads(Path(path).read_text(encoding="utf-8"))
    want = panel.get("digest")
    got = panel_digest(panel)
    if want != got:
        raise ValueError(
            f"{path}: the panel definition does not match its digest ({want} on file, {got} now). "
            f"The panel is frozen: if this change is deliberate, update 'digest' to {got} and say "
            f"in docs/learning.md that panel scores before and after are not comparable.")
    if "decks" not in panel:
        raise ValueError(
            f"{path}: this panel has no 'decks' block, so its opponents' decklists would have "
            f"to be redrawn from the sampler and would change whenever the sampler does. A panel "
            f"without "
            f"its decks written down is not frozen; see arena.panel_pairings.")
    want = panel.get("decks_digest")
    got = decks_digest(panel)
    if want != got:
        raise ValueError(
            f"{path}: the panel's decklists do not match their digest ({want} on file, {got} now). "
            f"The decks are the benchmark: scores before and after this edit are not comparable. "
            f"If it is deliberate, update 'decks_digest' to {got}, update 'digest' too, and say in "
            f"docs/learning.md.")
    if len(panel["decks"]) != panel["protocol"]["deck_pairs"]:
        raise ValueError(
            f"{path}: the protocol says {panel['protocol']['deck_pairs']} deck pairings but "
            f"{len(panel['decks'])} are stored.")
    return panel


def run_panel(reg: Registry, agent: str, panel: dict | None = None, *, workers: int | None = None,
              progress=None, cfg: RulesConfig = DEFAULT_CONFIG) -> dict:
    """``agent`` against every member of the frozen panel, on the panel's own fixed protocol.

    Members whose agent is not registered in this build (a generation snapshot that does not exist
    yet) are reported as unavailable rather than skipped silently.
    """
    panel = panel or load_panel()
    proto = panel["protocol"]
    pairings = panel_pairings(reg, panel)
    out = {"agent": agent, "panel_version": panel["version"], "panel_digest": panel["digest"],
           "decks_digest": decks_digest(panel), "frozen_on": panel["frozen_on"], "protocol": proto,
           "rules": cfg.digest(), "when": _now(), "members": []}
    for m in panel["members"]:
        if not agent_exists(m["agent"]):
            out["members"].append({"id": m["id"], "agent": m["agent"], "label": m["label"],
                                   "available": False, "note": m.get("available_when", "")})
            if progress:
                progress(m["id"], None)
            continue
        res = head_to_head(reg, agent, m["agent"], pairings, games_per_pairing=proto["games_per_pair"],
                           seed=proto["seed"], workers=workers, sprt=None, cfg=cfg)
        row = {"id": m["id"], "agent": m["agent"], "label": m["label"], "available": True,
               "result": res.to_json()}
        out["members"].append(row)
        if progress:
            progress(m["id"], res)
    return out


# ------------------------------------------------- the cheating upper bound
def run_exploit(reg: Registry, agent: str, *, deck_pairs: int = 6, games_per_pairing: int = 60,
                seed: int = 909, deck_seed: int = 77, workers: int | None = None,
                reference: str | None = None, cfg: RulesConfig = DEFAULT_CONFIG,
                progress=None) -> dict:
    """The same agent, honest against itself cheating.

    Cheating here means exactly one thing: the agent searches the **true** state instead of a world
    sampled from what its seat may legitimately know (``core.view.determinize``). Everything else —
    the budget, the evaluation, the policy — is identical, so the gap between the two is the cost of
    hidden information *for this agent at this budget*. It is a ceiling for that agent, and it is
    **not** an upper bound on how well this game can be played.

    An agent that does not consult ``core.view`` has nothing to cheat with, and this raises rather
    than reporting a meaningless zero.
    """
    require_agent(agent)
    cheat = CHEAT_PREFIX + agent
    make_agent(cheat)                      # raises with a clear message if the agent cannot cheat
    pairings = sampled_pairings(reg, deck_pairs, deck_seed=deck_seed, label="exploit")
    head = head_to_head(reg, cheat, agent, pairings, games_per_pairing=games_per_pairing,
                        seed=seed, workers=workers, sprt=None, cfg=cfg, deck_seed=deck_seed,
                        progress=(lambda r, row: progress("cheating vs honest", r)) if progress else None)
    out = {"agent": agent, "cheating_agent": cheat, "rules": cfg.digest(), "when": _now(),
           "deck_seed": deck_seed, "seed": seed, "direct": head.to_json(), "reference": None,
           "caveat": ("This is a ceiling for this agent at this budget — the value of perfect "
                      "information to its own search — not an upper bound on play quality.")}
    if reference:
        require_agent(reference)
        h = head_to_head(reg, agent, reference, pairings, games_per_pairing=games_per_pairing,
                         seed=seed + 1, workers=workers, sprt=None, cfg=cfg, deck_seed=deck_seed)
        c = head_to_head(reg, cheat, reference, pairings, games_per_pairing=games_per_pairing,
                         seed=seed + 1, workers=workers, sprt=None, cfg=cfg, deck_seed=deck_seed)
        # Both rows were played on the *same* pairings, so the comparison is paired: the interval
        # goes over the per-pairing differences, which cancels the deck term instead of ignoring
        # it. A two-proportion z over the pooled games would treat clustered games as independent
        # trials and overstate its own precision.
        diffs = [x - y for x, y in zip(c.pairing_rates, h.pairing_rates)]
        out["reference"] = {"agent": reference, "honest": h.to_json(), "cheating": c.to_json(),
                            "gap": c.rate - h.rate, "pairing_gaps": diffs,
                            "gap_interval": cluster_interval(diffs)}
    return out


# ------------------------------------------------------- the generalisation gap
#: The deck populations a generalisation run measures over. ``mix=None`` is the training mix.
POPULATIONS = (
    ("training", "the training mix (learn.decks.DEFAULT_MIX), the distribution self-play draws from"),
    ("holdout", "the two retail starters, held out of training entirely — **one** matchup, because "
                "the game has exactly two of them"),
    ("unseen-random", "fresh RAM-legal random decks on a deck seed training never used. **Not** "
                      "out of distribution: `random` is the 0.30 slice of the training mix, so "
                      "this row is a fresh draw from a source the model does train on, and it "
                      "isolates the unstructured end of that mix rather than testing transfer"),
)


def run_generalisation(reg: Registry, agent: str, *, baseline: str = "heuristic",
                       deck_pairs: int = 6, games_per_pairing: int = 60, seed: int = 5150,
                       training_seed: int = 31, unseen_seed: int = 8675309,
                       workers: int | None = None, cfg: RulesConfig = DEFAULT_CONFIG,
                       progress=None) -> dict:
    """``agent`` against a fixed ``baseline`` on three deck populations.

    Both seats draw from the same population in every run, so the number is about play and not
    about which population is stronger; what matters is the *difference* between the three.

    A gap that grows generation over generation means the model is memorising matchups instead of
    learning the game. It is reported every generation whether or not it flatters the run.

    The rows are not statistically alike, and the report says so rather than papering over it. The
    training and unseen rows are ``deck_pairs`` pairings each, so their difference gets an interval
    over the pairings. The holdout row is **one** matchup — ``the_heist`` against
    ``embracing_power``, the only two retail starters that exist — so it has no deck-level variance
    to estimate and gets no test statistic; it is reported as the single matchup it is, next to the
    training row's pairing-to-pairing scatter, which is the only honest thing to read it against.
    """
    require_agent(agent)
    require_agent(baseline)
    out = {"agent": agent, "baseline": baseline, "rules": cfg.digest(), "when": _now(),
           "populations": []}
    sets = {
        "training": sampled_pairings(reg, deck_pairs, deck_seed=training_seed, label="train"),
        "holdout": [holdout_pairing(reg)],
        "unseen-random": sampled_pairings(reg, deck_pairs, deck_seed=unseen_seed,
                                          mix={"random": 1.0}, label="unseen"),
    }
    # The holdout population is a single matchup, so it gets the whole budget on that pairing.
    budget = {"training": games_per_pairing, "holdout": games_per_pairing * deck_pairs,
              "unseen-random": games_per_pairing}
    for name, note in POPULATIONS:
        res = head_to_head(reg, agent, baseline, sets[name], games_per_pairing=budget[name],
                           seed=seed, workers=workers, sprt=None, cfg=cfg)
        out["populations"].append({"name": name, "note": note, "result": res.to_json()})
        if progress:
            progress(name, res)
    by = {p["name"]: p["result"] for p in out["populations"]}
    tr, ho, un = by["training"], by["holdout"], by["unseen-random"]
    out["gap_holdout"] = tr["rate"] - ho["rate"]
    out["gap_unseen"] = tr["rate"] - un["rate"]
    # No test statistic against the holdout. It is ONE matchup, so its games are not a sample of a
    # deck population and any two-proportion z over them would be answering a question the data
    # cannot answer — and answering it far too confidently, since the pairing-to-pairing scatter in
    # the training row alone is worth several points, more than the gap being reported. What a
    # reader needs instead is that scatter, so the holdout gap can be read against it.
    out["training_pairing_rates"] = tr["pairing_rates"]
    out["training_cluster"] = [tr["cluster_mean"], tr["cluster_low"], tr["cluster_high"]]
    out["holdout_pairings"] = len(ho["per_pairing"])
    out["holdout_inside_training_spread"] = bool(
        tr["pairing_rates"] and min(tr["pairing_rates"]) <= ho["rate"] <= max(tr["pairing_rates"]))
    # Training vs unseen-random are two independent samples of six pairings each, so the difference
    # of their pairing means gets a Welch interval on the cluster-level observations.
    out["gap_unseen_interval"] = welch_interval(tr["pairing_rates"], un["pairing_rates"])
    return out


# ------------------------------------------------------------------- reporting
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def rate_cell(k: int, n: int) -> str:
    if not n:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f}% [{100 * lo:.1f}–{100 * hi:.1f}]"


def band(iv: tuple[float, float, float] | None, *, signed: bool = False) -> str:
    """A (mean, low, high) triple as percentage points, or the reason there is no interval."""
    if iv is None:
        return "no interval (one deck pairing: nothing to estimate deck-level spread from)"
    m, lo, hi = iv
    if signed:      # "+2.5–-9.1" would be unreadable, so signed bands spell the range out
        return f"{100 * m:+.1f} [{100 * lo:+.1f} to {100 * hi:+.1f}]"
    return f"{100 * m:.1f} [{100 * lo:.1f}–{100 * hi:.1f}]"


def between_pairing_line(res: "HeadToHead", *, subject: str) -> str:
    """The paragraph that says which of the two error bars answers which question.

    Printed under every head-to-head table, because the Wilson interval above it is the one a
    reader will otherwise quote, and it is the interval for a question nobody is asking.
    """
    rates = res.pairing_rates
    if not rates:
        return ""
    spread = (f"{100 * min(rates):.1f}–{100 * max(rates):.1f}%" if len(rates) > 1
              else f"{100 * rates[0]:.1f}%")
    c = res.cluster
    if c is None:
        return (f"Measured on **one** deck pairing ({spread}), so the Wilson interval above is the "
                f"whole story for that matchup and there is no deck-level spread to estimate. It "
                f"is not an estimate of {subject} on decks in general.")
    return (f"The Wilson interval above is **conditional on these {len(rates)} deck pairings**: it "
            f"says what more games on these decks would tell you, and nothing about other decks. "
            f"Per-pairing rates run {spread}; over the deck population the mean is {band(c)}% "
            f"(t{len(rates) - 1} on {len(rates)} pairings). **That second band is the error bar "
            f"for {subject}**, and a generation-over-generation claim has to clear it rather "
            f"than the Wilson one — the same protocol on five different deck samples moves "
            f"several points while nothing about the agents changes. It is estimated from only "
            f"{len(rates)} "
            f"pairings, so it is itself noisy and can land either side of the Wilson bracket: "
            f"narrower when the pairings happened to agree, much wider when one of them did not.")


_VERDICT = {
    "off": "no sequential test was run (fixed sample)",
    "high": "agent A is stronger (SPRT accepted H1)",
    "low": "agent B is stronger (SPRT accepted H1 the other way)",
    "h0": "no difference of this size (SPRT accepted H0)",
    "continue": "undecided at this sample size",
}


def render_head_to_head(res: HeadToHead, *, title: str | None = None, note: str = "") -> str:
    lo, hi = res.interval
    lines = [f"### {title or f'{res.agent_a} vs {res.agent_b}'} — {_now()}", ""]
    if note:
        lines += [note, ""]
    lines += [
        f"{res.games} games over {len(res.per_pairing)} deck pairings, "
        + (f"{res.pairs} paired comparisons — every seed played from both seats and with the deck "
           f"assignments swapped"
           if res.balanced else
           "seats mirrored but deck assignments **not** swapped — agent A held deck A in every "
           "game, so deck strength is inside this number")
        + f". Ruleset `{res.rules}`, {res.seconds:.1f}s.",
        "",
        "| | games | win rate | 95% Wilson (these decks) |",
        "|---|---:|---:|---|",
        f"| **{res.agent_a}** | {res.games} | {pct(res.rate)} | {100 * lo:.1f}–{100 * hi:.1f}% |",
        f"| {res.agent_b} | {res.games} | {pct(1 - res.rate)} | "
        f"{100 * (1 - hi):.1f}–{100 * (1 - lo):.1f}% |",
        "",
        between_pairing_line(res, subject=f"{res.agent_a}'s strength"),
        "",
        (f"Paired test: {res.pair_wins} of {res.discordant} decisive pairs "
         f"({pct(res.pair_rate)})" if res.balanced else
         f"Unpaired test on {res.discordant} games ({pct(res.pair_rate)})")
        + f" — {_VERDICT.get(res.verdict, res.verdict)}."
        + (" Stopped early." if res.stopped_early else ""),
        "",
        f"{res.agent_a} sat in seat 0 in {res.a_seat0_games} of {res.games} games"
        + (" — exactly half, by construction. " if res.a_seat0_games * 2 == res.games else ". ")
        + f"{res.agent_a} on the play: {rate_cell(res.a_first_wins, res.a_first_games)} "
        f"(who goes first is the d20 winner's *choice*, so this is description, not balance). "
        f"Average game length {res.avg_turns:.1f} turns. End reasons: "
        + ", ".join(f"{k} {v}" for k, v in sorted(res.reasons.items())) + ".",
        "",
        "| deck pairing | games | " + f"{res.agent_a} win rate |",
        "|---|---:|---|",
    ]
    for row in res.per_pairing:
        lines.append(f"| `{row.label}` {row.deck_a} vs {row.deck_b} | {row.games} | "
                     f"{rate_cell(row.a_wins, row.games)} |")
    return "\n".join(lines) + "\n"


def render_panel(out: dict) -> str:
    proto = out["protocol"]
    lines = [f"### Frozen panel: {out['agent']} — {out['when']}", "",
             f"Panel `{out['panel_digest']}`, decks `{out['decks_digest']}`, frozen "
             f"{out['frozen_on']}: {proto['deck_pairs']} deck pairings whose **decklists are "
             f"stored verbatim in `data/arena/panel.json`** and are never redrawn from the "
             f"sampler, {proto['games_per_pair']} games each, no early stopping. Both digests "
             f"are checked on load, so these numbers are comparable across every generation as "
             f"long as "
             f"they read `{out['panel_digest']}` / `{out['decks_digest']}`.", "",
             "| opponent | games | win rate | 95% Wilson (these decks) | per-pairing spread | "
             "decisive pairs |",
             "|---|---:|---:|---|---|---|"]
    for m in out["members"]:
        if not m["available"]:
            lines.append(f"| {m['label']} (`{m['agent']}`) | — | not available yet | — | — | "
                         f"{m.get('note', '')} |")
            continue
        r = m["result"]
        rates = r.get("pairing_rates") or []
        spread = (f"{100 * min(rates):.1f}–{100 * max(rates):.1f}%" if len(rates) > 1 else "—")
        lines.append(f"| {m['label']} (`{m['agent']}`) | {r['games']} | {pct(r['rate'])} | "
                     f"{100 * r['wilson_low']:.1f}–{100 * r['wilson_high']:.1f}% | {spread} | "
                     f"{r['pair_wins']}/{r['discordant']} |")
    lines += ["", "Here the Wilson interval is the right one and the *only* one that changes "
                  "between generations: the decks are fixed by the panel, so nothing but more "
                  "games is being sampled. The per-pairing spread is printed beside it as a "
                  "reminder of what the panel is not — a panel score is a score on these twelve "
                  "decklists, and generalises no further than they do. For a claim about play in "
                  "general, use the "
                  "between-pairing interval from `a-vs-b` or `generalisation`."]
    return "\n".join(lines) + "\n"


def render_exploit(out: dict) -> str:
    d = out["direct"]
    lines = [f"### Cost of hidden information: {out['agent']} — {out['when']}", "",
             f"`{out['cheating_agent']}` is the same agent with determinization replaced by the "
             f"true state: same budget, same evaluation, same policy, perfect information.", "",
             f"Cheating beats honest **{pct(d['rate'])}** "
             f"[{100 * d['wilson_low']:.1f}–{100 * d['wilson_high']:.1f}] over {d['games']} games "
             f"({d['pair_wins']}/{d['discordant']} decisive pairs), the bracket conditional on "
             f"{d.get('pairings', 0)} deck pairings; over the deck population "
             + (f"{band((d['cluster_mean'], d['cluster_low'], d['cluster_high']))}%."
                if d.get("cluster_mean") is not None else
                "there is only one pairing, so no deck-level band can be estimated."),
             "", f"*{out['caveat']}*"]
    ref = out.get("reference")
    if ref:
        h, c = ref["honest"], ref["cheating"]
        lines += ["", f"Against `{ref['agent']}`: honest {rate_cell(h['a_wins'], h['games'])}, "
                      f"cheating {rate_cell(c['a_wins'], c['games'])} — a gap of "
                      f"{100 * ref['gap']:+.1f} points"
                      + (f", 95% paired interval over the deck pairings "
                         f"{band(ref['gap_interval'], signed=True)} points."
                         if ref.get("gap_interval") else
                         " (one deck pairing, so no interval).")
                      + " Both variants played the same pairings, so the comparison is paired and "
                        "the deck term cancels rather than being assumed away."]
    return "\n".join(lines) + "\n"


def render_generalisation(out: dict) -> str:
    lines = [f"### Generalisation gap: {out['agent']} vs {out['baseline']} — {out['when']}", "",
             "The same agent against the same baseline on three deck populations. Both seats draw "
             "from the same population in each row, so the number measures play, not deck strength; "
             "what matters is the difference between the rows.", "",
             "| deck population | pairings | games | win rate | 95% Wilson (these decks) | "
             "per-pairing spread |", "|---|---:|---:|---:|---|---|"]
    for p in out["populations"]:
        r = p["result"]
        rates = r.get("pairing_rates") or []
        spread = (f"{100 * min(rates):.1f}–{100 * max(rates):.1f}%" if len(rates) > 1
                  else "one matchup")
        lines.append(f"| {p['name']} — {p['note']} | {r.get('pairings', len(rates))} | "
                     f"{r['games']} | {pct(r['rate'])} | "
                     f"{100 * r['wilson_low']:.1f}–{100 * r['wilson_high']:.1f}% | {spread} |")
    tr = out["training_pairing_rates"]
    spread = f"{100 * min(tr):.1f}–{100 * max(tr):.1f}%" if tr else "n/a"
    inside = ("inside" if out["holdout_inside_training_spread"] else "outside")
    lines += [
        "",
        f"**Gap to the held-out starters: {100 * out['gap_holdout']:+.1f} points, and no test "
        f"statistic.** The holdout is {out['holdout_pairings']} matchup, so those games are not a "
        f"sample of a deck population and a two-proportion z over them would claim a precision the "
        f"design cannot support. Read it against the training row's own scatter instead: its "
        f"{len(tr)} pairings run {spread}, which puts the holdout rate {inside} the range the "
        f"training decks themselves cover.",
        "",
        f"Gap to fresh random decks: {100 * out['gap_unseen']:+.1f} points, "
        + (f"95% interval over the pairings {band(out['gap_unseen_interval'], signed=True)} points "
           f"(Welch, two independent samples of deck pairings)."
           if out["gap_unseen_interval"] else "with too few pairings for an interval.")
        + " Both rows have deck pairings to spare, so this comparison is between deck *populations*"
          " and not between two piles of games.",
        "",
        "A gap that grows generation over generation means memorised matchups. Watch the change in "
        "these numbers, and only trust a change that is large against the per-pairing spread "
        "beside it.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- persistence
def write_json(path: str | Path, data: dict) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, default=str) + "\n", encoding="utf-8")
    return p


def append_section(path: str | Path, text: str) -> Path:
    """Append one report section to ``docs/learning.md`` (or wherever), creating it if needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    sep = "" if not old else ("\n" if old.endswith("\n") else "\n\n")
    p.write_text(old + sep + "\n" + text.rstrip("\n") + "\n", encoding="utf-8")
    return p
