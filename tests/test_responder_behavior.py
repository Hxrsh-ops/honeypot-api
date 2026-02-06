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
    monkeypatch.setattr(main, "groq_chat", lambda messages, system_prompt, **_: "As an AI language model, i cant...")

    r = client.post("/honeypot", json={"message": "hi", "session_id": "t-meta"})
    assert r.status_code == 200
    reply = (r.json().get("reply") or "").lower()
    assert "as an ai" not in reply
    assert "language model" not in reply
    assert "system prompt" not in reply


def test_meta_false_positive_kapil_not_replaced(monkeypatch):
    _clear_sessions()

    monkeypatch.setattr(main, "MIN_LLM_DELAY_SEC", 0.0)
    monkeypatch.setattr(main, "groq_chat", lambda messages, system_prompt, **_: "ok kapil")

    r = client.post("/honeypot", json={"message": "hi", "session_id": "t-kapil"})
    assert r.status_code == 200
    assert r.json().get("reply") == "ok kapil"


def test_long_mode_postprocess_allows_more_lines(monkeypatch):
    _clear_sessions()

    monkeypatch.setattr(main, "MIN_LLM_DELAY_SEC", 0.0)

    monkeypatch.setattr(
        main,
        "choose_verbosity",
        lambda session, signals: {
            "mode": "long",
            "max_lines": 4,
            "max_chars": 520,
            "max_tokens": 220,
            "length_hint": "long",
        },
    )
    monkeypatch.setattr(main, "groq_chat", lambda messages, system_prompt, **_: "l1\nl2\nl3\nl4\nl5")

    r = client.post("/honeypot", json={"message": "hi", "session_id": "t-long"})
    assert r.status_code == 200
    reply = r.json().get("reply") or ""
    lines = [ln for ln in reply.splitlines() if ln.strip()]
    assert len(lines) == 4
    assert "l4" in reply
    assert "l5" not in reply


def test_target_rotation_deterministic_and_no_back_to_back_repeat():
    s = {"intel": {}}
    signals = {}

    t1 = main.choose_next_target(s, signals)
    t2 = main.choose_next_target(s, signals)
    assert t1 == "bank_org"
    assert t2 == "name_role"

    # simulate providing missing intel and ensure rotation progresses (fresh session state)
    s2 = {"intel": {"bank_org": {"value": "sbi bank", "ts": 0.0}}}
    t3 = main.choose_next_target(s2, signals)
    assert t3 == "name_role"

    s2["intel"]["name_role"] = {"value": "rajesh manager", "ts": 0.0}
    t4 = main.choose_next_target(s2, signals)
    assert t4 == "employee_id"
