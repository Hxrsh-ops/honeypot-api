# llm_adapter.py — Groq-only (single-call) adapter
#
# Goals:
# - Exactly one Groq call per message (no fallbacks, no retries across models)
# - Fixed model: llama-3.1-8b-instant
# - OpenAI SDK (Groq is OpenAI-compatible)
#
# This module intentionally does NOT implement multi-provider routing.

from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List

logger = logging.getLogger("llm_adapter")

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


def _clean_key(value: str) -> str:
    """
    Host env var UIs sometimes end up with:
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
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        v = v[1:-1].strip()
    if "=" in v and ("gsk_" in v or "sk-" in v):
        # if someone pasted KEY=VALUE, keep the RHS
        parts = v.split("=", 1)
        v = (parts[1] or "").strip()
    if v.startswith("="):
        v = v.lstrip("=").strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        v = v[1:-1].strip()
    return v


GROQ_API_KEY = _clean_key(os.getenv("GROQ_API_KEY") or "")
GROQ_BASE_URL = (os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1").strip()
LLM_TIMEOUT = float((os.getenv("LLM_TIMEOUT") or "8.0").strip())

# Hardcoded (no env override)
GROQ_MODEL = "llama-3.1-8b-instant"

_LAST_ERROR: Dict[str, Any] = {"type": "", "error": "", "ts": 0.0}


def _set_last_error(err: Exception):
    global _LAST_ERROR
    msg = str(err) if err is not None else ""
    _LAST_ERROR = {
        "type": type(err).__name__ if err is not None else "",
        "error": (msg or "")[:320],
        "ts": time.time(),
    }


def last_llm_error() -> Dict[str, Any]:
    return dict(_LAST_ERROR)


def _new_openai_client(**kwargs):
    """
    The OpenAI SDK signature can vary across versions. Build a client with
    best-effort optional kwargs without crashing.
    """
    if OpenAI is None:
        return None
    try:
        return OpenAI(**kwargs)
    except TypeError:
        safe = dict(kwargs)
        safe.pop("timeout", None)
        try:
            return OpenAI(**safe)
        except TypeError:
            safe.pop("max_retries", None)
            return OpenAI(**safe)


def groq_chat(
    messages: List[Dict[str, str]],
    system_prompt: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 120,
) -> str:
    """
    Makes exactly one Groq request and returns plain text.

    `messages` should be OpenAI-style: [{"role": "user"|"assistant", "content": "..."}]
    """
    if OpenAI is None:
        raise RuntimeError("openai sdk not installed")
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set")

    client = _new_openai_client(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        max_retries=0,
        timeout=LLM_TIMEOUT,
    )
    if client is None:  # pragma: no cover
        raise RuntimeError("openai sdk unavailable")

    wire_messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for m in messages or []:
        role = str(m.get("role") or "").strip()
        content = str(m.get("content") or "")
        if role not in {"user", "assistant"}:
            continue
        wire_messages.append({"role": role, "content": content})

    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=wire_messages,
            temperature=float(temperature),
            max_tokens=int(max_tokens),
        )
        text = resp.choices[0].message.content or ""
        return str(text)
    except Exception as e:
        _set_last_error(e)
        logger.warning("Groq call failed: %s", e)
        raise

