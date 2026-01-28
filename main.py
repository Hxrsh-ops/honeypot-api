import os
import re
import random
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

try:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except:
    client = None

app = FastAPI()

API_KEY = os.getenv("HONEYPOT_API_KEY")

# ---------------- MEMORY ----------------

conversation_memory = {}
persona_store = {}
intel_store = {}
scam_score_store = {}

# ---------------- PERSONAS ----------------

PERSONAS = {
    "elderly": [
        "Hello beta, I am not very good with phones.",
        "Wait, I am trying to understand.",
        "My eyes are not very clear, please explain slowly."
    ],
    "student": [
        "Hi, I'm really confused about this.",
        "I don't have much money actually.",
        "Can you explain again? I'm scared."
    ],
    "professional": [
        "I'm in the middle of something right now.",
        "Please keep it short.",
        "Send the details, I'll check."
    ]
}

# ---------------- EXTRACTION ----------------

def extract_upi(text):
    return re.findall(r'\b[\w.-]+@[\w.-]+\b', text)

def extract_links(text):
    return re.findall(r'https?://\S+', text)

def extract_phone(text):
    return re.findall(r'\b\d{10}\b', text)

# ---------------- LLM HUMANIZER ----------------

def humanize_reply(intent, persona):
    if not client:
        return intent

    prompt = f"""
You are a real human chatting casually on WhatsApp.
Persona: {persona}
Tone: informal, hesitant, imperfect.
Do NOT sound like an AI.
Rewrite this intent naturally:

Intent: "{intent}"
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=60
        )
        return resp.choices[0].message.content.strip()
    except:
        return intent

# ---------------- INPUT ----------------

class IncomingMessage(BaseModel):
    session_id: str
    message: str

# ---------------- ROUTES ----------------

@app.get("/")
def root():
    return {"status": "running"}

@app.post("/honeypot")
def honeypot(data: IncomingMessage, x_api_key: str = Header(None)):

    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    session_id = data.session_id
    msg = data.message.lower()

    # INIT MEMORY
    conversation_memory.setdefault(session_id, []).append(msg)
    msg_count = len(conversation_memory[session_id])

    # PERSONA
    persona_store.setdefault(session_id, random.choice(list(PERSONAS)))
    persona = persona_store[session_id]

    # INTEL
    intel_store.setdefault(session_id, {"upi": [], "links": [], "phone": []})
    intel_store[session_id]["upi"] += extract_upi(msg)
    intel_store[session_id]["links"] += extract_links(msg)
    intel_store[session_id]["phone"] += extract_phone(msg)

    # SCORE
    score = scam_score_store.get(session_id, 0)
    if intel_store[session_id]["upi"]: score += 30
    if intel_store[session_id]["links"]: score += 25
    if intel_store[session_id]["phone"]: score += 15
    if any(w in msg for w in ["urgent", "now", "immediately"]): score += 10
    if any(w in msg for w in ["blocked", "suspended"]): score += 20
    scam_score_store[session_id] = min(score, 100)

    # DECISION ENGINE
    if msg_count == 1:
        intent = random.choice(PERSONAS[persona])

    elif score < 60:
        intent = random.choice([
            "I’m trying but something is loading slowly.",
            "Give me a minute, I’m checking.",
            "I don’t want to make a mistake."
        ])

    elif score < 85:
        intent = "It’s asking for confirmation again. Can you resend the details?"

    else:
        intent = "Something looks wrong here. It stopped suddenly. Please explain again."

    # HUMANIZE (ONLY WHEN USEFUL)
    reply = humanize_reply(intent, persona) if score >= 60 else intent

    return {
        "reply": reply,
        "persona": persona,
        "messages_seen": msg_count,
        "scam_score": scam_score_store[session_id],
        "extracted_intelligence": intel_store[session_id]
    }
