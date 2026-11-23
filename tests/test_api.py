from fastapi.testclient import TestClient

from lab.api import app

client = TestClient(app)


def test_health_and_datasets():
    assert client.get("/api/health").json()["status"] == "ok"
    exps = client.get("/api/experiments").json()
    assert len(exps) == 5
    assert client.get("/api/experiments/EXP-102").json()["decision"]["decision"] == "Don't ship"
    assert client.get("/api/nope").status_code == 404


def test_planner_endpoint():
    r = client.post("/api/plan", json={"metric": "watch_min", "mde": 0.03, "use_cuped": True}).json()
    r2 = client.post("/api/plan", json={"metric": "watch_min", "mde": 0.03, "use_cuped": False}).json()
    assert r["n_per_arm"] < r2["n_per_arm"]


def test_ask_endpoint():
    r = client.post("/api/ask", json={"question": "Who benefits from low-latency mode?"}).json()
    assert "android" in r["answer"].lower()


def test_dashboard_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "LIVE Experimentation Lab" in r.text
