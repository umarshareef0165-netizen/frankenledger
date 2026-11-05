# Hooks — FrankenLedger

Kiro hooks for this project (intent documented here; enforced by the build
process and the reviewer-agent until Kiro hook configs are wired):

1. **On file save in `apps/api/`** — run the matching unit tests
   (`python3 -m pytest tests -q`). A failing test blocks the "done" claim for
   that task.
2. **On commit** — block if a secret pattern (API key, token, password) or a
   `.env` file is staged. The reviewer-agent re-checks every diff for the
   same.
3. **After every spec task completes** — re-run the demo-flow smoke test
   (sample chat + sample ledger → flags → PDF → spreadsheet export) and log
   the result in `BUILD-LOG.md`.

No hook runs a deployment, a payment, or a submission. Deployments and the
Devpost submission are manual steps with the entrant's approval.
