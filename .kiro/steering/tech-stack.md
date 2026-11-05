# tech-stack.md — FrankenLedger tech steering

## Stack (free tiers only, no card anywhere)
- **Frontend:** Next.js (App Router) + Tailwind, deployed on Vercel Hobby.
- **Backend:** Python FastAPI, deployed on Render Free. Fallback chain if
  Render asks for a card: PythonAnywhere free tier, then all-Next.js on
  Vercel alone.
- **Parsing:** deterministic rules first (Python stdlib + openpyxl for .xlsx).
  Keep the parser dependency-light so it can be ported.
- **PDF:** reportlab (server-side). Spreadsheet export: openpyxl.
- **LLM:** Google Gemini free tier (AI Studio) or Groq free tier, key in a
  server-side environment variable only, never in the repo, never in the
  client. No key configured = deterministic mode, labelled on screen.
- **Data:** no accounts, no database of users. Sessions are ephemeral; uploads
  live in memory/temp storage; nothing is retained after the session.

## Rules
- Never add a dependency that needs a card, a paid plan, or a secret in the
  repo.
- Never commit `.env` or any API key. Secrets are checked by the reviewer
  agent and the pre-commit hook rule.
- Python: stdlib first; FastAPI + openpyxl + reportlab + pydantic only.
- Frontend: no paid component, no analytics that phones home with user data.
