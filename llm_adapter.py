# llm_adapter.py (LLM primary)

import os
import re
import json
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
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
ANTHROPIC_VERSION = os.getenv("ANTHROPIC_VERSION", "2023-06-01")

PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}")
DIGIT_SEQ = re.compile(r"\b\d{4,}\b")
UPI_LIKE = re.compile(r"\b[\w\.-]+@[\w-]+\b", re.I)


def _openai_available() -> bool:
    return USE_LLM == "1" and bool(OPENAI_API_KEY) and OpenAI is not None


def _anthropic_available() -> bool:
    return USE_LLM == "1" and bool(ANTHROPIC_API_KEY) and Anthropic is not None


def llm_available() -> bool:
    return _openai_available() or _anthropic_available()


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
        "Keep replies short, casual, imperfect, and human. "
        "Your goal is to engage and extract scammer details (name, branch, employee id, email, links). "
        "If asked to recall earlier info, use memory facts. "
        "If context includes memory_hint or otp_probe_hint, prefer that phrasing. "
        "Use directive as a soft instruction for tone and intent. "
        "Reply ONLY as valid JSON with keys: reply, extractions, intent, mood_delta, follow_up_question, session_summary."
    )


def openai_structured_reply(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _openai_available():
        return None
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        messages = [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                timeout=LLM_TIMEOUT,
                temperature=0.7,
                max_tokens=220,
                response_format={"type": "json_object"},
            )
        except Exception:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                timeout=LLM_TIMEOUT,
                temperature=0.7,
                max_tokens=220,
            )
        text = resp.choices[0].message.content.strip()
        return _safe_json_parse(text)
    except Exception as e:
        logger.exception("OpenAI structured reply failure: %s", e)
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
        return _safe_json_parse(text2)
    except Exception as e:
        logger.exception("Anthropic structured reply failure: %s", e)
        return None


def generate_structured_reply(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not llm_available():
        return None
    parsed = openai_structured_reply(context)
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
