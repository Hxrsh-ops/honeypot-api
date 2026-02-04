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
from memory_manager import MemoryManager, FREE_EMAIL_DOMAINS
from llm_adapter import generate_structured_reply, llm_available, rephrase_with_llm

logger = logging.getLogger("agent")
logging.basicConfig(level=logging.INFO)

# ----------------------------
# Constants / Regex
# ----------------------------
DEFAULT_REPLY = "ok"
LLM_REPHRASE_PROB = float(os.getenv("LLM_REPHRASE_PROB", "0.2"))

OTP_RE = re.compile(r"\b(otp|one[-\s]?time\s?password|verification\s?code)\b", re.I)
URGENT_RE = re.compile(
    r"\b(urgent|immediate|within|expire|freez(?:e|ing|ed)?|frozen|block(?:ed|ing)?|suspend(?:ed|ing|ion)?|disable(?:d)?|deactivat(?:e|ed))\b",
    re.I,
)
AUTH_RE = re.compile(r"\b(bank|rbi|world\s?bank|sbi|hdfc|icici|axis|fraud|security|official|manager)\b", re.I)
PAY_RE = re.compile(r"\b(upi|transfer|pay|payment|refund|charge|fee|ifsc|beneficiary|amount|transaction)\b", re.I)
ACCOUNT_REQ_RE = re.compile(r"\b(a/c|acct|account\s*(?:number|no\.?)|acc\s*no\.?)\b", re.I)
THREAT_RE = re.compile(r"\b(block|freeze|legal|police|case|report|fine|penalty|court)\b", re.I)

ASK_PROFILE_RE = re.compile(r"(tell me my name|what'?s my name|what is my name|my name and branch|tell me my branch|my branch name)", re.I)
MEMORY_ASK_RE = re.compile(r"(what did i (say|tell) (you|u)|what i said before|do you remember|repeat what i said|what did i tell you|what i told you)", re.I)
TOLD_YOU_RE = re.compile(
    r"("
    r"i told (you|u)|already told (you|u)|told (you|u) before|"
    r"i already (gave|shared|sent)|i just (gave|shared|sent)|"
    r"i (gave|shared|sent) (you|u)|"
    r"i mentioned already|i said already|"
    r"why are you asking (again|that again)|why you asking (again|that again)|"
    r"you keep asking (again|same thing)"
    r")",
    re.I,
)
BOT_ACCUSATION_RE = re.compile(r"\b(you are a bot|youre a bot|u are a bot|bot)\b", re.I)
CONFUSED_RE = re.compile(r"\b(confused|huh|what\?)\b", re.I)
CLARIFICATION_RE = re.compile(r"(what do you want me to explain|explain what|what exactly|what should i explain|explain\??\s*what)", re.I)
TYPING_ACCUSATION_RE = re.compile(r"(typing.*off|your typing.*off|typing feels off|you type.*bot|typing feels.*bot)", re.I)

LEGIT_STATEMENT_RE = re.compile(r"(statement is ready|monthly statement|e-statement|no action needed)", re.I)
TRANSACTION_ALERT_RE = re.compile(r"(transaction of|debited|credited|if not initiated)", re.I)
SOCIAL_IMPERSONATION_RE = re.compile(r"\b(mom|dad|mother|father|cousin|bro|brother|sis|sister|uncle|aunt|aunty|wife|husband|son|daughter|boss|manager|colleague|friend)\b", re.I)
JOB_SCAM_RE = re.compile(r"(job offer|offer letter|training fee|placement fee)", re.I)
PARCEL_SCAM_RE = re.compile(r"(parcel|delivery|courier|re-delivery|customs fee|delivery fee)", re.I)

SMALLTALK_RE = re.compile(r"\b(hi|hello|hey|how are you|what's up|whats up|sup|good morning|good night|good evening)\b", re.I)
THANKS_RE = re.compile(r"\b(thanks|thank you|thx|ty)\b", re.I)
ROBOTIC_RE = re.compile(r"\b(please|kindly|regards|sincerely|apolog|regarding|dear|sir|madam|as per|we advise|we request)\b", re.I)
ASSISTANTY_RE = re.compile(
    r"\b("
    r"thanks for reaching out|"
    r"what brings you here|"
    r"purpose of your message|"
    r"how can i help|how may i help|"
    r"how'?s your day going|"
    r"reach out|assist you"
    r")\b",
    re.I,
)
CONTRADICTION_TALK_RE = re.compile(r"\b(earlier you said|but now|now you're saying)\b", re.I)
PROMPT_LEAK_RE = re.compile(r"\b(proof_state|verification_asks|intel_targets|intent_hint|session_summary|mood_delta|extractions?)\b", re.I)
DISMISSIVE_RE = re.compile(r"\b(i\s*don'?t\s*care|idc|not my problem)\b", re.I)


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
            # ensure variation remains for tests/human feel
            reply = self._unique_reply(reply, allow_variation=True)
        return reply

    # ----------------------------
    # Signals / Intent Routing
    # ----------------------------
    def _detect_signals(self, text: str) -> Dict[str, bool]:
        lower = (text or "").lower()
        smalltalk = bool(SMALLTALK_RE.search(lower))
        if smalltalk and (AUTH_RE.search(lower) or "i am" in lower or "from" in lower):
            smalltalk = False

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
            "clarification_request": bool(CLARIFICATION_RE.search(lower)),
            "typing_accusation": bool(TYPING_ACCUSATION_RE.search(lower)),
            "legit_statement": bool(LEGIT_STATEMENT_RE.search(text or "")),
            "transaction_alert": bool(TRANSACTION_ALERT_RE.search(text or "")),
            "social_impersonation": bool(SOCIAL_IMPERSONATION_RE.search(lower)),
            "job_scam": bool(JOB_SCAM_RE.search(text or "")),
            "parcel_scam": bool(PARCEL_SCAM_RE.search(text or "")),
            "smalltalk": smalltalk,
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

    def _intent_directive(self, intent: str, signals: Dict[str, bool], memory_hint: Optional[str]) -> str:
        if intent == "bot_accusation":
            return "deny being a bot in a casual way and deflect; ask them to be clear"
        if intent in ["legit_statement", "legit_transaction"]:
            return "acknowledge calmly; do not probe; keep it short"
        if intent == "social_impersonation":
            return "verify identity; ask them to call or share official proof; be cautious"
        if intent == "job_scam":
            return "push back on fees; ask for official company email or offer letter"
        if intent == "parcel_scam":
            return "ask for official courier site/app; refuse to pay via link"
        if intent == "smalltalk":
            return "reply very short like a normal texter (1 line). no long greetings. ask who this is / what's this about"
        if signals.get("repetition"):
            return "you already said that; get slightly annoyed; ask for official email/branch/employee id"
        if signals.get("otp") or signals.get("payment") or signals.get("account_request"):
            return (
                "do NOT share otp/account details. don't be a wall either—sound like a real person under pressure. "
                "give them a tiny bit of hope like you're checking, but stall and extract info. "
                "ask for ONE specific proof (bank-domain email / branch landline / employee id) or their link/upi if relevant. "
                "don't loop 'explain'. acknowledge what they already gave."
            )
        if memory_hint:
            return "use the provided memory_hint wording. keep it human + short"
        if signals.get("authority") and not any([signals.get("urgency"), signals.get("threat"), signals.get("otp"), signals.get("payment"), signals.get("link")]):
            return "they claim bank/authority but gave no issue. be suspicious: ask what this is about + one proof. don't be friendly"
        return "be skeptical, short, and human. avoid customer-support tone. ask for one specific proof if needed"

    # ----------------------------
    # Guardrails / Fallback
    # ----------------------------
    def _looks_robotic(self, reply: str) -> bool:
        if not reply:
            return False
        if ROBOTIC_RE.search(reply):
            return True
        if ASSISTANTY_RE.search(reply):
            return True
        if reply.count(".") >= 2:
            return True
        if len(reply.split()) > 26:
            return True
        return False

    def _rewrite_if_robotic(self, reply: str) -> str:
        if not reply or not self._looks_robotic(reply):
            return reply
        if ASSISTANTY_RE.search(reply):
            # Hard rewrite: assistant-y greetings are a dead giveaway.
            return random.choice([
                "who's this?",
                "who is this",
                "haan who?",
                "what is it?",
            ])
        if llm_available() and random.random() < LLM_REPHRASE_PROB:
            alt = rephrase_with_llm(reply)
            if alt:
                return alt
        text = reply.replace("\n", " ").strip()
        text = re.sub(r"\bkindly\b", "", text, flags=re.I)
        text = re.sub(r"\bplease\b", "pls", text, flags=re.I)
        text = re.sub(r"\bI am\b", "i'm", text, flags=re.I)
        text = re.sub(r"\bI cannot\b", "i can't", text, flags=re.I)
        text = re.sub(r"\bI will\b", "i'll", text, flags=re.I)
        text = re.sub(r"\bI have\b", "i've", text, flags=re.I)
        text = re.sub(r"\bdo not\b", "don't", text, flags=re.I)
        text = re.sub(r"\bwill not\b", "won't", text, flags=re.I)
        text = re.sub(r"\bregards\b.*$", "", text, flags=re.I)
        text = re.sub(r"\bsincerely\b.*$", "", text, flags=re.I)
        text = text.strip().lower()
        # shorten if still long
        if len(text) > 160:
            text = " ".join(text.split()[:22])
        return text.strip()

    def _trim_incomplete(self, reply: str) -> str:
        """
        Avoid returning replies that got cut mid-sentence by token limits (common with open models).
        Only trims when the message ends in an obvious dangling word/phrase.
        """
        if not reply:
            return reply
        text = (reply or "").strip()
        # Already ends cleanly.
        if re.search(r"[.!?]$", text):
            return text

        # Ends with a dangling stopword or fragment.
        if not re.search(r"(\bi want to\b|\bcan you give me\b|\bgive me your\b)$", text, re.I) and not re.search(
            r"\b(to|the|a|an|of|for|from|with|and|or|but|so|because)\b$",
            text,
            re.I,
        ):
            return text

        last = max(text.rfind("."), text.rfind("?"), text.rfind("!"))
        if last >= 10:
            return text[: last + 1].strip()
        return text

    def _humanize_ask(self, ask: str) -> str:
        a = (ask or "").strip().lower()
        if not a:
            return a
        # make the "asks" feel like texting, not a form.
        a = a.replace("official bank-domain email (not gmail)", "bank email (not gmail)")
        a = a.replace("branch landline (not mobile)", "branch landline (not mobile)")
        a = a.replace("branch name (not just city)", "exact branch name (not just city)")
        return a

    def _verification_status_line(self, proof_state: Dict[str, Any], verification_asks: List[str], scam_confirmed: bool) -> str:
        """
        Single short line that:
        - acknowledges what they already gave
        - calls out the most suspicious bit (if any)
        - asks for ONE next thing (rotates based on verification_asks)
        """
        proof = proof_state or {}
        suspicious = set(proof.get("suspicious") or [])
        missing = list(proof.get("missing") or [])
        email_dom = str(proof.get("email_domain") or "").strip()

        facts = self.s.get("memory_state", {}).get("facts", {}) or {}
        name = (facts.get("name") or "").strip()
        branch = (facts.get("branch") or "").strip()

        who = name or "bro"

        ask = ""
        if verification_asks:
            ask = verification_asks[0]
        elif missing:
            ask = missing[0]

        ask = self._humanize_ask(ask)

        # Preface based on suspicion
        pre = ""
        if "free_email" in suspicious and email_dom:
            pre = random.choice([
                f"bro that's {email_dom}, not bank mail",
                f"{email_dom} mail isn't official",
                f"gmail type mail isn't official",
            ])
        elif "landline_looks_mobile" in suspicious:
            pre = random.choice([
                "that 'landline' looks like a mobile number",
                "nah that number looks mobile",
                "branch landline shouldn't look like mobile",
            ])
        elif "branch_ambiguous" in suspicious:
            if branch and len(branch.split()) == 1:
                pre = random.choice([f"{branch} is just city", "city isn't branch name"])
            elif branch:
                pre = random.choice([f"'{branch}' is too generic", "need exact branch name"])
            else:
                pre = "branch name missing"
        else:
            pre = random.choice(["ok", "hmm", "listen", "wait"])

        if not ask:
            return random.choice([
                "ok what exactly do you want?",
                "hmm what's the issue then?",
            ])

        # Honeypot mode: when scam is confirmed, keep them engaged while extracting link/upi/etc.
        if scam_confirmed and "link" in ask:
            return random.choice([
                f"ok ok send me {ask}",
                f"fine. send {ask}",
                f"send {ask} then. i’ll check",
            ])
        if scam_confirmed and "upi" in ask:
            return random.choice([
                f"upi for what? send {ask}",
                f"ok which upi? send {ask}",
                f"send {ask} first, then we talk",
            ])

        return random.choice([
            f"{pre}. send {ask}",
            f"ya {who}, but {pre}. send {ask}",
            f"ok, still need {ask}",
        ])

    def _maybe_append_followup(self, reply: str, follow: str) -> str:
        r = (reply or "").strip()
        f = (follow or "").strip()
        if not r or not f:
            return r or f
        rlow = r.lower()
        flow = f.lower()
        if flow in rlow:
            return r
        # avoid double-questions / repeated asks
        if "?" in r and "?" in f:
            return r
        # skip if high token overlap (LLM often repeats itself)
        rtoks = set(re.findall(r"[a-z0-9]+", rlow))
        ftoks = set(re.findall(r"[a-z0-9]+", flow))
        if rtoks and (len(rtoks & ftoks) / max(1, len(ftoks))) >= 0.50:
            return r
        if len(r) > 160:
            return r
        return f"{r} {f}".strip()

    def _guardrails(self, reply: str) -> str:
        if not reply:
            return DEFAULT_REPLY
        # never admit bot
        lowered = reply.lower()
        if "i am a bot" in lowered or "i'm a bot" in lowered:
            reply = re.sub(r"i\s*('?m| am)\s*a\s*bot", "i'm not a bot", reply, flags=re.I)
        if "as an ai" in lowered or "as a bot" in lowered:
            reply = re.sub(r"as an? (ai|bot)", "as a person", reply, flags=re.I)
        reply = self._rewrite_if_robotic(reply)
        reply = self._trim_incomplete(reply)
        # redact sensitive
        reply = redact_sensitive(reply)
        # keep short-ish
        reply = reply.strip()
        if len(reply) > 450:
            reply = reply[:450]
        return reply

    def _unique_reply(self, reply: str, allow_variation: bool = True) -> str:
        if not reply:
            return DEFAULT_REPLY
        recent_norm = self.s.get("recent_responses", [])
        recent_raw = self.s.get("recent_raw_responses", [])
        recent_raw_set = set(recent_raw)

        # --- optional variation (still must remain unique) ---
        if allow_variation:
            # occasional shorten for length variety
            if len(reply) > 120 and random.random() < 0.2:
                reply = " ".join(reply.split()[:12])
            elif len(reply) > 80 and random.random() < 0.15:
                reply = " ".join(reply.split()[:16])
            # length variation for tests/human feel
            if len(reply) < 40 and random.random() < 0.3:
                # Avoid generic "explain" loops; keep it as light human filler instead.
                reply = f"{reply} {random.choice(['??', 'bro', 'ya', 'hmm'])}"

        # --- enforce no exact repeats (deterministic, not luck-based) ---
        reply = re.sub(r"\s+", " ", (reply or "").strip())
        base = reply

        if base in recent_raw_set:
            flags = self.s.setdefault("flags", {})
            counter = int(flags.get("outgoing_count", 0))

            prefixes = ["hmm", "ok", "hey", "one sec", "wait", "bro", "ya", "listen", "hold on", "look"]
            suffixes = ["ok", "hmm", "pls", "ya", "bro", "man", "ok then", "so?", "right", "nah"]
            punct = ["", ".", "..", "...", "?", "??", "!"]

            # Try a bunch of deterministic variants until we find a unique one.
            for i in range(80):
                idx = counter + i
                p = prefixes[idx % len(prefixes)]
                s = suffixes[(idx // len(prefixes)) % len(suffixes)]
                q = punct[(idx // (len(prefixes) * len(suffixes))) % len(punct)]

                form = idx % 4
                if form == 0:
                    cand = f"{p} {base}".strip()
                elif form == 1:
                    cand = f"{base} {s}".strip()
                elif form == 2:
                    cand = f"{p} {base} {s}".strip()
                else:
                    cand = f"{base}{q}".strip()

                cand = re.sub(r"\s+", " ", cand).strip()
                if cand and cand not in recent_raw_set:
                    reply = cand
                    flags["outgoing_count"] = idx + 1
                    break
            else:
                # extremely unlikely; last-resort punctuation that stays non-numeric
                reply = f"{base} ...".strip()

        norm = normalize_text(reply)
        recent_norm.append(norm)
        recent_raw.append(reply)
        self.s["recent_responses"] = recent_norm[-200:]
        self.s["recent_raw_responses"] = recent_raw[-200:]
        return reply

    def _fallback_reply(self, incoming: str, signals: Dict[str, bool]) -> str:
        lower = (incoming or "").lower()

        if signals.get("bot_accusation"):
            return "nah, just tell me properly"
        if signals.get("typing_accusation"):
            return random.choice([
                "typing off? bro just say what you want",
                "im typing normal lol. what is it?",
                "what? im typing fine. what's this about",
            ])
        if signals.get("clarification_request"):
            pressure = any([
                signals.get("otp"),
                signals.get("payment"),
                signals.get("link"),
                signals.get("authority"),
                signals.get("urgency"),
                signals.get("threat"),
                signals.get("account_request"),
                self.s.get("flags", {}).get("otp_ask_count", 0) > 0,
            ])
            if pressure:
                return random.choice([
                    "explain why you need otp + which branch you're from + official email",
                    "ok explain what you want. send employee id + branch landline",
                    "why otp? tell branch + official email + your id, then talk",
                ])
            return random.choice([
                "explain what exactly?",
                "about what? just say it straight",
            ])
        if signals.get("ask_profile"):
            return self.memory.answer_profile_question()
        if signals.get("memory_probe"):
            return self.memory.answer_memory_question()
        if signals.get("told_you"):
            return self.memory.answer_verification_status()
        if signals.get("transaction_alert"):
            return "if it's not me i'll call the bank now"
        if signals.get("legit_statement"):
            return "noted, i'll check later"
        if signals.get("social_impersonation"):
            if "boss" in lower or "manager" in lower:
                return "call me from office line, not this"
            return "call me, this number feels off"
        if signals.get("job_scam"):
            return "real jobs don't ask money"
        if signals.get("parcel_scam"):
            return "i'll check the official courier app"
        if signals.get("authority") or signals.get("urgency") or signals.get("threat"):
            return self.memory.answer_verification_status()
        if signals.get("otp"):
            return "otp is private, not sharing"
        if signals.get("payment") or signals.get("account_request"):
            return "not sharing account details on text"
        if "ifsc" in lower or "id" in lower or "employee" in lower:
            return self.memory.answer_verification_status()
        if signals.get("link"):
            return "link looks fake, send official site"
        if signals.get("confused"):
            if any([signals.get("otp"), signals.get("payment"), signals.get("authority"), signals.get("urgency")]):
                return "huh? why otp. send official email/branch and explain"
            return "huh? what exactly"

        if signals.get("smalltalk"):
            return "hey, what's this about"
        if signals.get("thanks"):
            return "ok"

        # if OTP/scam was already in the thread, keep asking for verification instead of looping "explain"
        if self.s.get("flags", {}).get("otp_ask_count", 0) > 0 and not any([signals.get("legit_statement"), signals.get("transaction_alert")]):
            return random.choice([
                "ok then send branch + official email + your id",
                "give employee id + branch landline. i'll verify",
                "send official email from bank domain, then talk",
            ])

        # generic fallback
        return random.choice([
            "what's this about exactly?",
            "ok but what's the actual issue?",
            "hmm. what do you need from me?",
        ])

    # ----------------------------
    # Main response
    # ----------------------------
    def respond(self, incoming: str, raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        incoming = str(incoming or "")
        self.memory.add_user_message(incoming)
        self.observe(incoming)

        signals = self._detect_signals(incoming)
        intent_hint = self._intent_hint(signals)

        # keep thread continuity: if OTP/scam was already in play, don't fall back to "general"
        if intent_hint == "general" and self.s.get("flags", {}).get("otp_ask_count", 0) > 0:
            if not any([signals.get("legit_statement"), signals.get("transaction_alert"), signals.get("smalltalk")]):
                intent_hint = "scam_pressure"

        if signals.get("otp"):
            self.s["flags"]["otp_ask_count"] = self.s["flags"].get("otp_ask_count", 0) + 1

        # bot accusation flag
        if signals.get("bot_accusation"):
            self.s["flags"]["bot_accused"] = True

        # repetition tracking
        finger = normalize_text(incoming)
        recent_texts = self.s.get("recent_texts", [])
        if recent_texts and recent_texts[-1] == finger:
            self.s["flags"]["repeat_count"] = self.s["flags"].get("repeat_count", 0) + 1
        else:
            self.s["flags"]["repeat_count"] = 0
        recent_texts.append(finger)
        self.s["recent_texts"] = recent_texts[-50:]
        if self.s["flags"]["repeat_count"] >= 3:
            signals["repetition"] = True

        memory_hint = None
        if signals.get("ask_profile"):
            memory_hint = self.memory.answer_profile_question()
        elif signals.get("memory_probe"):
            memory_hint = self.memory.answer_memory_question()
        elif signals.get("told_you"):
            # "i already told/gave you" — respond with what we have + what's missing.
            memory_hint = self.memory.answer_verification_status()

        otp_probe_hint = None

        # --------------------------------------------------
        # Proof state (prevents "ask same thing again" loops)
        # --------------------------------------------------
        facts_now = self.s.get("memory_state", {}).get("facts", {}) or {}
        proof_state = self.memory.compute_proof_state()
        verification_asks: List[str] = list(proof_state.get("asks") or [])

        # "scam confirmed" once we see enough signals; used to shift into honeypot mode.
        score_now = scam_signal_score(incoming)
        if signals.get("authority"):
            score_now += 0.2
        if signals.get("threat") or signals.get("urgency"):
            score_now += 0.3
        if signals.get("legit_statement") or signals.get("transaction_alert"):
            score_now = max(0.0, score_now - 1.0)
        score_now = min(score_now, 5.0)
        scam_confirmed = bool(self.s.get("flags", {}).get("scam_confirmed")) or (
            score_now >= 2.5 and not any([signals.get("legit_statement"), signals.get("transaction_alert")])
        )
        if scam_confirmed:
            self.s.setdefault("flags", {})["scam_confirmed"] = True
            if intent_hint == "general":
                intent_hint = "scam_pressure"

        # What intel we still want to extract (helps LLM pick useful questions).
        profile_now = self.s.get("extracted_profile", {}) or {}
        intel_targets: List[str] = []
        if scam_confirmed:
            if not profile_now.get("url"):
                intel_targets.append("the link/site they want you to use")
            if not profile_now.get("upi") and ("upi" in incoming.lower() or signals.get("payment")):
                intel_targets.append("their upi id")
            if not profile_now.get("employee_id"):
                intel_targets.append("their employee id")
            if not profile_now.get("branch_phone"):
                intel_targets.append("their branch landline/callback number")
            if not profile_now.get("email"):
                intel_targets.append("their bank-domain email")
        intel_targets = intel_targets[:3]

        # If we already have basic proofs but scam is confirmed, switch into intel-extraction asks
        # instead of repeating verification over and over.
        if scam_confirmed and not verification_asks:
            if not profile_now.get("url"):
                verification_asks = ["the link you're asking me to open"]
            else:
                verification_asks = ["case/ticket id or reference number"]

        # Honeypot behavior: when they describe "steps/process", ask for the link/beneficiary early to extract intel.
        incoming_low = incoming.lower()
        if scam_confirmed and not profile_now.get("url"):
            if any(w in incoming_low for w in ["click", "link", "steps", "step", "process", "guide", "renew", "update", "verify"]):
                link_ask = "the link you're asking me to open"
                verification_asks = [link_ask] + [a for a in verification_asks if a != link_ask]
        if scam_confirmed and signals.get("payment") and not profile_now.get("upi"):
            upi_ask = "the upi id / beneficiary you're asking me to send to"
            verification_asks = [upi_ask] + [a for a in verification_asks if a != upi_ask]

        verification_asks = verification_asks[:2]

        # Rotate asks to avoid asking the *same* thing back-to-back when they keep dodging.
        last_ask = self.s.get("flags", {}).get("last_verification_ask")
        if last_ask and verification_asks and verification_asks[0] == last_ask and len(verification_asks) > 1:
            verification_asks = [verification_asks[1], verification_asks[0]]

        # Override memory hints with proof-aware, honeypot-friendly wording.
        if signals.get("told_you"):
            memory_hint = self._verification_status_line(proof_state, verification_asks, scam_confirmed=scam_confirmed)
        if signals.get("clarification_request") and any(
            [
                scam_confirmed,
                signals.get("otp"),
                signals.get("payment"),
                signals.get("link"),
                signals.get("authority"),
                signals.get("urgency"),
                signals.get("threat"),
            ]
        ):
            ask0 = self._humanize_ask(verification_asks[0]) if verification_asks else "official proof"
            memory_hint = random.choice(
                [
                    f"explain what? what exactly you want me to do + send {ask0}",
                    f"ok, what are the steps? and send {ask0}",
                    f"what do you want from me? send {ask0} first",
                ]
            )

        # Honeypot stage (helps LLM drift from skeptical -> play-along -> stall).
        honeypot_stage = int(self.s.get("flags", {}).get("honeypot_stage", 0) or 0)
        if scam_confirmed:
            honeypot_stage = 1 if honeypot_stage <= 0 else min(6, honeypot_stage + 1)
            self.s.setdefault("flags", {})["honeypot_stage"] = honeypot_stage
        else:
            honeypot_stage = 0

        if signals.get("otp") and self.s["flags"].get("otp_ask_count", 0) == 1:
            # First OTP ask: probe for proof (not a generic OTP refusal).
            ask = verification_asks[0] if verification_asks else "official bank-domain email"
            otp_probe_hint = random.choice([
                f"otp?? why do you need otp. send {ask} first",
                f"no otp on text. send {ask}",
                f"before otp, send {ask}",
            ])

        # LLM-first
        llm_used = False
        reply = None
        llm_out = None

        if llm_available():
            directive = self._intent_directive(intent_hint, signals, memory_hint)
            context = {
                "incoming": incoming,
                "intent_hint": intent_hint,
                "signals": signals,
                "directive": directive,
                "memory_hint": memory_hint,
                "otp_probe_hint": otp_probe_hint,
                "verification_asks": verification_asks,
                "proof_state": proof_state,
                "scam_confirmed": scam_confirmed,
                "intel_targets": intel_targets,
                "honeypot_stage": honeypot_stage,
                "facts": facts_now,
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
            if reply is not None and not isinstance(reply, str):
                reply = str(reply)
            llm_used = True
            extractions = llm_out.get("extractions") or {}
            if not isinstance(extractions, dict):
                extractions = {}
            self.memory.merge_extractions(extractions, source="llm")

            intent_out = llm_out.get("intent")
            if isinstance(intent_out, str) and intent_out:
                intent_hint = intent_out.strip()

            # update persona / summary
            mood_delta = llm_out.get("mood_delta", 0.0) or 0.0
            self.memory.update_persona(mood_delta)
            summary = llm_out.get("session_summary")
            if summary:
                self.s["memory_state"]["session_summary"] = str(summary)[:240]
            else:
                self.memory.update_summary(incoming, reply or "")

            # Don't append follow_up_question to reply: open models sometimes put meta/prompt artifacts there.

        # Guardrail: if the model leaks internal prompt/context tokens, drop to a safe fallback.
        if reply and PROMPT_LEAK_RE.search(str(reply)):
            reply = otp_probe_hint or memory_hint or self._fallback_reply(incoming, signals)

        # loop-breaker: if the reply asks again for proof we already have, replace with a
        # short "got it / here's what's missing" line.
        if reply:
            rlow = reply.lower()
            if DISMISSIVE_RE.search(rlow):
                reply = self._verification_status_line(proof_state, verification_asks, scam_confirmed=scam_confirmed)
                rlow = reply.lower()
            missing_low = " ".join([str(m).lower() for m in (proof_state.get("missing") or [])])
            need_email = ("bank-domain email" in missing_low) or ("bank email" in missing_low)
            need_landline = "landline" in missing_low
            need_branch = "branch name" in missing_low

            emp_ok = bool(facts_now.get("employee_id"))
            email_ok = bool(facts_now.get("email")) and not need_email
            landline_ok = bool(facts_now.get("branch_phone")) and not need_landline
            branch_ok = bool(facts_now.get("branch")) and not need_branch

            asks_emp = bool(re.search(r"\b(employee id|emp id)\b", rlow) and re.search(r"\b(send|share|give)\b", rlow))
            asks_branch = bool(re.search(r"\bbranch\b", rlow) and re.search(r"\b(send|share|give|which)\b", rlow))
            asks_email = bool(re.search(r"\b(email|mail)\b", rlow) and re.search(r"\b(send|share|give)\b", rlow))
            asks_landline = bool(re.search(r"\b(landline|office line|branch line)\b", rlow) and re.search(r"\b(send|share|give)\b", rlow))

            if (asks_emp and emp_ok) or (asks_branch and branch_ok) or (asks_email and email_ok) or (asks_landline and landline_ok):
                reply = self._verification_status_line(proof_state, verification_asks, scam_confirmed=scam_confirmed)

            # Don't allow the LLM to invent contradictions; only mention them if we have any recorded.
            if not (self.s.get("memory_state", {}).get("contradictions") or []) and CONTRADICTION_TALK_RE.search(rlow):
                reply = random.choice([
                    "huh? just say what you want",
                    "what are you even saying. just tell me clearly",
                ])

            # If we're still missing proof, don't let the reply sound "convinced".
            if proof_state.get("missing") and re.search(r"\b(ok|okay|cool)\s+got it\b|\bgot it\b", rlow):
                reply = self._verification_status_line(proof_state, verification_asks, scam_confirmed=scam_confirmed)

            # Clarification loop breaker: must be specific, not "explain" spam.
            if signals.get("clarification_request"):
                if "explain" in rlow and not any(k in rlow for k in ["branch", "email", "employee", "landline", "link", "call", "upi", "ticket"]):
                    reply = memory_hint or self._fallback_reply(incoming, signals)

        # enforce memory accuracy when asked directly
        if memory_hint and reply:
            facts = self.s.get("memory_state", {}).get("facts", {})
            name = facts.get("name")
            bank = facts.get("bank")
            branch = facts.get("branch")
            if signals.get("ask_profile") and name and name.lower() not in reply.lower():
                reply = memory_hint
            if signals.get("ask_profile") and bank and bank.lower() not in reply.lower():
                reply = memory_hint
            if signals.get("told_you") and memory_hint:
                reply = memory_hint

        if otp_probe_hint and reply and signals.get("otp") and self.s["flags"].get("otp_ask_count", 0) == 1:
            # If the LLM reply forgot to ask for proof, force the OTP probe hint.
            if not any(k in reply.lower() for k in ["email", "branch", "employee", "landline", "call", "link"]):
                reply = otp_probe_hint

        # If they're applying pressure but the reply is too vague/short, force a specific next ask.
        if reply and not signals.get("smalltalk"):
            pressure = any([signals.get("urgency"), signals.get("threat"), signals.get("authority"), signals.get("otp"), signals.get("payment"), signals.get("link")])
            if pressure and len(str(reply).split()) <= 3:
                reply = memory_hint or self._verification_status_line(proof_state, verification_asks, scam_confirmed=scam_confirmed)

        if not reply:
            reply = otp_probe_hint or memory_hint or self._fallback_reply(incoming, signals)

        # repetition escalation enforce keywords
        if signals.get("repetition"):
            if not any(k in reply.lower() for k in ["official", "email", "branch", "call", "ticket", "suspicious"]):
                if verification_asks:
                    reply = f"{reply} send {verification_asks[0]}".strip()
                else:
                    reply = f"{reply} what's the issue then?".strip()

        # suspicious id/ifsc ensure probe
        lower = incoming.lower()
        if ("ifsc" in lower or "employee" in lower or "id" in lower) and not any(k in reply.lower() for k in ["id", "ifsc", "email", "branch", "call"]):
            if verification_asks:
                reply = f"{reply} send {verification_asks[0]}".strip()
            else:
                reply = f"{reply} send bank-domain email".strip()

        allow_variation = True
        if intent_hint in ["smalltalk", "legit_statement", "legit_transaction"]:
            allow_variation = False
        if signals.get("ask_profile") or signals.get("memory_probe") or signals.get("told_you") or signals.get("clarification_request") or signals.get("typing_accusation"):
            allow_variation = False
        reply = self._unique_reply(self._guardrails(reply), allow_variation=allow_variation)
        self.memory.add_bot_message(reply)
        self.memory.update_summary(incoming, reply)
        if verification_asks:
            self.s.setdefault("flags", {})["last_verification_ask"] = verification_asks[0]

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
