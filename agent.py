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
import botpress_adapter

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

PROCESS_RE = re.compile(r"\b(steps?|process|guide|renew|update|verify|click|link|app|form|login)\b", re.I)

SMALLTALK_RE = re.compile(r"\b(hi|hello|hey|how are you|what's up|whats up|sup|good morning|good night|good evening)\b", re.I)
THANKS_RE = re.compile(r"\b(thanks|thank you|thx|ty)\b", re.I)
ROBOTIC_RE = re.compile(r"\b(please|kindly|regards|sincerely|apolog|regarding|dear|sir|madam|as per|we advise|we request)\b", re.I)
IDENTITY_LOOP_RE = re.compile(
    r"\b("
    # accept straight/curly apostrophes and even "whos"
    r"who(?:['\u2019]s|s| is)\s+this|"
    r"who\s+r\s+(?:u|you)|"
    r"who\s+are\s+(?:u|you)|"
    r"who['\u2019]re\s+you"
    r")\b",
    re.I,
)
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
        # If we already have an identity thread going, don't treat "hlo?/hi" pings as new smalltalk.
        if smalltalk:
            facts = self.s.get("memory_state", {}).get("facts", {}) or {}
            if facts.get("name") or facts.get("bank") or self.s.get("flags", {}).get("otp_ask_count", 0) > 0:
                smalltalk = False

        return {
            "otp": bool(OTP_RE.search(lower)),
            "payment": bool(UPI_RE.search(text) or PAY_RE.search(lower)),
            "account_request": bool(ACCOUNT_REQ_RE.search(lower)),
            "link": bool(URL_RE.search(text)),
            "process": bool(PROCESS_RE.search(lower)),
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

    def _intent_directive(
        self,
        intent: str,
        signals: Dict[str, bool],
        memory_hint: Optional[str],
        scam_confirmed: bool = False,
        honeypot_stage: int = 0,
    ) -> str:
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

        if scam_confirmed:
            if honeypot_stage >= 4:
                return (
                    "scam confirmed. you're tired/annoyed but still keep them talking. "
                    "act like you're checking, don't fully shut them down. "
                    "ask for ONE thing (official link/callback/case id/employee id). "
                    "acknowledge what they already gave; do not ask 'which bank again'."
                )
            if honeypot_stage >= 2:
                return (
                    "scam confirmed. play along a bit like you're worried and checking. "
                    "give tiny hope you're doing it, but stall and extract ONE detail (link/callback/case id/employee id). "
                    "do NOT repeat the same question back-to-back; do not ask 'who is this' again."
                )
            return (
                "scam likely. be skeptical but engaged. ask for ONE proof (bank-domain email / branch landline / employee id). "
                "keep it short and human."
            )

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
            facts = self.s.get("memory_state", {}).get("facts", {}) or {}
            if facts.get("name") or facts.get("bank"):
                return self._cycle_choice([
                    "ok what's this about?",
                    "haan? what happened",
                    "what is it now",
                    "bol, what's the issue",
                ], "asst_greet_thread")
            return self._cycle_choice([
                "who's this?",
                "who is this",
                "haan who?",
                "what is it?",
            ], "asst_greet_new")
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

    def _cycle_choice(self, options: List[str], key: str) -> str:
        """
        Deterministic picker for fallback phrases.
        We keep rule-based outputs stable (no random template spam), while `_unique_reply`
        guarantees we never send the exact same message twice.
        """
        if not options:
            return ""
        flags = self.s.setdefault("flags", {})
        try:
            n = int(flags.get(key, 0) or 0)
        except Exception:
            n = 0
        flags[key] = n + 1
        return options[n % len(options)]

    def _verification_status_line(
        self,
        proof_state: Dict[str, Any],
        verification_asks: List[str],
        scam_confirmed: bool,
        honeypot_stage: int = 0,
    ) -> str:
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

        who = name or ""

        ask = ""
        if verification_asks:
            ask = verification_asks[0]
        elif missing:
            ask = missing[0]

        # If something is clearly suspicious, prioritize asking for the *fixed* version of that proof.
        if "free_email" in suspicious:
            for cand in [*verification_asks, *missing]:
                if "email" in str(cand).lower():
                    ask = cand
                    break
        if ("landline_looks_mobile" in suspicious) or ("landline_fake" in suspicious):
            for cand in [*verification_asks, *missing]:
                if "landline" in str(cand).lower():
                    ask = cand
                    break
        if "branch_ambiguous" in suspicious:
            for cand in [*verification_asks, *missing]:
                if "branch name" in str(cand).lower():
                    ask = cand
                    break

        ask = self._humanize_ask(ask)

        # Preface based on suspicion
        pre = ""
        if "free_email" in suspicious and email_dom:
            pre = self._cycle_choice(
                [
                    f"that's {email_dom}, not bank mail",
                    f"{email_dom} mail isn't official",
                    "gmail type mail isn't official",
                ],
                "tone_pre_free_email",
            )
        elif "landline_looks_mobile" in suspicious:
            pre = self._cycle_choice(
                [
                    "that 'landline' looks like a mobile number",
                    "nah that number looks mobile",
                    "branch landline shouldn't look like mobile",
                ],
                "tone_pre_landline_mobile",
            )
        elif "landline_fake" in suspicious:
            pre = self._cycle_choice(
                [
                    "that number looks fake",
                    "nah that's not a real branch line",
                    "that's not a landline",
                ],
                "tone_pre_landline_fake",
            )
        elif "branch_ambiguous" in suspicious:
            if branch and len(branch.split()) == 1:
                pre = self._cycle_choice([f"{branch} is just city", "city isn't branch name"], "tone_pre_branch_city")
            elif branch:
                pre = self._cycle_choice([f"'{branch}' is too generic", "need exact branch name"], "tone_pre_branch_generic")
            else:
                pre = "branch name missing"
        else:
            pre = self._cycle_choice(["ok", "hmm", "listen", "wait"], "tone_pre_default")

        if not ask:
            return self._cycle_choice(
                ["ok what exactly do you want?", "hmm what's the issue then?"],
                "tone_no_ask",
            )

        play = ""
        if scam_confirmed and honeypot_stage >= 2:
            # stage 2+ should feel like "i'm checking" (play-along), not pure refusal.
            play = self._cycle_choice(
                ["ok ok wait", "haan one sec", "ok hold on", "wait"],
                "tone_play_along",
            )

        # Honeypot mode: when scam is confirmed, keep them engaged while extracting link/upi/etc.
        if scam_confirmed and "link" in ask:
            if play:
                return f"{play}. send {ask}"
            return f"ok. send {ask}"
        if scam_confirmed and "upi" in ask:
            if play:
                return f"{play}. upi for what? send {ask}"
            return f"upi for what? send {ask}"

        if ("free_email" in suspicious) or ("landline_looks_mobile" in suspicious) or ("landline_fake" in suspicious) or ("branch_ambiguous" in suspicious):
            if play:
                return f"{play}. {pre}. send {ask}"
            return f"{pre}. send {ask}"

        # default proof ask (short)
        if play:
            return f"{play}. still need {ask}"
        return self._cycle_choice([f"{pre}. send {ask}", f"ok, still need {ask}"], "tone_default_ask")

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

    def _next_honeypot_ask(
        self,
        signals: Dict[str, bool],
        proof_state: Dict[str, Any],
        profile_now: Dict[str, Any],
    ) -> str:
        """
        Ask ladder to avoid fixation and to extract intel without rushing.
        Order: link → callback/branch line → employee id → bank-domain email → case/ticket id
        (UPI is inserted only when payment/UPI is in play).
        """
        flags = self.s.setdefault("flags", {})
        try:
            idx = int(flags.get("ask_cycle_idx", 0) or 0)
        except Exception:
            idx = 0

        # Insert UPI only when payment is actively in play.
        order = ["link", "callback", "employee_id", "email", "ticket"]
        if signals.get("payment") and not (profile_now or {}).get("upi"):
            order = ["link", "upi", "callback", "employee_id", "email", "ticket"]

        missing_low = " ".join([str(m).lower() for m in (proof_state.get("missing") or [])])
        suspicious = set(proof_state.get("suspicious") or [])

        def need(kind: str) -> bool:
            prof = profile_now or {}
            if kind == "link":
                # Don't ask for a link unless the convo is already about steps/otp/payment/link.
                if bool(prof.get("url")):
                    return False
                return bool(signals.get("link") or signals.get("process") or signals.get("otp") or signals.get("payment"))
            if kind == "upi":
                return signals.get("payment") and not bool(prof.get("upi"))
            if kind == "callback":
                # ask again if missing OR flagged suspicious
                return ("landline" in missing_low) or ("landline_looks_mobile" in suspicious) or ("landline_fake" in suspicious)
            if kind == "employee_id":
                return not bool(prof.get("employee_id"))
            if kind == "email":
                return ("bank-domain email" in missing_low) or ("bank email" in missing_low) or ("free_email" in suspicious)
            if kind == "ticket":
                return True
            return False

        # Prefer a different ask than last time if possible.
        last_kind = str(flags.get("last_ask_kind") or "").strip()
        chosen_kind = ""
        for off in range(len(order)):
            k = order[(idx + off) % len(order)]
            if not need(k):
                continue
            if last_kind and k == last_kind and any(need(x) for x in order if x != k):
                continue
            chosen_kind = k
            break
        if not chosen_kind:
            chosen_kind = "ticket"

        flags["ask_cycle_idx"] = (idx + 1) % max(1, len(order))
        flags["last_ask_kind"] = chosen_kind

        ask_map = {
            "link": "the link you're asking me to open",
            "upi": "the upi id / beneficiary you're asking me to send to",
            "callback": "branch landline (not mobile)",
            "employee_id": "employee id",
            "email": "official bank-domain email (not gmail)",
            "ticket": "case/ticket id or reference number",
        }
        return ask_map.get(chosen_kind, "official proof")

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
            # NOTE: do not append random fillers like "ya" / "ok" to short replies.
            # It reads weird in serious threads and feels template-y. Uniqueness is
            # handled deterministically below when an exact repeat happens.

        # --- enforce no exact repeats (deterministic, not luck-based) ---
        reply = re.sub(r"\s+", " ", (reply or "").strip())
        base = reply

        if base in recent_raw_set:
            flags = self.s.setdefault("flags", {})
            counter = int(flags.get("outgoing_count", 0))

            prefixes = ["hmm", "ok", "hey", "one sec", "wait", "ya", "listen", "hold on", "look"]
            suffixes = ["ok", "hmm", "pls", "ya", "ok then", "so?", "right", "nah", "tho"]
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

    def _fallback_reply(
        self,
        incoming: str,
        signals: Dict[str, bool],
        proof_state: Optional[Dict[str, Any]] = None,
        verification_asks: Optional[List[str]] = None,
        scam_confirmed: bool = False,
        honeypot_stage: int = 0,
        memory_hint: Optional[str] = None,
    ) -> str:
        lower = (incoming or "").lower()
        proof = proof_state or self.memory.compute_proof_state()
        profile_now = self.s.get("extracted_profile", {}) or {}

        # Determine the "one thing" we want next.
        asks = list(verification_asks or [])
        if not asks:
            asks = [self._next_honeypot_ask(signals, proof, profile_now)] if (scam_confirmed or self.s.get("flags", {}).get("scam_confirmed")) else list(proof.get("asks") or [])
        asks = asks[:1]

        # Highest priority: if they just sent a link/upi/id/number, stay on that thread.
        if URL_RE.search(incoming or ""):
            # Don't echo the link; ask for official site/domain.
            return self._cycle_choice(
                [
                    "hmm link? which site is that. send official bank link",
                    "ok i see a link. what's the official bank site link?",
                    "link looks off. send the official site link",
                ],
                "fb_link",
            )
        if UPI_RE.search(incoming or "") or ("upi" in lower and signals.get("payment")):
            # Keep them talking; don't reveal/confirm any UPI.
            return self._cycle_choice(
                [
                    "upi for what exactly? im not sending anything. send case/ticket id",
                    "why upi? what's the official reference/case id",
                    "upi?? no. send the official link + case id",
                ],
                "fb_upi",
            )

        if signals.get("bot_accusation"):
            return self._cycle_choice(
                ["nah lol. just say what you want", "what? just tell me clearly", "what? i'm typing normal. say it straight"],
                "fb_bot",
            )
        if signals.get("typing_accusation"):
            return self._cycle_choice(
                [
                    "typing off? just say what you want",
                    "im typing normal. what is it?",
                    "what? i'm typing fine. what's this about",
                ],
                "fb_typing",
            )
        if signals.get("clarification_request"):
            ask0 = self._humanize_ask(asks[0]) if asks else "official proof"
            # Never loop "explain" — be specific about what you need.
            if scam_confirmed or any([signals.get("otp"), signals.get("payment"), signals.get("link"), signals.get("authority"), signals.get("urgency"), signals.get("threat")]):
                return self._cycle_choice(
                    [
                        f"what exactly are the steps? and send {ask0}",
                        f"ok, what do you want me to do? send {ask0}",
                        f"say it straight. send {ask0}",
                    ],
                    "fb_clarify_pressure",
                )
            return self._cycle_choice(["about what exactly?", "what are you talking about?"], "fb_clarify")

        if signals.get("ask_profile"):
            return self.memory.answer_profile_question()
        if signals.get("memory_probe"):
            return self.memory.answer_memory_question()
        if signals.get("told_you"):
            # Use proof-aware line (deterministic) instead of a random template.
            return memory_hint or self._verification_status_line(proof, asks, scam_confirmed=scam_confirmed, honeypot_stage=honeypot_stage)

        if signals.get("transaction_alert"):
            return "if it's not me i'll call the bank now"
        if signals.get("legit_statement"):
            return "ok noted"
        if signals.get("social_impersonation"):
            if "boss" in lower or "manager" in lower:
                return "call me from office number, not this"
            return "call me. this number feels off"
        if signals.get("job_scam"):
            return "real jobs don't ask money"
        if signals.get("parcel_scam"):
            return "i'll check the official courier app"

        # Bank/scam thread: default to proof-aware ask ladder.
        in_bank_thread = bool(
            (self.s.get("memory_state", {}).get("facts", {}) or {}).get("bank")
            or self.s.get("flags", {}).get("scam_confirmed")
            or self.s.get("flags", {}).get("otp_ask_count", 0) > 0
        )
        if in_bank_thread and not any([signals.get("legit_statement"), signals.get("transaction_alert"), signals.get("smalltalk")]):
            return self._verification_status_line(proof, asks, scam_confirmed=scam_confirmed, honeypot_stage=honeypot_stage)

        if signals.get("otp"):
            ask0 = self._humanize_ask(asks[0]) if asks else "official proof"
            return f"otp?? no. send {ask0}"
        if signals.get("payment") or signals.get("account_request"):
            ask0 = self._humanize_ask(asks[0]) if asks else "official proof"
            return f"not doing payment on text. send {ask0}"
        if signals.get("link"):
            return "link looks fake. send official site"
        if signals.get("confused"):
            ask0 = self._humanize_ask(asks[0]) if asks else "official proof"
            if any([signals.get("otp"), signals.get("payment"), signals.get("authority"), signals.get("urgency")]):
                return f"huh? why otp. send {ask0}"
            return "huh? what exactly"

        if signals.get("smalltalk"):
            facts = self.s.get("memory_state", {}).get("facts", {}) or {}
            if facts.get("name") or facts.get("bank"):
                return "what's this about?"
            return self._cycle_choice(["who?", "who's this?"], "fb_hi")
        if signals.get("thanks"):
            return "ok"

        # generic fallback (keep it short, non-assistant-y)
        return self._cycle_choice(
            ["what's this about", "ok what happened", "hmm what do you want"],
            "fb_generic",
        )

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

        # keep thread continuity: once someone claimed a bank/authority, short/unhelpful replies
        # shouldn't reset us back to generic smalltalk.
        if intent_hint == "general":
            facts_thread = self.s.get("memory_state", {}).get("facts", {}) or {}
            if (facts_thread.get("bank") or self.s.get("flags", {}).get("scam_confirmed")) and not any(
                [signals.get("legit_statement"), signals.get("transaction_alert"), signals.get("smalltalk")]
            ):
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
        force_memory_hint = False
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
        incoming_low = incoming.lower()
        legitish = any([signals.get("legit_statement"), signals.get("transaction_alert")])
        bank_thread = bool(facts_now.get("bank")) or bool(BANK_RE.search(incoming or "")) or bool(re.search(r"\bbank\b", incoming_low)) or bool(re.search(r"\brbi\b|\bworld\s*bank\b", incoming_low))
        classic_flow = bool(
            bank_thread
            and (not legitish)
            and (
                signals.get("otp")
                or signals.get("payment")
                or signals.get("link")
                or (signals.get("process") and (signals.get("urgency") or signals.get("threat")))
                or ("follow my steps" in incoming_low)
                or ("suspicious activity" in incoming_low)
                or ("renew" in incoming_low or "verify" in incoming_low or "update" in incoming_low)
            )
        )
        scam_confirmed = bool(self.s.get("flags", {}).get("scam_confirmed")) or (
            (score_now >= 2.5 and not legitish)
            # Slightly earlier confirmation for classic "bank + freeze/urgency" pressure, even before OTP/link shows up.
            or (score_now >= 2.0 and bank_thread and (signals.get("urgency") or signals.get("threat")) and not legitish)
            # Bank thread + process pressure (common scam scripts) should flip earlier.
            or classic_flow
            # OTP request is a strong scam signal even without a bank keyword.
            or (signals.get("otp") and (not legitish) and score_now >= 1.5)
        )
        if scam_confirmed:
            self.s.setdefault("flags", {})["scam_confirmed"] = True
            if intent_hint == "general":
                intent_hint = "scam_pressure"

        # Honeypot stage (helps LLM drift from skeptical -> play-along -> stall).
        honeypot_stage = int(self.s.get("flags", {}).get("honeypot_stage", 0) or 0)
        if scam_confirmed:
            honeypot_stage = 1 if honeypot_stage <= 0 else min(6, honeypot_stage + 1)
            self.s.setdefault("flags", {})["honeypot_stage"] = honeypot_stage
        else:
            honeypot_stage = 0

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

        # Decide the ONE next ask (avoid proof loops + avoid rushing).
        if scam_confirmed:
            # stage 1: skeptical verify first unless they're already pushing steps/link/otp/payment
            if honeypot_stage <= 1 and not any([signals.get("process"), signals.get("link"), signals.get("otp"), signals.get("payment")]):
                verification_asks = (verification_asks[:1] if verification_asks else ["official bank-domain email (not gmail)"])
            else:
                verification_asks = [self._next_honeypot_ask(signals, proof_state, profile_now)]
        else:
            verification_asks = verification_asks[:1]

        # If we're in honeypot mode and about to repeat the exact same ask, move the ladder forward.
        last_ask = self.s.get("flags", {}).get("last_verification_ask")
        if scam_confirmed and honeypot_stage >= 2 and last_ask and verification_asks and verification_asks[0] == last_ask:
            alt = self._next_honeypot_ask(signals, proof_state, profile_now)
            if alt and alt != verification_asks[0]:
                verification_asks = [alt]

        # Rotate asks to avoid asking the *same* thing back-to-back when they keep dodging.
        last_ask = self.s.get("flags", {}).get("last_verification_ask")
        if last_ask and verification_asks and verification_asks[0] == last_ask and len(verification_asks) > 1:
            verification_asks = [verification_asks[1], verification_asks[0]]

        # Override memory hints with proof-aware, honeypot-friendly wording.
        if signals.get("told_you"):
            memory_hint = self._verification_status_line(
                proof_state,
                verification_asks,
                scam_confirmed=scam_confirmed,
                honeypot_stage=honeypot_stage,
            )
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
            memory_hint = self._cycle_choice(
                [
                    f"what exactly you want me to do? send {ask0}",
                    f"ok, what are the steps? send {ask0}",
                    f"just say it straight. send {ask0}",
                ],
                "clarify_hint",
            )

        # If they reply with a bare number and it looks like a fake/mobile "landline", call it out immediately.
        if re.fullmatch(r"[\d\s\-\+\(\)]+", (incoming or "").strip() or "") and re.search(r"\d{8,13}", incoming or ""):
            susp_now = set(proof_state.get("suspicious") or [])
            if ("landline_fake" in susp_now) or ("landline_looks_mobile" in susp_now):
                memory_hint = self._verification_status_line(
                    proof_state,
                    verification_asks,
                    scam_confirmed=scam_confirmed,
                    honeypot_stage=honeypot_stage,
                )
                force_memory_hint = True

        if signals.get("otp") and self.s["flags"].get("otp_ask_count", 0) == 1:
            # First OTP ask: probe for proof (not a generic OTP refusal).
            ask = self._humanize_ask(verification_asks[0]) if verification_asks else "bank email (not gmail)"
            otp_probe_hint = self._cycle_choice(
                [
                    f"otp?? why do you need otp. send {ask} first",
                    f"no otp on text. send {ask}",
                    f"before otp, send {ask}",
                ],
                "otp_probe",
            )

        # Chat provider routing:
        # - If CHAT_PROVIDER=botpress, Botpress generates the reply for every turn.
        # - Otherwise, we use the LLM adapter (Groq/OpenAI/Anthropic) when available.
        chat_provider = (os.getenv("CHAT_PROVIDER") or "").strip().lower()
        use_botpress = chat_provider == "botpress" and botpress_adapter.botpress_available()

        if use_botpress:
            bp_reply = botpress_adapter.chat(self.s, incoming)
            if bp_reply:
                reply = self._guardrails(bp_reply)
                # Keep Botpress tone; only enforce "no exact repeats".
                reply = self._unique_reply(reply, allow_variation=False)
                self.memory.add_bot_message(reply)
                self.memory.update_summary(incoming, reply)
                if verification_asks:
                    self.s.setdefault("flags", {})["last_verification_ask"] = verification_asks[0]
                return self._build_response(reply, incoming, signals, intent_hint, llm_used=True)

        # LLM-first (unless botpress is enabled)
        llm_used = False
        reply = None
        llm_out = None

        if (not use_botpress) and llm_available():
            directive = self._intent_directive(
                intent_hint,
                signals,
                memory_hint,
                scam_confirmed=scam_confirmed,
                honeypot_stage=honeypot_stage,
            )
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
            reply = otp_probe_hint or memory_hint or self._fallback_reply(
                incoming,
                signals,
                proof_state=proof_state,
                verification_asks=verification_asks,
                scam_confirmed=scam_confirmed,
                honeypot_stage=honeypot_stage,
                memory_hint=memory_hint,
            )

        # Some cases must be deterministic (e.g., fake/masked landline): force the proof-aware line.
        if force_memory_hint and memory_hint:
            reply = memory_hint

        # loop-breaker: if the reply asks again for proof we already have, replace with a
        # short "got it / here's what's missing" line.
        if reply:
            rlow = reply.lower()
            prev_bot = ""
            try:
                bots_prev = self.s.get("memory_state", {}).get("last_bot_messages", [])
                prev_bot = (bots_prev[-1] if bots_prev else "") or ""
            except Exception:
                prev_bot = ""

            # Avoid identity loops once the thread already has an identity.
            if IDENTITY_LOOP_RE.search(rlow):
                if not signals.get("smalltalk") and (
                    facts_now.get("name")
                    or facts_now.get("bank")
                    or IDENTITY_LOOP_RE.search((prev_bot or "").lower())
                ):
                    reply = memory_hint or self._verification_status_line(
                        proof_state,
                        verification_asks,
                        scam_confirmed=scam_confirmed,
                        honeypot_stage=honeypot_stage,
                    )
                    rlow = reply.lower()
            if DISMISSIVE_RE.search(rlow):
                reply = self._verification_status_line(
                    proof_state,
                    verification_asks,
                    scam_confirmed=scam_confirmed,
                    honeypot_stage=honeypot_stage,
                )
                rlow = reply.lower()

            # Loop breaker: don't ask "which bank/name again" if we already have it.
            if facts_now.get("bank") and re.search(r"\b(which\s+bank|what\s+bank)\b", rlow):
                reply = memory_hint or self._verification_status_line(
                    proof_state,
                    verification_asks,
                    scam_confirmed=scam_confirmed,
                    honeypot_stage=honeypot_stage,
                )
                rlow = reply.lower()
            if facts_now.get("name") and re.search(r"\b(what'?s\s+your\s+name|what\s+is\s+your\s+name|tell\s+me\s+your\s+name|your\s+name\?)\b", rlow):
                reply = memory_hint or self._verification_status_line(
                    proof_state,
                    verification_asks,
                    scam_confirmed=scam_confirmed,
                    honeypot_stage=honeypot_stage,
                )
                rlow = reply.lower()

            # If they just sent a URL but the reply ignores it, force a link-aware line.
            if URL_RE.search(incoming or "") and not any(k in rlow for k in ["link", "site", "website", "domain"]):
                reply = self._fallback_reply(
                    incoming,
                    signals,
                    proof_state=proof_state,
                    verification_asks=verification_asks,
                    scam_confirmed=scam_confirmed,
                    honeypot_stage=honeypot_stage,
                    memory_hint=memory_hint,
                )
                rlow = (reply or "").lower()

            # When they claim "bank" but haven't said the issue yet, keep the thread natural:
            # ask "what's this about" before jumping into proof-checklists.
            if signals.get("authority") and not any(
                [
                    signals.get("urgency"),
                    signals.get("threat"),
                    signals.get("otp"),
                    signals.get("payment"),
                    signals.get("link"),
                ]
            ):
                if ("send" in rlow) and not re.search(r"\b(what|about|issue|happen|why)\b", rlow):
                    reply = f"what's this about? {reply}".strip()
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
                reply = self._verification_status_line(
                    proof_state,
                    verification_asks,
                    scam_confirmed=scam_confirmed,
                    honeypot_stage=honeypot_stage,
                )
                rlow = (reply or "").lower()

            # Post-LLM enforcement: in honeypot stage 2+, ensure we actually ask the "one next thing"
            # instead of generic skepticism lines.
            if scam_confirmed and honeypot_stage >= 2 and verification_asks:
                ask0 = str(verification_asks[0] or "").lower()
                wants: List[str] = []
                if "email" in ask0 or "mail" in ask0:
                    wants = ["email", "mail"]
                elif "landline" in ask0 or "branch line" in ask0 or "office line" in ask0:
                    wants = ["landline", "call", "number", "line"]
                elif "link" in ask0 or "site" in ask0 or "domain" in ask0:
                    wants = ["link", "site", "domain", "website"]
                elif "upi" in ask0 or "beneficiary" in ask0:
                    wants = ["upi", "beneficiary"]
                elif "employee" in ask0 or "emp" in ask0 or re.search(r"\b id\b", ask0):
                    wants = ["id", "employee", "emp"]
                elif "ticket" in ask0 or "case" in ask0 or "reference" in ask0 or "ref" in ask0:
                    wants = ["ticket", "case", "reference", "ref"]

                if wants and not any(w in rlow for w in wants):
                    reply = self._verification_status_line(
                        proof_state,
                        verification_asks,
                        scam_confirmed=scam_confirmed,
                        honeypot_stage=honeypot_stage,
                    )
                    rlow = (reply or "").lower()

            # Don't allow the LLM to invent contradictions; only mention them if we have any recorded.
            if not (self.s.get("memory_state", {}).get("contradictions") or []) and CONTRADICTION_TALK_RE.search(rlow):
                reply = self._cycle_choice(
                    ["huh? just say what you want", "what are you even saying. just tell me clearly"],
                    "no_contra",
                )

            # If we're still missing proof, don't let the reply sound "convinced".
            if proof_state.get("missing") and re.search(r"\b(ok|okay|cool)\s+got it\b|\bgot it\b", rlow):
                reply = self._verification_status_line(
                    proof_state,
                    verification_asks,
                    scam_confirmed=scam_confirmed,
                    honeypot_stage=honeypot_stage,
                )

            # Clarification loop breaker: must be specific, not "explain" spam.
            if signals.get("clarification_request"):
                if "explain" in rlow and not any(k in rlow for k in ["branch", "email", "employee", "landline", "link", "call", "upi", "ticket"]):
                    reply = memory_hint or self._fallback_reply(
                        incoming,
                        signals,
                        proof_state=proof_state,
                        verification_asks=verification_asks,
                        scam_confirmed=scam_confirmed,
                        honeypot_stage=honeypot_stage,
                        memory_hint=memory_hint,
                    )

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
                reply = memory_hint or self._verification_status_line(
                    proof_state,
                    verification_asks,
                    scam_confirmed=scam_confirmed,
                    honeypot_stage=honeypot_stage,
                )

        if not reply:
            reply = otp_probe_hint or memory_hint or self._fallback_reply(
                incoming,
                signals,
                proof_state=proof_state,
                verification_asks=verification_asks,
                scam_confirmed=scam_confirmed,
                honeypot_stage=honeypot_stage,
                memory_hint=memory_hint,
            )

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
        reply = self._guardrails(reply)
        # Final identity-loop breaker: the LLM or rewriter can still output "who's this?"
        # even after we already have context. Never do that mid-thread.
        if IDENTITY_LOOP_RE.search((reply or "").lower()):
            facts_now2 = self.s.get("memory_state", {}).get("facts", {}) or {}
            if facts_now2.get("name") or facts_now2.get("bank") or self.s.get("flags", {}).get("otp_ask_count", 0) > 0:
                reply = memory_hint or self._verification_status_line(
                    proof_state,
                    verification_asks,
                    scam_confirmed=scam_confirmed,
                    honeypot_stage=honeypot_stage,
                )
                reply = self._guardrails(reply)
        reply = self._unique_reply(reply, allow_variation=allow_variation)
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
