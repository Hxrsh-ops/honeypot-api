# ==========================================
# SUPER HUMAN VICTIM DATASET (EXTENDED)
# ==========================================

# ---- Neutral / filler / real-human chatter ----
FILLERS = [
    "hmm", "uh", "okay", "wait", "one sec", "alright",
    "yeah", "ya", "huh", "hmm okay", "right", "fine",
    "ok then", "hmm right", "yeah okay", "alright then",
    "got it", "okay sure", "hmm noted", "alright fine"
]

SMALL_TALK = [
    "I’m in the middle of something right now",
    "I just stepped out actually",
    "can we be quick?",
    "I’m a bit busy",
    "I’m outside, signal is weak",
    "I just got free",
    "I’m at work right now",
    "I’m driving actually",
    "I’m with someone right now",
    "I was about to sleep",
    "I just woke up",
    "I’m not near my phone all the time",
]

# ---- First contact / confusion ----
CONFUSION = [
    "sorry, who is this?",
    "I don’t recognize this number",
    "what is this regarding?",
    "I’m not sure why you’re messaging me",
    "can you explain properly?",
    "I don’t remember any issue",
    "what exactly happened?",
    "I just saw this now",
    "why am I getting this message?",
    "this is the first I’m hearing of this",
    "what problem are you talking about?",
    "can you explain clearly?",
    "I don’t understand what this is about",
    "why are you contacting me?",
    "what account is this about?"
]

# ---- Acknowledging identity / name / role ----
INTRO_ACK = [
    "okay",
    "alright",
    "noted",
    "okay got it",
    "fine",
    "hmm okay",
    "right",
    "okay, go on",
    "alright, continue",
    "okay understood",
]

# ---- Bank & authority probing ----
BANK_VERIFICATION = [
    "which bank exactly?",
    "which branch are you calling from?",
    "is this my home branch?",
    "what city is this branch in?",
    "what department is this?",
    "can you share your designation?",
    "who is the branch manager there?",
    "do you have an employee ID?",
    "is this from head office or branch?",
    "why is this handled centrally?",
    "is this customer care or branch side?",
    "what extension are you calling from?"
]

# ---- Soft cooperation (appears normal) ----
COOPERATIVE = [
    "okay, what should I do now?",
    "alright, tell me the steps",
    "okay, please explain",
    "what needs to be done?",
    "okay, guide me",
    "how do I resolve this?",
    "what exactly is required?",
    "okay, go ahead",
    "please explain clearly",
    "tell me the process",
    "okay, I’m listening",
]

# ---- Near-fall (looks convinced) ----
NEAR_FALL = [
    "okay, I don’t want any issues",
    "I’m getting worried now",
    "please make sure this fixes it",
    "okay, tell me carefully",
    "I just want this resolved",
    "I can’t afford problems right now",
    "okay, I’ll do what you say",
    "just guide me properly",
    "I hope this works",
    "okay, don’t mess this up",
]

# ---- Probing (INTEL EXTRACTION) ----
PROBING = [
    "where exactly should I do this?",
    "can you resend the details?",
    "is this UPI or bank transfer?",
    "what account should it go to?",
    "can you send the link again?",
    "what reference should I mention?",
    "is there a complaint ID?",
    "what is the ticket number?",
    "can you share the exact account details?",
    "who is the beneficiary?",
    "what name should I enter there?",
]

# ---- Soft doubt (human hesitation) ----
SOFT_DOUBT = [
    "this sounds a bit unusual",
    "I didn’t get any notification though",
    "usually the app informs me",
    "this hasn’t happened before",
    "something feels different",
    "I’m not fully convinced",
    "are you sure about this?",
    "this is confusing me",
    "can you confirm once again?",
    "this doesn’t sound normal",
]

# ---- Resistance (after contradictions) ----
RESISTANCE = [
    "this doesn’t match what you said earlier",
    "you mentioned something different before",
    "you’re changing details now",
    "this is inconsistent",
    "something is off",
    "this isn’t adding up",
    "I’m getting more confused",
    "this feels wrong now",
    "why are the details changing?",
    "this is not clear at all",
]

# ---- Fatigue / annoyance ----
FATIGUE = [
    "you keep repeating the same thing",
    "this is going in circles",
    "you’re not answering my questions",
    "why are you avoiding my questions?",
    "this is getting frustrating",
    "please be clear",
    "you’re not explaining properly",
    "this is tiring honestly",
]

# ---- Exit / disengage ----
EXIT = [
    "I’ll check this directly with the bank",
    "I’ll visit the branch instead",
    "I’ll call customer care myself",
    "I don’t want to continue this",
    "I’ll verify this independently",
    "I’m stopping this conversation",
    "I don’t trust this anymore",
    "I’m ending this here",
    "I’ll handle this offline",
]
