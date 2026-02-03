# llm_adapter.py (FINAL – OpenAI v1.x compatible)

import os
import re
import time
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
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "6.0"))

PHONE_RE = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}")
DIGIT_SEQ = re.compile(r"\b\d{4,}\b")
UPI_LIKE = re.compile(r"\b[\w\.-]+@[\w-]+\b", re.I)

def redact_sensitive(text: str) -> str:
    if not text:
        return text
    text = PHONE_RE.sub("(phone)", text)
    text = DIGIT_SEQ.sub("[redacted]", text)
    text = UPI_LIKE.sub("(UPI)", text)
    return text


def generate_reply_with_llm(
    session: Dict[str, Any],
    incoming: str,
    strategy: str
) -> Optional[str]:

    if USE_LLM != "1" or not OPENAI_API_KEY or OpenAI is None:
        return None

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a realistic human victim in a scam honeypot. "
                    "Never share OTPs, PINs, or sensitive details. "
                    "Respond naturally, briefly, and cautiously."
                ),
            },
            {
                "role": "user",
                "content": incoming,
            },
        ]

        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            timeout=LLM_TIMEOUT,
            temperature=0.8,
            max_tokens=120,
        )

        text = resp.choices[0].message.content.strip()
        return redact_sensitive(text)

    except Exception as e:
        logger.exception("LLM failure: %s", e)
        return None
