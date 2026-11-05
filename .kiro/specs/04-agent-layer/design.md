# Spec 04 — Agent layer: design

## Module
`apps/api/frankenledger/agent.py` — LLM client + deterministic fallbacks.
`apps/api/frankenledger/draft.py` — draft-reply templates (deterministic).

## LLM client
- Provider: Google Gemini (AI Studio, free tier) via `GEMINI_API_KEY`, or
  Groq via `GROQ_API_KEY`. Plain HTTPS calls (urllib), no heavy SDK.
- One call per job, with a strict JSON-only prompt: input is the candidate
  order / flag evidence; output is `{structured_order | explanation |
  draft_reply}`. Responses are validated; invalid JSON → deterministic
  fallback for that job, logged as such.
- Timeouts: 20s per call; on timeout/rate-limit/error → deterministic
  fallback, UI shows "agent unavailable right now — deterministic results
  shown".

## Deterministic fallbacks (no key, or LLM failure)
- Structured orders: the parser's candidate orders as-is.
- Flag explanations: template from flag kind + evidence
  ("Chat line 12 says Ahmed paid Rs 500, but no ledger row records it.").
- Draft replies: template with the customer's name, item, amount
  ("Salam {name} bhai, {item} ka Rs {amount} rehta hai, kal de dena.").

## Endpoints
- `GET /api/agent/status` → `{mode: "llm"|"deterministic", provider?}`.
- `POST /api/agent/explain` — `{flag}` → `{explanation, source: llm|template}`.
- `POST /api/agent/draft-reply` — `{order}` → `{draft, source: llm|template}`.
- `POST /api/agent/structure` — `{candidate_orders}` →
  `{orders, source: llm|deterministic}`.
