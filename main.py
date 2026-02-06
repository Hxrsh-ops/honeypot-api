# ============================================================
# MAIN SERVER — Groq-only honeypot (demo-safe)
# ------------------------------------------------------------
# Guarantees:
# - /honeypot accepts ANY request shape (hackathon safe)
# - Exactly one Groq call per (non-throttled) message
# - Fixed Groq model: llama-3.1-8b-instant
# - Per-session minimum delay between LLM calls (default ~2s)
# - Never crashes; never returns raw errors
# ============================================================

from __future__ import annotations

import os
import re
import urllib.parse
import uuid
import time
import random
import asyncio
import logging
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_utils import safe_parse_body, redact_sensitive, URL_RE
from llm_adapter import groq_chat


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
API_KEY = os.getenv("HONEYPOT_API_KEY", "")
MAX_TURNS = int(os.getenv("MAX_TURNS", "80"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "12"))
MIN_LLM_DELAY_SEC = float(os.getenv("MIN_LLM_DELAY_SEC", "2.0"))
DEBUG_ENDPOINTS = (os.getenv("DEBUG_ENDPOINTS", "0").strip() == "1")

BUILD_ID = os.getenv("KOYEB_GIT_SHA", os.getenv("RAILWAY_GIT_COMMIT_SHA", os.getenv("BUILD_ID", "dev")))

# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("honeypot")

# ------------------------------------------------------------
# APP
# ------------------------------------------------------------
app = FastAPI(title="Honeypot API", version="groq-only")

# ------------------------------------------------------------
# IN-MEMORY SESSION STORE (lightweight)
# ------------------------------------------------------------
SESSIONS: Dict[str, Dict[str, Any]] = {}
sessions = SESSIONS  # compat export for old tests/tools

EXIT_RE = re.compile(r"\b(exit|quit|bye|goodbye|stop)\b", re.I)

# ------------------------------------------------------------
# SIGNALS / INTEL EXTRACTION (lightweight)
# ------------------------------------------------------------
OTP_RE = re.compile(r"\b(otp|one[-\s]?time\s?password|verification\s?code)\b", re.I)
PAYMENT_RE = re.compile(r"\b(upi|transfer|pay|payment|refund|fee)\b", re.I)
URGENCY_RE = re.compile(
    r"\b(urgent|immediate|within|expire|freez(?:e|ing|ed)?|blocked|suspend(?:ed|ing)?|disable(?:d)?|deactivat(?:e|ed)?)\b",
    re.I,
)
AUTHORITY_RE = re.compile(r"\b(bank|fraud|security|official|manager|head office)\b", re.I)
ACCOUNT_REQ_RE = re.compile(r"\b(account\s*(?:number|no\.?)|a/c|acc\s*no\.?)\b", re.I)

EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
PHONE_CAND_RE = re.compile(r"\b\+?\d[\d\s\-\(\)]{7,}\b")
CASE_TICKET_RE = re.compile(r"\b(ticket|case|ref|reference)\b\s*(?:id|no\.?|number|#)?\s*[:\-]?\s*([a-z0-9\-]{4,})", re.I)
EMP_ID_RE = re.compile(r"\b(?:employee\s*id|emp\s*id|staff\s*id|agent\s*id)\b\s*[:#\-]?\s*([a-z0-9\-]{4,})", re.I)
FROM_BANK_RE = re.compile(r"\bfrom\s+([a-z][a-z\s]{1,40}?)\s+bank\b", re.I)
FROM_ORG_RE = re.compile(r"\bfrom\s+([a-z][a-z\s]{1,50})\b", re.I)
BRANCH_RE = re.compile(r"\bbranch(?:\s+name)?\s*(?:is|:|-|at|in)\s*([a-z][a-z\s]{1,30})\b", re.I)
BRANCH_SUFFIX_RE = re.compile(r"\b([a-z][a-z\s]{1,30})\s+branch\b", re.I)
NAME_ROLE_RE = re.compile(r"\b(?:i am|i'm|im|this is)\s+([a-z][a-z\s]{1,40})\b", re.I)

# Meta leak detector (avoid false positives like "kapil" containing "api").
META_RE = re.compile(
    r"(?i)("
    r"as an ai|as a language model|language model|system prompt|developer message|"
    r"\bopenai\b|\bgroq\b|\bapi\b|\bmodel\b|\btemperature\b|\btokens?\b|max_tokens"
    r")"
)

FORBIDDEN_SENSITIVE_REQUEST_RE = re.compile(
    r"(?i)\b(send|share|give|tell|text|message)\b.{0,32}\b("
    r"otp|one[-\s]?time\s?password|verification\s?code|pin|password|upi|account\s*(?:number|no)|cvv"
    r")\b"
)
FORBIDDEN_CALL_REPORT_RE = re.compile(
    r"(?i)\b(call|contact|reach|report)\b.{0,24}\b(bank|police|cyber|support|customer\s*care)\b"
)

TARGET_ORDER = [
    "bank_org",
    "name_role",
    "employee_id",
    "case_ticket",
    "callback_number",
    "official_email",
    "official_website",
    "branch_location",
]

TARGET_HINTS: Dict[str, str] = {
    "bank_org": "which bank/company youre with (exact name)",
    "name_role": "your name and role/title",
    "employee_id": "your employee id",
    "case_ticket": "a case/ticket/reference number",
    "callback_number": "a number i can call you back on",
    "official_email": "an official email address (not gmail)",
    "official_website": "the official website/app name (not a random link)",
    "branch_location": "your branch and city",
}

TARGET_EXAMPLES: Dict[str, str] = {
    "bank_org": "ok wait... which bank/company is this from exactly?",
    "name_role": "ok, what's your full name and role?",
    "employee_id": "ok but what's your employee id?",
    "case_ticket": "do you have a case/ref number? im kinda panicking here",
    "callback_number": "what number can i call you back on?",
    "official_email": "can you message me from your official email (not gmail)?",
    "official_website": "what's the official website/app name? im not opening random links",
    "branch_location": "which branch/city are you from?",
}


def _pick_persona_state() -> str:
    return random.choice(["at_work", "at_home", "on_break"])


def get_session(session_id: str) -> Dict[str, Any]:
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "created": time.time(),
            "last_seen": time.time(),
            "last_llm_ts": 0.0,
            "in_flight": False,
            "persona_state": _pick_persona_state(),
            "history": [],  # list[{role, content}]
            "turn_count": 0,
            "intel": {},
            "last_signals": {},
            "last_ask_key": "",
        }
    return SESSIONS[session_id]


def cleanup_session(session_id: str):
    SESSIONS.pop(session_id, None)

def detect_signals(text: str) -> Dict[str, bool]:
    t = (text or "")
    low = t.lower()
    return {
        "otp": bool(OTP_RE.search(t)),
        "payment": bool(PAYMENT_RE.search(t)),
        "link": bool(URL_RE.search(t)),
        "urgency": bool(URGENCY_RE.search(t)),
        "authority": bool(AUTHORITY_RE.search(t)),
        "account_request": bool(ACCOUNT_REQ_RE.search(t)),
    }


def _digits_count(s: str) -> int:
    return sum(1 for c in (s or "") if c.isdigit())


def _store_intel(session: Dict[str, Any], key: str, value: str):
    if not value:
        return
    intel = session.setdefault("intel", {}) or {}
    session["intel"] = intel
    intel[key] = {"value": value, "ts": time.time()}


def _store_intel_flag(session: Dict[str, Any], key: str):
    intel = session.setdefault("intel", {}) or {}
    session["intel"] = intel
    intel[key] = {"value": True, "ts": time.time()}


def _has_intel(intel: Dict[str, Any], key: str) -> bool:
    v = (intel or {}).get(key)
    if not v:
        return False
    if isinstance(v, dict):
        if v.get("value"):
            return True
        vals = v.get("values")
        return bool(vals)
    return True


def extract_intel(text: str, session: Dict[str, Any]):
    """
    Best-effort extraction of scammer details from incoming text.
    This is only used to steer prompts / avoid repeat asks.
    """
    if not text:
        return

    # Website / domain
    url_m = URL_RE.search(text)
    if url_m:
        raw_url = url_m.group(0)
        try:
            parsed = urllib.parse.urlparse(raw_url)
            host = (parsed.hostname or "").strip().lower()
            if host:
                _store_intel(session, "official_website", host)
            else:
                _store_intel_flag(session, "official_website")
        except Exception:
            _store_intel_flag(session, "official_website")

    # Official email
    email_m = EMAIL_RE.search(text)
    if email_m:
        _store_intel(session, "official_email", email_m.group(0).lower())

    # Case / ticket / reference
    case_m = CASE_TICKET_RE.search(text)
    if case_m:
        _store_intel(session, "case_ticket", case_m.group(2))

    # Employee id
    emp_m = EMP_ID_RE.search(text)
    if emp_m:
        _store_intel(session, "employee_id", emp_m.group(1))

    # Callback number (avoid short OTP-like numbers)
    # Prefer numbers that look like phone/helpline length.
    best_phone = ""
    for m in PHONE_CAND_RE.finditer(text):
        cand = m.group(0)
        d = _digits_count(cand)
        if 8 <= d <= 15:
            best_phone = cand
            break
    if best_phone:
        _store_intel(session, "callback_number", best_phone)

    # Bank / org
    bank_m = FROM_BANK_RE.search(text)
    if bank_m:
        org = bank_m.group(1).strip().lower()
        _store_intel(session, "bank_org", org + " bank")
    else:
        # If they say "from <org>" without "bank", keep as org hint (lightly).
        org_m = FROM_ORG_RE.search(text)
        if org_m and "bank" in (text or "").lower():
            org = org_m.group(1).strip().lower()
            if 2 <= len(org) <= 50:
                _store_intel(session, "bank_org", org)

    # Branch / location
    br = BRANCH_RE.search(text) or BRANCH_SUFFIX_RE.search(text)
    if br:
        loc = br.group(1).strip().lower()
        _store_intel(session, "branch_location", loc)

    # Name / role (rough)
    nr = NAME_ROLE_RE.search(text)
    if nr:
        val = nr.group(1).strip()
        # keep short and non-weird
        if 2 <= len(val) <= 40:
            _store_intel(session, "name_role", val)


def choose_verbosity(session: Dict[str, Any], signals: Dict[str, bool]) -> Dict[str, Any]:
    turn_n = int(session.get("turn_count", 0) or 0)
    pressure = any(
        [
            bool(signals.get("otp")),
            bool(signals.get("payment")),
            bool(signals.get("link")),
            bool(signals.get("urgency")),
            bool(signals.get("authority")),
        ]
    )
    is_long = (turn_n % 4 == 2) or (pressure and (turn_n % 5 == 3))
    if is_long:
        return {
            "mode": "long",
            "max_lines": 4,
            "max_chars": 520,
            "max_tokens": 260,
            "length_hint": "write 3-6 short sentences, a bit rambly, 2-4 lines max. dont reply in just one short sentence",
        }
    return {
        "mode": "short",
        "max_lines": 2,
        "max_chars": 260,
        "max_tokens": 120,
        "length_hint": "keep it short (1-2 short sentences, max 2 short lines)",
    }


def choose_next_target(session: Dict[str, Any], signals: Dict[str, bool]) -> str:
    intel = session.get("intel", {}) or {}
    missing = [k for k in TARGET_ORDER if not _has_intel(intel, k)]
    if not missing:
        return ""

    # Default: first missing in rotation.
    target = missing[0]

    # Overrides
    if bool(signals.get("link")) and (not _has_intel(intel, "official_website")):
        target = "official_website"
    if bool(signals.get("otp")) or bool(signals.get("payment")):
        for k in ["case_ticket", "callback_number", "employee_id"]:
            if not _has_intel(intel, k):
                target = k
                break
    if bool(signals.get("authority")) and (not _has_intel(intel, "employee_id")):
        target = "employee_id"

    if target not in missing:
        target = missing[0]

    last = str(session.get("last_ask_key") or "")
    if target == last and len(missing) > 1:
        idx = missing.index(target) if target in missing else 0
        target = missing[(idx + 1) % len(missing)]

    session["last_ask_key"] = target
    return target


def _system_prompt(
    persona_state: str,
    *,
    length_hint: str,
    target_hint: str,
    target_example: str,
    pressure: bool,
) -> str:
    place = ""
    if persona_state == "at_work":
        place = "you are at work right now."
    elif persona_state == "on_break":
        place = "you are on a short break right now."
    else:
        place = "you are at home right now."

    parts = [
        "you are a real human texting on whatsapp/sms. ",
        "you got an unexpected message and youre not sure if its legit. ",
        f"{place} ",
        "you are worried/confused and a bit cooperative (like you want to fix it), but hesitant. ",
        "you are NOT customer support, NOT a chatbot, NOT an investigator. ",
        "goal: keep them texting and get their details without sounding like security. ",
        "never accuse them directly. ",
        "never share OR request sensitive info (otp, pin, passwords, account number, upi, address). ",
        "never suggest calling/reporting to the bank/police/cyber/etc. ",
        "no lists/bullets/steps. no explaining reasoning. ",
        "style: casual texting, mostly lowercase, a little messy. ",
        f"length: {length_hint}. ",
        "do not repeat your last message. ",
        "do not paste back any full links or long numbers they sent. ",
    ]
    if pressure:
        parts.append("if theyre pushing otp/upi/link/urgent stuff, stall like youre checking and sound a bit scared. ")
    if target_example:
        parts.append(f"ask exactly ONE question and it must be: {target_example} ")
    elif target_hint:
        parts.append(f"ask exactly ONE question about {target_hint}. dont ask vague stuff like 'what is this about'. ")
    else:
        parts.append("ask exactly ONE question to keep them talking. ")
    parts.append("return only the message text. no quotes. no json. no markdown.")
    return "".join(parts)


def _delay_reply(session: Dict[str, Any]) -> str:
    # Small rotating set to avoid exact repeats without becoming template-y.
    n = int(session.get("turn_count", 0) or 0)
    options = [
        "sorry, give me a moment... im checking something",
        "wait, one sec... im looking",
        "hold on... let me check",
    ]
    return options[n % len(options)]


def _fallback_reply(session: Dict[str, Any]) -> str:
    n = int(session.get("turn_count", 0) or 0)
    options = [
        "hmm... i need to check this properly. can you wait a bit?",
        "uhh give me a bit... i need to look at this",
        "one sec... i need to check something first",
    ]
    return options[n % len(options)]

def _safety_fallback(session: Dict[str, Any]) -> str:
    """
    Used when the model tries to request/share sensitive info or gives "stop scam" advice.
    Keep it human and in-character.
    """
    signals = session.get("last_signals", {}) or {}
    target_key = str(session.get("last_ask_key") or "")
    question = TARGET_EXAMPLES.get(target_key) or "ok but what's your employee id?"

    prefix = "hmm wait."
    if bool(signals.get("otp")):
        prefix = "no otp."
    elif bool(signals.get("payment")) or bool(signals.get("account_request")):
        prefix = "no, i'm not sending bank details."
    elif bool(signals.get("link")):
        prefix = "im not clicking links."

    return f"{prefix} {question}".strip()


def _looks_like_meta(text: str) -> bool:
    t = (text or "")
    if not t.strip():
        return True
    return bool(META_RE.search(t))


def _postprocess_reply(text: str, session: Dict[str, Any], *, max_lines: int, max_chars: int) -> str:
    out = (text or "").strip()
    if not out:
        return _fallback_reply(session)

    # Normalize whitespace; keep at most 2 short lines.
    out = re.sub(r"[ \t]+", " ", out)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    out = "\n".join(lines[: max(1, int(max_lines))]).strip()

    # Avoid long rambles (demo-safe).
    if len(out) > int(max_chars):
        out = out[: int(max_chars)].rstrip()

    if _looks_like_meta(out):
        return _fallback_reply(session)

    # Avoid list-y formatting if the model ignores instructions.
    if re.search(r"(^|\n)\s*([-*]|\d+\.)\s+", out):
        return _fallback_reply(session)

    # Safety: never ask for or share sensitive info; never recommend reporting/calling bank/police.
    if FORBIDDEN_SENSITIVE_REQUEST_RE.search(out) or FORBIDDEN_CALL_REPORT_RE.search(out):
        safe = _safety_fallback(session)
        safe = redact_sensitive(safe).strip()
        return safe or _fallback_reply(session)

    out = redact_sensitive(out)
    out = out.strip()
    if not out:
        return _fallback_reply(session)
    return out


def _append_history(session: Dict[str, Any], role: str, content: str):
    hist: List[Dict[str, str]] = session.get("history", []) or []
    hist.append({"role": role, "content": content})
    # trim to the most recent MAX_HISTORY_MESSAGES
    if MAX_HISTORY_MESSAGES > 0 and len(hist) > MAX_HISTORY_MESSAGES:
        hist = hist[-MAX_HISTORY_MESSAGES:]
    session["history"] = hist


@app.api_route("/", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def root():
    return JSONResponse({"status": "alive", "service": "honeypot", "build_id": BUILD_ID, "ts": time.time()})


@app.api_route("/honeypot", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def honeypot(request: Request):
    """
    Hackathon-safe endpoint:
    - accepts any method
    - accepts any body shape
    - never throws raw errors
    """
    try:
        invalid_key = False
        if API_KEY:
            provided = request.headers.get("x-api-key", "")
            if provided != API_KEY:
                logger.warning("Invalid API key attempt (soft-allowed)")
                invalid_key = True

        body = await safe_parse_body(request)

        incoming = (
            body.get("message")
            or body.get("text")
            or body.get("input")
            or body.get("data")
            or body.get("msg")
            or ""
        )
        incoming = str(incoming or "")

        session_id = (
            body.get("session_id")
            or body.get("sid")
            or request.headers.get("x-session-id")
            or str(uuid.uuid4())
        )
        session_id = str(session_id)

        # Empty / health-check payloads should never trigger LLM calls.
        if not incoming.strip():
            return JSONResponse({"reply": "??", "session_id": session_id})

        session = get_session(session_id)
        session["last_seen"] = time.time()

        # Turn limit (demo safety)
        if int(session.get("turn_count", 0) or 0) >= MAX_TURNS:
            cleanup_session(session_id)
            return JSONResponse(
                {"reply": "ok i'll check this properly and get back later", "session_id": session_id, "ended": True}
            )

        if EXIT_RE.search(incoming):
            farewell = random.choice(["ok bye", "alright bye", "ok, later", "cool, bye"])
            cleanup_session(session_id)
            return JSONResponse({"reply": farewell, "session_id": session_id, "ended": True})

        # Always record the incoming message in history.
        _append_history(session, "user", incoming)

        if invalid_key:
            logger.warning("Invalid API key (soft-allowed); continuing request")

        # Signals/intel are guidance only (no templates).
        signals = detect_signals(incoming)
        session["last_signals"] = dict(signals)
        extract_intel(incoming, session)

        # Rate-limit safety: minimum delay per session between LLM calls.
        now = time.time()
        last_llm_ts = float(session.get("last_llm_ts", 0.0) or 0.0)
        if bool(session.get("in_flight")) or (now - last_llm_ts < MIN_LLM_DELAY_SEC):
            reply = _delay_reply(session)
            reply = _postprocess_reply(reply, session, max_lines=2, max_chars=260)
            _append_history(session, "assistant", reply)
            session["turn_count"] = int(session.get("turn_count", 0) or 0) + 1
            return JSONResponse({"reply": reply, "session_id": session_id})

        verbosity = choose_verbosity(session, signals)
        target_key = choose_next_target(session, signals)
        target_hint = TARGET_HINTS.get(target_key, "")
        target_example = TARGET_EXAMPLES.get(target_key, "")
        pressure = any(
            [
                bool(signals.get("otp")),
                bool(signals.get("payment")),
                bool(signals.get("link")),
                bool(signals.get("urgency")),
                bool(signals.get("authority")),
            ]
        )

        # Reserve the slot before any await to prevent parallel Groq calls.
        session["in_flight"] = True
        session["last_llm_ts"] = now

        try:
            persona_state = str(session.get("persona_state") or "at_home")
            prompt = _system_prompt(
                persona_state,
                length_hint=str(verbosity.get("length_hint") or ""),
                target_hint=target_hint,
                target_example=target_example,
                pressure=pressure,
            )
            history = session.get("history", []) or []

            raw_reply = await asyncio.to_thread(
                groq_chat,
                history,
                prompt,
                temperature=0.7,
                max_tokens=int(verbosity.get("max_tokens") or 120),
            )
        except Exception:
            raw_reply = _fallback_reply(session)
        finally:
            session["in_flight"] = False

        reply = _postprocess_reply(
            str(raw_reply),
            session,
            max_lines=int(verbosity.get("max_lines") or 2),
            max_chars=int(verbosity.get("max_chars") or 260),
        )
        _append_history(session, "assistant", reply)
        session["turn_count"] = int(session.get("turn_count", 0) or 0) + 1

        return JSONResponse({"reply": reply, "session_id": session_id})

    except Exception:
        logger.exception("Honeypot error")
        # Absolute failsafe: never crash, never expose errors.
        session_id = str(uuid.uuid4())
        return JSONResponse({"reply": "hmm... can you give me a minute? i need to check something", "session_id": session_id})


@app.get("/sessions/{session_id}")
async def inspect_session(session_id: str):
    if not DEBUG_ENDPOINTS:
        return JSONResponse({"error": "not found"}, status_code=404)
    sess = SESSIONS.get(session_id)
    if not sess:
        return JSONResponse({"error": "not found"}, status_code=404)

    safe: Dict[str, Any] = {}
    for k, v in sess.items():
        if k in {"history"}:
            safe[k] = v[-20:]
        elif k in {"in_flight"}:
            safe[k] = bool(v)
        else:
            safe[k] = v
    return JSONResponse({"session_id": session_id, "session": safe})


@app.get("/sessions/{session_id}/summary")
async def session_summary(session_id: str):
    if not DEBUG_ENDPOINTS:
        return JSONResponse({"error": "not found"}, status_code=404)
    sess = SESSIONS.get(session_id)
    if not sess:
        return JSONResponse({"error": "not found"}, status_code=404)

    # Minimal summary: last few turns + timestamps.
    hist = sess.get("history", []) or []
    preview = hist[-10:]
    intel = sess.get("intel", {}) or {}
    summary = {
        "created": sess.get("created"),
        "last_seen": sess.get("last_seen"),
        "turn_count": sess.get("turn_count", 0),
        "persona_state": sess.get("persona_state"),
        "turns_preview": preview,
        "intel": intel,
        "last_signals": sess.get("last_signals", {}) or {},
        "last_ask_key": sess.get("last_ask_key", ""),
    }
    return JSONResponse({"summary": summary})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level="info",
    )
