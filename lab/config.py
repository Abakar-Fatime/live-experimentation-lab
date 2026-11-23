"""Shared constants: the simulated LIVE world and the experiment registry."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
KB_DIR = ROOT / "knowledge"

SEED = 42
N_USERS = 300_000
EXPERIMENT_DAYS = 14

COUNTRIES = {
    # code: (name, share of users, emerging market?, gifting propensity)
    "ID": ("Indonesia", 0.20, True, 0.9),
    "BR": ("Brazil", 0.14, True, 1.0),
    "PH": ("Philippines", 0.11, True, 0.9),
    "VN": ("Vietnam", 0.09, True, 0.8),
    "MX": ("Mexico", 0.09, True, 1.0),
    "TH": ("Thailand", 0.08, False, 1.1),
    "MY": ("Malaysia", 0.07, False, 1.3),
    "EG": ("Egypt", 0.08, True, 0.8),
    "SA": ("Saudi Arabia", 0.06, False, 1.6),
    "NG": ("Nigeria", 0.08, True, 0.7),
}
DEVICES = ["android_low", "android_high", "ios"]

# Metric dictionary. direction: +1 means higher is better.
METRICS = {
    "watch_min": {"label": "LIVE watch minutes per viewer", "kind": "mean", "direction": 1,
                  "unit": "min", "definition": "Total minutes of LIVE content watched per user during the experiment window."},
    "gifts": {"label": "Gifts sent per viewer", "kind": "mean", "direction": 1, "unit": "gifts",
              "definition": "Number of virtual gifts a user sent to creators during the window."},
    "gift_value": {"label": "Gift value per viewer", "kind": "mean", "direction": 1, "unit": "coins",
                   "definition": "Coins spent on gifts per user; the main monetisation metric for LIVE."},
    "gifts_per_hour": {"label": "Gifts per watch hour", "kind": "ratio", "num": "gifts", "den": "watch_hours",
                       "direction": 1, "unit": "gifts/h",
                       "definition": "Gifts divided by hours watched, pooled per arm. A ratio metric, so its variance uses the delta method."},
    "report_rate": {"label": "Report rate", "kind": "mean", "direction": -1, "unit": "%",
                    "definition": "Share of users who reported a LIVE stream as harmful or annoying. A guardrail: it must not rise."},
    "d7_retention": {"label": "7-day retention", "kind": "mean", "direction": 1, "unit": "%",
                     "definition": "Share of users who came back to LIVE in the 7 days after the window. A guardrail: it must not fall."},
}

EXPERIMENTS = [
    {
        "id": "EXP-101", "key": "gift_panel_v2", "name": "Gift panel redesign",
        "hypothesis": "A larger, scrollable gift panel with recent gifts pinned will make gifting easier and increase gifts per viewer.",
        "owner_team": "LIVE Monetisation", "n_users": 120_000, "primary": "gifts",
        "secondary": ["gift_value", "gifts_per_hour", "watch_min"], "guardrails": ["report_rate", "d7_retention"],
        "truth": {"gifts": 0.05, "gift_value": 0.05},
        "story": "Clean win: gifting rises about 5% with no harm to guardrails.",
    },
    {
        "id": "EXP-102", "key": "autoplay_preview", "name": "Autoplay LIVE previews in feed",
        "hypothesis": "Auto-playing a muted LIVE preview in the For You feed will pull more viewers into LIVE rooms and raise watch time.",
        "owner_team": "LIVE Growth", "n_users": 120_000, "primary": "watch_min",
        "secondary": ["gifts", "gift_value"], "guardrails": ["report_rate", "d7_retention"],
        "truth": {"watch_min": 0.06, "report_rate": 0.25, "d7_retention": -0.015},
        "story": "Trap: watch time rises 6% but reports rise 25% and retention slips, so it should not ship.",
    },
    {
        "id": "EXP-103", "key": "comment_ranking_ml", "name": "ML ranking for LIVE comments",
        "hypothesis": "Ranking comments with an engagement model will make rooms feel livelier and raise watch time.",
        "owner_team": "LIVE Interaction", "n_users": 100_000, "primary": "watch_min",
        "secondary": ["gifts", "gift_value"], "guardrails": ["report_rate", "d7_retention"],
        "truth": {},
        "story": "Null effect: nothing really changes. Used to show how daily peeking creates false wins.",
    },
    {
        "id": "EXP-104", "key": "beauty_filter_promo", "name": "Beauty filter promotion for hosts",
        "hypothesis": "Promoting beauty filters to hosts will make streams more attractive and raise watch time.",
        "owner_team": "LIVE Creator Tools", "n_users": 100_000, "primary": "watch_min",
        "secondary": ["gifts", "gift_value"], "guardrails": ["report_rate", "d7_retention"],
        "truth": {"watch_min": 0.0},
        "srm_bug": {"device": "android_low", "drop_share": 0.10},
        "story": "Broken: a logging bug drops low-engagement Android-low users from treatment, causing sample ratio mismatch and a fake lift.",
    },
    {
        "id": "EXP-105", "key": "low_latency_mode", "name": "Low-latency streaming mode",
        "hypothesis": "A lighter video codec will cut buffering and raise watch time, especially on low-end phones with slow networks.",
        "owner_team": "LIVE Infrastructure", "n_users": 150_000, "primary": "watch_min",
        "secondary": ["gifts", "gift_value"], "guardrails": ["report_rate", "d7_retention"],
        "truth": {"watch_min_segment": {"device": "android_low", "emerging": True, "lift": 0.12}},
        "story": "Heterogeneous: big gains only for low-end Android users in emerging markets; machine learning finds who benefits.",
    },
]
