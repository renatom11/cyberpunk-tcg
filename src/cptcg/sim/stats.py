"""Pure-Python statistics for win rates."""

from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for a proportion. Correct near 0 and 1, unlike the Wald interval."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def games_for_half_width(half: float, p: float = 0.5, z: float = 1.959964) -> int:
    """Games needed for a 95% interval of ±half at proportion p (worst case p=0.5)."""
    return math.ceil(z * z * p * (1 - p) / (half * half))


def two_proportion_z(k1: int, n1: int, k2: int, n2: int) -> float:
    """z statistic for H0: p1 == p2."""
    if n1 == 0 or n2 == 0:
        return 0.0
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return 0.0 if se == 0 else ((k1 / n1) - (k2 / n2)) / se


def fmt_rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{100 * k / n:5.1f}%  [{100 * lo:4.1f}–{100 * hi:4.1f}]" if n else "   n/a"
