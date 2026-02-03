# ============================================================
# VICTIM DATASET v5.5 — CANONICAL / NO-MISSING-SECTIONS
# Human • Exhaustive • Stable • Expandable
# ============================================================

import random

# ============================================================
# 1. PHASE REGISTRY (DO NOT CHANGE NAMES)
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

    "time_pressure",
    "authority_pressure",
    "verification_loop",
    "technical_confusion",
    "delay_tactics",
    "self_reassurance",
    "third_party_reference",
    "fake_compliance",
    "last_minute_doubt",
    "cooldown_state",

    "threatened_exit",
    "final_exit",
    "post_exit",
]

# ============================================================
# 2. BASE POOLS (EVERY PHASE ≥ 20 LINES)
# ============================================================

BASE_POOLS = {

# ------------------------------------------------------------
# ENTRY
# ------------------------------------------------------------
"casual_entry": [
    "hi", "hello", "hey", "who is this?", "missed call?",
    "just saw this", "what’s this about?", "why am I getting this?",
    "unknown number?", "can you explain?", "hello?", "hi?", "yes?",
    "what happened?", "why message me?", "what is this?",
    "I just opened my phone", "who are you?", "??", "what’s going on?"
],

"friendly_entry": [
    "hi, how can I help?", "hello, what’s this regarding?",
    "okay, go on", "yes, tell me", "hmm, explain",
    "sorry, was busy", "hi, I’m listening", "alright, tell me",
    "okay, what is it?", "yes?", "go ahead", "you can explain",
    "okay, continue", "tell me briefly", "hi there",
    "yes, what’s the issue?", "okay, listening", "tell me",
    "what’s the matter?", "go on then"
],

# ------------------------------------------------------------
# CONFUSION
# ------------------------------------------------------------
"confusion": [
    "I don’t remember anything like this",
    "nothing shows in my bank app",
    "I didn’t get any notification",
    "this is confusing",
    "I don’t understand",
    "what account is this?",
    "this is new to me",
    "I see no issue",
    "this is the first time",
    "I just checked, nothing there",
    "I don’t get it",
    "this doesn’t ring a bell",
    "I’m not aware of this",
    "no alerts on my side",
    "I’m lost",
    "can you clarify?",
    "this seems odd",
    "I’m not sure",
    "what exactly happened?",
    "this makes no sense"
],

"light_confusion": [
    "hmm not sure", "are you sure?", "maybe?",
    "this feels unfamiliar", "I don’t think so",
    "not sure about this", "I’m unsure",
    "could be a mistake", "I doubt it",
    "I don’t recall", "sounds strange",
    "this is odd", "I’m confused a bit",
    "can you repeat?", "hmm",
    "maybe I missed it", "this feels off",
    "I’m not convinced", "unclear",
    "I need clarity"
],

# ------------------------------------------------------------
# ENGAGEMENT
# ------------------------------------------------------------
"polite_engagement": [
    "okay please explain", "alright go ahead",
    "tell me slowly", "fine, explain",
    "yes please", "okay continue",
    "I’m listening", "go step by step",
    "okay, explain clearly", "yes, tell me",
    "alright then", "okay",
    "please elaborate", "continue please",
    "explain properly", "I’m paying attention",
    "go on", "you can explain",
    "tell me in detail", "explain once"
],

"cooperative": [
    "okay what should I do?",
    "tell me the steps",
    "guide me",
    "okay I’ll follow",
    "what next?",
    "alright, tell me",
    "how do I proceed?",
    "okay fine",
    "what is required?",
    "I’ll do it",
    "tell me how",
    "okay I’m ready",
    "go ahead",
    "please guide",
    "what needs to be done?",
    "I’ll comply",
    "okay show me",
    "tell me process",
    "I’ll try",
    "help me do this"
],

"curious": [
    "why did this happen?",
    "how did this occur?",
    "what caused this?",
    "is this common?",
    "has this happened before?",
    "why me?",
    "how serious is this?",
    "what triggered it?",
    "why now?",
    "how often does this happen?",
    "what’s the reason?",
    "how did you detect this?",
    "why was I selected?",
    "how does this work?",
    "what’s behind this?",
    "what system flagged it?",
    "why my account?",
    "how did you find this?",
    "what went wrong?",
    "why this issue?"
],

# ------------------------------------------------------------
# PROBING
# ------------------------------------------------------------
"probing_identity": [
    "who am I speaking with?",
    "what’s your name?",
    "full name please",
    "your designation?",
    "which department?",
    "branch or customer care?",
    "employee ID?",
    "who authorized this?",
    "how do I verify you?",
    "who is your manager?",
    "what’s your extension?",
    "official email?",
    "ID proof?",
    "can I verify you?",
    "who assigned you?",
    "what role are you?",
    "who do you report to?",
    "what’s your title?",
    "where are you calling from?",
    "how can I confirm you?"
],

"probing_bank": [
    "which bank?",
    "which branch?",
    "branch city?",
    "home branch?",
    "head office?",
    "why central?",
    "branch address?",
    "manager name?",
    "bank code?",
    "which division?",
    "is this RBI?",
    "what zone?",
    "regional office?",
    "branch phone?",
    "official contact?",
    "bank reference?",
    "bank email?",
    "what branch code?",
    "where is branch?",
    "confirm bank name"
],

"probing_process": [
    "what is the process?",
    "step by step?",
    "how long will it take?",
    "what happens after?",
    "is this reversible?",
    "confirmation?",
    "what if it fails?",
    "alternative method?",
    "can I do via app?",
    "manual or automatic?",
    "what’s the workflow?",
    "how is it resolved?",
    "is this safe?",
    "what system is this?",
    "why this process?",
    "who handles it?",
    "what exactly happens?",
    "explain flow",
    "break it down",
    "clarify process"
],

"probing_payment": [
    "UPI or transfer?",
    "which account?",
    "beneficiary name?",
    "what IFSC?",
    "send details again",
    "reference number?",
    "remarks?",
    "exact amount?",
    "partial payment?",
    "one time?",
    "refund after?",
    "why payment?",
    "what charge?",
    "fee involved?",
    "who receives it?",
    "payment proof?",
    "transaction ID?",
    "how to pay?",
    "where to pay?",
    "confirm payment details"
],

"probing_links": [
    "link not opening",
    "resend link",
    "looks suspicious",
    "official site?",
    "why strange URL?",
    "need to install?",
    "phone warning",
    "is link secure?",
    "HTTPS?",
    "site looks fake",
    "why different domain?",
    "can I avoid link?",
    "is app required?",
    "browser blocked it",
    "this looks unsafe",
    "is this legit?",
    "why redirect?",
    "site not loading",
    "is this phishing?",
    "verify link"
],

# ------------------------------------------------------------
# EMOTIONAL
# ------------------------------------------------------------
"emotional_drift": [
    "this is stressing me",
    "I’m worried now",
    "I feel anxious",
    "this is scary",
    "I don’t want trouble",
    "this is overwhelming",
    "I’m panicking",
    "this is tense",
    "I’m nervous",
    "this is serious",
    "I’m uneasy",
    "I’m uncomfortable",
    "this is alarming",
    "I’m tense",
    "this is too much",
    "I’m shaken",
    "this is stressful",
    "I’m concerned",
    "this worries me",
    "I feel pressured"
],

"fear_response": [
    "will my account block?",
    "will I lose money?",
    "is my balance safe?",
    "what if I don’t act?",
    "how urgent?",
    "what’s the risk?",
    "will funds freeze?",
    "is this dangerous?",
    "what if delayed?",
    "what’s worst case?",
    "am I at risk?",
    "can money go?",
    "will card stop?",
    "what will happen?",
    "is my account compromised?",
    "how bad is it?",
    "is this critical?",
    "will services stop?",
    "is this fraud?",
    "what danger?"
],

# ------------------------------------------------------------
# TRUST / DOUBT / RESISTANCE
# ------------------------------------------------------------
"near_fall": [
    "okay I trust you",
    "please fix this",
    "I don’t want issues",
    "I’ll do as told",
    "just help me",
    "tell me carefully",
    "okay fine",
    "I’m relying on you",
    "please resolve",
    "I believe you",
    "okay let’s do it",
    "I’m convinced",
    "don’t mess this up",
    "I need this fixed",
    "please hurry",
    "I trust this",
    "okay I’ll proceed",
    "make sure it works",
    "help me out",
    "I’m agreeing"
],

"partial_trust": [
    "you sound genuine",
    "seems official",
    "this looks legit",
    "I think it’s real",
    "okay maybe",
    "you seem valid",
    "sounds okay",
    "probably official",
    "I think so",
    "this feels real",
    "okay I guess",
    "seems authentic",
    "looks right",
    "maybe legit",
    "I trust this a bit",
    "not fully sure but okay",
    "partially convinced",
    "looks okay",
    "sounds right",
    "could be genuine"
],

"soft_doubt": [
    "sounds unusual",
    "no official alert",
    "app didn’t notify",
    "this feels different",
    "I want to check",
    "are you sure?",
    "this is odd",
    "I’m unsure",
    "something’s off",
    "not convinced",
    "this isn’t normal",
    "I want verification",
    "I doubt this",
    "this feels strange",
    "why no message?",
    "bank doesn’t do this",
    "this is weird",
    "I need to verify",
    "I have doubts",
    "questionable"
],

"logic_doubt": [
    "this doesn’t add up",
    "details keep changing",
    "process is odd",
    "bank policy differs",
    "this is illogical",
    "why manual?",
    "why OTP?",
    "this contradicts",
    "logic fails",
    "this isn’t standard",
    "no record of this",
    "rules don’t match",
    "bank won’t ask this",
    "this breaks policy",
    "inconsistent info",
    "doesn’t align",
    "something wrong",
    "logic mismatch",
    "process invalid",
    "this is flawed"
],

"resistance": [
    "this doesn’t match earlier",
    "you changed details",
    "inconsistent info",
    "this feels wrong",
    "I’m not okay with this",
    "I’m resisting",
    "I don’t like this",
    "this is shady",
    "I’m uncomfortable",
    "I won’t proceed",
    "this is suspicious",
    "I’m pushing back",
    "I don’t agree",
    "I’m stopping",
    "this is unacceptable",
    "I object",
    "this is unsafe",
    "I refuse",
    "I don’t consent",
    "this is wrong"
],

"strong_resistance": [
    "this is a scam",
    "I don’t trust you",
    "I’m done",
    "stop now",
    "I refuse completely",
    "this is fraud",
    "don’t contact me",
    "I’m ending this",
    "this is illegal",
    "I will report",
    "this is fake",
    "I know this is scam",
    "stop messaging",
    "I’m blocking you",
    "this is harassment",
    "cease contact",
    "this is dangerous",
    "back off",
    "conversation over",
    "final warning"
],

# ------------------------------------------------------------
# ADVANCED SCAM DYNAMICS / HUMAN REACTIONS
# ------------------------------------------------------------

"time_pressure": [
    "you’re saying this is urgent?",
    "how much time do I actually have?",
    "why such a short deadline?",
    "this feels rushed",
    "can this wait till tomorrow?",
    "why immediate action?",
    "I need some time to think",
    "why are you pushing so fast?",
    "this is happening too quickly",
    "can I do this later?",
    "why the hurry?",
    "is there any extension?",
    "I can’t act instantly",
    "this pressure is too much",
    "why now all of a sudden?",
    "I need time to process this",
    "this feels forced",
    "I don’t like deadlines like this",
    "can you slow down?",
    "this urgency is stressing me"
],

"authority_pressure": [
    "you’re saying this is from head office?",
    "are you senior staff?",
    "is this officially approved?",
    "who authorized this action?",
    "are you branch manager?",
    "is this RBI instructed?",
    "you sound very authoritative",
    "are you sure this is allowed?",
    "banks don’t usually threaten",
    "why are you commanding like this?",
    "this tone feels intimidating",
    "I don’t respond well to pressure",
    "authority doesn’t mean correctness",
    "can I verify your authority?",
    "are you legally allowed to ask this?",
    "this doesn’t feel professional",
    "officials don’t rush customers",
    "why such dominance?",
    "this feels coercive",
    "I’m uncomfortable with this tone"
],

"verification_loop": [
    "I want to verify this first",
    "let me cross-check once",
    "I need confirmation again",
    "I want to double verify",
    "how do I independently confirm this?",
    "I’m stuck verifying this",
    "nothing matches what you said",
    "verification keeps failing",
    "I’m not satisfied with verification",
    "details aren’t verifiable",
    "I’m unable to confirm this",
    "verification is unclear",
    "I keep checking but nothing shows",
    "can you give proof?",
    "this fails verification",
    "I can’t validate this info",
    "verification loop is confusing",
    "I need solid proof",
    "this doesn’t verify",
    "still not confirmed"
],

"technical_confusion": [
    "my app is not showing this",
    "I don’t see this option",
    "where exactly should I click?",
    "this screen looks different",
    "my app version is updated",
    "I’m not tech savvy",
    "this button isn’t there",
    "I don’t understand this interface",
    "nothing happens when I try",
    "this isn’t working",
    "my phone is lagging",
    "this app flow is confusing",
    "this step doesn’t exist",
    "I can’t find this option",
    "the app behaves differently",
    "this doesn’t match screenshots",
    "I’m lost in the app",
    "this UI is unfamiliar",
    "technical steps are unclear",
    "this process is confusing me"
],

"delay_tactics": [
    "I’m busy right now",
    "I’ll check later",
    "can we do this after some time?",
    "I’m not free at the moment",
    "let me call you back",
    "I need to step out",
    "I’ll handle this later",
    "I need to think",
    "can we pause this?",
    "I’ll respond after checking",
    "let me get back",
    "I’m occupied currently",
    "I need a break",
    "I can’t do this now",
    "I’ll message later",
    "can this wait?",
    "I need time",
    "let’s continue later",
    "I’ll check after work",
    "not available right now"
],

"self_reassurance": [
    "okay calm down",
    "don’t panic",
    "let me think clearly",
    "I need to stay calm",
    "this might be nothing",
    "don’t rush decisions",
    "I should think logically",
    "stay composed",
    "don’t act impulsively",
    "I’ll handle this carefully",
    "one step at a time",
    "no need to panic",
    "I’ll verify properly",
    "I should stay alert",
    "be cautious",
    "this needs careful thought",
    "I won’t rush",
    "I’ll assess this calmly",
    "take it slow",
    "think before acting"
],

"third_party_reference": [
    "I’ll ask my friend",
    "I’ll check with family",
    "I’ll consult someone",
    "let me ask my brother",
    "I’ll confirm with bank staff",
    "I’ll talk to my manager",
    "I’ll check with someone knowledgeable",
    "I’ll ask customer care",
    "I’ll verify with another source",
    "I’ll consult a trusted person",
    "I’ll cross-check externally",
    "I’ll seek advice",
    "I’ll confirm offline",
    "I’ll talk to a banker",
    "I’ll ask my colleague",
    "I’ll check with branch",
    "I’ll consult someone first",
    "I won’t do this alone",
    "I need a second opinion",
    "I’ll ask around"
],

"fake_compliance": [
    "okay I’m doing it now",
    "yes, one minute",
    "okay, processing",
    "wait, almost done",
    "I’m entering details",
    "just a second",
    "okay, loading",
    "working on it",
    "processing now",
    "one moment please",
    "doing it slowly",
    "almost finished",
    "okay, hold on",
    "yes, checking",
    "just completing it",
    "I’m on that step",
    "currently doing it",
    "yes, give me a sec",
    "working on it now",
    "still in progress"
],

"last_minute_doubt": [
    "wait, something feels off",
    "hold on, this is strange",
    "I suddenly feel unsure",
    "this doesn’t feel right",
    "why am I hesitating?",
    "something just clicked",
    "I’m having second thoughts",
    "this feels risky",
    "I don’t think I should do this",
    "my gut says no",
    "this might be wrong",
    "I’m not comfortable anymore",
    "this seems dangerous",
    "I should stop",
    "this doesn’t feel safe",
    "I think I made a mistake",
    "I need to stop here",
    "this is not okay",
    "I shouldn’t proceed",
    "I’m backing out"
],

"cooldown_state": [
    "I need to pause",
    "let’s slow this down",
    "I’m stepping back",
    "I need clarity",
    "I’ll reassess later",
    "I’m cooling off",
    "I need space to think",
    "let me reflect",
    "I’ll come back to this",
    "I need distance",
    "let’s pause this",
    "I’ll take time",
    "I’m disengaging temporarily",
    "I’ll think calmly",
    "this needs a break",
    "I’m stepping away",
    "I’ll revisit later",
    "I need mental space",
    "cooling down now",
    "pausing this conversation"
],


# ------------------------------------------------------------
# FATIGUE / EXIT
# ------------------------------------------------------------
"fatigue": [
    "you’re repeating",
    "this is circular",
    "answer properly",
    "this is tiring",
    "I’m exhausted",
    "stop repeating",
    "this is draining",
    "enough already",
    "this is going nowhere",
    "I’m fed up",
    "too much back and forth",
    "wasting time",
    "this is annoying",
    "no clear answer",
    "I’m frustrated",
    "this is pointless",
    "I’m tired of this",
    "end this",
    "this is irritating",
    "I’ve had enough"
],

"annoyance": [
    "stop spamming",
    "don’t rush me",
    "this is annoying",
    "why pressure?",
    "give proper answers",
    "stop messaging",
    "you’re irritating",
    "don’t push",
    "this is too much",
    "back off",
    "leave me alone",
    "why force?",
    "this is harassment",
    "enough messages",
    "I’m annoyed",
    "stop now",
    "this is nonsense",
    "don’t bother me",
    "go away",
    "I’m irritated"
],

"threatened_exit": [
    "I’ll call the bank",
    "I’ll visit branch",
    "I’ll contact support",
    "I’ll verify offline",
    "I’m stopping this",
    "I’ll check myself",
    "I’ll confirm independently",
    "I won’t do this online",
    "I’ll escalate",
    "I’ll report this",
    "I’ll check with staff",
    "I’ll verify in person",
    "I’m disengaging",
    "I won’t continue",
    "I’m done here",
    "I’ll block this",
    "I’ll verify directly",
    "I’m stopping",
    "this ends now",
    "I’ll handle it myself"
],

"final_exit": [
    "stop contacting me",
    "conversation over",
    "do not message again",
    "I’m blocking you",
    "final warning",
    "this ends here",
    "no further contact",
    "I’m reporting this",
    "cease communication",
    "I’m done",
    "goodbye",
    "end of discussion",
    "this is final",
    "don’t message again",
    "blocked",
    "reported",
    "finished",
    "no more",
    "end now",
    "terminated"
],

"post_exit": [
    "any further message will be reported",
    "bank already informed",
    "this number is reported",
    "do not attempt again",
    "legal action initiated",
    "this is logged",
    "reported to authorities",
    "do not reply",
    "case registered",
    "ignored",
    "blocked permanently",
    "cease attempts",
    "final notice",
    "do not engage",
    "this is documented",
    "stop now",
    "further contact illegal",
    "this is evidence",
    "reported officially",
    "case closed"
],
}

# ============================================================
# 3. HUMANIZER
# ============================================================

SLANG_MAP = {
    "please": ["pls", "plz"],
    "okay": ["ok", "k"],
    "I am": ["I'm"],
    "I will": ["I'll"],
    "do not": ["don't"],
    "cannot": ["can't"],
    "you": ["u"],
    "your": ["ur"],
}

def humanize_reply(phase: str) -> str:
    pool = BASE_POOLS.get(phase, [])
    if not pool:
        return "ok"

    text = random.choice(pool)

    for k, v in SLANG_MAP.items():
        if k in text and random.random() < 0.3:
            text = text.replace(k, random.choice(v))

    if random.random() < 0.35:
        text += random.choice([" …", " 🤔", " 😕", ""])

    if random.random() < 0.25:
        text = f"{text}. Please explain clearly."

    return text

# ============================================================
# 4. LEGACY EXPORTS (AGENT SAFE)
# ============================================================

ALL_SCENARIO_POOLS = BASE_POOLS
