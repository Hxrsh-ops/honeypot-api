import random
import time
import re
from typing import Dict, Any, List

from agent_utils import NAME_RE, BANK_RE, PHONE_RE, UPI_RE, URL_RE

FROM_BANK_RE = re.compile(r"\bfrom\s+([a-z][a-z\s]{1,30}?)\s+bank\b", re.I)
BRANCH_RE = re.compile(r"\bbranch(?:\s+name)?\s*(?:is|:|-)\s*([a-z][a-z\s]{1,30})\b", re.I)
BRANCH_CITY_RE = re.compile(r"\bbranch\s+(?:in|at)\s+([a-z][a-z\s]{1,30})\b", re.I)
BRANCH_SUFFIX_RE = re.compile(r"\b([a-z][a-z\s]{1,30})\s+branch\b", re.I)
EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
EMP_ID_RE = re.compile(r"\b\d{6,}\b")
LANDLINE_HINT_RE = re.compile(r"(landline|branch\s*line|office\s*line|branch\s*number|office\s*number)", re.I)
LONG_DIGITS_RE = re.compile(r"\b\d{8,13}\b")

FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.in",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "zoho.com",
    "gmx.com",
    "mail.com",
    "yandex.com",
    "rediffmail.com",
}

DEFAULT_PERSONAS = [
    {"state": "at_work", "energy": "medium", "mood": "neutral", "style": "short"},
    {"state": "at_home", "energy": "low", "mood": "tired", "style": "casual"},
    {"state": "on_break", "energy": "medium", "mood": "neutral", "style": "casual"},
]


def ensure_memory(session: Dict[str, Any]) -> Dict[str, Any]:
    mem = session.setdefault("memory_state", {})
    mem.setdefault("facts", {})
    mem.setdefault("claims", {})
    mem.setdefault("contradictions", [])
    mem.setdefault("session_summary", "")
    mem.setdefault("last_user_messages", [])
    mem.setdefault("last_bot_messages", [])

    if "persona" not in mem:
        mem["persona"] = random.choice(DEFAULT_PERSONAS).copy()
        mem["persona"]["skepticism"] = 0.0
    # honor legacy persona_state string if present
    if isinstance(session.get("persona_state"), str):
        mem["persona"]["state"] = session.get("persona_state")

    session.setdefault("extracted_profile", {
        "name": None,
        "bank": None,
        "branch": None,
        "email": None,
        "employee_id": None,
        # optional (not always available)
        "branch_phone": None,
        "ifsc": None,
        "phone": None,
        "upi": None,
        "url": None,
        "account": None,
    })

    session.setdefault("claims", {})
    session.setdefault("memory", [])

    return mem


class MemoryManager:
    def __init__(self, session: Dict[str, Any]):
        self.s = session
        self.mem = ensure_memory(session)

    def add_user_message(self, text: str):
        msgs = self.mem.get("last_user_messages", [])
        msgs.append(text)
        self.mem["last_user_messages"] = msgs[-3:]

    def add_bot_message(self, text: str):
        msgs = self.mem.get("last_bot_messages", [])
        msgs.append(text)
        self.mem["last_bot_messages"] = msgs[-3:]

    def add_event(self, event: Dict[str, Any]):
        mem_list = self.s.get("memory", [])
        mem_list.append(event)
        if len(mem_list) > 200:
            mem_list = mem_list[-200:]
        self.s["memory"] = mem_list

    def update_persona(self, mood_delta: float = 0.0):
        persona = self.mem.get("persona", {})
        try:
            persona["skepticism"] = max(0.0, min(5.0, float(persona.get("skepticism", 0.0)) + mood_delta))
        except Exception:
            pass
        # drift mood/style based on skepticism
        try:
            sk = float(persona.get("skepticism", 0.0))
            if sk >= 4.0:
                persona["mood"] = "annoyed"
                persona["style"] = "short"
            elif sk >= 2.0:
                persona["mood"] = "skeptical"
        except Exception:
            pass
        self.mem["persona"] = persona

    def extract_from_text(self, text: str) -> Dict[str, Any]:
        extracted: Dict[str, Any] = {}
        if not text:
            return extracted

        name_m = NAME_RE.search(text)
        if name_m:
            extracted["name"] = name_m.group(1).strip()

        bank_m = BANK_RE.search(text)
        if bank_m:
            extracted["bank"] = bank_m.group(1).strip().lower()

        from_bank = FROM_BANK_RE.search(text)
        if from_bank and not extracted.get("bank"):
            extracted["bank"] = from_bank.group(1).strip().lower()

        branch_m = BRANCH_RE.search(text)
        if branch_m:
            candidate = branch_m.group(1).strip().lower()
            if not any(x in candidate for x in ["msg", "message", "first", "told", "already"]):
                extracted["branch"] = candidate

        branch_city = BRANCH_CITY_RE.search(text)
        if branch_city:
            candidate = branch_city.group(1).strip().lower()
            if not any(x in candidate for x in ["msg", "message", "first", "told", "already"]):
                extracted["branch"] = candidate

        # "chennai branch" style
        branch_suffix = BRANCH_SUFFIX_RE.search(text)
        if branch_suffix and not extracted.get("branch"):
            candidate = branch_suffix.group(1).strip().lower()
            if not any(x in candidate for x in ["msg", "message", "first", "told", "already"]):
                extracted["branch"] = candidate

        # If we recently asked for branch, a short city/name reply likely IS the branch hint.
        if not extracted.get("branch"):
            last_bot = ""
            try:
                bots = self.mem.get("last_bot_messages", [])
                last_bot = (bots[-1] if bots else "") or ""
            except Exception:
                last_bot = ""
            if "branch" in last_bot.lower():
                candidate = (text or "").strip().lower()
                toks = [t for t in re.split(r"\s+", candidate) if t]
                banned = {
                    "otp", "share", "send", "email", "mail", "id", "account", "upi", "renew", "suspend",
                    "suspicious", "activity", "freeze", "blocked", "call", "link", "verify", "help",
                }
                if (
                    3 <= len(candidate) <= 24
                    and len(toks) <= 3
                    and re.fullmatch(r"[a-z][a-z\s]{2,23}", candidate) is not None
                    and candidate not in {"ok", "okay", "yes", "no", "ya", "yeah", "yep", "sure", "exit", "bye"}
                    and not any(t in banned for t in toks)
                ):
                    extracted["branch"] = candidate

        email_m = EMAIL_RE.search(text)
        if email_m:
            extracted["email"] = email_m.group(0)

        if IFSC_RE.search(text):
            extracted["ifsc"] = IFSC_RE.search(text).group(0)

        if "id" in text.lower() or "employee" in text.lower():
            emp = EMP_ID_RE.search(text)
            if emp:
                extracted["employee_id"] = emp.group(0)

        # Branch/office landline (often 8-12 digits). Don't echo it back in replies.
        if LANDLINE_HINT_RE.search(text):
            m = LONG_DIGITS_RE.search(text)
            if m:
                extracted["branch_phone"] = m.group(0)

        phone = PHONE_RE.search(text)
        if phone:
            extracted["phone"] = phone.group(0)

        upi = UPI_RE.search(text)
        if upi:
            extracted["upi"] = upi.group(0)

        url = URL_RE.search(text)
        if url:
            extracted["url"] = url.group(0)

        return extracted

    def _email_domain(self, email: Any) -> str:
        if not isinstance(email, str) or "@" not in email:
            return ""
        return email.split("@", 1)[1].lower().strip()

    def _is_free_email(self, email: Any) -> bool:
        dom = self._email_domain(email)
        return bool(dom) and dom in FREE_EMAIL_DOMAINS

    def _is_probably_mobile(self, number: Any) -> bool:
        # India mobile numbers are typically 10 digits starting 6-9 (optionally prefixed with +91 which we won't store here).
        s = str(number or "").strip()
        digits = re.sub(r"\D", "", s)
        return bool(
            re.fullmatch(r"[6-9]\d{9}", digits)  # 10-digit mobile
            or re.fullmatch(r"0[6-9]\d{9}", digits)  # 0 + mobile
            or re.fullmatch(r"91[6-9]\d{9}", digits)  # 91 + mobile
            or re.fullmatch(r"[6-9]\d{10}", digits)  # suspicious 11-digit starting like mobile
        )

    def _branch_is_ambiguous(self, branch: Any) -> bool:
        b = (str(branch or "").strip().lower())
        if not b:
            return False
        # Single-token "city" answers are often ambiguous for "branch name".
        toks = [t for t in re.split(r"\s+", b) if t]
        return len(toks) == 1 and len(b) <= 14

    def compute_proof_state(self) -> Dict[str, Any]:
        """
        Determine what the other party has already provided and what we still want.
        This helps avoid looping the same asks.
        """
        facts = self.mem.get("facts", {}) or {}
        bank = facts.get("bank")
        branch = facts.get("branch")
        email = facts.get("email")
        emp = facts.get("employee_id")
        branch_phone = facts.get("branch_phone")

        email_domain = self._email_domain(email)
        free_email = self._is_free_email(email)
        mobile_like_landline = self._is_probably_mobile(branch_phone)
        branch_ambiguous = self._branch_is_ambiguous(branch)

        provided: List[str] = []
        if bank:
            provided.append("bank")
        if branch:
            provided.append("branch")
        if emp:
            provided.append("employee id")
        if email:
            provided.append("email")
        if branch_phone:
            provided.append("branch landline")

        missing: List[str] = []
        suspicious: List[str] = []

        # We prefer a bank-domain email as a strong proof.
        if not email:
            missing.append("official bank-domain email (not gmail)")
        elif free_email:
            suspicious.append("free_email")
            missing.append("official bank-domain email (not gmail)")

        # Branch landline helps (and mobile-looking "landline" is suspicious).
        if not branch_phone:
            missing.append("branch landline (not mobile)")
        elif mobile_like_landline:
            suspicious.append("landline_looks_mobile")
            missing.append("branch landline (not mobile)")

        # Branch name: if they only gave a city, ask for a real branch name.
        if not branch:
            missing.append("branch name (not just city)")
        elif branch_ambiguous:
            suspicious.append("branch_ambiguous")
            missing.append("branch name (not just city)")

        if not emp:
            missing.append("employee id")

        asks = missing[:2]

        return {
            "provided": provided,
            "missing": missing,
            "suspicious": suspicious,
            "asks": asks,
            "email_domain": email_domain,
        }

    def _should_upgrade_fact(self, field: str, prev: Any, new: Any, facts: Dict[str, Any]) -> bool:
        """
        Facts are "best known" values. If we later receive a better value,
        allow upgrading (e.g., gmail -> bank-domain email).
        """
        if not prev:
            return True
        if not new or prev == new:
            return False

        if field == "email":
            # Prefer non-free domains over gmail/outlook/etc.
            prev_free = self._is_free_email(prev)
            new_free = self._is_free_email(new)
            if prev_free and not new_free:
                return True

            # If we know a bank keyword, prefer an email domain containing it.
            bank = str(facts.get("bank") or "").lower().strip()
            prev_dom = self._email_domain(prev)
            new_dom = self._email_domain(new)
            if bank and bank in new_dom and bank not in prev_dom:
                return True
            return False

        if field == "branch":
            # Prefer longer/more specific branch names over short city-only values.
            prev_s = str(prev).strip()
            new_s = str(new).strip()
            if len(new_s) > len(prev_s) + 3:
                return True
            if self._branch_is_ambiguous(prev_s) and not self._branch_is_ambiguous(new_s):
                return True
            return False

        if field == "branch_phone":
            # Prefer a non-mobile-looking landline if previously we only had a mobile-like number.
            if self._is_probably_mobile(prev) and not self._is_probably_mobile(new):
                return True
            return False

        # Default: do not overwrite stable facts like name/bank/employee_id.
        return False

    def merge_extractions(self, extracted: Dict[str, Any], source: str = "regex"):
        if not extracted:
            return

        facts = self.mem.get("facts", {})
        claims = self.mem.get("claims", {})
        contradictions = self.mem.get("contradictions", [])

        for k, v in extracted.items():
            if not v:
                continue
            prev = claims.get(k)
            if prev and prev != v:
                contradictions.append({
                    "field": k,
                    "prev": prev,
                    "new": v,
                    "ts": time.time(),
                    "source": source,
                })
            claims[k] = v
            prev_fact = facts.get(k)
            if not prev_fact or self._should_upgrade_fact(k, prev_fact, v, facts):
                facts[k] = v

        self.mem["facts"] = facts
        self.mem["claims"] = claims
        self.mem["contradictions"] = contradictions[-50:]

        profile = self.s.get("extracted_profile", {})
        for k, v in facts.items():
            if k in profile and v:
                profile[k] = v
        self.s["extracted_profile"] = profile
        self.s["claims"] = claims

    def update_summary(self, user_text: str, bot_text: str):
        facts = self.mem.get("facts", {})
        parts = []
        if facts.get("name"):
            parts.append(f"User says their name is {facts['name']}")
        if facts.get("bank"):
            parts.append(f"claims bank: {facts['bank']}")
        if facts.get("branch"):
            parts.append(f"branch: {facts['branch']}")
        if not parts:
            parts.append("Early conversation, no verified identity yet")
        summary = "; ".join(parts)
        self.mem["session_summary"] = summary

    def answer_profile_question(self) -> str:
        facts = self.mem.get("facts", {})
        name = facts.get("name")
        bank = facts.get("bank")
        branch = facts.get("branch")

        if name and bank and branch:
            return random.choice([
                f"you said {name} from {bank} bank, branch {branch}, right?",
                f"your name is {name} and branch {branch} at {bank}, yeah?",
                f"{name} from {bank} bank, branch {branch} — that's what you said",
            ])
        if name and bank and not branch:
            return random.choice([
                f"your name is {name}, right? i don't think you told me the branch yet",
                f"you said {name} from {bank} bank, but no branch info",
                f"{name} from {bank} — branch missing tho",
            ])
        if name and not bank:
            return random.choice([
                f"you said your name is {name}, but no bank yet",
                f"name was {name}, i didn't catch the bank",
            ])
        return random.choice([
            "i don't have your name/branch yet",
            "not sure, you didn't share name/branch",
        ])

    def answer_verification_status(self) -> str:
        """
        Human-ish summary of what they've provided and what's still missing/suspicious.
        Avoid echoing raw numbers/emails back.
        """
        facts = self.mem.get("facts", {})

        name = facts.get("name")
        bank = facts.get("bank")
        branch = facts.get("branch")
        email = facts.get("email")
        emp = facts.get("employee_id")
        branch_phone = facts.get("branch_phone")

        missing: List[str] = []

        # Use the same proof logic used by the agent to avoid loops.
        proof = self.compute_proof_state()
        free_email = "free_email" in (proof.get("suspicious") or [])
        landline_mobile = "landline_looks_mobile" in (proof.get("suspicious") or [])
        branch_ambiguous = "branch_ambiguous" in (proof.get("suspicious") or [])
        email_domain = str(proof.get("email_domain") or "")

        # Friendly-but-skeptical prioritization.
        if proof.get("missing"):
            missing = list(proof["missing"])

        who = "you"
        if name:
            who = name

        if missing:
            ask = missing[0]
            # keep it short and a bit annoyed
            if free_email and email_domain:
                return random.choice([
                    f"ok {who}, i saw the id/branch stuff but that mail is {email_domain}. not official. send {ask}",
                    f"bro that's a {email_domain} mail. send {ask}",
                    f"ok but that's not bank mail. send {ask}",
                ])
            if landline_mobile and "landline" in ask:
                return random.choice([
                    f"that looks like a mobile number. send {ask}",
                    f"bro that's not a branch landline. send {ask}",
                    f"nah, need the real branch landline. send {ask}",
                ])
            if branch_ambiguous and "branch name" in ask:
                return random.choice([
                    f"you said {branch}, that's just city. send {ask}",
                    f"ok {branch} where exactly? send {ask}",
                    f"city isn't branch name. send {ask}",
                ])
            return random.choice([
                f"you said you're from {bank} bank and gave some details. still need {ask}" if bank else f"you said you're from the bank and gave some details. still need {ask}",
                f"ok i got what you sent. still need {ask}",
                f"you gave the basics, but i still need {ask}",
            ])

        # nothing missing: push them to state the actual issue
        if bank and branch:
            return random.choice([
                f"ok {bank} {branch} branch, got it. what's the issue then?",
                "ok got it. so what's the actual problem?",
                "cool. now tell me what exactly you want from me",
            ])
        return random.choice([
            "ok. what exactly do you want now?",
            "got it. so what's the issue?",
        ])

    def answer_memory_question(self) -> str:
        msgs = self.mem.get("last_user_messages", [])
        if len(msgs) < 2:
            return "not sure, say it again?"
        prev = msgs[-2]
        if not prev:
            return "i didn't catch it, say again?"
        short = prev[:60]
        return random.choice([
            f"you said '{short}'",
            f"you said: {short}",
            f"you mentioned '{short}'",
        ])
