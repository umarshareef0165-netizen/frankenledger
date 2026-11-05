# Spec 04 — Agent layer: requirements

## User stories
1. As a shop owner, the agent explains each flag in plain language and drafts
   a reply I can paste back into WhatsApp for an unpaid customer.
2. As a judge trying the demo without any key, the app still works fully in
   deterministic mode and says so honestly.

## Acceptance criteria
- [ ] When a server-side LLM key (`GEMINI_API_KEY` or `GROQ_API_KEY`) is set,
      the agent: (a) turns low-confidence candidate orders into structured
      orders with a short reason; (b) writes a one-line plain-language
      explanation for each flag; (c) drafts a short Roman Urdu/English reply
      for any unpaid order.
- [ ] When NO key is set, the app runs in deterministic mode: the UI shows
      "Deterministic mode — parser + rules only, no AI key configured", agent
      features are shown as unavailable, and every other feature works.
- [ ] The LLM never sees a real user's files unless the owner uploaded them
      in this session; nothing is sent to the LLM except the current session's
      chat lines and ledger rows. No data is stored by the agent.
- [ ] Draft replies are in the same Roman Urdu/English mix as the chat
      ("Salam Ahmed bhai, 2kg cheeni ka Rs 500 rehta hai…"), copyable in one
      click.
- [ ] Agent output is always shown as a suggestion the owner must accept; it
      never changes the ledger by itself.
- [ ] Key is read from a server-side environment variable only. No key in the
      repo, no key in the client, no key in logs.
- [ ] No fine-tuning is done or claimed; the agent uses a hosted LLM via API.
