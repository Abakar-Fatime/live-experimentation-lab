"""Experiment Copilot: retrieval-augmented question answering over the lab's knowledge base.

Retrieval  : hybrid BM25 (keywords) + LSA embeddings (TF-IDF -> SVD, semantic), fused with
             reciprocal rank fusion, plus entity linking that boosts the experiment a question names.
Tools      : a structured lookup into the results database for exact figures (lifts, CIs, decisions).
Generation : pluggable LLM backends - Ollama (local), any OpenAI-compatible API, or an offline
             extractive answerer. Every answer cites its sources as [n].
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import httpx
import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from ..config import EXPERIMENTS, METRICS, RESULTS_DIR
from .knowledge import Chunk, load_chunks

STOP = set("""a an the of to in on for and or is are was were be been it its this that with as at by from what which
how why when who whom does do did can could should would we our you your i me my about into than then there their
they them so if not no any all most more much many tell show give explain please vs versus""".split())

ALIASES = {
    "EXP-101": ["gift panel", "gift_panel_v2", "gift panel redesign", "exp-101", "101"],
    "EXP-102": ["autoplay", "autoplay preview", "autoplay_preview", "previews in feed", "exp-102", "102"],
    "EXP-103": ["comment ranking", "comment_ranking_ml", "comments", "exp-103", "103"],
    "EXP-104": ["beauty filter", "beauty_filter_promo", "filter promotion", "exp-104", "104"],
    "EXP-105": ["low latency", "low-latency", "low_latency_mode", "latency", "codec", "exp-105", "105"],
}
METRIC_ALIASES = {
    "watch_min": ["watch time", "watch minutes", "watching", "watch"],
    "gifts": ["gifts", "gifting", "gift count"],
    "gift_value": ["gift value", "revenue", "coins", "monetisation", "monetization"],
    "gifts_per_hour": ["gifts per hour", "gifts per watch hour"],
    "report_rate": ["report", "reports", "report rate", "complaints"],
    "d7_retention": ["retention", "come back", "d7"],
}

SYSTEM_PROMPT = """You are the Experiment Copilot for a LIVE-streaming experimentation team.
Answer the question using ONLY the numbered context passages. Cite passages like [1] or [2] after each claim.
Be concise (at most 5 sentences), quote numbers exactly as given, and say clearly when the context does not
contain the answer. Write for a product manager: plain words, decision first."""


ACRONYMS = {
    "srm": "sample ratio mismatch", "did": "difference in differences", "ipw": "inverse propensity weighting",
    "aipw": "doubly robust augmented inverse propensity weighting", "cate": "conditional average treatment effect uplift",
    "mde": "minimum detectable effect", "fdr": "false discovery rate", "dau": "daily active users",
    "ab": "a/b test", "rca": "root cause analysis", "ate": "average treatment effect",
}


def expand_query(q: str) -> str:
    extra = [v for k, v in ACRONYMS.items() if re.search(rf"\b{k}\b", q.lower())]
    return q + (" " + " ".join(extra) if extra else "")


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+(?:-[0-9]+)?", text.lower())
    out = []
    for t in toks:
        if t in STOP:
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


def link_experiments(q: str) -> list[str]:
    ql = q.lower()
    return [eid for eid, al in ALIASES.items() if any(re.search(rf"\b{re.escape(a)}\b", ql) for a in al)]


def link_metrics(q: str) -> list[str]:
    ql = q.lower()
    return [m for m, al in METRIC_ALIASES.items() if any(a in ql for a in al)]


@dataclass
class Hit:
    chunk: Chunk
    score: float
    ranks: dict = field(default_factory=dict)


class Retriever:
    def __init__(self, chunks: list[Chunk] | None = None, n_components: int = 64):
        self.chunks = chunks or load_chunks()
        docs = [f"{c.title}. {c.section}. {c.text}" for c in self.chunks]
        self.bm25 = BM25Okapi([tokenize(d) for d in docs])
        self.tfidf = TfidfVectorizer(tokenizer=tokenize, lowercase=False, ngram_range=(1, 2), sublinear_tf=True,
                                     token_pattern=None, min_df=1)
        X = self.tfidf.fit_transform(docs)
        k = min(n_components, X.shape[1] - 1, X.shape[0] - 1)
        self.svd = TruncatedSVD(n_components=k, random_state=0)
        self.emb = normalize(self.svd.fit_transform(X))

    def _rank(self, scores):
        order = np.argsort(-scores)
        ranks = np.empty(len(scores), int)
        ranks[order] = np.arange(len(scores))
        return ranks

    def search(self, query: str, k: int = 4, mode: str = "hybrid") -> list[Hit]:
        query = expand_query(query)
        q_tokens = tokenize(query)
        bm = self.bm25.get_scores(q_tokens)
        qv = normalize(self.svd.transform(self.tfidf.transform([query])))
        dense = (self.emb @ qv.T).ravel()
        if mode == "bm25":
            fused = bm.copy()
        elif mode == "dense":
            fused = dense.copy()
        else:
            rb, rd = self._rank(bm), self._rank(dense)
            fused = 1 / (60 + rb) + 1 / (60 + rd)
        linked = link_experiments(query)
        if linked and mode == "hybrid":
            boost = np.array([1.0 if set(c.tags) & set(linked) else 0.0 for c in self.chunks])
            fused = fused + boost * (1 / 60)
        order = np.argsort(-fused)[:k]
        self.last_max_bm25 = float(bm.max()) if len(bm) else 0.0
        return [Hit(self.chunks[i], float(fused[i]), {"bm25": float(bm[i]), "dense": float(dense[i])}) for i in order]


class ResultsTool:
    """Exact figures from the analysis outputs, so numbers in answers are never paraphrased from memory."""

    def __init__(self):
        path = RESULTS_DIR / "experiments.json"
        self.exps = {e["id"]: e for e in json.loads(path.read_text())} if path.exists() else {}
        up = RESULTS_DIR / "uplift.json"
        self.uplift = json.loads(up.read_text()) if up.exists() else None

    def lookup(self, query: str) -> list[str]:
        facts = []
        for eid in link_experiments(query):
            e = self.exps.get(eid)
            if not e:
                continue
            metrics = link_metrics(query)
            ql = query.lower()
            wants_decision = any(w in ql for w in ["ship", "decision", "launch", "result", "recommend", "should", "trust", "valid"])
            if wants_decision or not metrics:
                facts.append(f"{eid} {e['name']}: decision '{e['decision']['decision']}'. " + " ".join(e["decision"]["reasons"]))
            for m in e["metrics"]:
                if m["metric"] in metrics:
                    facts.append(f"{eid} {m['label']}: {m['rel_lift']:+.1%} relative change (95% CI {m['ci_low']:+.1%} to "
                                 f"{m['ci_high']:+.1%}, adjusted p = {m['p_adjusted']:.3g}); control mean "
                                 f"{m['control_mean']:.3g}, treatment mean {m['treatment_mean']:.3g}.")
            if any(w in ql for w in ["who", "benefit", "segment", "which users", "where"]):
                sig = sorted([g for g in e["segments"] if g["p_adjusted"] < 0.05], key=lambda g: -g["rel_lift"])[:3]
                if sig:
                    facts.append(f"{eid} segments with a significant effect on the primary metric: " + "; ".join(
                        f"{g['dimension']} {g['segment']} {g['rel_lift']:+.1%}" for g in sig) + ".")
                if eid == "EXP-105" and self.uplift:
                    top = self.uplift["top_segments"][:4]
                    facts.append("The uplift model ranks these country / device segments highest: " + ", ".join(
                        f"{t['country']} {t['device']} (predicted {t['pred']:+.0%})" for t in top) + ".")
            if "srm" in ql or "sample ratio" in ql or "split" in ql:
                s = e["srm"]
                facts.append(f"{eid} sample ratio check: treatment share {s['treatment_share']:.2%}, p = {s['p_value']:.2g}, "
                             f"{'passed' if s['passed'] else 'FAILED'}.")
        return facts


def _sentences(text: str):
    text = re.sub(r"^\d+\.\s+", "", text, flags=re.M)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text) if len(s.strip()) > 20]


class Copilot:
    def __init__(self, backend: str | None = None):
        self.retriever = Retriever()
        self.tool = ResultsTool()
        self.backend = backend or os.getenv("LAB_LLM_BACKEND", "auto")
        self.model = os.getenv("LAB_LLM_MODEL", "qwen2.5:3b-instruct")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # ---------- generation backends ----------
    def _ollama(self, messages):
        r = httpx.post(f"{self.ollama_url}/api/chat", json={"model": self.model, "messages": messages, "stream": False,
                                                            "options": {"temperature": 0.1}}, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def _openai(self, messages):
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        r = httpx.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                       json={"model": os.getenv("LAB_LLM_MODEL", "gpt-4o-mini"), "messages": messages, "temperature": 0.1},
                       timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _extractive(self, question, passages, max_sentences: int = 4):
        """Offline answerer: pick the sentences that best match the question, keep the sentence that
        follows each pick (explanations usually continue there) and cite every sentence."""
        q = set(tokenize(expand_query(question)))
        scored, by_passage = [], {}
        has_facts = any(n == 0 for n, _, _ in passages)
        facts_text = " ".join(t for n, t, _ in passages if n == 0)
        sec_tokens = {s["n"]: set(tokenize(s["section"])) for s in getattr(self, "_last_sources", [])}
        for n, text, cid in passages:
            if n == 0:
                continue
            sents = _sentences(text)
            by_passage[n] = sents
            for pos, s in enumerate(sents):
                if has_facts and (re.match(r"(Experiment EXP-|Decision:|Key \w+, owned)", s) or s in facts_text):
                    continue  # already covered by the exact facts
                overlap = len(q & set(tokenize(s))) / (len(q) ** 0.5 + 1e-9)
                prior = 1.0 / (1 + 0.35 * (n - 1))
                lead = 0.3 if pos == 0 and cid.endswith("#0") else 0.0
                lead += 0.45 * prior if pos == 0 and q & sec_tokens.get(n, set()) else 0.0
                if overlap == 0 and lead == 0 and n > 1:
                    continue  # off-topic sentence from a weaker source
                scored.append((overlap * prior + 0.05 * prior + lead - 0.01 * pos, n, pos, s))
        scored.sort(key=lambda x: -x[0])
        if has_facts:
            max_sentences = 2
        picked, seen = [], set()
        for sc, n, pos, s in scored:
            if len(picked) >= max_sentences or sc <= 0.05:
                break
            follow = by_passage[n][pos + 1:pos + 2] if n <= 2 else []
            for p_i, cand in ((pos, s), *((pos + 1, f) for f in follow)):
                if cand not in seen and len(picked) < max_sentences:
                    seen.add(cand)
                    picked.append((n, p_i, cand))
        # Present sentences in reading order: by document, then section, then position
        cids = {n: cid for n, _, cid in passages}
        doc_rank = {}
        for n, _, cid in passages:
            doc_rank.setdefault(cid.split("#")[0], len(doc_rank))
        def order(item):
            n, p_i, _ = item
            doc, _, sec = cids[n].partition("#")
            return (doc_rank[doc], int(sec or 0), p_i)
        picked = [(n, c) for n, _, c in sorted(picked, key=order)]
        facts = " ".join(t for n, t, _ in passages if n == 0)
        body = " ".join(f"{s} [{n}]" for n, s in picked)
        return (facts + (" " + body if body else "")).strip()

    def _resolve_backend(self):
        if self.backend != "auto":
            return self.backend
        try:
            httpx.get(f"{self.ollama_url}/api/tags", timeout=0.5).raise_for_status()
            return "ollama"
        except Exception:
            return "openai" if os.getenv("OPENAI_API_KEY") else "extractive"

    # ---------- main entry ----------
    def ask(self, question: str, k: int = 4) -> dict:
        hits = self.retriever.search(question, k=k)
        facts = self.tool.lookup(question)
        linked = link_experiments(question)
        grounded = bool(facts) or self.retriever.last_max_bm25 >= 3.0 or bool(linked)
        sources = [{"n": i + 1, "id": h.chunk.id, "title": h.chunk.title, "section": h.chunk.section,
                    "text": h.chunk.text, "score": round(h.score, 4)} for i, h in enumerate(hits)]
        if not grounded:
            return {"answer": "I could not find this in the lab's knowledge base. Try asking about an experiment "
                              "(EXP-101 to EXP-105), a metric, or a method such as CUPED, SRM or difference-in-differences.",
                    "sources": [], "facts": [], "backend": "none", "experiments": []}
        passages = ([(0, " ".join(facts), "facts")] if facts else []) + [(s["n"], s["text"], s["id"]) for s in sources]
        self._last_sources = sources
        backend = self._resolve_backend()
        answer = None
        if backend in ("ollama", "openai"):
            ctx = ("[0] Results database: " + " ".join(facts) + "\n\n" if facts else "") + "\n\n".join(
                f"[{s['n']}] {s['title']} - {s['section']}: {s['text']}" for s in sources)
            messages = [{"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Context:\n{ctx}\n\nQuestion: {question}"}]
            try:
                answer = self._ollama(messages) if backend == "ollama" else self._openai(messages)
            except Exception as exc:  # fall back rather than fail the user
                backend = f"extractive (LLM unavailable: {type(exc).__name__})"
        if answer is None:
            answer = self._extractive(question, passages)
            backend = backend if backend.startswith("extractive") else "extractive"
        return {"answer": answer, "sources": sources, "facts": facts, "backend": backend, "experiments": linked}


def experiments_index():
    return [{"id": e["id"], "name": e["name"], "metrics": [METRICS[m]["label"] for m in [e["primary"], *e["guardrails"]]]}
            for e in EXPERIMENTS]
