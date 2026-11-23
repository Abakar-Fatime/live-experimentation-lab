"""Core experiment statistics: Welch tests with relative lifts, delta-method ratio metrics,
CUPED variance reduction, sample ratio mismatch, power analysis and multiple-testing control."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats

Z95 = stats.norm.ppf(0.975)


@dataclass
class Effect:
    metric: str
    control_mean: float
    treatment_mean: float
    abs_diff: float
    rel_lift: float          # treatment/control - 1
    ci_low: float            # CI on the relative lift
    ci_high: float
    p_value: float
    n_control: int
    n_treatment: int
    se_rel: float
    method: str = "welch"
    variance_reduction: float | None = None

    def to_dict(self):
        return {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in asdict(self).items()}


def _rel_from_means(mt, mc, var_mt, var_mc, cov=0.0):
    """Relative lift mt/mc - 1 with a delta-method standard error."""
    rel = mt / mc - 1
    se = np.sqrt(var_mt / mc**2 + mt**2 * var_mc / mc**4 - 2 * mt * cov / mc**3)
    return rel, se


def mean_effect(metric: str, y_t: np.ndarray, y_c: np.ndarray, alpha: float = 0.05) -> Effect:
    """Difference in means, reported as a relative lift with a delta-method confidence interval."""
    nt, nc = len(y_t), len(y_c)
    mt, mc = float(np.mean(y_t)), float(np.mean(y_c))
    vt, vc = np.var(y_t, ddof=1) / nt, np.var(y_c, ddof=1) / nc
    rel, se = _rel_from_means(mt, mc, vt, vc)
    z = stats.norm.ppf(1 - alpha / 2)
    t_stat = (mt - mc) / np.sqrt(vt + vc)
    p = 2 * stats.norm.sf(abs(t_stat))
    return Effect(metric, mc, mt, mt - mc, rel, rel - z * se, rel + z * se, float(p), nc, nt, float(se))


def ratio_effect(metric: str, num_t, den_t, num_c, den_c, alpha: float = 0.05) -> Effect:
    """Ratio metric (sum num / sum den per arm) with delta-method variance, since users are the unit of randomisation."""
    def ratio_and_var(num, den):
        n = len(num)
        mn, md = np.mean(num), np.mean(den)
        r = mn / md
        cov = np.cov(num, den, ddof=1)
        var = (cov[0, 0] - 2 * r * cov[0, 1] + r**2 * cov[1, 1]) / (n * md**2)
        return r, var

    rt, vt = ratio_and_var(np.asarray(num_t, float), np.asarray(den_t, float))
    rc, vc = ratio_and_var(np.asarray(num_c, float), np.asarray(den_c, float))
    rel, se = _rel_from_means(rt, rc, vt, vc)
    z = stats.norm.ppf(1 - alpha / 2)
    p = 2 * stats.norm.sf(abs((rt - rc) / np.sqrt(vt + vc)))
    return Effect(metric, float(rc), float(rt), float(rt - rc), float(rel), float(rel - z * se), float(rel + z * se),
                  float(p), len(num_c), len(num_t), float(se), method="delta")


def cuped_effect(metric: str, y_t, y_c, x_t, x_c, alpha: float = 0.05) -> Effect:
    """CUPED: subtract theta * (pre-period covariate - mean) to remove variance explained by past behaviour.
    theta is estimated on pooled data, so the estimate stays unbiased."""
    y = np.concatenate([y_t, y_c])
    x = np.concatenate([x_t, x_c])
    theta = np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1)
    mx = x.mean()
    adj_t = y_t - theta * (x_t - mx)
    adj_c = y_c - theta * (x_c - mx)
    eff = mean_effect(metric, adj_t, adj_c, alpha)
    # Report means on the original scale for readability
    eff.control_mean, eff.treatment_mean = float(np.mean(y_c)), float(np.mean(y_t))
    raw_var = np.var(y_t, ddof=1) / len(y_t) + np.var(y_c, ddof=1) / len(y_c)
    adj_var = np.var(adj_t, ddof=1) / len(adj_t) + np.var(adj_c, ddof=1) / len(adj_c)
    eff.method = "cuped"
    eff.variance_reduction = float(1 - adj_var / raw_var)
    return eff


def srm_test(n_control: int, n_treatment: int, expected_treatment_share: float = 0.5) -> dict:
    """Chi-square test for sample ratio mismatch. p < 0.001 is the usual alarm threshold."""
    total = n_control + n_treatment
    exp_t = total * expected_treatment_share
    exp_c = total - exp_t
    chi2 = (n_treatment - exp_t) ** 2 / exp_t + (n_control - exp_c) ** 2 / exp_c
    p = float(stats.chi2.sf(chi2, df=1))
    return {"n_control": int(n_control), "n_treatment": int(n_treatment),
            "treatment_share": n_treatment / total, "chi2": float(chi2), "p_value": p, "passed": p >= 0.001}


def benjamini_hochberg(p_values: list[float], q: float = 0.05) -> list[float]:
    """Benjamini-Hochberg adjusted p-values (controls the false discovery rate)."""
    p = np.asarray(p_values, float)
    m = len(p)
    order = np.argsort(p)
    ranked = p[order] * m / (np.arange(m) + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(adj, 1.0)
    return out.tolist()


def sample_size_per_arm(baseline_mean: float, baseline_sd: float, mde_rel: float,
                        alpha: float = 0.05, power: float = 0.8, variance_reduction: float = 0.0) -> int:
    """Users needed per arm to detect a relative lift of mde_rel with a two-sided test."""
    delta = baseline_mean * mde_rel
    var = baseline_sd**2 * (1 - variance_reduction)
    z_a, z_b = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    return int(np.ceil(2 * (z_a + z_b) ** 2 * var / delta**2))


def mde_for_n(baseline_mean: float, baseline_sd: float, n_per_arm: int, alpha=0.05, power=0.8) -> float:
    z_a, z_b = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    return float((z_a + z_b) * np.sqrt(2 * baseline_sd**2 / n_per_arm) / baseline_mean)
