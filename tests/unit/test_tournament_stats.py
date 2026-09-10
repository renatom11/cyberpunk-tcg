from cptcg.core.rng import Pcg32
from cptcg.sim.stats import (SPRT, bh_fdr, binomial_p_two_sided, bradley_terry, bt_predicted,
                             nash_fictitious_play)


def _simulate(p, seed, cap=2000):
    t = SPRT(delta=0.05)
    r = Pcg32(seed)
    k = 0
    for n in range(1, cap + 1):
        k += r.below(1000) < p * 1000
        verdict = t.test(k, n)
        if verdict != "continue":
            return verdict, n
    return "cap", cap


def test_sprt_resolves_lopsided_quickly_and_rarely_errs():
    highs = [_simulate(0.8, s) for s in range(50)]
    assert all(v == "high" for v, _ in highs) and max(n for _, n in highs) < 200
    lows = [_simulate(0.2, s) for s in range(50)]
    assert all(v == "low" for v, _ in lows)
    even = [_simulate(0.5, s) for s in range(100)]
    wrong = sum(1 for v, _ in even if v in ("high", "low"))
    assert wrong <= 12                                     # alpha 0.05 two-sided, some slack


def test_binomial_p_and_bh():
    assert abs(binomial_p_two_sided(5, 10) - 1.0) < 1e-9
    assert binomial_p_two_sided(60, 100) < 0.06 and binomial_p_two_sided(60, 100) > 0.04
    assert binomial_p_two_sided(100, 100) < 1e-20
    q = bh_fdr([0.01, 0.04, 0.03, 0.5])
    assert [round(x, 4) for x in q] == [0.04, 0.0533, 0.0533, 0.5]


def test_bradley_terry_recovers_ordering():
    # deck 0 beats everyone, deck 2 loses to everyone
    wins = [[0, 70, 90], [30, 0, 65], [10, 35, 0]]
    pi = bradley_terry(wins)
    assert pi[0] > pi[1] > pi[2]
    pred = bt_predicted(pi)
    assert abs(pred[0][2] - 0.9) < 0.05 and abs(pred[1][2] - 0.65) < 0.05


def test_nash_on_rock_paper_scissors_is_uniform():
    pay = [[0, 0.3, -0.3], [-0.3, 0, 0.3], [0.3, -0.3, 0]]
    mix = nash_fictitious_play(pay, iters=30000)
    assert all(abs(m - 1 / 3) < 0.02 for m in mix)


def test_nash_dominant_strategy():
    pay = [[0, 0.2, 0.2], [-0.2, 0, 0.0], [-0.2, 0.0, 0]]
    mix = nash_fictitious_play(pay, iters=5000)
    assert mix[0] > 0.95
