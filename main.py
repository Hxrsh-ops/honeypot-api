import os
import re
import random
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

# ================= CONFIG =================
app = FastAPI()
API_KEY = os.getenv("HONEYPOT_API_KEY")

# ================= SESSION STORE =================
sessions = {}

# ================= INPUT MODEL =================
class ScamInput(BaseModel):
    session_id: str
    message: str

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

# ================= PHASES =================
PHASES = ["confusion", "verification", "resistance"]

# ================= HUMAN-LIKE REPLY DATASETS =================

CONFUSION_REPLIES = [
    "uhh wait, what’s this about?",
    "sorry, just saw this msg… what happened?",
    "hmm I’m not sure I understand this fully",
    "this is the first time I’m getting a msg like this",
    "ok slow down pls, what exactly is the issue?",
    "I’m a bit confused here, can you explain once?"
]

VERIFICATION_REPLIES = [
    "before doing anything I need branch + ref number",
    "why isn’t this showing in my bank app?",
    "banks usually don’t msg like this, who exactly are you?",
    "which branch is this handled from?",
    "can you tell me IFSC and branch details?",
    "I’ll need something official to verify this"
]

RESISTANCE_REPLIES_LONG = [
    "see, I’ve already been warned about scam msgs that create panic. "
    "I’m not sharing any personal details over chat. "
    "If this is genuine, it should reflect in official channels.",

    "this feels rushed and honestly a bit off. "
    "I’ll contact customer care directly and confirm. "
    "Until then I’m not proceeding with anything.",

    "I don’t see any alert or block in my banking app right now. "
    "Banks don’t usually ask for sensitive info like this over messages. "
    "I’ll verify independently.",

    "I’ve faced scam attempts earlier, so I’m extra careful now. "
    "Please understand I need proper written confirmation through official means.",

    "I’m not comfortable continuing this conversation without verification. "
    "If there’s really an issue, I’ll find out directly from the bank."
]

# ================= ROOT =================
@app.get("/")
def root():
    return {"status": "running"}

# ================= HONEYPOT ENDPOINT =================
@app.post("/honeypot")
def honeypot(
    data: ScamInput,
    x_api_key: str = Header(None)
):
    # ---- AUTH ----
    if API_KEY is None:
        raise HTTPException(status_code=500, detail="API key not configured")

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    sid = data.session_id
    msg = data.message

    # ---- INIT SESSION ----
    if sid not in sessions:
        sessions[sid] = {
            "turns": 0,
            "phase": "confusion",
            "intel": {
                "phone_numbers": [],
                "upi_ids": [],
                "links": []
            }
        }

    session = sessions[sid]
    session["turns"] += 1

    # ---- EXTRACT INTEL ----
    phones = extract_phone(msg)
    upis = extract_upi(msg)
    links = extract_links(msg)

    session["intel"]["phone_numbers"].extend(phones)
    session["intel"]["upi_ids"].extend(upis)
    session["intel"]["links"].extend(links)

    # ---- PHASE TRANSITION ----
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

    # ---- FINAL RESPONSE ----
    return {
        "reply": reply,
        "messages_seen": session["turns"],
        "extracted_intelligence": session["intel"]
    }
