# Spec 01 — File ingest: tasks

- [x] Backend: `POST /api/upload/chat` — .txt ingest, line count, date range,
      sender list, unparsed/voice-note counts.
- [x] Backend: `POST /api/upload/ledger` — .xlsx (openpyxl) + .csv ingest,
      column detection, suggested mapping, preview rows.
- [x] Backend: `POST /api/upload/sample` — loads fictional sample files,
      labelled as sample.
- [x] Backend: `POST /api/upload/confirm-mapping` — owner-confirmed mapping.
- [x] Backend tests: empty file, wrong extension, unreadable file, missing
      columns, voice-note lines, 12-hour dates.
- [ ] Frontend: upload screen with two drop zones + sample-data button +
      mapping confirmation step.
- [ ] Demo-flow smoke test: sample chat + sample ledger upload end-to-end.
