import requests
import uuid
import os
import time
import subprocess
import sys
import argparse
from urllib.parse import urlparse

# use local default for testing/development
API_URL = os.getenv("HONEYPOT_URL", "http://web-production-ae3d7.up.railway.app/honeypot")
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

def _built_in_script():
    # mix of scam, legit bank statements, and social impersonation
    return [
        "hi",
        "i am from new bank",
        "your account might get freezed in 2 hours",
        "you didnt tell me anything yet",
        "bank manager from canara bank",
        "send otp now to verify",
        "click this link to secure: http://secure-verify.example.com",
        "why are you adding qn mark all the time",
        "do you remember what i said before?",
        "this is urgent, respond now",
        "Dear customer, a transaction of Rs.500 was debited. If not initiated by you, call 1800-111-111.",
        "Monthly statement is ready. No action needed.",
        "hey its your cousin, stuck and need 2k asap",
        "i am your boss, send me the report and a quick transfer",
        "your card will be blocked, share account number",
        "dont you trust me?",
        "why are you stalling?",
        "send your upi id",
        "upi id is needed or account freezes",
        "this is from head office",
        "bank won't ask otp, right?",
        "ok fine, i'll verify offline",
        "exit",
    ]


def _run_script(messages, delay_sec=10.0, log_path=None):
    if log_path:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"session_id: {session_id}\n")
    for msg in messages:
        payload = {
            "message": msg,
            "session_id": session_id
        }
        try:
            r = requests.post(API_URL, json=payload, headers=headers, timeout=10)
            try:
                data = r.json()
                bot = data.get("reply")
            except Exception:
                bot = r.text
        except Exception as e:
            bot = f"[error] {e}"
        line = f"You: {msg}\nBot: {bot}\n"
        print(line)
        if log_path:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        if msg.strip().lower() == "exit":
            break
        time.sleep(delay_sec)


def main():
    parser = argparse.ArgumentParser(description="Honeypot chat (manual or scripted)")
    parser.add_argument("--auto", action="store_true", help="Run built-in scripted chat")
    parser.add_argument("--delay", type=float, default=10.0, help="Delay seconds between messages")
    parser.add_argument("--log", type=str, default="", help="Optional log file path")
    args = parser.parse_args()

    # ensure base "/" is available before starting chat
    ensure_server(API_URL)

    print("Honeypot Chat Started")
    print("Type 'exit' to quit\n")

    if args.auto:
        msgs = _built_in_script()
        _run_script(msgs, delay_sec=args.delay, log_path=args.log or None)
        return

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


if __name__ == "__main__":
    main()
