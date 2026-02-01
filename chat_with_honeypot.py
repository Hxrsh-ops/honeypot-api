import requests
import uuid
import os

# use local default for testing/development
API_URL = os.getenv("HONEYPOT_URL", "http://127.0.0.1:8000/honeypot")
API_KEY = os.getenv("HONEYPOT_API_KEY", "")

session_id = str(uuid.uuid4())

headers = {
    "Content-Type": "application/json",
}
if API_KEY:
    headers["x-api-key"] = API_KEY

print("🔥 Honeypot Chat Started")
print("Type 'exit' to quit\n")

while True:
    msg = input("You: ")
    if msg.lower() == "exit":
        break

    payload = {
        "message": msg,
        "session_id": session_id
    }

    try:
        r = requests.post(API_URL, json=payload, headers=headers, timeout=10)
        try:
            data = r.json()
            print("Bot:", data.get("reply"))
        except Exception:
            print("Bot (non-json):", r.text)
    except Exception as e:
        print("Error:", e)
