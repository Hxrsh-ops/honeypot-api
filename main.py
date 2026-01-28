import os
import re
import random
import time
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI()

API_KEY = os.getenv("HONEYPOT_API_KEY", "test-key")

# ================= MEMORY =================
conversation_memory = {}
extracted_intel = {}
scam_score = {}

# ================= HELPERS =================
def human_delay():
    time.sleep(random.uniform(0.3, 1.0))

def extract_upi(text):
    return re.findall(r'\b[\w.-]+@[\w.-]+\b', text)

def extract_links(text):
    return re.findall(r'https?://\S+', text)

def extract_phone(text):
    return re.findall(r'\b\d{10}\b', text)

def score_message(text):
    score = 0
    keywords = ["upi", "pay", "transfer", "otp", "verify", "urgent", "blocked"]
    for k in keywords:
        if k in text:
            score += 10
    if extract_upi(text):
        score += 25
    if extract_links(text):
        score += 20
    if extract_phone(text):
        score += 15
    return score

def pick_message(payload: dict) -> str:
    """Extract message from ANY known scam-bot format"""
    for key in ["message", "msg", "text", "content", "body"]:
        if key in payload and isinstance(payload[key], str):
            return payload[key]
    return ""

def pick_session(payload: dict) -> str:
    for key in ["session_id", "session", "chat_id", "id"]:
        if key in payload:
            return str(payload[key])
    return "default-session"

# ================= ROUTES =================
@app.get("/")
def root():
    return {"status": "running"}

@app.post("/honeypot")
async def honeypot(request: Request, x_api_key: str = Header(None)):
    # -------- AUTH --------
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    try:
        payload = await request.json()
    except:
        payload = {}

    # -------- EXTRACT FLEXIBLY --------
    user_msg = pick_message(payload).lower().strip()
    session_id = pick_session(payload)

    # -------- GUVI TESTER (NO MESSAGE) --------
    if not user_msg:
        return {
            "reply": "Service live",
            "messages_seen": 0
        }

    # -------- NORMAL CHAT --------
    human_delay()

    if session_id not in conversation_memory:
        conversation_memory[session_id] = []
        extracted_intel[session_id] = {
            "upi_ids": [],
            "links": [],
            "phone_numbers": []
        }
        scam_score[session_id] = 0

    conversation_memory[session_id].append(user_msg)

    extracted_intel[session_id]["upi_ids"] += extract_upi(user_msg)
    extracted_intel[session_id]["links"] += extract_links(user_msg)
    extracted_intel[session_id]["phone_numbers"] += extract_phone(user_msg)

    scam_score[session_id] = min(
        100,
        scam_score[session_id] + score_message(user_msg)
    )

    msg_count = len(conversation_memory[session_id])

    # -------- HUMAN RESPONSE ENGINE --------
    openers = [
        "Hello?",
        "Yes?",
        "Who is this?",
        "Sorry I was busy."
    ]

    confusion = [
        "I don’t understand properly.",
        "Explain again please.",
        "I’m not good with these things."
    ]

    delay = [
        "Wait a bit.",
        "Network is slow.",
        "Phone is hanging."
    ]

    bait = [
        "I tried paying but it failed.",
        "It shows pending.",
        "Can you send details again?"
    ]

    trust = [
        "Is this really safe?",
        "My bank warned me about scams.",
        "Why is this urgent?"
    ]

    if msg_count == 1:
        reply = random.choice(openers)
    elif scam_score[session_id] >= 70:
        reply = random.choice(trust)
    elif any(k in user_msg for k in ["upi", "pay", "transfer"]):
        reply = random.choice(bait)
    elif "http" in user_msg:
        reply = "The link isn’t opening."
    else:
        reply = random.choice(confusion + delay)

    return {
        "reply": reply,
        "messages_seen": msg_count,
        "scam_score": scam_score[session_id],
        "extracted_intelligence": extracted_intel[session_id]
    }
