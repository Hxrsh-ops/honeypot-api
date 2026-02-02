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

def _normalize_text(s: str) -> str:
    return (s or "").strip().lower()


def sample_no_repeat(pool, recent_set, max_attempts=20):
    # track normalized values to detect repeats regardless of capitalization/punctuation
    # recent_set may contain raw or already-normalized strings; build normalized view
    normalized = set(_normalize_text(x) for x in recent_set)
    for _ in range(max_attempts):
        c = random.choice(pool)
        if _normalize_text(c) not in normalized:
            # store normalized form to prevent equivalent future replies
            try:
                recent_set.add(_normalize_text(c))
            except Exception:
                pass
            normalized.add(_normalize_text(c))
            if len(recent_set) > 200:
                # keep small; using pop on set is fine
                recent_set.pop()
            return c
    # as fallback, return a random choice but prefer one with a different normalized form if possible
    for c in pool:
        if _normalize_text(c) not in normalized:
            try:
                recent_set.add(_normalize_text(c))
            except Exception:
                pass
            return c
    return random.choice(pool)


def sample_no_repeat_varied(pool, recent_set, session=None, rephrase_hook=None, max_attempts=40):
    """
    Choose an element from pool avoiding exact repeats (based on recent_set).
    If all items are already used, attempt to generate a paraphrase (via rephrase_hook)
    or programmatically produce a rephrased variant that is not in recent_set.
    """
    # first, try to pick an unused item
    # recent_set may already contain normalized entries; build normalized view
    normalized = set(_normalize_text(x) for x in recent_set)
    for _ in range(max_attempts):
        c = random.choice(pool)
        if _normalize_text(c) not in normalized:
            try:
                recent_set.add(_normalize_text(c))
            except Exception:
                pass
            normalized.add(_normalize_text(c))
            if len(recent_set) > 400:
                recent_set.pop()
            return c

    # all items may have been used; try to paraphrase a base item
    base = random.choice(pool)

    # attempt LLM or provided rephrase_hook first
    if rephrase_hook:
        try:
            new_text = rephrase_hook(base)
            if new_text and _normalize_text(new_text) not in normalized and new_text != base:
                try:
                    recent_set.add(_normalize_text(new_text))
                except Exception:
                    pass
                if len(recent_set) > 400:
                    recent_set.pop()
                return new_text
        except Exception:
            pass

    # fallback programmatic paraphrase: contractions, add filler, or split into two sentences
    def programmatic_paraphrase(s):
        s2 = s
        # simple contractions / slang replacements
        replacements = {
            "do not": "don't",
            "does not": "doesn't",
            "i will": "i'll",
            "i am": "i'm",
            "please": "pls",
            "okay": "ok",
            "one sec": "one sec..",
            "I will not": "I won't",
            "I never share": "I never share"
        }
        for a, b in replacements.items():
            s2 = re.sub(r"\b" + re.escape(a) + r"\b", b, s2, flags=re.I)
        # add a short filler or an extra clause
        extras = ["Thanks.", "Pls be precise.", "Can you confirm?", "I need more details."]
        if random.random() < 0.5:
            s2 = s2 + " " + random.choice(extras)
        # make sure different characters / punctuation
        if s2 == s:
            s2 = s + "..."
        return s2.strip()

    for _ in range(10):
        cand = programmatic_paraphrase(base)
        if _normalize_text(cand) not in normalized and cand != base:
            try:
                recent_set.add(_normalize_text(cand))
            except Exception:
                pass
            if len(recent_set) > 400:
                recent_set.pop()
            return cand

    # as a last resort, append a random filler to the base
    fallback = base + " " + random.choice(["(confirm?)", "(pls)", "- ok?", "...pls reply"]) 
    try:
        recent_set.add(_normalize_text(fallback))
    except Exception:
        pass
    if len(recent_set) > 400:
        recent_set.pop()
    return fallback

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