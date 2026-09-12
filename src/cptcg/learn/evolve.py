"""An evolution strategy over the value head's weights, optimising wins rather than Brier.

Why this exists
---------------
``fit_eval`` minimises Brier score by gradient descent. That is a *proxy*, and this project has a
measurement showing the proxy and the goal come apart: a 125-feature model scored better on Brier,
accuracy and calibration, and played 4.4 points worse against the frozen panel. An ES optimises the
objective we actually have — games won — at the cost of needing games to evaluate it.

Why not survival of the fittest
-------------------------------
The obvious design is a population, cull the worst, breed the best. A probe measured why that
cannot work here: 24 mutants of gen-1 scored mean 49.1% over 48 games each, and 48 games carry a
+/-14 point band. Plausible mutation effects are one or two points, so truncation selection would
rank noise. The best mutant's +4.2 was not evidence of anything.

So this estimates a *direction* instead of ranking individuals:

* **antithetic pairs** — every perturbation is used twice, as ``+e`` and ``-e``. The pair plays
  itself, so the comparison is paired on identical seeds and most of the game-level variance cancels
  before it ever reaches the estimator.
* **rank normalisation** — a pair's raw margin is replaced by its centred rank. One pair that
  happened to win big cannot dominate the step, which matters when the signal is this close to the
  noise.
* **every sample contributes** — the step is a weighted sum over all pairs, not a selection of the
  top few. That is the part that turns noisy individual measurements into a usable direction.

Nothing here plays a game or imports numpy: the module takes fitness as *numbers* and returns the
next weights. That is deliberate, so the optimiser can be proven on a synthetic hill with the real
noise level injected, in seconds, before any compute is spent on it.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cptcg.core.rng import Pcg32

#: Perturbation scale, in absolute weight units. gen-1's mean |w1| is 0.092, so the default is about
#: a fifth of a typical weight — small enough that a step is a nudge, large enough to be visible
#: over the noise. The probe used 0.03 and found mutants slightly *worse* than the parent on
#: average, which is what too large looks like near an optimum.
SIGMA = 0.02

#: Step size. **Measured, not chosen.** The first value here was 0.03 and it diverged — on a
#: synthetic hill with no noise at all the objective got twenty-five times *worse*, because the
#: update is divided by sigma and 0.03/(16*0.02) makes every rank worth a tenth of a weight unit,
#: so the random half of a 16-sample estimate swamps the signal. Sweeping it on that hill:
#:
#:     alpha    3e-2     3e-3    3e-4    3e-5
#:     gain   -2461%    +23%     +9%     +1%
#:
#: 3e-3 is the peak. Below it the search crawls; above it, it walks away from the optimum.
ALPHA = 3e-3

#: Anchor checks without improvement before sigma is halved. Three is enough to distinguish a
#: plateau from one unlucky check, and few enough to re-focus the search while there is still time.
PATIENCE = 3


def perturbations(n: int, dim: int, seed: int) -> list[list[float]]:
    """``n`` unit-ish Gaussian vectors, reproducible from ``seed``.

    Generated rather than stored: a run's whole search path has to be reconstructible from the
    ledger, and the ledger holds seeds, not megabytes of vectors.
    """
    out = []
    for i in range(n):
        rng = Pcg32(seed ^ (0x9E3779B9 * (i + 1)) & 0xFFFFFFFF, seq=17)
        out.append([_gauss(rng) for _ in range(dim)])
    return out


def _gauss(rng: Pcg32) -> float:
    """Box-Muller off the project's PCG32, so a run reproduces on any machine."""
    u1 = (rng.next_u32() + 1) / 4294967297.0
    u2 = rng.next_u32() / 4294967296.0
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def centred_ranks(scores: list[float]) -> list[float]:
    """Map scores to ranks in [-0.5, +0.5], mean zero. Ties share the average rank.

    Rank rather than raw margin because the raw margins here are mostly noise: a pair that won 70%
    of twenty-four games has not necessarily found a better direction than one that won 60%, and
    weighting by the difference would let a coin flip steer the step.
    """
    n = len(scores)
    if n == 0:
        return []
    if n == 1:
        return [0.0]
    order = sorted(range(n), key=lambda i: scores[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return [r / (n - 1) - 0.5 for r in ranks]


def step(theta: list[float], eps: list[list[float]], scores: list[float],
         *, sigma: float = SIGMA, alpha: float = ALPHA) -> list[float]:
    """One antithetic ES update.

    ``scores[i]`` is how well ``theta + sigma*eps[i]`` did **against its own mirror**
    ``theta - sigma*eps[i]`` — a win rate in 0..1, where 0.5 means the pair could not be separated.
    Above 0.5 says the ``+e`` direction is better, so the step moves that way; below 0.5 says the
    mirror was better, and the centred rank carries the sign automatically.
    """
    n = len(eps)
    if n == 0 or not theta:
        return list(theta)
    w = centred_ranks(scores)
    scale = alpha / (n * sigma)
    out = list(theta)
    for i in range(n):
        wi = w[i]
        if wi == 0.0:
            continue
        e = eps[i]
        for d in range(len(out)):
            out[d] += scale * wi * e[d]
    return out


# ---------------------------------------------------------------- flattening a model
def flatten(w: dict) -> tuple[list[float], tuple]:
    """A model's trainable numbers as one vector, plus the shape needed to put them back."""
    w1, b1, w2 = w["w1"], w["b1"], w["w2"]
    vec = [v for row in w1 for v in row] + list(b1) + list(w2) + [w["b2"]]
    return vec, (len(w1), len(w1[0]))


def unflatten(vec: list[float], shape: tuple, template: dict) -> dict:
    """The inverse of :func:`flatten`, as a copy of ``template`` with new numbers."""
    hidden, nfeat = shape
    out = dict(template)
    k = hidden * nfeat
    out["w1"] = [list(vec[i * nfeat:(i + 1) * nfeat]) for i in range(hidden)]
    out["b1"] = list(vec[k:k + hidden])
    out["w2"] = list(vec[k + hidden:k + 2 * hidden])
    out["b2"] = vec[k + 2 * hidden]
    return out


# ---------------------------------------------------------------- the run's record
@dataclass
class Iteration:
    """One ES step, written down whether it helped or not."""

    n: int
    seed: int
    sigma: float
    alpha: float
    pair_scores: list[float] = field(default_factory=list)
    anchor: float | None = None          # win rate vs the frozen anchor, when checked
    anchor_games: int = 0
    note: str = ""


@dataclass
class Run:
    """The whole search, enough to resume it and enough to plot it."""

    sigma: float = SIGMA
    alpha: float = ALPHA
    best_anchor: float = 0.0
    best_iter: int = -1
    stale: int = 0
    iterations: list[Iteration] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Run":
        if not path.exists():
            return cls()
        d = json.loads(path.read_text(encoding="utf-8"))
        r = cls(**{k: v for k, v in d.items() if k != "iterations"})
        r.iterations = [Iteration(**x) for x in d.get("iterations", ())]
        return r

    def record_anchor(self, rate: float, *, patience: int = PATIENCE) -> str:
        """Fold an anchor check into the schedule, and say what it changed.

        Improvement keeps the champion and resets patience. No improvement eventually halves sigma
        — the search is looking too far out to see a small gain, which is the failure mode the probe
        measured directly.
        """
        if rate > self.best_anchor:
            self.best_anchor, self.best_iter, self.stale = rate, len(self.iterations) - 1, 0
            return f"new best {rate:.1%}"
        self.stale += 1
        if self.stale >= patience:
            self.sigma /= 2.0
            self.stale = 0
            return f"no gain on {patience} checks; sigma -> {self.sigma:.4f}"
        return f"no gain ({self.stale}/{patience})"
