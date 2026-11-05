# KIRO-USAGE.md — how Kiro was used to build FrankenLedger

For the Kiroween submission write-up. Every claim here is checkable in this
repo.

## Tool

- **Kiro CLI 3.0.0** in the build VM (`~/.local/bin/kiro-cli`), signed in with
  Google as umarshareef0165@gmail.com (verified with `kiro-cli whoami` on
  2026-11-05 before any build step).
- All implementation work was done through `kiro-cli chat` sessions
  (`--no-interactive -a --trust-workspace`), one session per spec slice,
  run from the project root so Kiro's specs, steering and agents loaded.
- No app code was written without Kiro. Scaffolding files Kiro needs to
  function (the `.kiro` directory itself, LICENSE, README, `.gitignore`,
  fictional sample data) were created first so Kiro had the specs to follow.

## Specs (`.kiro/specs/`, 6 specs, each with requirements.md, design.md, tasks.md)

| Spec | Slice | Built via Kiro |
|---|---|---|
| 01-file-ingest | Chat (.txt) + ledger (.xlsx/.csv) upload & detection | — |
| 02-parser | Deterministic extraction (dates, senders, items, quantities, amounts, paid/udhaar/kal) | — |
| 03-reconciliation | Flags + fixes (PAID_NOT_RECORDED, RECORDED_NOT_PAID, PRICE_MISMATCH, DUPLICATE, UNMATCHED_ORDER) | — |
| 04-agent-layer | LLM extraction + draft replies, deterministic fallback | — |
| 05-dashboard-pdf | Dashboard UI, PDF export, spreadsheet export, sample-data mode | — |
| 06-deploy | Vercel + Render/PythonAnywhere deploy, end-to-end test | — |

## Steering (`.kiro/steering/`)

- `product.md` — concept + honesty rules
- `tech-stack.md` — Next.js + FastAPI, free tiers only, no card
- `honesty.md` — never invent users/metrics/partners; every extraction links
  to its source line; label sample data as fictional; never claim a live
  WhatsApp integration
- `demo.md` — the 3-minute demo is the acceptance test for every feature

## Custom agents (`.kiro/agents/`)

- `ledger-agent` — owns parser + reconciler code and its tests
- `demo-agent` — owns the sample data and the demo script; verifies the demo
  flow end-to-end after every change
- `reviewer-agent` — reads each diff for false claims, secrets, and
  unhandled edge cases before anything is committed

## Hooks (`.kiro/hooks/`)

Documented in `.kiro/hooks/README.md`: run matching unit tests on file save
in `apps/api/`; block commits staging a secret pattern or a `.env` file;
re-run the demo-flow smoke test after every spec task completes.

## Credits

- Free Kiro credits (4,000) request: **NOT yet filed** — deadline Dec 1,
  2026, 12:00 PM PT via the Resources-tab form. (This build ran on the
  signed-in account's included usage.)
- Build with Kiro live session: Nov 11, 2026, 10:00 AM PT — attendance
  pending (entrant's step).

## Evidence in this repo

- `/.kiro` at the repo root, committed from day one, never gitignored.
- Each spec's `tasks.md` is checked off as Kiro completes it.
- `BUILD-LOG.md` is the honest build diary (what works, what is missing).
