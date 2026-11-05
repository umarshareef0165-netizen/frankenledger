# FrankenLedger — Kiroween 2026, Category: Frankenstein

> **Built with Kiro.** Solo project by Umar Shareef for Kiroween 2026.
> Status: in build (Nov 5, 2026). Not submitted yet.

**One-line pitch:** *Your shop already keeps its books in WhatsApp and Excel —
FrankenLedger stitches them together so nothing gets lost.*

A small general store runs its business on WhatsApp messages and an Excel
sheet. Orders arrive as chat messages in mixed Roman Urdu and English,
payments are promised in chat and sometimes forgotten, and the Excel ledger is
updated by hand — late, partially, or not at all. FrankenLedger takes the two
messy artefacts the shop already has, lets an agent reconcile them, and gives
the owner back a clean ledger, a list of exactly what is wrong, and a paper
printout for the shop counter.

## The four stitched technologies

| # | Technology | What it does here |
|---|---|---|
| 1 | WhatsApp chat export (.txt) | Raw source of truth for orders and payments; parsed line by line |
| 2 | Excel spreadsheet (.xlsx / .csv) | The shop's existing ledger; read and written as a real file |
| 3 | LLM agent | Extracts structured orders, explains matches/mismatches, drafts replies |
| 4 | Paper (printable PDF ledger) | A clean daily ledger for the shop counter |

## What it does

1. Upload a WhatsApp chat export (.txt) and the shop's ledger (.xlsx / .csv).
2. The deterministic parser extracts candidate orders (date, sender, item,
   quantity, amount, paid / udhaar / kal markers) — every extraction links to
   its source line number. No LLM needed for this step.
3. The reconciler matches chat orders against ledger rows and produces flags:
   `PAID_NOT_RECORDED`, `RECORDED_NOT_PAID`, `PRICE_MISMATCH`, `DUPLICATE`,
   `UNMATCHED_ORDER` — each with its evidence (chat line + ledger row) and a
   one-click fix (accept / edit / dismiss).
4. Dashboard: reconciled ledger, today's totals (sold, received, outstanding
   udhaar), flag list, search.
5. Draft reply in the same Roman Urdu/English mix as the chat, copyable in one
   click for pasting back into WhatsApp.
6. One-click daily ledger PDF and clean spreadsheet export (the original file
   is never overwritten).
7. Sample-data mode: one click loads a clearly labelled fictional sample shop
   ("Noor General Store" — invented customers, invented numbers).

## Run it

Backend (Python FastAPI):

```
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend (Next.js):

```
cd apps/web
npm install
npm run dev
```

Tests:

```
cd apps/api && python3 -m pytest tests -v
```

## Honest limitations

- No real WhatsApp integration — by design. The app reads a chat export the
  owner makes themselves (a free, standard WhatsApp feature); it never touches
  a live account, sends messages, or reads anyone's live chats.
- Single-user, single-shop, no accounts, no cloud sync, no payments.
- The LLM can mis-extract; every fact carries its evidence and every flag
  needs a human accept/edit.
- Sample data is fictional (invented shop and customers) and labelled as such
  wherever it appears. No real shop's data is used anywhere.
- No fine-tuning is done; the agent uses a hosted LLM via API. If no LLM key
  is configured, the app runs in deterministic mode (parser + rules only) and
  says so on screen.
- No accuracy percentage is claimed. Extraction quality is reported only on
  the small labelled sample set in `tests/`, honestly, with misses shown.

## How it was built

Spec-driven with Kiro (CLI 3.0.0): see `.kiro/specs/` (6 specs),
`.kiro/steering/`, `.kiro/agents/`, and `KIRO-USAGE.md`.
