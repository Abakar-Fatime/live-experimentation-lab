"""FastAPI backend: serves analysis results, the sample-size planner and the Experiment Copilot,
plus the single-page dashboard in /web.

Run:  uvicorn lab.api:app --reload    then open http://localhost:8000
"""
from __future__ import annotations

import json
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import RESULTS_DIR, ROOT
from .stats import sample_size_per_arm

app = FastAPI(title="LIVE Experimentation Lab", version="1.0.0")
WEB = ROOT / "web"
DATASETS = ["experiments", "uplift", "causal", "monitoring", "validation", "baselines", "copilot_eval"]


@lru_cache(maxsize=None)
def _load(name: str):
    path = RESULTS_DIR / f"{name}.json"
    if not path.exists():
        raise HTTPException(404, f"{name} not found - run `python -m lab.pipeline` first")
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def _copilot():
    from .copilot.engine import Copilot
    return Copilot()


@app.get("/api/health")
def health():
    return {"status": "ok", "datasets": [d for d in DATASETS if (RESULTS_DIR / f"{d}.json").exists()]}


@app.get("/api/{name}")
def dataset(name: str):
    if name not in DATASETS:
        raise HTTPException(404, "unknown dataset")
    return _load(name)


@app.get("/api/experiments/{exp_id}")
def experiment(exp_id: str):
    for e in _load("experiments"):
        if e["id"].lower() == exp_id.lower():
            return e
    raise HTTPException(404, "experiment not found")


class PlanRequest(BaseModel):
    metric: str = "watch_min"
    mde: float = Field(0.02, gt=0, lt=1)
    alpha: float = Field(0.05, gt=0, lt=0.5)
    power: float = Field(0.8, gt=0.5, lt=1)
    use_cuped: bool = True
    daily_users: int = Field(50_000, gt=0)


@app.post("/api/plan")
def plan(req: PlanRequest):
    b = _load("baselines").get(req.metric)
    if not b:
        raise HTTPException(400, "metric has no baseline")
    vr = b.get("cuped_variance_reduction", 0.0) if req.use_cuped else 0.0
    n = sample_size_per_arm(b["mean"], b["sd"], req.mde, req.alpha, req.power, vr)
    return {"n_per_arm": n, "total": 2 * n, "days": -(-2 * n // req.daily_users), "variance_reduction": vr}


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)


@app.post("/api/ask")
def ask(req: AskRequest):
    return _copilot().ask(req.question)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")
