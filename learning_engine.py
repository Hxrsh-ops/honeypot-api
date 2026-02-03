# ============================================================
# LEARNING ENGINE — FINAL VERSION
# ------------------------------------------------------------
# Purpose:
# - Persist knowledge across sessions
# - Learn scammer patterns automatically
# - Score strategies & replies
# - Improve probing over time
# - Zero-crash, zero-blocking
# ============================================================

import os
import json
import time
import threading
from collections import defaultdict, Counter
from typing import Dict, Any, List

# ============================================================
# CONFIG
# ============================================================
DATA_DIR = os.getenv("LEARNING_DIR", "learning_data")
SNAPSHOT_FILE = os.path.join(DATA_DIR, "honeypot_memory.json")
MAX_EVENTS = 50_000

os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================
# GLOBAL STATE (THREAD SAFE)
# ============================================================
_LOCK = threading.Lock()

STATE = {
    "strategy_stats": defaultdict(lambda: {"success": 0, "fail": 0}),
    "intent_stats": defaultdict(int),
    "scammer_phrases": Counter(),
    "extracted_fields": Counter(),
    "session_lengths": [],
    "last_snapshot": 0.0,
}

# ============================================================
# LOAD EXISTING DATA
# ============================================================
def _load_snapshot():
    if not os.path.exists(SNAPSHOT_FILE):
        return
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        STATE.update(data)
    except Exception:
        pass


_load_snapshot()

# ============================================================
# CORE LEARNING API
# ============================================================
def learn_from_turn(
    intent: str,
    strategy: str,
    incoming: str,
    extracted: Dict[str, Any],
    outcome: str = "unknown"
):
    """
    Called on every meaningful interaction.
    This is the heart of self-learning.
    """
    with _LOCK:
        # intent frequency
        if intent:
            STATE["intent_stats"][intent] += 1

        # strategy effectiveness
        if strategy:
            if outcome == "success":
                STATE["strategy_stats"][strategy]["success"] += 1
            elif outcome == "fail":
                STATE["strategy_stats"][strategy]["fail"] += 1

        # phrase mining (scammer language)
        if incoming:
            tokens = incoming.lower().split()
            for t in tokens:
                if len(t) > 4:
                    STATE["scammer_phrases"][t] += 1

        # extracted intelligence
        for k, v in (extracted or {}).items():
            if v:
                STATE["extracted_fields"][k] += 1

        _cap_state_size()


# ============================================================
# SESSION-LEVEL LEARNING
# ============================================================
def learn_from_session(session: Dict[str, Any]):
    """
    Called when a session ends or expires.
    """
    with _LOCK:
        turns = session.get("turns", [])
        if turns:
            STATE["session_lengths"].append(len(turns))

        _cap_state_size()


# ============================================================
# STRATEGY SCORING
# ============================================================
def get_best_strategies(limit: int = 5) -> List[str]:
    """
    Returns best-performing strategies so far.
    """
    with _LOCK:
        scored = []
        for strat, stats in STATE["strategy_stats"].items():
            score = stats["success"] - stats["fail"]
            scored.append((score, strat))
        scored.sort(reverse=True)
        return [s for _, s in scored[:limit]]


# ============================================================
# INTENT HEURISTIC BOOST
# ============================================================
def get_common_scammer_phrases(limit: int = 20) -> List[str]:
    with _LOCK:
        return [p for p, _ in STATE["scammer_phrases"].most_common(limit)]


# ============================================================
# SNAPSHOT MANAGEMENT
# ============================================================
def persist_learning_snapshot(force: bool = False):
    """
    Persist learning data to disk.
    Non-blocking safe write.
    """
    now = time.time()
    if not force and now - STATE["last_snapshot"] < 30:
        return

    with _LOCK:
        STATE["last_snapshot"] = now
        try:
            tmp = SNAPSHOT_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_serialize_state(), f, indent=2)
            os.replace(tmp, SNAPSHOT_FILE)
        except Exception:
            pass


def _serialize_state():
    return {
        "strategy_stats": dict(STATE["strategy_stats"]),
        "intent_stats": dict(STATE["intent_stats"]),
        "scammer_phrases": dict(STATE["scammer_phrases"]),
        "extracted_fields": dict(STATE["extracted_fields"]),
        "session_lengths": STATE["session_lengths"][-1000:],  # trim
        "last_snapshot": STATE["last_snapshot"],
    }


# ============================================================
# SIZE CONTROL (NO MEMORY LEAKS)
# ============================================================
def _cap_state_size():
    # prevent unbounded growth
    if len(STATE["scammer_phrases"]) > MAX_EVENTS:
        STATE["scammer_phrases"] = Counter(
            dict(STATE["scammer_phrases"].most_common(MAX_EVENTS // 2))
        )

    if len(STATE["session_lengths"]) > 5000:
        STATE["session_lengths"] = STATE["session_lengths"][-3000:]


# ============================================================
# DEBUG / INSPECTION
# ============================================================
def get_learning_summary() -> Dict[str, Any]:
    with _LOCK:
        return {
            "top_intents": dict(
                Counter(STATE["intent_stats"]).most_common(10)
            ),
            "top_phrases": dict(
                STATE["scammer_phrases"].most_common(10)
            ),
            "best_strategies": get_best_strategies(),
            "avg_session_length": (
                sum(STATE["session_lengths"]) / len(STATE["session_lengths"])
                if STATE["session_lengths"] else 0
            ),
        }
