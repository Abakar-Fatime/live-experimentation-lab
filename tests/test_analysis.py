import json

from lab.config import RESULTS_DIR


def load(name):
    return json.loads((RESULTS_DIR / f"{name}.json").read_text())


def test_decisions_match_the_designed_stories():
    d = {e["id"]: e["decision"]["decision"] for e in load("experiments")}
    assert d == {"EXP-101": "Ship", "EXP-102": "Don't ship", "EXP-103": "No clear effect",
                 "EXP-104": "Invalid - rerun", "EXP-105": "Ship"}


def test_true_effects_inside_confidence_intervals_when_srm_passes():
    for e in load("experiments"):
        if not e["srm"]["passed"]:
            continue
        for m in e["metrics"]:
            assert m["truth_in_ci"], (e["id"], m["metric"])


def test_srm_flags_the_broken_experiment():
    srm = {e["id"]: e["srm"]["passed"] for e in load("experiments")}
    assert srm["EXP-104"] is False and sum(srm.values()) == 4


def test_cuped_removes_substantial_variance():
    for e in load("experiments"):
        vr = [m["variance_reduction"] for m in e["metrics"] if m.get("variance_reduction")]
        assert all(v > 0.35 for v in vr)


def test_uplift_beats_random_and_finds_low_end_android():
    u = load("uplift")
    assert u["models"][u["best_model"]]["auuc"] > 1.2 * u["auuc_random"]
    top4 = u["top_segments"][:4]
    assert all(s["device"] == "android_low" and s["true"] > 0 for s in top4)


def test_causal_methods_recover_truth():
    c = load("causal")
    assert c["did"]["truth_in_ci"]
    assert c["did"]["naive_before_after_pct"] > 1.5 * c["did"]["truth_pct"]
    est = {e["key"]: e for e in c["propensity"]["estimates"]}
    assert est["aipw"]["truth_in_ci"] and est["ipw"]["truth_in_ci"]
    assert not est["naive"]["truth_in_ci"]


def test_monitoring_detects_incident_and_finds_root_cause():
    m = load("monitoring")
    assert m["first_alert_date"] == m["incident_start_truth"]
    assert m["found_correct_segment"]
    assert sum(r["anomaly"] for r in m["series"][:-7]) == 0  # no false alarms before the incident


def test_validation_simulations():
    v = load("validation")
    assert 0.03 <= v["aa_peeking"]["fixed_horizon_false_positive_rate"] <= 0.07
    assert v["aa_peeking"]["daily_peeking_false_positive_rate"] > 0.09
    assert 0.92 <= v["coverage"]["coverage_raw"] <= 0.97
    assert 0.74 <= v["power"]["observed_power"] <= 0.86
