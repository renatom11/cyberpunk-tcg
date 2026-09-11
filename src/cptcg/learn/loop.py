"""The generational loop: what a generation is, who it plays, and what lets it be promoted.

``tools/learn.py`` is the driver that runs harvests, fits and arenas as subprocesses. This module
is the part of the loop worth testing without playing a game: the ledger of generations, the
opponent schedule, the promotion rule, and the drift check. It is pure stdlib, like everything
under ``src/cptcg``.

Why this is not "self-play, refit, repeat"
------------------------------------------
Because that is the version that is known to fail, and it fails quietly. Three results from
projects that had the compute to find out:

* **AlphaGo Zero and KataGo** reached superhuman strength on pure self-play and still carried
  blind spots that their own games never probed — Go ladders early on, and later the cyclic-group
  shape that let a far weaker adversary beat a superhuman KataGo. A player trained only against
  itself learns what it needs to beat itself, which is not the same as learning the game.
* **Stockfish's** network never got to define its own test: a candidate is promoted only after an
  SPRT against the incumbent over games started from a fixed, deliberately diverse opening book,
  and its search — the part that catches evaluation errors — is frozen and hand-written. The net
  supplies opinion; something that cannot be corrupted by the net supplies the check.
* **AlphaStar** found that "beat the current best" is a weaker requirement than it sounds, and ran
  a *league*: past versions and purpose-built exploiters stayed in the opponent pool so a strategy
  could not win by being unfamiliar.

We have no human games for this game and never will, so there is no human anchor. What we do have
is three things that do not move: the frozen heuristic agent, the two retail starter decks that
were deliberately kept out of every harvest, and the delayed-reward suite of positions with
verified winning lines. Everything below is arranged so that those three, and not the loop's
opinion of itself, decide whether a generation is kept.

The four countermeasures this module implements
-----------------------------------------------
1. **Generation explores, gating does not.** Games played to *make training data* run with root
   Dirichlet noise and early-move temperature sampling on, so the data keeps covering moves the
   current policy has learned to dismiss. Games played to *decide promotion* run with both off, at
   full strength. This is the AlphaZero protocol and the two settings must never be swapped: noisy
   games make better data and a worse measurement.
2. **The opponent is a pool, not a mirror.** ``opponent_schedule`` mixes the current best against
   itself, against a uniformly sampled *past* generation, against the frozen heuristic and against
   random play. A generation that only ever saw itself would be training on the narrowest
   distribution available to it.
3. **Promotion needs three yeses, and any one no is a no.** Beating the incumbent by SPRT is
   necessary and not sufficient: the candidate must also not regress against the frozen reference
   panel, and must not solve fewer delayed-reward positions. A net that wins the mirror while
   going backwards against something that cannot move is the exact signature of drift.
4. **Non-transitivity is measured, not assumed away.** After a promotion, the new best plays every
   earlier generation. If generation N beats N-1 but loses to N-5, the ladder is a circle and the
   loop is chasing itself; ``drift_report`` finds that and says so.

None of the four is free. (1) costs the noise-on games, which are worse games. (2) spends part of
every generation's budget on opponents that are not the current best. (3) rejects candidates that
a mirror-only gate would have accepted. (4) costs a small round robin per promotion. They are
here because the failure they prevent is invisible until it is expensive.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cptcg.core.rng import Pcg32

#: The name of the frozen, hand-written agent. It is the anchor that cannot drift because nothing
#: in this loop may edit it; ``agents/heuristic.py`` is frozen by project rule and by test.
ANCHOR = "heuristic"
FLOOR = "random"

#: How a generation's games are divided among opponents. Proportions, not counts; they are a
#: *choice* and not yet a measurement, and they are written down here so that changing them is a
#: visible act rather than a drift. `self` is the current best playing itself, which is where most
#: of the signal is; the rest is what stops the distribution narrowing.
SCHEDULE: tuple[tuple[str, float], ...] = (
    ("self", 0.60),        # current best vs current best — the bulk of the learning signal
    ("past", 0.25),        # vs a uniformly sampled earlier generation — the league
    (ANCHOR, 0.10),        # vs the frozen heuristic — a fixed point the loop cannot move
    (FLOOR, 0.05),         # vs random — keeps wild, off-policy positions in the data
)

#: How many generations of examples a fit may see. A window rather than everything, because the
#: oldest generations were produced by a materially worse player; and a window rather than one,
#: because fitting only the newest generation is how a net forgets what it used to know.
REPLAY_WINDOW = 5

#: A candidate may be this many points worse than the incumbent against the frozen panel before it
#: is rejected as a regression, even if it beat the incumbent head to head. Not zero, because the
#: panel is itself a sample and a point or two is noise; not large, because this is the check that
#: catches drift.
PANEL_REGRESSION_TOLERANCE = 3.0


# ---------------------------------------------------------------------- the ledger
@dataclass
class GenerationRecord:
    """One turn of the handle, written down whether it was kept or thrown away."""

    n: int
    seed: int
    status: str = "generating"      # generating | fitting | gating | promoted | rejected | failed
    games: int = 0
    weights: str = ""               # path to this generation's fitted weights
    parent: str = ""                # the incumbent it was fitted to beat
    started: str = ""
    finished: str = ""
    #: Every measurement that decided this generation's fate, in the shape the arena wrote it.
    gate: dict = field(default_factory=dict)
    reason: str = ""                # why it was promoted or rejected, in one sentence
    notes: list[str] = field(default_factory=list)


class Ledger:
    """The loop's memory: an append-only list of generations on disk.

    Kept as one small JSON file rather than a database because the loop must survive a container
    being wiped mid-generation, and because a human should be able to read what happened without
    running anything. Every write is atomic (write beside, rename) so an interrupt can lose the
    newest generation but never corrupt the history.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.path = self.root / "ledger.json"
        self.header: dict = {}
        self.gens: list[GenerationRecord] = []
        if self.path.exists():
            d = json.loads(self.path.read_text(encoding="utf-8"))
            self.header = d.get("header", {})
            self.gens = [GenerationRecord(**g) for g in d.get("generations", [])]

    def save(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"header": self.header,
                                   "generations": [asdict(g) for g in self.gens]}, indent=1) + "\n",
                       encoding="utf-8")
        tmp.replace(self.path)
        return self.path

    # ------------------------------------------------------------------ queries
    @property
    def promoted(self) -> list[GenerationRecord]:
        return [g for g in self.gens if g.status == "promoted"]

    def best(self) -> GenerationRecord | None:
        """The incumbent: the most recent generation that actually passed its gate."""
        p = self.promoted
        return p[-1] if p else None

    def unfinished(self) -> GenerationRecord | None:
        """A generation that was interrupted, so a resume knows where to pick up."""
        for g in self.gens:
            if g.status in ("generating", "fitting", "gating"):
                return g
        return None

    def next_n(self) -> int:
        return (max((g.n for g in self.gens), default=-1)) + 1

    def add(self, g: GenerationRecord) -> GenerationRecord:
        self.gens.append(g)
        self.save()
        return g


# ---------------------------------------------------------------- the opponent pool
def opponent_schedule(games: int, past: int, *, schedule=SCHEDULE) -> dict[str, int]:
    """How many of this generation's ``games`` go to each opponent role.

    ``past`` is how many earlier generations exist to draw from; with none, the "past" share falls
    back to self-play rather than silently shrinking the generation. Counts are whole games and
    sum to exactly ``games``, with the remainder going to self-play — the largest share, so the
    rounding never distorts the small ones.
    """
    if games <= 0:
        return {}
    out: dict[str, int] = {}
    for role, share in schedule:
        if role == "past" and past <= 0:
            continue
        out[role] = int(games * share)
    spent = sum(out.values())
    out["self"] = out.get("self", 0) + (games - spent)
    return {k: v for k, v in out.items() if v > 0}


def pick_past(gens: list[GenerationRecord], seed: int, i: int) -> GenerationRecord | None:
    """A uniformly sampled earlier generation, as a pure function of ``(seed, i)``.

    Indexed rather than drawn from a running stream for the same reason the harvest is: game *i*
    has to be reachable without playing the *i-1* before it, or sharding and resume both break.
    """
    if not gens:
        return None
    r = Pcg32((seed ^ (i * 0x9E3779B1)) & 0xFFFFFFFFFFFFFFFF, seq=811)
    return gens[r.next_u32() % len(gens)]


# ------------------------------------------------------------------- promotion
@dataclass(frozen=True)
class GateResult:
    """What the three gate runs said about one candidate."""

    sprt: str                       # "high" (candidate stronger) | "low" | "continue"
    win_rate: float                 # candidate's win rate against the incumbent, 0..100
    pairing_lo: float               # low end of the between-pairing band, the honest error bar
    panel: float                    # candidate's frozen-panel score, 0..100
    panel_incumbent: float          # the incumbent's score on the same frozen panel
    delayed: int                    # delayed-reward positions solved
    delayed_incumbent: int


def decide(g: GateResult, *, tolerance: float = PANEL_REGRESSION_TOLERANCE) -> tuple[bool, str]:
    """Promote or reject, and say why in one sentence.

    The order of the checks is the order of their authority. Beating the incumbent is the claim
    being made, so it is tested first and a failure there ends it. The other two are the checks
    that the claim was not bought by drifting: the frozen panel cannot move, so losing ground
    against it while winning the mirror means the pair of them moved together and away, and the
    delayed suite holds positions with *verified* winning lines, so solving fewer of them is a
    loss of ability rather than a change of taste.
    """
    if g.sprt != "high":
        return False, (f"did not beat the incumbent: sequential test says {g.sprt!r} "
                       f"at {g.win_rate:.1f}%")
    if g.pairing_lo <= 50.0:
        return False, (f"beat the incumbent {g.win_rate:.1f}% but the between-pairing band reaches "
                       f"{g.pairing_lo:.1f}%, which does not clear even money on the deck population")
    drop = g.panel_incumbent - g.panel
    if drop > tolerance:
        return False, (f"beat the incumbent {g.win_rate:.1f}% but went backwards on the frozen "
                       f"panel, {g.panel_incumbent:.1f}% to {g.panel:.1f}% — winning the mirror "
                       f"while losing to something that cannot move is what drift looks like")
    if g.delayed < g.delayed_incumbent:
        return False, (f"beat the incumbent {g.win_rate:.1f}% but solves {g.delayed} of the "
                       f"delayed-reward positions against the incumbent's {g.delayed_incumbent}; "
                       f"those lines are verified, so this is ability lost, not taste changed")
    return True, (f"beat the incumbent {g.win_rate:.1f}% [band from {g.pairing_lo:.1f}%], "
                  f"panel {g.panel:.1f}% against {g.panel_incumbent:.1f}%, "
                  f"delayed {g.delayed} against {g.delayed_incumbent}")


# --------------------------------------------------------------------- drift
def drift_report(rates: dict[int, float]) -> tuple[bool, list[str]]:
    """Given the newest generation's win rate against each earlier one, is the ladder a circle?

    A healthy ladder is monotone-ish: the newest player should beat an ancient generation by more
    than it beats the one just before it, because the ancient one is further back. Two patterns
    say otherwise and both are reported:

    * **losing to an ancestor** — below even money against any earlier generation at all;
    * **an inversion** — beating an older generation by *less* than a newer one, which means the
      three of them form a rock-paper-scissors and "stronger" has stopped being a straight line.

    This cannot prove the loop is healthy. It can only catch the specific way it is known to go
    wrong, which is worth more than an assumption.
    """
    bad: list[str] = []
    order = sorted(rates)
    for n in order:
        if rates[n] < 50.0:
            bad.append(f"loses to generation {n} ({rates[n]:.1f}%) — an ancestor it should dominate")
    for a, b in zip(order, order[1:]):
        if rates[a] < rates[b] - 1e-9:
            bad.append(f"beats the older generation {a} ({rates[a]:.1f}%) by less than the newer "
                       f"generation {b} ({rates[b]:.1f}%) — the ladder is not a straight line here")
    return (not bad), bad
