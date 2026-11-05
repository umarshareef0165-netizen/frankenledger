# Spec 02 — Deterministic parser: design

## Module
`apps/api/frankenledger/parser.py` — pure functions, stdlib only (re,
datetime). No LLM, no network.

## Pipeline (per chat line)
1. Split line into `(date, time, sender, text)` with the WhatsApp export
   regex; tolerate `DD/MM/YYYY` and `MM/DD/YYYY` (disambiguate by value >
   12), 24-hour and 12-hour times. Unmatched lines → `unparsed`.
2. Skip media/voice lines (`<Media omitted>`, `voice message`, `image
   omitted`, `video omitted`) → counted as `needs_listening`.
3. Quantity: regex for number + unit
   (`kg|kilo|g|gram|packet|pack|darjan|dozen|litre|liter|piece|pcs`), plus
   Roman Urdu number words (`ek/do/teen/chaar/paanch` → 1–5). Default
   quantity 1 when an amount exists but no quantity.
4. Amount: regex for `Rs\.? ?[\d,]+`, `[\d,]+ ?rupy`, `[\d,]+/-`, or a bare
   number at end of line when a quantity/item is present. Strip commas.
5. Payment status: keyword scan on the lowercased text —
   `paid|de diya|paise de diye|payment done` → `paid`;
   `udhaar|rehta hai|baaki|kal|kal paise dunga|kal dunga|udhar` → `udhaar`;
   `promised` when a future-payment phrase is present without "kal";
   else `unknown`.
6. Item: longest catalogue keyword match in the text; else `item_raw` = the
   text with quantity/amount/payment words removed, truncated to 6 words.

## Data shapes
```python
CandidateOrder(date, sender, item, item_raw, quantity, unit, amount_pkr,
               payment_status, source_line, confidence)
# confidence: "high" (quantity+amount+item all found), "medium" (two of three),
# "low" (one). Never a numeric accuracy claim.
```

## Tests
`tests/test_parser.py` — the labelled sample set: ~40 lines covering the
quantity/amount/payment variants above, media lines, unparsed lines, and the
ambiguous cases. The test run prints a small honest report: extracted /
correct / missed / wrong on the sample set.
