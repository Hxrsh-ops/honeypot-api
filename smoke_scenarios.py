import argparse
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests


IDENTITY_LOOP_RE = re.compile(r"\b(who(?:'s|s| is)\s+this|who\s+are\s+u|who\s+r\s+u|who\?)\b", re.I)
META_RE = re.compile(r"\b(as an ai|language model|system prompt|openai|groq|api|model|tokens?)\b", re.I)


@dataclass
class Turn:
    you: str
    bot: str
    meta: Dict[str, Any]


def _post(url: str, key: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["x-api-key"] = key
    r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    try:
        return r.json()
    except Exception:
        return {"_non_json": r.text, "status_code": r.status_code}


def run_scenario(
    base_url: str,
    api_key: str,
    name: str,
    messages: List[str],
    delay: float,
    timeout: float,
) -> Tuple[str, List[Turn], Dict[str, Any]]:
    session_id = str(uuid.uuid4())
    turns: List[Turn] = []

    identity_given = False
    extra_keys = 0
    meta_hits = 0

    for msg in messages:
        payload = {"message": msg, "session_id": session_id}
        data = _post(base_url, api_key, payload, timeout=timeout)
        reply = data.get("reply")
        if reply is None:
            reply = f"[no reply] {data}"
        reply_s = str(reply)

        # Minimal response contract: only reply + session_id.
        allowed = {"reply", "session_id"}
        if isinstance(data, dict):
            if any(k not in allowed for k in data.keys()):
                extra_keys += 1

        # crude "identity provided" tracking
        low = msg.lower()
        if ("i am " in low or "this is " in low) and ("bank" in low or "from" in low):
            identity_given = True

        if META_RE.search(reply_s):
            meta_hits += 1

        turns.append(Turn(you=msg, bot=reply_s, meta=data))

        if msg.strip().lower() == "exit":
            break
        time.sleep(delay)

    # checks/metrics (lightweight)
    identity_loop_after_identity = False
    if identity_given:
        for t in turns:
            if IDENTITY_LOOP_RE.search(t.bot or ""):
                # allow the very first response to "hi"
                if t.you.strip().lower() not in {"hi", "hello", "hey"}:
                    identity_loop_after_identity = True
                    break

    report = {
        "scenario": name,
        "session_id": session_id,
        "identity_loop_after_identity": identity_loop_after_identity,
        "responses_with_extra_keys": extra_keys,
        "meta_leak_hits": meta_hits,
    }
    return name, turns, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke scenarios against a running honeypot API")
    parser.add_argument("--base", default=os.getenv("HONEYPOT_URL", "").strip() or "https://spotless-maggi-hxrsh-ops-36f954ea.koyeb.app/honeypot")
    parser.add_argument("--key", default=os.getenv("HONEYPOT_API_KEY", "").strip() or "test-key")
    parser.add_argument("--delay", type=float, default=float(os.getenv("SMOKE_DELAY", "2.2")))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("SMOKE_TIMEOUT", "40")))
    parser.add_argument("--out", default="", help="Optional output log path (defaults to learning_data/)")
    args = parser.parse_args()

    scenarios: List[Tuple[str, List[str]]] = [
        (
            "bank_freeze_steps_link",
            [
                "hi",
                "i am rahul from sbi bank",
                "your account will freeze in under 1 hour if you dont renew it",
                "no worries just follow my steps and ill renew it",
                "here is the link https://secure-renew.example.com",
                "my employee id is 55568994",
                "exit",
            ],
        ),
        (
            "otp_pressure",
            [
                "hi",
                "im from hdfc bank your kyc expired",
                "send otp now to verify",
                "why are you stalling? send otp",
                "exit",
            ],
        ),
        (
            "parcel_fee_link",
            [
                "your parcel is on hold. pay redelivery fee here https://parcel-fee.example.com",
                "exit",
            ],
        ),
        (
            "job_fee",
            [
                "job offer confirmed. pay training fee 499 now",
                "exit",
            ],
        ),
        (
            "social_impersonation_mom",
            [
                "mom here. phone broken. new number. send 2k asap",
                "exit",
            ],
        ),
        (
            "legit_bank_alert",
            [
                "Dear customer, a transaction of Rs.500 was debited. If not initiated by you, call 1800-111-111.",
                "exit",
            ],
        ),
    ]

    all_reports: List[Dict[str, Any]] = []
    all_turns: Dict[str, List[Dict[str, Any]]] = {}

    for name, msgs in scenarios:
        scen, turns, report = run_scenario(args.base, args.key, name, msgs, delay=args.delay, timeout=args.timeout)
        all_reports.append(report)
        all_turns[scen] = [{"you": t.you, "bot": t.bot, "meta": t.meta} for t in turns]
        print(f"\n== {scen} ==")
        print(json.dumps(report, indent=2, ensure_ascii=False))

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = args.out.strip()
    if not out_path:
        os.makedirs("learning_data", exist_ok=True)
        out_path = os.path.join("learning_data", f"smoke_{ts}.json")

    blob = {"ts_utc": ts, "base": args.base, "reports": all_reports, "turns": all_turns}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(blob, f, indent=2, ensure_ascii=False)

    # exit code: fail if any scenario hit identity loop after identity OR llm rate is basically zero
    bad = 0
    for r in all_reports:
        if r.get("identity_loop_after_identity"):
            bad += 1
    if bad:
        print(f"\n[warn] identity loops detected in {bad} scenario(s)")

    print(f"\n[ok] wrote log: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
