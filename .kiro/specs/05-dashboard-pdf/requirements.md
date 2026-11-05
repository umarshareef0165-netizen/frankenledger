# Spec 05 — Dashboard + PDF: requirements

## User stories
1. As a shop owner, I see my clean ledger, today's totals, and every flag on
   one screen that works on my phone.
2. As a shop owner, I download a paper ledger PDF for the counter and a clean
   spreadsheet of the reconciled ledger.

## Acceptance criteria
- [ ] Dashboard shows: reconciled ledger table, totals (sold, received,
      outstanding udhaar), flag list with evidence and fix buttons, search box
      (customer/item).
- [ ] Every flag shows its chat line number and ledger row number; clicking
      either scrolls to/highlights the evidence.
- [ ] One-click daily ledger PDF: date, totals, udhaar list, flags resolved
      today. Downloads as a real PDF, prints cleanly on A4.
- [ ] One-click clean spreadsheet export (.xlsx): reconciled rows + a flags
      sheet; original file never overwritten.
- [ ] Sample-data mode: one click, whole flow works, banner says "Fictional
      sample data — Noor General Store".
- [ ] Dashboard works on a phone browser (single column, big tap targets).
- [ ] The app loads without login; the live URL works immediately.
