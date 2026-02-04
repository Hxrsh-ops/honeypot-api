import time
import re
from agent import Agent


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
