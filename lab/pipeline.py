"""Run the whole lab: simulate -> analyse -> validate -> build knowledge base -> evaluate copilot.

Usage:  python -m lab.pipeline          (about a minute on a laptop)
"""
from __future__ import annotations

import json
import time

import numpy as np

from . import causal, experiments, monitor, simulate, uplift, validate
from .config import DATA_DIR, METRICS, RESULTS_DIR, ROOT


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating,)):
        o = float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def save(name: str, obj):
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"{name}.json").write_text(json.dumps(_clean(obj), indent=1))


def baselines():
    """Baseline mean/sd of each mean-type metric from control groups, used by the planner."""
    import pandas as pd
    frames = [pd.read_parquet(DATA_DIR / f"{k}.parquet") for k in ["gift_panel_v2", "comment_ranking_ml"]]
    df = pd.concat(frames)
    df = df[df.variant == "control"]
    out = {}
    for k, m in METRICS.items():
        if m["kind"] != "mean":
            continue
        out[k] = {"label": m["label"], "mean": float(df[k].mean()), "sd": float(df[k].std()), "unit": m["unit"]}
    # Variance CUPED removes for watch time (from the pre-period correlation)
    r = np.corrcoef(df["watch_min"], df["pre_watch"])[0, 1]
    out["watch_min"]["cuped_variance_reduction"] = float(r**2)
    return out


def main(skip_sim: bool = False):
    t0 = time.time()
    if not skip_sim or not (DATA_DIR / "truth.json").exists():
        simulate.main()
    exps = experiments.analyse_all()
    save("experiments", exps)
    print("experiments analysed")
    save("uplift", uplift.analyse())
    print("uplift models trained")
    save("causal", {"did": causal.did_analysis(), "propensity": causal.propensity_analysis()})
    print("causal studies done")
    save("monitoring", monitor.analyse())
    print("monitoring done")
    save("validation", validate.run_all())
    print("validation simulations done")
    save("baselines", baselines())

    from .copilot.knowledge import write_generated_docs
    write_generated_docs()
    from .copilot import evaluate
    save("copilot_eval", evaluate.run())
    print("copilot evaluated")
    # Copy results next to the dashboard so it also works as a static site (e.g. GitHub Pages)
    static = ROOT / "web" / "data"
    static.mkdir(exist_ok=True)
    for f in RESULTS_DIR.glob("*.json"):
        (static / f.name).write_text(f.read_text())
    print(f"pipeline finished in {time.time() - t0:.0f}s -> {RESULTS_DIR}")


if __name__ == "__main__":
    import sys
    main(skip_sim="--skip-sim" in sys.argv)
