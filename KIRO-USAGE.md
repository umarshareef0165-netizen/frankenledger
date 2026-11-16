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

## Property-based testing (added Nov 12, 2026 — win-prep)

- `tests/test_properties.py` — 16 property tests over the parser (Spec 02)
  and reconciler (Spec 03), seeded stdlib `random` only (no Hypothesis
  dependency; each property uses a fixed recorded seed, so runs are
  reproducible). Properties asserted for every generated input, not just
  hand-picked examples:
  - Parser: determinism (re-parse gives identical orders); an explicit Rs
    amount is always parsed exactly; quantity/unit/item round-trip;
    paid vs udhaar classification; shop-sender lines never produce orders;
    media/voice-note lines count as voice notes, never orders; arbitrary
    garbage lines never raise and line accounting always adds up; full
    signal (item + quantity + amount) always means high confidence.
  - Reconciler: totals always satisfy outstanding == sold − received;
    `reconcile()` never mutates its input rows or orders; an identical paid
    order + paid row raises zero flags; an amount gap > Rs 10 with the same
    name/item/date always raises PRICE_MISMATCH; matching is one-to-one;
    dismiss removes exactly one active flag and never mutates the original;
    accepting PAID_NOT_RECORDED adds a paid row for the order's amount;
    two identical ledger rows always raise DUPLICATE; `reconcile()` never
    raises on random inputs and only ever emits the five known flag kinds.
- Verified Nov 12, 2026: full suite **285 passed** (269 pre-existing + 16
  new property tests), `npm run build` clean in `apps/web`.

## What Kiro was NOT used for (honest limits)

- **No MCP server** is wired into the build; no Kiro powers, no Kiro Web,
  and no Kiro Crew were used — the build is Kiro CLI + specs + steering +
  custom agents + hooks only. The property-based test suite above is the
  one additional verifiable Kiro-prompted engineering practice added
  during win-prep; it is not a claim of MCP/powers/Web/Crew use.

## Evidence in this repo

- `/.kiro` at the repo root, committed from day one, never gitignored.
- Each spec's `tasks.md` is checked off as Kiro completes it.
- `BUILD-LOG.md` is the honest build diary (what works, what is missing).
