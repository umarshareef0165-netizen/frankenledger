# product.md — FrankenLedger product steering

## Concept
FrankenLedger stitches four incompatible technologies into one app for a small
shop: a WhatsApp chat export (.txt), an Excel ledger (.xlsx/.csv), an LLM
agent, and a printable paper ledger (PDF). The shop's books live in WhatsApp
and Excel; the app reconciles them so nothing gets lost.

## User
A small general store / kiryana shop owner (primary), home tutor, or
freelancer. They work in mixed Roman Urdu and English on a phone browser.
They do not want to change how they work — the app adapts to their files.

## Core flow
Upload chat export + ledger → deterministic parser extracts candidate orders
with source-line links → reconciler matches chat orders to ledger rows and
raises evidence-linked flags → owner accepts/edits/dismisses each flag →
dashboard shows clean ledger + totals → draft WhatsApp reply, daily PDF, clean
spreadsheet export.

## Honesty rules (non-negotiable)
- Every extracted fact links to its source chat line and ledger row.
- Sample data is fictional and labelled as such everywhere it appears.
- Never claim a live WhatsApp integration, real users, real shops, payments,
  or any accuracy percentage. Report extraction quality only on the small
  labelled sample set, with misses shown.
- The demo is the acceptance test: every feature must work in the 3-minute
  demo flow (see demo.md).
