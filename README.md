Honeypot AI chatbot for scam intelligence extraction.

Quick start (local):
1. python -m pip install -r requirements.txt
2. python main.py
3. Use chat_with_honeypot.py to interact locally.

Railway deploy:
- The Procfile is configured to run `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- Set env vars in Railway:
  - HONEYPOT_API_KEY (optional) -- API key enforced for endpoints if set
  - OPENAI_API_KEY (optional) -- enable OpenAI primary
  - OPENAI_MODEL (optional) -- default gpt-4
  - ANTHROPIC_API_KEY (optional) -- enable Anthropic fallback
  - ANTHROPIC_MODEL (optional) -- default claude-sonnet-4-20250514
  - ANTHROPIC_VERSION (optional) -- default 2023-06-01
  - USE_LLM (1 to enable LLM usage)
  - LLM_REPHRASE_PROB (0.0-1.0) optional paraphrase softening if replies feel robotic
  - LOG_LEVEL (e.g., INFO/DEBUG)
- Fallback routing: OpenAI first; on error/invalid JSON, Anthropic is tried.
- Push to GitHub and connect the repo to Railway. CI runs tests on PRs.
