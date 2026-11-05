# Spec 04 — Agent layer: tasks

- [x] `GET /api/agent/status` — llm vs deterministic mode detection.
- [x] LLM client (Gemini free tier, urllib, JSON-only prompts, 20s timeout).
- [x] Deterministic fallbacks: flag explanations + draft-reply templates.
- [x] `POST /api/agent/explain`, `/api/agent/draft-reply`,
      `/api/agent/structure` endpoints.
- [x] Draft reply copy-to-clipboard in the frontend.
- [x] Tests: deterministic mode with no key set (all endpoints work, source =
      template/deterministic); invalid-LLM-response fallback; no key ever
      appears in logs or responses.
- [x] Demo-flow smoke test in deterministic mode (the default for the video).
