# Spec 02 — Deterministic parser: tasks

- [x] Data model: `CandidateOrder` + `PaymentStatus` + confidence levels.
- [x] Chat-line splitter: dates (DD/MM + MM/DD, 12h/24h), sender, text;
      unparsed lines counted, not dropped.
- [x] Quantity extraction: units + Roman Urdu number words.
- [x] Amount extraction: Rs / rupy / /- / bare-number forms.
- [x] Payment-status markers: paid / udhaar / promised / unknown.
- [x] Item catalogue + `item_raw` fallback.
- [x] Media/voice lines → "needs listening", never parsed as orders.
- [x] Labelled sample set in `tests/test_parser.py` (~40 lines) + honest
      sample report (correct / missed / wrong).
- [x] `POST /api/parse` endpoint returning candidate orders with source lines.
