"""Simulate a LIVE-streaming platform with experiments whose true effects are known.

Because the ground truth is known, every estimate the lab produces can be checked:
did the A/B test find the real lift, did CUPED shrink the interval, did the causal
methods recover the effect, did the root-cause search find the broken segment?

Run:  python -m lab.simulate
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .config import COUNTRIES, DATA_DIR, DEVICES, EXPERIMENT_DAYS, EXPERIMENTS, N_USERS, SEED

BASE_WATCH = np.log(55.0)  # median minutes of LIVE watched per active user in 14 days


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def make_users(rng: np.random.Generator) -> pd.DataFrame:
    codes = list(COUNTRIES)
    shares = np.array([COUNTRIES[c][1] for c in codes])
    country = rng.choice(codes, size=N_USERS, p=shares / shares.sum())
    emerging = np.array([COUNTRIES[c][2] for c in country])
    dev_p = np.where(emerging[:, None], [0.55, 0.30, 0.15], [0.25, 0.40, 0.35])
    u = rng.random(N_USERS)[:, None]
    device = np.array(DEVICES)[(u > dev_p.cumsum(axis=1)).sum(axis=1)]
    is_new = rng.random(N_USERS) < 0.25
    dev_eff = pd.Series(device).map({"android_low": -0.15, "android_high": 0.0, "ios": 0.15}).to_numpy()
    engagement = rng.normal(0, 1, N_USERS) + dev_eff - 0.3 * is_new
    gift_prop = (np.array([COUNTRIES[c][3] for c in country])
                 * rng.lognormal(0, 0.5, N_USERS) * np.where(device == "ios", 1.3, 1.0))
    active_pre = rng.random(N_USERS) < _sigmoid(1.7 + 0.8 * engagement)
    pre_watch = np.where(active_pre, np.exp(BASE_WATCH + 0.9 * engagement + rng.normal(0, 0.45, N_USERS)), 0.0)
    return pd.DataFrame({
        "user_id": np.arange(1, N_USERS + 1), "country": country, "emerging": emerging, "device": device,
        "is_new": is_new, "engagement": engagement, "gift_prop": gift_prop, "pre_watch": pre_watch.round(2),
    })


def run_experiment(users: pd.DataFrame, exp: dict, rng: np.random.Generator):
    df = users.sample(n=exp["n_users"], random_state=int(rng.integers(1e9))).reset_index(drop=True)
    n = len(df)
    df["variant"] = np.where(rng.random(n) < 0.5, "treatment", "control")
    treat = (df["variant"] == "treatment").to_numpy()
    truth = exp["truth"]
    z = df["engagement"].to_numpy()

    # Potential outcome without treatment
    active = rng.random(n) < _sigmoid(1.7 + 0.8 * z)
    watch0 = np.where(active, np.exp(BASE_WATCH + 0.9 * z + rng.normal(0, 0.45, n)), 0.0)

    lift = np.full(n, truth.get("watch_min", 0.0))
    seg = truth.get("watch_min_segment")
    if seg:
        in_seg = (df["device"].to_numpy() == seg["device"]) & (df["emerging"].to_numpy() == seg["emerging"])
        lift = np.where(in_seg, seg["lift"], 0.0)
    true_tau = watch0 * lift
    watch = watch0 + treat * true_tau

    gift_mult = 1 + treat * truth.get("gifts", 0.0)
    gifts = rng.poisson(0.012 * watch * df["gift_prop"].to_numpy() * gift_mult)
    # Each gift has a price in coins; sum of a gamma approximates the basket value
    gift_value = np.where(gifts > 0, rng.gamma(shape=np.maximum(gifts, 1) * 1.5, scale=5.0), 0.0)

    p_report = np.clip(0.035 * np.exp(-0.25 * z) * (1 + treat * truth.get("report_rate", 0.0)), 0, 1)
    report = rng.random(n) < p_report
    p_ret = np.clip(_sigmoid(0.8 + 0.9 * z) * (1 + treat * truth.get("d7_retention", 0.0)), 0, 1)
    d7 = rng.random(n) < p_ret

    df = df.assign(watch_min=watch.round(2), watch_hours=(watch / 60).round(4), gifts=gifts,
                   gift_value=gift_value.round(2), report_rate=report.astype(int),
                   d7_retention=d7.astype(int), true_tau_watch=true_tau.round(3))

    # Daily breakdown of watch minutes (for cumulative effect and peeking analysis)
    w = rng.gamma(1.5, size=(n, EXPERIMENT_DAYS)) * (1 + 0.15 * np.isin(np.arange(EXPERIMENT_DAYS) % 7, [5, 6]))
    daily = (watch[:, None] * w / w.sum(axis=1, keepdims=True)).astype(np.float32)

    bug = exp.get("srm_bug")
    if bug:  # logging bug silently drops low-engagement users of one device from treatment
        target = treat & (df["device"].to_numpy() == bug["device"])
        weak = z < np.median(z[target])
        drop = target & weak & (rng.random(n) < 2 * bug["drop_share"])
        keep = ~drop
        df, daily = df[keep].reset_index(drop=True), daily[keep]

    return df.drop(columns=["engagement", "gift_prop"]), daily


def make_rollout_panel(rng):
    """Country-level daily gift revenue per DAU; gifting v3 launched in BR and MX on day 31."""
    days = 60
    treated = {"BR", "MX"}
    rows = []
    country_noise = {c: rng.normal(0, 0.05) for c in COUNTRIES}
    for c, (name, _, _, giftiness) in COUNTRIES.items():
        base = np.log(20 * giftiness) + country_noise[c]
        for t in range(days):
            season = 0.06 * np.sin(2 * np.pi * t / 7) + 0.002 * t
            effect = np.log(1.07) if (c in treated and t >= 30) else 0.0
            y = base + season + effect + rng.normal(0, 0.03)
            rows.append({"country": c, "day": t, "treated_country": c in treated, "post": t >= 30,
                         "gift_rev_per_dau": float(np.exp(y))})
    return pd.DataFrame(rows), {"true_effect_pct": 7.0, "launch_day": 30, "treated": sorted(treated)}


def make_creator_programme(rng):
    """Observational data: creators opt in to 'Creator Academy'. Strong creators opt in more (selection bias)."""
    n = 20_000
    followers_log = rng.normal(7, 1.2, n)
    prior_hours = np.exp(np.log(6) + 0.25 * (followers_log - 7) + rng.normal(0, 0.45, n))
    tenure = rng.integers(1, 37, n)
    country = rng.choice(list(COUNTRIES), n)
    p_opt = _sigmoid(-2.2 + 0.9 * (followers_log - 7) + 0.25 * (prior_hours - 6) + 0.02 * tenure)
    joined = rng.random(n) < p_opt
    true_effect = 1.5
    post_hours = (1.0 * prior_hours + 0.6 * (followers_log - 7) + 0.03 * tenure
                  + rng.normal(0, 1.5, n) + true_effect * joined)
    df = pd.DataFrame({"creator_id": np.arange(n), "country": country, "followers_log": followers_log.round(3),
                       "prior_weekly_hours": prior_hours.round(3), "tenure_months": tenure,
                       "joined_academy": joined.astype(int), "weekly_hours_after": post_hours.round(3)})
    return df, {"true_effect_hours": true_effect}


def make_monitoring_panel(rng):
    """Daily LIVE watch minutes per DAU by country x device; an app bug hits ID x android_low in the last week."""
    days = 60
    dates = pd.date_range(end="2026-11-22", periods=days)
    rows = []
    for c, (_, share, emerging, _) in COUNTRIES.items():
        dev_share = [0.55, 0.30, 0.15] if emerging else [0.25, 0.40, 0.35]
        for d, ds in zip(DEVICES, dev_share):
            dau0 = 2_000_000 * share * ds
            mpd0 = 34 * {"android_low": 0.85, "android_high": 1.0, "ios": 1.15}[d] * rng.uniform(0.9, 1.1)
            for t, date in enumerate(dates):
                weekend = 1.08 if date.dayofweek >= 5 else 1.0
                dau = dau0 * weekend * (1 + 0.001 * t) * rng.normal(1, 0.01)
                mpd = mpd0 * weekend * rng.normal(1, 0.012)
                if c == "ID" and d == "android_low" and t >= days - 7:  # app v8.3 player bug
                    mpd *= 0.62
                    dau *= 0.96
                rows.append({"date": date.date().isoformat(), "country": c, "device": d,
                             "dau": round(dau), "watch_minutes": round(dau * mpd)})
    truth = {"incident_start": dates[days - 7].date().isoformat(), "segment": {"country": "ID", "device": "android_low"},
             "cause": "Android app v8.3 video player bug"}
    return pd.DataFrame(rows), truth


def main():
    rng = np.random.default_rng(SEED)
    DATA_DIR.mkdir(exist_ok=True)
    users = make_users(rng)
    users.drop(columns=["engagement", "gift_prop"]).to_parquet(DATA_DIR / "users.parquet", index=False)
    for exp in EXPERIMENTS:
        df, daily = run_experiment(users, exp, rng)
        df.to_parquet(DATA_DIR / f"{exp['key']}.parquet", index=False)
        np.save(DATA_DIR / f"{exp['key']}_daily.npy", daily)
        print(f"{exp['id']} {exp['key']}: {len(df):,} users")
    panel, t1 = make_rollout_panel(rng)
    panel.to_parquet(DATA_DIR / "gifting_rollout_panel.parquet", index=False)
    creators, t2 = make_creator_programme(rng)
    creators.to_parquet(DATA_DIR / "creator_academy.parquet", index=False)
    mon, t3 = make_monitoring_panel(rng)
    mon.to_parquet(DATA_DIR / "monitoring_daily.parquet", index=False)
    (DATA_DIR / "truth.json").write_text(json.dumps({"gifting_rollout": t1, "creator_academy": t2, "incident": t3}, indent=2))
    print("simulation done ->", DATA_DIR)


if __name__ == "__main__":
    main()
