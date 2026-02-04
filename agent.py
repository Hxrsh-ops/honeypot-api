# ============================================================
# agent.py - LLM-first honeypot agent
# ============================================================

from typing import Dict, Any, List, Optional
import random
import logging
import re
import os
import time

from agent_utils import (
    normalize_text,
    scam_signal_score,
    redact_sensitive,
    URL_RE,
    UPI_RE,
    PHONE_RE,
    BANK_RE,
    NAME_RE,
)
from memory_manager import MemoryManager
from llm_adapter import generate_structured_reply, llm_available

logger = logging.getLogger("agent")
logging.basicConfig(level=logging.INFO)

# ----------------------------
# Constants / Regex
# ----------------------------
DEFAULT_REPLY = "ok"
LLM_USAGE_PROB = float(os.getenv("LLM_USAGE_PROB", "1.0"))

OTP_RE = re.compile(r"\b(otp|one[-\s]?time\s?password|verification\s?code)\b", re.I)
URGENT_RE = re.compile(r"\b(urgent|immediate|within|expire|freez|frozen|blocked|suspend|suspension)\b", re.I)
AUTH_RE = re.compile(r"\b(bank|rbi|world\s?bank|sbi|hdfc|icici|axis|fraud|security|official|manager)\b", re.I)
PAY_RE = re.compile(r"\b(upi|transfer|pay|payment|refund|charge|fee|ifsc|beneficiary|amount|transaction)\b", re.I)
ACCOUNT_REQ_RE = re.compile(r"\b(account number|a/c|acct|account)\b", re.I)
THREAT_RE = re.compile(r"\b(block|freeze|legal|police|case|report|fine|penalty|court)\b", re.I)

ASK_PROFILE_RE = re.compile(r"(tell me my name|what'?s my name|what is my name|my name and branch|tell me my branch|my branch name)", re.I)
MEMORY_ASK_RE = re.compile(r"(what did i (say|tell) (you|u)|what i said before|do you remember|repeat what i said|what did i tell you|what i told you)", re.I)
TOLD_YOU_RE = re.compile(r"(i told you|already told you|told you before).*(name|branch)", re.I)
BOT_ACCUSATION_RE = re.compile(r"\b(you are a bot|youre a bot|u are a bot|bot)\b", re.I)
CONFUSED_RE = re.compile(r"\b(confused|huh|what\?)\b", re.I)

LEGIT_STATEMENT_RE = re.compile(r"(statement is ready|monthly statement|e-statement|no action needed)", re.I)
TRANSACTION_ALERT_RE = re.compile(r"(transaction of|debited|credited|if not initiated)", re.I)
SOCIAL_IMPERSONATION_RE = re.compile(r"\b(mom|dad|mother|father|cousin|bro|brother|sis|sister|uncle|aunt|aunty|wife|husband|son|daughter|boss|manager|colleague|friend)\b", re.I)
JOB_SCAM_RE = re.compile(r"(job offer|offer letter|training fee|placement fee)", re.I)
PARCEL_SCAM_RE = re.compile(r"(parcel|delivery|courier|re-delivery|customs fee|delivery fee)", re.I)

SMALLTALK_RE = re.compile(r"\b(hi|hello|hey|how are you|what's up|whats up|sup|good morning|good night|good evening)\b", re.I)
THANKS_RE = re.compile(r"\b(thanks|thank you|thx|ty)\b", re.I)


class Agent:
    def __init__(self, session: Dict[str, Any]):
        self.s = session
        self.s.setdefault("flags", {})
        self.s["flags"].setdefault("repeat_count", 0)
        self.s["flags"].setdefault("otp_ask_count", 0)
        self.s["flags"].setdefault("bot_accused", False)

        self.memory = MemoryManager(self.s)
        self.s.setdefault("recent_responses", [])
        self.s.setdefault("recent_texts", [])

    # ----------------------------
    # Compatibility helpers (tests)
    # ----------------------------
    def observe(self, incoming: str):
        text = incoming or ""
        # suspicious IFSC or employee id
        if "ifsc" in text.lower() and not re.search(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", text or ""):
            self.memory.add_event({"type": "suspicious_ifsc", "value": text, "ts": time.time()})
        if re.search(r"\b\d{12,}\b", text or "") and ("id" in text.lower() or "employee" in text.lower()):
            self.memory.add_event({"type": "suspicious_emp_id", "value": text, "ts": time.time()})
        self.memory.merge_extractions(self.memory.extract_from_text(text), source="regex")
        return True

    def generate_reply(self, strategy: str, incoming: str):
        if strategy == "delay":
            persona = self.s.get("memory_state", {}).get("persona", {})
            state = persona.get("state", "")
            if state == "at_work" or self.s.get("persona_state") == "at_work":
                return "im at work, will check later"
            return "im busy rn, will check later"
        out = self.respond(incoming)
        reply = out.get("reply") if isinstance(out, dict) else out
        if strategy == "probe":
            tokens = ["hmm", "hey", "one sec", "ok", "oh", "hi", "lemme", "hold on"]
            if reply and not any(t in reply.lower() for t in tokens) and len(reply.split()) >= 6:
                reply = f"hmm {reply}"
        return reply

    # ----------------------------
    # Signals / Intent Routing
    # ----------------------------
    def _detect_signals(self, text: str) -> Dict[str, bool]:
        lower = (text or "").lower()
        return {
            "otp": bool(OTP_RE.search(lower)),
            "payment": bool(UPI_RE.search(text) or PAY_RE.search(lower)),
            "account_request": bool(ACCOUNT_REQ_RE.search(lower)),
            "link": bool(URL_RE.search(text)),
            "authority": bool(AUTH_RE.search(lower)),
            "urgency": bool(URGENT_RE.search(lower)),
            "threat": bool(THREAT_RE.search(lower)),
            "memory_probe": bool(MEMORY_ASK_RE.search(lower)),
            "ask_profile": bool(ASK_PROFILE_RE.search(lower)),
            "told_you": bool(TOLD_YOU_RE.search(lower)),
            "bot_accusation": bool(BOT_ACCUSATION_RE.search(lower)),
            "confused": bool(CONFUSED_RE.search(lower)),
            "legit_statement": bool(LEGIT_STATEMENT_RE.search(text or "")),
            "transaction_alert": bool(TRANSACTION_ALERT_RE.search(text or "")),
            "social_impersonation": bool(SOCIAL_IMPERSONATION_RE.search(lower)),
            "job_scam": bool(JOB_SCAM_RE.search(text or "")),
            "parcel_scam": bool(PARCEL_SCAM_RE.search(text or "")),
            "smalltalk": bool(SMALLTALK_RE.search(lower)),
            "thanks": bool(THANKS_RE.search(lower)),
        }

    def _intent_hint(self, signals: Dict[str, bool]) -> str:
        if signals.get("bot_accusation"):
            return "bot_accusation"
        if signals.get("transaction_alert"):
            return "legit_transaction"
        if signals.get("legit_statement"):
            return "legit_statement"
        if signals.get("social_impersonation"):
            return "social_impersonation"
        if signals.get("job_scam"):
            return "job_scam"
        if signals.get("parcel_scam"):
            return "parcel_scam"
        if signals.get("smalltalk") and not any([signals.get("urgency"), signals.get("payment"), signals.get("link"), signals.get("authority")]):
            return "smalltalk"
        return "scam_pressure" if any([signals.get("otp"), signals.get("payment"), signals.get("link"), signals.get("authority"), signals.get("urgency"), signals.get("threat")]) else "general"

    # ----------------------------
    # Guardrails / Fallback
    # ----------------------------
    def _guardrails(self, reply: str) -> str:
        if not reply:
            return DEFAULT_REPLY
        # never admit bot
        lowered = reply.lower()
        if "i am a bot" in lowered or "i'm a bot" in lowered:
            reply = re.sub(r"i\s*('?m| am)\s*a\s*bot", "i'm not a bot", reply, flags=re.I)
        # redact sensitive
        reply = redact_sensitive(reply)
        # keep short-ish
        reply = reply.strip()
        if len(reply) > 200:
            reply = reply[:200]
        return reply

    def _unique_reply(self, reply: str) -> str:
        if not reply:
            return DEFAULT_REPLY
        recent = self.s.get("recent_responses", [])
        norm = normalize_text(reply)
        if norm in recent:
            reply = f"{reply} {random.choice(['ok','hmm','pls'])}"
        # length variation for tests/human feel
        if len(reply) < 40 and random.random() < 0.3:
            reply = f"{reply} {random.choice(['explain properly', 'not sure', 'be clear'])}"
        recent.append(norm)
        self.s["recent_responses"] = recent[-200:]
        return reply

    def _fallback_reply(self, incoming: str, signals: Dict[str, bool]) -> str:
        lower = (incoming or "").lower()

        if signals.get("bot_accusation"):
            return "nah, just tell me properly"
        if signals.get("ask_profile"):
            return self.memory.answer_profile_question()
        if signals.get("memory_probe"):
            return self.memory.answer_memory_question()
        if signals.get("told_you"):
            return "you told me your name, not the branch"
        if signals.get("transaction_alert"):
            return "if it's not me i'll call the bank now"
        if signals.get("legit_statement"):
            return "noted, i'll check later"
        if signals.get("social_impersonation"):
            return "call me, this number feels off"
        if signals.get("otp"):
            return "otp is private, not sharing"
        if signals.get("payment") or signals.get("account_request"):
            return "not sharing account details on text"
        if "ifsc" in lower or "id" in lower or "employee" in lower:
            return "send official id or ifsc, then i'll verify"
        if signals.get("link"):
            return "link looks fake, send official site"
        if signals.get("confused"):
            return "same, explain properly"

        if signals.get("smalltalk"):
            return "hey, what's this about"
        if signals.get("thanks"):
            return "ok"

        # generic fallback
        return random.choice([
            "this feels off, explain clearly",
            "not sure about this, explain properly",
            "hmm, this is odd, explain",
        ])

    # ----------------------------
    # Main response
    # ----------------------------
    def respond(self, incoming: str, raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        incoming = str(incoming or "")
        self.memory.add_user_message(incoming)

        # update regex extractions
        regex_extractions = self.memory.extract_from_text(incoming)
        self.memory.merge_extractions(regex_extractions, source="regex")

        signals = self._detect_signals(incoming)
        intent_hint = self._intent_hint(signals)

        if signals.get("otp"):
            self.s["flags"]["otp_ask_count"] = self.s["flags"].get("otp_ask_count", 0) + 1

        # bot accusation flag
        if signals.get("bot_accusation"):
            self.s["flags"]["bot_accused"] = True

        # deterministic memory/profile answers
        if signals.get("ask_profile"):
            reply = self.memory.answer_profile_question()
            reply = self._unique_reply(self._guardrails(reply))
            self.memory.add_bot_message(reply)
            self.memory.update_summary(incoming, reply)
            return self._build_response(reply, incoming, signals, intent_hint, llm_used=False)

        if signals.get("memory_probe"):
            reply = self.memory.answer_memory_question()
            reply = self._unique_reply(self._guardrails(reply))
            self.memory.add_bot_message(reply)
            self.memory.update_summary(incoming, reply)
            return self._build_response(reply, incoming, signals, intent_hint, llm_used=False)

        if signals.get("told_you"):
            reply = "you told me your name, not the branch"
            reply = self._unique_reply(self._guardrails(reply))
            self.memory.add_bot_message(reply)
            self.memory.update_summary(incoming, reply)
            return self._build_response(reply, incoming, signals, intent_hint, llm_used=False)

        # LLM-first
        llm_used = False
        reply = None
        llm_out = None

        if llm_available() and random.random() < LLM_USAGE_PROB:
            context = {
                "incoming": incoming,
                "intent_hint": intent_hint,
                "signals": signals,
                "facts": self.s.get("memory_state", {}).get("facts", {}),
                "claims": self.s.get("memory_state", {}).get("claims", {}),
                "contradictions": self.s.get("memory_state", {}).get("contradictions", []),
                "session_summary": self.s.get("memory_state", {}).get("session_summary", ""),
                "persona": self.s.get("memory_state", {}).get("persona", {}),
                "last_user_messages": self.s.get("memory_state", {}).get("last_user_messages", []),
                "last_bot_messages": self.s.get("memory_state", {}).get("last_bot_messages", []),
            }
            llm_out = generate_structured_reply(context)

        if llm_out and isinstance(llm_out, dict):
            reply = llm_out.get("reply")
            llm_used = True
            extractions = llm_out.get("extractions") or {}
            self.memory.merge_extractions(extractions, source="llm")

            # update persona / summary
            mood_delta = llm_out.get("mood_delta", 0.0) or 0.0
            self.memory.update_persona(mood_delta)
            summary = llm_out.get("session_summary")
            if summary:
                self.s["memory_state"]["session_summary"] = str(summary)[:240]
            else:
                self.memory.update_summary(incoming, reply or "")

            follow = llm_out.get("follow_up_question")
            if follow and reply and len(reply) < 140 and follow.lower() not in reply.lower():
                reply = f"{reply} {follow}".strip()

        if not reply:
            reply = self._fallback_reply(incoming, signals)

        reply = self._unique_reply(self._guardrails(reply))
        self.memory.add_bot_message(reply)
        self.memory.update_summary(incoming, reply)

        return self._build_response(reply, incoming, signals, intent_hint, llm_used=llm_used)

    # ----------------------------
    # Response builder
    # ----------------------------
    def _build_response(self, reply: str, incoming: str, signals: Dict[str, bool], intent: str, llm_used: bool) -> Dict[str, Any]:
        score = scam_signal_score(incoming)
        # boost by signals on incoming (more accurate)
        if signals.get("authority"):
            score += 0.2
        if signals.get("threat") or signals.get("urgency"):
            score += 0.3
        if signals.get("legit_statement"):
            score = max(0.0, score - 1.5)
        elif signals.get("transaction_alert"):
            score = max(0.0, score - 0.5)
        score = min(score, 5.0)
        is_scam = score >= 2.5
        legit_score = max(0.0, 1 - (score / 5.0))

        return {
            "reply": reply,
            "strategy": intent,
            "signals": signals,
            "extracted_profile": self.s.get("extracted_profile", {}),
            "claims": self.s.get("claims", {}),
            "memory": self.s.get("memory", []),
            "intent": intent,
            "scam_score": score,
            "legit_score": legit_score,
            "is_scam": is_scam,
            "llm_used": llm_used,
            "persona_state": self.s.get("memory_state", {}).get("persona", {}),
            "session_summary": self.s.get("memory_state", {}).get("session_summary", ""),
        }
