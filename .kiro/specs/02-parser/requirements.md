# Spec 02 — Deterministic parser: requirements

## User stories
1. As a shop owner, my chat lines become structured orders automatically —
   without any AI key — so I can see what was ordered, by whom, for how
   much, and whether it was paid.
2. As a shop owner, every extracted order shows me the exact chat line it
   came from, so I can trust or correct it.

## Acceptance criteria
- [ ] Each chat line yields 0 or 1 candidate order with fields: date, sender,
      item (keyword), quantity, amount, payment status
      (`paid` / `udhaar` / `promised` / `unknown`), and `source_line`.
- [ ] Quantities understood: "2kg", "2 kilo", "do kilo", "2 kg", "5 packet",
      "3 darjan" (dozen = 12), plain numbers.
- [ ] Amounts understood: "500", "Rs 500", "Rs. 500", "500 rupy", "500/-",
      "Rs 1,500".
- [ ] Payment markers: "paid", "de diya", "paise de diye", "udhaar", "kal",
      "kal paise dunga", "kal dunga", "rehta hai", "baaki".
- [ ] Item keywords: a small built-in catalogue for the sample shop
      (cheeni/sugar, atta/flour, chawal/rice, doodh/milk, anda/egg, chai/tea,
      ghee, daal, namak/salt, sabun/soap) plus a fallback: the first
      non-quantity noun phrase after the sender is kept as `item_raw`.
- [ ] Voice-note / media lines are never parsed as orders; they are counted
      as "needs listening".
- [ ] Parser is deterministic: same input always gives the same output, no
      LLM, no network.
- [ ] Every candidate order carries its source line number; the UI shows it.
- [ ] Labelled sample set in `tests/`: each sample line has the expected
      extraction; the parser's measured results (correct / missed / wrong)
      are reported honestly — no percentage is claimed beyond the sample set.
