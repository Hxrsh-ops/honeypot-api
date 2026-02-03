# ============================================================
# MAIN SERVER — FINAL HARDENED VERSION
# ------------------------------------------------------------
# Guarantees:
# - Accepts ANY request shape (hackathon safe)
# - Never throws invalid request body
# - Works with UptimeRobot HEAD/GET
# - Railway-safe
# - Learning engine fully integrated
# - Agent memory never crashes server
# ============================================================

import os
import uuid
import time
import random
import asyncio
import logging
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent import Agent
from agent_utils import safe_parse_body, redact_sensitive
from learning_engine import persist_learning_snapshot

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
API_KEY = os.getenv("HONEYPOT_API_KEY", "")
MAX_TURNS = int(os.getenv("MAX_TURNS", "60"))
HUMAN_DELAY_MIN = float(os.getenv("DELAY_MIN", "0.4"))
HUMAN_DELAY_MAX = float(os.getenv("DELAY_MAX", "1.6"))
BUILD_ID = os.getenv("RAILWAY_GIT_COMMIT_SHA", os.getenv("BUILD_ID", "dev"))

# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("honeypot")

# ------------------------------------------------------------
# APP
# ------------------------------------------------------------
app = FastAPI(
    title="Agentic Honeypot API",
    version="1.0-final",
)

# ------------------------------------------------------------
# IN-MEMORY SESSION STORE
# (Swap to Redis later if needed)
# ------------------------------------------------------------
SESSIONS: Dict[str, Dict[str, Any]] = {}
# compat export for tests
sessions = SESSIONS


# ============================================================
# SESSION HANDLING
# ============================================================
def get_session(session_id: str) -> Dict[str, Any]:
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "created": time.time(),
            "last_seen": time.time(),
        }
    return SESSIONS[session_id]


def cleanup_session(session_id: str):
    sess = SESSIONS.pop(session_id, None)
    if sess:
        try:
            persist_learning_snapshot()
        except Exception:
            pass


def build_session_summary(session: Dict[str, Any]) -> Dict[str, Any]:
    extract = session.get("extracted_profile", {}) or {}
    if "name" not in extract:
        extract["name"] = None
    if "bank" not in extract:
        extract["bank"] = None
    return {
        "extract": extract,
        "stats": {
            "turns": len(session.get("turns", [])),
            "created": session.get("created"),
            "last_seen": session.get("last_seen"),
        },
        "memory_count": len(session.get("memory", [])),
    }


# ============================================================
# ROOT — HEALTH CHECK (UPTIMEROBOT SAFE)
# ============================================================
@app.api_route(
    "/",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
)
async def root():
    return JSONResponse({
        "status": "alive",
        "service": "honeypot",
        "build_id": BUILD_ID,
        "ts": time.time()
    })


# ============================================================
# HONEYPOT ENDPOINT — CORE
# ============================================================
@app.api_route(
    "/honeypot",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
)
async def honeypot(request: Request):
    """
    This endpoint intentionally:
    - Accepts ANY method
    - Accepts ANY body shape
    - Never throws 4xx for bad payloads
    """

    try:
        # ----------------------------------------------------
        # API KEY (soft enforcement)
        # ----------------------------------------------------
        if API_KEY:
            provided = request.headers.get("x-api-key", "")
            if provided != API_KEY:
                # Never hard-fail hackathon systems
                logger.warning("Invalid API key attempt")
                return JSONResponse(
                    {"reply": "Service temporarily unavailable"},
                    status_code=200
                )

        # ----------------------------------------------------
        # SAFE BODY PARSING
        # ----------------------------------------------------
        body = await safe_parse_body(request)

        # Support ALL possible field names
        incoming = (
            body.get("message")
            or body.get("text")
            or body.get("input")
            or body.get("data")
            or body.get("msg")
            or ""
        )

        incoming = str(incoming)

        session_id = (
            body.get("session_id")
            or body.get("sid")
            or request.headers.get("x-session-id")
            or str(uuid.uuid4())
        )

        session = get_session(session_id)
        session["last_seen"] = time.time()
        session.setdefault("turns", [])

        # ----------------------------------------------------
        # TURN LIMIT SAFETY
        # ----------------------------------------------------
        if len(session.get("turns", [])) > MAX_TURNS:
            cleanup_session(session_id)
            return JSONResponse({
                "reply": "I’ll check this directly with the bank.",
                "session_id": session_id,
                "ended": True
            })

        # ----------------------------------------------------
        # AGENT EXECUTION (ISOLATED)
        # ----------------------------------------------------
        agent = Agent(session)
        # store incoming turn
        session["turns"].append({
            "speaker": "scammer",
            "text": incoming,
            "ts": time.time()
        })

        output = await asyncio.to_thread(
            agent.respond,
            incoming,
            raw=body
        )

        reply = output.get("reply", "Hmm.")
        reply = redact_sensitive(reply)

        # ----------------------------------------------------
        # HUMAN DELAY (ANTI-BOT SIGNAL)
        # ----------------------------------------------------
        await asyncio.sleep(
            random.uniform(HUMAN_DELAY_MIN, HUMAN_DELAY_MAX)
        )

        # store outgoing turn
        session["turns"].append({
            "speaker": "bot",
            "text": reply,
            "ts": time.time(),
            "phases": output.get("phases_used"),
            "strategy": output.get("strategy"),
        })

        # ----------------------------------------------------
        # RESPONSE (HACKATHON SAFE)
        # ----------------------------------------------------
        return JSONResponse({
            "reply": reply,
            "session_id": session_id,
            "incoming_preview": incoming[:120],
            "intent": output.get("intent"),
            "strategy": output.get("strategy"),
            "phases_used": output.get("phases_used"),
            "signals": output.get("signals"),
            "extracted_profile": output.get("extracted_profile"),
            "claims": output.get("claims"),
            "memory": output.get("memory"),
            "scam_score": output.get("scam_score"),
            "legit_score": output.get("legit_score"),
            "is_scam": output.get("is_scam"),
            "build_id": BUILD_ID,
            "ts": time.time()
        })

    except Exception as e:
        # ----------------------------------------------------
        # ABSOLUTE FAILSAFE (NEVER CRASH)
        # ----------------------------------------------------
        logger.exception("Honeypot error")
        return JSONResponse({
            "reply": "Sorry, I’m having trouble. I’ll verify this offline.",
            "session_id": str(uuid.uuid4()),
            "error": "handled"
        })


# ============================================================
# SESSION INSPECTION (DEBUG / JUDGES)
# ============================================================
@app.get("/sessions/{session_id}")
async def inspect_session(session_id: str):
    sess = SESSIONS.get(session_id)
    if not sess:
        return JSONResponse({"error": "not found"}, status_code=404)

    safe = {}
    for k, v in sess.items():
        if k == "turns":
            safe["turns_preview"] = v[-10:]
        elif k == "recent_responses" and isinstance(v, set):
            safe[k] = list(v)
        else:
            safe[k] = v

    return JSONResponse({
        "session_id": session_id,
        "session": safe
    })


# ============================================================
# SESSION SUMMARY (JUDGES / TESTS)
# ============================================================
@app.get("/sessions/{session_id}/summary")
async def session_summary(session_id: str):
    sess = SESSIONS.get(session_id)
    if not sess:
        return JSONResponse({"error": "not found"}, status_code=404)
    summary = build_session_summary(sess)
    return JSONResponse({"summary": summary})


# ============================================================
# LOCAL RUN SUPPORT
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level="info"
    )
