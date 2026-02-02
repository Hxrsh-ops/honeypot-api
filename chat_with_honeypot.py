import requests
import uuid
import os
import time
import subprocess
import sys
from urllib.parse import urlparse

# use local default for testing/development
API_URL = os.getenv("HONEYPOT_URL", "http://127.0.0.1:8000/honeypot")
API_KEY = os.getenv("HONEYPOT_API_KEY", "")
AUTOSTART = os.getenv("AUTOSTART_SERVER", "1")  # set to "0" to disable auto-start

session_id = str(uuid.uuid4())

headers = {
    "Content-Type": "application/json",
}
if API_KEY:
    headers["x-api-key"] = API_KEY

def server_is_up(base_url, timeout=1.0):
    try:
        r = requests.get(base_url, timeout=timeout)
        return r.status_code == 200 or r.status_code < 500
    except Exception:
        return False

def ensure_server(api_url, timeout=10):
    parsed = urlparse(api_url)
    base = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}/"
    if server_is_up(base):
        return True
    # only auto-start for localhost/127.0.0.1 and when AUTOSTART permitted
    if str(parsed.hostname) in ("127.0.0.1", "localhost") and AUTOSTART != "0":
        print("Local server appears down. Attempting to start uvicorn locally...")
        # Prefer running uvicorn using the current Python executable so venv is respected
        # Check if uvicorn is importable first to give a clear error if not installed
        try:
            import uvicorn  # type: ignore
        except Exception:
            print(f"uvicorn is not available in this Python environment. Install with:\n{sys.executable} -m pip install uvicorn")
            return False
        # spawn uvicorn in background using the venv's python -m uvicorn
        cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", parsed.hostname, "--port", str(parsed.port or 8000)]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # wait until server responds or timeout
        deadline = time.time() + timeout
        while time.time() < deadline:
            if server_is_up(base):
                print("Server started.")
                return True
            time.sleep(0.3)
        print("Timed out waiting for server to start; continue anyway.")
        return server_is_up(base)
    return False

# ensure base "/" is available before starting chat
ensure_server(API_URL)

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
    except requests.exceptions.ConnectionError as e:
        print("Connection error:", e)
        print("Make sure the API is running at", API_URL)
    except Exception as e:
        print("Error:", e)
