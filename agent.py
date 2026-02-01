import time, random
from typing import Dict, Any
from agent_utils import detect_links, UPI_RE, PHONE_RE, BANK_RE, NAME_RE, sample_no_repeat

class Agent:
    def __init__(self, session: Dict[str, Any]):
        self.s = session
        self.s.setdefault("profile", {
            "name": None, "bank": None, "phone": None, "upi": None, "links": [], "contradictions": 0
        })

    def observe(self, msg: str,raw: dict = None):
        msg = (msg or "").strip()
        now = time.time()
        self.s.setdefault("turns", []).append({"text": msg, "raw": raw, "ts": now})
        # extract claims
        n = NAME_RE.search(msg)
        if n: self._record_claim("name", n.group(1), msg, now)
        b = BANK_RE.search(msg)
        if b: self._record_claim("bank", b.group(1).upper(), msg, now)
        u = UPI_RE.search(msg)
        if u: self._record_claim("upi", u.group(0), msg, now)
        p = PHONE_RE.search(msg)
        if p: self._record_claim("phone", p.group(0), msg, now)
        for l in detect_links(msg): self._record_claim("link", l, msg, now)

    def _record_claim(self, kind, value, src, ts):
        claims = self.s.setdefault("claims", [])
        prev = [c for c in claims if c["kind"] == kind]
        if prev and prev[-1]["value"] != value:
            self.s["profile"]["contradictions"] = self.s["profile"].get("contradictions", 0) + 1
            self.s.setdefault("memory", []).append({
                "type": "contradiction", "kind": kind, "old": prev[-1]["value"], "new": value, "when": ts, "msg": src
            })
        claims.append({"kind": kind, "value": value, "when": ts, "msg": src})
        self.s["profile"][kind] = value

    def detect_intent(self, msg: str):
        t = (msg or "").lower()
        if any(k in t for k in ["transfer", "pay", "upi", "account", "send money", "collect", "link"]):
            return "extraction"
        if any(k in t for k in ["urgent", "immediately", "now", "asap"]):
            return "urgency"
        if any(k in t for k in ["branch", "manager", "customer care", "sir", "madam"]):
            return "authority"
        if any(k in t for k in ["hello", "hi", "hey"]):
            return "greeting"
        return "neutral"

    def choose_strategy(self, intent: str):
        contra = self.s["profile"].get("contradictions", 0)
        if contra >= 2:
            return "challenge"
        if intent == "extraction":
            return random.choice(["probe", "delay"])
        if intent == "urgency":
            return "delay"
        if intent == "authority":
            return random.choice(["probe", "challenge"])
        if intent == "greeting":
            return "smalltalk"
        return random.choice(["probe", "smalltalk", "delay"])

    def generate_reply(self, strategy: str):
        recent = self.s.setdefault("recent_responses", set())
        name = self.s["profile"].get("name")
        if strategy == "probe":
            pool = [
                "Can you send the account number and IFSC or UPI ID clearly?",
                "Where exactly should I transfer? Please share full steps.",
                "Is that a UPI ID or bank transfer? I need exact details."
            ]
        elif strategy == "delay":
            pool = [
                "One sec, I need to check my app.",
                "I’m a bit busy, can you wait a minute?",
                "I’ll do it shortly, hold on."
            ]
        elif strategy == "challenge":
            pool = [
                "This doesn't match what you said earlier — why the change?",
                "You said something different a moment ago.",
                "I’m confused — the details are changing."
            ]
        elif strategy == "smalltalk":
            pool = ["Hmm, okay", "Alright, go on", "I’m a bit busy right now"]
        else:
            pool = ["Okay, I’ll try that.", "Alright, do it then."]

        reply = sample_no_repeat(pool, recent)
        # occasional personalization
        if name and random.random() < 0.28 and strategy != "challenge":
            reply = f"{name}, {reply}"
        # vary length
        if random.random() < 0.25:
            reply = reply + " " + random.choice(["Please be precise.", "I don’t want issues.", "Explain step by step."])
        return reply

    def respond(self, incoming: str):
        self.observe(incoming)
        intent = self.detect_intent(incoming)
        strategy = self.choose_strategy(intent)
        reply = self.generate_reply(strategy)
        self.s.setdefault("strategy_history", []).append({"strategy": strategy, "intent": intent, "ts": time.time()})
        return {"reply": reply, "strategy": strategy, "intent": intent, "profile": self.s["profile"], "memory": self.s.get("memory", []), "claims": self.s.get("claims", [])}