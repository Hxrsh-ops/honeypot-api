import json, re, random
from typing import Any, Dict, Optional
from fastapi import Request

URL_RE = re.compile(r"https?://[^\s]+", re.I)
UPI_RE = re.compile(r"\b[\w\.-]+@(?:ybl|okaxis|oksbi|okhdfc|upi)\b", re.I)
PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}")
BANK_RE = re.compile(r"(sbi|hdfc|icici|axis|canara|pnb|bob)", re.I)
NAME_RE = re.compile(r"(?:i am|this is|my name is)\s+([A-Za-z]+)", re.I)

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
                # keep small
                recent_set.pop()
            return c
    return random.choice(pool)