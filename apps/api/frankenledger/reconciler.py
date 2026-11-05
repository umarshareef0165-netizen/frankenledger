"""
FrankenLedger — deterministic reconciler, Spec 03.
Pure functions, stdlib only (datetime, re, copy, uuid).

Pipeline:
  1. Normalise customer names + item keywords.
  2. One-to-one matcher: same customer + item + date±1d + amount±Rs10.
  3. Identify payment events (chat orders with no item, paid status) and
     use them to mark matched chat orders as paid before flag generation.
  4. Generate flags in spec order:
       PAID_NOT_RECORDED, UNMATCHED_ORDER, RECORDED_NOT_PAID,
       PRICE_MISMATCH, DUPLICATE.
  5. Fix actions: accept / edit / dismiss; totals recompute after every fix.
  6. The original ledger is never mutated.
"""
from __future__ import annotations

import copy
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from .models import CandidateOrder, LedgerRow, PaymentStatus

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

# Titles to strip from customer names
_TITLE_RE = re.compile(
    r"\b(bhai|sahab|sahib|uncle|auntie|aunty|ji|sb|bh)\b",
    re.IGNORECASE,
)


def normalise_name(name: Optional[str]) -> str:
    """Lowercase, strip titles, take first token, strip punctuation."""
    if not name:
        return ""
    cleaned = _TITLE_RE.sub("", name)
    cleaned = re.sub(r"[^a-z0-9\s]", "", cleaned.lower())
    tokens = cleaned.split()
    return tokens[0] if tokens else ""


# Item catalogue keyword list — same as parser
_ITEM_CATALOGUE = {
    "cheeni", "atta", "chawal", "doodh", "anda",
    "chai", "ghee", "daal", "namak", "sabun",
}

# Alias → canonical (duplicates the parser catalogue for independence)
_ITEM_ALIASES: dict[str, str] = {
    "cheeni": "cheeni", "chini": "cheeni", "sugar": "cheeni",
    "atta": "atta", "flour": "atta",
    "chawal": "chawal", "rice": "chawal",
    "doodh": "doodh", "dudh": "doodh", "milk": "doodh",
    "anda": "anda", "egg": "anda", "eggs": "anda", "anday": "anda",
    "chai": "chai", "tea": "chai",
    "ghee": "ghee",
    "daal": "daal", "dal": "daal", "lentil": "daal", "lentils": "daal",
    "namak": "namak", "salt": "namak",
    "sabun": "sabun", "soap": "sabun",
}


def normalise_item(item: Optional[str]) -> Optional[str]:
    """Return canonical catalogue keyword, or the raw keyword lowercased."""
    if not item:
        return None
    lower = item.strip().lower()
    return _ITEM_ALIASES.get(lower, lower)


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse ISO (YYYY-MM-DD) or DD/MM/YYYY to a date object."""
    if not date_str:
        return None
    s = date_str.strip()
    # Try ISO first
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    # Try DD/MM/YYYY
    parts = re.split(r"[/\-]", s)
    if len(parts) == 3:
        try:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            if d > 12:
                return date(y, m, d)
            # DD/MM/YYYY assumption (WhatsApp default)
            return date(y, m, d)
        except (ValueError, TypeError):
            pass
    return None


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

class FlagKind:
    PAID_NOT_RECORDED = "PAID_NOT_RECORDED"
    UNMATCHED_ORDER   = "UNMATCHED_ORDER"
    RECORDED_NOT_PAID = "RECORDED_NOT_PAID"
    PRICE_MISMATCH    = "PRICE_MISMATCH"
    DUPLICATE         = "DUPLICATE"


@dataclass
class Flag:
    flag_id: str
    kind: str
    chat_order: Optional[CandidateOrder]
    ledger_rows: list[LedgerRow]           # one or more involved rows
    explanation: str
    # Proposed fix description (human-readable)
    fix_description: str
    dismissed: bool = False


@dataclass
class Totals:
    sold: float          # sum of all ledger-row amounts
    received: float      # sum of paid=True rows
    outstanding: float   # udhaar = sold - received


@dataclass
class ReconciledLedger:
    rows: list[LedgerRow]
    flags: list[Flag]
    totals: Totals

    def active_flags(self) -> list[Flag]:
        """Flags not yet dismissed."""
        return [f for f in self.flags if not f.dismissed]


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------

def _match_score(
    order: CandidateOrder,
    row: LedgerRow,
) -> Optional[int]:
    """
    Return a match score >= 0 if customer+item match AND date within ±1 day
    AND amount within Rs 10, else None.
    Higher = better match. 0 is the worst passing score.
    """
    # Customer
    o_name = normalise_name(order.sender)
    r_name = normalise_name(row.customer)
    if not o_name or not r_name:
        return None
    if o_name != r_name:
        return None

    # Item
    o_item = normalise_item(order.item)
    r_item = normalise_item(row.item)
    if o_item is None or r_item is None:
        return None
    if o_item != r_item:
        return None

    # Date
    o_date = _parse_date(order.date)
    r_date = _parse_date(row.date)
    if o_date is None and r_date is None:
        date_score = 0
        date_diff = 0
    elif o_date is None or r_date is None:
        return None
    else:
        date_diff = abs((o_date - r_date).days)
        if date_diff > 1:
            return None
        date_score = 1 if date_diff == 0 else 0

    # Amount (allow None amounts — count as within tolerance but lower score)
    o_amt = order.amount_pkr
    r_amt = row.amount_pkr
    if o_amt is not None and r_amt is not None:
        amt_diff = abs(o_amt - r_amt)
        if amt_diff > 10:
            # Still a candidate for PRICE_MISMATCH; we return special score -1
            # to mark "name+item+date match but amount diffs"
            return -1
        amt_score = 2 if amt_diff == 0 else 1
    else:
        amt_score = 0

    return date_score * 10 + amt_score


_PRICE_MISMATCH_SCORE = -1  # sentinel


def match_orders_to_rows(
    orders: list[CandidateOrder],
    rows: list[LedgerRow],
) -> tuple[
    dict[int, int],      # order_index -> row_index (exact/near matches)
    dict[int, int],      # order_index -> row_index (price-mismatch matches)
    dict[int, list[int]],# row_index -> [order_indices] (for duplicate detection)
]:
    """
    One-to-one greedy matcher (best score wins).
    Returns:
      matched:        order_idx -> row_idx   (amount within Rs 10)
      price_mismatch: order_idx -> row_idx   (name+item+date match, amount diff > Rs 10)
      row_to_orders:  row_idx   -> [order_idxs]  (for duplicate detection)
    """
    # Build all candidate (order, row, score) triples
    candidates: list[tuple[int, int, int]] = []
    for oi, order in enumerate(orders):
        for ri, row in enumerate(rows):
            score = _match_score(order, row)
            if score is not None:
                candidates.append((oi, ri, score))

    # Sort: exact matches (score > 0) first, then price-mismatch (-1) last
    candidates.sort(key=lambda x: x[2], reverse=True)

    matched: dict[int, int] = {}         # order_idx -> row_idx
    price_mismatch: dict[int, int] = {}  # order_idx -> row_idx
    used_orders: set[int] = set()
    used_rows: set[int] = set()

    # First pass: assign exact/near matches (score >= 0)
    for oi, ri, score in candidates:
        if score < 0:
            continue
        if oi in used_orders or ri in used_rows:
            continue
        matched[oi] = ri
        used_orders.add(oi)
        used_rows.add(ri)

    # Second pass: price-mismatch — only for unmatched orders/rows
    for oi, ri, score in candidates:
        if score != _PRICE_MISMATCH_SCORE:
            continue
        if oi in used_orders or ri in used_rows:
            continue
        price_mismatch[oi] = ri
        used_orders.add(oi)
        used_rows.add(ri)

    # row_to_orders: multiple orders pointing to same row → duplicate signal
    row_to_orders: dict[int, list[int]] = {}
    for oi, ri in {**matched, **price_mismatch}.items():
        row_to_orders.setdefault(ri, []).append(oi)

    return matched, price_mismatch, row_to_orders


# ---------------------------------------------------------------------------
# Payment-event resolution
# ---------------------------------------------------------------------------

def _resolve_payment_events(
    orders: list[CandidateOrder],
) -> tuple[list[CandidateOrder], set[int]]:
    """
    Identify payment events (paid status, no item) and use each one to mark
    the best-matching open (udhaar/unknown) chat order from the same sender
    with the same amount (within Rs 10) as paid.

    Returns:
      orders_resolved: copy of orders list with payment-event targets marked paid
      payment_event_indices: set of order indices that ARE payment events (to exclude
                             from flag generation)
    """
    orders_resolved = list(orders)  # shallow copy — we'll replace entries
    payment_event_indices: set[int] = set()

    for ei, event in enumerate(orders):
        # A payment event: paid status AND no catalogue item
        if event.payment_status != PaymentStatus.paid:
            continue
        if event.item is not None:
            continue  # has an item → regular order, not a payment event

        e_name = normalise_name(event.sender)
        e_amt = event.amount_pkr
        if e_amt is None:
            continue

        # Find the best matching open order from same sender with same amount
        best_idx: Optional[int] = None
        for oi, order in enumerate(orders_resolved):
            if oi == ei:
                continue
            if order.payment_status == PaymentStatus.paid:
                continue  # already paid
            if normalise_name(order.sender) != e_name:
                continue
            if order.amount_pkr is None:
                continue
            if abs(order.amount_pkr - e_amt) > 10:
                continue
            # Pick the most recent open order (closest date to event)
            e_date = _parse_date(event.date)
            o_date = _parse_date(order.date)
            if e_date and o_date and o_date > e_date:
                continue  # can't pay for a future order
            best_idx = oi
            break  # take first qualifying match

        if best_idx is not None:
            # Mark the target order as paid (create a new copy to avoid mutation)
            original = orders_resolved[best_idx]
            updated = CandidateOrder(
                date=original.date,
                sender=original.sender,
                item=original.item,
                item_raw=original.item_raw,
                quantity=original.quantity,
                unit=original.unit,
                amount_pkr=original.amount_pkr,
                payment_status=PaymentStatus.paid,
                source_line=original.source_line,
                confidence=original.confidence,
            )
            orders_resolved[best_idx] = updated
            payment_event_indices.add(ei)

    return orders_resolved, payment_event_indices


# ---------------------------------------------------------------------------
# Flag generation
# ---------------------------------------------------------------------------

def _make_id() -> str:
    return str(uuid.uuid4())


def _chat_evidence(order: CandidateOrder) -> str:
    return f"chat line {order.source_line}"


def _ledger_evidence(row: LedgerRow) -> str:
    return f"ledger row {row.row_index}"


def generate_flags(
    orders: list[CandidateOrder],
    rows: list[LedgerRow],
    matched: dict[int, int],
    price_mismatch: dict[int, int],
    payment_event_indices: set[int],
) -> list[Flag]:
    """
    Generate flags in spec order. Payment-event orders are excluded.
    """
    flags: list[Flag] = []
    matched_order_idxs = set(matched.keys())
    matched_row_idxs   = set(matched.values())
    pm_order_idxs      = set(price_mismatch.keys())
    pm_row_idxs        = set(price_mismatch.values())
    all_matched_order  = matched_order_idxs | pm_order_idxs | payment_event_indices
    all_matched_row    = matched_row_idxs | pm_row_idxs

    # -------------------------------------------------------------------------
    # 1. PAID_NOT_RECORDED — chat paid, no ledger row
    # -------------------------------------------------------------------------
    for oi, order in enumerate(orders):
        if oi in all_matched_order:
            continue
        if order.payment_status != PaymentStatus.paid:
            continue
        flags.append(Flag(
            flag_id=_make_id(),
            kind=FlagKind.PAID_NOT_RECORDED,
            chat_order=order,
            ledger_rows=[],
            explanation=(
                f"{order.sender} paid "
                f"Rs {order.amount_pkr or '?'} for {order.item or order.item_raw or '?'} "
                f"({_chat_evidence(order)}) but no matching ledger row exists."
            ),
            fix_description="Add a new paid ledger row for this order.",
        ))

    # -------------------------------------------------------------------------
    # 2. UNMATCHED_ORDER — chat unpaid/unknown, no ledger row
    # -------------------------------------------------------------------------
    for oi, order in enumerate(orders):
        if oi in all_matched_order:
            continue
        if order.payment_status == PaymentStatus.paid:
            continue  # already handled above
        flags.append(Flag(
            flag_id=_make_id(),
            kind=FlagKind.UNMATCHED_ORDER,
            chat_order=order,
            ledger_rows=[],
            explanation=(
                f"{order.sender} ordered "
                f"{order.item or order.item_raw or '?'} "
                f"({_chat_evidence(order)}) with no ledger row."
            ),
            fix_description="Add a new udhaar ledger row for this order.",
        ))

    # -------------------------------------------------------------------------
    # 3. RECORDED_NOT_PAID — ledger row paid/received, no matching chat order
    #    OR ledger says paid but matched chat order says unpaid
    # -------------------------------------------------------------------------
    for ri, row in enumerate(rows):
        if ri not in all_matched_row:
            # No chat order at all
            if row.paid:
                flags.append(Flag(
                    flag_id=_make_id(),
                    kind=FlagKind.RECORDED_NOT_PAID,
                    chat_order=None,
                    ledger_rows=[row],
                    explanation=(
                        f"Ledger row {row.row_index} shows {row.customer} "
                        f"paid Rs {row.amount_pkr or '?'} for {row.item or '?'}, "
                        f"but no chat order matches."
                    ),
                    fix_description="Keep row — no chat evidence. Verify or dismiss.",
                ))
        else:
            # Has a matched chat order — check for paid-status mismatch
            # Find which order is matched to this row
            order_idx = None
            for oi, ridx in {**matched, **price_mismatch}.items():
                if ridx == ri:
                    order_idx = oi
                    break
            if order_idx is None:
                continue
            order = orders[order_idx]
            # Ledger says paid but chat says unpaid/udhaar
            if row.paid and order.payment_status in (
                PaymentStatus.udhaar, PaymentStatus.unknown,
            ):
                flags.append(Flag(
                    flag_id=_make_id(),
                    kind=FlagKind.RECORDED_NOT_PAID,
                    chat_order=order,
                    ledger_rows=[row],
                    explanation=(
                        f"Ledger row {row.row_index} marks {row.customer} as paid "
                        f"(Rs {row.amount_pkr or '?'} for {row.item or '?'}), "
                        f"but {_chat_evidence(order)} shows no payment confirmed."
                    ),
                    fix_description="Verify: mark as udhaar or dismiss if paid outside chat.",
                ))

    # -------------------------------------------------------------------------
    # 4. PRICE_MISMATCH — matched pair, amounts differ > Rs 10
    # -------------------------------------------------------------------------
    for oi, ri in price_mismatch.items():
        order = orders[oi]
        row = rows[ri]
        o_amt = order.amount_pkr or 0.0
        r_amt = row.amount_pkr or 0.0
        flags.append(Flag(
            flag_id=_make_id(),
            kind=FlagKind.PRICE_MISMATCH,
            chat_order=order,
            ledger_rows=[row],
            explanation=(
                f"{order.sender} {order.item or '?'}: chat shows Rs {o_amt} "
                f"({_chat_evidence(order)}) but "
                f"{_ledger_evidence(row)} shows Rs {r_amt}. "
                f"Difference: Rs {abs(o_amt - r_amt):.0f}."
            ),
            fix_description="Choose chat amount or ledger amount.",
        ))

    # -------------------------------------------------------------------------
    # 5. DUPLICATE — two ledger rows match one chat order
    # -------------------------------------------------------------------------
    # Find rows that were matched by the same chat order
    # (we need to re-examine unmatched rows that have a near-twin)
    seen_pairs: set[frozenset] = set()
    for ri in range(len(rows)):
        for ri2 in range(ri + 1, len(rows)):
            row_a, row_b = rows[ri], rows[ri2]
            pair = frozenset([ri, ri2])
            if pair in seen_pairs:
                continue
            # Same customer + item + similar date + similar amount
            if normalise_name(row_a.customer) != normalise_name(row_b.customer):
                continue
            if normalise_item(row_a.item) != normalise_item(row_b.item):
                continue
            if normalise_item(row_a.item) is None:
                continue
            date_a = _parse_date(row_a.date)
            date_b = _parse_date(row_b.date)
            if date_a and date_b and abs((date_a - date_b).days) > 1:
                continue
            amt_a = row_a.amount_pkr or 0.0
            amt_b = row_b.amount_pkr or 0.0
            if abs(amt_a - amt_b) > 10:
                continue
            seen_pairs.add(pair)
            # Find a chat order that matches either row
            linked_order: Optional[CandidateOrder] = None
            for oi, ridx in {**matched, **price_mismatch}.items():
                if ridx in (ri, ri2):
                    linked_order = orders[oi]
                    break
            flags.append(Flag(
                flag_id=_make_id(),
                kind=FlagKind.DUPLICATE,
                chat_order=linked_order,
                ledger_rows=[row_a, row_b],
                explanation=(
                    f"Two ledger rows ({_ledger_evidence(row_a)} and "
                    f"{_ledger_evidence(row_b)}) both record {row_a.customer} "
                    f"{row_a.item or '?'} Rs {amt_a} on ~{row_a.date}. "
                    + (f"Linked to {_chat_evidence(linked_order)}."
                       if linked_order else "No matching chat order.")
                ),
                fix_description="Keep first row; mark second as duplicate.",
            ))

    return flags


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------

def compute_totals(rows: list[LedgerRow]) -> Totals:
    sold = sum(r.amount_pkr or 0.0 for r in rows)
    received = sum(r.amount_pkr or 0.0 for r in rows if r.paid)
    return Totals(sold=sold, received=received, outstanding=sold - received)


# ---------------------------------------------------------------------------
# Main reconcile entry point
# ---------------------------------------------------------------------------

def reconcile(
    orders: list[CandidateOrder],
    ledger_rows: list[LedgerRow],
) -> ReconciledLedger:
    """
    Run the full reconciliation pipeline.

    The original ledger_rows list is NEVER mutated.
    Returns a new ReconciledLedger with a deep-copied row list.
    """
    # Deep-copy rows so the original is never mutated
    rows = copy.deepcopy(ledger_rows)

    # Step 1: resolve payment events (marks matched orders as paid in a copy)
    orders_resolved, payment_event_indices = _resolve_payment_events(orders)

    # Step 2: match
    matched, price_mismatch, _ = match_orders_to_rows(orders_resolved, rows)

    # Step 3: generate flags
    flags = generate_flags(
        orders_resolved, rows, matched, price_mismatch, payment_event_indices
    )

    # Step 4: totals
    totals = compute_totals(rows)

    return ReconciledLedger(rows=rows, flags=flags, totals=totals)


# ---------------------------------------------------------------------------
# Fix actions
# ---------------------------------------------------------------------------

def apply_fix(
    reconciled: ReconciledLedger,
    flag_id: str,
    action: str,                     # "accept" | "edit" | "dismiss"
    patch: Optional[dict] = None,    # for "edit": {"amount_pkr": ..., "paid": ...}
) -> ReconciledLedger:
    """
    Apply a fix to a copy of the reconciled ledger.
    The original ReconciledLedger is NEVER mutated.
    Returns a NEW ReconciledLedger.

    Actions:
      accept  — apply the default fix for this flag kind to the reconciled rows.
      edit    — apply patch values to the relevant row, then accept.
      dismiss — mark flag as dismissed (hidden, logged, never deleted).
    """
    # Work on a deep copy
    new_rows = copy.deepcopy(reconciled.rows)
    new_flags = copy.deepcopy(reconciled.flags)

    target_flag: Optional[Flag] = None
    for f in new_flags:
        if f.flag_id == flag_id:
            target_flag = f
            break

    if target_flag is None:
        raise ValueError(f"Flag {flag_id!r} not found.")

    if action == "dismiss":
        target_flag.dismissed = True
        new_totals = compute_totals(new_rows)
        return ReconciledLedger(rows=new_rows, flags=new_flags, totals=new_totals)

    # --- apply edit patch first ---
    if action == "edit" and patch:
        for row in new_rows:
            is_involved = any(
                lr.row_index == row.row_index for lr in target_flag.ledger_rows
            )
            if not is_involved:
                continue
            if "amount_pkr" in patch:
                row.amount_pkr = float(patch["amount_pkr"])
            if "paid" in patch:
                row.paid = bool(patch["paid"])
        # For "edit", the patch IS the user's custom fix.
        # Skip the default per-kind action so the patch is not overwritten.
        target_flag.dismissed = True
        new_totals = compute_totals(new_rows)
        return ReconciledLedger(rows=new_rows, flags=new_flags, totals=new_totals)

    # --- apply default fix per flag kind (for "accept" only) ---
    kind = target_flag.kind

    if kind == FlagKind.PAID_NOT_RECORDED:
        # Add a new ledger row for the chat order
        order = target_flag.chat_order
        if order:
            new_row_index = max((r.row_index for r in new_rows), default=0) + 1
            new_row = LedgerRow(
                row_index=new_row_index,
                date=order.date,
                customer=order.sender,
                item=order.item or order.item_raw,
                quantity=str(order.quantity) + " " + (order.unit or "") if order.quantity else None,
                amount_pkr=order.amount_pkr,
                paid=True,
                raw={"source": f"chat:line {order.source_line}"},
            )
            new_rows.append(new_row)

    elif kind == FlagKind.UNMATCHED_ORDER:
        # Add a new ledger row as udhaar
        order = target_flag.chat_order
        if order:
            new_row_index = max((r.row_index for r in new_rows), default=0) + 1
            new_row = LedgerRow(
                row_index=new_row_index,
                date=order.date,
                customer=order.sender,
                item=order.item or order.item_raw,
                quantity=str(order.quantity) + " " + (order.unit or "") if order.quantity else None,
                amount_pkr=order.amount_pkr,
                paid=False,
                raw={"source": f"chat:line {order.source_line}"},
            )
            new_rows.append(new_row)

    elif kind == FlagKind.RECORDED_NOT_PAID:
        # Mark the ledger row as udhaar (not paid)
        for row in new_rows:
            if any(lr.row_index == row.row_index for lr in target_flag.ledger_rows):
                row.paid = False

    elif kind == FlagKind.PRICE_MISMATCH:
        # Default: use the chat amount (most trusted source is evidence)
        order = target_flag.chat_order
        if order and order.amount_pkr is not None:
            for row in new_rows:
                if any(lr.row_index == row.row_index for lr in target_flag.ledger_rows):
                    row.amount_pkr = order.amount_pkr

    elif kind == FlagKind.DUPLICATE:
        # Mark all rows after the first as duplicates (paid=False, raw note)
        involved_rows = sorted(target_flag.ledger_rows, key=lambda r: r.row_index)
        for row in new_rows:
            is_dup = any(
                lr.row_index == row.row_index for lr in involved_rows[1:]
            )
            if is_dup:
                row.paid = False
                row.raw = {**row.raw, "note": "DUPLICATE — marked inactive"}

    # Mark the flag resolved (dismissed after fix)
    target_flag.dismissed = True

    new_totals = compute_totals(new_rows)
    return ReconciledLedger(rows=new_rows, flags=new_flags, totals=new_totals)
