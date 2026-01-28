import os
import re
import random
import time
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI()

API_KEY = os.getenv("HONEYPOT_API_KEY", "test-key")

conversation_memory = {}
extracted_intel = {}
scam_score = {}

# ---------- UTILITIES ----------
def human_delay():
    time.sleep(random.uniform(0.4, 1.2))

def deep_find_message(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ["message", "msg", "text", "content"] and isinstance(v, str):
                return v
            found = deep_find_message(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = deep_find_message(item)
            if found:
                return found
    return ""

def deep_find_session(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ["session_id", "session", "chat_id", "id"]:
                return str(v)
            found = deep_find_session(v)
            if found:
                return found
    return "default-session"

def extract_upi(text):
    return re.findall(r'\b[\w.-]+@[\w.-]+\b', text)

def extract_links(text):
    return re.findall(r'https?://\S+', text)

def extract_phone(text):
    return re.findall(r'\b\d{10}\b', text)

def score_message(text):
    score = 0
    keywords = ["upi", "pay", "otp", "urgent", "verify", "transfer", "blocked"]
    for k in keywords:
        if k in text:
            score += 10
    if extract_upi(text):
        score += 30
    if extract_links(text):
        score += 20
    if extract_phone(text):
        score += 15
    return score

# ---------- ROUTES ----------
@app.get("/")
def root():
    return {"status": "running"}

@app.post("/honeypot")
async def honeypot(request: Request, x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    try:
        payload = await request.json()
    except:
        payload = {}

    user_msg = deep_find_message(payload).strip()
    session_id = deep_find_session(payload)

    # ---- GUVI TESTER ONLY (EMPTY BODY) ----
    if not payload or not user_msg:
        return {"reply": "OK"}

    human_delay()

    if session_id not in conversation_memory:
        conversation_memory[session_id] = []
        extracted_intel[session_id] = {
            "upi_ids": [],
            "links": [],
            "phone_numbers": []
        }
        scam_score[session_id] = 0

    user_msg = user_msg.lower()
    conversation_memory[session_id].append(user_msg)

    extracted_intel[session_id]["upi_ids"] += extract_upi(user_msg)
    extracted_intel[session_id]["links"] += extract_links(user_msg)
    extracted_intel[session_id]["phone_numbers"] += extract_phone(user_msg)

    scam_score[session_id] = min(100, scam_score[session_id] + score_message(user_msg))
    msg_count = len(conversation_memory[session_id])

    # ---------- HUMAN RESPONSE ENGINE ----------
    openers = [
        "Hello?",
        "Yes, who is this?",
        "Sorry I missed your message.",
        "What is this regarding?"
    ]

    delays = [
        "Wait a minute.",
        "Network is slow.",
        "Phone is hanging.",
        "Let me check."
    ]

    bait = [
        "I tried paying but it failed.",
        "It shows pending on my side.",
        "Can you resend the details?"
    ]

    suspicion = [
        "Why are you rushing me?",
        "This feels risky.",
        "My bank warned me about scams."
    ]

    if msg_count == 1:
        reply = random.choice(openers)
    elif scam_score[session_id] >= 70:
        reply = random.choice(suspicion)
    elif any(k in user_msg for k in ["upi", "pay", "transfer"]):
        reply = random.choice(bait)
    elif "http" in user_msg:
        reply = "The link is not opening."
    else:
        reply = random.choice(delays)

    return {
        "reply": reply,
        "messages_seen": msg_count,
        "scam_score": scam_score[session_id],
        "extracted_intelligence": extracted_intel[session_id]
    }
