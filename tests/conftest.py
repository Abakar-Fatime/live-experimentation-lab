import pytest

from lab.config import DATA_DIR, RESULTS_DIR


@pytest.fixture(scope="session", autouse=True)
def lab_outputs():
    """Generate data and results once per test session if they are missing."""
    if not (DATA_DIR / "truth.json").exists() or not (RESULTS_DIR / "copilot_eval.json").exists():
        from lab import pipeline
        pipeline.main()
