import os
import re
import random
import time
from fastapi import FastAPI, Header, HTTPException, Request

# ================= LLM SETUP =================
LLM_ENABLED = bool(os.getenv("OPENAI_API_KEY"))
if LLM_ENABLED:
    try:
        from openai import OpenAI
        llm = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except:
        llm = None
        LLM_ENABLED = False
else:
    llm = None

# ================= APP =================
app = FastAPI()
API_KEY = os.getenv("HONEYPOT_API_KEY", "test-key")

# ================= MEMORY =================
conversation = {}
intel = {}
score = {}
phase = {}
emotion = {}
repeat_counter = {}
last_reply_time = {}

# ================= HELPERS =================
def human_delay():
    time.sleep(random.uniform(0.5, 1.4))

def extract_upi(t): return re.findall(r'\b[\w.-]+@[\w.-]+\b', t)
def extract_links(t): return re.findall(r'https?://\S+', t)
def extract_phone(t): return re.findall(r'\b\d{10}\b', t)

def deep_find(obj, keys):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in keys and isinstance(v, str):
                return v
            found = deep_find(v, keys)
            if found: return found
    elif isinstance(obj, list):
        for i in obj:
            found = deep_find(i, keys)
            if found: return found
    return ""

def calc_score(t):
    s = 0
    for k in ["upi","pay","otp","urgent","verify","blocked","account","security","freeze"]:
        if k in t: s += 10
    if extract_upi(t): s += 25
    if extract_links(t): s += 20
    if extract_phone(t): s += 15
    return s

def ai_humanize(intent, emo, ph, annoyed=False):
    if not LLM_ENABLED or not llm:
        return intent

    tone = "annoyed and impatient" if annoyed else emo

    prompt = f"""
You are a real human chatting on WhatsApp.

Emotion: {tone}
Phase: {ph}

Rules:
- sound human, imperfect
- short (1–2 lines)
- no AI tone
- no explanations
- no emojis

Rewrite naturally:
"{intent}"
"""

    try:
        r = llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.75,
            max_tokens=60
        )
        out = r.choices[0].message.content.strip()
        return out if len(out) < 200 else intent
    except:
        return intent

# ================= ROUTES =================
@app.get("/")
def root():
    return {"status": "running"}

@app.post("/honeypot")
async def honeypot(req: Request, x_api_key: str = Header(None)):

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    try:
        payload = await req.json()
    except:
        payload = {}

    msg = deep_find(payload, ["message","msg","text","content"]).strip()
    sid = deep_find(payload, ["session_id","session","chat_id","id"]) or "default"

    # Tester ping
    if not payload or not msg:
        return {"reply": "OK"}

    human_delay()
    msg = msg.lower()

    # INIT
    if sid not in conversation:
        conversation[sid] = []
        intel[sid] = {"upi":[], "links":[], "phone":[]}
        score[sid] = 0
        phase[sid] = "confusion"
        emotion[sid] = "neutral"
        repeat_counter[sid] = 0
        last_reply_time[sid] = time.time()

    # Repeat detection
    if conversation[sid] and msg == conversation[sid][-1]:
        repeat_counter[sid] += 1
    else:
        repeat_counter[sid] = 0

    conversation[sid].append(msg)

    # Intel
    intel[sid]["upi"] += extract_upi(msg)
    intel[sid]["links"] += extract_links(msg)
    intel[sid]["phone"] += extract_phone(msg)
    score[sid] = min(100, score[sid] + calc_score(msg))

    # Phase transitions
    if score[sid] > 30 and phase[sid] == "confusion":
        phase[sid] = "verify"; emotion[sid] = "uneasy"
    if score[sid] > 55 and phase[sid] == "verify":
        phase[sid] = "delay"; emotion[sid] = "worried"
    if score[sid] > 75 and phase[sid] == "delay":
        phase[sid] = "pressure_reverse"; emotion[sid] = "suspicious"
    if score[sid] > 90:
        phase[sid] = "extract"; emotion[sid] = "annoyed"

    # Time-based impatience
    annoyed = False
    if time.time() - last_reply_time[sid] < 3:
        annoyed = True

    last_reply_time[sid] = time.time()

    # Memory callback
    if repeat_counter[sid] >= 2:
        intent = "You already said the same thing. Why are you repeating this?"
        reply = ai_humanize(intent, emotion[sid], phase[sid], annoyed=True)
        return {
            "reply": reply,
            "phase": phase[sid],
            "emotion": emotion[sid],
            "scam_score": score[sid],
            "extracted_intelligence": intel[sid]
        }

    # Intent engine
    intents = {
        "confusion": [
            "Which account are you talking about?",
            "I don’t understand what this is.",
            "Can you explain clearly?"
        ],
        "verify": [
            "Why are you messaging instead of calling from registered number?",
            "Tell me the branch name linked to this account.",
            "What city branch is this?"
        ],
        "delay": [
            "I’m outside, need time.",
            "My documents are at home.",
            "I’ll check once I reach."
        ],
        "pressure_reverse": [
            "Earlier you said 2 hours, now it’s immediate?",
            "Why can’t I just visit the bank?",
            "This is sounding strange."
        ],
        "extract": [
            "Before sharing anything, tell me IFSC and branch.",
            "What’s the official SBI email for this?",
            "Which branch manager is handling this?"
        ]
    }

    base = random.choice(intents[phase[sid]])
    reply = ai_humanize(base, emotion[sid], phase[sid], annoyed)

    return {
        "reply": reply,
        "phase": phase[sid],
        "emotion": emotion[sid],
        "scam_score": score[sid],
        "extracted_intelligence": intel[sid]
    }
