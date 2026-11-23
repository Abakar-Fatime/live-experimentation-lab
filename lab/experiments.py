"""Analyse every A/B test in the registry and produce a decision-ready readout."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DATA_DIR, EXPERIMENTS, METRICS
from .stats import benjamini_hochberg, cuped_effect, mean_effect, ratio_effect, srm_test

CUPED_COVARIATE = {"watch_min": "pre_watch"}


def load(exp_key: str):
    df = pd.read_parquet(DATA_DIR / f"{exp_key}.parquet")
    daily = np.load(DATA_DIR / f"{exp_key}_daily.npy")
    return df, daily


def metric_effect(df: pd.DataFrame, metric: str, use_cuped: bool = True):
    t, c = df[df.variant == "treatment"], df[df.variant == "control"]
    spec = METRICS[metric]
    if spec["kind"] == "ratio":
        return ratio_effect(metric, t[spec["num"]], t[spec["den"]], c[spec["num"]], c[spec["den"]])
    cov = CUPED_COVARIATE.get(metric)
    if use_cuped and cov:
        return cuped_effect(metric, t[metric].to_numpy(float), c[metric].to_numpy(float),
                            t[cov].to_numpy(float), c[cov].to_numpy(float))
    return mean_effect(metric, t[metric].to_numpy(float), c[metric].to_numpy(float))


def true_lift(df: pd.DataFrame, exp: dict, metric: str) -> float | None:
    truth = exp["truth"]
    if metric == "watch_min":
        if "watch_min_segment" in truth:
            tau = df["true_tau_watch"].to_numpy()
            watch0 = df["watch_min"].to_numpy() - np.where(df.variant == "treatment", tau, 0)
            return float(tau.mean() / watch0.mean())
        return truth.get("watch_min", 0.0)
    if metric in ("gifts", "gift_value", "gifts_per_hour"):
        # gifts scale with watch time, so a watch-time effect carries through to gifting
        g = truth.get("gifts", 0.0)
        w = true_lift(df, exp, "watch_min") if ("watch_min" in truth or "watch_min_segment" in truth) else 0.0
        if metric == "gifts_per_hour":
            return (1 + g) - 1
        return (1 + g) * (1 + w) - 1
    return truth.get(metric, 0.0)


def cumulative(df: pd.DataFrame, daily: np.ndarray, metric: str):
    """Effect estimate as data accumulates day by day (what a dashboard 'peeker' would see)."""
    treat = (df.variant == "treatment").to_numpy()
    cum = np.cumsum(daily, axis=1)
    if metric != "watch_min":  # spread the metric over days in proportion to watch time
        share = np.divide(cum, cum[:, -1:], out=np.zeros_like(cum), where=cum[:, -1:] > 0)
        cum = share * df[metric].to_numpy()[:, None]
    out = []
    for d in range(cum.shape[1]):
        e = mean_effect(metric, cum[treat, d], cum[~treat, d])
        out.append({"day": d + 1, "rel_lift": e.rel_lift, "ci_low": e.ci_low, "ci_high": e.ci_high, "p_value": e.p_value})
    return out


def segments(df: pd.DataFrame, metric: str):
    rows = []
    for dim in ["device", "country", "is_new"]:
        for val, g in df.groupby(dim):
            if g.variant.nunique() < 2:
                continue
            e = metric_effect(g, metric)
            rows.append({"dimension": dim, "segment": str(val), "n": int(len(g)), "rel_lift": e.rel_lift,
                         "ci_low": e.ci_low, "ci_high": e.ci_high, "p_value": e.p_value})
    adj = benjamini_hochberg([r["p_value"] for r in rows])
    for r, a in zip(rows, adj):
        r["p_adjusted"] = a
    return rows


def decide(srm: dict, primary: dict, guardrails: list[dict]) -> dict:
    reasons = []
    if not srm["passed"]:
        return {"decision": "Invalid - rerun", "tone": "invalid",
                "reasons": [f"Sample ratio mismatch: treatment share {srm['treatment_share']:.2%} vs 50% expected "
                            f"(p = {srm['p_value']:.1e}). Results cannot be trusted until the assignment bug is fixed."]}
    breached = [g for g in guardrails if g["breached"]]
    if breached:
        for g in breached:
            reasons.append(f"Guardrail breached: {METRICS[g['metric']]['label']} moved {g['rel_lift']:+.1%} "
                           f"(adjusted p = {g['p_adjusted']:.3g}).")
        if primary["significant"] and primary["rel_lift"] > 0:
            reasons.insert(0, f"Primary metric improved {primary['rel_lift']:+.1%}, but the trade-off is not acceptable.")
        return {"decision": "Don't ship", "tone": "bad", "reasons": reasons}
    if primary["significant"] and primary["rel_lift"] > 0:
        return {"decision": "Ship", "tone": "good",
                "reasons": [f"{METRICS[primary['metric']]['label']} up {primary['rel_lift']:+.1%} "
                            f"(95% CI {primary['ci_low']:+.1%} to {primary['ci_high']:+.1%}); all guardrails healthy."]}
    if primary["significant"] and primary["rel_lift"] < 0:
        return {"decision": "Don't ship", "tone": "bad",
                "reasons": [f"Primary metric fell {primary['rel_lift']:+.1%}."]}
    return {"decision": "No clear effect", "tone": "neutral",
            "reasons": [f"{METRICS[primary['metric']]['label']} moved {primary['rel_lift']:+.1%} but the 95% CI "
                        f"({primary['ci_low']:+.1%} to {primary['ci_high']:+.1%}) includes zero. Keep control or iterate."]}


def analyse(exp: dict) -> dict:
    df, daily = load(exp["key"])
    n_t = int((df.variant == "treatment").sum())
    srm = srm_test(len(df) - n_t, n_t)
    metric_list = [exp["primary"], *exp["secondary"], *exp["guardrails"]]
    effects = [metric_effect(df, m).to_dict() for m in metric_list]
    adj = benjamini_hochberg([e["p_value"] for e in effects])
    for e, a in zip(effects, adj):
        spec = METRICS[e["metric"]]
        e.update(label=spec["label"], unit=spec["unit"], direction=spec["direction"], p_adjusted=a,
                 significant=a < 0.05,
                 role="primary" if e["metric"] == exp["primary"] else
                 "guardrail" if e["metric"] in exp["guardrails"] else "secondary",
                 true_lift=true_lift(df, exp, e["metric"]))
        e["breached"] = bool(e["role"] == "guardrail" and e["significant"] and e["rel_lift"] * spec["direction"] < 0)
        if e["true_lift"] is not None:
            e["truth_in_ci"] = bool(e["ci_low"] <= e["true_lift"] <= e["ci_high"])
    primary = next(e for e in effects if e["role"] == "primary")
    raw_primary = metric_effect(df, exp["primary"], use_cuped=False).to_dict()
    guardrails = [e for e in effects if e["role"] == "guardrail"]
    cum = cumulative(df, daily, exp["primary"])
    first_sig = next((c["day"] for c in cum if c["p_value"] < 0.05), None)
    return {
        "id": exp["id"], "key": exp["key"], "name": exp["name"], "hypothesis": exp["hypothesis"],
        "owner_team": exp["owner_team"], "primary": exp["primary"], "n_users": int(len(df)), "days": daily.shape[1],
        "srm": srm, "metrics": effects, "primary_raw": raw_primary,
        "decision": decide(srm, primary, guardrails), "cumulative": cum,
        "peeking": {"first_day_p_below_05": first_sig, "final_p": cum[-1]["p_value"]},
        "segments": segments(df, exp["primary"]), "story": exp["story"],
    }


def analyse_all() -> list[dict]:
    return [analyse(e) for e in EXPERIMENTS]
