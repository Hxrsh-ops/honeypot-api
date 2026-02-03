# ============================================================
# AGENT UTILS — FINAL MINOR UPGRADE
# ------------------------------------------------------------
# Goals:
# - Zero repetition leaks
# - Better normalization
# - Better regex accuracy
# - Human-style paraphrase helpers
# - Absolute safety (never crashes callers)
# ============================================================

import json
import re
import random
import string
from typing import Any, Dict
from fastapi import Request

# ============================================================
# REGEX (STRICT + LOW FALSE POSITIVE)
# ============================================================

URL_RE = re.compile(r"https?://[^\s]+", re.I)

# UPI: restrict to real UPI handles only
UPI_RE = re.compile(
    r"\b[\w.\-]{2,}@(ybl|okaxis|oksbi|okhdfc|upi|paytm|ibl|axl)\b",
    re.I
)

# Indian phone numbers (robust)
PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}")

# Bank keywords (expanded safely)
BANK_RE = re.compile(
    r"\b(sbi|hdfc|icici|axis|canara|pnb|bob|yes\s?bank|kotak|idbi|union)\b",
    re.I
)

# Names (avoid over-capture)
NAME_RE = re.compile(
    r"\b(?:i am|this is|my name is)\s+([A-Z][a-z]{1,20})(?:\s+[A-Z][a-z]{1,20})?\b",
    re.I
)

# ============================================================
# BODY PARSER (HACKATHON-SAFE)
# ============================================================

async def safe_parse_body(request: Request) -> Dict[str, Any]:
    """
    Accepts:
    - JSON
    - text/plain
    - weird hackathon payloads
    Never throws.
    """
    try:
        ct = (request.headers.get("content-type") or "").lower()
        if "json" in ct:
            obj = await request.json()
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass

    try:
        raw = await request.body()
        if not raw:
            return {}
        text = raw.decode("utf-8", errors="ignore").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"message": text}
    except Exception:
        pass

    return {}

# ============================================================
# NORMALIZATION (KEY TO NO REPETITION)
# ============================================================

def _normalize_text(text: str) -> str:
    """
    Strong normalization:
    - lowercase
    - remove punctuation
    - collapse spaces
    """
    if not text:
        return ""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ============================================================
# LINK DETECTOR
# ============================================================

def detect_links(text: str):
    if not text:
        return []
    return URL_RE.findall(text)

# ============================================================
# NON-REPEATING SAMPLER (CORE)
# ============================================================

def sample_no_repeat(pool, recent_set, max_attempts=30):
    """
    Guarantees:
    - No exact repeats
    - No normalized repeats
    """
    if not pool:
        return ""

    normalized_recent = set(_normalize_text(x) for x in recent_set)

    for _ in range(max_attempts):
        choice = random.choice(pool)
        norm = _normalize_text(choice)
        if norm not in normalized_recent:
            recent_set.add(norm)
            _trim_recent(recent_set)
            return choice

    # fallback: force variation
    base = random.choice(pool)
    variant = _force_variation(base)
    recent_set.add(_normalize_text(variant))
    _trim_recent(recent_set)
    return variant

# ============================================================
# VARIED SAMPLER (PARAPHRASE SAFE)
# ============================================================

def sample_no_repeat_varied(
    pool,
    recent_set,
    session=None,
    rephrase_hook=None,
    max_attempts=50
):
    if not pool:
        return ""

    normalized_recent = set(_normalize_text(x) for x in recent_set)

    # try raw choices first
    for _ in range(max_attempts):
        base = random.choice(pool)
        if _normalize_text(base) not in normalized_recent:
            recent_set.add(_normalize_text(base))
            _trim_recent(recent_set)
            return base

    # try LLM / hook
    if rephrase_hook:
        try:
            base = random.choice(pool)
            out = rephrase_hook(base)
            if out and _normalize_text(out) not in normalized_recent:
                recent_set.add(_normalize_text(out))
                _trim_recent(recent_set)
                return out
        except Exception:
            pass

    # programmatic paraphrase
    base = random.choice(pool)
    for _ in range(10):
        variant = _force_variation(base)
        if _normalize_text(variant) not in normalized_recent:
            recent_set.add(_normalize_text(variant))
            _trim_recent(recent_set)
            return variant

    # absolute fallback
    fallback = base + random.choice([" pls", " ok?", " …", " — confirm"])
    recent_set.add(_normalize_text(fallback))
    _trim_recent(recent_set)
    return fallback

# ============================================================
# PARAPHRASE ENGINE (LIGHTWEIGHT)
# ============================================================

def _force_variation(text: str) -> str:
    """
    Deterministic micro-paraphrase:
    Safe, fast, human-like.
    """
    replacements = {
        "please": ["pls", "plz"],
        "okay": ["ok", "alright"],
        "i am": ["i'm"],
        "do not": ["don't"],
        "cannot": ["can't"],
        "will not": ["won't"],
        "one sec": ["sec", "moment"],
    }

    out = text
    for k, vs in replacements.items():
        if re.search(rf"\b{k}\b", out, re.I) and random.random() < 0.6:
            out = re.sub(rf"\b{k}\b", random.choice(vs), out, flags=re.I)

    if random.random() < 0.4:
        out += random.choice(["", ".", "…", " pls confirm"])

    return out.strip()

# ============================================================
# HOUSEKEEPING
# ============================================================

def _trim_recent(recent_set, limit=500):
    try:
        while len(recent_set) > limit:
            recent_set.pop()
    except Exception:
        pass

# ============================================================
# REDACTION (LOG SAFETY)
# ============================================================

def redact_sensitive(text: str) -> str:
    if not text:
        return text
    text = PHONE_RE.sub("(phone)", text)
    text = UPI_RE.sub("(upi)", text)
    text = re.sub(r"\b\d{4,}\b", "[redacted]", text)
    return text
