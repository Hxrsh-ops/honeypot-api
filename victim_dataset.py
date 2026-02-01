# ==========================================
# SUPER HUMAN VICTIM DATASET (EXTENDED, STYLES + SCENARIOS)
# ==========================================
import random
# BANK NAMES / DOMAINS (used for legitimacy heuristics)
BANKS = [
    "sbi", "hdfc", "icici", "axis", "canara", "pnb", "bob", "idbi", "kotak",
    "yesbank", "indusind", "ubi", "unionbank", "bandhan", "citi", "hsbc"
]
BANK_DOMAINS = ["sbi.co.in", "hdfcbank.com", "icicibank.com", "axisbank.com", "canarabank.com"]

# Legit patterns that often indicate official messages
LEGIT_PATTERNS = [
    "dear customer", "transaction of", "credited to your account", "debit alert",
    "if not initiated by you", "for assistance call", "toll free", "thank you for banking with",
    "regards", "sincerely", "customer id", "account number ending"
]

# OTP and safety reminders (bot should use these when asked for OTP)
OTP_WARNINGS = [
    "I never share OTPs. If this is about my account I'll call the bank directly.",
    "I won't provide any OTP or password. Please confirm this is from the bank.",
    "I don't share any verification codes. I'll call the bank's official number instead."
]

# ---- Neutral / filler / real-human chatter ----
FILLERS = [
    "hmm", "uh", "okay", "wait", "one sec", "alright",
    "yeah", "ya", "huh", "hmm okay", "right", "fine",
    "ok then", "hmm right", "yeah okay", "alright then",
    "got it", "okay sure", "hmm noted", "alright fine",
    "mm hmm", "bear with me", "let me see", "one moment"
]

# ---- Small talk choices ----
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
    "Ah okay, hang on a sec",
    "Sorry, I have a meeting"
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
    "please give details",
    "who am I talking to exactly?"
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
    "what extension are you calling from?",
    "please provide a formal email or ID",
    "can you give me your employee ID or name so I can verify?"
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
    "I can try that, but I'm careful with any payment"
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
    "okay, don’t mess this up"
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
    "can you write the exact UPI ID again?",
    "what bank is the beneficiary with?",
    "please show me the account number in full",
    "do you have a transaction reference or virtual ID?",
    "what's the IFSC?"
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
    "I want to verify that on my bank app first"
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
    "I’ll need written proof or an official mail"
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
    "stop repeating yourself"
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
    "Please stop contacting me"
]

# ---- OTP / security focused replies ----
SECURITY_REPLIES = [
    "I will not share any OTP or passwords.",
    "No one should ask for my OTP. I will call the bank's official number.",
    "I keep my OTP private. Please send official communication if needed."
]

# ---- Persona styles (decoy personality flavours) ----
PERSONA_STYLE_KEYS = ["confused", "cooperative", "cautious", "nearly_convinced", "frustrated"]
PERSONA_STYLE_TEMPLATES = {
    "confused": CONFUSION + ["who is this? please explain properly", "I’m not sure what you mean, can you elaborate?"],
    "cooperative": COOPERATIVE + ["okay, I’m listening — step by step please"],
    "cautious": SOFT_DOUBT + SECURITY_REPLIES,
    "nearly_convinced": NEAR_FALL + ["I really want this sorted out quickly"],
    "frustrated": FATIGUE + RESISTANCE
}

# Expand dataset with scenario-based replies for common scam flows
# Example scenarios: KYC/Verification scams, Fake refunds, Payment collection, OTP tricking, Phishing links, Authority impersonation

# ---- KYC / Document requests ----
KYC_SCENARIOS = [
    "please send a scanned copy of your ID",
    "we need your PAN and Aadhaar for verification",
    "upload a photo and sign the document at this link",
    "please fill out this KYC form at http://..."
] + PROBING + BANK_VERIFICATION

# ---- Fake refunds / deposit scams ----
REFUND_SCENARIOS = [
    "We have a pending refund of Rs. 10,000 to your account, please provide account details",
    "A duplicate transaction was detected; share your UPI to credit the refund",
    "We need to confirm beneficiary details to release the refund"
] + PROBING + SOFT_DOUBT

# ---- Payment / transfer collection attempts ----
COLLECTION_SCENARIOS = [
    "You must pay tax or fee to release your account",
    "Please transfer Rs. XXXX to confirm your identity",
    "Pay through the link to avoid account suspension"
] + PROBING + RESISTANCE

# ---- Phishing link messages ----
PHISHING_LINKS = [
    "Click this link to verify: http://phish.example/verify",
    "Open this attachment and complete verification",
    "Install this app to proceed: http://app.example/install"
] + PROBING

# ---- Authority impersonation (manager/ico/customer care) ----
AUTHORITY_SCENARIOS = [
    "I am the branch manager, this is urgent",
    "This is a system alert from fraud control, act now",
    "This is customer care, we require immediate verification",
    "This is from the head office — share your details for enforcement"
] + BANK_VERIFICATION + RESISTANCE

# ---- Additional small probes and clarifications ----
EXTRA_PROBES = [
    "Can you send your employee ID and extension?",
    "What is the transaction reference?",
    "Is there a complaint ID or ticket number?",
    "Which bank and branch should I contact?",
    "What exact amount and purpose should I enter in transfer?"
]

# Combine and export common pools
PROBING = list(dict.fromkeys(PROBING + EXTRA_PROBES + ["Please provide exact beneficiary name and account."]))
BANK_VERIFICATION = list(dict.fromkeys(BANK_VERIFICATION))
COOPERATIVE = list(dict.fromkeys(COOPERATIVE))
SOFT_DOUBT = list(dict.fromkeys(SOFT_DOUBT))
RESISTANCE = list(dict.fromkeys(RESISTANCE))
NEAR_FALL = list(dict.fromkeys(NEAR_FALL))
FATIGUE = list(dict.fromkeys(FATIGUE))
EXIT = list(dict.fromkeys(EXIT))
SMALL_TALK = list(dict.fromkeys(SMALL_TALK))
FILLERS = list(dict.fromkeys(FILLERS))

# Utility: quick mapping for external modules
ALL_SCENARIO_POOLS = {
    "fillers": FILLERS,
    "small_talk": SMALL_TALK,
    "confusion": CONFUSION,
    "intro_ack": INTRO_ACK,
    "bank_verification": BANK_VERIFICATION,
    "cooperative": COOPERATIVE,
    "probing": PROBING,
    "soft_doubt": SOFT_DOUBT,
    "resistance": RESISTANCE,
    "near_fall": NEAR_FALL,
    "fatigue": FATIGUE,
    "exit": EXIT,
    "otp_warnings": OTP_WARNINGS,
    "kyc": KYC_SCENARIOS,
    "refund": REFUND_SCENARIOS,
    "collection": COLLECTION_SCENARIOS,
    "phishing": PHISHING_LINKS,
    "authority": AUTHORITY_SCENARIOS
}

# --- Programmatic augmentation to expand the dataset (keeps file manageable) ---
PERSONA_NAMES = ["Arjun","Ravi","Sita","Priya","Anita","Vikas","Rahul","Asha"]
AMOUNTS = ["₹500","₹1,000","₹2,500","₹5,000","₹10,000"]
COMMON_REASONS = ["refund","verification fee","tax","processing fee","account lock"]
LONG_ADDITIONS = []

for name in PERSONA_NAMES:
    for amt in AMOUNTS:
        for reason in COMMON_REASONS:
            LONG_ADDITIONS.append(f"{name}, we have a pending {reason} of {amt} to be processed. Please provide account/UPI details.")
            LONG_ADDITIONS.append(f"Dear customer, this is an alert regarding {reason}, reference ID {random.randint(10000,99999)}.")
            LONG_ADDITIONS.append(f"{name}, please confirm the account number or UPI ID for {reason} of {amt}.")

# add augmented lines to probing pool and refund scenarios
PROBING = list(dict.fromkeys(PROBING + LONG_ADDITIONS[:200]))
REFUND_SCENARIOS = list(dict.fromkeys(REFUND_SCENARIOS + LONG_ADDITIONS[200:400] if len(LONG_ADDITIONS)>400 else REFUND_SCENARIOS + LONG_ADDITIONS[:200]))

# Add longer dialogues as example templates (used by future persona-driven flows)
LONG_DIALOGUES = [
    [
        "Hi, this is fraud control from the bank, urgent verification required",
        "Who am I speaking with? (sorry, who is this?)",
        "I am Rahul from Fraud Dept., please confirm your name and last 4 digits of account",
        "Why do you need my account details? (this sounds a bit unusual)",
        "This is standard: we need it to release a pending refund",
        "Can you share a formal ticket ID or email for this request? (which bank exactly?)",
    ],
    [
        "Dear customer: transaction of ₹5000 was flagged — confirm immediately",
        "I didn't get any notification though, where did this show up?",
        "We sent an SMS. Please share your UPI to process a refund",
        "I never share OTPs. I'll call the bank's official number if this is real."
    ]
]

# Expose LONG_DIALOGUES for any higher-level strategist or tests

# --- End of dataset ---