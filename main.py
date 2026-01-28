import os
import re
import random
from typing import Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

API_KEY = os.getenv("HONEYPOT_API_KEY")

# Memory
conversation_memory = {}
extracted_intel = {}

# ---------- Utils ----------
def extract_upi(text):
    return re.findall(r'\b[\w.-]+@[\w.-]+\b', text)

def extract_links(text):
    return re.findall(r'https?://\S+', text)

def extract_phone(text):
    return re.findall(r'\b\d{10}\b', text)

# ---------- Models ----------
class IncomingMessage(BaseModel):
    session_id: str
    message: str

# ---------- Routes ----------
@app.get("/")
def root():
    return {"status": "running"}

@app.post("/honeypot")
def honeypot(
    data: Optional[IncomingMessage] = None,
    x_api_key: str = Header(None)
):
    # ---- Auth ----
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # ---- GUVI TESTER CALL (NO BODY) ----
    if data is None:
        return {
            "reply": "Service active",
            "messages_seen": 0
        }

    # ---- REAL CHAT LOGIC ----
    session_id = data.session_id
    user_msg = data.message.lower()

    if session_id not in conversation_memory:
        conversation_memory[session_id] = []
        extracted_intel[session_id] = {
            "upi_ids": [],
            "links": [],
            "phone_numbers": []
        }

    conversation_memory[session_id].append(user_msg)

    extracted_intel[session_id]["upi_ids"] += extract_upi(user_msg)
    extracted_intel[session_id]["links"] += extract_links(user_msg)
    extracted_intel[session_id]["phone_numbers"] += extract_phone(user_msg)

    msg_count = len(conversation_memory[session_id])

    # ---- Human-like Hybrid Replies ----
    replies_stage_1 = [
        "Hi, yes? Who is this?",
        "Sorry, missed this. What happened?",
        "Hello, I’m busy. Tell me quickly."
    ]

    replies_stall = [
        "Hmm wait, I’m checking.",
        "One minute, network issue.",
        "I’m not very good with this, explain again."
    ]

    replies_payment = [
        "UPI app is stuck on loading.",
        "It says transaction pending.",
        "Can you send details once more?"
    ]

    if msg_count == 1:
        reply = random.choice(replies_stage_1)
    elif "upi" in user_msg or "pay" in user_msg:
        reply = random.choice(replies_payment)
    elif "http" in user_msg or "link" in user_msg:
        reply = "This link is not opening for me. Is there another way?"
    else:
        reply = random.choice(replies_stall)

    return {
        "reply": reply,
        "messages_seen": msg_count,
        "extracted_intelligence": extracted_intel[session_id]
    }
