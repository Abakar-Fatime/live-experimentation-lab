"""Heterogeneous treatment effects with machine learning (T-learner and X-learner on LightGBM).

Question answered: *who* benefits from a feature, so it can be targeted instead of shipped to everyone.
The simulation stores each user's true effect, so the model's ranking can be scored against the truth."""
from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.linear_model import LogisticRegression

from .config import DATA_DIR

FEATURES_CAT = ["country", "device"]
FEATURES_NUM = ["pre_watch", "is_new"]


def _design(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.get_dummies(df[FEATURES_CAT], dtype=float)
    X["pre_watch"] = np.log1p(df["pre_watch"].to_numpy())
    X["is_new"] = df["is_new"].astype(float).to_numpy()
    return X


def _model():
    return LGBMRegressor(n_estimators=250, learning_rate=0.05, num_leaves=15, min_child_samples=400,
                         subsample=0.8, subsample_freq=1, colsample_bytree=0.9, verbose=-1, random_state=7)


def t_learner(X_tr, y_tr, w_tr, X_te):
    m1, m0 = _model().fit(X_tr[w_tr == 1], y_tr[w_tr == 1]), _model().fit(X_tr[w_tr == 0], y_tr[w_tr == 0])
    return m1.predict(X_te) - m0.predict(X_te)


def x_learner(X_tr, y_tr, w_tr, X_te):
    m1, m0 = _model().fit(X_tr[w_tr == 1], y_tr[w_tr == 1]), _model().fit(X_tr[w_tr == 0], y_tr[w_tr == 0])
    d1 = y_tr[w_tr == 1] - m0.predict(X_tr[w_tr == 1])
    d0 = m1.predict(X_tr[w_tr == 0]) - y_tr[w_tr == 0]
    tau1, tau0 = _model().fit(X_tr[w_tr == 1], d1), _model().fit(X_tr[w_tr == 0], d0)
    g = LogisticRegression(max_iter=1000).fit(X_tr, w_tr).predict_proba(X_te)[:, 1]
    return g * tau0.predict(X_te) + (1 - g) * tau1.predict(X_te)


def qini_curve(score, y, w, points: int = 20):
    """Cumulative incremental outcome when targeting users in order of predicted uplift."""
    order = np.argsort(-score)
    y, w = y[order], w[order]
    n = len(y)
    out = []
    for k in np.linspace(0, n, points + 1).astype(int)[1:]:
        yt, yc = y[:k][w[:k] == 1], y[:k][w[:k] == 0]
        gain = (yt.mean() - yc.mean()) * k if len(yt) and len(yc) else 0.0
        out.append({"share_targeted": k / n, "incremental": float(gain)})
    return out


def _auuc(curve):
    xs = np.array([0] + [c["share_targeted"] for c in curve])
    ys = np.array([0] + [c["incremental"] for c in curve])
    return float(np.trapezoid(ys, xs))


def analyse(exp_key: str = "low_latency_mode", seed: int = 11) -> dict:
    df = pd.read_parquet(DATA_DIR / f"{exp_key}.parquet")
    rng = np.random.default_rng(seed)
    test = rng.random(len(df)) < 0.5
    X = _design(df)
    y = df["watch_min"].to_numpy(float)
    y_log = np.log1p(y)  # model relative lift: watch time is heavy-tailed
    w = (df["variant"] == "treatment").astype(int).to_numpy()
    true_tau = df["true_tau_watch"].to_numpy()
    watch0 = y - w * true_tau
    true_rel = np.divide(true_tau, watch0, out=np.zeros_like(true_tau), where=watch0 > 0)

    results = {}
    for name, fn in [("t_learner", t_learner), ("x_learner", x_learner)]:
        pred = fn(X[~test], y_log[~test], w[~test], X[test])
        curve = qini_curve(pred, y[test], w[test])
        results[name] = {"pred": pred, "curve": curve, "auuc": _auuc(curve),
                         "corr_with_truth": float(np.corrcoef(pred, true_rel[test])[0, 1])}
    random_curve = [{"share_targeted": c["share_targeted"],
                     "incremental": c["share_targeted"] * results["t_learner"]["curve"][-1]["incremental"]}
                    for c in results["t_learner"]["curve"]]
    oracle_curve = qini_curve(true_rel[test] + 1e-6 * rng.random(int(test.sum())), y[test], w[test])
    best = max(results, key=lambda k: results[k]["auuc"])
    pred = results[best]["pred"]

    te = df[test].assign(pred_cate=pred, true_cate=true_rel[test], true_minutes=true_tau[test])
    te["decile"] = pd.qcut(te["pred_cate"].rank(method="first"), 10, labels=False)
    deciles = []
    for d, g in te.groupby("decile"):
        gt, gc = g[g.variant == "treatment"], g[g.variant == "control"]
        deciles.append({"decile": int(10 - d), "predicted": float(g.pred_cate.mean()), "true": float(g.true_cate.mean()),
                        "observed": float(gt.watch_min.mean() / gc.watch_min.mean() - 1), "n": int(len(g))})
    deciles.sort(key=lambda r: r["decile"])
    seg = (te.groupby(["country", "device"]).agg(pred=("pred_cate", "mean"), true=("true_cate", "mean"),
                                                   n=("pred_cate", "size")).reset_index()
           .sort_values("pred", ascending=False))
    top = seg.head(8).to_dict(orient="records")
    # Targeting policy: treat only segments whose predicted gain is clearly positive
    target_mask = te.groupby(["country", "device"])["pred_cate"].transform("mean") > 0.04
    share_targeted = float(target_mask.mean())
    captured = float(te.loc[target_mask, "true_minutes"].sum() / te["true_minutes"].sum())
    in_true_seg = te["true_cate"] > 0
    precision = float(in_true_seg[target_mask].mean())
    return {
        "experiment": exp_key, "best_model": best, "n_test": int(test.sum()),
        "models": {k: {"auuc": v["auuc"], "corr_with_truth": v["corr_with_truth"]} for k, v in results.items()},
        "auuc_random": _auuc(random_curve), "auuc_oracle": _auuc(oracle_curve),
        "qini": {"model": results[best]["curve"], "random": random_curve, "oracle": oracle_curve},
        "deciles": deciles, "top_segments": top,
        "targeting": {"share_targeted": share_targeted, "share_of_total_gain_captured": captured,
                      "precision": precision, "threshold_rel_lift": 0.04},
    }
