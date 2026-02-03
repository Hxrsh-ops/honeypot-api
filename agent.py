# ============================================================
# agent.py — FINAL STABLE INTELLIGENT AGENT
# Multi-Phase | Human-Like | Crash-Proof | Railway-Safe
# ============================================================

from typing import Dict, Any, List, Optional
import random
import logging

# ----------------------------
# Safe imports (NEVER CRASH)
# ----------------------------
try:
    import victim_dataset as vd
except Exception as e:
    vd = None

try:
    from learning_engine import LearningEngine
except Exception:
    LearningEngine = None

logger = logging.getLogger("agent")
logging.basicConfig(level=logging.INFO)

# ----------------------------
# Constants
# ----------------------------
REPEAT_AVOIDANCE_LIMIT = 6
MAX_PHASES_PER_MESSAGE = 3
DEFAULT_REPLY = "ok"

# ----------------------------
# Utility helpers
# ----------------------------
def _normalize(text: str) -> str:
    return " ".join(text.lower().split())

def _safe_list(x):
    return x if isinstance(x, list) else []

# ============================================================
# AGENT
# ============================================================
class Agent:
    def __init__(self, session: Dict[str, Any]):
        self.s = session
        self.s.setdefault("recent_responses", set())
        self.s.setdefault("phase_history", [])
        self.s.setdefault("outgoing_count", 0)

        self.learner = LearningEngine(self.s) if LearningEngine else None

    # --------------------------------------------------------
    # Phase selection logic
    # --------------------------------------------------------
    def _select_phases(self, incoming: str) -> List[str]:
        """
        Decide which phases to use for a SINGLE reply.
        This is NOT chatting — this is composing one human message.
        """
        phases = []

        text = incoming.lower()

        # Entry logic
        if self.s["outgoing_count"] == 0:
            phases.append("casual_entry")

        # Confusion / probing
        if any(k in text for k in ["what", "why", "how", "who"]):
            phases.append(random.choice([
                "confusion",
                "light_confusion",
                "probing_identity",
                "probing_bank",
                "probing_process"
            ]))

        # Pressure & authority detection
        if any(k in text for k in ["urgent", "immediately", "blocked", "suspended"]):
            phases.append(random.choice([
                "time_pressure",
                "authority_pressure",
                "fear_response"
            ]))

        # Payment / links
        if any(k in text for k in ["upi", "pay", "transfer", "link", "click"]):
            phases.append(random.choice([
                "probing_payment",
                "probing_links",
                "technical_confusion"
            ]))

        # Late-stage doubt
        if self.s["outgoing_count"] > 3:
            phases.append(random.choice([
                "soft_doubt",
                "logic_doubt",
                "verification_loop",
                "last_minute_doubt"
            ]))

        # Exit trajectory
        if self.s["outgoing_count"] > 6:
            phases.append(random.choice([
                "fatigue",
                "annoyance",
                "delay_tactics",
                "cooldown_state"
            ]))

        # Trim + fallback
        phases = list(dict.fromkeys(phases))[:MAX_PHASES_PER_MESSAGE]
        return phases or ["casual_entry"]

    # --------------------------------------------------------
    # Message composition (CORE FEATURE)
    # --------------------------------------------------------
    def compose_message(self, phases: List[str]) -> str:
        """
        Build ONE long, human-like message by combining phases.
        """
        if not vd:
            return DEFAULT_REPLY

        parts = []

        for phase in phases:
            try:
                if hasattr(vd, "humanize_reply"):
                    part = vd.humanize_reply(phase)
                else:
                    pool = vd.BASE_POOLS.get(phase, [])
                    part = random.choice(pool) if pool else None
            except Exception:
                part = None

            if part:
                parts.append(part)

        if not parts:
            return DEFAULT_REPLY

        # Human spacing / flow
        message = " ".join(parts)

        return message.strip()

    # --------------------------------------------------------
    # Main response method (API CALLS THIS)
    # --------------------------------------------------------
    def respond(self, incoming: str, raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        phases = self._select_phases(incoming)

        reply = self.compose_message(phases)
        norm = _normalize(reply)

        # Repetition guard
        attempts = 0
        while norm in self.s["recent_responses"] and attempts < REPEAT_AVOIDANCE_LIMIT:
            reply = self.compose_message(phases)
            norm = _normalize(reply)
            attempts += 1

        self.s["recent_responses"].add(norm)
        self.s["phase_history"].append(phases)
        self.s["outgoing_count"] += 1

        # Learning hook (SAFE)
        if self.learner:
            try:
                self.learner.observe(incoming, reply, phases)
            except Exception:
                pass

        return {
            "reply": reply,
            "phases_used": phases,
            "intent": "honeypot_engagement"
        }
