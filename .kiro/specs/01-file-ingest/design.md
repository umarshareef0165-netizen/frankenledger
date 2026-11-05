# Spec 01 — File ingest: design

## Upload endpoints (FastAPI, `apps/api/`)
- `POST /api/upload/chat` — multipart .txt; returns `{lines, date_range,
  senders, preview_lines}`.
- `POST /api/upload/ledger` — multipart .xlsx/.csv; returns `{columns,
  row_count, suggested_mapping, preview_rows}`.
- `POST /api/upload/sample` — loads the fictional sample files from
  `samples/`; returns the same shapes as the two upload endpoints, plus
  `{sample: true, label: "fictional sample data"}`.
- `POST /api/upload/confirm-mapping` — owner-confirmed column mapping
  `{date, customer, item, quantity, amount, paid}` (any may be null).

## Parsing (no LLM)
- Chat: split into lines; WhatsApp export format
  `DD/MM/YYYY, HH:MM - Sender: message` (also `MM/DD/YYYY` and 12-hour
  variants tolerated); lines that do not match are kept as "unparsed" and
  counted, not dropped silently. Voice-note placeholders
  (`<Media omitted>`, "voice message") are counted as "needs listening".
- Ledger: openpyxl for .xlsx (first sheet, first row = header), csv module
  for .csv. Header names are matched case-insensitively against synonyms
  (e.g. `amount`/`rs`/`price`/`total`; `customer`/`name`/`party`;
  `paid`/`status`/`payment`); unmatched columns are shown, not guessed.

## Data shapes
```json
ChatFile { lines: int, date_range: [str, str], senders: [str],
           parsed_lines: int, unparsed_lines: int, voice_notes: int }
LedgerFile { columns: [str], row_count: int,
             suggested_mapping: {date, customer, item, quantity, amount, paid},
             preview_rows: [ {col: value} ] }
```

## Frontend (`apps/web/`)
- Upload screen ("monster lab"): two drop zones (chat, ledger) + sample-data
  button; shows line/row counts and detected date range; column-mapping
  confirmation step before the parser runs.
