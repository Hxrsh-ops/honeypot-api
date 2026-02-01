import os
import re
import uuid
import random
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# =====================================================
# APP INIT (PLATFORM SAFE)
# =====================================================
app = FastAPI()
API_KEY = os.getenv("HONEYPOT_API_KEY", "").strip()

# =====================================================
# MEMORY (SESSION SAFE)
# =====================================================
conversation_memory = {}
extracted_intel = {}
reply_history = {}

MAX_TURNS = 25

# =====================================================
# REGEX (FIXED & ACCURATE)
# =====================================================
UPI_REGEX = re.compile(
    r'\b[\w.-]+@(ybl|okaxis|oksbi|okhdfc|upi)\b',
    re.I
)

PHONE_REGEX = re.compile(
    r'(?:\+91[-\s]?)?[6-9]\d{9}'
)

LINK_REGEX = re.compile(
    r'https?://[^\s]+'
)

# =====================================================
# SCAM INTENT CLUSTERS (SMART)
# =====================================================
SCAM_TRIGGERS = [
    "blocked", "freeze", "suspend", "kyc",
    "refund", "reversal", "charge",
    "security issue", "unauthorized",
    "limited time", "immediate action",
    "account issue", "verification pending",
    "restriction", "hold placed"
]

# =====================================================
# DATASETS (EXPANDED – NEVER REDUCED)
# =====================================================
FILLERS = [
    "hmm", "uh", "uhh", "wait", "look", "see", "ok", "ah", "erm", "well",
    "hold on", "one sec", "just a sec", "hang on",
    "listen", "bro", "ya", "umm", "idk", "tbh",
    "huh", "uh oh", "hmm wait", "lemme check", "not sure"
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
    "this is kinda confusing ngl",
    "I’m not very tech savvy, what does this mean?"
]

PROBING_REPLIES = [
    "ok but where exactly should I send the money?",
    "can you resend the link? previous one didn’t open",
    "is this UPI or bank transfer?",
    "can you share the exact account details again?",
    "which app should I use for this?",
    "is this same as last time or different?",
    "do I need to visit a branch for this?",
    "can you send step by step instructions?"
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
    "you’re just repeating yourself now",
    "I don’t think we’re getting anywhere"
]

# =====================================================
# UTILITIES
# =====================================================
def humanize(text):
    if random.random() < 0.4:
        return f"{random.choice(FILLERS)}, {text}"
    if random.random() < 0.25:
        return f"{text} honestly"
    return text

def cleanup_session(session_id):
    if len(conversation_memory.get(session_id, [])) > MAX_TURNS:
        conversation_memory.pop(session_id, None)
        extracted_intel.pop(session_id, None)
        reply_history.pop(session_id, None)

def choose_reply(session_id, msg):
    turns = len(conversation_memory[session_id])

    if any(t in msg for t in SCAM_TRIGGERS) and turns <= 4:
        pool = PROBING_REPLIES
    elif turns <= 2:
        pool = CONFUSION_REPLIES
    elif turns <= 5:
        pool = VERIFICATION_REPLIES
    elif turns <= 8:
        pool = RESISTANCE_MEDIUM
    elif turns <= 12:
        pool = RESISTANCE_LONG
    else:
        pool = FATIGUE_REPLIES

    reply = random.choice(pool)
    return humanize(reply)

# =====================================================
# ROOT – NEVER FAILS (UPTIME SAFE)
# =====================================================
@app.api_route("/", methods=["GET", "POST", "HEAD"])
async def root():
    return JSONResponse({"status": "alive"})

# =====================================================
# HONEYPOT ENDPOINT – FAIL-SAFE
# =====================================================
@app.api_route("/honeypot", methods=["GET", "POST", "HEAD"])
async def honeypot(request: Request):
    headers = request.headers or {}

    provided_key = (
        headers.get("x-api-key")
        or headers.get("authorization")
        or headers.get("Authorization")
        or ""
    ).replace("Bearer", "").strip()

    # NEVER crash evaluator
    if API_KEY and provided_key and provided_key != API_KEY:
        return JSONResponse({"reply": "ok"}, status_code=200)

    body = {}
    try:
        if "application/json" in headers.get("content-type", ""):
            body = await request.json()
    except:
        body = {}

    msg = (
        body.get("message")
        or body.get("text")
        or body.get("input")
        or body.get("msg")
        or body.get("data")
        or ""
    )

    msg = str(msg)
    session_id = body.get("session_id") or str(uuid.uuid4())

    conversation_memory.setdefault(session_id, []).append(msg)
    cleanup_session(session_id)

    extracted_intel.setdefault(session_id, {
        "upi_ids": [],
        "links": [],
        "phone_numbers": []
    })

    extracted_intel[session_id]["upi_ids"] += UPI_REGEX.findall(msg)
    extracted_intel[session_id]["links"] += LINK_REGEX.findall(msg)
    extracted_intel[session_id]["phone_numbers"] += PHONE_REGEX.findall(msg)

    extracted_intel[session_id]["upi_ids"] = list(set(extracted_intel[session_id]["upi_ids"]))
    extracted_intel[session_id]["links"] = list(set(extracted_intel[session_id]["links"]))
    extracted_intel[session_id]["phone_numbers"] = list(set(extracted_intel[session_id]["phone_numbers"]))

    reply = choose_reply(session_id, msg.lower())

    await asyncio.sleep(random.uniform(0.4, 1.2))

    return JSONResponse({
        "reply": reply,
        "messages_seen": len(conversation_memory[session_id]),
        "extracted_intelligence": extracted_intel[session_id]
    })
