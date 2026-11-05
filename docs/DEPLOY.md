# FrankenLedger — Deploy Runbook

**Last updated:** Session 5 (Spec 06 deploy prep)  
**Target:** Free-tier deploy, no card anywhere.  
**Frontend:** Vercel Hobby | **Backend:** Render Free  
**Fallback chain:** Render → PythonAnywhere free → all-Next.js on Vercel

---

## 0. Prerequisites (do these before opening Vercel or Render)

1. The repo must be **public** on GitHub/GitLab.
2. Confirm `/.kiro` is present and committed:
   ```
   git ls-files | grep '^\.kiro/' | head -5
   ```
   Must return results. The `.gitignore` explicitly never ignores `.kiro`.
3. Confirm no secrets are committed:
   ```
   grep -rn "GEMINI_API_KEY\s*=\s*[A-Za-z0-9]" . --include="*.py" --include="*.ts" --include="*.env"
   ```
   Must return nothing. LLM keys go in the Render dashboard (step 2.4), never
   in the repo.
4. Confirm `LICENSE` is MIT and detectable at the repo root:
   ```
   head -3 LICENSE
   ```
   Must contain "MIT License".

---

## 1. Deploy the backend — Render Free

**Trigger to skip this step:** If Render asks for a credit card at *any*
point during sign-up or service creation, STOP immediately, do not enter a
card, and jump to the PythonAnywhere fallback (section 4).

### 1.1 Create the Render web service

1. Go to <https://dashboard.render.com> → **New** → **Web Service**.
2. Connect the GitHub/GitLab repo.
3. Render will auto-detect `render.yaml` at the repo root. Accept the
   detected service `frankenledger-api`.
   - If it does NOT auto-detect, fill in manually:
     - **Name:** `frankenledger-api`
     - **Root directory:** `apps/api`
     - **Runtime:** Python 3
     - **Build command:** `pip install -r requirements.txt`
     - **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Select **Free** plan. If there is no Free option without a card, STOP and
   use the PythonAnywhere fallback (section 4).
5. Click **Create Web Service**.

### 1.2 Confirm the health check

Render will poll `GET /api/health` after deploy. Wait for the service to show
**Live** in the dashboard. Note the URL — it will look like:
```
https://frankenledger-api.onrender.com
```
Record this URL in `README.md` and `BUILD-LOG.md`.

### 1.3 Optional: set LLM keys (deterministic mode works without them)

In the Render dashboard → **Environment** → **Add Environment Variable**:
- `GEMINI_API_KEY` — your Google AI Studio key (never in the repo)
- `GROQ_API_KEY` — your Groq key (never in the repo)

If neither is set, the backend runs in deterministic mode. The frontend mode
badge will read: *"Deterministic mode — parser + rules only, no AI key
configured"*. This is the expected state for the demo video.

---

## 2. Deploy the frontend — Vercel Hobby

### 2.1 Create the Vercel project

1. Go to <https://vercel.com> → **Add New Project** → Import your Git repo.
2. Vercel reads `vercel.json` at the repo root, which sets
   `"rootDirectory": "apps/web"`. Verify that Vercel shows:
   - **Root directory:** `apps/web`
   - **Framework preset:** Next.js (auto-detected)
   - **Build command:** `next build` (or `npm run build` — same thing)
   - **Output directory:** `.next` (auto)
3. **Important:** If Vercel does not pick up `rootDirectory` from
   `vercel.json` automatically (some older CLI versions ignore it for the
   initial import), set it manually in the dashboard:
   Project Settings → **General** → **Root Directory** → type `apps/web`.
   The `vercel.json` file with `"rootDirectory": "apps/web"` is the
   canonical source; the dashboard setting is a fallback override.
4. Select **Hobby** plan (free, no card).

### 2.2 Set the environment variable

In the Vercel project → **Settings** → **Environment Variables**:
- Key: `NEXT_PUBLIC_API_URL`
- Value: `https://frankenledger-api.onrender.com` (the URL from step 1.2)
- Environment: Production + Preview + Development

Click **Save**. Then **Redeploy** so the new env var takes effect.

### 2.3 Verify the deploy

The Vercel build runs `npm run build`. It should succeed (4 routes:
`/`, `/dashboard`, `/flags`, `/_not-found`). Once live:
1. Open the Vercel URL — the monster-lab upload page must load with no login.
2. Click **Load fictional sample** — should call the Render backend and
   succeed (first call may be slow due to cold start — see section 3).
3. Proceed through the full demo flow to verify end to end.

Record the Vercel live URL in `README.md` and `BUILD-LOG.md`.

---

## 3. Cold-start behaviour (Render Free)

Render Free services **spin down after 15 minutes of inactivity**. The first
request after a sleep period can take **30–60 seconds** while the container
restarts.

### Current frontend behaviour (honest assessment)

The upload page (`app/page.tsx`) handles a slow backend **partially**:

- The `agentStatus()` call on mount is **fire-and-forget** — if the backend
  is sleeping, it will simply show no mode badge until the backend responds.
  This is graceful: the UI never shows an error for this call.
- The sample button shows a **"Loading fictional sample data…" spinner** with
  `aria-busy` while `uploadSample()` is in flight. If the backend takes 45
  seconds to wake up, the spinner will keep showing — no error is thrown until
  the fetch itself errors or times out (browser default: no timeout).
- If the backend does time out (browser or network enforced), the global error
  state shows: *"Could not load sample data. Is the backend running?"*

**What is missing:** There is no explicit "waking up the server — this may
take up to 60 seconds on the first request" message. The spinner alone is
ambiguous to a judge. **Recommended fix before the demo:** add a timed
message to the sample button — after 5 seconds of waiting, change the spinner
label to *"Waking up the server… (Render Free cold start, ~30s)"*. This is
a small UI change to `app/page.tsx` that does not affect the build.

Until that fix is applied, tell judges verbally (or in the submission text)
that the first sample load may take up to 60 seconds on Render Free.

---

## 4. Fallback chain

Work through this list in order. Move to the next fallback **only** if the
current platform asks for a card at any point.

### Fallback 1 (primary): Render Free

- Trigger to abandon: Render asks for a credit card during sign-up or service
  creation.
- Action: Close without entering a card. Log "Render asked for card —
  switching to PythonAnywhere" in `BUILD-LOG.md`.

### Fallback 2: PythonAnywhere free tier

PythonAnywhere offers a free tier with Python 3.12, WSGI hosting, and no card.

1. Create a free account at <https://www.pythonanywhere.com>.
2. Open a **Bash console** and clone/upload the repo.
3. Create a virtualenv:
   ```
   mkvirtualenv frankenledger --python=python3.12
   pip install -r apps/api/requirements.txt
   ```
4. In the **Web** tab → **Add a new web app** → Manual configuration →
   Python 3.12.
5. Set the WSGI file to point at `apps/api/main.py`:
   ```python
   import sys
   sys.path.insert(0, '/home/<username>/frankenledger/apps/api')
   from main import app as application
   ```
   (PythonAnywhere uses WSGI; uvicorn is not needed here.)
6. The free URL will be `https://<username>.pythonanywhere.com`.
7. Update `NEXT_PUBLIC_API_URL` in Vercel to this URL; redeploy.
8. Note: PythonAnywhere free tier has outbound network restrictions — the LLM
   calls (Gemini/Groq) will likely be blocked. The backend will run in
   deterministic mode. This is acceptable; label it in the submission.

### Fallback 3: All-Next.js on Vercel alone

Use this only if both Render and PythonAnywhere ask for a card.

The parser is dependency-light by design (stdlib + openpyxl logic only). Port
the backend logic to Next.js API routes in `apps/web/app/api/`:

- `POST /api/upload/sample` → read the sample files from `public/`
- `POST /api/parse` → TypeScript port of `parser.py` (regex + string ops)
- `POST /api/reconcile` → TypeScript port of `reconciler.py`
- `POST /api/export/pdf` → `jsPDF` (browser-side or server-side)
- `POST /api/export/xlsx` → `SheetJS` (`xlsx` package)

LLM calls go through Next.js API routes (server-side only — key never in the
client). PDF generation uses `@react-pdf/renderer` or `jsPDF`.

This is the most work but the most robust fallback. It keeps everything on
Vercel Hobby (free, no card).

---

## 5. Wiring NEXT_PUBLIC_API_URL

| Backend platform | Value to set in Vercel env var |
|---|---|
| Render Free | `https://frankenledger-api.onrender.com` |
| PythonAnywhere | `https://<username>.pythonanywhere.com` |
| All-Next.js (Vercel) | Delete the var entirely — API routes are on the same origin |

After changing the env var, always **Redeploy** in Vercel (Deployments →
⋮ → Redeploy). The variable is baked in at build time for the `NEXT_PUBLIC_`
prefix.

---

## 6. Repo-verification checklist

Run these before submitting the Devpost entry:

```bash
# 1. .kiro is committed
git ls-files | grep '^\.kiro/' | wc -l
# Expected: > 0

# 2. .kiro is NOT in .gitignore
grep -n "kiro" .gitignore
# Expected: line 2 comment saying .kiro is NEVER ignored, no actual ignore rule

# 3. No .env or key files committed
git ls-files | grep -E "\.env|\.secret|apikey"
# Expected: empty

# 4. No live key values in source
grep -rn "AIza[A-Za-z0-9_-]\{20\}" . --include="*.py" --include="*.ts"
grep -rn "gsk_[A-Za-z0-9]\{20\}" . --include="*.py" --include="*.ts"
# Expected: empty

# 5. MIT license detectable
head -1 LICENSE
# Expected: "MIT License"

# 6. Repo is public (check in GitHub/GitLab UI — cannot verify from CLI)

# 7. Live URL loads without login (check in browser)
curl -s -o /dev/null -w "%{http_code}" https://<vercel-url>/
# Expected: 200
```

Results of on-disk checks completed in Session 5:
- `.kiro` in `.gitignore`: **NOT mentioned** (only a comment on line 2 saying
  it is never ignored). ✅
- `.env` files in repo: **none found**. ✅
- Secret values in source: **none found** — only variable-name strings like
  `"GEMINI_API_KEY"` in comments, docstrings, and tests (which use
  `monkeypatch.setenv` with fake values). ✅

---

## 7. Local development (for reference)

```bash
# Backend
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd apps/web
npm install
# Create .env.local (this file is gitignored):
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
# Open http://localhost:3000
```

Optional LLM keys for local dev (add to `.env.local`, never commit):
```
GEMINI_API_KEY=your_key_here
# or
GROQ_API_KEY=your_key_here
```
Without either key the backend runs in deterministic mode (labelled on screen).

---

## 8. Post-deploy smoke test

Once both services are live:

1. Open the Vercel URL. Should load `/` with no login.
2. Check the mode badge — should read "Deterministic mode — parser + rules
   only, no AI key configured" (unless an LLM key was set in Render).
3. Click **Load fictional sample — Noor General Store**. Wait up to 60s for
   the first cold-start. The "Fictional sample data — Noor General Store"
   banner must appear.
4. Confirm mapping → dashboard loads with 8 ledger rows, 10 flags,
   totals sold=Rs 4,020 / received=Rs 1,420 / outstanding=Rs 2,600.
5. Accept or dismiss one flag → totals recompute.
6. Click **Download daily PDF** → a real PDF downloads.
7. Click **Download clean XLSX** → a real .xlsx downloads with 2 sheets.
8. Navigate to `/flags` → all 10 flags show with evidence chips.
9. Generate a draft reply → copy to clipboard → paste works.
10. Record all results in `BUILD-LOG.md` under "Session 6: live deploy".
