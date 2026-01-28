import os
import re
import random
from typing import Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

# ===== CONFIG =====
API_KEY = os.getenv("HONEYPOT_API_KEY")

# ===== MEMORY STORES =====
conversation_memory = {}   # session_id -> list of messages
extracted_intel = {}       # session_id -> extracted data
scam_score = {}            # session_id -> score


# ===== REGEX EXTRACTORS =====
def extract_upi(text):
    return re.findall(r'\b[\w.-]+@[\w.-]+\b', text)

def extract_links(text):
    return re.findall(r'https?://\S+', text)

def extract_phone(text):
    return re.findall(r'\b\d{10}\b', text)


# ===== REQUEST MODEL =====
class IncomingMessage(BaseModel):
    session_id: str
    message: str


# ===== ROOT =====
@app.get("/")
def root():
    return {"status": "running"}


# ===== MAIN HONEYPOT =====
@app.post("/honeypot")
def honeypot(
    data: Optional[IncomingMessage] = None,
    x_api_key: str = Header(None)
):
    # ---- AUTH ----
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # ---- TESTER CALL (NO BODY) ----
    if data is None:
        return {
            "status": "active",
            "message": "Honeypot API is live and secured"
        }

    # ---- NORMAL CHAT FLOW ----
    session_id = data.session_id
    user_msg = data.message.lower()

    if session_id not in conversation_memory:
        conversation_memory[session_id] = []
        extracted_intel[session_id] = {
            "upi_ids": [],
            "links": [],
            "phone_numbers": []
        }
        scam_score[session_id] = 0

    conversation_memory[session_id].append(user_msg)

    # ---- INTEL EXTRACTION ----
    upis = extract_upi(user_msg)
    links = extract_links(user_msg)
    phones = extract_phone(user_msg)

    extracted_intel[session_id]["upi_ids"] += upis
    extracted_intel[session_id]["links"] += links
    extracted_intel[session_id]["phone_numbers"] += phones

    scam_score[session_id] += len(upis) * 3
    scam_score[session_id] += len(links) * 2
    scam_score[session_id] += len(phones) * 2

    msg_count = len(conversation_memory[session_id])

    # ===== HUMAN-LIKE HYBRID RESPONSES =====
    first_replies = [
        "Hello? Yes, who is this?",
        "Sorry I missed your call, what is it about?",
        "Hi, I just saw your message."
    ]

    delay_replies = [
        "One minute please, I’m checking.",
        "Wait, I’m opening my app.",
        "Hmm it’s taking time, network issue."
    ]

    payment_trap = [
        "I tried sending but it failed. Can you resend the details?",
        "It’s asking for confirmation again, what should I select?",
        "My bank app is acting weird today."
    ]

    link_trap = [
        "That link isn’t opening properly.",
        "It shows an error page, is there another link?",
        "My phone says unsafe link, are you sure?"
    ]

    pressure_replies = [
        "Please don’t rush me, I’m arranging it.",
        "I already told you I’m trying.",
        "Why are you stressing so much?"
    ]

    if msg_count == 1:
        reply = random.choice(first_replies)
    elif upis or "pay" in user_msg or "transfer" in user_msg:
        reply = random.choice(payment_trap)
    elif links or "link" in user_msg:
        reply = random.choice(link_trap)
    elif msg_count >= 4:
        reply = random.choice(pressure_replies)
    else:
        reply = random.choice(delay_replies)

    return {
        "reply": reply,
        "messages_seen": msg_count,
        "scam_score": scam_score[session_id],
        "extracted_intelligence": extracted_intel[session_id]
    }
