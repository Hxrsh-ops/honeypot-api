# ============================================================
# VICTIM DATASET v5.0 — SUPER FANTASTIC AWESOME EDITION
# Large + Human + Generative + Expandable
# ============================================================

import random

# ============================================================
# 1. CONVERSATION PHASES (DO NOT REMOVE — ONLY ADD)
# ============================================================
PHASES = [
    "casual_entry",
    "friendly_entry",
    "confusion",
    "light_confusion",
    "polite_engagement",
    "cooperative",
    "curious",
    "probing_identity",
    "probing_bank",
    "probing_process",
    "probing_payment",
    "probing_links",
    "emotional_drift",
    "fear_response",
    "near_fall",
    "partial_trust",
    "soft_doubt",
    "logic_doubt",
    "resistance",
    "strong_resistance",
    "fatigue",
    "annoyance",
    "threatened_exit",
    "final_exit",
    "post_exit"
]

# ============================================================
# 2. CORE HUMAN TEXT POOLS (BIG & REAL)
# ============================================================

BASE_POOLS = {

    # ---- Entry / Casual ----
    "casual_entry": [
        "hi",
        "hello",
        "hey",
        "who's this?",
        "who is this?",
        "what is this about?",
        "just saw this message",
        "missed call?",
        "why am I getting this?",
        "can you explain?",
        "what happened?",
        "uhh?",
        "??",
        "hello?",
        "hi, yes?"
    ],

    "friendly_entry": [
        "hi, how can I help?",
        "hello, what’s this regarding?",
        "okay, go on",
        "yes, tell me",
        "hmm, what is this about?",
        "I just opened my phone",
        "sorry, I was busy earlier",
        "hi, I’m listening"
    ],

    # ---- Confusion ----
    "confusion": [
        "I don’t remember anything like this",
        "nothing shows in my bank app",
        "I didn’t get any notification",
        "this is confusing",
        "I’m not sure what you mean",
        "can you explain clearly?",
        "what account is this about?",
        "I don’t see any issue on my side",
        "this is the first time I’m hearing this",
        "I just checked, nothing is there",
        "I don’t understand what went wrong"
    ],

    "light_confusion": [
        "hmm, not sure",
        "I don’t think so",
        "are you sure?",
        "this feels new to me",
        "I haven’t faced this before",
        "I’m a bit lost here",
        "can you explain once again?"
    ],

    # ---- Cooperation ----
    "polite_engagement": [
        "okay, please explain",
        "alright, go ahead",
        "okay, tell me slowly",
        "fine, what do I need to do?",
        "yes, please tell me",
        "okay, continue",
        "I’m listening, explain properly"
    ],

    "cooperative": [
        "okay, what should I do now?",
        "tell me the steps",
        "alright, explain step by step",
        "okay, guide me",
        "what exactly needs to be done?",
        "how do I fix this?",
        "okay, I’ll follow",
        "please explain clearly"
    ],

    "curious": [
        "why did this happen?",
        "how did this issue come?",
        "what caused this?",
        "is this common?",
        "has this happened before?",
        "why am I affected?",
        "how serious is this?"
    ],

    # ---- Probing Identity ----
    "probing_identity": [
        "who am I speaking with?",
        "what is your name?",
        "can you share your full name?",
        "what is your designation?",
        "which department is this?",
        "are you from branch or customer care?",
        "who authorized this process?",
        "how do I verify you?",
        "do you have an employee ID?",
        "who is your reporting manager?"
    ],

    # ---- Probing Bank ----
    "probing_bank": [
        "which bank is this?",
        "which branch are you calling from?",
        "what city branch?",
        "is this my home branch?",
        "is this head office?",
        "why is this handled centrally?",
        "can you tell branch address?",
        "who is the branch manager?"
    ],

    # ---- Probing Process ----
    "probing_process": [
        "what is the exact process?",
        "how long will this take?",
        "what happens after this?",
        "is this reversible?",
        "will I get confirmation?",
        "what if this fails?",
        "is there an alternative way?",
        "can I do this from app?"
    ],

    # ---- Probing Payment ----
    "probing_payment": [
        "is this UPI or bank transfer?",
        "what account should I send to?",
        "who is the beneficiary?",
        "what name should I enter?",
        "what IFSC should I use?",
        "can you send details again?",
        "is there a reference number?",
        "should I add any remark?"
    ],

    # ---- Probing Links ----
    "probing_links": [
        "the link isn’t opening",
        "can you resend the link?",
        "this link looks different",
        "is this an official site?",
        "why does the link look strange?",
        "should I install something?",
        "my phone is warning me about this link"
    ],

    # ---- Emotional Drift ----
    "emotional_drift": [
        "this is stressing me out",
        "I’m getting worried now",
        "I don’t want any trouble",
        "this is making me anxious",
        "I’m scared something bad will happen",
        "I can’t afford issues right now"
    ],

    "fear_response": [
        "will my account get blocked?",
        "will I lose money?",
        "is my balance safe?",
        "what if I don’t do this?",
        "how urgent is this really?",
        "what happens if I delay?"
    ],

    # ---- Near Fall ----
    "near_fall": [
        "okay, I trust you",
        "please make sure this works",
        "I don’t want problems",
        "just help me fix this",
        "okay, tell me carefully",
        "I’ll do what you say",
        "please don’t mess this up"
    ],

    "partial_trust": [
        "okay, I believe you",
        "you sound genuine",
        "this seems official",
        "okay, let’s do this",
        "I hope this is legit"
    ],

    # ---- Doubt ----
    "soft_doubt": [
        "this sounds a bit unusual",
        "I didn’t get any official alert",
        "normally the app informs me",
        "this feels different",
        "I want to double check",
        "are you sure about this?"
    ],

    "logic_doubt": [
        "why didn’t the app notify me?",
        "why are details changing?",
        "this doesn’t make sense",
        "banks usually don’t do this",
        "this process seems odd"
    ],

    # ---- Resistance ----
    "resistance": [
        "this doesn’t match what you said earlier",
        "you mentioned something different before",
        "details are changing now",
        "this is inconsistent",
        "something feels off",
        "this isn’t adding up"
    ],

    "strong_resistance": [
        "I’m not comfortable continuing",
        "I don’t trust this anymore",
        "this feels like a scam now",
        "I won’t proceed like this",
        "I need official confirmation"
    ],

    # ---- Fatigue ----
    "fatigue": [
        "you keep repeating the same thing",
        "this is going in circles",
        "you’re not answering my questions",
        "this is getting frustrating",
        "please be clear",
        "this is tiring honestly"
    ],

    "annoyance": [
        "stop messaging me like this",
        "why are you pushing so much?",
        "this is annoying now",
        "don’t rush me",
        "give proper answers"
    ],

    # ---- Exit ----
    "threatened_exit": [
        "I’ll check this directly with the bank",
        "I’ll call customer care myself",
        "I’ll visit the branch",
        "I’m not proceeding online"
    ],

    "final_exit": [
        "I’m ending this conversation",
        "do not contact me again",
        "I’m blocking this number",
        "this conversation is over",
        "stop messaging me"
    ],

    "post_exit": [
        "any further messages will be reported",
        "this is your final warning",
        "I’ve already informed the bank",
        "do not message again"
    ]
}

# ============================================================
# 3. SLANG / SHORT FORMS (VERY IMPORTANT FOR HUMAN FEEL)
# ============================================================

SLANG_MAP = {
    "please": ["pls", "plz"],
    "okay": ["ok", "k"],
    "I am": ["I'm"],
    "I will": ["I'll"],
    "do not": ["don't"],
    "cannot": ["can't"],
    "because": ["bc"],
    "before": ["b4"],
    "you": ["u"],
    "your": ["ur"],
}

# ============================================================
# 4. TYPING STYLES (PEOPLE TYPE DIFFERENTLY)
# ============================================================

def apply_style(text: str) -> str:
    styles = []

    styles.append(lambda t: t.lower())
    styles.append(lambda t: t.capitalize())
    styles.append(lambda t: t + random.choice(["", " …", " pls", " asap"]))
    styles.append(lambda t: t.replace("you", "u").replace("your", "ur"))
    styles.append(lambda t: t if len(t.split()) < 8 else " ".join(t.split()[:8]))
    styles.append(lambda t: t + random.choice([" 😟", " 😕", " 🤔", ""]))

    return random.choice(styles)(text)

# ============================================================
# 5. LONG CONVERSATION EXPANDER (FOR BIG REPLIES)
# ============================================================

def expand_long(text: str) -> str:
    long_forms = [
        f"{text}. I’m really confused and don’t understand what’s happening.",
        f"{text}. This has never happened before and I’m worried.",
        f"{text}. Please explain properly because I don’t want any issues.",
        f"{text}. I just want to make sure my account is safe.",
        f"{text}. Can you please guide me step by step?"
    ]
    return random.choice(long_forms)

# ============================================================
# 6. FINAL HUMANIZER (AGENT CALLS THIS)
# ============================================================

def humanize_reply(phase: str) -> str:
    pool = BASE_POOLS.get(phase, [])
    if not pool:
        return "ok"

    text = random.choice(pool)

    # slang replacement
    for k, v in SLANG_MAP.items():
        if k in text and random.random() < 0.25:
            text = text.replace(k, random.choice(v))

    # style
    text = apply_style(text)

    # long reply chance
    if random.random() < 0.45:
        text = expand_long(text)

    return text
