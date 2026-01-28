import os
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


app = FastAPI()

API_KEY = os.getenv("HONEYPOT_API_KEY")

class IncomingMessage(BaseModel):
    message: str


@app.get("/")
def root():
    return {"status": "running"}

@app.post("/honeypot")
def honeypot(data: IncomingMessage, x_api_key: str = Header(None)):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    user_msg = data.message.lower()

    # Simple intelligence rules
    if "upi" in user_msg or "pay" in user_msg:
        reply = "I can pay, but my bank app is showing an error. Can you resend the UPI?"
    elif "link" in user_msg:
        reply = "The link is not opening on my phone. Can you explain what I should do?"
    elif "urgent" in user_msg or "immediately" in user_msg:
        reply = "Please wait, I am arranging the money. Don’t cancel it."
    else:
        reply = "Okay, I’m a bit confused. Can you explain again?"

    return {
        "reply": reply
    }
