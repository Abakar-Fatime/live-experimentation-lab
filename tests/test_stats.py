import numpy as np
from scipy import stats as sps

from lab.stats import (benjamini_hochberg, cuped_effect, mean_effect, ratio_effect, sample_size_per_arm, srm_test)


def test_mean_effect_matches_welch_and_relative_lift():
    rng = np.random.default_rng(0)
    c, t = rng.normal(100, 20, 5000), rng.normal(103, 20, 5000)
    e = mean_effect("y", t, c)
    welch = sps.ttest_ind(t, c, equal_var=False)
    assert abs(e.p_value - welch.pvalue) < 1e-3
    assert abs(e.rel_lift - (t.mean() / c.mean() - 1)) < 1e-12
    assert e.ci_low < e.rel_lift < e.ci_high


def test_cuped_is_unbiased_and_reduces_variance():
    rng = np.random.default_rng(1)
    z = rng.normal(0, 1, 20000)
    x = 50 + 10 * z + rng.normal(0, 3, 20000)
    y = 50 + 10 * z + rng.normal(0, 3, 20000)
    treat = rng.random(20000) < 0.5
    y = y * np.where(treat, 1.02, 1.0)
    raw = mean_effect("y", y[treat], y[~treat])
    cup = cuped_effect("y", y[treat], y[~treat], x[treat], x[~treat])
    assert cup.variance_reduction > 0.7
    assert (cup.ci_high - cup.ci_low) < (raw.ci_high - raw.ci_low)
    assert abs(cup.rel_lift - 0.02) < 3 * cup.se_rel  # unbiased within sampling error


def test_ratio_metric_delta_method_close_to_bootstrap():
    rng = np.random.default_rng(2)
    den_c, den_t = rng.gamma(2, 1, 3000), rng.gamma(2, 1, 3000)
    num_c, num_t = rng.poisson(den_c * 3), rng.poisson(den_t * 3.3)
    e = ratio_effect("r", num_t, den_t, num_c, den_c)
    boots = []
    for _ in range(300):
        i, j = rng.integers(0, 3000, 3000), rng.integers(0, 3000, 3000)
        boots.append((num_t[i].sum() / den_t[i].sum()) / (num_c[j].sum() / den_c[j].sum()) - 1)
    assert abs(np.std(boots) - e.se_rel) / e.se_rel < 0.15


def test_srm_detects_imbalance():
    assert srm_test(50_000, 50_100)["passed"]
    assert not srm_test(50_000, 48_000)["passed"]


def test_benjamini_hochberg_is_monotone_and_bounded():
    adj = benjamini_hochberg([0.01, 0.04, 0.03, 0.5])
    assert all(0 <= a <= 1 for a in adj)
    assert adj[0] <= adj[2] <= adj[1] <= adj[3]


def test_sample_size_formula():
    # classic result: 2 * (1.96 + 0.84)^2 * sd^2 / delta^2
    n = sample_size_per_arm(100, 20, 0.02)
    assert 1_560 < n < 1_580
    assert sample_size_per_arm(100, 20, 0.02, variance_reduction=0.5) < n * 0.51
