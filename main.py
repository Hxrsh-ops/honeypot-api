import os
import re
import random
from fastapi import FastAPI, Header, HTTPException, Request

# ================= CONFIG =================
app = FastAPI()
API_KEY = os.getenv("HONEYPOT_API_KEY", "test-key")

# ================= SESSION STORE =================
sessions = {}

# ================= INTEL EXTRACTION =================
PHONE_REGEX = r"\+?\d{10,13}"
UPI_REGEX = r"\b[\w.-]+@[\w.-]+\b"
LINK_REGEX = r"https?://\S+"

def extract_phone(text):
    return re.findall(PHONE_REGEX, text)

def extract_upi(text):
    return re.findall(UPI_REGEX, text)

def extract_links(text):
    return re.findall(LINK_REGEX, text)

# ================= HUMAN-LIKE DATASETS =================
CONFUSION_REPLIES = [
    "uhh wait, what’s this about?",
    "sorry just saw this msg, what happened?",
    "hmm I don’t fully get this",
    "ok slow down pls, what exactly is the issue?",
    "this is the first time I’m seeing something like this",
    "I’m a bit confused here, can you explain?"
]

VERIFICATION_REPLIES = [
    "before doing anything I need branch + ref number",
    "why isn’t this showing in my bank app?",
    "banks usually don’t msg like this, who exactly are you?",
    "which branch is handling this?",
    "can you share IFSC and branch details?",
    "I need something official to verify this"
]

RESISTANCE_REPLIES_LONG = [
    "see, I’ve already been warned about scam msgs that create panic. "
    "I’m not sharing any personal details over chat. "
    "If this is genuine, it should reflect officially.",

    "this feels rushed and honestly a bit off. "
    "I’ll contact customer care directly and confirm. "
    "Until then I’m not proceeding with anything.",

    "I don’t see any alert or block in my banking app right now. "
    "Banks don’t usually ask for sensitive info like this over messages.",

    "I’ve faced scam attempts earlier, so I’m extra careful now. "
    "Please understand I need proper written confirmation.",

    "I’m not comfortable continuing this without verification. "
    "If there’s really an issue, I’ll find out directly from the bank."
]

# ================= ROOT =================
@app.get("/")
def root():
    return {"status": "running"}

# ================= HONEYPOT =================
@app.post("/honeypot")
async def honeypot(
    request: Request,
    x_api_key: str = Header(None)
):
    # ---- AUTH ----
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # ---- SAFE BODY PARSING (NO 422 EVER) ----
    try:
        body = await request.json()
    except:
        body = {}

    # Extract message safely
    message = ""
    if isinstance(body, dict):
        for key in ["message", "msg", "text", "content"]:
            if key in body and isinstance(body[key], str):
                message = body[key]
                break

    # Extract session_id safely
    session_id = body.get("session_id", "default")

    # ---- INIT SESSION ----
    if session_id not in sessions:
        sessions[session_id] = {
            "turns": 0,
            "phase": "confusion",
            "intel": {
                "phone_numbers": [],
                "upi_ids": [],
                "links": []
            }
        }

    session = sessions[session_id]
    session["turns"] += 1

    # ---- INTEL EXTRACTION ----
    phones = extract_phone(message)
    upis = extract_upi(message)
    links = extract_links(message)

    session["intel"]["phone_numbers"].extend(phones)
    session["intel"]["upi_ids"].extend(upis)
    session["intel"]["links"].extend(links)

    # ---- PHASE LOGIC ----
    if phones or upis or links:
        session["phase"] = "resistance"
    elif session["turns"] > 1:
        session["phase"] = "verification"

    # ---- RESPONSE SELECTION ----
    if session["phase"] == "confusion":
        reply = random.choice(CONFUSION_REPLIES)
    elif session["phase"] == "verification":
        reply = random.choice(VERIFICATION_REPLIES)
    else:
        reply = random.choice(RESISTANCE_REPLIES_LONG)

    # ---- FINAL RESPONSE (ALWAYS VALID JSON) ----
    return {
        "reply": reply,
        "messages_seen": session["turns"],
        "extracted_intelligence": session["intel"]
    }
