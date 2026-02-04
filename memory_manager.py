import random
import time
import re
from typing import Dict, Any, List

from agent_utils import NAME_RE, BANK_RE, PHONE_RE, UPI_RE, URL_RE

FROM_BANK_RE = re.compile(r"\bfrom\s+([a-z][a-z\s]{1,30}?)\s+bank\b", re.I)
BRANCH_RE = re.compile(r"\bbranch(?:\s+name|\s+is)?\s+([a-z][a-z\s]{1,30})\b", re.I)
BRANCH_CITY_RE = re.compile(r"\bbranch\s+(?:in|at)\s+([a-z][a-z\s]{1,30})\b", re.I)
EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
EMP_ID_RE = re.compile(r"\b\d{6,}\b")

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
            extracted["branch"] = branch_m.group(1).strip().lower()

        branch_city = BRANCH_CITY_RE.search(text)
        if branch_city:
            extracted["branch"] = branch_city.group(1).strip().lower()

        email_m = EMAIL_RE.search(text)
        if email_m:
            extracted["email"] = email_m.group(0)

        if IFSC_RE.search(text):
            extracted["ifsc"] = IFSC_RE.search(text).group(0)

        if "id" in text.lower() or "employee" in text.lower():
            emp = EMP_ID_RE.search(text)
            if emp:
                extracted["employee_id"] = emp.group(0)

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
            if not facts.get(k):
                facts[k] = v

        self.mem["facts"] = facts
        self.mem["claims"] = claims
        self.mem["contradictions"] = contradictions[-50:]

        profile = self.s.get("extracted_profile", {})
        for k, v in facts.items():
            if k in profile and not profile.get(k):
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
            return f"you said {name} from {bank} bank, branch {branch}"
        if name and bank and not branch:
            return f"you said {name} from {bank} bank, you didnt give branch"
        if name and not bank:
            return f"you said your name is {name}, no bank yet"
        return "i don't have your name/branch yet"

    def answer_memory_question(self) -> str:
        msgs = self.mem.get("last_user_messages", [])
        if len(msgs) < 2:
            return "not sure, say it again"
        prev = msgs[-2]
        return f"you said '{prev[:60]}'"
