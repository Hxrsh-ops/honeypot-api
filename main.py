import os
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()

API_KEY = os.getenv("HONEYPOT_API_KEY")

@app.get("/")
def root():
    return {"status": "running"}

@app.post("/honeypot")
def honeypot(x_api_key: str = Header(None)):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")

    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    return {
        "status": "active",
        "message": "Honeypot API is live and secured"
    }
