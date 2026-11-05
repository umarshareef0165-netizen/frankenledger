# demo.md — FrankenLedger demo steering

The 3-minute demo video (target 2:45, hard limit 3:00) is the acceptance
test for every feature. A feature that does not work in the demo flow does
not ship.

## Demo flow (see docs/DEMO-SCRIPT.md for the timed script)
1. Hook: monster-lab upload screen. "My shop's books live in WhatsApp and
   Excel. Both are lying to me."
2. The mess: fictional "Noor General Store" sample chat export + messy sample
   Excel ledger uploaded.
3. The stitch: orders extracted with source-line links; the four technologies
   shown joining.
4. The flags: PAID_NOT_RECORDED, RECORDED_NOT_PAID, PRICE_MISMATCH — each
   with evidence. One flag fixed on screen; totals update.
5. The reply + the paper: draft reply in Roman Urdu copied in one click;
   daily ledger PDF downloaded and shown.
6. Close: clean spreadsheet export; honest close on screen: "Built with Kiro.
   Sample data — fictional. No WhatsApp API, no payments."

## Rules
- Real app only. No mockups, no generated video, no staged screenshots
  presented as the app.
- Sample-data mode must work with one click — judges try the whole flow
  without their own files.
- The demo is designed to work end-to-end in deterministic mode (no LLM key).
- The demo-agent verifies the demo flow end-to-end after every change.
- Video is recorded by the entrant (screen recording of the real app), public
  on YouTube, under 3:00.
