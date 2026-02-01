import os, re, uuid, random, asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from victim_dataset import *

app = FastAPI()

# ================= CONFIG =================
API_KEY = os.getenv("HONEYPOT_API_KEY", "")
MAX_TURNS = 30

# ================= MEMORY =================
sessions = {}

# ================= REGEX (IMPROVED) =================
UPI_REGEX = re.compile(r'\b[\w.-]+@(ybl|okaxis|oksbi|okhdfc|upi)\b', re.I)
PHONE_REGEX = re.compile(r'(?:\+91[-\s]?)?[6-9]\d{9}')
NAME_REGEX = re.compile(r"(?:i am|this is|my name is)\s+([A-Za-z]+)", re.I)
BANK_REGEX = re.compile(r"(sbi|hdfc|icici|axis|canara|pnb|bob)", re.I)

# ================= HELPERS =================
def get_session(sid):
    if sid not in sessions:
        sessions[sid] = {
            "turns": [],
            "used": set(),
            "profile": {
                "name": None,
                "bank": None,
                "phone": None,
                "upi": None,
                "links": [],
                "contradictions": 0,
            }
        }
    return sessions[sid]

def pick(pool, used):
    for _ in range(20):
        r = random.choice(pool)
        if r not in used:
            used.add(r)
            return r
    return random.choice(pool)

# ================= ROOT (ALL METHODS SAFE) =================
@app.api_route(
    "/",
    methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"]
)
async def root_probe():
    return JSONResponse({"status": "alive"})

# ================= HONEYPOT (ALL METHODS SAFE) =================
@app.api_route(
    "/honeypot",
    methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"]
)
async def honeypot(request: Request):

    # ---- SAFE BODY PARSING ----
    body = {}
    try:
        if "json" in request.headers.get("content-type", "").lower():
            body = await request.json()
    except:
        body = {}

    msg = str(
        body.get("message")
        or body.get("text")
        or body.get("input")
        or body.get("msg")
        or body.get("data")
        or ""
    )

    session_id = body.get("session_id") or str(uuid.uuid4())
    session = get_session(session_id)
    session["turns"].append(msg.lower())

    # ---- MEMORY CLEANUP ----
    if len(session["turns"]) > MAX_TURNS:
        sessions.pop(session_id, None)
        return JSONResponse({
            "reply": "I’ll check this directly with the bank.",
            "session_id": session_id
        })

    profile = session["profile"]

    # ---- EXTRACT SCAMMER INFO ----
    if not profile["name"]:
        m = NAME_REGEX.search(msg)
        if m:
            profile["name"] = m.group(1)

    if not profile["bank"]:
        b = BANK_REGEX.search(msg)
        if b:
            profile["bank"] = b.group(1).upper()

    phone = PHONE_REGEX.search(msg)
    if phone:
        profile["phone"] = phone.group(0)

    upi = UPI_REGEX.search(msg)
    if upi:
        profile["upi"] = upi.group(0)

    # ---- PHASE SELECTION ----
    text = msg.lower()

    if any(k in text for k in ["pay", "transfer", "upi", "account", "link"]):
        phase = PROBING
    elif profile["bank"]:
        phase = BANK_VERIFICATION
    elif len(session["turns"]) <= 2:
        phase = CONFUSION
    elif len(session["turns"]) <= 5:
        phase = COOPERATIVE
    elif len(session["turns"]) <= 8:
        phase = SOFT_DOUBT
    elif len(session["turns"]) <= 12:
        phase = RESISTANCE
    else:
        phase = EXIT

    reply = pick(phase, session["used"])

    # ---- PERSONALIZATION ----
    if profile["name"] and random.random() < 0.4:
        reply = f"{profile['name']}, {reply}"

    await asyncio.sleep(random.uniform(0.4, 1.2))

    return JSONResponse({
        "reply": reply,
        "session_id": session_id,
        "extracted_profile": profile
    })
