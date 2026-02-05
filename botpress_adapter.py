import os
import time
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, List

import httpx

logger = logging.getLogger("botpress_adapter")


def _clean_token(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if v.lower().startswith("bearer "):
        v = v[7:].strip()
    # strip surrounding quotes
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        v = v[1:-1].strip()
    return v


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _env_str(name: str, default: str) -> str:
    v = (os.getenv(name) or "").strip()
    return v if v else default


def botpress_available() -> bool:
    # Keep this check cheap and deterministic; no network calls.
    if (os.getenv("CHAT_PROVIDER") or "").strip().lower() != "botpress":
        return False
    token = _clean_token(os.getenv("BOTPRESS_TOKEN") or "")
    bot_id = (os.getenv("BOTPRESS_BOT_ID") or "").strip()
    return bool(token) and bool(bot_id)


# Cooldown to avoid hammering Botpress on 429s.
_BOTPRESS_COOLDOWN_UNTIL: float = 0.0
_BOTPRESS_COOLDOWN_SEC: float = _env_float("BOTPRESS_COOLDOWN_SEC", 20.0)

# Best-effort debug hook (safe to expose only when explicitly requested).
_LAST_ERROR: Dict[str, Any] = {"provider": "botpress", "type": "", "error": "", "status": 0, "ts": 0.0}


def _set_last_error(err_type: str, msg: str, status: int = 0):
    global _LAST_ERROR
    _LAST_ERROR = {
        "provider": "botpress",
        "type": (err_type or "")[:80],
        "error": (msg or "")[:320],
        "status": int(status or 0),
        "ts": time.time(),
    }


def last_botpress_error() -> Dict[str, Any]:
    return dict(_LAST_ERROR)


def _parse_iso(ts: str) -> float:
    if not ts:
        return 0.0
    try:
        t = ts.strip()
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        return datetime.fromisoformat(t).timestamp()
    except Exception:
        return 0.0


def _headers() -> Dict[str, str]:
    token = _clean_token(os.getenv("BOTPRESS_TOKEN") or "")
    bot_id = (os.getenv("BOTPRESS_BOT_ID") or "").strip()
    headers = {
        "Authorization": f"Bearer {token}",
        "x-bot-id": bot_id,
        "Content-Type": "application/json",
    }
    # Runtime API requires an integration context to create *incoming* messages.
    # Defaulting to the Botpress "Chat" integration alias keeps this simple for most setups.
    alias = (os.getenv("BOTPRESS_INTEGRATION_ALIAS") or "chat").strip()
    if alias:
        headers["x-integration-alias"] = alias
    return headers


def _message_text(msg: Dict[str, Any]) -> str:
    payload = msg.get("payload") or {}
    if isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        for k in ("markdown", "message", "content", "body", "value"):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    # last resort: stringify
    try:
        s = str(payload).strip()
        return s if s and s != "{}" else ""
    except Exception:
        return ""


def _ensure_ids(client: httpx.Client, session: Dict[str, Any]) -> Tuple[str, str]:
    global _BOTPRESS_COOLDOWN_UNTIL
    user_id = (session.get("bp_user_id") or "").strip()
    conv_id = (session.get("bp_conversation_id") or "").strip()
    if user_id and conv_id:
        return user_id, conv_id

    # create user
    user_body: Dict[str, Any] = {"tags": {}}
    # Keep a stable display name; doesn't affect security.
    user_body["name"] = (session.get("bp_user_name") or "User")[:40]
    r_user = client.post("/v1/chat/users", json=user_body)
    if r_user.status_code == 429:
        _BOTPRESS_COOLDOWN_UNTIL = time.time() + max(1.0, _BOTPRESS_COOLDOWN_SEC)
        _set_last_error("RateLimit", r_user.text, status=429)
        raise RuntimeError("botpress rate limited")
    r_user.raise_for_status()
    user = (r_user.json() or {}).get("user") or {}
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        raise RuntimeError("botpress createUser missing id")

    # create conversation
    channel = _env_str("BOTPRESS_CHANNEL", "api")
    conv_body: Dict[str, Any] = {"channel": channel, "tags": {}}
    r_conv = client.post("/v1/chat/conversations", json=conv_body)
    if r_conv.status_code == 429:
        _BOTPRESS_COOLDOWN_UNTIL = time.time() + max(1.0, _BOTPRESS_COOLDOWN_SEC)
        _set_last_error("RateLimit", r_conv.text, status=429)
        raise RuntimeError("botpress rate limited")
    r_conv.raise_for_status()
    conv = (r_conv.json() or {}).get("conversation") or {}
    conv_id = str(conv.get("id") or "").strip()
    if not conv_id:
        raise RuntimeError("botpress createConversation missing id")

    # add participant (required for many integrations)
    r_part = client.post(f"/v1/chat/conversations/{conv_id}/participants", json={"userId": user_id})
    if r_part.status_code == 429:
        _BOTPRESS_COOLDOWN_UNTIL = time.time() + max(1.0, _BOTPRESS_COOLDOWN_SEC)
        _set_last_error("RateLimit", r_part.text, status=429)
        raise RuntimeError("botpress rate limited")
    r_part.raise_for_status()

    session["bp_user_id"] = user_id
    session["bp_conversation_id"] = conv_id
    session.setdefault("bp_last_bot_msg_id", "")
    session.setdefault("bp_last_bot_ts", 0.0)
    return user_id, conv_id


def _send_text(client: httpx.Client, user_id: str, conv_id: str, text: str) -> str:
    global _BOTPRESS_COOLDOWN_UNTIL
    body = {
        "payload": {"type": "text", "text": text},
        "userId": user_id,
        "conversationId": conv_id,
        "type": "text",
        "tags": {},
    }
    r = client.post("/v1/chat/messages", json=body)
    if r.status_code == 429:
        _BOTPRESS_COOLDOWN_UNTIL = time.time() + max(1.0, _BOTPRESS_COOLDOWN_SEC)
        _set_last_error("RateLimit", r.text, status=429)
        raise RuntimeError("botpress rate limited")
    r.raise_for_status()
    msg = (r.json() or {}).get("message") or {}
    return str(msg.get("id") or "").strip()


def _poll_outgoing(client: httpx.Client, conv_id: str, last_id: str, last_ts: float) -> Optional[Tuple[str, str, float]]:
    global _BOTPRESS_COOLDOWN_UNTIL
    poll_timeout = _env_float("BOTPRESS_POLL_TIMEOUT", 6.0)
    poll_interval = _env_float("BOTPRESS_POLL_INTERVAL", 0.25)
    deadline = time.time() + max(0.5, poll_timeout)

    while time.time() < deadline:
        r = client.get("/v1/chat/messages", params={"conversationId": conv_id})
        if r.status_code == 429:
            _BOTPRESS_COOLDOWN_UNTIL = time.time() + max(1.0, _BOTPRESS_COOLDOWN_SEC)
            _set_last_error("RateLimit", r.text, status=429)
            return None
        r.raise_for_status()
        data = r.json() or {}
        msgs = data.get("messages") or []
        if not isinstance(msgs, list):
            msgs = []

        out: List[Dict[str, Any]] = [m for m in msgs if isinstance(m, dict) and m.get("direction") == "outgoing"]
        out.sort(key=lambda m: _parse_iso(str(m.get("createdAt") or "")))

        new_msgs: List[Dict[str, Any]] = []
        for m in out:
            mid = str(m.get("id") or "")
            mts = _parse_iso(str(m.get("createdAt") or ""))
            if last_id and mid == last_id:
                continue
            if last_ts and mts and mts <= float(last_ts):
                continue
            if mid:
                new_msgs.append(m)

        if new_msgs:
            texts = [_message_text(m) for m in new_msgs]
            texts = [t for t in texts if t]
            reply = "\n".join(texts).strip()
            last = new_msgs[-1]
            new_last_id = str(last.get("id") or "").strip()
            new_last_ts = _parse_iso(str(last.get("createdAt") or "")) or time.time()
            if reply:
                return reply, new_last_id, new_last_ts

        time.sleep(max(0.05, poll_interval))
    return None


def chat(session: Dict[str, Any], incoming: str) -> Optional[str]:
    if not botpress_available():
        return None
    global _BOTPRESS_COOLDOWN_UNTIL
    if time.time() < _BOTPRESS_COOLDOWN_UNTIL:
        return None

    base = (_env_str("BOTPRESS_API_BASE", "https://api.botpress.cloud")).rstrip("/")
    timeout = _env_float("BOTPRESS_TIMEOUT", 8.0)
    try:
        with httpx.Client(base_url=base, headers=_headers(), timeout=timeout) as client:
            user_id, conv_id = _ensure_ids(client, session)
            _send_text(client, user_id, conv_id, str(incoming or ""))
            last_id = str(session.get("bp_last_bot_msg_id") or "").strip()
            last_ts = float(session.get("bp_last_bot_ts") or 0.0)
            polled = _poll_outgoing(client, conv_id, last_id=last_id, last_ts=last_ts)
            if not polled:
                return None
            reply, new_last_id, new_last_ts = polled
            session["bp_last_bot_msg_id"] = new_last_id
            session["bp_last_bot_ts"] = float(new_last_ts or time.time())
            return reply.strip() if reply else None
    except Exception as e:
        _set_last_error(type(e).__name__, str(e), status=0)
        logger.warning("Botpress chat failed: %s", e)
        return None
