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
    r"\b(?:i am|this is|my name is)\s+([A-Za-z]{2,20})(?:\s+[A-Za-z]{2,20})?\b",
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


def normalize_text(text: str) -> str:
    """
    Public wrapper for normalization.
    Safe for external imports.
    """
    return _normalize_text(text)


def fingerprint_text(text: str) -> str:
    """
    Normalize + remove digits to build a repeat-resistant fingerprint.
    """
    if not text:
        return ""
    text = _normalize_text(text)
    text = re.sub(r"\d+", "", text)
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

    normalized_recent = set(_normalize_text(x) for x in _iter_recent(recent_set))

    for _ in range(max_attempts):
        choice = random.choice(pool)
        norm = _normalize_text(choice)
        if norm not in normalized_recent:
            _add_recent(recent_set, norm)
            return choice

    # fallback: force variation
    base = random.choice(pool)
    variant = _force_variation(base)
    _add_recent(recent_set, _normalize_text(variant))
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

    normalized_recent = set(_normalize_text(x) for x in _iter_recent(recent_set))

    # try raw choices first
    for _ in range(max_attempts):
        base = random.choice(pool)
        if _normalize_text(base) not in normalized_recent:
            _add_recent(recent_set, _normalize_text(base))
            return base

    # try LLM / hook
    if rephrase_hook:
        try:
            base = random.choice(pool)
            out = rephrase_hook(base)
            if out and _normalize_text(out) not in normalized_recent:
                _add_recent(recent_set, _normalize_text(out))
                return out
        except Exception:
            pass

    # programmatic paraphrase
    base = random.choice(pool)
    for _ in range(10):
        variant = _force_variation(base)
        if _normalize_text(variant) not in normalized_recent:
            _add_recent(recent_set, _normalize_text(variant))
            return variant

    # absolute fallback
    fallback = base + random.choice([" pls", " ok?", " …", " — confirm"])
    _add_recent(recent_set, _normalize_text(fallback))
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
        if isinstance(recent_set, list):
            while len(recent_set) > limit:
                recent_set.pop(0)
        else:
            while len(recent_set) > limit:
                recent_set.pop()
    except Exception:
        pass


def _iter_recent(recent_set):
    if isinstance(recent_set, list):
        return recent_set
    if isinstance(recent_set, set):
        return list(recent_set)
    return []


def _add_recent(recent_set, value: str):
    try:
        if isinstance(recent_set, list):
            recent_set.append(value)
            _trim_recent(recent_set)
        else:
            recent_set.add(value)
            _trim_recent(recent_set)
    except Exception:
        pass

# ============================================================
# SCAM SIGNAL + COMPLEXITY (LIGHTWEIGHT)
# ============================================================

_OTP_RE = re.compile(r"\b(otp|one[-\s]?time\s?password|verification\s?code)\b", re.I)
_URGENT_RE = re.compile(r"\b(urgent|immediate|within|expire|freeze|blocked|suspend|suspension|last\s?chance)\b", re.I)
_AUTH_RE = re.compile(r"\b(bank|rbi|world\s?bank|sbi|hdfc|icici|axis|fraud|security|official|manager)\b", re.I)
# Avoid matching plain "account" (common in legit alerts). Only treat account *details* as payment/data signals.
_PAY_RE = re.compile(
    r"\b(upi|transfer|pay|payment|refund|charge|fee|ifsc|beneficiary|amount|transaction|"
    r"account\s*(?:number|no\.?)|acc\s*no\.?|a/c)\b",
    re.I,
)
_THREAT_RE = re.compile(r"\b(block|freeze|legal|police|case|report|fine|penalty|court)\b", re.I)


def scam_signal_score(text: str) -> float:
    """
    Returns a 0-5 score based on common scam signals.
    """
    if not text:
        return 0.0
    score = 0.0
    if URL_RE.search(text):
        score += 1.0
    if _OTP_RE.search(text):
        score += 1.5
    if UPI_RE.search(text) or _PAY_RE.search(text):
        score += 1.0
    if _URGENT_RE.search(text):
        score += 0.8
    if _AUTH_RE.search(text):
        score += 0.6
    if _THREAT_RE.search(text):
        score += 0.8
    return min(score, 5.0)


def classify_message_complexity(text: str) -> str:
    """
    Rough complexity for logging/learning.
    """
    if not text:
        return "empty"
    length = len(text)
    if length < 40:
        return "short"
    if length < 120:
        return "medium"
    return "long"

# ============================================================
# REDACTION (LOG SAFETY)
# ============================================================

def redact_sensitive(text: str) -> str:
    if not text:
        return text
    # Keep masking human-ish; avoid botty "[redacted]" tokens in replies.
    text = PHONE_RE.sub("xxxx", text)
    text = UPI_RE.sub("(upi)", text)
    text = re.sub(r"\b\d{4,}\b", "xxxx", text)
    return text
