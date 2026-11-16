"""
tests/test_properties.py — Property-based tests for the FrankenLedger
parser (Spec 02) and reconciler (Spec 03).

Method: seeded pseudo-random generation with the stdlib `random` module
only — no Hypothesis dependency (the API requirements list stdlib only,
and the build VM has no network install of test-only packages baked in).
Each property runs N generated cases from a fixed seed, so every run is
reproducible: the same seed always generates the same cases.

What "property-based" means here: instead of one hand-picked example per
behaviour, each test asserts an INVARIANT that must hold for every
generated input (e.g. "a parsed Rs amount is always exactly the amount
written in the line", "reconcile() never mutates its input rows",
"totals always satisfy outstanding == sold - received").

Run from apps/api/:
    /tmp/fl-venv/bin/python -m pytest tests/test_properties.py -v
(or any python with pytest installed; see apps/api/requirements.txt)

Seed policy: one fixed seed per property, recorded in the test name, so a
failure can be reproduced exactly by re-running the same test.
"""
from __future__ import annotations

import copy
import pathlib
import random
import string
import sys

# Allow importing from apps/api without installing the package
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps" / "api"))

from frankenledger.models import CandidateOrder, Confidence, LedgerRow, PaymentStatus
from frankenledger.parser import parse_chat
from frankenledger.reconciler import (
    FlagKind,
    apply_fix,
    compute_totals,
    match_orders_to_rows,
    reconcile,
)

# ---------------------------------------------------------------------------
# Generators (seeded, deterministic)
# ---------------------------------------------------------------------------

_ITEMS = [
    ("cheeni", ["cheeni", "chini", "sugar"]),
    ("atta", ["atta", "flour"]),
    ("chawal", ["chawal", "rice"]),
    ("doodh", ["doodh", "dudh", "milk"]),
    ("anda", ["anda", "egg", "eggs", "anday"]),
    ("chai", ["chai", "tea"]),
    ("ghee", ["ghee"]),
    ("daal", ["daal", "dal", "lentil"]),
    ("namak", ["namak", "salt"]),
    ("sabun", ["sabun", "soap"]),
]
_ALL_ALIASES = [a for _, aliases in _ITEMS for a in aliases]
_CANONICAL = [c for c, _ in _ITEMS]
_UNITS = ["kg", "g", "packet", "darjan", "litre", "piece", "bottle"]
_SENDERS = ["Ali", "Ahmed", "Bilal", "Fatima", "Hassan", "Ayesha", "Usman", "Zara"]
_WORD_NUM = ["ek", "do", "teen", "chaar", "paanch", "chhay", "saat", "aath", "nau", "das"]


def _rand_date(rng: random.Random) -> str:
    """A valid DD/MM/YYYY date in Nov 2026 (WhatsApp default format)."""
    day = rng.randint(1, 28)
    return f"{day:02d}/11/2026"


def _rand_line(rng: random.Random) -> tuple[str, dict]:
    """One generated valid WhatsApp order line + the ground truth it encodes."""
    canonical, aliases = rng.choice(_ITEMS)
    alias = rng.choice(aliases)
    sender = rng.choice(_SENDERS)
    date = _rand_date(rng)
    hour = rng.randint(1, 12)
    minute = rng.randint(0, 59)
    ampm = rng.choice(["AM", "PM"])
    # Quantity: digit + unit, or Roman-Urdu word + unit
    if rng.random() < 0.5:
        qty = rng.choice([1, 2, 3, 5, 10])
        qty_text = f"{qty}"
        qty_val = float(qty)
    else:
        word = rng.choice(_WORD_NUM[:5])
        qty_text = word
        qty_val = float(_WORD_NUM.index(word) + 1)
    unit = rng.choice(_UNITS)
    amount = rng.choice([50, 100, 150, 200, 250, 300, 500, 750, 1000, 1250])
    pay_word = rng.choice(["paid", "de diye", "udhaar", "kal dunga", ""])
    pay_status = (
        PaymentStatus.paid
        if pay_word in ("paid", "de diye")
        else PaymentStatus.udhaar
        if pay_word in ("udhaar", "kal dunga")
        else PaymentStatus.unknown
    )
    text = f"{qty_text} {unit} {alias} Rs {amount}"
    if pay_word:
        text += f" {pay_word}"
    line = f"{date}, {hour}:{minute:02d} {ampm} - {sender}: {text}"
    truth = {
        "canonical": canonical,
        "sender": sender,
        "qty": qty_val,
        "unit": unit,
        "amount": float(amount),
        "payment": pay_status,
    }
    return line, truth


def _rand_order(rng: random.Random, **overrides) -> CandidateOrder:
    canonical = rng.choice(_CANONICAL)
    kw = {
        "date": "2026-11-05",
        "sender": rng.choice(_SENDERS),
        "item": canonical,
        "item_raw": None,
        "quantity": 2.0,
        "unit": "kg",
        "amount_pkr": 500.0,
        "payment_status": PaymentStatus.paid,
        "source_line": 1,
        "confidence": Confidence.high,
    }
    kw.update(overrides)
    return CandidateOrder(**kw)


def _rand_row(rng: random.Random, **overrides) -> LedgerRow:
    kw = {
        "row_index": 1,
        "date": "2026-11-05",
        "customer": rng.choice(_SENDERS),
        "item": rng.choice(_CANONICAL),
        "quantity": "2 kg",
        "amount_pkr": 500.0,
        "paid": True,
        "raw": {},
    }
    kw.update(overrides)
    return LedgerRow(**kw)


# ---------------------------------------------------------------------------
# Parser properties
# ---------------------------------------------------------------------------

def test_prop_parser_deterministic_and_exact_amount():
    """P1/P2: parsing is deterministic, and an explicit Rs amount is exact."""
    rng = random.Random(20261112)
    for _ in range(200):
        lines, truths = [], []
        for _ in range(rng.randint(1, 8)):
            line, truth = _rand_line(rng)
            lines.append(line)
            truths.append(truth)
        text = "\n".join(lines)
        first = parse_chat(text)
        second = parse_chat(text)
        # P1 — determinism: identical orders on re-parse
        assert len(first.orders) == len(second.orders)
        for a, b in zip(first.orders, second.orders):
            assert a == b
        # P2 — every generated order is found, with its exact amount
        assert len(first.orders) == len(lines), (
            f"expected one order per line, got {len(first.orders)} from {len(lines)}"
        )
        for order, truth in zip(first.orders, truths):
            assert order.amount_pkr == truth["amount"], (
                f"amount {order.amount_pkr} != written {truth['amount']} in {lines}"
            )


def test_prop_parser_quantity_unit_item():
    """P3: digit/word quantity + unit + catalogue alias round-trip exactly."""
    rng = random.Random(20261113)
    for _ in range(200):
        line, truth = _rand_line(rng)
        orders = parse_chat(line).orders
        assert len(orders) == 1
        o = orders[0]
        assert o.quantity == truth["qty"], f"{line!r} -> qty {o.quantity}"
        assert o.unit == truth["unit"], f"{line!r} -> unit {o.unit}"
        assert o.item == truth["canonical"], f"{line!r} -> item {o.item}"
        assert o.sender == truth["sender"]
        assert o.payment_status == truth["payment"]


def test_prop_parser_payment_classification():
    """P4: 'paid'/'de diye' -> paid; 'udhaar'/'kal dunga' -> udhaar."""
    rng = random.Random(20261114)
    cases = [
        ("paid", PaymentStatus.paid),
        ("de diye", PaymentStatus.paid),
        ("udhaar", PaymentStatus.udhaar),
        ("kal dunga", PaymentStatus.udhaar),
    ]
    for _ in range(100):
        word, expected = rng.choice(cases)
        canonical, aliases = rng.choice(_ITEMS)
        line = f"05/11/2026, 10:30 AM - Ali: 2 kg {rng.choice(aliases)} Rs 500 {word}"
        orders = parse_chat(line).orders
        assert len(orders) == 1
        assert orders[0].payment_status == expected, f"{line!r}"


def test_prop_parser_shop_sender_never_orders():
    """P5: lines sent by the shop itself never produce an order."""
    rng = random.Random(20261115)
    shop_names = ["Noor General Store", "My Shop", "Super Store", "Corner Shop"]
    for _ in range(100):
        sender = rng.choice(shop_names)
        line = f"05/11/2026, 10:30 AM - {sender}: 2 kg cheeni Rs 500 paid"
        result = parse_chat(line)
        assert result.orders == [], f"shop line produced orders: {line!r}"
        assert result.parsed_line_count == 1  # still counted as parsed


def test_prop_parser_media_lines_counted_not_orders():
    """P6: media/voice-note lines count as voice notes, never as orders."""
    rng = random.Random(20261116)
    placeholders = ["<Media omitted>", "voice message", "image omitted", "audio omitted"]
    for _ in range(100):
        ph = rng.choice(placeholders)
        line = f"05/11/2026, 10:30 AM - Ali: {ph}"
        result = parse_chat(line)
        assert result.orders == []
        assert result.voice_note_count == 1, f"{line!r}"


def test_prop_parser_never_crashes_on_garbage():
    """P7: arbitrary garbage lines never raise; line accounting always adds up."""
    rng = random.Random(20261117)
    alphabet = string.printable[:-6]  # exclude \t\n\r\x0b\x0c
    for _ in range(200):
        n = rng.randint(1, 10)
        lines = [
            "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 60)))
            for _ in range(n)
        ]
        # Skip blank / comment lines: the parser skips those silently, and
        # the accounting property only covers lines it actually processes.
        lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        if not lines:
            continue
        result = parse_chat("\n".join(lines))
        assert result.parsed_line_count + result.unparsed_count == len(lines)
        assert len(result.orders) <= result.parsed_line_count
        # source lines are 1-based, in range, and unique (<=1 order per line)
        srcs = [o.source_line for o in result.orders]
        assert len(srcs) == len(set(srcs))
        assert all(1 <= s <= len(lines) for s in srcs)


def test_prop_parser_full_signal_means_high_confidence():
    """P9: item + quantity + amount in one line -> high confidence."""
    rng = random.Random(20261118)
    for _ in range(100):
        line, _ = _rand_line(rng)
        orders = parse_chat(line).orders
        assert len(orders) == 1
        assert orders[0].confidence == Confidence.high, f"{line!r}"


# ---------------------------------------------------------------------------
# Reconciler properties
# ---------------------------------------------------------------------------

def test_prop_reconciler_totals_invariant():
    """R1: sold == sum(amounts); received == sum(paid); outstanding == sold - received."""
    rng = random.Random(20261119)
    for _ in range(200):
        rows = [
            _rand_row(rng, row_index=i + 1, amount_pkr=float(rng.choice([0, 50, 100, 500, 999])),
                      paid=rng.random() < 0.5)
            for i in range(rng.randint(0, 10))
        ]
        totals = compute_totals(rows)
        sold = sum(r.amount_pkr or 0.0 for r in rows)
        received = sum(r.amount_pkr or 0.0 for r in rows if r.paid)
        assert totals.sold == sold
        assert totals.received == received
        assert totals.outstanding == sold - received
        assert totals.received <= totals.sold  # amounts are non-negative


def test_prop_reconciler_never_mutates_input():
    """R2: reconcile() never mutates the caller's ledger rows (or orders)."""
    rng = random.Random(20261120)
    for _ in range(100):
        rows = [_rand_row(rng, row_index=i + 1) for i in range(rng.randint(1, 5))]
        orders = [_rand_order(rng, source_line=i + 1) for i in range(rng.randint(1, 5))]
        rows_before = copy.deepcopy(rows)
        orders_before = copy.deepcopy(orders)
        reconcile(orders, rows)
        assert rows == rows_before, "reconcile() mutated the input rows"
        assert orders == orders_before, "reconcile() mutated the input orders"


def test_prop_reconciler_exact_paid_pair_has_no_flags():
    """R3: identical paid order + paid row (same name/item/date/amount) -> zero flags."""
    rng = random.Random(20261121)
    for _ in range(100):
        sender = rng.choice(_SENDERS)
        item = rng.choice(_CANONICAL)
        amount = float(rng.choice([100, 250, 500, 1000]))
        order = _rand_order(rng, sender=sender, item=item, amount_pkr=amount,
                            payment_status=PaymentStatus.paid)
        row = _rand_row(rng, customer=sender, item=item, amount_pkr=amount, paid=True)
        result = reconcile([order], [row])
        assert result.flags == [], f"exact paid pair raised flags: {result.flags}"


def test_prop_reconciler_price_mismatch_detected():
    """R4: same name/item/date, amounts differing by > Rs 10 -> PRICE_MISMATCH."""
    rng = random.Random(20261122)
    for _ in range(100):
        sender = rng.choice(_SENDERS)
        item = rng.choice(_CANONICAL)
        order_amt = float(rng.choice([100, 200, 500]))
        row_amt = order_amt + rng.choice([11, 50, 500, 1000])
        order = _rand_order(rng, sender=sender, item=item, amount_pkr=order_amt,
                            payment_status=PaymentStatus.paid)
        row = _rand_row(rng, customer=sender, item=item, amount_pkr=row_amt, paid=True)
        result = reconcile([order], [row])
        kinds = [f.kind for f in result.flags]
        assert FlagKind.PRICE_MISMATCH in kinds, f"no PRICE_MISMATCH for {order_amt} vs {row_amt}"
        assert kinds == [FlagKind.PRICE_MISMATCH], f"unexpected flags: {kinds}"


def test_prop_reconciler_matching_is_one_to_one():
    """R5: each ledger row is matched to at most one order (and vice versa)."""
    rng = random.Random(20261123)
    for _ in range(200):
        n_orders = rng.randint(1, 6)
        n_rows = rng.randint(1, 6)
        orders = [_rand_order(rng, source_line=i + 1) for i in range(n_orders)]
        rows = [_rand_row(rng, row_index=i + 1) for i in range(n_rows)]
        matched, price_mismatch, _ = match_orders_to_rows(orders, rows)
        assert len(set(matched.values())) == len(matched), "one row matched twice"
        assert len(set(price_mismatch.values())) == len(price_mismatch)
        assert not (set(matched.values()) & set(price_mismatch.values())), (
            "row in both matched and price-mismatch"
        )


def test_prop_reconciler_dismiss_reduces_active_flags_and_preserves_original():
    """R6: dismiss removes exactly one active flag; the original ledger is untouched."""
    rng = random.Random(20261124)
    for _ in range(100):
        # Unmatched paid order -> exactly one PAID_NOT_RECORDED flag
        order = _rand_order(rng, payment_status=PaymentStatus.paid)
        result = reconcile([order], [])
        assert len(result.active_flags()) == 1
        before = copy.deepcopy(result)
        flag_id = result.flags[0].flag_id
        after = apply_fix(result, flag_id, "dismiss")
        assert len(after.active_flags()) == 0
        assert len(after.flags) == 1 and after.flags[0].dismissed
        assert result == before, "apply_fix mutated the original ledger"
        # Dismissing again is a no-op on the active count
        after2 = apply_fix(after, flag_id, "dismiss")
        assert len(after2.active_flags()) == 0


def test_prop_reconciler_accept_paid_not_recorded_adds_paid_row():
    """R7: accepting PAID_NOT_RECORDED adds a paid row for the order's amount."""
    rng = random.Random(20261125)
    for _ in range(100):
        amount = float(rng.choice([100, 250, 500]))
        order = _rand_order(rng, amount_pkr=amount, payment_status=PaymentStatus.paid)
        result = reconcile([order], [])
        flag_id = result.flags[0].flag_id
        after = apply_fix(result, flag_id, "accept")
        assert len(after.rows) == 1
        assert after.rows[0].paid is True
        assert after.rows[0].amount_pkr == amount
        assert after.totals.received == amount
        assert len(after.active_flags()) == 0


def test_prop_reconciler_duplicate_rows_flagged():
    """R8: two identical ledger rows for one order -> a DUPLICATE flag exists."""
    rng = random.Random(20261126)
    for _ in range(100):
        sender = rng.choice(_SENDERS)
        item = rng.choice(_CANONICAL)
        order = _rand_order(rng, sender=sender, item=item)
        row1 = _rand_row(rng, row_index=1, customer=sender, item=item)
        row2 = _rand_row(rng, row_index=2, customer=sender, item=item)
        result = reconcile([order], [row1, row2])
        kinds = [f.kind for f in result.flags]
        assert FlagKind.DUPLICATE in kinds, f"no DUPLICATE flag: {kinds}"


def test_prop_reconciler_never_crashes_on_random_inputs():
    """R9: reconcile() never raises on random orders/rows; flags use only known kinds."""
    rng = random.Random(20261127)
    known = {
        FlagKind.PAID_NOT_RECORDED, FlagKind.UNMATCHED_ORDER,
        FlagKind.RECORDED_NOT_PAID, FlagKind.PRICE_MISMATCH, FlagKind.DUPLICATE,
    }
    for _ in range(200):
        orders = [
            _rand_order(
                rng, source_line=i + 1,
                payment_status=rng.choice(list(PaymentStatus)),
                amount_pkr=rng.choice([None, 0.0, 100.0, 500.0]),
                item=rng.choice(_CANONICAL + [None]),
            )
            for i in range(rng.randint(0, 5))
        ]
        rows = [
            _rand_row(
                rng, row_index=i + 1,
                amount_pkr=rng.choice([None, 0.0, 100.0, 500.0]),
                paid=rng.choice([True, False]),
            )
            for i in range(rng.randint(0, 5))
        ]
        result = reconcile(orders, rows)
        assert all(f.kind in known for f in result.flags)
        assert result.totals.outstanding == result.totals.sold - result.totals.received
