import requests
import uuid

API_URL = "https://web-production-df2ff.up.railway.app/honeypot"
API_KEY = "test-key"

session_id = str(uuid.uuid4())

headers = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY
}

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
        data = r.json()
        print("Bot:", data.get("reply"))
    except Exception as e:
        print("Error:", e)
