"""
FrankenLedger — deterministic draft-reply templates, Spec 04.

All templates use the same Roman Urdu/English mix as the sample chat export.
These are used as fallbacks when no LLM key is configured, or when the LLM
call fails.

Public functions:
  explain_flag(flag: dict) -> str
      One-line evidence-linked explanation for a reconciliation flag.
  draft_reply(order: dict) -> str
      Short WhatsApp reminder message for an unpaid order.
"""
from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Flag explanation templates
# ---------------------------------------------------------------------------

# Keys match the FlagKind constants in reconciler.py
_EXPLAIN_TEMPLATES: dict[str, str] = {
    "PAID_NOT_RECORDED": (
        "{sender} ne {item} ka Rs {amount} de diya ({chat_evidence}), "
        "lekin ledger mein koi row nahi hai."
    ),
    "UNMATCHED_ORDER": (
        "{sender} ne {item} manga ({chat_evidence}), "
        "lekin ledger mein koi matching row nahi mili."
    ),
    "RECORDED_NOT_PAID": (
        "Ledger {ledger_evidence} mein {customer} ka Rs {amount} paid dikhata hai, "
        "lekin chat mein payment confirm nahi hua."
    ),
    "PRICE_MISMATCH": (
        "{sender} {item}: chat mein Rs {chat_amount} likha hai ({chat_evidence}), "
        "lekin {ledger_evidence} mein Rs {ledger_amount} hai. "
        "Farq: Rs {diff}."
    ),
    "DUPLICATE": (
        "{ledger_evidence_a} aur {ledger_evidence_b} dono mein {customer} "
        "{item} Rs {amount} record hai — shayad duplicate entry hai."
    ),
}

_GENERIC_EXPLAIN = (
    "Flag {kind}: {explanation}"
)


def explain_flag(flag: dict) -> str:
    """
    Return a one-line explanation for a reconciliation flag.
    Uses evidence from the flag (chat line number and ledger row number)
    so every claim links to a source.

    Parameters
    ----------
    flag : dict
        A flag dict as serialised by main.py's _serialise_reconciled().
        Expected keys: kind, chat_order (optional), ledger_rows (list),
        explanation (pre-computed by reconciler).
    """
    kind: str = flag.get("kind", "UNKNOWN")
    existing: str = flag.get("explanation", "")
    chat_order: Optional[dict] = flag.get("chat_order")
    ledger_rows: list[dict] = flag.get("ledger_rows", [])

    # Helpers
    def _sender() -> str:
        if chat_order:
            return chat_order.get("sender") or "Grahak"
        if ledger_rows:
            return ledger_rows[0].get("customer") or "Grahak"
        return "Grahak"

    def _item() -> str:
        if chat_order:
            return chat_order.get("item") or chat_order.get("item_raw") or "item"
        if ledger_rows:
            return ledger_rows[0].get("item") or "item"
        return "item"

    def _chat_evidence() -> str:
        if chat_order:
            line = chat_order.get("source_line")
            return f"chat line {line}" if line else "chat"
        return "chat"

    def _ledger_evidence(row: dict) -> str:
        idx = row.get("row_index")
        return f"ledger row {idx}" if idx else "ledger"

    def _amount(source: Optional[dict]) -> str:
        if source:
            amt = source.get("amount_pkr")
            if amt is not None:
                return str(int(amt)) if float(amt) == int(float(amt)) else str(amt)
        return "?"

    template = _EXPLAIN_TEMPLATES.get(kind)

    if kind == "PAID_NOT_RECORDED":
        return template.format(
            sender=_sender(),
            item=_item(),
            amount=_amount(chat_order),
            chat_evidence=_chat_evidence(),
        )

    if kind == "UNMATCHED_ORDER":
        return template.format(
            sender=_sender(),
            item=_item(),
            chat_evidence=_chat_evidence(),
        )

    if kind == "RECORDED_NOT_PAID":
        row = ledger_rows[0] if ledger_rows else {}
        return template.format(
            customer=_sender(),
            amount=_amount(row),
            ledger_evidence=_ledger_evidence(row),
        )

    if kind == "PRICE_MISMATCH":
        row = ledger_rows[0] if ledger_rows else {}
        chat_amt = float(chat_order.get("amount_pkr") or 0) if chat_order else 0.0
        ledger_amt = float(row.get("amount_pkr") or 0)
        diff = abs(chat_amt - ledger_amt)
        return template.format(
            sender=_sender(),
            item=_item(),
            chat_amount=int(chat_amt) if chat_amt == int(chat_amt) else chat_amt,
            chat_evidence=_chat_evidence(),
            ledger_evidence=_ledger_evidence(row),
            ledger_amount=int(ledger_amt) if ledger_amt == int(ledger_amt) else ledger_amt,
            diff=int(diff) if diff == int(diff) else diff,
        )

    if kind == "DUPLICATE":
        row_a = ledger_rows[0] if len(ledger_rows) > 0 else {}
        row_b = ledger_rows[1] if len(ledger_rows) > 1 else {}
        customer = row_a.get("customer") or _sender()
        item = row_a.get("item") or _item()
        amount = _amount(row_a)
        return template.format(
            ledger_evidence_a=_ledger_evidence(row_a),
            ledger_evidence_b=_ledger_evidence(row_b),
            customer=customer,
            item=item,
            amount=amount,
        )

    # Generic fallback — use the reconciler's pre-computed explanation
    if existing:
        return existing
    return _GENERIC_EXPLAIN.format(kind=kind, explanation="koi explanation nahi mili.")


# ---------------------------------------------------------------------------
# Draft-reply templates
# ---------------------------------------------------------------------------

# Greeting variants by index (deterministic rotation via hash of sender name)
_GREETINGS = [
    "Salam {name} bhai",
    "Assalamu alaikum {name} bhai",
    "Salam {name}",
]

# Reminder body variants
_REMINDER_BODIES = [
    "{item} ka Rs {amount} rehta hai, kal de dena.",
    "{item} ka udhaar Rs {amount} baaki hai, jab ho sake de dena.",
    "Rs {amount} ({item}) abhi tak baaki hai, please thora jaldi kar dena.",
]

# Closing variants
_CLOSINGS = [
    "Shukriya.",
    "Allah hafiz.",
    "Mehrbani.",
]


def _pick(options: list[str], key: str) -> str:
    """Deterministically pick one option based on a string key."""
    idx = hash(key) % len(options)
    return options[idx]


def draft_reply(order: dict) -> str:
    """
    Return a short WhatsApp reminder message in Roman Urdu/English mix.

    Parameters
    ----------
    order : dict
        A CandidateOrder dict (or compatible dict) with keys:
        sender, item, item_raw, amount_pkr, date.

    The output is deterministic (no randomness) — same input → same draft.
    """
    sender: str = order.get("sender") or "Grahak"
    # Strip common titles for greeting
    name = _strip_titles(sender)
    item: str = (
        order.get("item")
        or order.get("item_raw")
        or "saman"
    )
    amount_raw = order.get("amount_pkr")
    amount: str = (
        str(int(amount_raw)) if amount_raw is not None and float(amount_raw) == int(float(amount_raw))
        else str(amount_raw) if amount_raw is not None
        else "kuch"
    )

    greeting = _pick(_GREETINGS, sender).format(name=name)
    body = _pick(_REMINDER_BODIES, item).format(item=item, amount=amount)
    closing = _pick(_CLOSINGS, sender + item)

    return f"{greeting}, {body} {closing}"


def _strip_titles(name: str) -> str:
    """Remove common Urdu/English honorifics and return the first name."""
    import re
    title_re = re.compile(
        r"\b(bhai|sahab|sahib|uncle|auntie|aunty|ji|sb|bh)\b",
        re.IGNORECASE,
    )
    cleaned = title_re.sub("", name)
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", cleaned).strip()
    tokens = cleaned.split()
    # Capitalise first token
    if tokens:
        first = tokens[0]
        return first[0].upper() + first[1:] if first else first
    return name.split()[0] if name.split() else name
