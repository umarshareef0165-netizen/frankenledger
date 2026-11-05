# Spec 01 — File ingest: requirements

## User stories
1. As a shop owner, I upload my WhatsApp chat export (.txt) so the app can
   read my orders and payment promises.
2. As a shop owner, I upload my existing ledger (.xlsx or .csv) so the app can
   compare it with the chat.
3. As a judge, I click "Load sample data" and the fictional sample shop loads
   with no files of my own.

## Acceptance criteria
- [ ] .txt upload accepted; the app shows line count and detected date range.
- [ ] .xlsx upload accepted (openpyxl); .csv upload accepted; the app shows
      detected columns and asks the owner to confirm the column mapping
      (date / customer / item / quantity / amount / paid) on screen.
- [ ] No fixed schema is required: if columns are missing, the app says which
      ones are missing instead of failing.
- [ ] Empty files, wrong extensions, and unreadable files produce a clear
      on-screen error, never a crash.
- [ ] Sample-data mode loads `samples/sample-chat-export.txt` and the sample
      ledger, clearly labelled "fictional sample data".
- [ ] Uploaded files live only for the session (memory/temp storage); nothing
      is retained after the session ends unless the owner exports.
- [ ] The original ledger file is never overwritten.
