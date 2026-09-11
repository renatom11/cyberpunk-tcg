"""The value model: a position in, a win probability out.

This is the half of the learning loop that replaces ``agents/heuristic.py``'s dict of seventeen
hand-written constants with numbers fitted to what actually happened. Given the features of a
position it returns the probability that the player to move eventually wins.

**Why it is this small.** One hidden layer. The shipped weights are sixteen units, 1,857
parameters; ``tools/fit_eval.py bench`` measures the forward pass against hidden width on whatever
machine you are on. The search agent calls this at every leaf, inside a move budget of about 1.5 s,
in pure Python, under Pyodide on a phone, so the width is a measured decision and not a taste.

Measured here (CPython 3.11, medians over 400 calls on a real-shaped 114-vector)::

    width 16   1,857 params    46 us        width 32   3,713 params    93 us
    features(), on real decision states:    49 us median (45 to 102)

So at the shipped width the model costs about as much as extracting its own input, and doubling it
would make the model cost twice its input for capacity a 114-dimensional hand-designed vector
probably cannot use.

**Why tanh — and not for the reason you might expect.** An earlier version of this file claimed
tanh was *faster* than ReLU here, on the reasoning that ``math.tanh`` is one C call where ``x >
0.0`` is an interpreted branch. That is measurably wrong: ReLU is not slower, and at width 32 it is
about 5% quicker (88 us against 93), because the branch skips an accumulate. The real reason to
prefer tanh is modelling — a bounded output, a clean gradient for the squared-error Brier fit this
is trained under, and no dead units on an input that is already scaled. The activation is nearly
free either way: the dot product alone is 44 us of the 46, about 96% of the cost.

That 96% is why the forward pass below is one row-major ``sumprod`` per hidden unit rather than
nested loops. At the shipped width that shape measures 38.5 us against 74.0 us, 1.9x.

**Inference is stdlib only.** Training lives in ``tools/fit_eval.py`` and may use numpy; nothing in
``src/cptcg`` may, because this package is shipped into the browser. ``tools/build_site.py`` already
packs every non-pyc file under ``src/cptcg`` into ``cptcg.zip``, so ``agents/weights.json`` reaches
Pyodide with no build change.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from operator import mul
from pathlib import Path
from typing import Sequence

from cptcg.core.config import DEFAULT_CONFIG
from cptcg.core.state import GameState
from cptcg.learn.features import FEATURE_NAMES, NFEAT, features

# Bump when the on-disk shape changes in a way older readers cannot handle.
FORMAT = 1

# The ruleset these weights are only meaningful under. Passing ``rules=None`` deliberately reads a
# file fitted under another one, which is what a refit needs; the default never silently does that.
# Same convention as ``learn.experience.read_games``.
_RULES = DEFAULT_CONFIG.digest()

# Weights ride inside the package so the site build ships them automatically.
WEIGHTS_PATH = Path(__file__).resolve().parents[1] / "agents" / "weights.json"

# math.sumprod is a single C call over two sequences (3.12+). On 3.11 the map/mul form is the
# fastest pure-Python equivalent measured. One indirection so tests can exercise both.
_SUMPROD = getattr(math, "sumprod", None) or (lambda a, b: sum(map(mul, a, b)))
_TANH = math.tanh


def _logistic(x: float) -> float:
    """Overflow-safe sigmoid: exp(1000) raises, and a saturated unit is not an error."""
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def feature_digest(names: Sequence[str] = FEATURE_NAMES) -> str:
    """Short fingerprint of the feature list, stored beside the weights.

    Weights are only meaningful for the exact feature vector they were fitted to. Storing the whole
    list lets a mismatch name the offending index; the digest makes the common check cheap.
    """
    import hashlib

    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class ValueModel:
    """A fitted value head. ``forward`` is the hot path; ``value`` is the convenience wrapper."""

    hidden: int
    w1: tuple[tuple[float, ...], ...]        # `hidden` rows, each NFEAT long
    b1: tuple[float, ...]
    w2: tuple[float, ...]
    b2: float
    header: dict = field(default_factory=dict)
    _rows: tuple = field(default=(), init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Pre-zip the three per-unit values so the hot loop does no indexing at all.
        rows = tuple(zip(self.w1, self.b1, self.w2))
        object.__setattr__(self, "_rows", rows)

    # ---------------------------------------------------------------- inference
    def raw(self, x: Sequence[float]) -> float:
        """The pre-logistic score: an unbounded log-odds, and the number an agent should rank on.

        ``forward`` is the calibrated answer and the one a human reads, but a greedy agent only
        ever compares two previews, and near a decided game every probability is 0.999-something:
        the differences that decide the move fall off the end of a float's useful precision once
        they have been squashed. The logistic is monotone, so ranking on this loses nothing and
        keeps the resolution. It is also where the tie-break noise has a sane scale.
        """
        out = self.b2
        sumprod = _SUMPROD
        tanh = _TANH
        for w, b, v in self._rows:
            out += v * tanh(sumprod(w, x) + b)
        return out

    def forward(self, x: Sequence[float]) -> float:
        """Win probability for the player the features were extracted for."""
        return _logistic(self.raw(x))

    def value(self, s: GameState, me: int) -> float:
        return _logistic(self.raw(features(s, me)))

    def score(self, s: GameState, me: int) -> float:
        """``raw`` straight from a position: what ``agents/neural.py`` argmaxes over."""
        return self.raw(features(s, me))

    # ------------------------------------------------------------------- disk
    def to_json(self) -> dict:
        d = dict(self.header)
        d.update(format=FORMAT, kind="value", hidden=self.hidden, activation="tanh",
                 features=list(FEATURE_NAMES), feature_digest=feature_digest(),
                 rules=DEFAULT_CONFIG.digest(),
                 w1=[list(r) for r in self.w1], b1=list(self.b1),
                 w2=list(self.w2), b2=self.b2)
        return d

    @classmethod
    def from_json(cls, d: dict, *, rules: str | None = _RULES, where: str = "weights") -> "ValueModel":
        """Rebuild a model, refusing anything that would silently score garbage.

        Every check here exists because its absence would produce plausible numbers from a model
        that is not the one that was measured: a stale feature list, a different activation, a
        ruleset whose rulings changed what a position means.
        """
        def bad(msg: str):
            return ValueError(f"{where}: {msg}")

        if d.get("format") != FORMAT:
            raise bad(f"format {d.get('format')!r}, this build reads {FORMAT}")
        if d.get("activation") != "tanh":
            raise bad(f"activation {d.get('activation')!r}, this build implements 'tanh'")

        names = list(d.get("features") or ())
        if names != list(FEATURE_NAMES):
            if len(names) != NFEAT:
                raise bad(f"{len(names)} features, this build extracts {NFEAT}")
            i = next(i for i, (a, b) in enumerate(zip(names, FEATURE_NAMES)) if a != b)
            raise bad(f"feature {i} is {names[i]!r} in the weights but {FEATURE_NAMES[i]!r} here; "
                      "the weights were fitted to a different feature vector")

        if rules is not None and d.get("rules") != rules:
            raise bad(f"fitted under ruleset {d.get('rules')}, this build is {rules}. A changed "
                      "ruling changes what a position is worth; refit rather than reuse.")

        hidden = int(d["hidden"])
        w1 = tuple(tuple(float(v) for v in row) for row in d["w1"])
        b1 = tuple(float(v) for v in d["b1"])
        w2 = tuple(float(v) for v in d["w2"])
        if len(w1) != hidden or len(b1) != hidden or len(w2) != hidden:
            raise bad(f"hidden={hidden} but shapes are w1={len(w1)} b1={len(b1)} w2={len(w2)}")
        for i, row in enumerate(w1):
            if len(row) != NFEAT:
                raise bad(f"w1 row {i} has {len(row)} weights, expected {NFEAT}")

        header = {k: v for k, v in d.items()
                  if k not in ("w1", "b1", "w2", "b2", "format", "kind", "hidden",
                               "activation", "features", "feature_digest", "rules")}
        header["rules"] = d.get("rules")
        return cls(hidden=hidden, w1=w1, b1=b1, w2=w2, b2=float(d["b2"]), header=header)

    @classmethod
    def load(cls, path: str | Path = WEIGHTS_PATH, *, rules: str | None = _RULES) -> "ValueModel":
        p = Path(path)
        return cls.from_json(json.loads(p.read_text(encoding="utf-8")), rules=rules, where=str(p))

    def save(self, path: str | Path = WEIGHTS_PATH) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Full repr precision, not rounded: the numpy-agreement test asserts a tight tolerance, and
        # rounding here would make that test apologise for a difference we introduced ourselves.
        p.write_text(json.dumps(self.to_json()) + "\n", encoding="utf-8")
        return p


_CACHE: dict[str, ValueModel] = {}


def load_weights(path: str | Path = WEIGHTS_PATH, *, rules: str | None = _RULES) -> ValueModel:
    """Load once per process. Agents are rebuilt per game, so the cache has to outlive them."""
    key = str(path)
    m = _CACHE.get(key)
    if m is None:
        m = _CACHE[key] = ValueModel.load(path, rules=rules)
    return m


def available(path: str | Path = WEIGHTS_PATH) -> bool:
    return Path(path).exists()


def zeros(hidden: int = 32) -> ValueModel:
    """An untrained model that returns 0.5 everywhere. Useful as a test fixture and as the honest
    fallback when no weights have been fitted yet."""
    return ValueModel(hidden=hidden,
                      w1=tuple(tuple(0.0 for _ in range(NFEAT)) for _ in range(hidden)),
                      b1=tuple(0.0 for _ in range(hidden)),
                      w2=tuple(0.0 for _ in range(hidden)), b2=0.0,
                      header={"run": {"name": "zeros"}})
