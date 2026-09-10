"""Game budgets and structural progress for lab jobs.

Every comparison the lab runs may stop early: a tournament cell stops as soon as the sequential
test is sure, a hill-climb step as soon as the paired test is sure. So a job's size is not one
number but a range — the games it plays if every comparison settles at its first batch, and the
games it plays if none does. ``tourney_budget``, ``climb_step_budget``, ``league_budget`` and
``generate_budget`` give that ``(min_games, max_games)`` pair before a job starts, and a
``Tracker`` keeps it current while the job runs: every comparison that settles moves its games
from "remaining" to "done" and takes its unplayed games out of the maximum. Progress is
structural — comparisons done out of comparisons planned — never games out of a guess.

Pure Python, no engine imports: the same numbers serve the HTTP server, the browser build and
the tests.
"""

from __future__ import annotations

DEFAULT_BATCH = 40           # tournament games per cell between test checks (tournament.run_tournament)
DEFAULT_SEEDS = 20           # hill-climb seeds per batch (builder.hill_climb)
DEFAULT_MAX_BATCHES = 3      # hill-climb batches per step before giving up on a decision


# ------------------------------------------------------------------ budgets
def pairs(n_decks: int) -> int:
    """Unordered pairs in a round robin of ``n_decks``."""
    n = max(0, int(n_decks))
    return n * (n - 1) // 2


def cell_budget(cap: int, batch: int = DEFAULT_BATCH, sprt: bool = True) -> tuple[int, int]:
    """Games one tournament cell plays: at least one batch (or the cap when it is smaller),
    at most the cap. Without the sequential test every cell plays the cap."""
    cap = max(0, int(cap))
    return (min(int(batch), cap) if sprt else cap), cap


def tourney_budget(n_decks: int, cap: int, batch: int = DEFAULT_BATCH, sprt: bool = True) -> tuple[int, int]:
    """(min, max) games of a round robin: every pair is one cell."""
    lo, hi = cell_budget(cap, batch, sprt)
    p = pairs(n_decks)
    return p * lo, p * hi


def climb_step_budget(field: int, seeds_per_batch: int = DEFAULT_SEEDS, max_batches: int = DEFAULT_MAX_BATCHES,
                      first: bool = False) -> tuple[int, int]:
    """(min, max) games of one hill-climb step. A batch plays every seed twice (both seats) against
    every deck in the field; the challenger plays one batch at least and ``max_batches`` at most.
    The champion's games are cached between steps: on the first step it plays every batch the
    challenger plays; afterwards its first batch is always on file and only batches the earlier
    steps never reached are new."""
    g = 2 * max(0, int(seeds_per_batch)) * max(0, int(field))
    m = max(1, int(max_batches))
    if first:
        return 2 * g, 2 * m * g
    return g, (2 * m - 1) * g


def climb_budget(field: int, steps: int, seeds_per_batch: int = DEFAULT_SEEDS,
                 max_batches: int = DEFAULT_MAX_BATCHES) -> tuple[int, int]:
    """(min, max) games of a whole hill climb of ``steps`` steps."""
    lo = hi = 0
    for k in range(1, max(0, int(steps)) + 1):
        a, b = climb_step_budget(field, seeds_per_batch, max_batches, first=k == 1)
        lo += a
        hi += b
    return lo, hi


def league_budget(builders: int, generations: int, steps: int, cap: int, field: int | None = None,
                  batch: int = DEFAULT_BATCH, seeds_per_batch: int = DEFAULT_SEEDS,
                  max_batches: int = DEFAULT_MAX_BATCHES, sprt: bool = True) -> tuple[int, int]:
    """(min, max) games of a league: every generation, each builder climbs against ``field``
    opponents (default: the other builders), then all builders play a round robin."""
    b = max(0, int(builders))
    field = b - 1 if field is None else int(field)
    c_lo, c_hi = climb_budget(field, steps, seeds_per_batch, max_batches)
    t_lo, t_hi = tourney_budget(b, cap, batch, sprt)
    g = max(0, int(generations))
    return g * (b * c_lo + t_lo), g * (b * c_hi + t_hi)


def generate_budget(count: int, screen: int, panel: int) -> tuple[int, int]:
    """(min, max) games of a generate job: building plays nothing, the screen plays every deck
    ``screen`` games against each panel deck and never stops early."""
    n = max(0, int(count)) * max(0, int(screen)) * max(0, int(panel))
    return n, n


# ------------------------------------------------------------------ tracker
class Tracker:
    """Structural progress of one job.

    The job is a set of *units* — tournament cells, hill-climb steps, decks to build or screen —
    each with a nominal ``(min, max)`` game budget that the constructor already summed into
    ``remaining_min``/``remaining_max``. Reporting a unit moves its games to ``done`` and replaces
    its nominal budget with what it can still play (nothing once it has settled), so the maximum
    only ever shrinks. ``step``/``steps`` count settled units out of planned units; ``phase`` is
    the sentence the job card shows. ``to_json()`` is the ``progress`` object of a job.

    Use ``for_tourney``, ``for_league`` or ``for_generate``: they remember the run's parameters
    so the event methods need only what the callbacks provide.
    """

    def __init__(self, remaining_min: int = 0, remaining_max: int = 0, steps: int = 0,
                 phase: str = "starting", unit: str = "steps") -> None:
        self.done = 0
        self.remaining_min = int(remaining_min)
        self.remaining_max = int(remaining_max)
        self.step = 0
        self.steps = int(steps)
        self.phase = phase
        self.unit = unit
        self._units: dict[tuple, list] = {}          # key -> [done, remaining_min, remaining_max, settled]
        # run parameters (set by the constructors below; harmless defaults otherwise)
        self.cap = 0
        self.batch = DEFAULT_BATCH
        self.sprt = True
        self.seeds_per_batch = DEFAULT_SEEDS
        self.max_batches = DEFAULT_MAX_BATCHES
        self.field = 0
        self.climb_steps = 0
        self.builders = 0
        self.generations = 0
        self._fields: dict[tuple, int] = {}          # (gen, builder) -> actual field size

    # ------------------------------------------------------------ constructors
    @classmethod
    def for_tourney(cls, n_decks: int, cap: int, batch: int = DEFAULT_BATCH, sprt: bool = True) -> "Tracker":
        lo, hi = tourney_budget(n_decks, cap, batch, sprt)
        t = cls(lo, hi, pairs(n_decks), unit="matchups")
        t.cap, t.batch, t.sprt = int(cap), int(batch), bool(sprt)
        return t

    @classmethod
    def for_league(cls, builders: int, generations: int, steps: int, cap: int, field: int | None = None,
                   batch: int = DEFAULT_BATCH, seeds_per_batch: int = DEFAULT_SEEDS,
                   max_batches: int = DEFAULT_MAX_BATCHES, sprt: bool = True) -> "Tracker":
        b = max(0, int(builders))
        field = b - 1 if field is None else int(field)
        lo, hi = league_budget(b, generations, steps, cap, field, batch, seeds_per_batch, max_batches, sprt)
        n_units = max(0, int(generations)) * (b * max(0, int(steps)) + pairs(b))
        t = cls(lo, hi, n_units, unit="steps")
        t.cap, t.batch, t.sprt = int(cap), int(batch), bool(sprt)
        t.seeds_per_batch, t.max_batches = int(seeds_per_batch), int(max_batches)
        t.field, t.climb_steps, t.builders, t.generations = field, max(0, int(steps)), b, max(0, int(generations))
        return t

    @classmethod
    def for_generate(cls, count: int, screen: int, panel: int) -> "Tracker":
        lo, hi = generate_budget(count, screen, panel)
        n = max(0, int(count))
        t = cls(lo, hi, n + (n if int(screen) > 0 and int(panel) > 0 else 0), unit="decks")
        t.cap = int(screen) * max(0, int(panel))          # games one screened deck plays
        return t

    # ------------------------------------------------------------ core
    def unit_state(self, key: tuple, done: int, rmin: int, rmax: int, nominal: tuple[int, int] = (0, 0),
                   settled: bool = False) -> None:
        """Report a unit: ``done`` games so far and ``(rmin, rmax)`` it can still play. A unit
        seen for the first time replaces the ``nominal`` budget the constructor counted for it."""
        prev = self._units.get(key) or [0, int(nominal[0]), int(nominal[1]), False]
        self.done += int(done) - prev[0]
        self.remaining_min += int(rmin) - prev[1]
        self.remaining_max += int(rmax) - prev[2]
        if settled and not prev[3]:
            self.step += 1
        self._units[key] = [int(done), int(rmin), int(rmax), settled or prev[3]]

    def seen(self, key: tuple) -> bool:
        return key in self._units

    # ------------------------------------------------------------ tournament cells
    def cell(self, a, b, n: int, verdict: str, cap: int | None = None, gen: int = 0) -> bool:
        """A tournament cell after a batch: ``n`` games played, ``verdict`` from the sequential
        test (``continue`` = not settled). Returns whether the cell is now settled."""
        cap = self.cap if cap is None else int(cap)
        nominal = cell_budget(cap, self.batch, self.sprt)
        settled = verdict != "continue" or n >= cap
        left = max(0, cap - int(n))
        rmin, rmax = (0, 0) if settled else ((min(self.batch, left) if self.sprt else left), left)
        self.unit_state(("cell", gen, a, b), n, rmin, rmax, nominal, settled)
        return settled

    def cells_seen(self, gen: int = 0) -> int:
        return sum(1 for k in self._units if k[0] == "cell" and k[1] == gen)

    # ------------------------------------------------------------ hill climbs
    def _step_nominal(self, gen: int, builder, step: int) -> tuple[int, int]:
        field = self._fields.get((gen, builder), self.field)
        return climb_step_budget(field, self.seeds_per_batch, self.max_batches, first=step == 1)

    def climb_start(self, builder, field: int, steps: int | None = None, gen: int = 0) -> None:
        """A builder starts improving against ``field`` opponents. When the field differs from the
        one the budget assumed (the hall of fame lends fewer champions than hoped), this builder's
        unplayed steps are re-budgeted."""
        steps = self.climb_steps if steps is None else int(steps)
        field = int(field)
        if field != self._fields.get((gen, builder), self.field):
            for k in range(1, steps + 1):
                key = ("climb", gen, builder, k)
                if key in self._units:
                    continue
                old = self._step_nominal(gen, builder, k)
                new = climb_step_budget(field, self.seeds_per_batch, self.max_batches, first=k == 1)
                self.remaining_min += new[0] - old[0]
                self.remaining_max += new[1] - old[1]
        self._fields[(gen, builder)] = field

    def climb_step(self, builder, step: int, games: int, gen: int = 0) -> None:
        """One hill-climb step finished with ``games`` challenger games."""
        self.unit_state(("climb", gen, builder, int(step)), games, 0, 0, self._step_nominal(gen, builder, int(step)), True)

    def climb_done(self, builder, gen: int = 0, steps: int | None = None) -> None:
        """A builder's climb is over: steps it skipped (no legal swap) cost nothing."""
        steps = self.climb_steps if steps is None else int(steps)
        for k in range(1, steps + 1):
            key = ("climb", gen, builder, k)
            if key not in self._units:
                self.unit_state(key, 0, 0, 0, self._step_nominal(gen, builder, k), True)

    def gen_done(self, gen: int) -> None:
        """A league generation is over: cells never reported (there are none in practice) are
        settled at zero so the remaining budget stays honest."""
        missing = pairs(self.builders) - self.cells_seen(gen)
        nominal = cell_budget(self.cap, self.batch, self.sprt)
        for k in range(missing):
            self.unit_state(("cell", gen, "?", k), 0, 0, 0, nominal, True)

    # ------------------------------------------------------------ generate
    def built(self, index: int) -> None:
        """Deck number ``index`` (1-based) of a batch was built (no games)."""
        self.unit_state(("build", int(index)), 0, 0, 0, (0, 0), True)

    def screened(self, index: int, games: int | None = None) -> None:
        """Deck number ``index`` finished its screen."""
        g = self.cap if games is None else int(games)
        self.unit_state(("screen", int(index)), g, 0, 0, (self.cap, self.cap), True)

    # ------------------------------------------------------------ end
    def finish(self, phase: str | None = None) -> None:
        """Nothing remains, whatever was or was not reported."""
        self.remaining_min = self.remaining_max = 0
        self.step = self.steps
        if phase is not None:
            self.phase = phase

    def to_json(self) -> dict:
        return {"phase": self.phase, "step": self.step, "steps": self.steps, "unit": self.unit,
                "done": self.done, "remaining_min": max(0, self.remaining_min), "remaining_max": max(0, self.remaining_max)}
