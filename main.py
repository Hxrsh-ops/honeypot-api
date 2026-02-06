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
import uuid
import time
import random
import asyncio
import logging
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_utils import safe_parse_body, redact_sensitive
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
        }
    return SESSIONS[session_id]


def cleanup_session(session_id: str):
    SESSIONS.pop(session_id, None)


def _system_prompt(persona_state: str) -> str:
    place = ""
    if persona_state == "at_work":
        place = "you are at work right now."
    elif persona_state == "on_break":
        place = "you are on a short break right now."
    else:
        place = "you are at home right now."

    return (
        "you are a real human texting on whatsapp/sms. "
        "you just got an unexpected message from an unknown person and you are not sure if its legit. "
        f"{place} "
        "you are cautious and a bit confused, sometimes slightly emotional. "
        "you never accuse the sender directly. "
        "you never share personal or sensitive info (otp, pin, passwords, bank details, account number, upi, address). "
        "you do not sound like customer support, a chatbot, an investigator, or security. "
        "you do not explain your reasoning. "
        "you do not use lists, bullet points, or numbered steps. "
        "write like normal texting: mostly lowercase, short, a little messy. "
        "reply in 1–2 short sentences (max 2 short lines). "
        "ask at most one question. "
        "do not repeat your last message. "
        "if they push for otp/upi/link or say urgent/freeze/block, stall a bit like youre checking, and ask for a simple verification detail casually. "
        "return only the message text. no quotes. no json. no markdown."
    )


def _delay_reply(session: Dict[str, Any]) -> str:
    # Small rotating set to avoid exact repeats without becoming template-y.
    n = int(session.get("turn_count", 0) or 0)
    options = [
        "sorry, give me a moment… im checking something",
        "wait, one sec… im looking",
        "hold on… let me check",
    ]
    return options[n % len(options)]


def _fallback_reply(session: Dict[str, Any]) -> str:
    n = int(session.get("turn_count", 0) or 0)
    options = [
        "hmm… i need to check this properly. can you wait a bit?",
        "uhh give me a bit… i need to look at this",
        "one sec… i need to check something first",
    ]
    return options[n % len(options)]


def _looks_like_meta(text: str) -> bool:
    t = (text or "").lower()
    if not t:
        return True
    bad = [
        "as an ai",
        "as a language model",
        "system prompt",
        "developer message",
        "openai",
        "groq",
        "api",
        "model",
        "temperature",
        "tokens",
    ]
    return any(b in t for b in bad)


def _postprocess_reply(text: str, session: Dict[str, Any]) -> str:
    out = (text or "").strip()
    if not out:
        return _fallback_reply(session)

    # Normalize whitespace; keep at most 2 short lines.
    out = re.sub(r"[ \t]+", " ", out)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    out = "\n".join(lines[:2]).strip()

    # Avoid long rambles (demo-safe).
    if len(out) > 260:
        out = out[:260].rstrip()

    if _looks_like_meta(out):
        return _fallback_reply(session)

    # Avoid list-y formatting if the model ignores instructions.
    if re.search(r"(^|\n)\s*([-*]|\d+\.)\s+", out):
        return _fallback_reply(session)

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
                {"reply": "ok i’ll check this properly and get back later", "session_id": session_id, "ended": True}
            )

        if EXIT_RE.search(incoming):
            farewell = random.choice(["ok bye", "alright bye", "ok, later", "cool, bye"])
            cleanup_session(session_id)
            return JSONResponse({"reply": farewell, "session_id": session_id, "ended": True})

        # Always record the incoming message in history.
        _append_history(session, "user", incoming)

        if invalid_key:
            logger.warning("Invalid API key (soft-allowed); continuing request")

        # Rate-limit safety: minimum delay per session between LLM calls.
        now = time.time()
        last_llm_ts = float(session.get("last_llm_ts", 0.0) or 0.0)
        if bool(session.get("in_flight")) or (now - last_llm_ts < MIN_LLM_DELAY_SEC):
            reply = _delay_reply(session)
            reply = _postprocess_reply(reply, session)
            _append_history(session, "assistant", reply)
            session["turn_count"] = int(session.get("turn_count", 0) or 0) + 1
            return JSONResponse({"reply": reply, "session_id": session_id})

        # Reserve the slot before any await to prevent parallel Groq calls.
        session["in_flight"] = True
        session["last_llm_ts"] = now

        try:
            persona_state = str(session.get("persona_state") or "at_home")
            prompt = _system_prompt(persona_state)
            history = session.get("history", []) or []

            raw_reply = await asyncio.to_thread(
                groq_chat,
                history,
                prompt,
                temperature=0.7,
                max_tokens=120,
            )
        except Exception:
            raw_reply = _fallback_reply(session)
        finally:
            session["in_flight"] = False

        reply = _postprocess_reply(str(raw_reply), session)
        _append_history(session, "assistant", reply)
        session["turn_count"] = int(session.get("turn_count", 0) or 0) + 1

        return JSONResponse({"reply": reply, "session_id": session_id})

    except Exception:
        logger.exception("Honeypot error")
        # Absolute failsafe: never crash, never expose errors.
        session_id = str(uuid.uuid4())
        return JSONResponse({"reply": "hmm… can you give me a minute? i need to check something", "session_id": session_id})


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
    summary = {
        "created": sess.get("created"),
        "last_seen": sess.get("last_seen"),
        "turn_count": sess.get("turn_count", 0),
        "persona_state": sess.get("persona_state"),
        "turns_preview": preview,
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

