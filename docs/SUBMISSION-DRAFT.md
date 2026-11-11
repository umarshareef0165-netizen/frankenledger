# FrankenLedger — Devpost submission DRAFT (not submitted)

> DRAFT ONLY. Verify every field live on the Devpost form before submitting.
> Submission needs the entrant's separate final approval.

## Title
FrankenLedger — Your Shop's Books, Stitched Together

## Category
Frankenstein

## Tagline
Your shop already keeps its books in WhatsApp and Excel — FrankenLedger
stitches them together so nothing gets lost.

## Description (draft)
A small general store runs its business on WhatsApp messages and an Excel
sheet. Orders arrive as chat messages in mixed Roman Urdu and English,
payments are promised in chat and sometimes forgotten, and the Excel ledger is
updated by hand — late, partially, or not at all. FrankenLedger takes the two
messy artefacts the shop already has, lets an agent reconcile them, and gives
the owner back a clean ledger, a list of exactly what is wrong, and a paper
printout for the shop counter.

Four incompatible technologies, one app: a WhatsApp chat export (.txt), an
Excel spreadsheet (.xlsx/.csv), an LLM agent, and a printable paper ledger
(PDF). The deterministic parser extracts orders with source-line links; the
reconciler raises evidence-linked flags (PAID_NOT_RECORDED,
RECORDED_NOT_PAID, PRICE_MISMATCH, DUPLICATE, UNMATCHED_ORDER); the agent
explains each flag and drafts a reply in the same Roman Urdu/English mix;
the dashboard shows the clean ledger and totals; one click downloads the
daily PDF and a clean spreadsheet. No WhatsApp API, no payments, no accounts,
no login — the live URL works immediately, and sample-data mode loads a
clearly labelled fictional shop.

Built with Kiro: spec-driven development (6 specs in `/.kiro`), steering
files, custom agents, and hooks. See `KIRO-USAGE.md` in the repo.

## How Kiro was used (draft — from KIRO-USAGE.md)
Built entirely with Kiro CLI 3.0.0, spec-driven: 6 specs
(`01-file-ingest`, `02-parser`, `03-reconciliation`, `04-agent-layer`,
`05-dashboard-pdf`, `06-deploy`), steering files (product, tech-stack,
honesty, demo), custom agents (ledger-agent, demo-agent, reviewer-agent),
and hooks (tests on save, secret blocking, demo smoke test). The `/.kiro`
directory is committed at the repo root as evidence.

## Links (verified 2026-11-11)
- Public GitHub repo: https://github.com/umarshareef0165-netizen/frankenledger
- Live app URL: https://frankenledger-21fh.vercel.app
- Demo video (< 3 min, public YouTube): https://youtu.be/xNHWhH5CjZc

## Bonus
- Best Student Project (Frankenstein): LinkedIn profile, student email,
  4th year BSCS, University of Agriculture Faisalabad.
- Optional: Social Blitz post (starts with `#KiroweenHackathon26`); Bonus
  Blog post URL.

## Honest limits (stated in the submission)
- No real WhatsApp integration — reads a chat export the owner makes
  themselves.
- Single-user, single-shop, no accounts, no cloud sync, no payments.
- Sample data is fictional. No accuracy percentage is claimed; extraction
  quality is reported only on the small labelled sample set.
- No fine-tuning; the deployed agent currently runs in deterministic mode
  (parser + rules only) because no LLM key is configured — a hosted LLM
  via API is wired in and activates when a key is set.
