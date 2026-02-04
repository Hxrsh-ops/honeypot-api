# llm_adapter.py (LLM primary)

import os
import re
import json
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("llm_adapter")

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from anthropic import Anthropic
except Exception:
    Anthropic = None

def _clean_key(value: str) -> str:
    """
    Railway/env var UIs sometimes end up with:
    - accidental surrounding quotes
    - a pasted `Bearer ...` prefix
    - accidentally pasting a whole KEY=VALUE line (we extract the actual key)
    - a leading '=' (common when pasting `KEY = value`)
    - trailing newlines/spaces
    """
    v = (value or "").strip()
    if not v:
        return ""
    if v.lower().startswith("bearer "):
        v = v[7:].strip()
    # strip a single pair of surrounding quotes
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        v = v[1:-1].strip()

    # Some users paste `NAME=secret` or even `NAME = secret` into the VALUE box.
    # Heuristically extract known key prefixes if present anywhere.
    candidates = ["gsk_", "sk-ant-", "sk-"]
    for pref in candidates:
        idx = v.find(pref)
        if idx > 0:
            v = v[idx:]
            break

    # Leading '=' can happen when pasting `KEY = value` and only the value is captured.
    if v.startswith("="):
        v = v.lstrip("=").strip()

    # one more quote strip in case we extracted from a quoted assignment
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        v = v[1:-1].strip()
    return v


OPENAI_API_KEY = _clean_key(os.getenv("OPENAI_API_KEY") or "")
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4").strip()
USE_LLM = (os.getenv("USE_LLM") or "1").strip()
LLM_TIMEOUT = float((os.getenv("LLM_TIMEOUT") or "8.0").strip())
GROQ_API_KEY = _clean_key(os.getenv("GROQ_API_KEY") or "")
GROQ_BASE_URL = (os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1").strip()
GROQ_MODEL = (os.getenv("GROQ_MODEL") or "").strip()
ANTHROPIC_API_KEY = _clean_key(os.getenv("ANTHROPIC_API_KEY") or "")
ANTHROPIC_MODEL = (os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514").strip()
ANTHROPIC_VERSION = (os.getenv("ANTHROPIC_VERSION") or "2023-06-01").strip()

PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}")
DIGIT_SEQ = re.compile(r"\b\d{4,}\b")
UPI_LIKE = re.compile(r"\b[\w\.-]+@[\w-]+\b", re.I)
CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)

# Best-effort debug hook (safe to expose only when explicitly requested).
_LAST_ERROR: Dict[str, Any] = {"provider": "none", "type": "", "error": "", "ts": 0.0}
_GROQ_WORKING_MODEL: str = ""


def _set_last_error(provider: str, err: Exception):
    global _LAST_ERROR
    msg = str(err) if err is not None else ""
    # Avoid dumping huge stack-ish payloads into memory/response.
    _LAST_ERROR = {
        "provider": provider,
        "type": type(err).__name__ if err is not None else "",
        "error": (msg or "")[:320],
        "ts": time.time(),
    }


def last_llm_error() -> Dict[str, Any]:
    return dict(_LAST_ERROR)


def _key_fingerprint(key: str) -> Dict[str, Any]:
    k = (key or "").strip()
    if not k:
        return {"set": False}
    return {
        "set": True,
        "prefix": k[:4],
        "suffix": k[-4:],
        "len": len(k),
    }


def llm_debug_info() -> Dict[str, Any]:
    # Never return raw keys.
    return {
        "use_llm": USE_LLM,
        "openai": {
            "available": _openai_available(),
            "model": OPENAI_MODEL,
            "key": _key_fingerprint(OPENAI_API_KEY),
        },
        "groq": {
            "available": _groq_available(),
            "model": GROQ_MODEL or "",
            "base_url": GROQ_BASE_URL,
            "key": _key_fingerprint(GROQ_API_KEY),
        },
        "anthropic": {
            "available": _anthropic_available(),
            "model": ANTHROPIC_MODEL,
            "key": _key_fingerprint(ANTHROPIC_API_KEY),
        },
    }


def _openai_available() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return USE_LLM == "1" and bool(OPENAI_API_KEY) and OpenAI is not None


def _groq_available() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    # Groq uses the OpenAI-compatible API, so it needs the OpenAI SDK.
    return USE_LLM == "1" and bool(GROQ_API_KEY) and OpenAI is not None


def _anthropic_available() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return USE_LLM == "1" and bool(ANTHROPIC_API_KEY) and Anthropic is not None


def llm_available() -> bool:
    return _openai_available() or _groq_available() or _anthropic_available()


def current_llm_provider() -> str:
    if _openai_available():
        return "openai"
    if _groq_available():
        return "groq"
    if _anthropic_available():
        return "anthropic"
    return "none"


def redact_sensitive(text: str) -> str:
    if not text:
        return text
    text = PHONE_RE.sub("(phone)", text)
    text = DIGIT_SEQ.sub("[redacted]", text)
    text = UPI_LIKE.sub("(UPI)", text)
    return text


def _safe_json_parse(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass

    # try to extract JSON object
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
    except Exception:
        return None
    return None


def _system_prompt() -> str:
    return (
        "You are a real person texting on WhatsApp/SMS (NOT customer support). "
        "Style: mostly lowercase, a bit messy, short + reactive. "
        "Do NOT write stuff like: 'thanks for reaching out', 'how can i help', 'what brings you here', "
        "'purpose of your message', or other assistant-y phrases. "
        "Never say you are a bot or AI. "
        "Never share OTP, PIN, account number, or UPI. "
        "Usually reply in 1 short line; when probing/clarifying you may use 2-4 short lines (no essays). "
        "Ask at most ONE new question per reply (unless clarifying). "
        "Do not repeat the same question in back-to-back turns; acknowledge what they already provided. "
        "If someone claims to be a bank/authority, be skeptical and mildly annoyed; ask for specific proof "
        "(branch landline / bank-domain email / employee id / official link). "
        "If context includes verification_asks, choose from that list (prefer the first). "
        "If context includes proof_state.provided/missing, DO NOT ask again for something already provided; "
        "instead ask for the next missing proof. If they claim 'i already gave it', respond with what you got "
        "and what's still missing (human tone). "
        "If context.scam_confirmed is true, keep them engaged (don't just refuse forever): "
        "sound a bit worried and act like you're checking, but stall and extract info. "
        "Try to get at least ONE item from context.intel_targets per turn when possible. "
        "If asked to recall earlier info, use memory facts; if memory_hint exists, prefer that wording. "
        "Only mention contradictions if contradictions[] is non-empty; do NOT invent contradictions. "
        "Your goal is to keep them talking and extract scammer details (name, branch, employee id, email, links). "
        "Reply ONLY as a single valid JSON object (no markdown, no code fences) with keys: "
        "reply, extractions, intent, mood_delta, follow_up_question, session_summary."
    )


def _model_candidates(primary: str, fallbacks: list[str]) -> list[str]:
    out: list[str] = []
    for m in [primary, *fallbacks]:
        m = (m or "").strip()
        if not m:
            continue
        if m not in out:
            out.append(m)
    return out


def _looks_rate_limited(err: Exception) -> bool:
    s = str(err or "")
    if not s:
        return False
    s_low = s.lower()
    return ("429" in s) or ("too many requests" in s_low) or ("rate limit" in s_low) or ("ratelimit" in s_low)


def _new_openai_client(**kwargs):
    """
    The OpenAI SDK signature changes across versions. Build a client with
    best-effort optional kwargs without crashing.
    """
    if OpenAI is None:
        return None
    try:
        return OpenAI(**kwargs)
    except TypeError:
        # Retry with a smaller set of args (some versions don't accept all kwargs).
        safe = dict(kwargs)
        safe.pop("timeout", None)
        try:
            return OpenAI(**safe)
        except TypeError:
            safe.pop("max_retries", None)
            return OpenAI(**safe)


def _coerce_structured(text: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Groq/open models sometimes ignore JSON-only instructions.
    If parsing fails, degrade gracefully by wrapping plain text as the `reply`.
    """
    if not text:
        return None

    text = text.strip()

    parsed = _safe_json_parse(text)
    if parsed:
        return parsed

    cleaned = CODE_FENCE.sub("", text).strip()
    parsed = _safe_json_parse(cleaned)
    if parsed:
        return parsed

    # As a last resort, treat the entire response as the reply.
    if not cleaned:
        return None

    intent = str(context.get("intent_hint") or context.get("intent") or "general").strip() or "general"
    summary = str(context.get("session_summary") or "").strip()
    return {
        "reply": cleaned,
        "extractions": {},
        "intent": intent,
        "mood_delta": 0.0,
        "follow_up_question": "",
        "session_summary": summary[:240],
    }


def openai_structured_reply(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _openai_available():
        return None

    # Try multiple models (accounts often don't have access to some models).
    fallbacks = [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1-mini",
        "gpt-4.1",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
    ]
    models = _model_candidates(OPENAI_MODEL, fallbacks)

    client = OpenAI(api_key=OPENAI_API_KEY)
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]

    last_err: Optional[Exception] = None
    for model in models:
        try:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=LLM_TIMEOUT,
                    temperature=0.7,
                    max_tokens=300,
                    response_format={"type": "json_object"},
                )
            except Exception:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=LLM_TIMEOUT,
                    temperature=0.7,
                    max_tokens=300,
                )
            text = resp.choices[0].message.content.strip()
            parsed = _coerce_structured(text, context)
            if parsed:
                return parsed
        except Exception as e:
            last_err = e
            continue

    if last_err:
        _set_last_error("openai", last_err)
        logger.warning("OpenAI structured reply failed across models: %s", last_err)
    return None


def groq_structured_reply(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _groq_available():
        return None

    fallbacks = [
        "llama3-70b-8192",
        "llama3-8b-8192",
        "mixtral-8x7b-32768",
        # newer/alt names (won't hurt if unavailable)
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "llama-3.3-70b-specdec",
    ]
    models = _model_candidates(GROQ_MODEL, fallbacks)
    if not models:
        models = fallbacks

    # Groq free tiers can rate-limit aggressively. Disable SDK retries to avoid long hangs,
    # and rely on our rule-based fallback when rate-limited.
    client = _new_openai_client(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        max_retries=0,
        timeout=LLM_TIMEOUT,
    )
    if client is None:
        return None
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]

    global _GROQ_WORKING_MODEL
    if _GROQ_WORKING_MODEL:
        models = _model_candidates(_GROQ_WORKING_MODEL, models)

    last_err: Optional[Exception] = None
    for model in models:
        try:
            # Do NOT use response_format here: Groq OpenAI-compat often rejects it (400),
            # causing 2x calls per turn and quickly hitting 429 on free tiers.
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=LLM_TIMEOUT,
                temperature=0.7,
                max_tokens=300,
            )
            text = resp.choices[0].message.content.strip()
            parsed = _coerce_structured(text, context)
            if parsed:
                _GROQ_WORKING_MODEL = model
                return parsed
        except Exception as e:
            last_err = e
            # If we're rate-limited, don't spam retries/model-fallbacks.
            if _looks_rate_limited(e):
                break
            continue

    if last_err:
        _set_last_error("groq", last_err)
        logger.warning("Groq structured reply failed across models: %s", last_err)
    return None


def anthropic_structured_reply(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _anthropic_available():
        return None
    try:
        client = Anthropic(
            api_key=ANTHROPIC_API_KEY,
            default_headers={"anthropic-version": ANTHROPIC_VERSION},
        )
        user_content = json.dumps(context, ensure_ascii=False)
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=240,
            temperature=0.7,
            system=_system_prompt(),
            messages=[{"role": "user", "content": user_content}],
        )
        text = ""
        try:
            text = "".join([block.text for block in resp.content if hasattr(block, "text")]).strip()
        except Exception:
            text = str(resp.content).strip()
        parsed = _safe_json_parse(text)
        if parsed:
            return parsed

        # one retry with explicit JSON-only hint
        retry_context = dict(context)
        retry_context["force_json_only"] = True
        retry_user = json.dumps(retry_context, ensure_ascii=False)
        resp2 = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=240,
            temperature=0.4,
            system=_system_prompt() + " Return JSON only.",
            messages=[{"role": "user", "content": retry_user}],
        )
        text2 = ""
        try:
            text2 = "".join([block.text for block in resp2.content if hasattr(block, "text")]).strip()
        except Exception:
            text2 = str(resp2.content).strip()
        parsed2 = _safe_json_parse(text2)
        if parsed2:
            return parsed2

        return _coerce_structured(text2, context)
    except Exception as e:
        _set_last_error("anthropic", e)
        logger.exception("Anthropic structured reply failure: %s", e)
        return None


def generate_structured_reply(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not llm_available():
        return None
    parsed = openai_structured_reply(context)
    if parsed:
        return parsed
    parsed = groq_structured_reply(context)
    if parsed:
        return parsed
    return anthropic_structured_reply(context)


def rephrase_with_llm(text: str) -> Optional[str]:
    if not text:
        return None
    if _openai_available():
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Paraphrase the message in casual texting style. "
                        "Keep the same meaning. Do not add new facts. "
                        "Keep it short (1-2 clauses)."
                    ),
                },
                {"role": "user", "content": text},
            ]
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                timeout=LLM_TIMEOUT,
                temperature=0.6,
                max_tokens=80,
            )
            out = resp.choices[0].message.content.strip()
            return redact_sensitive(out)
        except Exception as e:
            logger.exception("OpenAI rephrase failure: %s", e)
            return None
    if _anthropic_available():
        try:
            client = Anthropic(
                api_key=ANTHROPIC_API_KEY,
                default_headers={"anthropic-version": ANTHROPIC_VERSION},
            )
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=80,
                temperature=0.6,
                system=(
                    "Paraphrase the message in casual texting style. "
                    "Keep the same meaning. Do not add new facts. "
                    "Keep it short (1-2 clauses)."
                ),
                messages=[{"role": "user", "content": text}],
            )
            text_out = ""
            try:
                text_out = "".join([block.text for block in resp.content if hasattr(block, "text")]).strip()
            except Exception:
                text_out = str(resp.content).strip()
            return redact_sensitive(text_out)
        except Exception as e:
            logger.exception("Anthropic rephrase failure: %s", e)
            return None
    return None
