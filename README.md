Honeypot decoy chatbot API (Groq-only) for scam engagement.

Quick start (local):
1. python -m pip install -r requirements.txt
2. python main.py
3. Use chat_with_honeypot.py to interact locally.

Endpoints:
- `GET /` health check
- `/honeypot` accepts any method/body shape and returns JSON with:
  - `reply` (string)
  - `session_id` (string)
  - `ended` (bool, optional)

Deploy (Koyeb):
- This repo runs `uvicorn main:app --host 0.0.0.0 --port $PORT` (see `Procfile` / `Dockerfile`).
- Required env vars:
  - `GROQ_API_KEY`
- Optional env vars:
  - `GROQ_BASE_URL` (default `https://api.groq.com/openai/v1`)
  - `LLM_TIMEOUT` (default `8.0`)
  - `MIN_LLM_DELAY_SEC` (default `2.0`) — per-session minimum time between Groq calls (rate-limit safety)
  - `MAX_HISTORY_MESSAGES` (default `12`) — how much conversation history is sent to Groq
  - `MAX_TURNS` (default `80`) — session auto-end safety
  - `DEBUG_ENDPOINTS` (default `0`) — set to `1` to enable `/sessions/*`
  - `HONEYPOT_API_KEY` (optional) — soft-checked via `x-api-key` header (never blocks responses)
  - `LOG_LEVEL` (e.g., `INFO`, `DEBUG`)

LLM constraints:
- Model is fixed to `llama-3.1-8b-instant`.
- One Groq call per incoming message (no fallbacks).
