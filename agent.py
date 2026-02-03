# ============================================================
# agent.py - Human-Like Honeypot Agent (Reactive + Safe)
# ============================================================

from typing import Dict, Any, List, Optional
import random
import logging
import re
import time
import os

try:
    import victim_dataset as vd
except Exception:
    vd = None

try:
    from learning_engine import LearningEngine
except Exception:
    LearningEngine = None

try:
    from llm_adapter import rephrase_with_llm
except Exception:
    rephrase_with_llm = None

from agent_utils import (
    sample_no_repeat_varied,
    normalize_text,
    fingerprint_text,
    scam_signal_score,
    detect_links,
    redact_sensitive,
    URL_RE,
    UPI_RE,
    PHONE_RE,
    BANK_RE,
    NAME_RE,
)

logger = logging.getLogger("agent")
logging.basicConfig(level=logging.INFO)

# ----------------------------
# Constants
# ----------------------------
REPEAT_AVOIDANCE_LIMIT = 8
MAX_PHASES_PER_MESSAGE = 4
DEFAULT_REPLY = "ok"
LLM_USAGE_PROB = float(os.getenv("LLM_USAGE_PROB", "0.10"))

OTP_RE = re.compile(r"\b(otp|one[-\s]?time\s?password|verification\s?code)\b", re.I)
URGENT_RE = re.compile(r"\b(urgent|immediate|within|expire|freez|frozen|blocked|suspend|suspension)\b", re.I)
AUTH_RE = re.compile(r"\b(bank|rbi|world\s?bank|sbi|hdfc|icici|axis|fraud|security|official|manager)\b", re.I)
PAY_RE = re.compile(r"\b(upi|transfer|pay|payment|refund|charge|fee|ifsc|account|beneficiary)\b", re.I)
THREAT_RE = re.compile(r"\b(block|freeze|legal|police|case|report|fine|penalty|court)\b", re.I)
EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
MEMORY_ASK_RE = re.compile(r"(what did i (say|tell) (you|u)|what i said before|do you remember|repeat what i said|what did i tell you|what i told you)", re.I)
REPEAT_COMPLAINT_RE = re.compile(r"(already told you|told you already|how many times|keep asking|repeat myself|you keep asking)", re.I)
PUNCT_COMPLAINT_RE = re.compile(r"(question mark|qn mark|\?\s*all the time|why .* \?)", re.I)
IDENTITY_CLAIM_RE = re.compile(r"\b(i am|this is|i'm)\b", re.I)
BANK_CLAIM_RE = re.compile(r"\bbank\b", re.I)
LEGIT_ALERT_RE = re.compile(r"(transaction of|debited|credited|statement is ready|if not initiated|call (us|bank))", re.I)
SOCIAL_IMPERSONATION_RE = re.compile(r"\b(mom|dad|mother|father|cousin|bro|brother|sis|sister|uncle|aunt|aunty|wife|husband|son|daughter|boss|manager|colleague|friend)\b", re.I)

CASUAL_PREFIX = [
    "hmm",
    "hey",
    "ok",
    "oh",
    "hi",
    "one sec",
    "hold on",
    "lemme see",
]

OTP_WARNINGS = [
    "i dont share otp",
    "otp is private, not sharing",
    "no otp. i'll call the bank",
    "cant share verification code",
    "otp stays with me",
]

OTP_PROBES = [
    "why otp? bank never asks that",
    "otp for what? send official email",
    "not sharing otp, verify another way",
]

ESCALATION_PROBES = [
    "this is getting suspicious, give official email",
    "send branch number, i'll call",
    "need your official ticket id",
    "which branch? give phone",
    "email from official domain first",
]

DELAY_AT_WORK = [
    "im at work, will check later",
    "busy at work rn",
    "cant talk, at work",
    "at work, text later",
    "im working, give me time",
]

DELAY_GENERIC = [
    "im busy rn",
    "i will check later",
    "cant do this now",
    "give me some time",
    "will get back",
]

EXIT_LINES = [
    "stop messaging me",
    "im done, bye",
    "dont contact again",
    "i will report this",
]


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _safe_list(x):
    return x if isinstance(x, list) else []


class Agent:
    def __init__(self, session: Dict[str, Any]):
        self.s = session
        self.s.setdefault("recent_responses", [])
        self.s.setdefault("recent_texts", [])
        self.s.setdefault("recent_incoming", [])
        self.s.setdefault("recent_incoming_texts", [])
        self.s.setdefault("phase_history", [])
        self.s.setdefault("outgoing_count", 0)
        self.s.setdefault("flags", {})
        self.s["flags"].setdefault("otp_ask_count", 0)
        self.s["flags"].setdefault("repeat_count", 0)
        self.s["flags"].setdefault("punct_complaint", False)
        self.s["flags"].setdefault("asked_identity", False)
        self.s.setdefault("memory", [])
        self.s.setdefault("claims", {})
        self.s.setdefault("extracted_profile", {
            "name": None,
            "bank": None,
            "phone": None,
            "upi": None,
            "ifsc": None,
            "account": None,
            "email": None,
            "url": None,
            "employee_id": None,
            "branch": None,
        })
        self.s.setdefault("persona_state", random.choice(["at_work", "at_home", "on_break"]))
        self.s.setdefault("mood_score", 0.0)

        # normalize legacy types
        if isinstance(self.s.get("recent_responses"), set):
            self.s["recent_responses"] = list(self.s.get("recent_responses"))
        if isinstance(self.s.get("recent_texts"), set):
            self.s["recent_texts"] = list(self.s.get("recent_texts"))

        self.learner = LearningEngine(self.s) if LearningEngine else None

    # --------------------------------------------------------
    # Observation / Memory
    # --------------------------------------------------------
    def observe(self, incoming: str):
        text = incoming or ""
        self._track_repetition(text)
        self._record_incoming(text)

        signals = self._detect_signals(text)

        # OTP tracking
        if signals.get("otp"):
            self.s["flags"]["otp_ask_count"] += 1
        if signals.get("punct_complaint"):
            self.s["flags"]["punct_complaint"] = True

        # mood drift
        mood = self.s.get("mood_score", 0.0)
        if signals.get("threat") or signals.get("urgency"):
            mood += 0.6
        if signals.get("authority"):
            mood += 0.3
        if signals.get("repetition"):
            mood += 0.8
        mood -= 0.1
        self.s["mood_score"] = _clamp(mood, 0.0, 4.0)

        # extraction + contradictions
        extracted, memory_events = self._extract_entities(text)
        self._update_profile_and_claims(extracted, memory_events)
        if any(ev.get("type") == "contradiction" for ev in memory_events):
            signals["contradiction"] = True

        return signals

    def _track_repetition(self, text: str):
        fp = fingerprint_text(text)
        recent_in = self.s.get("recent_incoming", [])
        if recent_in and recent_in[-1] == fp:
            self.s["flags"]["repeat_count"] += 1
        else:
            self.s["flags"]["repeat_count"] = 0
        recent_in.append(fp)
        if len(recent_in) > 50:
            recent_in.pop(0)

    def _record_incoming(self, text: str):
        recent_texts = self.s.get("recent_incoming_texts", [])
        recent_texts.append(text)
        if len(recent_texts) > 30:
            recent_texts.pop(0)
        self.s["recent_incoming_texts"] = recent_texts

    # --------------------------------------------------------
    # Signal Detection
    # --------------------------------------------------------
    def _detect_signals(self, text: str) -> Dict[str, bool]:
        lower = (text or "").lower()
        return {
            "otp": bool(OTP_RE.search(lower)),
            "payment": bool(UPI_RE.search(text) or PAY_RE.search(lower)),
            "link": bool(URL_RE.search(text) or "link" in lower),
            "authority": bool(AUTH_RE.search(lower)),
            "urgency": bool(URGENT_RE.search(lower)),
            "threat": bool(THREAT_RE.search(lower)),
            "repetition": self.s.get("flags", {}).get("repeat_count", 0) >= 1,
            "contradiction": False,
            "memory_probe": bool(MEMORY_ASK_RE.search(lower)),
            "repeat_complaint": bool(REPEAT_COMPLAINT_RE.search(lower)),
            "punct_complaint": bool(PUNCT_COMPLAINT_RE.search(lower)),
            "identity_claim": bool(IDENTITY_CLAIM_RE.search(lower)),
            "bank_claim": bool(BANK_CLAIM_RE.search(lower)),
            "social_impersonation": bool(SOCIAL_IMPERSONATION_RE.search(lower)),
        }

    # --------------------------------------------------------
    # Entity Extraction
    # --------------------------------------------------------
    def _extract_entities(self, text: str):
        extracted: Dict[str, Any] = {}
        memory_events: List[Dict[str, Any]] = []
        lower = (text or "").lower()

        # name
        m = NAME_RE.search(text or "")
        if m:
            extracted["name"] = m.group(1).strip()

        # bank
        mb = BANK_RE.search(text or "")
        if mb:
            extracted["bank"] = mb.group(1).lower()

        # phone
        mp = PHONE_RE.search(text or "")
        if mp:
            extracted["phone"] = mp.group(0)

        # upi
        mu = UPI_RE.search(text or "")
        if mu:
            extracted["upi"] = mu.group(0)

        # urls
        links = detect_links(text or "")
        if links:
            extracted["url"] = links[0]

        # email
        me = EMAIL_RE.search(text or "")
        if me:
            extracted["email"] = me.group(0)

        # ifsc
        if "ifsc" in lower:
            mi = IFSC_RE.search(text or "")
            if mi:
                extracted["ifsc"] = mi.group(0)
            else:
                memory_events.append({
                    "type": "suspicious_ifsc",
                    "value": text,
                    "ts": time.time(),
                })

        # employee id / suspicious long numeric id
        long_num = re.search(r"\b\d{12,}\b", text or "")
        if long_num and ("id" in lower or "employee" in lower):
            extracted["employee_id"] = long_num.group(0)
            memory_events.append({
                "type": "suspicious_emp_id",
                "value": long_num.group(0),
                "ts": time.time(),
            })

        # account number (if explicitly mentioned)
        if "account" in lower or "a/c" in lower:
            acct = re.search(r"\b\d{8,18}\b", text or "")
            if acct:
                extracted["account"] = acct.group(0)

        # branch hints
        if "branch" in lower:
            extracted["branch"] = "mentioned"

        return extracted, memory_events

    def _update_profile_and_claims(self, extracted: Dict[str, Any], memory_events: List[Dict[str, Any]]):
        profile = self.s.get("extracted_profile", {})
        claims = self.s.get("claims", {})

        for k, v in extracted.items():
            if not v:
                continue
            prev = claims.get(k)
            if prev and prev != v:
                memory_events.append({
                    "type": "contradiction",
                    "field": k,
                    "prev": prev,
                    "new": v,
                    "ts": time.time(),
                })
            claims[k] = v
            if not profile.get(k):
                profile[k] = v

        if memory_events:
            mem = self.s.get("memory", [])
            for ev in memory_events:
                mem.append(ev)
            if len(mem) > 200:
                self.s["memory"] = mem[-200:]

    def _memory_reply(self) -> str:
        """
        Short recall of the last incoming message.
        """
        history = self.s.get("recent_incoming_texts", [])
        if len(history) < 2:
            return "not sure, say it again"
        prev = history[-2]
        if not prev:
            return "dont remember, repeat pls"

        # try to summarize by entities
        lower = prev.lower()
        if "bank" in lower:
            mb = BANK_RE.search(prev)
            if mb:
                return f"you said you're from {mb.group(1)} bank"
            return "you said you're from some bank"
        if "freeze" in lower or "blocked" in lower:
            return "you said account will freeze"
        if "otp" in lower:
            return "you asked for otp"
        if "link" in lower:
            return "you sent a link"

        # fallback to short snippet
        words = prev.split()
        snippet = " ".join(words[:7])
        if len(words) > 7:
            snippet += "..."
        return f"you said '{snippet}'"

    def _reactive_override(self, incoming: str, signals: Dict[str, bool]) -> Optional[str]:
        """
        Short, highly reactive replies that anchor to the incoming text.
        """
        lower = (incoming or "").lower()

        if "dont you trust me" in lower or "don't you trust me" in lower:
            return "trust needs proof, not pressure"
        if "why are you stalling" in lower or "why are you stalling?" in lower:
            return "because you keep rushing me"
        if "wht" in lower or lower.strip() in ("what", "wht", "what?"):
            return "you messaged me, so explain properly"
        if "you didnt tell me anything" in lower or "you didn't tell me anything" in lower:
            return "exactly, you jumped to threat without details"

        if signals.get("urgency") or "freeze" in lower or "blocked" in lower:
            return random.choice([
                "why no sms then",
                "stop rushing and explain properly",
                "if it's frozen how are you messaging",
            ])

        if signals.get("identity_claim") or "i am from" in lower:
            return random.choice([
                "which bank exactly, branch and city?",
                "official email and employee id?",
                "name and branch? then i'll verify",
            ])

        if signals.get("payment") and "upi" in lower:
            return random.choice([
                "why need my upi, this sounds off",
                "share official email first",
                "upi not needed for verification",
            ])

        if signals.get("link"):
            return random.choice([
                "link looks fake, send official website",
                "not clicking links, give official email",
                "why a random link?",
            ])

        if signals.get("social_impersonation"):
            if "boss" in lower or "manager" in lower:
                return random.choice([
                    "which project? also call me, why text",
                    "if you're my boss, tell me the deadline",
                    "call me from office line, not this",
                ])
            return random.choice([
                "call me, this number feels off",
                "what's our last chat about?",
                "send a voice note so i know it's you",
            ])

        return None

    # --------------------------------------------------------
    # Phase Selection
    # --------------------------------------------------------
    def _select_phases(self, incoming: str, signals: Dict[str, bool], strategy: str) -> List[str]:
        phases: List[str] = []
        last_phases = self.s.get("phase_history", [])
        last_phases = last_phases[-1] if last_phases else []

        if self.s.get("outgoing_count", 0) == 0:
            phases.append("casual_entry")

        if strategy == "delay":
            phases.extend(["delay_tactics", "cooldown_state"])
        elif strategy == "exit":
            phases.extend(["final_exit", "post_exit"])
        elif strategy == "resist":
            phases.extend(["resistance", "logic_doubt"])
        else:
            if signals.get("authority"):
                if not self.s["flags"].get("asked_identity"):
                    phases.append("probing_identity")
                    phases.append("probing_bank")
            if signals.get("identity_claim") or signals.get("bank_claim"):
                if not self.s["flags"].get("asked_identity"):
                    phases.append("probing_identity")
                    phases.append("probing_bank")
            if signals.get("payment"):
                phases.append("probing_payment")
            if signals.get("link"):
                phases.append("probing_links")
            if signals.get("urgency"):
                phases.append("time_pressure")
            if signals.get("repetition"):
                phases.append("annoyance")
            if self.s.get("outgoing_count", 0) > 2:
                phases.append("soft_doubt")

        # fallback to confusion/probe if still empty
        if not phases:
            phases.extend(["confusion", "probing_process"])

        # de-dup and trim
        phases = list(dict.fromkeys(phases))[:MAX_PHASES_PER_MESSAGE]

        # avoid repeating the exact same phase set when no new signals
        if last_phases and phases == last_phases:
            if "casual_entry" in phases:
                phases = [p for p in phases if p != "casual_entry"]
            if "probing_identity" in phases and "probing_identity" in last_phases:
                phases = [p for p in phases if p != "probing_identity"]
            if not phases:
                phases = ["logic_doubt", "verification_loop"]

        # ensure at least 2 phases if possible
        if len(phases) == 1 and vd and vd.BASE_POOLS:
            phases.append("light_confusion")

        return phases[:MAX_PHASES_PER_MESSAGE]

    # --------------------------------------------------------
    # Message Composition
    # --------------------------------------------------------
    def _compose_from_phases(self, phases: List[str]) -> str:
        if not vd:
            return DEFAULT_REPLY

        # length bucket (ensure variation across turns)
        turn = self.s.get("outgoing_count", 0)
        if turn % 5 == 0:
            target_parts = 1
        elif turn % 5 == 1:
            target_parts = 2
        else:
            bucket = random.random()
            if bucket < 0.35:
                target_parts = 1
            elif bucket < 0.8:
                target_parts = 2
            else:
                target_parts = 3

        parts: List[str] = []
        for phase in phases:
            pool = vd.BASE_POOLS.get(phase, [])
            if not pool:
                continue
            part = sample_no_repeat_varied(
                pool,
                self.s.get("recent_responses", []),
                session=self.s,
                rephrase_hook=None
            )
            if part:
                parts.append(part)
            if len(parts) >= target_parts:
                break

        if not parts:
            return DEFAULT_REPLY

        # join in human-ish style
        if len(parts) == 1:
            message = parts[0]
        else:
            if random.random() < 0.3:
                message = "\n".join(parts)
            else:
                message = " ".join(parts)

        return message.strip()

    # --------------------------------------------------------
    # Style Scrubber
    # --------------------------------------------------------
    def _style_scrubber(self, text: str) -> str:
        if not text:
            return DEFAULT_REPLY
        t = text.strip()

        # lower + soften
        t = t.replace("Please", "pls")
        t = t.replace("please", "pls")
        t = t.replace("kindly", "")
        t = t.replace("Kindly", "")
        t = t.replace(" do not ", " dont ")
        t = t.replace("cannot", "cant")
        t = t.lower()
        t = re.sub(r"\s+", " ", t).strip()

        # reduce question marks after complaints
        if self.s.get("flags", {}).get("punct_complaint"):
            t = t.replace("?", "")
        elif t.count("?") > 1:
            # keep at most one question mark
            parts = t.split("?")
            t = "?".join(parts[:2]).strip()

        # add casual prefix sometimes
        if random.random() < 0.25 and not t.startswith(tuple(CASUAL_PREFIX)):
            t = f"{random.choice(CASUAL_PREFIX)} {t}"

        # shorten overly long replies
        if len(t) > 140:
            cut = t[:140]
            if "." in cut:
                cut = cut.split(".", 1)[0]
            t = cut.strip()

        return t.strip()

    # --------------------------------------------------------
    # Strategy-Based Reply
    # --------------------------------------------------------
    def generate_reply(self, strategy: str, incoming: str, from_respond: bool = False) -> str:
        if not from_respond:
            self._track_repetition(incoming)
            self._record_incoming(incoming)
        signals = self._detect_signals(incoming)

        # legit statement handling
        if LEGIT_ALERT_RE.search(incoming or ""):
            reply = random.choice([
                "ok thanks, i'll check the app",
                "noted, i'll verify and call bank if needed",
                "ok, i'll check my statement later",
            ])
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["polite_engagement"], "legit", signals)

        # OTP refusal after first request
        if signals.get("otp") and self.s["flags"].get("otp_ask_count", 0) == 1:
            reply = random.choice(OTP_PROBES)
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["probing_identity"], "otp_probe", signals)

        if signals.get("otp") and self.s["flags"].get("otp_ask_count", 0) >= 2:
            reply = random.choice(OTP_WARNINGS)
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["strong_resistance"], strategy, signals)

        # memory probe (what did I say before?)
        if signals.get("memory_probe"):
            reply = self._memory_reply()
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["verification_loop"], "memory", signals)

        # repeat complaint -> annoyance + clarify
        if signals.get("repeat_complaint"):
            reply = random.choice([
                "you already said it, why repeating",
                "i heard you, stop repeating",
                "why keep saying same thing",
                "you said it already, explain properly",
            ])
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["annoyance", "fatigue"], "annoyed", signals)

        # punctuation complaint
        if signals.get("punct_complaint"):
            reply = random.choice([
                "ok ok no more question marks",
                "fine, i will type normal",
                "ok chill, tell me properly",
            ])
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["cooldown_state"], "calm", signals)

        # direct reactive override
        override = self._reactive_override(incoming, signals)
        if override:
            reply = self._style_scrubber(override)
            return self._finalize_reply(reply, ["logic_doubt", "probing_process"], "react", signals)

        if strategy == "delay":
            if self.s.get("persona_state") == "at_work":
                reply = random.choice(DELAY_AT_WORK)
            else:
                reply = random.choice(DELAY_GENERIC)
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["delay_tactics"], strategy, signals)

        if strategy == "exit":
            reply = random.choice(EXIT_LINES)
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["final_exit"], strategy, signals)

        # escalation on repeated pressure
        if self.s["flags"].get("repeat_count", 0) >= 4:
            reply = random.choice(ESCALATION_PROBES)
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["annoyance", "probing_identity"], strategy, signals)

        phases = self._select_phases(incoming, signals, strategy)
        reply = self._compose_from_phases(phases)

        # ensure probing replies include id/ifsc when asked
        lower = (incoming or "").lower()
        if ("ifsc" in lower or "id" in lower) and strategy == "probe":
            if not any(k in reply.lower() for k in ["id", "ifsc", "email", "branch", "call"]):
                reply = f"{reply} send ifsc or official id"

        reply = self._style_scrubber(reply)

        # first reply should feel casual
        if self.s.get("outgoing_count", 0) == 0 and strategy == "probe":
            if not any(x in reply.split()[:2] for x in ["hmm", "hey", "ok", "oh", "hi", "lemme"]):
                reply = f"{random.choice(CASUAL_PREFIX)} {reply}"

        return self._finalize_reply(reply, phases, strategy, signals)

    # --------------------------------------------------------
    # Finalize Reply (no repeats + optional rephrase)
    # --------------------------------------------------------
    def _finalize_reply(self, reply: str, phases: List[str], strategy: str, signals: Dict[str, bool]) -> str:
        recent_texts = self.s.get("recent_texts", [])
        recent_norms = self.s.get("recent_responses", [])

        attempts = 0
        candidate = reply
        while attempts < REPEAT_AVOIDANCE_LIMIT:
            norm = normalize_text(candidate)
            if candidate not in recent_texts and norm not in recent_norms:
                break
            # recompose
            candidate = self._compose_from_phases(phases)
            candidate = self._style_scrubber(candidate)
            attempts += 1

        # last-resort uniqueness guard
        norm = normalize_text(candidate)
        if candidate in recent_texts or norm in recent_norms:
            candidate = f"{candidate} {random.choice(['ok?', 'hmm', 'pls', '...'])}"

        # optional LLM rephrase (low probability)
        if rephrase_with_llm and random.random() < LLM_USAGE_PROB:
            out = rephrase_with_llm(candidate)
            if out:
                candidate = self._style_scrubber(out)

        # track recent
        recent_texts.append(candidate)
        recent_norms.append(normalize_text(candidate))
        if len(recent_texts) > 200:
            self.s["recent_texts"] = recent_texts[-200:]
        if len(recent_norms) > 500:
            self.s["recent_responses"] = recent_norms[-500:]

        self.s["phase_history"].append(phases)
        self.s["outgoing_count"] += 1
        if "probing_identity" in phases or "who are you" in candidate.lower():
            self.s["flags"]["asked_identity"] = True

        return candidate

    # --------------------------------------------------------
    # Main API Response
    # --------------------------------------------------------
    def respond(self, incoming: str, raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        signals = self.observe(incoming)

        # strategy selection
        strategy = "probe"
        if signals.get("memory_probe"):
            strategy = "memory"
        if signals.get("repeat_complaint"):
            strategy = "annoyed"
        if signals.get("punct_complaint"):
            strategy = "calm"
        if self.s["flags"].get("repeat_count", 0) >= 3:
            strategy = "resist"
        if signals.get("threat"):
            strategy = "resist"
        if signals.get("otp") and self.s["flags"].get("otp_ask_count", 0) >= 2:
            strategy = "otp_warn"
        if signals.get("urgency") and self.s.get("outgoing_count", 0) > 3:
            strategy = "resist"

        reply = self.generate_reply(strategy, incoming, from_respond=True)
        reply = redact_sensitive(reply)

        # score + classification
        score = scam_signal_score(incoming)
        if signals.get("authority"):
            score += 0.2
        if signals.get("threat"):
            score += 0.3
        if LEGIT_ALERT_RE.search(incoming or ""):
            score = max(0.0, score - 1.5)
        score = min(score, 5.0)
        is_scam = score >= 2.5
        legit_score = max(0.0, 1 - (score / 5.0))

        # learning hook
        if self.learner:
            try:
                self.learner.observe(
                    incoming=incoming,
                    reply=reply,
                    phases=self.s.get("phase_history", [])[-1] if self.s.get("phase_history") else [],
                    extracted=self.s.get("extracted_profile", {}),
                    outcome="unknown",
                    strategy=strategy
                )
            except Exception:
                pass

        return {
            "reply": reply,
            "phases_used": self.s.get("phase_history", [])[-1] if self.s.get("phase_history") else [],
            "strategy": strategy,
            "signals": signals,
            "extracted_profile": self.s.get("extracted_profile", {}),
            "claims": self.s.get("claims", {}),
            "memory": self.s.get("memory", []),
            "intent": "honeypot_engagement",
            "scam_score": score,
            "legit_score": legit_score,
            "is_scam": is_scam,
        }
        # memory probe (what did I say before?)
        if signals.get("memory_probe"):
            reply = self._memory_reply()
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["verification_loop"], "memory", signals)

        # repeat complaint -> annoyance + clarify
        if signals.get("repeat_complaint"):
            reply = random.choice([
                "you already said it, why repeating",
                "i heard you, stop repeating",
                "why keep saying same thing",
                "you said it already, explain properly",
            ])
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["annoyance", "fatigue"], "annoyed", signals)

        # punctuation complaint
        if signals.get("punct_complaint"):
            reply = random.choice([
                "ok ok no more question marks",
                "fine, i will type normal",
                "ok chill, tell me properly",
            ])
            reply = self._style_scrubber(reply)
            return self._finalize_reply(reply, ["cooldown_state"], "calm", signals)
