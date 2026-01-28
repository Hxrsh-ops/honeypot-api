import os
import re
import random
import time
from fastapi import FastAPI, Header, HTTPException, Request

# ================= LLM =================
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
memory = {}
beliefs = {}
intel = {}
topics_asked = {}
last_intent = {}

# ================= HELPERS =================
def delay():
    time.sleep(random.uniform(0.4, 1.2))

def extract(pattern, text):
    return re.findall(pattern, text)

def extract_all(text):
    return {
        "upi": extract(r'\b[\w.-]+@[\w.-]+\b', text),
        "links": extract(r'https?://\S+', text),
        "phones": extract(r'\b\d{10}\b', text),
        "ifsc": extract(r'\b[A-Z]{4}0[A-Z0-9]{6}\b', text),
        "email": extract(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    }

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

def ai_say(intent, context):
    if not LLM_ENABLED or not llm:
        return intent
    prompt = f"""
You are a real human chatting on WhatsApp.
Context: {context}

Rules:
- sound human
- short
- imperfect
- no AI tone
- no emojis

Say this naturally:
"{intent}"
"""
    try:
        r = llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.8,
            max_tokens=60
        )
        return r.choices[0].message.content.strip()
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

    delay()
    msg = msg.lower()

    # INIT
    if sid not in memory:
        memory[sid] = []
        beliefs[sid] = {
            "city": None,
            "ifsc": None,
            "email": None,
            "claimed_role": None,
            "urgency": 0
        }
        intel[sid] = {"upi":[], "links":[], "phones":[]}
        topics_asked[sid] = set()
        last_intent[sid] = ""

    memory[sid].append(msg)

    # ========== UPDATE BELIEFS ==========
    found = extract_all(msg)
    if found["ifsc"]: beliefs[sid]["ifsc"] = found["ifsc"][0]
    if found["email"]: beliefs[sid]["email"] = found["email"][0]
    if "mumbai" in msg: beliefs[sid]["city"] = "mumbai"
    if "head office" in msg: beliefs[sid]["claimed_role"] = "central"
    if "urgent" in msg or "immediately" in msg: beliefs[sid]["urgency"] += 1

    intel[sid]["upi"] += found["upi"]
    intel[sid]["links"] += found["links"]
    intel[sid]["phones"] += found["phones"]

    # ========== GOAL SELECTION ==========
    goal = None

    # 1. Contradiction
    if beliefs[sid]["claimed_role"] == "central" and intel[sid]["phones"]:
        goal = "challenge authority inconsistency"

    # 2. Repetition fatigue
    elif last_intent[sid] and last_intent[sid] in msg:
        goal = "call out repetition"

    # 3. Topic exhaustion
    elif "ifsc" in topics_asked[sid] and beliefs[sid]["ifsc"]:
        goal = "pivot verification"

    # 4. High urgency → pressure reversal
    elif beliefs[sid]["urgency"] >= 2:
        goal = "reverse pressure"

    # 5. Default extraction
    else:
        goal = "extract more info"

    # ========== INTENT GENERATION ==========
    if goal == "challenge authority inconsistency":
        intent = "If this is handled centrally, why are you sharing a personal number?"

    elif goal == "call out repetition":
        intent = "You already told me that. Why are you repeating instead of answering?"

    elif goal == "pivot verification":
        intent = "Instead of repeating IFSC, tell me the registered branch landline."

    elif goal == "reverse pressure":
        intent = "You keep saying urgent. Why wasn’t I notified earlier through my bank app?"

    else:  # extract
        options = [
            "Who is the branch manager handling this?",
            "Which department is sending this message?",
            "What’s the official SBI email for this case?"
        ]
        intent = random.choice(options)

    last_intent[sid] = intent
    topics_asked[sid].add(intent.split()[0])

    reply = ai_say(intent, beliefs[sid])

    return {
        "reply": reply,
        "beliefs": beliefs[sid],
        "extracted_intelligence": intel[sid]
    }
