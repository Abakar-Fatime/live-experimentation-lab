"""Monte-Carlo checks that the statistics behave as promised.

- A/A tests: a fixed-horizon test should give false positives about 5% of the time.
- Peeking: checking p-values every day and stopping at the first p < 0.05 inflates that rate.
- Coverage: 95% confidence intervals should contain the true lift about 95% of the time, with and without CUPED.
"""
from __future__ import annotations

import numpy as np

from .stats import cuped_effect, mean_effect, sample_size_per_arm


def _users(rng, n, lift=0.0):
    z = rng.normal(0, 1, n)
    pre = np.exp(np.log(55) + 0.9 * z + rng.normal(0, 0.45, n))
    post = np.exp(np.log(55) + 0.9 * z + rng.normal(0, 0.45, n))
    return pre, post * (1 + lift)


def aa_and_peeking(n_sims=1000, n_per_arm=4000, days=14, seed=1):
    rng = np.random.default_rng(seed)
    fixed_fp = peek_fp = 0
    stop_days = []
    for _ in range(n_sims):
        _, yc = _users(rng, n_per_arm)
        _, yt = _users(rng, n_per_arm)
        wc, wt = rng.gamma(1.5, size=(n_per_arm, days)), rng.gamma(1.5, size=(n_per_arm, days))
        cc = np.cumsum(yc[:, None] * wc / wc.sum(1, keepdims=True), axis=1)
        ct = np.cumsum(yt[:, None] * wt / wt.sum(1, keepdims=True), axis=1)
        mc, mt = cc.mean(0), ct.mean(0)
        se = np.sqrt(cc.var(0, ddof=1) / n_per_arm + ct.var(0, ddof=1) / n_per_arm)
        z = np.abs(mt - mc) / se
        sig = z > 1.959964
        fixed_fp += bool(sig[-1])
        if sig.any():
            peek_fp += 1
            stop_days.append(int(np.argmax(sig)) + 1)
    return {"n_sims": n_sims, "n_per_arm": n_per_arm, "looks": days,
            "fixed_horizon_false_positive_rate": fixed_fp / n_sims,
            "daily_peeking_false_positive_rate": peek_fp / n_sims,
            "median_stop_day_when_peeking": float(np.median(stop_days)) if stop_days else None}


def coverage(n_sims=1000, n_per_arm=5000, lift=0.03, seed=2):
    rng = np.random.default_rng(seed)
    cov_raw = cov_cuped = 0
    widths_raw, widths_cuped, vr = [], [], []
    for _ in range(n_sims):
        xc, yc = _users(rng, n_per_arm)
        xt, yt = _users(rng, n_per_arm, lift)
        r = mean_effect("y", yt, yc)
        c = cuped_effect("y", yt, yc, xt, xc)
        cov_raw += r.ci_low <= lift <= r.ci_high
        cov_cuped += c.ci_low <= lift <= c.ci_high
        widths_raw.append(r.ci_high - r.ci_low)
        widths_cuped.append(c.ci_high - c.ci_low)
        vr.append(c.variance_reduction)
    return {"n_sims": n_sims, "true_lift": lift, "coverage_raw": cov_raw / n_sims, "coverage_cuped": cov_cuped / n_sims,
            "mean_ci_width_raw": float(np.mean(widths_raw)), "mean_ci_width_cuped": float(np.mean(widths_cuped)),
            "mean_variance_reduction": float(np.mean(vr))}


def power_check(n_sims=500, lift=0.03, seed=4):
    """Does the sample-size formula deliver the promised 80% power?"""
    rng = np.random.default_rng(seed)
    _, y = _users(rng, 200_000)
    n = sample_size_per_arm(y.mean(), y.std(), lift)
    hits = 0
    for _ in range(n_sims):
        _, yc = _users(rng, n)
        _, yt = _users(rng, n, lift)
        hits += mean_effect("y", yt, yc).p_value < 0.05
    return {"mde": lift, "n_per_arm": n, "target_power": 0.8, "observed_power": hits / n_sims, "n_sims": n_sims}


def run_all():
    return {"aa_peeking": aa_and_peeking(), "coverage": coverage(), "power": power_check()}
