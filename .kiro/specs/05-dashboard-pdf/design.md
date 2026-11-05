# Spec 05 — Dashboard + PDF: design

## Frontend (`apps/web/`, Next.js App Router + Tailwind)
- Pages: `/` (upload / monster-lab screen), `/dashboard` (ledger + totals +
  flags + search), `/flags` (flag detail with evidence + fix actions).
- State: session object in memory (no login, no persistence): `{chat, ledger,
  orders, reconciled, flags, totals, mode}`. API base URL from
  `NEXT_PUBLIC_API_URL` (default `http://localhost:8000` for local dev).
- Components: `UploadZone`, `MappingConfirm`, `LedgerTable`, `TotalsBar`,
  `FlagCard` (evidence + accept/edit/dismiss), `DraftReply` (copy button),
  `SampleBanner`.

## PDF (backend, reportlab)
- `POST /api/export/pdf` — `{reconciled, totals, date}` → PDF bytes.
  Layout: header (shop name "Noor General Store (sample)" or the owner's
  shop name from the ledger filename), date, totals box, udhaar table
  (customer, item, amount, since), flags resolved today, footer ("Built with
  Kiro — FrankenLedger, Kiroween 2026").

## Spreadsheet export (backend, openpyxl)
- `POST /api/export/xlsx` — `{reconciled, flags}` → .xlsx bytes with two
  sheets: `Ledger` (reconciled rows) and `Flags` (flag kind, explanation,
  status: open/fixed/dismissed).

## Endpoints
- `GET /api/health` → `{ok: true, mode}`.
- `POST /api/export/pdf`, `POST /api/export/xlsx` as above.
