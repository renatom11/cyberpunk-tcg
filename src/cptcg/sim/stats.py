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


# ------------------------------------------------------------------ SPRT
class SPRT:
    """Two-sided sequential probability ratio test on a win proportion.

    H0: p = p0 (usually 0.5). H1: p = p0 ± delta. Call ``test(k, n)`` as games accumulate; it
    returns "continue", "high" (p > p0 established), "low" (p < p0), or "h0" (no difference
    established at this delta). A lopsided matchup resolves in a few dozen games; a close one
    runs until the game cap the caller applies.
    """

    def __init__(self, delta: float = 0.05, alpha: float = 0.05, beta: float = 0.05, p0: float = 0.5) -> None:
        self.p0, self.delta = p0, delta
        self.alpha, self.beta = alpha, beta
        self.upper = math.log((1 - beta) / alpha)
        self.lower = math.log(beta / (1 - alpha))

    def llr(self, k: int, n: int, p1: float) -> float:
        p0 = self.p0
        return k * math.log(p1 / p0) + (n - k) * math.log((1 - p1) / (1 - p0))

    def test(self, k: int, n: int) -> str:
        if n == 0:
            return "continue"
        hi = self.llr(k, n, self.p0 + self.delta)
        lo = self.llr(k, n, self.p0 - self.delta)
        if hi >= self.upper:
            return "high"
        if lo >= self.upper:
            return "low"
        if hi <= self.lower and lo <= self.lower:
            return "h0"
        return "continue"


# ------------------------------------------------------- exact binomial test
def _log_pmf(k: int, n: int, p: float) -> float:
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log(1 - p))


def binomial_p_two_sided(k: int, n: int, p: float = 0.5) -> float:
    """Exact two-sided p-value for k successes in n trials under P(success) = p."""
    if n == 0:
        return 1.0
    lower = sum(math.exp(_log_pmf(x, n, p)) for x in range(0, k + 1))
    upper = sum(math.exp(_log_pmf(x, n, p)) for x in range(k, n + 1))
    return min(1.0, 2 * min(lower, upper))


def bh_fdr(pvalues: list[float]) -> list[float]:
    """Benjamini–Hochberg q-values (adjusted p-values) in the input order."""
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        q[i] = min(1.0, running)
    return q


# ------------------------------------------------------------ Bradley–Terry
def bradley_terry(wins: list[list[int]], iters: int = 500, prior: float = 0.5) -> list[float]:
    """Bradley–Terry strengths from a wins matrix (wins[i][j] = games i beat j), by the MM
    algorithm (Hunter 2004). ``prior`` adds a fractional win each way per pair so an unbeaten
    or winless deck gets a finite rating. Returned strengths are normalised to mean 1."""
    n = len(wins)
    if n == 0:
        return []
    w = [[wins[i][j] + (prior if i != j else 0) for j in range(n)] for i in range(n)]
    total = [sum(w[i]) for i in range(n)]
    games = [[w[i][j] + w[j][i] for j in range(n)] for i in range(n)]
    pi = [1.0] * n
    for _ in range(iters):
        new = []
        for i in range(n):
            denom = sum(games[i][j] / (pi[i] + pi[j]) for j in range(n) if j != i and games[i][j])
            new.append(total[i] / denom if denom else pi[i])
        mean = sum(new) / n
        pi = [x / mean for x in new]
    return pi


def bt_predicted(pi: list[float]) -> list[list[float]]:
    n = len(pi)
    return [[pi[i] / (pi[i] + pi[j]) if i != j else 0.5 for j in range(n)] for i in range(n)]


# ------------------------------------------------------------- Nash (symmetric)
def nash_fictitious_play(payoff: list[list[float]], iters: int = 20000) -> list[float]:
    """Mixed strategy of the symmetric zero-sum game with payoff[i][j] = (win rate of i vs j) - 0.5,
    by fictitious play. Converges slowly but reliably; fine for a few dozen decks."""
    n = len(payoff)
    if n == 0:
        return []
    counts = [1.0] * n
    for _ in range(iters):
        best, best_v = 0, -1e18
        for i in range(n):
            v = sum(payoff[i][j] * counts[j] for j in range(n))
            if v > best_v:
                best, best_v = i, v
        counts[best] += 1
    tot = sum(counts)
    return [c / tot for c in counts]
