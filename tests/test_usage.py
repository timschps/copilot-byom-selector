import pytest

from byom import usage


@pytest.fixture(autouse=True)
def byom_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BYOM_HOME", str(tmp_path))


def test_estimate_prefers_most_specific_price():
    mini = usage.estimate_cost("priv-gpt-4-1-mini", 1_000_000, 0)
    full = usage.estimate_cost("priv-gpt-4-1", 1_000_000, 0)
    assert mini < full
    assert usage.estimate_cost("priv-unknown", 10, 10) == 0.0


def test_session_usage_roundtrip():
    sid = usage.start_session("C:/work")
    usage.record(sid, "priv-gpt-5", 1000, 500, 0.01, 120, True)
    usage.record(sid, "priv-gpt-5", 0, 0, 0.0, 50, False)
    o = usage.overview()
    s = o["sessions"][0]
    assert s["open"] and s["requests"] == 2 and s["prompt_tokens"] == 1000
    usage.end_session(sid)
    assert not usage.overview()["sessions"][0]["open"]
    assert o["models"][0]["alias"] == "priv-gpt-5"
