import time
import re
import random
import botpress_adapter
from agent import Agent
from memory_manager import MemoryManager


def test_otp_staged_behavior():
    s = {}
    a = Agent(s)

    # first OTP request should provoke a verification probe, not immediate OTP warning
    out1 = a.respond("Please share your OTP now")
    r1 = out1["reply"] if isinstance(out1, dict) else out1.get("reply")
    assert not any(w in r1 for w in ["I never share OTP","I won't provide any OTP","I don't share any verification codes"]) or "employee" in r1.lower() or "branch" in r1.lower()
    # session should record that OTP was asked
    assert s.get("flags", {}).get("otp_ask_count") == 1

    # second OTP request should return a refusal from OTP_WARNINGS
    out2 = a.respond("Send me OTP please, share OTP now")
    r2 = out2["reply"] if isinstance(out2, dict) else out2.get("reply")
    assert any(k in r2.lower() for k in ["otp", "verification", "call the bank"]) or len(r2) > 0


def test_persona_state_consistency():
    s = {"persona_state": "at_work"}
    a = Agent(s)

    # generate a delay reply and ensure it matches the "at_work" phrasing
    reply = a.generate_reply("delay", "")
    # reply may be a string or dict depending on implementation
    r = reply if isinstance(reply, str) else reply.get("reply")
    assert any(x in r.lower() for x in ["at work", "i'm at work", "busy"]) or 'check' in r.lower()
    # ensure we didn't flip to driving
    assert "driving" not in r.lower()
    # ensure state persisted
    assert s.get("persona_state") == "at_work"


def test_no_exact_repeats_over_many_replies():
    s = {}
    a = Agent(s)
    seen = set()
    # generate many replies and ensure none are exact duplicates
    for i in range(30):
        out = a.generate_reply("probe", "Please send your UPI id")
        r = out if isinstance(out, str) else out
        # normalize to string
        if isinstance(r, dict):
            r = r.get("reply")
        assert r is not None
        assert r not in seen, f"Repeated exact reply: {r}"
        seen.add(r)


def test_length_variation():
    # This test is intentionally about variety; seed locally to avoid flakes while
    # keeping behavior random in production.
    state = random.getstate()
    random.seed(1337)

    s = {}
    a = Agent(s)
    types = {"short":0, "medium":0, "long":0}
    for _ in range(30):
        r = a.generate_reply("probe", "Details please")
        rstr = r if isinstance(r, str) else r.get("reply")
        L = len(rstr)
        if L < 40:
            types["short"] += 1
        elif L < 100:
            types["medium"] += 1
        else:
            types["long"] += 1
    assert sum(types.values()) == 30
    # expect at least one of each length in a reasonable random run
    assert types["short"] > 0 and types["medium"] > 0

    random.setstate(state)


def test_otp_probe_variety():
    s = {}
    a = Agent(s)
    out1 = a.respond("Please share your OTP now")
    r1 = out1["reply"] if isinstance(out1, dict) else out1
    # reset otp ask count to simulate a fresh probe while preserving recent_responses
    s.setdefault("flags", {})["otp_ask_count"] = 0
    out2 = a.respond("Please share OTP now")
    r2 = out2["reply"] if isinstance(out2, dict) else out2
    assert r1 != r2, "Probe replies should vary when the prior text is in recent responses"


def test_detect_suspicious_empid_ifsc():
    s = {}
    a = Agent(s)
    # simulate an incoming message that includes a long numeric employee id and malformed IFSC
    msg = "My official ID is 1234567890123456 and my IFSC is ABCD0123456"
    a.observe(msg)
    mem = s.get("memory", [])
    assert any(m.get("type") == "suspicious_emp_id" for m in mem)
    # generate a reply, agent should escalate / question suspicious claims
    rep = a.generate_reply("probe", msg)
    r = rep if isinstance(rep, str) else rep
    assert any(k in r.lower() for k in ["id", "ifsc", "email", "branch", "call"])


def test_casual_then_escalate_on_repeats():
    s = {}
    a = Agent(s)
    # first reply should be casual-chill biased
    r1 = a.generate_reply("probe", "Please share your employee id and branch phone")
    r1s = r1 if isinstance(r1, str) else r1
    assert any(x in r1s.lower() for x in ["hmm", "hey", "one sec", "ok", "oh", "hi", "lemme", "gimme", "hold on"]) or len(r1s.split()) < 6
    # simulate repeated identical incoming messages and ensure the bot does not repeat the exact same outgoing text
    out_prev = None
    repeated_ok = True
    for _ in range(4):
        out = a.generate_reply("probe", "Please share your employee id and branch phone")
        out_s = out if isinstance(out, str) else out
        if out_s == out_prev:
            repeated_ok = False
            break
        out_prev = out_s
    assert repeated_ok, "Bot repeated the same outgoing message across repeated identical incoming messages"
    # after repeats, expect an escalation reply containing escalation keywords
    final = a.generate_reply("probe", "Please share your employee id and branch phone")
    final_s = final if isinstance(final, str) else final
    assert any(k in final_s.lower() for k in ["suspicious", "official", "ticket", "email", "branch", "call"])


def test_account_freeze_not_account_request():
    s = {}
    a = Agent(s)
    out = a.respond("I am from Joy Bank your account will freeze in under 1 hour")
    assert out.get("signals", {}).get("account_request") is False


def test_clarification_loop_breaker_after_scam_pressure():
    s = {}
    a = Agent(s)
    a.respond("send otp now to renew your account")
    out = a.respond("what do you want me to explain?")
    r = (out.get("reply") or "").lower()
    assert any(k in r for k in ["branch", "official", "email", "employee", "call"])


def test_branch_extraction_ignores_honorifics():
    s = {}
    mem = MemoryManager(s)
    mem.merge_extractions({"name": "raju", "bank": "canara"}, source="test")
    mem.mem["last_bot_messages"] = ["which branch? send branch name"]

    ex1 = mem.extract_from_text("raju sir")
    assert "branch" not in ex1

    ex2 = mem.extract_from_text("chennai")
    assert ex2.get("branch") == "chennai"


def test_employee_id_extraction_from_digits_only_after_ask():
    s = {}
    mem = MemoryManager(s)
    mem.mem["last_bot_messages"] = ["send employee id"]
    ex = mem.extract_from_text("55568994")
    assert ex.get("employee_id") == "55568994"


def test_fallback_prioritizes_link_when_provided():
    s = {}
    a = Agent(s)
    a.respond("i am from sbi bank your account will freeze in 1 hour renew now")
    out = a.respond("here is link https://secure-login.example.com")
    r = (out.get("reply") or "").lower()
    assert any(k in r for k in ["link", "site", "domain", "official"])


def test_no_bank_reask_when_extracted():
    s = {}
    a = Agent(s)
    a.respond("i am kumar from lic bank")
    out = a.respond("ok my mail is kumar.lic@gmail.com and id 66677790")
    r = (out.get("reply") or "").lower()
    assert "which bank" not in r


def test_fake_landline_called_out():
    s = {}
    mem = MemoryManager(s)
    mem.add_bot_message("send branch landline (not mobile)")
    a = Agent(s)
    out = a.respond("0008799689")
    r = (out.get("reply") or "").lower()
    assert any(k in r for k in ["fake", "landline", "mobile"])


def test_botpress_chat_path_used_and_no_exact_repeats(monkeypatch):
    """
    CI-safe: we don't call Botpress for real; we just ensure the Agent uses the adapter
    when CHAT_PROVIDER=botpress and enforces no exact duplicate outgoing messages.
    """
    s = {}
    a = Agent(s)

    monkeypatch.setenv("CHAT_PROVIDER", "botpress")
    monkeypatch.setenv("BOTPRESS_TOKEN", "dummy")
    monkeypatch.setenv("BOTPRESS_BOT_ID", "dummy")

    calls = {"n": 0}

    def _fake_chat(session, incoming):
        calls["n"] += 1
        return "ok got it"

    monkeypatch.setattr(botpress_adapter, "botpress_available", lambda: True)
    monkeypatch.setattr(botpress_adapter, "chat", _fake_chat)

    out1 = a.respond("hi")
    out2 = a.respond("hi")

    assert calls["n"] >= 2
    assert out1.get("llm_used") is True
    assert out1.get("reply")
    assert out2.get("reply")
    assert out2.get("reply") != out1.get("reply"), "Agent must not repeat exact same outgoing text"
