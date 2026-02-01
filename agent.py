import re, time, random
from typing import Dict, Any, Optional
from agent_utils import detect_links, UPI_RE, PHONE_RE, BANK_RE, NAME_RE, sample_no_repeat
from victim_dataset import PERSONA_STYLE_TEMPLATES, BANKS, PROBING, OTP_WARNINGS

NUM_RE = re.compile(r"\b(\d{3,})\b")
BANK_NAME_RE = re.compile(r"\b(?:from|at)\s+([A-Za-z ]+?)(?:\s+bank\b|\bbranch\b|[.,;:]|$)", re.I)
TICKET_KEYWORDS = ["ticket", "complaint", "ref", "reference", "ticket number", "complaint id", "txn", "transaction"]

class Agent:
    def __init__(self, session: Dict[str, Any]):
        self.s = session
        self.s.setdefault("profile", {
            "name": None, "bank": None, "phone": None, "upi": None, "links": [], "contradictions": 0
        })
        # persona and persistent internal state
        self.s.setdefault("persona", self.s.get("persona", random.choice(list(PERSONA_STYLE_TEMPLATES.keys()))))
        self.s.setdefault("persona_state", self.s.get("persona_state", random.choice(["busy", "free", "driving", "sleeping", "at_work"])))
        self.s.setdefault("last_question", None)

    def observe(self, msg: str, raw: Optional[dict] = None):
        msg = (msg or "").strip()
        now = time.time()
        # single place to record turns, include redacted raw
        self.s.setdefault("turns", []).append({"text": msg, "raw": raw, "ts": now})
        # extract claims
        n = NAME_RE.search(msg)
        if n:
            self._record_claim("name", n.group(1), msg, now)

        # detect "from <bank name>" patterns even if unknown
        bname = BANK_NAME_RE.search(msg)
        if bname:
            bn = bname.group(1).strip().lower()
            # normalize common tokens
            bn = re.sub(r"\s+bank$", "", bn).strip()
            # store bank claim
            self._record_claim("bank", bn.title(), msg, now)
            # mark unknown bank if not in known list
            if bn not in [x.lower() for x in BANKS]:
                self.s.setdefault("memory", []).append({"type": "unknown_bank", "value": bn, "when": now, "msg": msg})

        # existing BANK_RE matches known banks
        b = BANK_RE.search(msg)
        if b:
            self._record_claim("bank", b.group(1).upper(), msg, now)

        u = UPI_RE.search(msg)
        if u:
            self._record_claim("upi", u.group(0), msg, now)

        p = PHONE_RE.search(msg)
        if p:
            self._record_claim("phone", p.group(0), msg, now)

        for l in detect_links(msg):
            self._record_claim("link", l, msg, now)

        # detect numeric claims next to ticket/complaint words
        lower = msg.lower()
        for kw in TICKET_KEYWORDS:
            if kw in lower:
                m = NUM_RE.search(msg)
                if m:
                    self._record_claim("ticket", m.group(1), msg, now)

        # if message indicates a state (busy/driving/sleeping) update persona_state
        if any(x in lower for x in ["i'm driving", "i'm driving actually", "driving"]):
            self.s["persona_state"] = "driving"
        elif any(x in lower for x in ["i'm at work", "i'm at work right now", "at work"]):
            self.s["persona_state"] = "at_work"
        elif any(x in lower for x in ["i was about to sleep", "i was about to sleep", "going to sleep", "sleep"]):
            self.s["persona_state"] = "sleeping"
        elif any(x in lower for x in ["i just got free", "i just got free", "i'm free now", "i am free"]):
            self.s["persona_state"] = "free"

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
        if any(k in t for k in ["branch", "manager", "customer care", "sir", "madam", "head office"]):
            return "authority"
        if any(k in t for k in ["hello", "hi", "hey"]):
            return "greeting"
        if any(k in t for k in ["ticket", "complaint", "reference", "ref", "complaint id", "ticket number"]):
            return "ticket_info"
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
        if intent == "ticket_info":
            return "probe"
        return random.choice(["probe", "smalltalk", "delay"])

    def _choose_persona_phrase(self, category: str):
        # category = "confusion", "smalltalk", "cooperative", ...
        persona = self.s.get("persona", "confused")
        pool = PERSONA_STYLE_TEMPLATES.get(persona, [])
        # filter pool by category keyword if present
        candidates = [p for p in pool if category in p.lower()] or pool
        if not candidates:
            candidates = pool or ["Okay"]
        return sample_no_repeat(candidates, self.s.setdefault("recent_responses", set()))

    def generate_reply(self, strategy: str, incoming: str):
        recent = self.s.setdefault("recent_responses", set())
        name = self.s["profile"].get("name")
        persona = self.s.get("persona", "confused")
        state = self.s.get("persona_state", "free")

        # If the last question expects a numeric answer, and incoming contains digits, confirm
        if self.s.get("last_question"):
            m = NUM_RE.search(incoming or "")
            if m:
                value = m.group(1)
                q = self.s["last_question"]
                self.s["last_question"] = None
                return f"Got it — the {q} is {value}. Is that correct?"

        if strategy == "probe":
            pool = [
                "Can you send the account number and IFSC or UPI ID clearly?",
                "Where exactly should I transfer? Please share full steps.",
                "Is that a UPI ID or bank transfer? I need exact details.",
                "Can you resend the details (UPI/account/IFSC/ticket)?"
            ]
        elif strategy == "delay":
            # state-aware delay phrasing
            if state in ("busy", "at_work"):
                pool = ["One sec, I'm at work, I'll check my phone in a bit.", "Hold on, I'm busy right now, will check soon."]
            elif state == "driving":
                pool = ["I’m driving, I’ll check once I stop.", "I’ll look into that in a few minutes, driving now."]
            elif state == "sleeping":
                pool = ["I was about to sleep — can we do this later?", "It's late here, I’ll check tomorrow morning."]
            else:
                pool = ["One sec, I need to check my app.", "I’ll do it in a minute, hold on."]
        elif strategy == "challenge":
            pool = [
                "This doesn't match what you said earlier — why the change?",
                "You said something different a moment ago. Please clarify.",
                "I’m getting confused — the details are inconsistent."
            ]
        elif strategy == "smalltalk":
            # pick from persona templates, keep consistent with persona_state
            pool = PERSONA_STYLE_TEMPLATES.get(persona, ["Hmm, okay"])
        elif strategy == "soft_doubt":
            pool = [
                "This sounds a bit unusual, I want to verify on my app.",
                "Can you confirm this is really from the bank? Please provide ID or reference."
            ]
        else:
            pool = ["Okay, I’ll try that.", "Alright, do it then."]

        reply = sample_no_repeat(pool, recent)
        # set last_question if reply asks for something specific
        if any(word in reply.lower() for word in ["ticket", "upi", "account", "ifsc", "account number"]):
            # map to short key for confirmation
            if "ticket" in reply.lower() or "complaint" in reply.lower():
                self.s["last_question"] = "ticket"
            elif "upi" in reply.lower():
                self.s["last_question"] = "upi"
            elif "ifsc" in reply.lower() or "account" in reply.lower():
                self.s["last_question"] = "account"

        # personalization and variable length
        if name and random.random() < 0.28 and strategy != "challenge":
            reply = f"{name}, {reply}"
        if random.random() < 0.22:
            reply = reply + " " + random.choice(["Please be precise.", "I don’t want issues.", "Explain step by step."])
        return reply

    def respond(self, incoming: str, raw: Optional[dict] = None):
        # single entry point: observe, infer, choose, generate
        self.observe(incoming, raw=raw)
        intent = self.detect_intent(incoming)
        strategy = self.choose_strategy(intent)

        # special-case: if incoming contains an OTP/pin request, refuse immediately
        if re.search(r"\b(otp|one time password|pin|password)\b", (incoming or "").lower()):
            reply = random.choice(OTP_WARNINGS)
            strategy = "challenge"
            self.s.setdefault("strategy_history", []).append({"strategy": strategy, "intent": intent, "ts": time.time()})
            return {"reply": reply, "strategy": strategy, "intent": intent, "profile": self.s["profile"], "memory": self.s.get("memory", []), "claims": self.s.get("claims", [])}

        reply = self.generate_reply(strategy, incoming)
        self.s.setdefault("strategy_history", []).append({"strategy": strategy, "intent": intent, "ts": time.time()})
        return {"reply": reply, "strategy": strategy, "intent": intent, "profile": self.s["profile"], "memory": self.s.get("memory", []), "claims": self.s.get("claims", [])}