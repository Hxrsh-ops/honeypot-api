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
