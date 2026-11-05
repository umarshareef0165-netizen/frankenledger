# Spec 06 — Deploy: requirements

## User stories
1. As a judge, I open the live URL and the app works immediately, no login.
2. As the entrant, I can redeploy the app without a card or a payment.

## Acceptance criteria
- [ ] Frontend deployed on Vercel Hobby (free, no card): `NEXT_PUBLIC_API_URL`
      points at the deployed backend.
- [ ] Backend deployed on Render Free (no card). Fallback chain, tested in
      order if Render asks for a card: PythonAnywhere free tier, then
      all-Next.js on Vercel alone.
- [ ] Live URL loads without login; sample-data mode works on the live URL.
- [ ] Cold-start behaviour documented (Render Free sleeps; the UI shows a
      "waking up the server…" state instead of an error).
- [ ] Repo checks pass: public repo, MIT license detectable at top, `/.kiro`
      present and NOT in `.gitignore`, no secrets in the repo.
- [ ] End-to-end test on the live URL: sample chat + sample ledger → flags →
      PDF → xlsx, all working.
- [ ] No deployment step needs a card, a payment, or a secret in the repo.
