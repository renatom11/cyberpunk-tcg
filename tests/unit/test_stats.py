from cptcg.sim.stats import games_for_half_width, two_proportion_z, wilson


def test_wilson_matches_known_values():
    lo, hi = wilson(550, 1000)
    assert abs(lo - 0.5190) < 0.001 and abs(hi - 0.5806) < 0.001   # 550/1000
    assert wilson(0, 10)[0] < 1e-9 and wilson(10, 10)[1] > 1 - 1e-9
    assert wilson(0, 0) == (0.0, 1.0)


def test_sample_size_table():
    assert games_for_half_width(0.05) == 385
    assert games_for_half_width(0.03) == 1068
    assert games_for_half_width(0.01) == 9604


def test_two_proportion_z_sign():
    assert two_proportion_z(60, 100, 40, 100) > 2.5
    assert two_proportion_z(50, 100, 50, 100) == 0.0
