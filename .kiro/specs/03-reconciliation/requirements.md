# Spec 03 — Reconciliation: requirements

## User stories
1. As a shop owner, I see exactly what is wrong between my chat and my
   ledger — each problem with its evidence — so I can fix it in one click.
2. As a shop owner, I accept, edit, or dismiss each flag; nothing changes in
   my ledger until I say so.

## Acceptance criteria
- [ ] Flags produced: `PAID_NOT_RECORDED` (chat says paid, no ledger row),
      `RECORDED_NOT_PAID` (ledger row says paid/received, chat shows unpaid
      or no chat order), `PRICE_MISMATCH` (same customer+item+date, amounts
      differ by more than Rs 10), `DUPLICATE` (two ledger rows for one chat
      order), `UNMATCHED_ORDER` (chat order with no ledger row at all).
- [ ] Matching: same customer (fuzzy: case-insensitive, first-name match),
      same item keyword, date within ±1 day, amount within Rs 10 → match.
- [ ] Every flag shows its evidence: chat line(s) with line numbers + ledger
      row number(s), and a one-line plain-language explanation.
- [ ] Each flag has one-click actions: accept (applies the fix to the
      reconciled ledger), edit (change amount/status first), dismiss (flag
      hidden, logged as dismissed, never deleted silently).
- [ ] Totals recompute after every fix: sold, received, outstanding udhaar.
- [ ] The reconciled ledger is a new in-memory ledger; the original uploaded
      ledger is never mutated.
- [ ] Reconciler is deterministic (rules only, no LLM).
