from lab.copilot.engine import Copilot, expand_query, link_experiments


def test_entity_linking_and_acronyms():
    assert link_experiments("why not ship autoplay previews?") == ["EXP-102"]
    assert "EXP-105" in link_experiments("who benefits from low-latency mode")
    assert "sample ratio mismatch" in expand_query("what is SRM")


def test_answers_are_grounded_and_cited():
    c = Copilot(backend="extractive")
    r = c.ask("Can we trust the beauty filter promotion result?")
    assert "Invalid" in r["answer"] and r["facts"]
    r = c.ask("How does CUPED reduce noise?")
    assert "[" in r["answer"] and r["sources"][0]["id"].startswith("cuped")


def test_out_of_scope_questions_are_declined():
    r = Copilot(backend="extractive").ask("What is the capital of France?")
    assert r["backend"] == "none" and not r["sources"]


def test_unreachable_llm_falls_back_to_extractive(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")
    r = Copilot(backend="ollama").ask("Should we ship the gift panel redesign?")
    assert r["backend"].startswith("extractive") and "Ship" in r["answer"]


def test_evaluation_quality_bar():
    import json
    from lab.config import RESULTS_DIR
    ev = json.loads((RESULTS_DIR / "copilot_eval.json").read_text())
    assert ev["retrieval"]["hybrid"]["hit@3"] >= 0.9
    assert ev["retrieval"]["hybrid"]["mrr"] >= ev["retrieval"]["bm25"]["mrr"]
    assert ev["answer_key_fact_rate"] >= 0.85
