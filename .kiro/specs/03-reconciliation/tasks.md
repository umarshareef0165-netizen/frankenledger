# Spec 03 — Reconciliation: tasks

- [x] Normalisation: customer names, item keywords, dates.
- [x] Matcher: customer + item + ±1 day + ±Rs 10; best-score, one-to-one.
- [x] Flag generation: PAID_NOT_RECORDED, RECORDED_NOT_PAID,
      PRICE_MISMATCH, DUPLICATE, UNMATCHED_ORDER — each with evidence.
- [x] Fix actions: accept / edit / dismiss; totals recompute after each fix.
- [x] `POST /api/reconcile` and `POST /api/reconcile/fix` endpoints.
- [x] Tests: one test per flag kind on the fictional sample set; matching
      edge cases (name variants, ±1 day, Rs 10 boundary, duplicates).
- [x] Demo-flow smoke test: sample data → all five flag kinds visible.
