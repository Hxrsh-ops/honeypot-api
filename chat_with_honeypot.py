import requests
import uuid
import os
import time
import subprocess
import sys
import argparse
from urllib.parse import urlparse

# use local default for testing/development
RAW_API_URL = os.getenv("HONEYPOT_URL", "https://spotless-maggi-hxrsh-ops-36f954ea.koyeb.app/honeypot")
API_KEY = os.getenv("HONEYPOT_API_KEY", "")
AUTOSTART = os.getenv("AUTOSTART_SERVER", "1")  # set to "0" to disable auto-start
BOT_LABEL = os.getenv("HONEYPOT_BOT_LABEL", "Asha")
REQ_TIMEOUT = float(os.getenv("HONEYPOT_TIMEOUT", "30"))

session_id = str(uuid.uuid4())

headers = {
    "Content-Type": "application/json",
}
if API_KEY:
    headers["x-api-key"] = API_KEY

def normalize_api_url(api_url: str) -> str:
    """
    Common footgun: people paste the base domain (/) which returns health JSON,
    so `reply` becomes None. If the URL has no path, assume /honeypot.
    """
    url = (api_url or "").strip()
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc and (parsed.path in ("", "/")):
        return url.rstrip("/") + "/honeypot"
    return url

API_URL = normalize_api_url(RAW_API_URL)
if API_URL != RAW_API_URL:
    print(f"[note] HONEYPOT_URL had no path; using: {API_URL}")

def server_is_up(base_url, timeout=1.0):
    try:
        r = requests.get(base_url, timeout=timeout)
        return r.status_code == 200 or r.status_code < 500
    except Exception:
        return False

def ensure_server(api_url, timeout=10):
    parsed = urlparse(api_url)
    # Don't force a port; HTTPS default is 443, HTTP default is 80.
    port = f":{parsed.port}" if parsed.port else ""
    base = f"{parsed.scheme}://{parsed.hostname}{port}/"
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
        "how are you?",
        "hello, I am ramesh from hit bank",
        "i litrally told you the name and branch in the very first msg",
        "tell me my name and my branch name",
        "you are definetly an bot",
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
        "Your parcel is on hold. Pay re-delivery fee here: http://parcel-fee.example.com",
        "hey its your cousin, stuck and need 2k asap",
        "mom here, phone broken, new number",
        "i am your boss, send me the report and a quick transfer",
        "your card will be blocked, share account number",
        "dont you trust me?",
        "why are you stalling?",
        "send your upi id",
        "upi id is needed or account freezes",
        "this is from head office",
        "bank won't ask otp, right?",
        "job offer: pay 500 to get offer letter",
        "can you help me with a quick loan?",
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
            r = requests.post(API_URL, json=payload, headers=headers, timeout=REQ_TIMEOUT)
            try:
                data = r.json()
                bot = data.get("reply")
                if bot is None:
                    bot = f"[no reply field] {data}"
            except Exception:
                bot = r.text
        except requests.exceptions.Timeout:
            # Retry once; LLM calls can spike.
            try:
                r = requests.post(API_URL, json=payload, headers=headers, timeout=REQ_TIMEOUT * 2)
                data = r.json()
                bot = data.get("reply") or f"[no reply field] {data}"
            except Exception:
                bot = "(no reply - server busy)"
        except requests.exceptions.ConnectionError:
            bot = "(network glitch)"
        except Exception:
            bot = "(error)"
        line = f"You: {msg}\n{BOT_LABEL}: {bot}\n"
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
            r = requests.post(API_URL, json=payload, headers=headers, timeout=REQ_TIMEOUT)
            try:
                data = r.json()
                bot = data.get("reply")
                if bot is None:
                    bot = f"[no reply field] {data}"
                print(f"{BOT_LABEL}:", bot)
            except Exception:
                print(f"{BOT_LABEL} (non-json):", r.text)
        except requests.exceptions.Timeout:
            print(f"{BOT_LABEL}: (no reply - server busy)")
        except requests.exceptions.ConnectionError:
            print(f"{BOT_LABEL}: (network glitch)")
        except Exception:
            print(f"{BOT_LABEL}: (error)")


if __name__ == "__main__":
    main()
