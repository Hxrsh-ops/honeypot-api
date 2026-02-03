# ============================================================
# INGESTION ENGINE — FINAL IMMUTABLE VERSION
#
# Purpose:
# - Feed conversations into the honeypot safely
# - Train the bot from:
#     • Manual conversations
#     • JSON chat logs
#     • Plain text exports
#     • Simulated scam flows
#
# - Supports:
#     • Dry-run
#     • Replay speed control
#     • Direction-aware ingestion
#     • Learning engine integration
#
# ============================================================

import json
import time
import argparse
import os
from typing import List, Dict, Any

from agent import Agent
from learning_engine import learn_from_conversation


# ============================================================
# STRUCTURE DEFINITIONS
# ============================================================

"""
Expected canonical format (internally normalized):

conversation = {
    "meta": {
        "source": "manual|json|txt|telegram|whatsapp",
        "is_scam": True,
        "confidence": 0.85
    },
    "turns": [
        {"dir": "in", "text": "Hello, this is SBI fraud dept"},
        {"dir": "out", "text": "hmm, who is this?"},
        ...
    ]
}
"""


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_conversation(raw: Any, source: str) -> Dict[str, Any]:
    """
    Converts arbitrary input into canonical conversation format.
    Safe by design: never throws.
    """
    convo = {
        "meta": {
            "source": source,
            "is_scam": True,
            "confidence": 0.7
        },
        "turns": []
    }

    try:
        if isinstance(raw, dict) and "turns" in raw:
            convo.update(raw)
            return convo

        if isinstance(raw, list):
            for line in raw:
                if isinstance(line, dict):
                    convo["turns"].append({
                        "dir": line.get("dir", "in"),
                        "text": str(line.get("text", "")).strip()
                    })
                else:
                    convo["turns"].append({
                        "dir": "in",
                        "text": str(line).strip()
                    })
            return convo

        if isinstance(raw, str):
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            for l in lines:
                direction = "out" if l.lower().startswith("bot:") else "in"
                text = l.replace("Bot:", "").replace("You:", "").strip()
                convo["turns"].append({"dir": direction, "text": text})

    except Exception:
        pass

    return convo


# ============================================================
# INGEST CORE
# ============================================================

def ingest_conversation(
    conversation: Dict[str, Any],
    simulate: bool = True,
    delay: float = 0.4,
    dry_run: bool = False
) -> None:
    """
    Replays a conversation through the Agent,
    then feeds it into the learning engine.
    """

    session: Dict[str, Any] = {
        "turns": [],
        "agent_state": {},
        "meta": conversation.get("meta", {})
    }

    agent = Agent(session)

    for turn in conversation.get("turns", []):
        text = turn.get("text", "").strip()
        direction = turn.get("dir", "in")

        if not text:
            continue

        if direction == "in":
            agent.respond(text)
            session["turns"].append({"dir": "in", "text": text})
        else:
            session["turns"].append({"dir": "out", "text": text})

        if simulate and not dry_run:
            time.sleep(delay)

    if not dry_run:
        learn_from_conversation(session)


# ============================================================
# FILE INGESTION
# ============================================================

def ingest_file(path: str, dry_run: bool = False) -> None:
    if not os.path.exists(path):
        print("❌ File not found:", path)
        return

    source = os.path.splitext(path)[1].lower().replace(".", "")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()

    conversation = normalize_conversation(raw, source)
    ingest_conversation(conversation, dry_run=dry_run)


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Honeypot Conversation Ingestor")

    parser.add_argument(
        "--file",
        help="Path to conversation file (json / txt)",
        required=False
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and replay without learning"
    )

    parser.add_argument(
        "--speed",
        type=float,
        default=0.4,
        help="Replay delay in seconds"
    )

    args = parser.parse_args()

    if args.file:
        ingest_file(args.file, dry_run=args.dry_run)
        print("✅ Ingestion complete")
    else:
        print("ℹ️ No file provided. Nothing to ingest.")


if __name__ == "__main__":
    main()
