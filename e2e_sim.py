import requests
import time
import uuid

API_URL = 'http://127.0.0.1:8000/honeypot'
# no API key for local testing
session_id = str(uuid.uuid4())

messages = [
    "URGENT: Your SBI account has been compromised. Your account will be blocked in 2 hours. Share your account number and OTP immediately to verify your identity.",
    "I am Rajesh Kumar, Senior Manager, Fraud Prevention Department, SBI. My extension is 2045. We need the OTP to verify your identity and immediately secure your account before unauthorized transactions occur. Please share the OTP and your account number urgently.",
    "Thank you for your caution. For your reference, my official SBI ID is 1234567890123456 and my direct line is +91-9876543210. For immediate assistance, please provide your account number and OTP now, as your account may be blocked soon.",
    "I understand your concern. I am Rajesh Kumar, Senior Manager, Fraud Prevention Department, SBI, extension 2045. We require the OTP to verify it’s truly you and to stop any fraudulent activity—please share your account number and OTP urgently to prevent automatic account block.",
    "I understand your caution. For your reference, our branch helpline is +91-9876543210 and your official ticket ID is SBI2045-1234. To resolve this quickly and avoid account suspension, please provide your account number and OTP now.",
    "You are speaking with Rajesh Kumar, Employee ID: SBI-FR2045, posted at the SBI Mumbai Main Branch. For verification and to secure your funds, please provide your account number and OTP urgently—this is a time-sensitive security alert."
]

print('Starting E2E conversation; session_id:', session_id)
import subprocess

# helper: try to start uvicorn locally if connection refused
def ensure_local_server(timeout=6):
    try:
        r = requests.get('http://127.0.0.1:8000/', timeout=1)
        return True
    except Exception:
        print('Local server not up: starting uvicorn...')
        # spawn uvicorn in background
        proc = subprocess.Popen(["E:/vs code/honeypot-api/venv/Scripts/python.exe", "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = requests.get('http://127.0.0.1:8000/', timeout=1)
                return True
            except Exception:
                time.sleep(0.3)
        return False

if not ensure_local_server():
    print('Could not start local server; aborting.')
    raise SystemExit(1)

import os
headers = {'Content-Type': 'application/json'}
if os.getenv('HONEYPOT_API_KEY'):
    headers['x-api-key'] = os.getenv('HONEYPOT_API_KEY')

for i, m in enumerate(messages, 1):
    payload = {'session_id': session_id, 'message': m}
    try:
        r = requests.post(API_URL, json=payload, headers=headers, timeout=6)
    except Exception as e:
        print(f'Error posting message {i}:', e)
        raise
    try:
        data = r.json()
    except Exception:
        print('Non-JSON response:', r.status_code, r.text)
        break
    reply = data.get('reply')
    print(f'--- Turn {i} ---')
    print('Scammer:', m)
    print('Bot:', reply)
    time.sleep(0.7)
