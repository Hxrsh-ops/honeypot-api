import json, re, random
from typing import Any, Dict, Optional
from fastapi import Request

URL_RE = re.compile(r"https?://[^\s]+", re.I)
# more generic UPI pattern (captures usual id@bank style)
UPI_RE = re.compile(r"\b[\w\.-]+@[\w-]+\b", re.I)
PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}")
BANK_RE = re.compile(r"(sbi|hdfc|icici|axis|canara|pnb|bob|yesbank|kotak)", re.I)
# capture multi-word names after common phrases
NAME_RE = re.compile(r"(?:\b(?:i am|this is|my name is)\b)\s+([A-Za-z][A-Za-z\s]{0,40})", re.I)

async def safe_parse_body(request: Request) -> Dict[str, Any]:
    # Robust body parsing: JSON if possible, otherwise raw text under "message"
    try:
        ct = request.headers.get("content-type", "")
        if "json" in ct.lower():
            obj = await request.json()
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    try:
        raw = await request.body()
        if not raw:
            return {}
        text = raw.decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"message": text}
    except Exception:
        pass
    return {}

def detect_links(text: str):
    return URL_RE.findall(text)

def sample_no_repeat(pool, recent_set, max_attempts=20):
    for _ in range(max_attempts):
        c = random.choice(pool)
        if c not in recent_set:
            recent_set.add(c)
            if len(recent_set) > 200:
                # keep small; using pop on set is fine
                recent_set.pop()
            return c
    return random.choice(pool)

# new: simple redaction util (useful for logs / outputs)
def redact_sensitive(text: str) -> str:
    """
    Redact phone numbers, long digit sequences and UPI-like tokens from text.
    """
    if not text:
        return text
    red = PHONE_RE.sub("(phone)", text)
    red = re.sub(r"\b\d{4,}\b", "[redacted]", red)
    red = UPI_RE.sub("(UPI)", red)
    return red