import os
import time
import random
from fastapi import FastAPI, Header, HTTPException, Request
from openai import OpenAI

# ================= CONFIG =================
app = FastAPI()
API_KEY = os.getenv("HONEYPOT_API_KEY", "test-key")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ================= MEMORY =================
sessions = {}

# ================= PHASES =================
PHASES = [
    "confusion",
    "skepticism",
    "verification",
    "challenge",
    "annoyance",
    "shutdown"
]

PHASE_BEHAVIOR = {
    "confusion": "You are confused, cautious, asking basic questions.",
    "skepticism": "You are doubtful and uneasy, questioning authenticity.",
    "verification": "You actively ask for verifiable details.",
    "challenge": "You point out inconsistencies and push back.",
    "annoyance": "You are irritated and slow to cooperate.",
    "shutdown": "You are tired, defensive, and resistant."
}

# ================= HELPERS =================
def human_delay():
    time.sleep(random.uniform(0.6, 1.5))

def extract_text(payload):
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k.lower() in ["message", "msg", "text", "content"] and isinstance(v, str):
                return v
            found = extract_text(v)
            if found:
                return found
    if isinstance(payload, list):
        for i in payload:
            found = extract_text(i)
            if found:
                return found
    return ""

def analyze_signals(text):
    t = text.lower()
    return {
        "urgency": any(w in t for w in ["urgent", "immediately", "blocked", "freeze"]),
        "money": any(w in t for w in ["otp", "account", "upi", "transfer"]),
        "authority": any(w in t for w in ["bank", "sbi", "manager", "head office"]),
        "repeat": any(w in t for w in ["again", "already", "as i said"]),
    }

def advance_phase(session, signals):
    idx = PHASES.index(session["phase"])

    if session["turns"] < 2:
        return "confusion"
    if signals["money"] and idx < 3:
        return PHASES[min(idx + 1, len(PHASES) - 1)]
    if signals["repeat"] or signals["urgency"]:
        return PHASES[min(idx + 1, len(PHASES) - 1)]
    return session["phase"]

# ================= SYSTEM PROMPT =================
SYSTEM_PROMPT = """
You are a REAL HUMAN chatting on WhatsApp.

CRITICAL:
- You are NOT an AI.
- Never mention AI, bots, policies, or safety systems.
- You speak like a normal person, not smart, not formal.
- Replies should feel human: slightly long, emotional, imperfect.
- NEVER share OTP, account number, UPI, or real personal info.
- You are suspicious and defensive.
- You are allowed to repeat ideas, but NOT exact sentences.
- Avoid short replies like "wait what" or "this feels off".
"""

def generate_reply(session, message, signals):
    phase = session["phase"]
    history = session["history"][-6:]

    controller_instruction = f"""
Current phase: {phase}
Phase behavior: {PHASE_BEHAVIOR[phase]}

Rules for this reply:
- Reply length: 2–4 sentences
- Do NOT repeat previous wording
- Sound like a real person texting
- Express emotion naturally
- Ask at least one question unless phase is 'shutdown'
"""

    user_prompt = f"""
Conversation so far:
{chr(10).join(history)}

Latest scammer message:
{message}

Observations:
Urgency={signals["urgency"]}, Authority={signals["authority"]}, Money={signals["money"]}

{controller_instruction}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.95,
            max_tokens=140
        )
        reply = resp.choices[0].message.content.strip()

        # hard guard against ultra-short replies
        if len(reply.split()) < 8:
            reply += " I’m not comfortable rushing into anything like this."

        return reply

    except Exception:
        return (
            "I’m not comfortable with how this is being handled. "
            "You’re pushing for sensitive details without proper verification, "
            "and I need clear answers before continuing."
        )

# ================= ROUTES =================
@app.get("/")
def root():
    return {"status": "running"}

@app.post("/honeypot")
async def honeypot(req: Request, x_api_key: str = Header(None)):

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401)

    try:
        payload = await req.json()
    except:
        payload = {}

    message = extract_text(payload)

    # tester ping / empty request
    if not message:
        return {"reply": "OK", "messages_seen": 0}

    human_delay()

    sid = "default"

    if sid not in sessions:
        sessions[sid] = {
            "turns": 0,
            "phase": "confusion",
            "history": []
        }

    session = sessions[sid]
    session["turns"] += 1
    session["history"].append(f"Scammer: {message}")

    signals = analyze_signals(message)
    session["phase"] = advance_phase(session, signals)

    reply = generate_reply(session, message, signals)
    session["history"].append(f"You: {reply}")

    return {
        "reply": reply,
        "messages_seen": session["turns"]
    }
