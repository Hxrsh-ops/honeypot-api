import os
import re
import uuid
import random
import asyncio
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI()

API_KEY = os.getenv("HONEYPOT_API_KEY")

# ================= MEMORY =================
conversation_memory = {}
extracted_intel = {}
reply_history = {}

# ================= REGEX =================
def extract_upi(text):
    return re.findall(r'\b[\w.-]+@[\w.-]+\b', text)

def extract_links(text):
    return re.findall(r'https?://\S+', text)

def extract_phone(text):
    return re.findall(r'\b\d{10}\b', text)

# ================= HUMAN DATASETS (EXPANDED – NEVER REDUCED) =================

FILLERS = [
    "hmm", "uh", "uhh", "wait", "look", "see", "ok", "ah", "erm", "well",
    "hold on", "one sec", "just a sec", "hang on",
    "listen", "bro", "ya", "umm", "idk", "tbh"
]

CONFUSION_REPLIES = [
    "uhh wait, what’s this about?",
    "sorry just saw this msg, what happened?",
    "hmm I don’t really get this",
    "ok hold on, what exactly is the issue?",
    "this is the first time I’m seeing something like this",
    "I’m a bit lost here, can you explain?",
    "wait, how did this even come up?",
    "I just opened my phone and saw this, what’s going on?",
    "not sure I understand, can you say that again properly?",
    "hmm this is new to me, what’s the problem exactly?",
    "uhh sorry, can you slow down?",
    "this message came out of nowhere honestly",
    "I don’t remember doing anything unusual",
    "something doesn’t feel clear here",
    "can you explain from the beginning?",
    "why am I hearing about this only now?",
    "this is kinda confusing ngl"
]

VERIFICATION_REPLIES = [
    "before doing anything I need branch and reference number",
    "why isn’t this showing in my bank app?",
    "banks usually don’t message like this, who are you exactly?",
    "which city branch is handling this?",
    "can you share IFSC and branch details?",
    "I’ll need something official to verify this",
    "who authorised this request from your side?",
    "is there any ticket or complaint number?",
    "which department is this coming from?",
    "why didn’t I get an official alert from my bank app?",
    "what’s the registered SBI email for this?",
    "who is the manager handling this?",
    "can you tell me your employee ID?",
    "this should reflect in net banking right?",
    "why didn’t the app notify me?",
    "banks normally send proper alerts, this feels odd"
]

RESISTANCE_SHORT = [
    "this feels off",
    "not comfortable sharing this",
    "something isn’t adding up",
    "this doesn’t seem right",
    "I’m not convinced",
    "this sounds risky",
    "I don’t trust this yet",
    "nah this feels weird"
]

RESISTANCE_MEDIUM = [
    "you’re rushing me a lot and that’s concerning",
    "banks don’t usually pressure customers like this",
    "I don’t see any warning inside my banking app",
    "this approach feels very unprofessional",
    "I’ve been warned about messages like this",
    "I prefer verifying things on my own",
    "I’m uncomfortable with how this is going",
    "this is not how official communication works"
]

RESISTANCE_LONG = [
    "see, I’ve already been warned about scam messages that create panic. "
    "I’m not sharing personal details over chat. "
    "If this is genuine, it should appear officially in my bank app.",

    "this feels rushed and honestly suspicious. "
    "I’ll contact customer care directly and confirm before doing anything.",

    "I don’t see any alert, block, or warning inside my banking app right now. "
    "Banks normally don’t ask for sensitive details like this over messages.",

    "I’ve faced scam attempts earlier, so I’m extra careful now. "
    "Please understand I need proper written confirmation from official channels.",

    "you’re asking me to act fast but I don’t see any issue on my side. "
    "That itself is a red flag for me.",

    "I’m not ignoring this, but I won’t act blindly. "
    "I’ll verify independently and then decide.",

    "this whole thing feels engineered to scare me into acting quickly, "
    "and that’s exactly how scams usually work."
]

FATIGUE_REPLIES = [
    "you’ve already asked this multiple times",
    "why do you keep repeating the same thing?",
    "you’re not answering my questions",
    "this conversation is going in circles",
    "you keep pushing without clarifying anything",
    "this is getting exhausting honestly",
    "I’ve asked you the same thing again and again",
    "you’re just repeating yourself now"
]

# ================= HUMANIZATION LOGIC =================
def humanize(text):
    if random.random() < 0.4:
        return f"{random.choice(FILLERS)}, {text}"
    if random.random() < 0.2:
        return f"{text} honestly"
    return text

def avoid_repetition(session_id, candidate):
    used = reply_history.setdefault(session_id, set())
    if candidate in used:
        candidate = humanize(candidate)
    used.add(candidate)
    return candidate

def choose_reply(session_id, msg):
    if len(reply_history.get(session_id, [])) > 40:
        reply_history[session_id].clear()

    turns = len(conversation_memory[session_id])

    if turns >= 8:
        pool = FATIGUE_REPLIES
    elif any(k in msg for k in ["otp", "account", "verify", "urgent"]):
        pool = VERIFICATION_REPLIES
    elif turns <= 2:
        pool = CONFUSION_REPLIES
    elif turns <= 4:
        pool = RESISTANCE_MEDIUM
    else:
        pool = RESISTANCE_LONG

    reply = random.choice(pool)
    reply = humanize(reply)
    return avoid_repetition(session_id, reply)

# ================= ROUTES =================
@app.get("/")
def root():
    return {"status": "running"}

@app.post("/honeypot")
async def honeypot(request: Request, x_api_key: str = Header(None)):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    body = {}
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        try:
            body = await request.json()
        except:
            body = {}


    msg = (
        body.get("message")
        or body.get("text")
        or body.get("input")
        or body.get("msg")
        or body.get("data")
        or "hello"
    )

    msg = str(msg)

    session_id = body.get("session_id") or str(uuid.uuid4())

    conversation_memory.setdefault(session_id, []).append(msg)

    extracted_intel.setdefault(session_id, {
        "upi_ids": [],
        "links": [],
        "phone_numbers": []
    })

    extracted_intel[session_id]["upi_ids"] += extract_upi(msg)
    extracted_intel[session_id]["links"] += extract_links(msg)
    extracted_intel[session_id]["phone_numbers"] += extract_phone(msg)

    extracted_intel[session_id]["upi_ids"] = list(set(extracted_intel[session_id]["upi_ids"]))
    extracted_intel[session_id]["links"] = list(set(extracted_intel[session_id]["links"]))
    extracted_intel[session_id]["phone_numbers"] = list(set(extracted_intel[session_id]["phone_numbers"]))

    reply = choose_reply(session_id, msg.lower())

    await asyncio.sleep(random.uniform(0.4, 1.4))

    return {
        "reply": reply,
        "messages_seen": len(conversation_memory[session_id]),
        "extracted_intelligence": extracted_intel[session_id]
    }
#completed 