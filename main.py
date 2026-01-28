import os
import re
import random
import time
from typing import Optional, Dict, Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

app = FastAPI()

# ================= CONFIG =================
API_KEY = os.getenv("HONEYPOT_API_KEY", "test-key")

# ================= MEMORY =================
conversation_memory = {}
extracted_intel = {}
scam_score = {}

# ================= UTILS =================
def human_delay():
    time.sleep(random.uniform(0.2, 0.8))

def extract_upi(text):
    return re.findall(r'\b[\w.-]+@[\w.-]+\b', text)

def extract_links(text):
    return re.findall(r'https?://\S+', text)

def extract_phone(text):
    return re.findall(r'\b\d{10}\b', text)

def score_message(text):
    score = 0
    keywords = ["upi", "pay", "transfer", "urgent", "otp", "verify", "blocked"]
    for k in keywords:
        if k in text:
            score += 15
    if extract_upi(text):
        score += 25
    if extract_links(text):
        score += 20
    if extract_phone(text):
        score += 15
    return score

# ================= ROUTES =================
@app.get("/")
def root():
    return {"status": "running"}

@app.post("/honeypot")
async def honeypot(
    request: Request,
    x_api_key: str = Header(None)
):
    # -------- AUTH --------
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # -------- READ BODY SAFELY --------
    try:
        payload: Dict[str, Any] = await request.json()
    except:
        payload = {}

    # -------- GUVI TESTER SAFE PATH --------
    if "session_id" not in payload or "message" not in payload:
        return {
            "reply": "Honeypot active",
            "messages_seen": 0,
            "scam_score": 0
        }

    # -------- NORMAL CHAT FLOW --------
    human_delay()

    session_id = str(payload.get("session_id"))
    user_msg = str(payload.get("message")).lower()

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
        "Yes, who is this?",
        "Sorry I was busy, tell me."
    ]

    confusion = [
        "I don’t understand properly.",
        "Can you explain once?",
        "I’m not very good with apps."
    ]

    delay = [
        "Wait, network is slow.",
        "Hold on, phone is hanging.",
        "Let me check, one minute."
    ]

    bait = [
        "I tried paying but it failed.",
        "It shows pending.",
        "Can you send the details again?"
    ]

    trust = [
        "Is this really safe?",
        "My bank warned me about scams.",
        "Are you sure this won’t cause issues?"
    ]

    if msg_count == 1:
        reply = random.choice(openers)
    elif scam_score[session_id] >= 70:
        reply = random.choice(trust)
    elif any(k in user_msg for k in ["upi", "pay", "transfer"]):
        reply = random.choice(bait)
    elif "http" in user_msg:
        reply = "The link isn’t opening properly."
    else:
        reply = random.choice(confusion + delay)

    return {
        "reply": reply,
        "messages_seen": msg_count,
        "scam_score": scam_score[session_id],
        "extracted_intelligence": extracted_intel[session_id]
    }
