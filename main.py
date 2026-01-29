import os
import re
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

# ================= PERSONAS =================
PERSONAS = {
    "elder": "You are an elderly bank customer. Slightly slow, cautious, repeats questions.",
    "professional": "You are a busy working professional. Short replies, annoyed by urgency.",
    "genz": "You are a Gen-Z user. Casual language, suspicious, slang allowed."
}

# ================= HELPERS =================
def human_delay():
    time.sleep(random.uniform(0.4, 1.2))

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
        "repeat": any(w in t for w in ["again", "already told"]),
        "link": "http" in t
    }

def extract_intel(text, store):
    store["phones"] += re.findall(r"\b\d{10}\b", text)
    store["emails"] += re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    store["links"] += re.findall(r"https?://\S+", text)
    store["upi"] += re.findall(r"\b[\w.-]+@[\w.-]+\b", text)

# ================= SYSTEM PROMPT =================
BASE_SYSTEM_PROMPT = """
You are NOT an AI. You are a real human chatting on WhatsApp.

Rules:
- Never mention AI, bots, or safety policies
- Short, imperfect replies
- Sometimes confused, annoyed, sarcastic
- NEVER share OTP, account number, UPI
- Ask verification questions
- Waste scammer time
- Extract details indirectly
- Humans repeat and hesitate — that is OK
"""

def generate_reply(session, message, signals):
    persona = session["persona"]
    history = session["history"][-8:]

    behavior = []
    if signals["urgency"]: behavior.append("Scammer is rushing you.")
    if signals["money"]: behavior.append("Scammer wants sensitive info.")
    if signals["authority"]: behavior.append("Scammer claims authority.")
    if signals["repeat"]: behavior.append("Scammer is repeating.")

    prompt = f"""
Persona:
{PERSONAS[persona]}

Conversation:
{chr(10).join(history)}

Observations:
{'; '.join(behavior) if behavior else 'None'}

Reply naturally as a human.
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": BASE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9,
            max_tokens=90
        )
        return resp.choices[0].message.content.strip()
    except:
        return random.choice([
            "wait what?",
            "this feels off",
            "why are you rushing me",
            "i need to verify this",
            "my bank warned about scams"
        ])

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

    # Tester ping / empty payload
    if not message:
        return {"reply": "OK", "messages_seen": 0}

    human_delay()

    sid = "default"

    if sid not in sessions:
        sessions[sid] = {
            "turns": 0,
            "persona": random.choice(list(PERSONAS.keys())),
            "history": [],
            "intel": {"phones": [], "emails": [], "links": [], "upi": []}
        }

    session = sessions[sid]
    session["turns"] += 1
    session["history"].append(f"Scammer: {message}")

    extract_intel(message, session["intel"])
    signals = analyze_signals(message)

    reply = generate_reply(session, message, signals)
    session["history"].append(f"You: {reply}")

    return {
        "reply": reply,
        "messages_seen": session["turns"]
    }
