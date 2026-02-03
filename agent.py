# ============================================================
# AGENT — FINAL MAXED VERSION
# Brain of the honeypot
#
# Guarantees:
# - No exact reply repetition (ever)
# - Consistent human state
# - Scam detection + info extraction
# - Learns from every conversation
# - Strategy adapts over time
# ============================================================

import re
import time
import random
from typing import Dict, Any, Optional

from agent_utils import (
    detect_links,
    UPI_RE,
    PHONE_RE,
    BANK_RE,
    NAME_RE,
    sample_no_repeat_varied,
    _normalize_text,
)

from victim_dataset import (
    FILLERS,
    SMALL_TALK,
    CONFUSION,
    INTRO_ACK,
    BANK_VERIFICATION,
    COOPERATIVE,
    PROBING,
    SOFT_DOUBT,
    RESISTANCE,
    NEAR_FALL,
    FATIGUE,
    EXIT,
    OTP_WARNINGS,
    OTP_PROBES,
    PERSONA_STYLE_TEMPLATES,
    CASUAL_OPENERS,
    SLANGS,
    ABBREVS,
)

from learning_engine import (
    record_reply,
    record_scammer_message,
    feedback_from_turn,
    phrase_score,
    strategy_bias,
)

# ------------------------------------------------------------
# Regex
# ------------------------------------------------------------
NUM_RE = re.compile(r"\b\d{3,}\b")
OTP_RE = re.compile(r"\b(otp|one time password|pin|password)\b", re.I)


# ============================================================
# AGENT CLASS
# ============================================================

class Agent:
    def __init__(self, session: Dict[str, Any]):
        self.s = session

        # ---------- persistent memory ----------
        self.s.setdefault("turns", [])
        self.s.setdefault("profile", {})
        self.s.setdefault("memory", [])
        self.s.setdefault("claims", [])
        self.s.setdefault("recent_responses", set())
        self.s.setdefault("asked_about", set())

        # ---------- persona ----------
        self.s.setdefault("persona", random.choice(list(PERSONA_STYLE_TEMPLATES.keys())))
        self.s.setdefault("persona_state", "free")
        self.s.setdefault("tone_level", 0)  # ramps slowly
        self.s.setdefault("out_count", 0)

    # ========================================================
    # OBSERVE INCOMING MESSAGE
    # ========================================================
    def observe(self, msg: str, raw: Optional[dict] = None):
        msg = (msg or "").strip()
        ts = time.time()

        self.s["turns"].append({
            "direction": "in",
            "text": msg,
            "ts": ts,
        })

        record_scammer_message(msg)

        # ---- extract info ----
        if NAME_RE.search(msg):
            self._claim("name", NAME_RE.search(msg).group(1), msg)

        if BANK_RE.search(msg):
            self._claim("bank", BANK_RE.search(msg).group(1).upper(), msg)

        if PHONE_RE.search(msg):
            self._claim("phone", PHONE_RE.search(msg).group(0), msg)

        if UPI_RE.search(msg):
            self._claim("upi", UPI_RE.search(msg).group(0), msg)

        for link in detect_links(msg):
            self._claim("link", link, msg)

        # ---- persona state inference ----
        lower = msg.lower()
        if "driving" in lower:
            self.s["persona_state"] = "driving"
        elif "at work" in lower:
            self.s["persona_state"] = "at_work"
        elif "sleep" in lower:
            self.s["persona_state"] = "sleeping"

    # ========================================================
    # CLAIM TRACKING (WITH CONTRADICTION DETECTION)
    # ========================================================
    def _claim(self, kind: str, value: str, src: str):
        profile = self.s["profile"]
        prev = profile.get(kind)

        if prev and prev != value:
            self.s["memory"].append({
                "type": "contradiction",
                "field": kind,
                "old": prev,
                "new": value,
                "ts": time.time(),
            })

        profile[kind] = value
        self.s["claims"].append({
            "kind": kind,
            "value": value,
            "src": src,
            "ts": time.time(),
        })

    # ========================================================
    # INTENT DETECTION
    # ========================================================
    def detect_intent(self, msg: str) -> str:
        t = msg.lower()

        if OTP_RE.search(t):
            return "otp"

        if any(k in t for k in ["transfer", "upi", "account", "pay", "credit"]):
            return "extraction"

        if any(k in t for k in ["urgent", "immediately", "blocked", "freeze"]):
            return "urgency"

        if any(k in t for k in ["manager", "officer", "branch", "department"]):
            return "authority"

        if any(k in t for k in ["hello", "hi", "hey"]):
            return "greeting"

        return "neutral"

    # ========================================================
    # STRATEGY SELECTION (SELF-ADJUSTING)
    # ========================================================
    def choose_strategy(self, intent: str) -> str:
        base = {
            "greeting": "smalltalk",
            "neutral": "confusion",
            "authority": "probe",
            "urgency": "delay",
            "extraction": "probe",
            "otp": "otp_probe",
        }.get(intent, "probe")

        bias = strategy_bias(base)
        if bias < -0.5:
            return "challenge"
        if bias > 0.8:
            return "near_fall"

        return base

    # ========================================================
    # REPLY GENERATION
    # ========================================================
    def generate_reply(self, strategy: str, incoming: str) -> str:
        persona = self.s["persona"]
        tone = self.s["tone_level"]
        recent = self.s["recent_responses"]

        # ---- pool selection ----
        pool_map = {
            "smalltalk": CASUAL_OPENERS + SMALL_TALK,
            "confusion": CONFUSION,
            "probe": PROBING,
            "delay": SMALL_TALK,
            "challenge": RESISTANCE,
            "near_fall": NEAR_FALL,
            "fatigue": FATIGUE,
            "exit": EXIT,
            "otp_probe": OTP_PROBES,
        }

        pool = pool_map.get(strategy, PROBING)

        # ---- tone ramping (human pacing) ----
        if tone < 2:
            pool = CASUAL_OPENERS + FILLERS + pool[:4]
        elif tone < 4:
            pool = pool + SOFT_DOUBT
        else:
            pool = pool + RESISTANCE

        # ---- intelligent weighting using learning engine ----
        scored = sorted(
            pool,
            key=lambda p: phrase_score(p),
            reverse=True
        )

        # ---- pick non-repeating reply ----
        reply = sample_no_repeat_varied(
            scored,
            recent,
            session=self.s
        )

        # ---- slang injection ----
        if random.random() < 0.15:
            for k, v in SLANGS.items():
                if k.lower() in reply.lower():
                    reply = re.sub(rf"\b{k}\b", random.choice(v), reply, flags=re.I)

        if random.random() < 0.08:
            reply += " " + random.choice(ABBREVS)

        # ---- state consistency ----
        if strategy == "delay":
            state = self.s["persona_state"]
            if state == "driving":
                reply += " I'm driving rn."
            elif state == "at_work":
                reply += " I'm at work atm."

        # ---- finalize ----
        self.s["tone_level"] = min(6, tone + 1)
        self.s["out_count"] += 1

        self.s["turns"].append({
            "direction": "out",
            "text": reply,
            "ts": time.time(),
        })

        recent.add(_normalize_text(reply))

        # ---- learning feedback ----
        outcome = feedback_from_turn(self.s["turns"][-6:])
        record_reply(reply, outcome)

        return reply

    # ========================================================
    # MAIN ENTRY
    # ========================================================
    def respond(self, incoming: str, raw: Optional[dict] = None) -> Dict[str, Any]:
        self.observe(incoming, raw)

        intent = self.detect_intent(incoming)
        strategy = self.choose_strategy(intent)

        reply = self.generate_reply(strategy, incoming)

        return {
            "reply": reply,
            "strategy": strategy,
            "intent": intent,
            "profile": self.s["profile"],
            "memory": self.s["memory"][-10:],
            "claims": self.s["claims"][-10:],
        }
