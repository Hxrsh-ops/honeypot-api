import os
import re
import uuid
import random
import asyncio
import time
from typing import Dict, Any, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_utils import safe_parse_body, detect_links, UPI_RE, PHONE_RE, NAME_RE, BANK_RE, sample_no_repeat
from agent import Agent
from victim_dataset import (
    FILLERS, SMALL_TALK, CONFUSION, INTRO_ACK, BANK_VERIFICATION, COOPERATIVE,
    PROBING, SOFT_DOUBT, RESISTANCE, NEAR_FALL, FATIGUE, EXIT, OTP_WARNINGS,
    LEGIT_PATTERNS, BANK_DOMAINS, PERSONA_STYLE_KEYS
)

app = FastAPI()

# ================= CONFIG =================
API_KEY = os.getenv("HONEYPOT_API_KEY", "")
MAX_TURNS = int(os.getenv("MAX_TURNS", 40))

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
        # enforce API key if configured
        if API_KEY:
            provided = request.headers.get("x-api-key", "")
            if provided != API_KEY:
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

        # instantiate a single agent and record observation once
        agent = Agent(session)
        agent.observe(msg, raw=body)

        # memory cleanup
        if len(session["turns"]) > MAX_TURNS:
            sessions.pop(session_id, None)
            return JSONResponse({"reply": "I’ll check this directly with the bank.", "session_id": session_id})

        # classify intent & strategy
        intent = agent.detect_intent(msg)
        strategy = agent.choose_strategy(intent)

        # detect legitimacy vs scam heuristics
        legit = detect_legitimate(msg, sender)
        is_scam = not legit["is_legit"]

        # If looks legitimate: treat carefully (no deception), respond like normal customer
        if not is_scam:
            # choose cautious verification style
            reply_pool = [
                "Okay, I'm checking through the app and will call the bank branch.",
                "Thanks for the info. I'll verify with customer care and call back.",
                "I don't share OTPs or passwords. I'll contact my bank directly."
            ]
            # include dataset polite replies
            reply = sample_no_repeat(reply_pool + INTRO_ACK, session.setdefault("recent_responses", set()))
            strategy_tag = "legitimate_verification"
        else:
            # scam path: choose reply based on strategy + agent state
            # prefer agent.generate_reply for coherence with persona/state
            # safety enforcement: never reveal OTP, never perform transactions
            if re.search(r"\b(otp|one time password|pin|password)\b", msg.lower()):
                reply = random.choice(OTP_WARNINGS)
                strategy_tag = "challenge"
            else:
                # let agent generate a reply (uses recent responses internally)
                reply = agent.generate_reply(strategy, msg)
                strategy_tag = strategy

        # record outgoing reply in session (keeps conversation state)
        now = time.time()
        session.setdefault("turns", []).append({"text": reply, "direction": "out", "ts": now})
        session.setdefault("recent_responses", set()).add(reply)
        session.setdefault("strategy_history", []).append({"strategy": strategy_tag, "intent": intent, "ts": now})

        # short random delay to appear human
        await asyncio.sleep(random.uniform(0.3, 1.4))

        # return structured output, useful to hackathon checker
        return JSONResponse({
            "reply": reply,
            "session_id": session_id,
            "is_scam": bool(is_scam),
            "legit_score": legit["score"],
            "legit_reason": legit["reason"],
            "strategy": strategy_tag,
            "intent": intent,
            "extracted_profile": session["profile"],
            "memory": session.get("memory", [])[-8:],  # recent memory
            "claims": session.get("claims", [])[-12:]
        })
    except Exception as e:
        # never crash the endpoint; return safe fallback
        print("ERROR in /honeypot:", str(e))
        return JSONResponse({"reply": "Sorry, I’m having trouble. I’ll check with the bank.", "session_id": str(uuid.uuid4())})

# simple session inspection endpoint (useful while integrating)
@app.get("/sessions/{session_id}")
async def inspect_session(session_id: str, request: Request):
    if API_KEY:
        provided = request.headers.get("x-api-key", "")
        if provided != API_KEY:
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