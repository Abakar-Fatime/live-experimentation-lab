"""Causal inference for launches that were NOT randomised.

1. Difference-in-differences: gifting v3 rolled out to two countries only.
2. Propensity methods (IPW, matching, doubly robust): creators chose to join 'Creator Academy'."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.neighbors import NearestNeighbors

from .config import DATA_DIR


def did_analysis() -> dict:
    panel = pd.read_parquet(DATA_DIR / "gifting_rollout_panel.parquet")
    truth = json.loads((DATA_DIR / "truth.json").read_text())["gifting_rollout"]
    panel["log_y"] = np.log(panel["gift_rev_per_dau"])
    panel["treat_post"] = (panel["treated_country"] & panel["post"]).astype(int)
    fit = smf.ols("log_y ~ treat_post + C(country) + C(day)", data=panel).fit(
        cov_type="cluster", cov_kwds={"groups": panel["country"]})
    b, se = fit.params["treat_post"], fit.bse["treat_post"]
    est = {"effect_pct": float(np.expm1(b) * 100), "ci_low_pct": float(np.expm1(b - 1.96 * se) * 100),
           "ci_high_pct": float(np.expm1(b + 1.96 * se) * 100), "p_value": float(fit.pvalues["treat_post"])}

    # Naive before/after on treated countries only (ignores the common trend)
    tr = panel[panel.treated_country]
    naive = float((np.exp(tr[tr.post].log_y.mean() - tr[~tr.post].log_y.mean()) - 1) * 100)

    # Event study: weekly leads/lags relative to launch, to check parallel pre-trends
    panel["rel_week"] = ((panel["day"] - truth["launch_day"]) // 7).clip(-4, 3)
    for k in range(-4, 4):
        if k != -1:
            panel[f"w_{k + 4}"] = ((panel["rel_week"] == k) & panel["treated_country"]).astype(int)
    terms = " + ".join(f"w_{k + 4}" for k in range(-4, 4) if k != -1)
    ev = smf.ols(f"log_y ~ {terms} + C(country) + C(day)", data=panel).fit(
        cov_type="cluster", cov_kwds={"groups": panel["country"]})
    event = []
    for k in range(-4, 4):
        if k == -1:
            event.append({"week": k, "effect_pct": 0.0, "ci_low_pct": 0.0, "ci_high_pct": 0.0})
            continue
        c, s = ev.params[f"w_{k + 4}"], ev.bse[f"w_{k + 4}"]
        event.append({"week": k, "effect_pct": float(np.expm1(c) * 100),
                      "ci_low_pct": float(np.expm1(c - 1.96 * s) * 100), "ci_high_pct": float(np.expm1(c + 1.96 * s) * 100)})

    daily = (panel.groupby(["day", "treated_country"])["gift_rev_per_dau"].mean().unstack()
             .rename(columns={True: "treated", False: "control"}).reset_index())
    return {"estimate": est, "naive_before_after_pct": naive, "truth_pct": truth["true_effect_pct"],
            "truth_in_ci": bool(est["ci_low_pct"] <= truth["true_effect_pct"] <= est["ci_high_pct"]),
            "launch_day": truth["launch_day"], "treated_countries": truth["treated"],
            "event_study": event, "daily": daily.to_dict(orient="records")}


def _covariates(df):
    X = pd.get_dummies(df[["country"]], dtype=float, drop_first=True)
    for c in ["followers_log", "prior_weekly_hours", "tenure_months"]:
        X[c] = df[c].to_numpy(float)
    return X


def _smd(x, t, w=None):
    w = np.ones_like(x) if w is None else w
    m1 = np.average(x[t == 1], weights=w[t == 1]); m0 = np.average(x[t == 0], weights=w[t == 0])
    v1 = np.average((x[t == 1] - m1) ** 2, weights=w[t == 1]); v0 = np.average((x[t == 0] - m0) ** 2, weights=w[t == 0])
    return float((m1 - m0) / np.sqrt((v1 + v0) / 2))


def propensity_estimates(df) -> dict:
    X, t, y = _covariates(df), df["joined_academy"].to_numpy(), df["weekly_hours_after"].to_numpy()
    ps = LogisticRegression(max_iter=2000).fit(X, t).predict_proba(X)[:, 1].clip(0.01, 0.99)
    naive = y[t == 1].mean() - y[t == 0].mean()
    w = np.where(t == 1, 1 / ps, 1 / (1 - ps))
    ipw = np.average(y[t == 1], weights=w[t == 1]) - np.average(y[t == 0], weights=w[t == 0])
    m1 = LinearRegression().fit(X[t == 1], y[t == 1]); m0 = LinearRegression().fit(X[t == 0], y[t == 0])
    mu1, mu0 = m1.predict(X), m0.predict(X)
    aipw = np.mean(mu1 - mu0 + t * (y - mu1) / ps - (1 - t) * (y - mu0) / (1 - ps))
    nn = NearestNeighbors(n_neighbors=1).fit(ps[t == 0].reshape(-1, 1))
    _, idx = nn.kneighbors(ps[t == 1].reshape(-1, 1))
    att = float(np.mean(y[t == 1] - y[t == 0][idx[:, 0]]))
    return {"naive": float(naive), "ipw": float(ipw), "aipw": float(aipw), "matching_att": att, "ps": ps, "w": w}


def propensity_analysis(n_boot: int = 200, seed: int = 3) -> dict:
    df = pd.read_parquet(DATA_DIR / "creator_academy.parquet")
    truth = json.loads((DATA_DIR / "truth.json").read_text())["creator_academy"]["true_effect_hours"]
    full = propensity_estimates(df)
    rng = np.random.default_rng(seed)
    boots = {k: [] for k in ["naive", "ipw", "aipw", "matching_att"]}
    for _ in range(n_boot):
        b = propensity_estimates(df.sample(frac=1, replace=True, random_state=int(rng.integers(1e9))))
        for k in boots:
            boots[k].append(b[k])
    estimates = []
    labels = {"naive": "Naive difference", "ipw": "Inverse propensity weighting", "matching_att": "Propensity matching (ATT)",
              "aipw": "Doubly robust (AIPW)"}
    for k in ["naive", "ipw", "matching_att", "aipw"]:
        lo, hi = np.percentile(boots[k], [2.5, 97.5])
        estimates.append({"method": labels[k], "key": k, "estimate": full[k], "ci_low": float(lo), "ci_high": float(hi),
                          "truth_in_ci": bool(lo <= truth <= hi)})
    t = df["joined_academy"].to_numpy()
    balance = []
    for c in ["followers_log", "prior_weekly_hours", "tenure_months"]:
        x = df[c].to_numpy(float)
        balance.append({"covariate": c, "smd_before": _smd(x, t), "smd_after": _smd(x, t, full["w"])})
    hist_bins = np.linspace(0, 1, 21)
    overlap = {"bins": hist_bins.tolist(),
               "joined": np.histogram(full["ps"][t == 1], hist_bins)[0].tolist(),
               "not_joined": np.histogram(full["ps"][t == 0], hist_bins)[0].tolist()}
    return {"truth_hours": truth, "n_creators": int(len(df)), "share_joined": float(t.mean()),
            "estimates": estimates, "balance": balance, "overlap": overlap}
