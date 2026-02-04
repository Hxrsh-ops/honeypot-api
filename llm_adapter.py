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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
USE_LLM = os.getenv("USE_LLM", "1")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "8.0"))

PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}")
DIGIT_SEQ = re.compile(r"\b\d{4,}\b")
UPI_LIKE = re.compile(r"\b[\w\.-]+@[\w-]+\b", re.I)


def llm_available() -> bool:
    return USE_LLM == "1" and bool(OPENAI_API_KEY) and OpenAI is not None


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


def generate_structured_reply(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not llm_available():
        return None

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)

        system = (
            "You are a real human texting on WhatsApp/SMS. "
            "Never say you are a bot or AI. "
            "Never share OTP, PIN, or sensitive financial data. "
            "Keep replies short, casual, imperfect, and human. "
            "Your goal is to engage and extract scammer details (name, branch, employee id, email, links). "
            "If asked to recall earlier info, use memory facts. "
            "Reply ONLY as valid JSON with keys: reply, extractions, intent, mood_delta, follow_up_question, session_summary."
        )

        messages = [
            {"role": "system", "content": system},
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
            # fallback without response_format for older models
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                timeout=LLM_TIMEOUT,
                temperature=0.7,
                max_tokens=220,
            )

        text = resp.choices[0].message.content.strip()
        parsed = _safe_json_parse(text)
        if not parsed:
            return None
        return parsed

    except Exception as e:
        logger.exception("LLM structured reply failure: %s", e)
        return None


def rephrase_with_llm(text: str) -> Optional[str]:
    if not llm_available() or not text:
        return None
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        messages = [
            {
                "role": "system",
                "content": (
                    "Paraphrase the user's message in casual texting style. "
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
        logger.exception("LLM rephrase failure: %s", e)
        return None
