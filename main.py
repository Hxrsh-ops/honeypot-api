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

def extract_phone(text): return re.findall(PHONE_REGEX, text)
def extract_upi(text): return re.findall(UPI_REGEX, text)
def extract_links(text): return re.findall(LINK_REGEX, text)

# ================= HUMAN FILLERS =================
FILLERS = ["hmm", "uh", "uhm", "ok", "wait", "huh", "erm"]
PREFIXES = ["look", "honestly", "see", "ok", "wait"]
SUFFIXES = ["just saying", "for now", "I guess", "to be honest", "that’s all"]

# ================= DATASETS (VERY LARGE, NEVER REDUCED) =================
# Each entry: (intent, text)

CONFUSION = [
    ("confusion_short","hmm"),
    ("confusion_short","uhh"),
    ("confusion_short","wait"),
    ("confusion_short","ok…"),
    ("confusion_medium","sorry just saw this msg, what happened?"),
    ("confusion_medium","uhh wait, what’s this about?"),
    ("confusion_medium","I don’t really get what this is"),
    ("confusion_medium","can you explain what exactly happened?"),
    ("confusion_medium","this is new to me, what’s going on?"),
    ("confusion_long","I just opened my phone and saw this message and I’m honestly confused about what it’s referring to."),
    ("confusion_long","I don’t usually get messages like this from the bank, so I’m trying to understand what this is about."),
    ("confusion_long","I’m a bit lost here, this came out of nowhere and I don’t understand what triggered it.")
]

VERIFICATION = [
    ("verify_short","which branch?"),
    ("verify_short","ref number?"),
    ("verify_short","IFSC?"),
    ("verify_medium","before doing anything I need branch and ref number"),
    ("verify_medium","why isn’t this showing in my bank app?"),
    ("verify_medium","who exactly are you from the bank?"),
    ("verify_medium","which department is handling this?"),
    ("verify_medium","can you share official email ID?"),
    ("verify_long","banks usually don’t communicate like this, so I’ll need official branch details and a reference ID."),
    ("verify_long","I don’t see any alert in my banking app, so I need to verify this properly."),
    ("verify_long","for something this serious, there should be official confirmation somewhere.")
]

RESISTANCE = [
    ("resist_short","this feels off"),
    ("resist_short","not comfortable"),
    ("resist_short","this is weird"),
    ("resist_medium","you’re pushing this too fast"),
    ("resist_medium","I’m not sharing details like this"),
    ("resist_medium","this doesn’t feel like normal bank process"),
    ("resist_medium","I’ve already said I need verification"),
    ("resist_long","I’ve faced scam attempts earlier, so I’m extremely careful now and I won’t share personal details over chat."),
    ("resist_long","this feels rushed and honestly suspicious, I’ll contact customer care directly and confirm."),
    ("resist_long","banks don’t usually ask for sensitive information over messages, so I’m not proceeding."),
    ("resist_long","if there’s really an issue, it should reflect through official channels and not just messages.")
]

CONTRADICTION = [
    ("contradict_short","wait, that’s different"),
    ("contradict_short","you said something else earlier"),
    ("contradict_short","this changed now?"),
    ("contradict_medium","earlier you mentioned different details, can you clarify?"),
    ("contradict_medium","first you said one thing, now it’s something else"),
    ("contradict_medium","your details don’t seem consistent"),
    ("contradict_medium","this doesn’t add up properly"),
    ("contradict_long","earlier you gave different information, now you’re saying something else and that’s concerning."),
    ("contradict_long","your details keep changing, which makes this feel unreliable."),
    ("contradict_long","if this was genuine, the information wouldn’t keep changing like this.")
]

FATIGUE = [
    ("fatigue_short","ok enough"),
    ("fatigue_short","I’m done"),
    ("fatigue_short","stop messaging"),
    ("fatigue_medium","I’m not continuing this conversation"),
    ("fatigue_medium","this is going nowhere"),
    ("fatigue_medium","I’ll handle this myself"),
    ("fatigue_long","I’m done engaging here, I’ll contact the bank directly and sort this out."),
    ("fatigue_long","please don’t message me further about this, I’ll verify on my own."),
    ("fatigue_long","this conversation isn’t productive anymore, I’m stopping here.")
]

# ================= REPLY ENGINE =================
INTENT_COOLDOWN = 4

def choose_reply(session, pool):
    recent = session["recent_intents"][-INTENT_COOLDOWN:]
    candidates = [(i,t) for i,t in pool if i not in recent]
    if not candidates:
        candidates = pool
    intent, text = random.choice(candidates)
    session["recent_intents"].append(intent)
    return text

def humanize(text):
    if random.random() < 0.35:
        if random.choice([True, False]):
            text = f"{random.choice(FILLERS)}… {text}"
        else:
            text = f"{text} — {random.choice(SUFFIXES)}"
    return text

async def typing_delay(text):
    await asyncio.sleep(min(0.15 + len(text.split())*0.03, 1.8))

# ================= ROOT =================
@app.get("/")
def root():
    return {"status":"running"}

# ================= HONEYPOT =================
@app.post("/honeypot")
async def honeypot(request: Request, x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        body = await request.json()
    except:
        body = {}

    msg = ""
    if isinstance(body, dict):
        for k in ["message","msg","text","content"]:
            if k in body and isinstance(body[k], str):
                msg = body[k]
                break

    sid = body.get("session_id","default")

    if sid not in sessions:
        sessions[sid] = {
            "turns":0,
            "fatigue":0,
            "recent_intents":[],
            "seen":{"phones":set(),"upis":set(),"links":set()},
            "intel":{"phone_numbers":[],"upi_ids":[],"links":[]}
        }

    s = sessions[sid]
    s["turns"] += 1

    phones = extract_phone(msg)
    upis = extract_upi(msg)
    links = extract_links(msg)

    contradiction = False
    for p in phones:
        if s["seen"]["phones"] and p not in s["seen"]["phones"]:
            contradiction = True
        s["seen"]["phones"].add(p)

    s["intel"]["phone_numbers"].extend(phones)
    s["intel"]["upi_ids"].extend(upis)
    s["intel"]["links"].extend(links)

    if contradiction:
        base = choose_reply(s, CONTRADICTION)
        s["fatigue"] += 3
    elif phones or upis:
        base = choose_reply(s, RESISTANCE)
        s["fatigue"] += 2
    elif s["turns"] > 2:
        base = choose_reply(s, VERIFICATION)
    else:
        base = choose_reply(s, CONFUSION)

    if s["fatigue"] >= 6:
        base = choose_reply(s, FATIGUE)

    reply = humanize(base)
    await typing_delay(reply)

    return {
        "reply": reply,
        "messages_seen": s["turns"],
        "extracted_intelligence": s["intel"]
    }
