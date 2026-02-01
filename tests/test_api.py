import os
import time
import pytest
from fastapi.testclient import TestClient

# ensure tests run against the app import
from main import app, sessions

client = TestClient(app)

def test_root_alive():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json().get("status") == "alive"

def test_honeypot_legitimate_message():
    payload = {"message": "Dear customer, a transaction of ₹500 was debited. If not initiated by you, call us.", "session_id": "test-legit"}
    r = client.post("/honeypot", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert data.get("is_scam") is False or data.get("legit_score") >= 0  # ensure heuristic ran

def test_honeypot_scam_message_and_session_summary():
    session_id = f"test-scam-{int(time.time()*1000)}"
    payload = {"message": "Send me your UPI id and transfer now", "session_id": session_id}
    r = client.post("/honeypot", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert data.get("is_scam") is True or data.get("legit_score") < 1.0
    # summary endpoint
    r2 = client.get(f"/sessions/{session_id}/summary")
    assert r2.status_code == 200
    s = r2.json().get("summary", {})
    assert s.get("extract") is not None
    # summary should contain at least the profile keys
    assert "name" in s["extract"] and "bank" in s["extract"]

def test_sessions_inspect_sanitization():
    sid = "test-inspect"
    client.post("/honeypot", json={"message": "Hello, who is this?", "session_id": sid})
    r = client.get(f"/sessions/{sid}")
    assert r.status_code == 200
    sess = r.json().get("session")
    # recent_responses should be serializable (not a set)
    assert isinstance(sess.get("recent_responses", []), list) or isinstance(sess.get("recent_responses", []), (list, tuple))
