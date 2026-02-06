import time

from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def _clear_sessions():
    main.SESSIONS.clear()


def test_root_alive():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json().get("status") == "alive"


def test_honeypot_minimal_response_shape(monkeypatch):
    _clear_sessions()

    monkeypatch.setattr(main, "MIN_LLM_DELAY_SEC", 0.0)
    monkeypatch.setattr(main, "groq_chat", lambda messages, system_prompt, **_: "who's this?")

    r = client.post("/honeypot", json={"message": "hi", "session_id": "t-min"})
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"reply", "session_id"}
    assert data["session_id"] == "t-min"
    assert isinstance(data["reply"], str) and data["reply"].strip()


def test_throttle_returns_delay_without_llm_call(monkeypatch):
    _clear_sessions()

    calls = {"n": 0}

    def _fake_groq(messages, system_prompt, **_):
        calls["n"] += 1
        return "ok"

    class _Clock:
        def __init__(self, t: float):
            self.t = t

        def time(self) -> float:
            return self.t

    clock = _Clock(1000.0)
    monkeypatch.setattr(main.time, "time", clock.time)
    monkeypatch.setattr(main, "MIN_LLM_DELAY_SEC", 2.0)
    monkeypatch.setattr(main, "groq_chat", _fake_groq)

    sid = f"t-throttle-{int(time.time() * 1000)}"

    r1 = client.post("/honeypot", json={"message": "hi", "session_id": sid})
    assert r1.status_code == 200
    assert calls["n"] == 1

    clock.t = 1000.5  # < 2s later
    r2 = client.post("/honeypot", json={"message": "hello?", "session_id": sid})
    assert r2.status_code == 200
    assert calls["n"] == 1, "Second request should be throttled (no Groq call)"

    reply2 = (r2.json().get("reply") or "").lower()
    assert any(k in reply2 for k in ["give me a moment", "one sec", "hold on", "im checking", "im looking"])


def test_llm_failure_returns_human_fallback(monkeypatch):
    _clear_sessions()

    monkeypatch.setattr(main, "MIN_LLM_DELAY_SEC", 0.0)

    def _boom(*args, **kwargs):
        raise RuntimeError("nope")

    monkeypatch.setattr(main, "groq_chat", _boom)

    r = client.post("/honeypot", json={"message": "hi", "session_id": "t-fail"})
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"reply", "session_id"}
    assert data["reply"]
    assert "groq" not in data["reply"].lower()
    assert "api" not in data["reply"].lower()


def test_debug_endpoints_disabled_by_default(monkeypatch):
    _clear_sessions()

    monkeypatch.setattr(main, "DEBUG_ENDPOINTS", False)
    r1 = client.get("/sessions/whatever")
    assert r1.status_code == 404
    r2 = client.get("/sessions/whatever/summary")
    assert r2.status_code == 404

