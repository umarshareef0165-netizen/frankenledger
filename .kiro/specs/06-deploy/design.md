# Spec 06 — Deploy: design

## Frontend — Vercel Hobby
- `apps/web/` is the Vercel project root. Build: `npm run build`, output:
  Next.js standalone. Env: `NEXT_PUBLIC_API_URL` = deployed backend URL.
- `vercel.json` (if needed) sets the root directory to `apps/web`.

## Backend — Render Free
- `apps/api/` is the Render service root. Build: `pip install -r
  requirements.txt`. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- `render.yaml` in the repo root declares the service (free plan).
- Health check: `GET /api/health`.

## Fallbacks (in order, only if the previous asks for a card)
1. **PythonAnywhere** (free tier, account already exists): WSGI app pointing
   at `apps/api/main.py`; static frontend stays on Vercel.
2. **All-Next.js on Vercel alone**: parser ported to TypeScript (SheetJS for
   .xlsx, jsPDF for PDF, LLM via a Next.js API route). This is a real plan,
   not a hope: the parser is dependency-light by design (see spec 02).

## Repo verification (before submission)
- `git ls-files | grep '^\.kiro/'` is non-empty; `.gitignore` does not mention
  `.kiro`; LICENSE is MIT and detectable; no `.env`, no key files.
- Live URL cold-start test recorded in `BUILD-LOG.md`.
