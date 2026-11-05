# honesty.md — FrankenLedger honesty steering

These rules apply to every file, screen, and submission text. They exist
because the project's credibility depends on them.

1. **Never invent users, metrics, partners, or results.** No user counts, no
   revenue, no "shops using it", no accuracy percentage. The only numbers
   reported are the ones measured on the small labelled sample set in
   `tests/`, with misses shown.
2. **Every extraction links to its source.** Each parsed order and each flag
   carries its chat line number and ledger row reference. A fact without
   evidence is not shown as a fact.
3. **Sample data is fictional.** "Noor General Store" and all its customers,
   items, and numbers are invented. Every sample file, screen, and the demo
   video label them as fictional.
4. **Never claim a live WhatsApp integration.** The app reads a chat export
   the owner makes themselves. It never touches a live account, never sends
   messages, never reads live chats. The README, UI, and submission all say
   this.
5. **No payments, no bank integration, no real money movement.** The app
   tracks promised/paid amounts in text only.
6. **Deterministic mode is labelled.** When no LLM key is configured, the UI
   says "deterministic mode — parser + rules only" and the agent features are
   honestly shown as unavailable, not faked.
7. **No fine-tuning claimed.** The agent uses a hosted LLM via API; it is not
   a trained model. The write-up says exactly that.
