# BUILD-LOG.md — FrankenLedger honest build diary

Started 2026-11-05. Updated after every build session. Nothing here is a
submission; the Devpost submission happens only with the entrant's separate
final approval.

## 2026-11-05 — Session 0: login + scaffold

- Verified `kiro-cli whoami`: "Logged in with Google, Email:
  umarshareef0165@gmail.com", kiro-cli 3.0.0.
- Scaffold created: LICENSE (MIT), README, `.gitignore` (does NOT ignore
  `.kiro`), `KIRO-USAGE.md`, `.kiro/` (6 specs, 4 steering files, 3 agents,
  hooks note), `apps/web/` (Next.js), `apps/api/` (FastAPI), `samples/`
  (fictional data), `tests/`, `docs/` (demo script + submission draft).
- Environment: Node v24.22.1, npm 10.9.4, Python 3.12.3, openpyxl 3.1.2
  present. fastapi / reportlab / pydantic NOT installed — backend venv + pip
  install still to do.
- Not yet built: parser, reconciler, FastAPI app, Next.js UI, PDF export,
  LLM agent layer, deploy, demo video, submission.

## Sessions (append as they run)

<!-- Each Kiro chat session: date, spec, what was built, test results, what is still missing. -->

## 2026-11-05 — Session 1: Spec 01 (file ingest) + Spec 02 (deterministic parser)

### What was built

**`apps/api/frankenledger/`** (new package):
- `__init__.py` — package marker
- `models.py` — `CandidateOrder`, `PaymentStatus`, `Confidence`, `ChatFile`,
  `LedgerFile`, `LedgerRow` dataclasses
- `parser.py` — deterministic WhatsApp chat parser: stdlib only (re, datetime).
  Line splitter (DD/MM/YYYY + MM/DD/YYYY, 24h/12h); quantity extraction
  incl. Roman-Urdu number words (ek/do/teen/chaar/paanch) and units
  (kg/kilo/darjan/packet/litre); amount extraction (Rs/rupy//-/bare-number);
  payment markers (paid/de diya/paise de diye/udhaar/kal/rehta hai/baaki);
  item catalogue (cheeni/atta/chawal/doodh/anda/chai/ghee/daal/namak/sabun)
  with item_raw fallback; media/voice lines counted as needs_listening;
  every CandidateOrder carries source_line and confidence (high/medium/low).
- `ledger_io.py` — reads .xlsx (openpyxl) and .csv; header detection with
  synonym mapping; filters trailing empty rows; suggests column mapping;
  apply_mapping converts rows to LedgerRow.

**`apps/api/main.py`** — FastAPI app:
- `GET /api/health`
- `POST /api/upload/chat`
- `POST /api/upload/ledger`
- `POST /api/upload/sample` (fictional data, labelled)
- `POST /api/upload/confirm-mapping`
- `POST /api/parse`

**`apps/api/requirements.txt`** — pinned versions:
  fastapi==0.162.0, uvicorn==0.54.0, openpyxl==3.1.5, pydantic==2.14.3,
  reportlab==5.1.0, pytest==9.2.0, httpx==0.28.1, python-multipart==0.0.33

**`samples/sample-ledger.xlsx`** — 8 fictional rows (Ahmed/Sana/Bilal/Fatima/Usman),
  designed to exercise the reconciler. README sheet labels it fictional.
  Columns: Date | Customer | Item | Quantity | Amount (Rs) | Paid.

**`tests/test_parser.py`** — 71 assertions across 8 test classes + the labelled
  sample set. Honest report printed: 14/14 expected orders extracted from
  the fictional sample chat (0 missed, 1 extra payment-confirmation line).
  No accuracy percentage claimed beyond this sample set.

**`tests/test_ingest.py`** — 21 endpoint tests covering: wrong extension, empty
  file, unreadable file, missing columns, voice-note counting, 12-hour dates,
  sample endpoint, confirm-mapping, parse end-to-end.

**`apps/api/conftest.py`** + **`apps/api/pytest.ini`** — pytest path config.

**`create_sample_ledger.py`** — one-shot script to regenerate the sample ledger.

### Test results
```
92 passed, 0 failed, 1 warning (starlette TestClient deprecation — cosmetic only)
```
Honest sample report (labelled set, fictional data):
  Expected: 14 | Extracted: 15 | Correct: 14 | Missed: 0 | Extra: 1

### Still missing (not in Spec 01/02 scope)
- Frontend (Next.js upload screen, drop zones, column-mapping UI) — Spec 01
- Reconciler (PAID_NOT_RECORDED / RECORDED_NOT_PAID / PRICE_MISMATCH flags) — Spec 03
- Dashboard + totals — Spec 05
- Draft WhatsApp reply generator — Spec 04/05
- PDF daily ledger export (reportlab) — Spec 05
- Clean spreadsheet export (openpyxl) — Spec 05
- LLM agent layer (Gemini/Groq, labelled "LLM mode") — Spec 04
- Demo-flow smoke test (end-to-end with sample data in one click) — Spec 01
- Vercel + Render deployment — Spec 06

## 2026-11-05 — Session 2: Spec 03 (reconciliation) — all tasks complete

### What was done

Four tasks completed in this session:

**1. PARSER FIX (Spec 02 defect)**
- `apps/api/frankenledger/parser.py`: added a shop-sender skip in `parse_chat`.
  Lines whose sender contains `'store'` or `'shop'` (case-insensitive) are
  counted as parsed lines but never emit a `CandidateOrder`. Fixes the false
  order generated from the Noor General Store reply line on L7 of the sample
  chat ("Walaikum salam Ahmed bhai, bhej di, Rs 500").
- `tests/test_parser.py`: added `TestShopSenderSkip` (6 tests) and hardened
  `test_honest_sample_report` from a soft assertion (≥7/14) to a hard
  assertion (==14/14 correct, 0 missed, 0 extra).
- Honest sample report after fix:
  **Expected 14 | Extracted 14 | Correct 14 | Missed 0 | Extra 0**

**2. RECONCILE ENDPOINT FIX (integration gap)**
- `apps/api/main.py`: `POST /api/reconcile` now works in two modes:
  - **Session-driven** (new, preferred): empty/omitted body → re-parses
    `chat_text` from session, re-reads ALL ledger rows from `ledger_bytes`
    server-side using confirmed mapping (or suggested mapping as fallback),
    then reconciles. Returns 400 with a clear message if no chat or no ledger
    is in session.
  - **Explicit** (forward-compat): if body contains non-empty `orders` +
    `ledger_rows`, those are used directly as before.
- `ReconcileRequest` fields `orders` and `ledger_rows` changed from required
  `list[dict]` to optional (defaulting to `[]`).
- New helper `_read_all_ledger_rows()` handles both .xlsx and .csv
  re-reading inline.

**3. apply_fix() DEFAULT PATCH**
- `apps/api/frankenledger/reconciler.py`: `apply_fix()` parameter changed
  from `patch: Optional[dict]` (required) to `patch: Optional[dict] = None`
  (optional with default). Callers no longer need to pass `None` explicitly.
- Also fixed a bug in the `edit` action: when `action == "edit"` and a patch
  is provided, `apply_fix` now returns immediately after applying the patch,
  preventing the default per-kind handler from overwriting the user's custom
  values (e.g., PRICE_MISMATCH default was overwriting the patched amount
  with the chat order amount).

**4. TESTS (tests/test_reconciler.py, new file)**
- 76 new tests across 9 test classes:
  - `TestNormaliseName` / `TestNormaliseItem`: normalisation helpers
  - `TestMatcher`: edge cases — name variants ('Ahmed bhai'), ±1 day, Rs 10
    boundary (within/exactly/+1 outside), one-to-one priority, duplicates
  - `TestPaymentEvents`: Bilal's 450 payment marks atta paid; payment event
    is never a standalone flag; wrong-amount event does not match
  - `TestFlagKindsOnSampleSet`: one test per flag kind + count assertions
  - `TestTotalsOnSampleSet`: sold/received/outstanding exact values
  - `TestOriginalNotMutated`: reconcile() and apply_fix() never mutate input
  - `TestFixActions`: accept/edit/dismiss for each flag kind + totals recompute
  - `TestSessionDrivenReconcileEndpoint`: 400 on missing session, session-driven
    reconcile returns 10 flags with correct totals, fix accept updates totals
  - `TestDemoSmokeTest`: full demo flow (upload sample → reconcile → list flags
    → accept PRICE_MISMATCH → totals update to 3970)

### Honest flag list on the full sample set (post parser fix)

10 flags total — measured on the fictional Noor General Store sample set only.
No accuracy percentage claimed beyond this labelled set.

| # | Kind                | Evidence                                               |
|---|---------------------|--------------------------------------------------------|
| 1 | PAID_NOT_RECORDED   | Usman anda Rs 600 (chat L12) — no ledger row           |
| 2 | PAID_NOT_RECORDED   | Ahmed ghee Rs 850 (chat L19) — no ledger row           |
| 3 | UNMATCHED_ORDER     | Ahmed cheeni Rs 500 2nd order (chat L14) — no row      |
| 4 | UNMATCHED_ORDER     | Sana doodh Rs 220 restatement (chat L16) — no row      |
| 5 | UNMATCHED_ORDER     | Sana cheeni Rs 250 (chat L22) — no row                 |
| 6 | UNMATCHED_ORDER     | Ahmed atta Rs 300 (chat L24) — no row                  |
| 7 | RECORDED_NOT_PAID   | Sana doodh ledger row 2 (paid=Yes) — chat shows udhaar |
| 8 | RECORDED_NOT_PAID   | Fatima chawal ledger row 7 (paid=Yes) — no chat order  |
| 9 | PRICE_MISMATCH      | Ahmed cheeni chat Rs 500 vs ledger row 1 Rs 550        |
| 10| DUPLICATE           | Bilal atta ledger rows 3+4 — same customer/item/date   |

Totals (fictional sample set, no real shop):
- sold = Rs 4020 | received = Rs 1420 | outstanding = Rs 2600

### Test results

```
168 passed, 0 failed, 2 warnings (starlette + pytest class-fixture deprecations — cosmetic)
```
Previous: 92 passed. New tests added: 76. All 92 prior tests still pass.

### Files changed
- `apps/api/frankenledger/parser.py` — shop-sender skip
- `apps/api/frankenledger/reconciler.py` — apply_fix default patch; edit
  action returns early (patch not overwritten by default handler)
- `apps/api/main.py` — session-driven POST /api/reconcile; ReconcileRequest
  fields optional; new helper _read_all_ledger_rows()
- `tests/test_parser.py` — TestShopSenderSkip (6 tests); hardened
  test_honest_sample_report
- `tests/test_reconciler.py` — new file, 76 tests
- `.kiro/specs/03-reconciliation/tasks.md` — all 7 items checked off

### Still missing
- Frontend (Next.js upload screen, column-mapping UI, flag review, totals
  dashboard) — Specs 01/05
- Draft WhatsApp reply generator (frontend copy button) — Spec 04/05
- PDF daily ledger export (reportlab) — Spec 05
- Clean spreadsheet export (openpyxl) — Spec 05
- LLM agent layer (Gemini/Groq, labelled "LLM mode") — Spec 04
- Vercel + Render deployment — Spec 06
- Demo video (screen recording of real app, public on YouTube, under 3:00)

## 2026-11-05 — Session 3: Spec 04 (agent layer) — all tasks complete

### What was built

**`apps/api/frankenledger/agent.py`** (new file):
- Mode detection: reads `GEMINI_API_KEY` or `GROQ_API_KEY` from env only.
  Returns `{mode: "llm", provider: "gemini"|"groq"}` or
  `{mode: "deterministic"}`. Key value is never logged, never returned.
- LLM client (urllib, no SDK): `_call_gemini()` uses Gemini AI Studio
  generateContent REST endpoint; `_call_groq()` uses Groq OpenAI-compatible
  chat completions with `llama-3.1-8b-instant`. Both have a 20s timeout.
- JSON-only prompts: one prompt template per job (explain, draft_reply,
  structure). Strict JSON-only response format requested.
- Response validation: parses JSON, checks expected key and type.
  Invalid JSON / empty result / missing key → deterministic fallback, logged
  at WARNING with the error reason (never the key).
- Error fallback chain: timeout / network error / rate-limit / any exception
  → deterministic fallback; `agent_note` in response says
  "Deterministic mode — agent unavailable right now."
- Three public jobs: `explain(flag)`, `draft_reply(order)`,
  `structure(candidate_orders)`. Each returns `{..., source: "llm"|"template"|"deterministic"}`.
- Agent output is always a suggestion; it never mutates the ledger.
- No fine-tuning done or claimed.

**`apps/api/frankenledger/draft.py`** (new file):
- `explain_flag(flag: dict) -> str`: evidence-linked template explanations
  for all five flag kinds (PAID_NOT_RECORDED, UNMATCHED_ORDER,
  RECORDED_NOT_PAID, PRICE_MISMATCH, DUPLICATE). Each cites the chat line
  number and/or ledger row number from the flag's evidence. Falls back to
  the reconciler's pre-computed explanation for unknown kinds.
- `draft_reply(order: dict) -> str`: deterministic Roman Urdu/English mix
  reply template. Greeting, reminder body, and closing are selected
  deterministically (hash of sender/item) from small variant pools.
  Strips Urdu honorifics (bhai/sahab/ji etc.) from the greeting name.
  Example: "Salam Ahmed bhai, cheeni ka Rs 500 rehta hai, kal de dena.
  Shukriya."

**`apps/api/main.py`** — four new endpoints:
- `GET /api/agent/status` → `{mode, label, provider?}`. Label says
  "Deterministic mode — parser + rules only, no AI key configured" when
  no key is set.
- `POST /api/agent/explain` `{flag}` → `{explanation, source, agent_note?}`
- `POST /api/agent/draft-reply` `{order}` → `{draft, source, agent_note?}`
- `POST /api/agent/structure` `{candidate_orders}` → `{orders, source, agent_note?}`

**`tests/test_agent.py`** (new file, 67 tests across 10 test classes):
- `TestAgentStatus` — mode=deterministic, label present, no key in response
- `TestAgentExplain` — source=template, explanation links to evidence, all
  five flag kinds, no key in response
- `TestAgentDraftReply` — source=template, draft contains name/amount/item,
  Roman Urdu words present, graceful handling of None fields
- `TestAgentStructure` — source=deterministic, orders returned unchanged,
  empty list handled
- `TestInvalidLLMFallback` — bad JSON / empty fields / missing keys / wrong
  types / network errors → fallback confirmed for all three jobs;
  `agent_note` present in fallback response
- `TestKeySafety` — fake key never appears in status/explain/draft/structure
  responses; fake key never appears in log output
- `TestExplainFlagTemplates` — all five flag kinds + unknown kind + no
  chat_order
- `TestDraftReplyTemplates` — various order shapes including None fields;
  determinism (same input → same output)
- `TestGetMode` — reflects env-var state; empty string treated as unset;
  Gemini takes precedence over Groq
- `TestDemoFlowDeterministic` — full demo flow: upload sample → parse →
  reconcile → agent/status → explain flag → draft reply → structure orders

**BUILD-LOG.md** — documentation corrections:
- Session 1 "Still missing" list: corrected spec numbers (Spec 07 → Spec 04,
  Spec 08 → Spec 06, dashboard → Spec 05, draft reply → Spec 04/05,
  PDF/spreadsheet → Spec 05).
- Session 2 "Still missing" list: corrected spec numbers (Spec 07 → Spec 04,
  Spec 08 → Spec 06, dashboard → Spec 05, draft reply → Spec 04/05,
  PDF/spreadsheet → Spec 05). Total spec count is 6 (01–06), not 8.

### Test results

```
235 passed, 0 failed, 2 warnings (starlette + pytest class-fixture deprecations — cosmetic)
```
Previous: 168 passed. New tests added: 67. All 168 prior tests still pass.

Honest agent behaviour report (fictional Noor General Store sample set):
  - No LLM key configured in this environment → deterministic mode throughout.
  - All four agent endpoints return HTTP 200 with source = "template" or
    "deterministic".
  - Fallback tested with 11 simulated LLM failure scenarios — all fell back
    correctly with `agent_note` in response.
  - Key-safety tested: fake key value confirmed absent from all responses and
    log output across 5 tests.
  - No accuracy percentage claimed; no real users; no fine-tuning.

### Files changed
- `apps/api/frankenledger/agent.py` — new (LLM client + deterministic fallbacks)
- `apps/api/frankenledger/draft.py` — new (explain/draft templates)
- `apps/api/main.py` — 4 new agent endpoints + `_agent` import
- `tests/test_agent.py` — new (67 tests)
- `BUILD-LOG.md` — spec number corrections (Sessions 1 + 2) + this entry
- `.kiro/specs/04-agent-layer/tasks.md` — all items checked off

### Still missing
- Frontend (Next.js upload screen, column-mapping UI, flag review, totals
  dashboard, copy-to-clipboard for draft reply) — Specs 01/05
- PDF daily ledger export (reportlab) — Spec 05
- Clean spreadsheet export (openpyxl) — Spec 05
- Vercel + Render deployment — Spec 06
- Demo video (screen recording of real app, public on YouTube, under 3:00)

## 2026-11-05 — Session 4a: Spec 05 backend exports

### What was built

**`apps/api/frankenledger/ledger_export.py`** (new file, 17 KB):
- `build_pdf(payload: dict) -> bytes` — renders a daily A4 paper ledger using
  reportlab (already in requirements.txt). Layout: header with shop name
  ("Noor General Store (sample)"), date, totals box (sold / received /
  outstanding, outstanding in red), udhaar table (unpaid rows: customer, item,
  amount, date), full reconciled ledger table, dismissed-flags section, footer
  "Built with Kiro — FrankenLedger, Kiroween 2026". `pageCompression=0` keeps
  content streams uncompressed so text is grep-able (no new dependency).
  Handles empty input (zero rows → valid PDF with zeroed totals, not a crash).
- `build_xlsx(payload: dict) -> bytes` — produces a clean .xlsx workbook using
  openpyxl (already in requirements.txt) with exactly two sheets:
  - **Ledger**: Row #, Date, Customer, Item, Quantity, Amount (Rs), Paid.
  - **Flags**: Flag ID, Kind, Explanation, Status (open/fixed/dismissed),
    Chat Line, Ledger Row(s).
  Styled with dark header row, alternating row fill, frozen header, column
  widths. Handles empty input (headers-only sheets, not a crash).
  The original uploaded file is never touched.

**`apps/api/main.py`** — three changes:
- Docstring updated to list Spec 05 endpoints.
- `from fastapi.responses import Response` added (line 30).
- `from frankenledger.ledger_export import build_pdf, build_xlsx as _build_xlsx`
  added (line 39).
- `GET /api/health` extended: now returns `{ok: true, status: "ok",
  mode: "llm"|"deterministic", service, version}`. Existing callers that only
  read `status` are unaffected; `mode` mirrors `/api/agent/status`.
- `POST /api/export/pdf` (lines 711–758): accepts
  `{reconciled, totals, date, flags, shop_name}` (all optional), calls
  `build_pdf`, returns `application/pdf` with
  `Content-Disposition: attachment; filename="frankenledger-YYYY-MM-DD.pdf"`.
- `POST /api/export/xlsx` (lines 760–796): accepts `{reconciled, flags}`
  (all optional), calls `build_xlsx`, returns the correct xlsx MIME type with
  `Content-Disposition: attachment; filename="frankenledger-ledger.xlsx"`.

**`tests/test_export.py`** (new file, 34 tests across 6 test classes):
- `TestExportPdf` (7 tests): 200, application/pdf, `%PDF-` header, ≥1 KB,
  totals values appear in uncompressed PDF text, date in filename, customer
  names in PDF text.
- `TestExportPdfEmpty` (4 tests): empty body → 200, valid `%PDF-`, ≥512 B,
  zero-totals does not crash.
- `TestExportXlsx` (9 tests): 200, xlsx MIME type, filename in header, opens
  with openpyxl, exactly 2 sheets named Ledger + Flags, correct data-row
  counts, header row contents, round-trip data values (customer = "Ahmed",
  amount = 550.0), flag status values ("open" / "dismissed"), flag kind values.
- `TestExportXlsxEmpty` (5 tests): empty body → 200, valid xlsx, 2 sheets,
  header-only Ledger sheet, header-only Flags sheet.
- `TestExportSecretSafety` (3 tests): fake GEMINI_API_KEY and GROQ_API_KEY
  never appear in PDF bytes, xlsx bytes, or response headers.
- `TestDemoSmokeExport` (2 tests): full end-to-end pipeline — POST
  /api/upload/sample → POST /api/reconcile (session-driven) → POST
  /api/export/pdf → POST /api/export/xlsx. Asserts: 8 reconciled rows, 10
  flags, totals sold=4020/received=1420/outstanding=2600; PDF is valid and
  contains "4020" and "2600"; xlsx has 2 sheets with correct row counts and
  correct customer names. Also asserts GET /api/health returns
  `{ok: true, mode: "deterministic"}`.

### Bug fixed during this session
- PDF content streams were FlateDecode-compressed by ReportLab's default
  (`pageCompression=1`), making text invisible to raw-byte search. Fixed by
  setting `pageCompression=0` in `SimpleDocTemplate` — no new dependency,
  same output quality for a daily ledger, text now grep-able for tests and
  logging.

### Test results
```
269 passed, 0 failed, 2 warnings
(starlette + pytest class-fixture deprecations — cosmetic, no action needed)
```
Previous total: 235 passed. New tests added: 34. All 235 prior tests still pass.

Honest data note: all sample data is fictional. "Noor General Store" and all
customers (Ahmed, Sana, Bilal, Fatima, Usman) do not exist. No real users, no
real shop, no accuracy percentage claimed beyond the labelled sample set.

### Files changed
- `apps/api/frankenledger/ledger_export.py` — new (PDF + xlsx builders;
  `pageCompression=0` fix)
- `apps/api/main.py` — extended health endpoint; added `Response` import and
  `ledger_export` import; added `POST /api/export/pdf` and
  `POST /api/export/xlsx` routes
- `tests/test_export.py` — new (34 tests)
- `.kiro/specs/05-dashboard-pdf/tasks.md` — checked off PDF endpoint, xlsx
  endpoint, demo-flow smoke test (frontend items left unchecked)
- `BUILD-LOG.md` — this entry

### Tasks checked off (Spec 05 backend only)
- [x] `POST /api/export/pdf` (reportlab daily ledger, A4-printable)
- [x] `POST /api/export/xlsx` (Ledger + Flags sheets)
- [x] Demo-flow smoke test: sample data → reconcile → PDF → xlsx

### Still missing (frontend — next session)
- Next.js app scaffold (App Router + Tailwind), pages `/` and `/dashboard`
- Upload screen (monster-lab): two drop zones + sample-data button
- Mapping confirmation step
- Dashboard: ledger table, totals bar, flag list, search box
- Flag cards: evidence (chat line + ledger row), accept/edit/dismiss
- Draft reply with copy-to-clipboard
- Phone layout check (single column, big tap targets)
- Vercel + Render deployment — Spec 06
- Demo video (screen recording of real app, public on YouTube, under 3:00)

## 2026-11-05 — Session 4b: Spec 05 frontend

### What was built

**`apps/web/lib/api.ts`** — typed API client for the FastAPI backend (new file):
- Base URL from `NEXT_PUBLIC_API_URL` env var, default `http://localhost:8000`.
- 11 functions: `health`, `uploadChat`, `uploadLedger`, `uploadSample`,
  `confirmMapping`, `parse`, `reconcile`, `reconcileFix`, `agentStatus`,
  `agentExplain`, `agentDraftReply`, `exportPdf`, `exportXlsx`.
- Exported types mirroring all FastAPI response shapes (`ChatSummary`,
  `LedgerSummary`, `SampleResponse`, `Flag`, `LedgerRow`, `Totals`,
  `AgentStatus`, `CandidateOrder`, etc.).
- Custom `ApiError` class with `status` + `detail`; callers can `instanceof`-check.
- No credentials, no API key, no secret anywhere.

**`apps/web/app/page.tsx`** — upload / monster-lab screen (replaced stock scaffold):
- `"use client"` component; state machine: `idle → uploading → mapping →
  reconciling → /dashboard`.
- `ModeBadge`: fires `agentStatus()` on mount; deterministic mode renders
  "Deterministic mode — parser + rules only, no AI key configured"; gracefully
  silent if backend is not running.
- Four body-part stitch display: 🧠 WhatsApp Chat Export / 💀 Excel Ledger /
  ⚡ LLM Agent / 📄 Printable PDF — always visible in upload step, with 🪡
  animated stitch needle between parts.
- Two `UploadZone` components (drag-and-drop + click-to-browse):
  - Chat zone: `.txt` only, wired to `uploadChat()`.
  - Ledger zone: `.xlsx`/`.csv` only, wired to `uploadLedger()`.
  Both show loading spinner, success state (with line/row counts), and inline
  error messages.
- Sample button: `uploadSample()` in one click, creates synthetic `File` stubs
  so the zones show as "ready", sets `isSample = true`, auto-advances to
  mapping step.
- `SampleBanner`: appears whenever `isSample` is true — "Fictional sample data
  — Noor General Store. All customers, items, and amounts are invented."
- `MappingConfirm`: selects pre-filled from `suggested_mapping`, 5-row preview
  table, confirm button → `confirmMapping()` → `reconcile()` → store results
  in `sessionStorage` → `router.push('/dashboard')`.
- Progress indicator shows current step inline.

**`apps/web/app/dashboard/page.tsx`** — dashboard:
- `"use client"` component; reads `fl_*` keys from `sessionStorage` on mount.
  If missing → `EmptyState` with "upload files first" message and link to `/`.
- `SampleBanner`, `ModeBadge` (from stored `fl_mode`).
- `TotalsBar`: three cards — Total Sold, Received, Outstanding Udhaar; large
  numerals with colour coding (red for outstanding).
- `LedgerTable`: reconciled rows with highlight animation (`evidence-highlight`
  CSS class); filtered by search query; `scrollIntoView` on evidence click.
- Search box: filters both the ledger table and the flag list by customer/item.
- Flag list: `FlagCard` × N; each card is expand/collapse; evidence chips
  (💬 chat line, 📊 ledger row) with `scrollIntoView + highlight` on click;
  accept / edit (with amount + paid inputs) / dismiss buttons wired to
  `reconcileFix()` with totals recomputing after each fix.
- `DraftReply` inside each flag card (for flags with an unpaid chat order):
  "Generate draft reply" button → `agentDraftReply()` → shows draft text →
  "📋 Copy to clipboard" button (Clipboard API with `execCommand` fallback).
- Export bar: "Download daily PDF" → `exportPdf()` + `triggerDownload`;
  "Download clean XLSX" → `exportXlsx()` + `triggerDownload`.
- All session updates (after each fix) written back to `sessionStorage`.

**`apps/web/app/flags/page.tsx`** — flag detail page (new):
- `"use client"` component; same `fl_*` sessionStorage reader, same empty
  state.
- Shows all flags, one per `FlagDetail` card (dismissed flags shown greyed
  out/struck-through).
- Each `FlagDetail`:
  - Kind badge + full explanation.
  - Evidence chips (💬 chat line, 📊 ledger row) scroll to and highlight the
    corresponding inline evidence panel on click.
  - Inline **Chat order detail** panel (`dl` with date / sender / item / qty /
    amount / status / confidence) — highlighted by `evidence-highlight` class
    when the chat-line chip is clicked.
  - Inline **Ledger rows table** — rows highlighted when the ledger-row chip is
    clicked; uses `scrollIntoView`.
  - Edit form (amount + paid dropdowns).
  - Accept / Edit / Dismiss buttons, all wired to `reconcileFix()` with totals
    recomputing after each fix; session written back.
  - `DraftReply` section (same as dashboard: generate → copy-to-clipboard).
- Compact `TotalsBar` at top recomputes live as flags are fixed.
- Back link → `/dashboard`.

### Session state note (deviation from design doc)

The design.md says "in-memory session object". The actual implementation uses
`sessionStorage` (browser, per-tab). This is functionally equivalent for the
demo flow: the data is never sent to a server, never persisted to disk, and
is cleared when the tab closes. It was chosen so that state survives a hard
page navigation between `/` → `/dashboard` → `/flags` (React router state
would not). This is documented here honestly; nothing is retained after the
session.

### Versions installed

- Next.js: 15.3.3
- Tailwind CSS: v4 (`@tailwindcss/postcss ^4`, `tailwindcss ^4`)
- React: 19.0.0
- TypeScript: 5.x

### Build verification

```
npm run build — Exit 0, zero type/lint errors.

Route (app)            Size    First Load JS
/ (upload)             5.61 kB  107 kB
/dashboard             6.44 kB  111 kB
/flags                 5.94 kB  110 kB
/_not-found              977 B  102 kB
```

### Dev-server check (user-confirmed)

- `GET /`          → HTTP 200
- `GET /dashboard` → HTTP 200
- `GET /flags`     → HTTP 200

### Backend test suite (unchanged — no backend files were touched)

```
269 passed, 0 failed, 2 warnings
(starlette + pytest class-fixture deprecations — cosmetic, no action needed)
```

### Bug fixed during this session

`co?.customer` on `CandidateOrder` (which has `sender`, not `customer`) caused
a TypeScript type error in `dashboard/page.tsx` line 686. Fixed by removing
the `co?.customer` check from the flag-search filter (the `co?.sender` check
on the next line already covers the sender field; ledger-row `.customer` checks
elsewhere are valid because `LedgerRow` does have `customer`).

### Files changed

- `apps/web/lib/api.ts` — new (typed API client)
- `apps/web/app/globals.css` — updated (dark theme, evidence-highlight keyframe)
- `apps/web/app/page.tsx` — replaced stock scaffold with monster-lab upload screen
- `apps/web/app/dashboard/page.tsx` — new (full dashboard)
- `apps/web/app/flags/page.tsx` — new (flag detail page)

### Tasks checked off

**Spec 05 — Dashboard + PDF (`tasks.md`):**
- [x] Next.js app scaffold (App Router + Tailwind), pages `/` and `/dashboard`
- [x] Upload screen (monster-lab): two drop zones + sample-data button
- [x] Mapping confirmation step (spec 01 data)
- [x] Dashboard: ledger table, totals bar, flag list, search box
- [x] Flag cards: evidence (chat line + ledger row), accept/edit/dismiss
- [x] Draft reply with copy-to-clipboard
- [x] Phone layout check (single column, big tap targets)

**Spec 04 — Agent layer (`tasks.md`):**
- [x] Draft reply copy-to-clipboard in the frontend

All 10 items in Spec 05 tasks.md are now checked. All 7 items in Spec 04
tasks.md are now checked.

### Still missing

- Spec 06: Vercel + Render deployment
- Demo video (screen recording of real app, public on YouTube, under 3:00)
- Final Devpost submission (entrant's separate approval required)

## 2026-11-05 — Session 5: Spec 06 deploy prep

### What was created

**`vercel.json`** (repo root):
```json
{ "rootDirectory": "apps/web" }
```
Sets the Vercel project root to `apps/web` so the Next.js build runs there.
Note: if Vercel's import wizard does not pick up `rootDirectory` automatically,
set it manually in Project Settings → General → Root Directory → `apps/web`.
The `vercel.json` file is the canonical declaration; the dashboard is the
fallback.

**`render.yaml`** (repo root):
- Service name: `frankenledger-api`
- Runtime: Python 3.12
- Root directory: `apps/api`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Plan: free
- Health check path: `GET /api/health`
- LLM keys commented out (never in the file — set in Render dashboard if needed)

**`docs/DEPLOY.md`** — full step-by-step runbook covering:
- Render Free deploy (step 1) with card-check trigger
- Vercel Hobby deploy (step 2) with rootDirectory note
- Cold-start behaviour and "waking up" UI gap (step 3)
- Fallback chain: Render → PythonAnywhere → all-Next.js (step 4)
- NEXT_PUBLIC_API_URL wiring table (step 5)
- Repo-verification checklist (step 6)
- Local dev instructions (step 7)
- Post-deploy smoke test checklist (step 8)

### requirements.txt — verified pinned and complete

File: `apps/api/requirements.txt`
```
fastapi==0.162.0
uvicorn==0.54.0
openpyxl==3.1.5
pydantic==2.14.3
reportlab==5.1.0
pytest==9.2.0
httpx==0.28.1
python-multipart==0.0.33
```
All deps pinned to exact versions. No unpinned ranges. All necessary for
runtime (fastapi, uvicorn, openpyxl, pydantic, reportlab, python-multipart)
and testing (pytest, httpx). No new deps needed.

### On-disk security checks (run this session)

| Check | Result |
|---|---|
| `.kiro` mentioned in `.gitignore` | ✅ NOT ignored — line 2 is a comment saying `.kiro` is never ignored; no ignore rule present |
| `.env` or `.env.*` files in repo | ✅ None found |
| Live secret values in source (AIza…, gsk_…) | ✅ None found |
| `GEMINI_API_KEY` / `GROQ_API_KEY` strings in source | ✅ Only variable names in comments, docstrings, and test fixtures using `monkeypatch.setenv` with fake values — no real key values |

### Cold-start UI gap (honest)

The current upload page (`app/page.tsx`) shows a loading spinner while
`uploadSample()` is in flight but gives no explicit "waking up the server"
message. A judge seeing a 45-second spinner with no explanation may think
the app is broken. Recommended fix (not yet applied): after ~5 seconds of
waiting, change the spinner label to:
*"Waking up the server… (Render Free cold start, may take ~30s)"*
This is a small change to `app/page.tsx` that can be done in the next session.

### Tasks checked off (Spec 06)

- [x] `vercel.json` — `rootDirectory: apps/web`
- [x] `render.yaml` — free Render service, build/start/health declared
- [x] `requirements.txt` — pinned, complete, versions recorded above

### Tasks NOT checked off (need browser session with Vercel/Render sign-in)

- [ ] Deploy frontend to Vercel Hobby
- [ ] Deploy backend to Render Free (fallback chain ready in DEPLOY.md)
- [ ] Cold-start test + "waking up" UI state (UI gap noted above)
- [ ] End-to-end test on live URL
- [ ] Repo verification: public repo check (on-disk checks passed)

### Still missing

- Live deploy (Vercel + Render, or fallback) — needs browser session
- "Waking up the server" timed message in app/page.tsx (optional but recommended)
- Demo video (screen recording of real app, public on YouTube, under 3:00)
- Final Devpost submission (entrant's separate approval required)
