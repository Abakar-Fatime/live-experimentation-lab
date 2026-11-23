"""Metric monitoring and automated root-cause analysis.

1. Detect: compare each day with a same-weekday baseline and flag robust outliers.
2. Explain: split the week-over-week change of a ratio metric (minutes per DAU) into
   segment contributions, separating 'rate' changes from 'mix' changes."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .config import COUNTRIES, DATA_DIR


def daily_metric(df: pd.DataFrame) -> pd.DataFrame:
    d = df.groupby("date")[["watch_minutes", "dau"]].sum().reset_index()
    d["value"] = d["watch_minutes"] / d["dau"]
    return d


def detect(d: pd.DataFrame, weeks: int = 4, threshold: float = 4.0) -> pd.DataFrame:
    """Baseline = median of the same weekday over the previous `weeks` weeks.
    Residuals are scaled by the median absolute deviation of earlier residuals (robust z-score)."""
    d = d.copy()
    vals = d["value"].to_numpy()
    base = np.full(len(d), np.nan)
    for i in range(7 * weeks, len(d)):
        base[i] = np.median(vals[[i - 7 * k for k in range(1, weeks + 1)]])
    d["baseline"] = base
    d["residual_pct"] = d["value"] / d["baseline"] - 1
    hist = d["residual_pct"].iloc[7 * weeks: len(d) - 7].dropna()
    mad = 1.4826 * np.median(np.abs(hist - hist.median()))
    d["robust_z"] = (d["residual_pct"] - hist.median()) / mad
    d["anomaly"] = d["robust_z"].abs() > threshold
    return d


def decompose(df: pd.DataFrame, dims: list[str], cur_days: list[str], prev_days: list[str]) -> pd.DataFrame:
    """Symmetric rate/mix decomposition of the change in sum(minutes)/sum(dau) across segments."""
    def agg(days):
        g = df[df.date.isin(days)].groupby(dims)[["watch_minutes", "dau"]].sum()
        g["rate"] = g["watch_minutes"] / g["dau"]
        g["weight"] = g["dau"] / g["dau"].sum()
        return g
    a, b = agg(prev_days), agg(cur_days)
    j = a.join(b, lsuffix="_prev", rsuffix="_cur", how="outer").fillna(0)
    j["rate_effect"] = (j.weight_prev + j.weight_cur) / 2 * (j.rate_cur - j.rate_prev)
    j["mix_effect"] = (j.rate_prev + j.rate_cur) / 2 * (j.weight_cur - j.weight_prev)
    j["contribution"] = j.rate_effect + j.mix_effect
    total_prev = (j.rate_prev * j.weight_prev).sum()
    total_change = (j.rate_cur * j.weight_cur).sum() - total_prev
    j["share_of_change"] = j["contribution"] / total_change
    j["segment_change_pct"] = j.rate_cur / j.rate_prev - 1
    return j.reset_index().sort_values("contribution")


def analyse() -> dict:
    df = pd.read_parquet(DATA_DIR / "monitoring_daily.parquet")
    truth = json.loads((DATA_DIR / "truth.json").read_text())["incident"]
    d = detect(daily_metric(df))
    dates = d["date"].tolist()
    cur, prev = dates[-7:], dates[-14:-7]
    total_prev = d[d.date.isin(prev)].watch_minutes.sum() / d[d.date.isin(prev)].dau.sum()
    total_cur = d[d.date.isin(cur)].watch_minutes.sum() / d[d.date.isin(cur)].dau.sum()

    by_dim = {}
    for dims in (["country"], ["device"], ["country", "device"]):
        dec = decompose(df, dims, cur, prev)
        # How concentrated is the change? share explained by the single top segment
        by_dim["_x_".join(dims)] = {
            "top_share": float(dec.iloc[0]["share_of_change"]),
            "rows": [{"segment": " / ".join(str(r[c]) for c in dims),
                      **{k: float(r[k]) for k in ["contribution", "rate_effect", "mix_effect", "share_of_change",
                                                    "segment_change_pct", "rate_prev", "rate_cur", "weight_cur"]}}
                     for _, r in dec.iterrows()]}
    best_dim = max(by_dim, key=lambda k: by_dim[k]["top_share"] if k != "country_x_device" else by_dim[k]["top_share"] - 0.05)
    top = by_dim["country_x_device"]["rows"][0]
    first_alert = d[d.anomaly]["date"].min() if d.anomaly.any() else None
    seg_series = (df[(df.country == truth["segment"]["country"]) & (df.device == truth["segment"]["device"])]
                  .assign(value=lambda x: x.watch_minutes / x.dau)[["date", "value"]])
    return {
        "metric": "LIVE watch minutes per DAU",
        "series": d[["date", "value", "baseline", "residual_pct", "robust_z", "anomaly"]]
        .replace({np.nan: None}).to_dict(orient="records"),
        "first_alert_date": first_alert, "incident_start_truth": truth["incident_start"],
        "week_over_week": {"previous": float(total_prev), "current": float(total_cur),
                           "change_pct": float(total_cur / total_prev - 1)},
        "decomposition": by_dim, "most_concentrated_dimension": best_dim,
        "root_cause": {"segment": top["segment"], "share_of_change": top["share_of_change"],
                       "segment_change_pct": top["segment_change_pct"],
                       "country_name": COUNTRIES[top["segment"].split(" / ")[0]][0]},
        "truth": truth, "found_correct_segment": top["segment"] == f"{truth['segment']['country']} / {truth['segment']['device']}",
        "segment_series": seg_series.to_dict(orient="records"),
    }
