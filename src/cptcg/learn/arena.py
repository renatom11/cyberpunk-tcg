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

The four instruments
--------------------

``a-vs-b``          two agents, paired seeds, mirrored seats, swapped decks, SPRT stopping.
``panel``           the frozen benchmark: fixed opponents, fixed decks, fixed seeds, no early
                    stopping, so a win rate is comparable across every future generation.
``exploit``         the same agent honest against itself cheating (determinization replaced by the
                    true state). The gap is the cost of hidden information — **a ceiling for that
                    agent at that budget, not an upper bound on play quality in general.**
``generalisation``  the same agent on training-distribution decks, on the held-out retail starters
                    and on fresh unseen random decks. A growing gap means memorised matchups.

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

from cptcg.agents.base import AGENTS, CHEAT_PREFIX, make_agent
from cptcg.cards.registry import Registry
from cptcg.core.config import DEFAULT_CONFIG, RulesConfig
from cptcg.core.rng import Pcg32
from cptcg.deck.decklist import Decklist
from cptcg.learn.decks import holdout_pairs, sample_pair
from cptcg.sim.runner import run_match
from cptcg.sim.stats import SPRT, two_proportion_z, wilson

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


def agent_exists(name: str) -> bool:
    base = name[len(CHEAT_PREFIX):] if name.startswith(CHEAT_PREFIX) else name
    return base in known_agents()


def require_agent(name: str) -> str:
    if not agent_exists(name):
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

    A pure function of ``deck_seed``: the same seed gives the same decks forever, which is what
    lets the frozen panel pin its decks in a data file rather than in a directory of saved lists.
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
    def avg_turns(self) -> float:
        return self.turns / self.games if self.games else 0.0

    def to_json(self) -> dict:
        lo, hi = self.interval
        d = asdict(self)
        d.update(rate=self.rate, wilson_low=lo, wilson_high=hi, pair_rate=self.pair_rate,
                 avg_turns=self.avg_turns)
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


def load_panel(path: str | Path = PANEL_PATH) -> dict:
    """Read the frozen panel and refuse it if its digest does not match its contents."""
    panel = json.loads(Path(path).read_text(encoding="utf-8"))
    want = panel.get("digest")
    got = panel_digest(panel)
    if want != got:
        raise ValueError(
            f"{path}: the panel definition does not match its digest ({want} on file, {got} now). "
            f"The panel is frozen: if this change is deliberate, update 'digest' to {got} and say "
            f"in docs/learning.md that panel scores before and after are not comparable.")
    return panel


def run_panel(reg: Registry, agent: str, panel: dict | None = None, *, workers: int | None = None,
              progress=None, cfg: RulesConfig = DEFAULT_CONFIG) -> dict:
    """``agent`` against every member of the frozen panel, on the panel's own fixed protocol.

    Members whose agent is not registered in this build (a generation snapshot that does not exist
    yet) are reported as unavailable rather than skipped silently.
    """
    panel = panel or load_panel()
    proto = panel["protocol"]
    pairings = sampled_pairings(reg, proto["deck_pairs"], deck_seed=proto["deck_seed"], label="panel")
    out = {"agent": agent, "panel_version": panel["version"], "panel_digest": panel["digest"],
           "frozen_on": panel["frozen_on"], "protocol": proto, "rules": cfg.digest(),
           "when": _now(), "members": []}
    for m in panel["members"]:
        if not agent_exists(m["agent"]):
            out["members"].append({"id": m["id"], "agent": m["agent"], "label": m["label"],
                                   "available": False, "note": m.get("available_when", "")})
            if progress:
                progress(m["id"], None)
            continue
        res = head_to_head(reg, agent, m["agent"], pairings, games_per_pairing=proto["games_per_pair"],
                           seed=proto["seed"], workers=workers, sprt=None, cfg=cfg,
                           deck_seed=proto["deck_seed"])
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
        out["reference"] = {"agent": reference, "honest": h.to_json(), "cheating": c.to_json(),
                            "gap": c.rate - h.rate,
                            "z": two_proportion_z(c.a_wins, c.games, h.a_wins, h.games)}
    return out


# ------------------------------------------------------- the generalisation gap
#: The deck populations a generalisation run measures over. ``mix=None`` is the training mix.
POPULATIONS = (
    ("training", "the training mix (learn.decks.DEFAULT_MIX), the distribution self-play draws from"),
    ("holdout", "the two retail starters, held out of training entirely"),
    ("unseen-random", "fresh RAM-legal random decks from a deck seed training never used"),
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
    tr, ho = by["training"], by["holdout"]
    un = by["unseen-random"]
    out["gap_holdout"] = tr["rate"] - ho["rate"]
    out["gap_unseen"] = tr["rate"] - un["rate"]
    out["z_holdout"] = two_proportion_z(tr["a_wins"], tr["games"], ho["a_wins"], ho["games"])
    out["z_unseen"] = two_proportion_z(tr["a_wins"], tr["games"], un["a_wins"], un["games"])
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
        "| | games | win rate | 95% Wilson |",
        "|---|---:|---:|---|",
        f"| **{res.agent_a}** | {res.games} | {pct(res.rate)} | {100 * lo:.1f}–{100 * hi:.1f}% |",
        f"| {res.agent_b} | {res.games} | {pct(1 - res.rate)} | "
        f"{100 * (1 - hi):.1f}–{100 * (1 - lo):.1f}% |",
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
    lines = [f"### Frozen panel: {out['agent']} — {out['when']}", "",
             f"Panel `{out['panel_digest']}`, frozen {out['frozen_on']}: "
             f"{out['protocol']['deck_pairs']} deck pairings from deck seed "
             f"{out['protocol']['deck_seed']}, {out['protocol']['games_per_pair']} games each, no "
             f"early stopping. The protocol never changes, so these numbers are comparable across "
             f"every generation.", "",
             "| opponent | games | win rate | 95% Wilson | decisive pairs |",
             "|---|---:|---:|---|---|"]
    for m in out["members"]:
        if not m["available"]:
            lines.append(f"| {m['label']} (`{m['agent']}`) | — | not available yet | — | "
                         f"{m.get('note', '')} |")
            continue
        r = m["result"]
        lines.append(f"| {m['label']} (`{m['agent']}`) | {r['games']} | {pct(r['rate'])} | "
                     f"{100 * r['wilson_low']:.1f}–{100 * r['wilson_high']:.1f}% | "
                     f"{r['pair_wins']}/{r['discordant']} |")
    return "\n".join(lines) + "\n"


def render_exploit(out: dict) -> str:
    d = out["direct"]
    lines = [f"### Cost of hidden information: {out['agent']} — {out['when']}", "",
             f"`{out['cheating_agent']}` is the same agent with determinization replaced by the "
             f"true state: same budget, same evaluation, same policy, perfect information.", "",
             f"Cheating beats honest **{pct(d['rate'])}** "
             f"[{100 * d['wilson_low']:.1f}–{100 * d['wilson_high']:.1f}] over {d['games']} games "
             f"({d['pair_wins']}/{d['discordant']} decisive pairs).", "",
             f"*{out['caveat']}*"]
    ref = out.get("reference")
    if ref:
        h, c = ref["honest"], ref["cheating"]
        lines += ["", f"Against `{ref['agent']}`: honest {rate_cell(h['a_wins'], h['games'])}, "
                      f"cheating {rate_cell(c['a_wins'], c['games'])} — a gap of "
                      f"{100 * ref['gap']:+.1f} points (z = {ref['z']:.2f})."]
    return "\n".join(lines) + "\n"


def render_generalisation(out: dict) -> str:
    lines = [f"### Generalisation gap: {out['agent']} vs {out['baseline']} — {out['when']}", "",
             "The same agent against the same baseline on three deck populations. Both seats draw "
             "from the same population in each row, so the number measures play, not deck strength; "
             "what matters is the difference between the rows.", "",
             "| deck population | games | win rate | 95% Wilson |", "|---|---:|---:|---|"]
    for p in out["populations"]:
        r = p["result"]
        lines.append(f"| {p['name']} — {p['note']} | {r['games']} | {pct(r['rate'])} | "
                     f"{100 * r['wilson_low']:.1f}–{100 * r['wilson_high']:.1f}% |")
    lines += ["", f"Gap to the held-out starters: {100 * out['gap_holdout']:+.1f} points "
                  f"(z = {out['z_holdout']:.2f}). Gap to fresh random decks: "
                  f"{100 * out['gap_unseen']:+.1f} points (z = {out['z_unseen']:.2f}). "
                  "A gap that grows generation over generation means memorised matchups."]
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
