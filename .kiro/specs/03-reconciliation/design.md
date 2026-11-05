# Spec 03 — Reconciliation: design

## Module
`apps/api/frankenledger/reconciler.py` — pure functions, stdlib only.

## Matching
- Normalise customer names: lowercase, strip titles (bhai, sahab, uncle),
  first-token match accepted.
- Normalise items: catalogue keyword (same list as the parser).
- Candidate match: same customer AND same item AND |date diff| ≤ 1 day AND
  |amount diff| ≤ Rs 10 → `matched`. Amount differs by > Rs 10 with the rest
  matching → `PRICE_MISMATCH`.
- Each chat order matches at most one ledger row (best score: exact date,
  then exact amount, then first row). Each ledger row matches at most one
  chat order. Leftovers become flags.

## Flag generation (in order)
1. Chat order paid + no ledger row → `PAID_NOT_RECORDED`
   (fix: add ledger row).
2. Chat order unpaid + no ledger row → `UNMATCHED_ORDER`
   (fix: add ledger row as udhaar).
3. Ledger row paid + no chat order → `RECORDED_NOT_PAID`
   (fix: keep row, mark "no chat evidence" — or dismiss).
4. Matched pair, amounts differ > Rs 10 → `PRICE_MISMATCH`
   (fix: choose chat amount or ledger amount).
5. Two ledger rows match one chat order → `DUPLICATE`
   (fix: keep first, mark second duplicate).

## Data shapes
```python
Flag(kind, chat_order: CandidateOrder|None, ledger_row: LedgerRow|None,
     explanation: str, fix: {action, row_patch})
ReconciledLedger(rows: [LedgerRow], flags: [Flag],
                 totals: {sold, received, outstanding})
LedgerRow(date, customer, item, quantity, amount_pkr, paid, source: str)
# source: "ledger:row N" or "chat:line N" or "fix:<flag kind>"
```

## Endpoints
- `POST /api/reconcile` — `{orders, ledger_rows, mapping}` →
  `{reconciled, flags, totals}`.
- `POST /api/reconcile/fix` — `{flag_id, action: accept|edit|dismiss,
  patch?}` → updated `{reconciled, flags, totals}`.
