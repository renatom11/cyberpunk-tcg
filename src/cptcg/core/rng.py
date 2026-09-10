"""Deterministic RNG.

The engine stores its RNG *inside* the game state, because a search agent clones the state
thousands of times per decision. ``random.Random`` carries a 625-word Mersenne Twister buffer,
which is far too much to copy that often, and its cross-version output stability is documented
as "not guaranteed". PCG32 is two integers, is trivially fast to copy, and produces identical
streams on every platform and Python version.
"""

from __future__ import annotations

_MASK64 = 0xFFFFFFFFFFFFFFFF
_MASK32 = 0xFFFFFFFF
_MULT = 6364136223846793005


def _splitmix64(x: int) -> int:
    x = (x + 0x9E3779B97F4A7C15) & _MASK64
    z = x
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
    return z ^ (z >> 31)


class Pcg32:
    """A PCG32 generator. Two ints of state; ``copy()`` is the hot-path operation."""

    __slots__ = ("state", "inc")

    def __init__(self, seed: int = 0, seq: int = 54) -> None:
        inc = self.inc = ((seq << 1) | 1) & _MASK64
        # Closed form of the reference construction (state = 0; next_u32(); state += splitmix64(seed);
        # next_u32()): the first step from state 0 leaves state == inc, the second only advances the
        # state; both outputs were discarded. Search agents build one of these per preview.
        self.state = (((inc + _splitmix64(seed)) & _MASK64) * _MULT + inc) & _MASK64

    def copy(self) -> "Pcg32":
        r = Pcg32.__new__(Pcg32)
        r.state = self.state
        r.inc = self.inc
        return r

    def next_u32(self) -> int:
        old = self.state
        self.state = (old * _MULT + self.inc) & _MASK64
        xorshifted = (((old >> 18) ^ old) >> 27) & _MASK32
        rot = old >> 59
        return ((xorshifted >> rot) | (xorshifted << ((-rot) & 31))) & _MASK32

    def below(self, n: int) -> int:
        """Uniform integer in ``[0, n)``, rejection-sampled so it carries no modulo bias."""
        if n <= 1:
            if n <= 0:
                raise ValueError(f"below() needs a positive bound, got {n}")
            return 0
        threshold = (-n) % n  # == 2**32 % n, without the big intermediate
        while True:
            r = self.next_u32()
            if r >= threshold:
                return r % n

    def die(self, sides: int) -> int:
        """Roll a die: uniform in ``[1, sides]``."""
        return self.below(sides) + 1

    def choice(self, seq):
        return seq[self.below(len(seq))]

    def shuffle(self, lst: list) -> None:
        """In-place Fisher-Yates."""
        for i in range(len(lst) - 1, 0, -1):
            j = self.below(i + 1)
            lst[i], lst[j] = lst[j], lst[i]

    def split(self, label: int) -> "Pcg32":
        """Derive an independent generator.

        Used to seed simulation workers: game *i* draws from ``master.split(i)``, so its outcome
        is identical no matter how many worker processes run or in what order they are scheduled.
        """
        return Pcg32(_splitmix64(self.state ^ (label * 0x9E3779B97F4A7C15)), seq=label * 2 + 1)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Pcg32(state=0x{self.state:016x}, inc=0x{self.inc:016x})"
