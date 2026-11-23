"""Evaluation of the Experiment Copilot on 30 hand-written questions.

Retrieval: hit@1, hit@3 and MRR against the document that should answer each question,
           for BM25 only, LSA embeddings only, and the hybrid retriever.
Answers  : share of answers containing the key fact (number or term), using the offline extractive backend.
"""
from __future__ import annotations

from .engine import Copilot

EVAL_SET = [
    # (question, expected doc stem(s), any of these phrases must appear in the answer)
    ("Should we ship the gift panel redesign?", ["readout-exp-101"], ["ship"]),
    ("How much did gifting go up with the new gift panel?", ["readout-exp-101"], ["+4.7%", "4.7%"]),
    ("Why are we not launching autoplay previews even though watch time increased?", ["readout-exp-102", "guardrails"], ["report", "guardrail"]),
    ("What happened to the report rate in the autoplay test?", ["readout-exp-102"], ["+25.7%", "25.7%"]),
    ("Did ML comment ranking change anything?", ["readout-exp-103"], ["no clear effect", "includes zero"]),
    ("Can we trust the beauty filter promotion result?", ["readout-exp-104", "sample-ratio-mismatch"], ["mismatch", "invalid", "rerun"]),
    ("What share of users ended up in treatment for EXP-104?", ["readout-exp-104"], ["49.15%", "49.1", "49.2"]),
    ("Who benefits most from low-latency mode?", ["uplift-modelling", "readout-exp-105"], ["android", "low-end"]),
    ("What is the overall watch time lift for the low latency codec?", ["readout-exp-105"], ["+3.9%", "3.9%"]),
    ("How does CUPED reduce noise in experiments?", ["cuped"], ["pre-experiment", "pre-period", "covariate"]),
    ("How much variance does CUPED remove for watch time?", ["cuped"], ["45%"]),
    ("Why is checking the dashboard every day and stopping early dangerous?", ["peeking"], ["false positive", "11.9%"]),
    ("What false positive rate did daily peeking produce in the A/A simulations?", ["peeking"], ["11.9%"]),
    ("What does a sample ratio mismatch mean?", ["sample-ratio-mismatch"], ["split", "chi-square", "designed"]),
    ("Which p-value threshold flags an SRM?", ["sample-ratio-mismatch"], ["0.001"]),
    ("How do you compute the variance of gifts per watch hour?", ["delta-method"], ["delta method", "taylor"]),
    ("Which guardrail metrics does the LIVE team use?", ["guardrails", "metric-dictionary"], ["retention", "report"]),
    ("How is the false discovery rate controlled across metrics?", ["multiple-testing"], ["benjamini", "hochberg"]),
    ("How many users per arm do I need to detect a 3% change in watch time?", ["power-analysis"], ["41,900", "22,400"]),
    ("Did the sample size formula achieve 80% power in simulation?", ["power-analysis"], ["79.4%"]),
    ("What was the effect of gifting v3 in Brazil and Mexico?", ["difference-in-differences"], ["7.5%"]),
    ("Why is a simple before and after comparison misleading for the gifting rollout?", ["difference-in-differences"], ["trend", "14.0%"]),
    ("What assumption does difference-in-differences rely on?", ["difference-in-differences"], ["parallel trends"]),
    ("Does Creator Academy actually make creators stream more?", ["propensity-methods"], ["1.49", "1.57", "1.5 hours"]),
    ("Why is the naive comparison of academy joiners biased?", ["propensity-methods"], ["selection", "followers", "active"]),
    ("What is doubly robust estimation?", ["propensity-methods"], ["outcome model", "either model"]),
    ("How was the uplift model evaluated?", ["uplift-modelling"], ["qini", "oracle"]),
    ("What caused the drop in watch minutes per DAU in November?", ["root-cause-analysis"], ["indonesia", "v8.3"]),
    ("How does the anomaly detector decide a day is unusual?", ["root-cause-analysis"], ["median", "robust z", "same weekday"]),
    ("What is the definition of 7-day retention?", ["metric-dictionary"], ["came back", "come back"]),
]


def _rank_of(hits, expected):
    for i, h in enumerate(hits):
        if h.chunk.doc in expected:
            return i + 1
    return None


def run(k: int = 3) -> dict:
    cop = Copilot(backend="extractive")
    retrieval = {}
    for mode in ["bm25", "dense", "hybrid"]:
        ranks = [_rank_of(cop.retriever.search(q, k=10, mode=mode), exp) for q, exp, _ in EVAL_SET]
        retrieval[mode] = {
            "hit@1": sum(r == 1 for r in ranks) / len(ranks),
            "hit@3": sum(r is not None and r <= 3 for r in ranks) / len(ranks),
            "mrr": sum(1 / r for r in ranks if r) / len(ranks),
        }
    rows, correct = [], 0
    for q, exp, phrases in EVAL_SET:
        res = cop.ask(q, k=k)
        text = (res["answer"] + " " + " ".join(res["facts"])).lower()
        ok = any(p.lower() in text for p in phrases)
        correct += ok
        rows.append({"question": q, "ok": ok, "answer": res["answer"], "top_source": res["sources"][0]["id"] if res["sources"] else None})
    out_of_scope = ["What is the capital of France?", "Write me a poem about cats"]
    refusals = sum(cop.ask(q)["backend"] == "none" for q in out_of_scope)
    return {"n_questions": len(EVAL_SET), "retrieval": retrieval, "answer_key_fact_rate": correct / len(EVAL_SET),
            "backend": "extractive", "out_of_scope_refusals": f"{refusals}/{len(out_of_scope)}", "rows": rows}
