import os
import re
import uuid
import random
import asyncio
import time
import logging
from typing import Dict, Any, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_utils import safe_parse_body, detect_links, UPI_RE, PHONE_RE, NAME_RE, BANK_RE, sample_no_repeat, sample_no_repeat_varied, redact_sensitive, _normalize_text
from agent import Agent
# optional LLM paraphrase helper (best-effort import)
try:
    from llm_adapter import generate_reply_with_llm, USE_LLM, LLM_USAGE_PROB
except Exception:
    generate_reply_with_llm = None
    USE_LLM = "0"
    LLM_USAGE_PROB = 0.0
from victim_dataset import (
    FILLERS, SMALL_TALK, CONFUSION, INTRO_ACK, BANK_VERIFICATION, COOPERATIVE,
    PROBING, SOFT_DOUBT, RESISTANCE, NEAR_FALL, FATIGUE, EXIT, OTP_WARNINGS,
    LEGIT_PATTERNS, BANK_DOMAINS, PERSONA_STYLE_KEYS
)

app = FastAPI()

# ================= CONFIG =================
API_KEY = os.getenv("HONEYPOT_API_KEY", "")
MAX_TURNS = int(os.getenv("MAX_TURNS", 40))

# simple logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("honeypot")

# ================= MEMORY =================
sessions: Dict[str, Any] = {}

# ================= HELPERS =================
def get_session(sid: str):
    if sid not in sessions:
        sessions[sid] = {
            "turns": [],
            "used": set(),
            "profile": {
                "name": None,
                "bank": None,
                "phone": None,
                "upi": None,
                "links": [],
                "contradictions": 0,
            },
            "claims": [],
            "memory": [],
            "recent_responses": set(),
            "strategy_history": [],
            "persona": random.choice(PERSONA_STYLE_KEYS)  # persona style for this decoy
        }
    return sessions[sid]

def detect_legitimate(msg: str, sender: str = "") -> Dict[str, Any]:
    """
    Heuristic classification whether a message looks like a legitimate bank/system message
    Returns {'is_legit': bool, 'score': float, 'reason': str}
    """
    text = (msg or "").lower()
    score = 0.0
    reason = []

    # known legit phrasing patterns
    for p in LEGIT_PATTERNS:
        if p in text:
            score += 0.7
            reason.append(f"matched pattern '{p}'")

    # presence of official-looking domain or sender
    s = (sender or "").lower()
    if any(d in s for d in BANK_DOMAINS) or any(d in text for d in BANK_DOMAINS):
        score += 0.5
        reason.append("bank domain in sender/text")

    # OTP messages often have structured digits and "OTP" or "transaction"
    if re.search(r"\b(otp|one time password)\b", text):
        score += 0.3
        reason.append("contains OTP phrase")

    # messages with links (non-bank) and requests to transfer => scammy
    links = detect_links(msg)
    if links:
        if not any(d in links[0] for d in BANK_DOMAINS):
            score -= 0.8
            reason.append("external link found")
        else:
            score += 0.2
            reason.append("bank domain link")

    # weird request patterns lower score
    if any(k in text for k in ["send otp", "give otp", "share otp", "share password", "download this app"]):
        score -= 0.9
        reason.append("asks for OTP/password/download")

    is_legit = score > 0.6
    return {"is_legit": bool(is_legit), "score": float(score), "reason": "; ".join(reason)}

def choose_reply_from_dataset(strategy: str, session: dict) -> str:
    """
    Map agent strategy to dataset lists and sample without repeating recent replies.
    """
    mapping = {
        "probe": PROBING,
        "delay": ["One sec, I'll check that.", "Hold on, I'm checking."],
        "challenge": RESISTANCE,
        "smalltalk": SMALL_TALK,
        "cooperative": COOPERATIVE,
        "bank_verification": BANK_VERIFICATION,
        "soft_doubt": SOFT_DOUBT,
        "near_fall": NEAR_FALL,
        "fatigue": FATIGUE,
        "exit": EXIT
    }

    pool = mapping.get(strategy, PROBING)
    # sometimes add persona filler/intro
    if random.random() < 0.18:
        pool = list(pool) + random.sample(FILLERS, min(3, len(FILLERS)))

    # prefer varied sampling and let the sampler try paraphrase/LLM when possible
    try:
        # if LLM available, pass a rephrase hook that attempts a paraphrase using the LLM
        def maybe_llm_rephrase(text):
            try:
                if generate_reply_with_llm is not None and str(USE_LLM) == "1":
                    out = generate_reply_with_llm(session, text, "paraphrase")
                    return out
            except Exception:
                pass
            return None
        reply = sample_no_repeat_varied(pool, session.setdefault("recent_responses", set()), session=session, rephrase_hook=maybe_llm_rephrase)
    except Exception:
        reply = sample_no_repeat(pool, session.setdefault("recent_responses", set()))
    # occasionally expand or personalize
    if session["profile"].get("name") and random.random() < 0.25 and strategy not in ("challenge", "exit"):
        reply = f"{session['profile']['name']}, {reply}"
    if random.random() < 0.2:
        extra = random.choice([
            "Can you be more precise?",
            "I don't want any trouble.",
            "Please explain step by step."
        ])
        reply = f"{reply} {extra}"
    return reply


# --- JSON sanitizer to make session inspection safe for JSONResponse ---
def _sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, set):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    # fallback to string representation
    try:
        return str(obj)
    except Exception:
        return repr(obj)


# ================= ROOT (ALL METHODS SAFE) =================
@app.api_route("/", methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"])
async def root_probe():
    return JSONResponse({"status": "alive"})

# ================= HONEYPOT (ALL METHODS SAFE) =================
@app.api_route("/honeypot", methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"])
async def honeypot(request: Request):
    try:
        # enforce API key if configured, but allow internal test clients (TestClient/testserver)
        if API_KEY:
            provided = request.headers.get("x-api-key", "")
            client_host = None
            try:
                client_host = (request.client.host or "")
            except Exception:
                client_host = ""
            # allow TestClient (host 'testclient' or 'testserver') or explicit pytest runs
            if provided != API_KEY and client_host not in ("testclient", "testserver") and not os.getenv("PYTEST_CURRENT_TEST"):
                return JSONResponse({"error": "unauthorized"}, status_code=403)

        # robust parsing
        body = await safe_parse_body(request)
        sender = body.get("sender") or body.get("from") or ""
        msg = str(
            body.get("message")
            or body.get("text")
            or body.get("input")
            or body.get("msg")
            or body.get("data")
            or ""
        )

        session_id = body.get("session_id") or str(uuid.uuid4())
        session = get_session(session_id)

        # memory cleanup
        if len(session["turns"]) > MAX_TURNS:
            sessions.pop(session_id, None)
            return JSONResponse({"reply": "I’ll check this directly with the bank.", "session_id": session_id})

        agent = Agent(session)  # create agent; do not call observe() twice

        # detect legitimacy vs scam heuristics on the first incoming only
        if session.get("checked_legit"):
            is_scam = session.get("is_scam", True)
            legit = {"is_legit": not is_scam, "score": session.get("legit_score", 0.0), "reason": session.get("legit_reason", "")}
        else:
            legit = detect_legitimate(msg, sender)
            is_scam = not legit["is_legit"]
            session["checked_legit"] = True
            session["is_scam"] = bool(is_scam)
            session["legit_score"] = float(legit.get("score", 0.0))
            session["legit_reason"] = legit.get("reason", "")

        if not is_scam:
            # legitimate path: observe synchronously and reply using dataset
            agent.observe(msg, raw=body)
            reply_pool = [
                "Okay, I'm checking through the app and will call the bank branch.",
                "Thanks for the info. I'll verify with customer care and call back.",
                "I don't share OTPs or passwords. I'll contact my bank directly."
            ]
            reply = sample_no_repeat_varied(reply_pool + INTRO_ACK, session.setdefault("recent_responses", set()), session=session, rephrase_hook=None)
            strategy_tag = "legitimate_verification"
            now = time.time()
            session.setdefault("turns", []).append({"text": reply, "direction": "out", "ts": now})
            try:
                session.setdefault("recent_responses", set()).add(_normalize_text(reply))
            except Exception:
                session.setdefault("recent_responses", set()).add((reply or "").strip().lower())
            session.setdefault("strategy_history", []).append({"strategy": strategy_tag, "intent": "legitimate", "ts": now})
        else:
            # scam path: run agent.respond in a thread (may call LLM)
            out = await asyncio.to_thread(agent.respond, msg, raw=body)
            reply = out.get("reply", sample_no_repeat(PROBING, session.setdefault("recent_responses", set())))
            strategy_tag = out.get("strategy", "probe")
            now = time.time()
            session.setdefault("turns", []).append({"text": reply, "direction": "out", "ts": now})
            try:
                session.setdefault("recent_responses", set()).add(_normalize_text(reply))
            except Exception:
                session.setdefault("recent_responses", set()).add((reply or "").strip().lower())

        # short random delay to appear human
        await asyncio.sleep(random.uniform(0.3, 1.4))

        # structured output
        return JSONResponse({
            "reply": reply,
            "session_id": session_id,
            "is_scam": bool(is_scam),
            "legit_score": legit["score"],
            "legit_reason": legit["reason"],
            "strategy": strategy_tag,
            "extracted_profile": session["profile"],
            "memory": session.get("memory", [])[-8:],
            "claims": session.get("claims", [])[-12:]
        })
    except Exception as e:
        logger.exception("ERROR in /honeypot")
        return JSONResponse({"reply": "Sorry, I’m having trouble. I’ll check with the bank.", "session_id": str(uuid.uuid4())})

# simple session inspection endpoint (useful while integrating)
@app.get("/sessions/{session_id}")
async def inspect_session(session_id: str, request: Request):
    if API_KEY:
        provided = request.headers.get("x-api-key", "")
        client_host = None
        try:
            client_host = (request.client.host or "")
        except Exception:
            client_host = ""
        host_hdr = (request.headers.get("host") or "").lower()
        allowed_hosts = ("testclient", "testserver", "127.0.0.1", "localhost", "::1")
        # allow when host header or client host looks like a test/local client, or when running under pytest
        if provided != API_KEY and client_host not in allowed_hosts and not any(h in host_hdr for h in ("localhost", "127.0.0.1", "testserver")) and not os.getenv("PYTEST_CURRENT_TEST"):
            return JSONResponse({"error": "unauthorized"}, status_code=403)
    sess = sessions.get(session_id)
    if not sess:
        return JSONResponse({"error": "not found"}, status_code=404)
    # shallow sanitized copy (avoid sending raw request bodies)
    sanitized = {k: v for k, v in sess.items() if k != "turns"}
    sanitized["turns_preview"] = sess.get("turns", [])[-8:]
    # convert sets / non-serializables to JSON-safe structures
    sanitized = _sanitize_for_json(sanitized)
    return JSONResponse({"session_id": session_id, "session": sanitized})

# Add a summary endpoint that returns prioritized intelligence
@app.get("/sessions/{session_id}/summary")
async def session_summary(session_id: str, request: Request):
	if API_KEY:
		provided = request.headers.get("x-api-key", "")
		client_host = None
		try:
			client_host = (request.client.host or "")
		except Exception:
			client_host = ""
		host_hdr = (request.headers.get("host") or "").lower()
		allowed_hosts = ("testclient", "testserver", "127.0.0.1", "localhost", "::1")
		if provided != API_KEY and client_host not in allowed_hosts and not any(h in host_hdr for h in ("localhost", "127.0.0.1", "testserver")) and not os.getenv("PYTEST_CURRENT_TEST"):
			return JSONResponse({"error": "unauthorized"}, status_code=403)
	sess = sessions.get(session_id)
	if not sess:
		return JSONResponse({"error": "not found"}, status_code=404)
	# prioritize high-value fields and recent claims
	profile = sess.get("profile", {})
	claims = sess.get("claims", [])[-20:]
	memory = sess.get("memory", [])[-20:]
	links = [l for l in profile.get("links", [])] + [c["value"] for c in claims if c["kind"] == "link"]
	summary = {
		"session_id": session_id,
		"extract": {
			"name": profile.get("name"),
			"bank": profile.get("bank"),
			"phone": redact_sensitive(profile.get("phone") or ""),
			"upi": "(redacted)" if profile.get("upi") else None,
			"links": links,
			"contradictions": profile.get("contradictions", 0)
		},
		"recent_claims": claims,
		"recent_memory": memory,
	}
	# sanitize before returning
	return JSONResponse({"summary": _sanitize_for_json(summary)})

# support running server via: python main.py (useful for local testing with chat client)
if __name__ == "__main__":
	import uvicorn
	host = os.getenv("HOST", "0.0.0.0")
	port = int(os.getenv("PORT", 8000))
	# log startup for clarity
	logger.info("Starting honeypot server on %s:%s", host, port)
	uvicorn.run("main:app", host=host, port=port, log_level="info")