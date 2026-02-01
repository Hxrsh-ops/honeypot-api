import os
import re
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("llm_adapter")

try:
    import openai
except Exception:
    openai = None

# Config via env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
USE_LLM = os.getenv("USE_LLM", "1")  # "1" to enable
LLM_USAGE_PROB = float(os.getenv("LLM_USAGE_PROB", "0.6"))  # probability to use LLM when available
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "6.0"))  # seconds

PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}")
DIGIT_SEQ = re.compile(r"\b\d{4,}\b")  # sequences of 4+ digits
UPI_LIKE = re.compile(r"\b[\w\.-]+@(?:\w+)\b", re.I)

def _redact_sensitive(text: str) -> str:
    # Replace phone numbers, long digit sequences and UPI-like patterns
    text = PHONE_RE.sub("(phone)", text)
    text = DIGIT_SEQ.sub("[redacted]", text)
    text = UPI_LIKE.sub("(UPI)", text)
    return text

def _build_messages(session: Dict[str, Any], incoming: str, strategy: str) -> list:
    persona = session.get("persona", "confused")
    profile = {k: v for k, v in session.get("profile", {}).items() if k not in ("phone", "upi")}
    recent_turns = session.get("turns", [])[-6:]
    context_lines = []
    for t in recent_turns:
        role = "You" if t.get("direction") == "out" else "Them"
        context_lines.append(f"{role}: {t.get('text')}")
    context = "\n".join(context_lines)
    sys = (
        "You are a simulated human victim in a scam-detection honeypot. "
        "Respond as a plausible human according to the persona and the profile. "
        "Do NOT provide any OTPs, PINs, account numbers, or any sensitive numeric values. "
        "If asked for OTP or PIN, refuse politely. If asked for account/UPI details, probe and request exact fields but never fabricate them. "
        "Keep replies short, natural, and varied (use occasional hesitations like 'hmm', 'one sec')."
    )
    user = (
        f"Persona: {persona}\nProfile(RED): {profile}\nContext:\n{context}\nIncoming: {incoming}\nStrategy: {strategy}\n\n"
        "Provide a concise (1-2 sentence) human reply only."
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]

def generate_reply_with_llm(session: Dict[str, Any], incoming: str, strategy: str, timeout: Optional[float] = None) -> Optional[str]:
    """
    Return a single reply string from the LLM or None if unavailable.
    The output is sanitized and redacted to avoid leaking sensitive information.
    """
    if USE_LLM != "1":
        return None
    if not OPENAI_API_KEY or openai is None:
        return None

    try:
        openai.api_key = OPENAI_API_KEY
        messages = _build_messages(session, incoming, strategy)
        resp = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.85,
            max_tokens=150,
            request_timeout=timeout or LLM_TIMEOUT
        )
        text = ""
        try:
            # safe extraction for different SDK response shapes
            choice = resp.choices[0]
            if hasattr(choice, "message"):
                # object-like
                text = getattr(choice.message, "get", lambda k, d=None: None)("content") or getattr(choice.message, "content", "")
            elif isinstance(choice, dict):
                text = (choice.get("message") or {}).get("content", "") or choice.get("text", "") or ""
        except Exception:
            text = getattr(resp.choices[0], "text", "") if resp and getattr(resp, "choices", None) else ""

        text = (text or "").strip()
        if not text:
            return None

        # simple sanitation and redaction
        text = _redact_sensitive(text)
        text = text.split("\n")[0].strip()  # keep concise
        if len(text) < 2:
            return None
        if DIGIT_SEQ.search(text):
            text = DIGIT_SEQ.sub("[redacted]", text)

        # record lightweight LLM usage note in session memory
        try:
            session.setdefault("memory", []).append({
                "type": "llm_used",
                "model": OPENAI_MODEL,
                "when": time.time(),
                "snippet": text[:120]
            })
        except Exception:
            pass

        return text
    except Exception:
        logger.exception("LLM generation failed")
        return None
