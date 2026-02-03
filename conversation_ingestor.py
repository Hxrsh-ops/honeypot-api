# ============================================================
# CONVERSATION INGESTOR — FINAL IMMUTABLE VERSION (vULTIMATE)
#
# Responsibilities:
# - Ingest raw scammer ↔ bot conversations
# - Normalize + fingerprint messages
# - Store learning signals
# - Update adaptive reply preferences
# - Enable self-training after each conversation
#
# This file is intentionally LONG and STATEFUL.
# Shortening it would reduce learning capability.
# ============================================================

import time
import json
import os
from typing import Dict, List, Optional

from agent_utils import (
    normalize_text,
    fingerprint_text,
    scam_signal_score,
    classify_message_complexity,
)

# ============================================================
# STORAGE CONFIG
# ============================================================

DATA_DIR = os.getenv("LEARNING_DATA_DIR", "learning_data")
os.makedirs(DATA_DIR, exist_ok=True)

CONVO_LOG_FILE = os.path.join(DATA_DIR, "conversation_log.jsonl")
LEARNING_STATE_FILE = os.path.join(DATA_DIR, "learning_state.json")

# ============================================================
# GLOBAL LEARNING STATE (IN-MEMORY + PERSISTED)
# ============================================================

DEFAULT_STATE = {
    "total_conversations": 0,
    "total_messages": 0,
    "scam_conversations": 0,
    "legit_conversations": 0,
    "high_risk_patterns": {},
    "successful_responses": {},
    "failed_responses": {},
    "fingerprints_seen": set(),  # runtime only
}

_learning_state: Dict = {}


# ============================================================
# STATE LOAD / SAVE
# ============================================================

def load_learning_state() -> Dict:
    global _learning_state

    if os.path.exists(LEARNING_STATE_FILE):
        try:
            with open(LEARNING_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["fingerprints_seen"] = set()
                _learning_state = data
                return _learning_state
        except Exception:
            pass

    _learning_state = DEFAULT_STATE.copy()
    _learning_state["fingerprints_seen"] = set()
    return _learning_state


def save_learning_state():
    if not _learning_state:
        return

    persistable = {
        k: v for k, v in _learning_state.items()
        if k != "fingerprints_seen"
    }

    try:
        with open(LEARNING_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(persistable, f, indent=2)
    except Exception:
        pass


# ============================================================
# INGESTION CORE
# ============================================================

def ingest_turn(
    session_id: str,
    speaker: str,
    message: str,
    reply_used: Optional[str] = None,
):
    """
    Ingest a single turn.
    speaker: "scammer" | "bot"
    """

    if not message:
        return

    state = _learning_state or load_learning_state()

    normalized = normalize_text(message)
    fp = fingerprint_text(message)

    # avoid duplicate ingestion in same runtime
    if fp in state["fingerprints_seen"]:
        return
    state["fingerprints_seen"].add(fp)

    risk = scam_signal_score(message)
    complexity = classify_message_complexity(message)

    record = {
        "ts": time.time(),
        "session_id": session_id,
        "speaker": speaker,
        "message": message,
        "normalized": normalized,
        "fingerprint": fp,
        "risk": risk,
        "complexity": complexity,
        "reply_used": reply_used,
    }

    # append to log
    try:
        with open(CONVO_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # update counters
    state["total_messages"] += 1

    # learn scam patterns
    if speaker == "scammer":
        if risk >= 3:
            state["high_risk_patterns"][normalized] = (
                state["high_risk_patterns"].get(normalized, 0) + 1
            )

    # learn bot response effectiveness
    if speaker == "bot" and reply_used:
        key = normalize_text(reply_used)
        state["successful_responses"][key] = (
            state["successful_responses"].get(key, 0) + 1
        )

    save_learning_state()


# ============================================================
# CONVERSATION-LEVEL INGESTION
# ============================================================

def ingest_conversation(
    session_id: str,
    turns: List[Dict],
    is_scam: bool,
):
    """
    Ingest full conversation after completion.
    """

    state = _learning_state or load_learning_state()

    state["total_conversations"] += 1
    if is_scam:
        state["scam_conversations"] += 1
    else:
        state["legit_conversations"] += 1

    for t in turns:
        ingest_turn(
            session_id=session_id,
            speaker=t.get("speaker", "unknown"),
            message=t.get("text", ""),
            reply_used=t.get("reply_used"),
        )

    save_learning_state()


# ============================================================
# ADAPTIVE SIGNAL EXTRACTION
# ============================================================

def get_learned_high_risk_phrases(limit: int = 50) -> List[str]:
    """
    Used by agent to bias suspicion earlier.
    """
    state = _learning_state or load_learning_state()
    items = sorted(
        state["high_risk_patterns"].items(),
        key=lambda x: x[1],
        reverse=True,
    )
    return [k for k, _ in items[:limit]]


def get_preferred_responses(limit: int = 50) -> List[str]:
    """
    Used by agent to prefer historically effective replies.
    """
    state = _learning_state or load_learning_state()
    items = sorted(
        state["successful_responses"].items(),
        key=lambda x: x[1],
        reverse=True,
    )
    return [k for k, _ in items[:limit]]


# ============================================================
# DEBUG / INSPECTION
# ============================================================

def learning_summary() -> Dict:
    state = _learning_state or load_learning_state()
    return {
        "total_conversations": state["total_conversations"],
        "total_messages": state["total_messages"],
        "scam_conversations": state["scam_conversations"],
        "legit_conversations": state["legit_conversations"],
        "known_high_risk_patterns": len(state["high_risk_patterns"]),
        "known_successful_responses": len(state["successful_responses"]),
    }

# ============================================================
# END OF FILE — DO NOT TRIM
# ============================================================
