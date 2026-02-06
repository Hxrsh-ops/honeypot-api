from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def _clear_sessions():
    main.SESSIONS.clear()


def test_history_trimming(monkeypatch):
    _clear_sessions()

    monkeypatch.setattr(main, "MIN_LLM_DELAY_SEC", 0.0)
    monkeypatch.setattr(main, "MAX_HISTORY_MESSAGES", 4)
    monkeypatch.setattr(main, "groq_chat", lambda messages, system_prompt, **_: "ok")

    sid = "t-hist"
    for i in range(6):
        r = client.post("/honeypot", json={"message": f"msg {i}", "session_id": sid})
        assert r.status_code == 200

    sess = main.SESSIONS.get(sid) or {}
    hist = sess.get("history") or []
    assert len(hist) <= 4
    # history is role/content dicts
    assert all(isinstance(m, dict) and "role" in m and "content" in m for m in hist)


def test_redaction_masks_urls_digits_and_upi(monkeypatch):
    _clear_sessions()

    monkeypatch.setattr(main, "MIN_LLM_DELAY_SEC", 0.0)

    def _fake(messages, system_prompt, **_):
        return "ok click https://evil.example.com and otp is 123456, pay foo@upi"

    monkeypatch.setattr(main, "groq_chat", _fake)

    r = client.post("/honeypot", json={"message": "hi", "session_id": "t-redact"})
    assert r.status_code == 200
    reply = r.json().get("reply") or ""
    low = reply.lower()
    assert "https://" not in low
    assert "evil.example.com" not in low
    assert "123456" not in low
    assert "foo@upi" not in low
    assert "that link" in low or "(upi)" in low or "xxxx" in low


def test_meta_leak_replaced_with_fallback(monkeypatch):
    _clear_sessions()

    monkeypatch.setattr(main, "MIN_LLM_DELAY_SEC", 0.0)
    monkeypatch.setattr(main, "groq_chat", lambda messages, system_prompt, **_: "As an AI language model, i cant…")

    r = client.post("/honeypot", json={"message": "hi", "session_id": "t-meta"})
    assert r.status_code == 200
    reply = (r.json().get("reply") or "").lower()
    assert "as an ai" not in reply
    assert "language model" not in reply
    assert "system prompt" not in reply

