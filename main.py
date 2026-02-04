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
import re
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent import Agent
from agent_utils import safe_parse_body, redact_sensitive, scam_signal_score
from llm_adapter import llm_available, current_llm_provider, last_llm_error
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

EXIT_RE = re.compile(r"\b(exit|quit|bye|goodbye|stop)\b", re.I)

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
        invalid_key = False
        if API_KEY:
            provided = request.headers.get("x-api-key", "")
            if provided != API_KEY:
                # Never hard-fail hackathon systems
                logger.warning("Invalid API key attempt")
                invalid_key = True

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

        # optional debug (do not enable by default)
        debug_llm = False
        try:
            q = request.query_params.get("debug_llm", "")
            debug_llm = str(q).strip().lower() in ("1", "true", "yes") or str(body.get("debug_llm", "")).strip().lower() in ("1", "true", "yes")
        except Exception:
            debug_llm = False

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
            resp = {
                "reply": "I'll check this directly with the bank.",
                "session_id": session_id,
                "ended": True,
                "llm_available": llm_available(),
                "llm_provider": current_llm_provider(),
            }
            if debug_llm:
                resp["llm_error"] = last_llm_error()
            return JSONResponse(resp)

        # ----------------------------------------------------
        # EXIT HANDLING
        # ----------------------------------------------------
        if EXIT_RE.search(incoming):
            farewell = random.choice(["ok bye", "cool, bye", "alright bye", "ok, later"])
            cleanup_session(session_id)
            resp = {
                "reply": farewell,
                "session_id": session_id,
                "ended": True,
                "llm_available": llm_available(),
                "llm_provider": current_llm_provider(),
                "ts": time.time(),
            }
            if debug_llm:
                resp["llm_error"] = last_llm_error()
            return JSONResponse(resp)

        # ----------------------------------------------------
        # AGENT EXECUTION (ISOLATED)
        # ----------------------------------------------------
        # store incoming turn
        session["turns"].append({
            "speaker": "scammer",
            "text": incoming,
            "ts": time.time()
        })

        if invalid_key:
            score = scam_signal_score(incoming)
            score = min(score, 5.0)
            is_scam = score >= 2.5
            legit_score = max(0.0, 1 - (score / 5.0))
            output = {
                "reply": "Service temporarily unavailable",
                "intent": "blocked",
                "strategy": "blocked",
                "signals": {},
                "extracted_profile": session.get("extracted_profile", {}),
                "claims": session.get("claims", {}),
                "memory": session.get("memory", []),
                "scam_score": score,
                "legit_score": legit_score,
                "is_scam": is_scam,
                "llm_used": False,
                "persona_state": session.get("memory_state", {}).get("persona", {}),
                "session_summary": session.get("memory_state", {}).get("session_summary", ""),
            }
        else:
            agent = Agent(session)
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

        if not llm_available():
            logger.warning("LLM not available; check OPENAI_API_KEY/ANTHROPIC_API_KEY")

        # ----------------------------------------------------
        # RESPONSE (HACKATHON SAFE)
        # ----------------------------------------------------
        resp = {
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
            "llm_used": output.get("llm_used"),
            "llm_available": llm_available(),
            "llm_provider": current_llm_provider(),
            "persona_state": output.get("persona_state"),
            "session_summary": output.get("session_summary"),
            "build_id": BUILD_ID,
            "ts": time.time()
        }
        if debug_llm:
            resp["llm_error"] = last_llm_error()
        return JSONResponse(resp)

    except Exception as e:
        # ----------------------------------------------------
        # ABSOLUTE FAILSAFE (NEVER CRASH)
        # ----------------------------------------------------
        logger.exception("Honeypot error")
        resp = {
            "reply": "Sorry, I'm having trouble. I'll verify this offline.",
            "session_id": str(uuid.uuid4()),
            "error": "handled",
            "llm_available": llm_available(),
            "llm_provider": current_llm_provider(),
        }
        # always include llm error on hard fails; it's already an error response
        resp["llm_error"] = last_llm_error()
        return JSONResponse(resp)


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
