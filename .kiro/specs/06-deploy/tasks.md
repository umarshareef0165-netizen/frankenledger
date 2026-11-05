# Spec 06 — Deploy: tasks

- [x] `apps/web/vercel.json` (root directory `apps/web`) — or Vercel
      dashboard config documented.
- [x] `render.yaml` — free Render service for `apps/api/`.
- [x] `apps/api/requirements.txt` — fastapi, uvicorn, openpyxl, reportlab,
      pydantic (pinned, versions recorded).
- [ ] Deploy frontend to Vercel Hobby; record live URL in README + BUILD-LOG.
      ⚠ Needs browser session with Vercel sign-in. See docs/DEPLOY.md §2.
- [ ] Deploy backend to Render Free; record live URL; wire
      `NEXT_PUBLIC_API_URL`.
      ⚠ Needs browser session with Render sign-in. See docs/DEPLOY.md §1.
      If Render asks for a card: STOP, use PythonAnywhere fallback (§4).
- [ ] Cold-start test on the live URL + "waking up" UI state.
      ⚠ Needs live URL. Note: a timed "Waking up…" message is recommended
      in app/page.tsx (see docs/DEPLOY.md §3) — not yet added to the frontend.
- [ ] End-to-end test on the live URL (sample data → flags → PDF → xlsx).
      ⚠ Needs live URL. Smoke-test checklist in docs/DEPLOY.md §8.
- [ ] Repo verification: public, MIT detectable, `/.kiro` present, not
      gitignored, no secrets.
      ⚠ On-disk checks passed (Session 5). "Public repo" check needs GitHub UI.
- [ ] If Render asks for a card: STOP, use PythonAnywhere fallback, log it.
      ⚠ Triggered only during the live deploy session.
