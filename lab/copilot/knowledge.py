"""Builds the copilot's knowledge base: hand-written method guides plus documents generated
from the lab's own results (metric dictionary, experiment readouts, causal studies, incidents)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..config import EXPERIMENTS, KB_DIR, METRICS, RESULTS_DIR


@dataclass
class Chunk:
    id: str
    doc: str
    title: str
    section: str
    text: str
    tags: list[str]

    def to_dict(self):
        return self.__dict__


def _pct(x):
    return f"{x:+.1%}"


def experiment_readout(r: dict) -> str:
    lines = [f"# {r['id']} {r['name']} - experiment readout", "",
             "## Summary",
             f"Experiment {r['id']} ({r['name']}, key {r['key']}) was run by {r['owner_team']} on "
             f"{r['n_users']:,} users for {r['days']} days. Decision: {r['decision']['decision']}. "
             + " ".join(r["decision"]["reasons"]), "",
             "## Hypothesis", r["hypothesis"], "",
             "## Sample ratio check",
             f"Treatment received {r['srm']['treatment_share']:.2%} of users (chi-square p = {r['srm']['p_value']:.2g}). "
             + ("The split is healthy." if r["srm"]["passed"] else
                "This is a sample ratio mismatch, so the results are not trustworthy."), "",
             "## Metric results"]
    for m in r["metrics"]:
        extra = f" CUPED removed {m['variance_reduction']:.0%} of the variance." if m.get("variance_reduction") else ""
        lines.append(f"{m['label']} ({m['role']}): {_pct(m['rel_lift'])} relative change, 95% CI {_pct(m['ci_low'])} "
                     f"to {_pct(m['ci_high'])}, adjusted p = {m['p_adjusted']:.3g}"
                     f"{', guardrail breached' if m.get('breached') else ''}.{extra}")
    sig_segments = [s for s in r["segments"] if s["p_adjusted"] < 0.05]
    lines += ["", "## Segments"]
    if sig_segments:
        best = sorted(sig_segments, key=lambda s: -s["rel_lift"])[:4]
        lines.append("Significant segment effects on the primary metric: " + "; ".join(
            f"{s['dimension']} {s['segment']} {_pct(s['rel_lift'])}" for s in best) + ".")
    else:
        lines.append("No segment showed a significant effect on the primary metric after multiple-testing correction.")
    lines += ["", "## Peeking",
              (f"The cumulative p-value first dropped below 0.05 on day {r['peeking']['first_day_p_below_05']}."
               if r["peeking"]["first_day_p_below_05"] else
               "The cumulative p-value never dropped below 0.05 during the test."), ""]
    return "\n".join(lines)


def metric_dictionary() -> str:
    lines = ["# Metric dictionary", ""]
    for key, m in METRICS.items():
        lines += [f"## {m['label']}",
                  f"Metric key {key}. {m['definition']} Unit: {m['unit']}. "
                  f"{'Higher is better.' if m['direction'] > 0 else 'Lower is better.'}", ""]
    return "\n".join(lines)


def experiment_registry() -> str:
    lines = ["# Experiment registry", ""]
    for e in EXPERIMENTS:
        lines += [f"## {e['id']} {e['name']}",
                  f"Key {e['key']}, owned by {e['owner_team']}. Hypothesis: {e['hypothesis']} "
                  f"Primary metric: {METRICS[e['primary']]['label']}. Guardrails: "
                  + ", ".join(METRICS[g]["label"] for g in e["guardrails"]) + ".", ""]
    return "\n".join(lines)


def incident_report(m: dict) -> str:
    rc, wow = m["root_cause"], m["week_over_week"]
    rows = m["decomposition"]["country_x_device"]["rows"][:3]
    return "\n".join([
        f"# Incident report - LIVE watch time drop ({m['first_alert_date']})", "",
        "## What happened",
        f"LIVE watch minutes per DAU fell {abs(wow['change_pct']):.1%} week over week "
        f"(from {wow['previous']:.1f} to {wow['current']:.1f} minutes). The anomaly detector raised the first alert on "
        f"{m['first_alert_date']}, the same day the drop started.", "",
        "## Root cause",
        f"The drop is concentrated in {rc['country_name']} on low-end Android phones ({rc['segment']}): that segment's "
        f"minutes per DAU fell {abs(rc['segment_change_pct']):.0%} and it explains {rc['share_of_change']:.0%} of the total change "
        "(other segments slightly offset it). The cause was the Android app v8.3 video player bug on low-end devices.", "",
        "## Top contributing segments",
        "; ".join(f"{r['segment']}: {r['share_of_change']:.0%} of the change" for r in rows) + ".", "",
        "## Follow-up",
        "Roll back or hotfix the v8.3 player on low-end Android, add app version as a monitoring dimension, and "
        "exclude the incident week from experiment baselines.", ""])


def write_generated_docs():
    out = KB_DIR / "generated"
    out.mkdir(parents=True, exist_ok=True)
    exps = json.loads((RESULTS_DIR / "experiments.json").read_text())
    for r in exps:
        (out / f"readout-{r['id'].lower()}.md").write_text(experiment_readout(r))
    (out / "metric-dictionary.md").write_text(metric_dictionary())
    mon = json.loads((RESULTS_DIR / "monitoring.json").read_text())
    (out / "incident-watch-time-drop.md").write_text(incident_report(mon))
    (out / "experiment-registry.md").write_text(experiment_registry())


def _split_sections(text: str):
    title = re.search(r"^# (.+)$", text, re.M).group(1).strip()
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    sections = []
    for i in range(1, len(parts), 2):
        sections.append((parts[i].strip(), parts[i + 1].strip()))
    return title, sections


def load_chunks() -> list[Chunk]:
    chunks = []
    for path in sorted(KB_DIR.rglob("*.md")):
        title, sections = _split_sections(path.read_text())
        exp_ids = re.findall(r"EXP-\d{3}", title)
        for j, (sec, body) in enumerate(sections):
            tags = sorted(set(exp_ids + re.findall(r"EXP-\d{3}", body)))
            chunks.append(Chunk(id=f"{path.stem}#{j}", doc=path.stem, title=title, section=sec, text=body, tags=tags))
    return chunks
