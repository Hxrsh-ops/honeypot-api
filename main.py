import os
import re
import random
import asyncio
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

# ================= HUMAN DATASETS (EXPANDED) =================

CONFUSION_REPLIES = [
    # existing
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
    # added
    "just woke up and saw this, what’s going on here?",
    "can you slow down a bit, I’m trying to understand",
    "I don’t usually get msgs like this, what happened?",
    "this is kinda confusing, explain once clearly pls",
    "wait I need a minute, what is this regarding?"
]

VERIFICATION_REPLIES = [
    # existing
    "before doing anything I need branch and ref number",
    "why isn’t this showing in my bank app?",
    "banks usually don’t msg like this, who are you exactly?",
    "which branch is handling this?",
    "can you share IFSC and branch details?",
    "I’ll need something official to verify this",
    "who authorised this request from your side?",
    "is there any ticket or reference ID for this?",
    "which department is this coming from?",
    "why didn’t I get an official alert for this?",
    # added
    "what’s the official email ID for this?",
    "is there a case number linked to this?",
    "why didn’t I receive any SMS from the bank?",
    "which city branch is this handled from?",
    "can you tell me the manager name handling this?"
]

RESISTANCE_REPLIES_LONG = [
    # existing
    "see, I’ve already been warned about scam msgs that create panic. "
    "I’m not sharing any personal details over chat. "
    "If this is genuine, it should show up officially.",

    "this feels rushed and honestly a bit off. "
    "I’ll contact customer care directly and confirm. "
    "Until then I’m not proceeding with anything.",

    "I don’t see any alert or block in my banking app right now. "
    "Banks don’t usually ask for sensitive info like this over messages.",

    "I’ve faced scam attempts earlier, so I’m extra careful now. "
    "Please understand I need proper written confirmation.",

    "I’m not comfortable continuing this without verification. "
    "If there’s really an issue, I’ll find out directly from the bank.",

    "you’re asking me to act fast but I don’t see anything wrong on my side. "
    "That itself is concerning, so I’ll verify independently.",

    "I’m not ignoring this, I just won’t act blindly. "
    "I’ll speak to the bank directly and clear this.",

    "I’m not okay sharing details when things don’t add up. "
    "Official confirmation is the only way forward.",
    # added
    "every time I ask for clarity, you push for details instead. "
    "That’s not how banks usually handle things.",

    "if this was serious, there would be an official trail already. "
    "Right now it just feels like pressure tactics.",

    "I’m done engaging unless I see proper confirmation through my app or email."
]

CONTRADICTION_REPLIES = [
    "wait, earlier you gave different details — can you clarify?",
    "you mentioned something else before, now it’s changed… why?",
    "first you said one thing, now you’re saying another",
    "your details don’t seem consistent, that’s worrying",
    "this doesn’t add up, you already shared different info earlier"
]

PREFIXES = ["hmm", "look", "see", "honestly", "wait", "ok", "uh"]
SUFFIXES = ["just saying", "that’s all", "for now", "I guess", "that’s what I feel", "to be honest"]

# ================= HUMAN VARIATION =================
def mutate_reply(reply):
    if random.random() < 0.4:
        if random.choice([True, False]):
            reply = f"{random.choice(PREFIXES)}… {reply}"
        else:
            reply = f"{reply} — {random.choice(SUFFIXES)}"
    return reply

def unique_reply(session, base):
    if base not in session["reply_history"]:
        session["reply_history"].append(base)
        return base

    for _ in range(5):
        mutated = mutate_reply(base)
        if mutated not in session["reply_history"]:
            session["reply_history"].append(mutated)
            return mutated

    return base

# ================= TYPING DELAY =================
async def typing_delay(reply):
    delay = 0.15 + len(reply.split()) * 0.03
    await asyncio.sleep(min(delay, 1.8))

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
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        body = await request.json()
    except:
        body = {}

    message = ""
    if isinstance(body, dict):
        for k in ["message", "msg", "text", "content"]:
            if k in body and isinstance(body[k], str):
                message = body[k]
                break

    session_id = body.get("session_id", "default")

    # ---- INIT SESSION ----
    if session_id not in sessions:
        sessions[session_id] = {
            "turns": 0,
            "emotion": "calm",
            "fatigue": 0,
            "intel": {
                "phone_numbers": [],
                "upi_ids": [],
                "links": []
            },
            "seen_intel": {
                "phones": set(),
                "upis": set(),
                "links": set()
            },
            "reply_history": []
        }

    session = sessions[session_id]
    session["turns"] += 1

    # ---- EXTRACT INTEL ----
    phones = extract_phone(message)
    upis = extract_upi(message)
    links = extract_links(message)

    # ---- CONTRADICTION DETECTION ----
    contradiction = False
    for p in phones:
        if p not in session["seen_intel"]["phones"] and session["seen_intel"]["phones"]:
            contradiction = True
        session["seen_intel"]["phones"].add(p)

    for u in upis:
        if u not in session["seen_intel"]["upis"] and session["seen_intel"]["upis"]:
            contradiction = True
        session["seen_intel"]["upis"].add(u)

    for l in links:
        if l not in session["seen_intel"]["links"] and session["seen_intel"]["links"]:
            contradiction = True
        session["seen_intel"]["links"].add(l)

    session["intel"]["phone_numbers"].extend(phones)
    session["intel"]["upi_ids"].extend(upis)
    session["intel"]["links"].extend(links)

    # ---- FATIGUE & EMOTION ----
    if contradiction:
        session["fatigue"] += 3
    if phones or upis:
        session["fatigue"] += 2
    if session["turns"] > 3:
        session["fatigue"] += 1

    if session["fatigue"] >= 6:
        session["emotion"] = "fed_up"
    elif session["fatigue"] >= 4:
        session["emotion"] = "annoyed"
    elif session["turns"] > 1:
        session["emotion"] = "cautious"

    # ---- REPLY SELECTION ----
    if contradiction:
        base = random.choice(CONTRADICTION_REPLIES)
    elif session["emotion"] == "calm":
        base = random.choice(CONFUSION_REPLIES)
    elif session["emotion"] == "cautious":
        base = random.choice(VERIFICATION_REPLIES)
    else:
        base = random.choice(RESISTANCE_REPLIES_LONG)

    reply = unique_reply(session, base)
    await typing_delay(reply)

    return {
        "reply": reply,
        "messages_seen": session["turns"],
        "extracted_intelligence": session["intel"]
    }
