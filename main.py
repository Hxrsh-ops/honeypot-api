import os
import random
import time
from fastapi import FastAPI, Header, HTTPException, Request

# ================== APP ==================
app = FastAPI()
API_KEY = os.getenv("HONEYPOT_API_KEY", "test-key")

# ================== MASSIVE HUMAN DATA BANK ==================

CONFUSED = [
    "wait, what is this about?",
    "which account are you talking about?",
    "i don’t remember doing anything wrong",
    "i’m not sure i understand this message",
    "why am i getting this now?",
    "what problem are you referring to?",
    "i just woke up, explain slowly",
    "sorry, i’m a bit lost here",
    "this is the first time i’m hearing this",
    "can you explain in simple words?",
    "i don’t usually get messages like this",
    "what exactly happened?",
    "is this savings or salary account?",
    "i didn’t receive any alert before",
    "what suspicious activity?",
    "i haven’t checked my account today",
    "nothing like this showed in my app",
    "i didn’t get any sms",
    "why is this sudden?",
    "i’m not able to follow this",
    "can you repeat that?",
    "i’m not good with banking terms",
    "this sounds very sudden",
    "what do you mean compromised?",
    "i’m genuinely confused now",
    "are you sure this is my account?",
    "i haven’t shared anything",
    "what exactly do you need from me?",
    "i’ve never faced this before",
    "why wasn’t i informed earlier?",
    "this doesn’t ring a bell",
    "i don’t remember any issue",
    "i checked balance yesterday",
    "everything looked normal",
    "this is confusing me more"
]

VERIFY = [
    "why are you messaging instead of calling?",
    "my bank usually calls me",
    "which branch is this related to?",
    "can you tell me the branch name?",
    "who exactly is handling this?",
    "what department are you from?",
    "why didn’t i get an email first?",
    "is there a reference number?",
    "how can i verify this independently?",
    "which city office is this?",
    "why does this not show in my bank app?",
    "can you tell me the last transaction?",
    "what is your official designation?",
    "why are you using this number?",
    "what’s the registered email for this?",
    "why am i not seeing this in net banking?",
    "do you have a complaint id?",
    "who raised this alert?",
    "what is the escalation process?",
    "which team detected this?",
    "what is your employee id?",
    "why was i not notified earlier?",
    "is this automated or manual?",
    "why does your number look personal?",
    "can i cross-check with my branch?",
    "why isn’t this from sbi domain?",
    "which division is this?",
    "can i verify by calling customer care?",
    "why does this feel rushed?",
    "how did you detect this activity?",
    "what triggered this alert?",
    "why didn’t i get ivr call?",
    "what’s the standard protocol?"
]

STALL = [
    "i’m outside right now",
    "i’m driving, can’t check",
    "phone battery is low",
    "network is very bad",
    "i need to reach home first",
    "i don’t have documents with me",
    "can i get back to you later?",
    "i’m in a meeting",
    "i’ll check once i reach office",
    "i don’t have my passbook",
    "i need to find my papers",
    "i’m traveling right now",
    "i’ll call you later",
    "give me some time please",
    "i can’t check now",
    "my phone is hanging",
    "i need to charge my phone",
    "i’m on the road",
    "i’m with someone",
    "i’ll message once free",
    "let me sit and check",
    "i don’t want to rush this",
    "i need a quiet place",
    "i’m at work",
    "i’ll look into it shortly",
    "i need to calm down",
    "this is too sudden",
    "i can’t think clearly",
    "give me a few minutes",
    "i need to check with family",
    "i’m busy right now",
    "i’ll get back to you"
]

ANNOYED = [
    "why are you rushing me so much?",
    "i already told you i need time",
    "stop repeating the same thing",
    "you’re not answering my question",
    "this is getting irritating",
    "i’m trying to cooperate",
    "why are you not listening?",
    "you’re pressuring me",
    "you said something else earlier",
    "this doesn’t make sense",
    "why is everything urgent?",
    "i’m not comfortable with this",
    "you’re confusing me",
    "your answers are unclear",
    "details keep changing",
    "this feels very off",
    "this is frustrating",
    "i’m losing patience",
    "you’re dodging questions",
    "this is not convincing",
    "stop pushing me",
    "this is weird now",
    "why can’t you answer properly",
    "i don’t trust this",
    "this is annoying",
    "you’re making it worse",
    "this is suspicious",
    "i don’t like this tone",
    "this is unnecessary pressure"
]

GENZ = [
    "wait what??",
    "bro what is this",
    "nah this feels sus",
    "this ain’t normal",
    "hold on lemme check",
    "bruh",
    "why so urgent tho",
    "ngl this feels fake",
    "stop spamming pls",
    "idk man",
    "this doesn’t add up",
    "this is sketchy",
    "lowkey looks fake",
    "nah i’m good",
    "why you rushing me",
    "this is weird af",
    "why you texting like this",
    "my bank never texts like this",
    "send proper details first",
    "how do i verify this",
    "this looks fake tbh",
    "i’m not sharing anything",
    "lemme think",
    "idk about this",
    "something’s off",
    "can you chill for a sec",
    "this stressing me out",
    "nah bro",
    "this ain’t convincing",
    "stop repeating",
    "this is sus ngl",
    "i’ll check later",
    "not doing this rn",
    "sounds like a scam",
    "yeah no"
]

FILLERS = [
    "uhh", "umm", "hmm", "uh", "huh",
    "hmm wait", "uh idk", "umm okay",
    "hmm not sure", "bruh wait", "lol wait",
    "uhh hold on", "umm give me a sec",
    "hmm pause", "uhh sorry", "hmm okay",
    "uh wait a min", "hmm idk man"
]

DATASETS = {
    "confused": CONFUSED,
    "verify": VERIFY,
    "stall": STALL,
    "annoyed": ANNOYED,
    "genz": GENZ
}

# ================== SESSION STATE ==================
sessions = {}

def human_delay():
    time.sleep(random.uniform(0.4, 1.1))

def rotate_mood(turn):
    if turn < 2:
        return "confused"
    elif turn < 4:
        return "verify"
    elif turn < 6:
        return "stall"
    elif turn < 8:
        return "annoyed"
    else:
        return random.choice(list(DATASETS.keys()))

def choose_reply(session_id):
    mood = sessions[session_id]["mood"]
    used = sessions[session_id]["used"]
    pool = DATASETS[mood]

    options = [r for r in pool if r not in used]
    if not options:
        used.clear()
        options = pool

    reply = random.choice(options)
    used.add(reply)

    if random.random() < 0.3:
        reply = f"{random.choice(FILLERS)}… {reply}"

    return reply

# ================== ROUTES ==================
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

    message = payload.get("message", "")
    session_id = payload.get("session_id", "default")

    if not payload or not message:
        return {"reply": "OK", "messages_seen": 0}

    human_delay()

    if session_id not in sessions:
        sessions[session_id] = {
            "turns": 0,
            "used": set(),
            "mood": "confused"
        }

    sessions[session_id]["turns"] += 1
    turn = sessions[session_id]["turns"]
    sessions[session_id]["mood"] = rotate_mood(turn)

    reply = choose_reply(session_id)

    return {
        "reply": reply,
        "messages_seen": turn
    }
