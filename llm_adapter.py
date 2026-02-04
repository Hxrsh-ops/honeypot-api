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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
USE_LLM = os.getenv("USE_LLM", "1")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "8.0"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
ANTHROPIC_VERSION = os.getenv("ANTHROPIC_VERSION", "2023-06-01")

PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}")
DIGIT_SEQ = re.compile(r"\b\d{4,}\b")
UPI_LIKE = re.compile(r"\b[\w\.-]+@[\w-]+\b", re.I)
CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)

# Best-effort debug hook (safe to expose only when explicitly requested).
_LAST_ERROR: Dict[str, Any] = {"provider": "none", "type": "", "error": "", "ts": 0.0}


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
        "You are a real human texting on WhatsApp/SMS. "
        "Never say you are a bot or AI. "
        "Never share OTP, PIN, or sensitive financial data. "
        "Keep replies casual, imperfect, and human. "
        "Usually keep it short, but when clarifying/probing you may send 2-4 short lines (not long paragraphs). "
        "Your goal is to engage and extract scammer details (name, branch, employee id, email, links). "
        "If asked to recall earlier info, use memory facts. "
        "If context includes memory_hint or otp_probe_hint, prefer that phrasing. "
        "Use directive as a soft instruction for tone and intent. "
        "Avoid generic loops like 'explain' over and over; ask for specific proof (branch, official email, employee id). "
        "Reply ONLY as a single valid JSON object (no markdown, no code fences) with keys: "
        "reply, extractions, intent, mood_delta, follow_up_question, session_summary. "
        "Example: "
        "{\"reply\":\"...\",\"extractions\":{},\"intent\":\"scam_pressure\",\"mood_delta\":0.0,"
        "\"follow_up_question\":\"\",\"session_summary\":\"...\"}"
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
                    max_tokens=260,
                    response_format={"type": "json_object"},
                )
            except Exception:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=LLM_TIMEOUT,
                    temperature=0.7,
                    max_tokens=260,
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

    client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]

    last_err: Optional[Exception] = None
    for model in models:
        try:
            # Groq OpenAI-compat may not support response_format; try, then fall back.
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=LLM_TIMEOUT,
                    temperature=0.7,
                    max_tokens=260,
                    response_format={"type": "json_object"},
                )
            except Exception:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=LLM_TIMEOUT,
                    temperature=0.7,
                    max_tokens=260,
                )
            text = resp.choices[0].message.content.strip()
            parsed = _coerce_structured(text, context)
            if parsed:
                return parsed
        except Exception as e:
            last_err = e
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
