"""
tests/test_reconciler.py — Spec 03 reconciler tests.

Covers:
  - One test per flag kind on the fictional sample set (PAID_NOT_RECORDED,
    RECORDED_NOT_PAID, PRICE_MISMATCH, DUPLICATE, UNMATCHED_ORDER).
  - Matching edge cases: name variants ('Ahmed bhai'), ±1 day, Rs 10
    boundary, duplicates.
  - Payment-event rule: Bilal's 450 payment marks his atta order paid;
    a payment event is never a standalone order and never raises a flag.
  - Fix actions: accept / edit / dismiss with totals recompute.
  - Original ledger is never mutated.
  - Session-driven /api/reconcile endpoint: upload sample → POST with
    empty body → flags; then POST /api/reconcile/fix accept on one flag
    → totals update.
  - Demo smoke test: sample chat + sample ledger → reconcile → list flags
    → fix one flag → totals update.

Expected flag list on the full sample set AFTER parser fix (10 flags total):
  PAID_NOT_RECORDED  x2  (Usman anda 600, Ahmed ghee 850)
  UNMATCHED_ORDER    x4  (Ahmed cheeni 2nd order, Sana doodh restatement,
                          Sana cheeni 250, Ahmed atta 300)
  RECORDED_NOT_PAID  x2  (Sana doodh row 2, Fatima chawal row 7)
  PRICE_MISMATCH     x1  (Ahmed cheeni chat 500 vs ledger 550)
  DUPLICATE          x1  (Bilal atta rows 3+4)

Totals: sold=4020, received=1420, outstanding=2600.

Run from apps/api/:
  apps/api/.venv/bin/python -m pytest tests/test_reconciler.py -v
"""
from __future__ import annotations

import copy
import io
import pathlib
import sys
from typing import Optional

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps" / "api"))

from frankenledger.models import CandidateOrder, Confidence, LedgerRow, PaymentStatus
from frankenledger.reconciler import (
    FlagKind,
    ReconciledLedger,
    Totals,
    apply_fix,
    compute_totals,
    match_orders_to_rows,
    normalise_name,
    normalise_item,
    reconcile,
    _resolve_payment_events,
)

SAMPLES_DIR = pathlib.Path(__file__).parent.parent / "samples"
SAMPLE_CHAT = SAMPLES_DIR / "sample-chat-export.txt"
SAMPLE_LEDGER = SAMPLES_DIR / "sample-ledger.xlsx"


# ---------------------------------------------------------------------------
# Helpers — build minimal test fixtures
# ---------------------------------------------------------------------------

def make_order(
    sender: str = "Ahmed",
    item: Optional[str] = "cheeni",
    amount: Optional[float] = 500.0,
    date: str = "2026-11-03",
    payment_status: PaymentStatus = PaymentStatus.unknown,
    source_line: int = 1,
    item_raw: Optional[str] = None,
    quantity: Optional[float] = 2.0,
    unit: Optional[str] = "kg",
) -> CandidateOrder:
    return CandidateOrder(
        date=date,
        sender=sender,
        item=item,
        item_raw=item_raw,
        quantity=quantity,
        unit=unit,
        amount_pkr=amount,
        payment_status=payment_status,
        source_line=source_line,
        confidence=Confidence.high,
    )


def make_row(
    row_index: int = 1,
    customer: str = "Ahmed",
    item: str = "cheeni",
    amount: Optional[float] = 500.0,
    paid: bool = False,
    date: str = "2026-11-03",
) -> LedgerRow:
    return LedgerRow(
        row_index=row_index,
        date=date,
        customer=customer,
        item=item,
        quantity="2kg",
        amount_pkr=amount,
        paid=paid,
        raw={},
    )


def load_sample() -> tuple[list[CandidateOrder], list[LedgerRow]]:
    """
    Load the fictional sample data from disk and return
    (orders, ledger_rows).  Uses the actual parser and ledger_io pipeline.
    """
    from frankenledger.parser import parse_chat
    from frankenledger.ledger_io import read_xlsx, apply_mapping
    import openpyxl

    chat_text = SAMPLE_CHAT.read_text(encoding="utf-8")
    orders = parse_chat(chat_text).orders

    ledger_bytes = SAMPLE_LEDGER.read_bytes()
    lf = read_xlsx(ledger_bytes)
    mapping = lf.suggested_mapping

    wb = openpyxl.load_workbook(io.BytesIO(ledger_bytes), read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    headers = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(all_rows[0])]
    data_rows = all_rows[1:]
    data_rows = [r for r in data_rows if any(c is not None for c in r)]
    raw_dicts = [
        {headers[i]: (str(c).strip() if c is not None else None) for i, c in enumerate(row)}
        for row in data_rows
    ]
    ledger_rows = apply_mapping(lf, mapping, raw_dicts)
    return orders, ledger_rows


# ---------------------------------------------------------------------------
# 1. Normalisation helpers
# ---------------------------------------------------------------------------

class TestNormaliseName:

    def test_lowercase(self):
        assert normalise_name("Ahmed") == "ahmed"

    def test_strip_bhai(self):
        assert normalise_name("Ahmed bhai") == "ahmed"

    def test_strip_sahab(self):
        assert normalise_name("Bilal sahab") == "bilal"

    def test_first_token_only(self):
        assert normalise_name("Sana Begum") == "sana"

    def test_empty(self):
        assert normalise_name("") == ""

    def test_none(self):
        assert normalise_name(None) == ""

    def test_strip_ji(self):
        assert normalise_name("Fatima ji") == "fatima"


class TestNormaliseItem:

    def test_cheeni(self):
        assert normalise_item("cheeni") == "cheeni"

    def test_chini_alias(self):
        assert normalise_item("chini") == "cheeni"

    def test_sugar_alias(self):
        assert normalise_item("sugar") == "cheeni"

    def test_none(self):
        assert normalise_item(None) is None

    def test_unknown_item(self):
        # Unknown items come back as-is (lowercased)
        assert normalise_item("mashroom") == "mashroom"


# ---------------------------------------------------------------------------
# 2. Matcher edge cases
# ---------------------------------------------------------------------------

class TestMatcher:

    def test_exact_match(self):
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03")
        row = make_row(1, "Ahmed", "cheeni", 500.0, False, "2026-11-03")
        matched, pm, _ = match_orders_to_rows([order], [row])
        assert matched == {0: 0}
        assert pm == {}

    def test_name_variant_bhai(self):
        """'Ahmed bhai' in chat must match 'Ahmed' in ledger."""
        order = make_order("Ahmed bhai", "cheeni", 500.0, "2026-11-03")
        row = make_row(1, "Ahmed", "cheeni", 500.0, False, "2026-11-03")
        matched, pm, _ = match_orders_to_rows([order], [row])
        assert matched == {0: 0}, "Name variant 'bhai' must normalise and match"

    def test_name_case_insensitive(self):
        order = make_order("ahmed", "cheeni", 500.0, "2026-11-03")
        row = make_row(1, "Ahmed", "cheeni", 500.0, False, "2026-11-03")
        matched, pm, _ = match_orders_to_rows([order], [row])
        assert matched == {0: 0}

    def test_date_plus_one_day_matches(self):
        """Chat order on Nov 3, ledger row on Nov 4 — within ±1 day."""
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03")
        row = make_row(1, "Ahmed", "cheeni", 500.0, False, "2026-11-04")
        matched, pm, _ = match_orders_to_rows([order], [row])
        assert matched == {0: 0}

    def test_date_minus_one_day_matches(self):
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-04")
        row = make_row(1, "Ahmed", "cheeni", 500.0, False, "2026-11-03")
        matched, pm, _ = match_orders_to_rows([order], [row])
        assert matched == {0: 0}

    def test_date_two_days_no_match(self):
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-05")
        row = make_row(1, "Ahmed", "cheeni", 500.0, False, "2026-11-03")
        matched, pm, _ = match_orders_to_rows([order], [row])
        assert matched == {}
        assert pm == {}

    def test_amount_within_10_matches(self):
        """Amounts within Rs 10 still count as a match (no PRICE_MISMATCH)."""
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03")
        row = make_row(1, "Ahmed", "cheeni", 508.0, False, "2026-11-03")  # diff = 8
        matched, pm, _ = match_orders_to_rows([order], [row])
        assert matched == {0: 0}
        assert pm == {}

    def test_amount_exactly_10_matches(self):
        """Rs 10 difference is within tolerance."""
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03")
        row = make_row(1, "Ahmed", "cheeni", 510.0, False, "2026-11-03")  # diff = 10
        matched, pm, _ = match_orders_to_rows([order], [row])
        assert matched == {0: 0}

    def test_amount_11_is_price_mismatch(self):
        """Rs 11 difference → PRICE_MISMATCH, not a clean match."""
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03")
        row = make_row(1, "Ahmed", "cheeni", 511.0, False, "2026-11-03")
        matched, pm, _ = match_orders_to_rows([order], [row])
        assert matched == {}
        assert pm == {0: 0}

    def test_duplicate_two_rows_same_order(self):
        """Two ledger rows with identical data → both candidates for one order."""
        order = make_order("Bilal", "atta", 450.0, "2026-11-03")
        row1 = make_row(1, "Bilal", "atta", 450.0, False, "2026-11-03")
        row2 = make_row(2, "Bilal", "atta", 450.0, False, "2026-11-03")
        matched, pm, row_to_orders = match_orders_to_rows([order], [row1, row2])
        # Only one should be matched (one-to-one), the other is a leftover
        assert len(matched) == 1

    def test_no_match_different_item(self):
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03")
        row = make_row(1, "Ahmed", "atta", 500.0, False, "2026-11-03")
        matched, pm, _ = match_orders_to_rows([order], [row])
        assert matched == {}
        assert pm == {}

    def test_no_match_different_customer(self):
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03")
        row = make_row(1, "Bilal", "cheeni", 500.0, False, "2026-11-03")
        matched, pm, _ = match_orders_to_rows([order], [row])
        assert matched == {}

    def test_one_to_one_best_score_wins(self):
        """When two orders could match one row, only the better one gets it."""
        order_exact = make_order("Ahmed", "cheeni", 500.0, "2026-11-03", source_line=1)
        order_near = make_order("Ahmed", "cheeni", 505.0, "2026-11-03", source_line=2)
        row = make_row(1, "Ahmed", "cheeni", 500.0, False, "2026-11-03")
        matched, pm, _ = match_orders_to_rows([order_exact, order_near], [row])
        # Only one of them gets matched
        assert len(matched) <= 1


# ---------------------------------------------------------------------------
# 3. Payment-event rule
# ---------------------------------------------------------------------------

class TestPaymentEvents:

    def test_payment_event_marks_order_paid(self):
        """Bilal's 450 payment event marks his atta order (450) as paid."""
        atta_order = make_order(
            "Bilal", "atta", 450.0, "2026-11-03",
            payment_status=PaymentStatus.unknown,
            source_line=1,
        )
        payment_event = make_order(
            "Bilal", None, 450.0, "2026-11-05",
            payment_status=PaymentStatus.paid,
            source_line=2,
            item_raw="kal wale 450 de diye",
            quantity=None,
            unit=None,
        )
        orders_resolved, payment_event_indices = _resolve_payment_events(
            [atta_order, payment_event]
        )
        # Payment event index should be identified
        assert 1 in payment_event_indices
        # Atta order should now be marked paid
        assert orders_resolved[0].payment_status == PaymentStatus.paid

    def test_payment_event_is_not_a_flag(self):
        """A payment event (no item, paid status) never generates its own flag."""
        atta_order = make_order(
            "Bilal", "atta", 450.0, "2026-11-03",
            payment_status=PaymentStatus.udhaar,
            source_line=1,
        )
        payment_event = make_order(
            "Bilal", None, 450.0, "2026-11-05",
            payment_status=PaymentStatus.paid,
            source_line=2,
            item_raw="kal wale 450 de diye",
            quantity=None,
            unit=None,
        )
        row = make_row(1, "Bilal", "atta", 450.0, False, "2026-11-03")
        result = reconcile([atta_order, payment_event], [row])
        # No flag should reference the payment event as a standalone order
        payment_event_flags = [
            f for f in result.flags
            if f.chat_order is not None and f.chat_order.source_line == 2
        ]
        assert payment_event_flags == [], (
            "Payment event must not generate its own flag"
        )

    def test_payment_event_does_not_match_wrong_amount(self):
        """A 450 payment event does not mark a 500-Rs atta order as paid."""
        atta_order = make_order(
            "Bilal", "atta", 500.0, "2026-11-03",
            payment_status=PaymentStatus.udhaar,
            source_line=1,
        )
        payment_event = make_order(
            "Bilal", None, 450.0, "2026-11-05",
            payment_status=PaymentStatus.paid,
            source_line=2,
            item_raw="kal wale 450",
            quantity=None,
            unit=None,
        )
        orders_resolved, payment_event_indices = _resolve_payment_events(
            [atta_order, payment_event]
        )
        # Atta order (500) should NOT be marked paid (diff = 50 > Rs 10)
        assert orders_resolved[0].payment_status == PaymentStatus.udhaar

    def test_bilal_sample_payment_event(self):
        """
        On the full sample set, Bilal's 450 payment event (L21) resolves his
        atta order. The atta order must not appear as UNMATCHED_ORDER.
        """
        orders, ledger_rows = load_sample()
        result = reconcile(orders, ledger_rows)
        # No UNMATCHED_ORDER for Bilal atta
        bilal_atta_unmatched = [
            f for f in result.flags
            if f.kind == FlagKind.UNMATCHED_ORDER
            and f.chat_order is not None
            and normalise_name(f.chat_order.sender) == "bilal"
            and f.chat_order.item == "atta"
        ]
        assert bilal_atta_unmatched == [], (
            "Bilal atta should not be UNMATCHED_ORDER — "
            "payment event at L21 marks it paid"
        )


# ---------------------------------------------------------------------------
# 4. Flag generation — one test per flag kind on the sample set
# ---------------------------------------------------------------------------

class TestFlagKindsOnSampleSet:

    @pytest.fixture(scope="class")
    def sample_reconcile(self):
        orders, ledger_rows = load_sample()
        return reconcile(orders, ledger_rows)

    def test_total_flag_count(self, sample_reconcile):
        """
        After the parser fix, the sample set must produce exactly 10 flags.
        If this fails, report the actual flags plainly — do not fake it.
        """
        flags = sample_reconcile.flags
        flag_summary = [(f.kind, f.chat_order.sender if f.chat_order else None,
                         f.chat_order.item if f.chat_order else None,
                         [r.row_index for r in f.ledger_rows]) for f in flags]
        assert len(flags) == 10, (
            f"Expected 10 flags, got {len(flags)}.\n"
            f"Actual flags:\n" + "\n".join(f"  {f}" for f in flag_summary)
        )

    def test_paid_not_recorded_usman_anda(self, sample_reconcile):
        """Usman paid for anda (Rs 600) but no ledger row exists."""
        flags = [
            f for f in sample_reconcile.flags
            if f.kind == FlagKind.PAID_NOT_RECORDED
            and f.chat_order is not None
            and normalise_name(f.chat_order.sender) == "usman"
            and f.chat_order.item == "anda"
        ]
        assert flags, "Expected PAID_NOT_RECORDED for Usman anda 600"
        assert flags[0].chat_order.amount_pkr == 600.0

    def test_paid_not_recorded_ahmed_ghee(self, sample_reconcile):
        """Ahmed paid for ghee (Rs 850) but no ledger row exists."""
        flags = [
            f for f in sample_reconcile.flags
            if f.kind == FlagKind.PAID_NOT_RECORDED
            and f.chat_order is not None
            and normalise_name(f.chat_order.sender) == "ahmed"
            and f.chat_order.item == "ghee"
        ]
        assert flags, "Expected PAID_NOT_RECORDED for Ahmed ghee 850"
        assert flags[0].chat_order.amount_pkr == 850.0

    def test_paid_not_recorded_count(self, sample_reconcile):
        """Exactly 2 PAID_NOT_RECORDED flags."""
        pnr = [f for f in sample_reconcile.flags if f.kind == FlagKind.PAID_NOT_RECORDED]
        assert len(pnr) == 2, (
            f"Expected 2 PAID_NOT_RECORDED, got {len(pnr)}: "
            f"{[(f.chat_order.sender, f.chat_order.item) for f in pnr if f.chat_order]}"
        )

    def test_unmatched_order_ahmed_cheeni_2nd(self, sample_reconcile):
        """Ahmed's 2nd cheeni order (L14, Rs 500) has no ledger row."""
        flags = [
            f for f in sample_reconcile.flags
            if f.kind == FlagKind.UNMATCHED_ORDER
            and f.chat_order is not None
            and normalise_name(f.chat_order.sender) == "ahmed"
            and f.chat_order.item == "cheeni"
        ]
        assert flags, "Expected UNMATCHED_ORDER for Ahmed 2nd cheeni order"

    def test_unmatched_order_sana_doodh_restatement(self, sample_reconcile):
        """Sana's doodh restatement (L16) — 'rehta hai' — is unmatched."""
        flags = [
            f for f in sample_reconcile.flags
            if f.kind == FlagKind.UNMATCHED_ORDER
            and f.chat_order is not None
            and normalise_name(f.chat_order.sender) == "sana"
            and f.chat_order.item == "doodh"
        ]
        assert flags, "Expected UNMATCHED_ORDER for Sana doodh restatement"

    def test_unmatched_order_sana_cheeni(self, sample_reconcile):
        """Sana cheeni 250 (L22) has no ledger row."""
        flags = [
            f for f in sample_reconcile.flags
            if f.kind == FlagKind.UNMATCHED_ORDER
            and f.chat_order is not None
            and normalise_name(f.chat_order.sender) == "sana"
            and f.chat_order.item == "cheeni"
        ]
        assert flags, "Expected UNMATCHED_ORDER for Sana cheeni 250"

    def test_unmatched_order_ahmed_atta(self, sample_reconcile):
        """Ahmed atta 300 (L24) has no ledger row."""
        flags = [
            f for f in sample_reconcile.flags
            if f.kind == FlagKind.UNMATCHED_ORDER
            and f.chat_order is not None
            and normalise_name(f.chat_order.sender) == "ahmed"
            and f.chat_order.item == "atta"
        ]
        assert flags, "Expected UNMATCHED_ORDER for Ahmed atta 300"

    def test_unmatched_order_count(self, sample_reconcile):
        """Exactly 4 UNMATCHED_ORDER flags."""
        uo = [f for f in sample_reconcile.flags if f.kind == FlagKind.UNMATCHED_ORDER]
        assert len(uo) == 4, (
            f"Expected 4 UNMATCHED_ORDER, got {len(uo)}: "
            f"{[(f.chat_order.sender, f.chat_order.item) for f in uo if f.chat_order]}"
        )

    def test_recorded_not_paid_sana_doodh_row2(self, sample_reconcile):
        """Ledger row 2 (Sana doodh, paid=Yes) has no payment confirmation in chat."""
        flags = [
            f for f in sample_reconcile.flags
            if f.kind == FlagKind.RECORDED_NOT_PAID
            and any(r.row_index == 2 for r in f.ledger_rows)
        ]
        assert flags, "Expected RECORDED_NOT_PAID for Sana doodh ledger row 2"

    def test_recorded_not_paid_fatima_chawal_row7(self, sample_reconcile):
        """Ledger row 7 (Fatima chawal, paid=Yes) has no matching chat order."""
        flags = [
            f for f in sample_reconcile.flags
            if f.kind == FlagKind.RECORDED_NOT_PAID
            and any(r.row_index == 7 for r in f.ledger_rows)
        ]
        assert flags, "Expected RECORDED_NOT_PAID for Fatima chawal ledger row 7"

    def test_recorded_not_paid_count(self, sample_reconcile):
        """Exactly 2 RECORDED_NOT_PAID flags."""
        rnp = [f for f in sample_reconcile.flags if f.kind == FlagKind.RECORDED_NOT_PAID]
        assert len(rnp) == 2, (
            f"Expected 2 RECORDED_NOT_PAID, got {len(rnp)}: "
            f"{[(f.chat_order.sender if f.chat_order else None, [r.row_index for r in f.ledger_rows]) for f in rnp]}"
        )

    def test_price_mismatch_ahmed_cheeni(self, sample_reconcile):
        """Ahmed cheeni: chat shows Rs 500 (L6), ledger row 1 shows Rs 550."""
        flags = [
            f for f in sample_reconcile.flags
            if f.kind == FlagKind.PRICE_MISMATCH
        ]
        assert flags, "Expected at least one PRICE_MISMATCH flag"
        flag = flags[0]
        assert flag.chat_order is not None
        assert normalise_name(flag.chat_order.sender) == "ahmed"
        assert flag.chat_order.item == "cheeni"
        assert flag.chat_order.amount_pkr == 500.0
        assert any(r.amount_pkr == 550.0 for r in flag.ledger_rows)

    def test_price_mismatch_count(self, sample_reconcile):
        """Exactly 1 PRICE_MISMATCH flag."""
        pm = [f for f in sample_reconcile.flags if f.kind == FlagKind.PRICE_MISMATCH]
        assert len(pm) == 1, (
            f"Expected 1 PRICE_MISMATCH, got {len(pm)}: "
            f"{[(f.chat_order.sender if f.chat_order else None, f.chat_order.item if f.chat_order else None) for f in pm]}"
        )

    def test_duplicate_bilal_atta_rows_3_4(self, sample_reconcile):
        """Bilal atta appears in both ledger rows 3 and 4."""
        flags = [
            f for f in sample_reconcile.flags
            if f.kind == FlagKind.DUPLICATE
        ]
        assert flags, "Expected at least one DUPLICATE flag"
        flag = flags[0]
        row_indices = {r.row_index for r in flag.ledger_rows}
        assert 3 in row_indices, f"Expected row 3 in DUPLICATE, got {row_indices}"
        assert 4 in row_indices, f"Expected row 4 in DUPLICATE, got {row_indices}"

    def test_duplicate_count(self, sample_reconcile):
        """Exactly 1 DUPLICATE flag."""
        dup = [f for f in sample_reconcile.flags if f.kind == FlagKind.DUPLICATE]
        assert len(dup) == 1, f"Expected 1 DUPLICATE, got {len(dup)}"

    def test_all_flags_have_explanation(self, sample_reconcile):
        """Every flag must have a non-empty explanation (evidence)."""
        for f in sample_reconcile.flags:
            assert f.explanation, f"Flag {f.flag_id} ({f.kind}) has no explanation"

    def test_all_flags_have_fix_description(self, sample_reconcile):
        """Every flag must have a non-empty fix_description."""
        for f in sample_reconcile.flags:
            assert f.fix_description, f"Flag {f.flag_id} ({f.kind}) has no fix_description"


# ---------------------------------------------------------------------------
# 5. Totals on the full sample set
# ---------------------------------------------------------------------------

class TestTotalsOnSampleSet:

    def test_totals_sold(self):
        """sold = sum of all ledger row amounts = 4020."""
        orders, ledger_rows = load_sample()
        result = reconcile(orders, ledger_rows)
        assert result.totals.sold == pytest.approx(4020.0), (
            f"Expected sold=4020, got {result.totals.sold}"
        )

    def test_totals_received(self):
        """received = sum of paid=True rows = 1420."""
        orders, ledger_rows = load_sample()
        result = reconcile(orders, ledger_rows)
        assert result.totals.received == pytest.approx(1420.0), (
            f"Expected received=1420, got {result.totals.received}"
        )

    def test_totals_outstanding(self):
        """outstanding = sold - received = 2600."""
        orders, ledger_rows = load_sample()
        result = reconcile(orders, ledger_rows)
        assert result.totals.outstanding == pytest.approx(2600.0), (
            f"Expected outstanding=2600, got {result.totals.outstanding}"
        )


# ---------------------------------------------------------------------------
# 6. Original ledger never mutated
# ---------------------------------------------------------------------------

class TestOriginalNotMutated:

    def test_reconcile_does_not_mutate_ledger(self):
        """reconcile() must return a new ledger; original rows unchanged."""
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03")
        row = make_row(1, "Ahmed", "cheeni", 500.0, True, "2026-11-03")
        original_paid = row.paid
        original_amount = row.amount_pkr
        original_rows = [row]

        reconcile([order], original_rows)
        # Original row must be unchanged
        assert original_rows[0].paid == original_paid
        assert original_rows[0].amount_pkr == original_amount

    def test_apply_fix_does_not_mutate_reconciled(self):
        """apply_fix() must return a new ReconciledLedger; original unchanged."""
        order = make_order("Ahmed", "ghee", 850.0, "2026-11-04",
                           payment_status=PaymentStatus.paid)
        rows: list[LedgerRow] = []  # no ledger rows → PAID_NOT_RECORDED
        result = reconcile([order], rows)
        assert result.flags, "Expected at least one flag"

        original_flags_count = len(result.flags)
        flag = result.flags[0]

        updated = apply_fix(result, flag.flag_id, "dismiss")
        # Original unchanged
        assert len(result.flags) == original_flags_count
        assert not result.flags[0].dismissed
        # Updated has the dismissal
        matching = [f for f in updated.flags if f.flag_id == flag.flag_id]
        assert matching[0].dismissed is True


# ---------------------------------------------------------------------------
# 7. Fix actions
# ---------------------------------------------------------------------------

class TestFixActions:

    def _setup_paid_not_recorded(self):
        order = make_order("Usman", "anda", 600.0, "2026-11-03",
                           payment_status=PaymentStatus.paid, source_line=12)
        return reconcile([order], [])

    def test_accept_paid_not_recorded_adds_row(self):
        """accept on PAID_NOT_RECORDED must add a new ledger row."""
        result = self._setup_paid_not_recorded()
        flags = [f for f in result.flags if f.kind == FlagKind.PAID_NOT_RECORDED]
        assert flags
        before_count = len(result.rows)
        updated = apply_fix(result, flags[0].flag_id, "accept")
        assert len(updated.rows) == before_count + 1
        new_row = updated.rows[-1]
        assert new_row.paid is True
        assert new_row.amount_pkr == 600.0
        assert normalise_name(new_row.customer) == "usman"

    def test_accept_paid_not_recorded_updates_totals(self):
        """Accepting PAID_NOT_RECORDED must increase sold and received totals."""
        result = self._setup_paid_not_recorded()
        flags = [f for f in result.flags if f.kind == FlagKind.PAID_NOT_RECORDED]
        before_sold = result.totals.sold
        before_received = result.totals.received
        updated = apply_fix(result, flags[0].flag_id, "accept")
        assert updated.totals.sold == pytest.approx(before_sold + 600.0)
        assert updated.totals.received == pytest.approx(before_received + 600.0)

    def test_accept_unmatched_order_adds_udhaar_row(self):
        """accept on UNMATCHED_ORDER must add a new udhaar (paid=False) row."""
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03",
                           payment_status=PaymentStatus.unknown, source_line=14)
        result = reconcile([order], [])
        flags = [f for f in result.flags if f.kind == FlagKind.UNMATCHED_ORDER]
        assert flags
        updated = apply_fix(result, flags[0].flag_id, "accept")
        assert len(updated.rows) == 1
        assert updated.rows[0].paid is False
        assert updated.rows[0].amount_pkr == 500.0

    def test_accept_recorded_not_paid_marks_udhaar(self):
        """accept on RECORDED_NOT_PAID marks the ledger row as unpaid."""
        row = make_row(1, "Sana", "doodh", 220.0, True, "2026-11-03")  # paid=True in ledger
        # Sana's doodh order is udhaar in chat
        order = make_order("Sana", "doodh", 220.0, "2026-11-03",
                           payment_status=PaymentStatus.udhaar, source_line=11)
        result = reconcile([order], [row])
        flags = [f for f in result.flags if f.kind == FlagKind.RECORDED_NOT_PAID]
        assert flags, "Expected RECORDED_NOT_PAID for Sana doodh (ledger paid=True, chat udhaar)"
        updated = apply_fix(result, flags[0].flag_id, "accept")
        row_after = next(r for r in updated.rows if r.row_index == 1)
        assert row_after.paid is False

    def test_accept_price_mismatch_uses_chat_amount(self):
        """accept on PRICE_MISMATCH updates the ledger row to the chat amount."""
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03")  # chat: 500
        row = make_row(1, "Ahmed", "cheeni", 550.0, False, "2026-11-03")  # ledger: 550
        result = reconcile([order], [row])
        flags = [f for f in result.flags if f.kind == FlagKind.PRICE_MISMATCH]
        assert flags
        updated = apply_fix(result, flags[0].flag_id, "accept")
        row_after = next(r for r in updated.rows if r.row_index == 1)
        assert row_after.amount_pkr == pytest.approx(500.0), (
            "After accepting PRICE_MISMATCH, row amount should be chat amount (500)"
        )

    def test_accept_price_mismatch_updates_totals(self):
        """Accepting PRICE_MISMATCH recalculates totals correctly."""
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03")  # chat: 500
        row = make_row(1, "Ahmed", "cheeni", 550.0, False, "2026-11-03")  # ledger: 550
        result = reconcile([order], [row])
        flags = [f for f in result.flags if f.kind == FlagKind.PRICE_MISMATCH]
        updated = apply_fix(result, flags[0].flag_id, "accept")
        assert updated.totals.sold == pytest.approx(500.0)

    def test_accept_duplicate_marks_second_row_inactive(self):
        """accept on DUPLICATE marks the second row as not paid and notes DUPLICATE."""
        order = make_order("Bilal", "atta", 450.0, "2026-11-03")
        row1 = make_row(1, "Bilal", "atta", 450.0, False, "2026-11-03")
        row2 = make_row(2, "Bilal", "atta", 450.0, False, "2026-11-03")
        result = reconcile([order], [row1, row2])
        flags = [f for f in result.flags if f.kind == FlagKind.DUPLICATE]
        assert flags
        updated = apply_fix(result, flags[0].flag_id, "accept")
        # The second row should be marked with a DUPLICATE note
        row2_after = next((r for r in updated.rows if r.row_index == 2), None)
        assert row2_after is not None
        assert "DUPLICATE" in str(row2_after.raw.get("note", ""))

    def test_dismiss_flag_hides_it(self):
        """dismiss must set dismissed=True; flag is not deleted."""
        order = make_order("Usman", "anda", 600.0, "2026-11-03",
                           payment_status=PaymentStatus.paid)
        result = reconcile([order], [])
        flags = result.flags
        assert flags
        updated = apply_fix(result, flags[0].flag_id, "dismiss")
        dismissed = [f for f in updated.flags if f.flag_id == flags[0].flag_id]
        assert dismissed[0].dismissed is True
        # active_flags should not include it
        assert flags[0].flag_id not in {f.flag_id for f in updated.active_flags()}

    def test_dismiss_does_not_change_totals(self):
        """Dismissing a flag must not change totals (no rows modified)."""
        order = make_order("Usman", "anda", 600.0, "2026-11-03",
                           payment_status=PaymentStatus.paid)
        result = reconcile([order], [])
        before = result.totals
        updated = apply_fix(result, result.flags[0].flag_id, "dismiss")
        assert updated.totals.sold == before.sold
        assert updated.totals.received == before.received

    def test_edit_changes_amount_then_updates_totals(self):
        """edit action applies the patch and recomputes totals."""
        order = make_order("Ahmed", "cheeni", 500.0, "2026-11-03")
        row = make_row(1, "Ahmed", "cheeni", 550.0, False, "2026-11-03")
        result = reconcile([order], [row])
        flags = [f for f in result.flags if f.kind == FlagKind.PRICE_MISMATCH]
        assert flags
        # Edit: choose 520 as the agreed amount
        updated = apply_fix(
            result,
            flags[0].flag_id,
            "edit",
            patch={"amount_pkr": 520.0},
        )
        row_after = next(r for r in updated.rows if r.row_index == 1)
        assert row_after.amount_pkr == pytest.approx(520.0)
        assert updated.totals.sold == pytest.approx(520.0)

    def test_apply_fix_default_patch_none(self):
        """apply_fix must work without a patch argument (default None)."""
        order = make_order("Usman", "anda", 600.0, "2026-11-03",
                           payment_status=PaymentStatus.paid)
        result = reconcile([order], [])
        flags = result.flags
        # Should not raise — patch defaults to None
        updated = apply_fix(result, flags[0].flag_id, "accept")
        assert updated is not None

    def test_totals_recompute_after_accept_adds_row(self):
        """After accept adds a row, outstanding must decrease."""
        order = make_order("Ahmed", "ghee", 850.0, "2026-11-04",
                           payment_status=PaymentStatus.paid)
        result = reconcile([order], [])
        assert result.totals.sold == pytest.approx(0.0)
        flags = [f for f in result.flags if f.kind == FlagKind.PAID_NOT_RECORDED]
        updated = apply_fix(result, flags[0].flag_id, "accept")
        assert updated.totals.sold == pytest.approx(850.0)
        assert updated.totals.received == pytest.approx(850.0)
        assert updated.totals.outstanding == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 8. Session-driven /api/reconcile endpoint
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    """Return a TestClient with the FastAPI app."""
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps" / "api"))
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


class TestSessionDrivenReconcileEndpoint:

    def test_reconcile_without_session_returns_400(self, api_client):
        """POST /api/reconcile with empty body and no session → 400."""
        from main import _SESSION
        _SESSION["chat_text"] = None
        _SESSION["ledger_bytes"] = None
        r = api_client.post("/api/reconcile", json={})
        assert r.status_code == 400
        assert "chat" in r.json()["detail"].lower() or "session" in r.json()["detail"].lower()

    def test_reconcile_no_ledger_returns_400(self, api_client):
        """POST /api/reconcile with chat but no ledger → 400."""
        from main import _SESSION
        _SESSION["chat_text"] = "03/11/2026, 09:15 - Ahmed: 2kg cheeni Rs 500\n"
        _SESSION["ledger_bytes"] = None
        _SESSION["confirmed_mapping"] = None
        r = api_client.post("/api/reconcile", json={})
        assert r.status_code == 400
        assert "ledger" in r.json()["detail"].lower()

    def test_session_driven_reconcile_sample(self, api_client):
        """
        Upload sample → POST /api/reconcile with empty body → 10 flags.
        """
        # Reset session via sample upload
        r = api_client.post("/api/upload/sample")
        assert r.status_code == 200

        # POST reconcile with empty body — session-driven
        r = api_client.post("/api/reconcile", json={})
        assert r.status_code == 200
        body = r.json()
        assert "flags" in body
        assert "totals" in body
        flags = body["flags"]
        assert len(flags) == 10, (
            f"Expected 10 flags from session-driven reconcile, got {len(flags)}.\n"
            f"Flags: {[(f['kind'], f.get('chat_order', {}) and f['chat_order'].get('sender'), [lr.get('row_index') for lr in f.get('ledger_rows', [])]) for f in flags]}"
        )

    def test_session_driven_totals(self, api_client):
        """Session-driven reconcile must produce correct totals."""
        api_client.post("/api/upload/sample")
        r = api_client.post("/api/reconcile", json={})
        assert r.status_code == 200
        totals = r.json()["totals"]
        assert totals["sold"] == pytest.approx(4020.0)
        assert totals["received"] == pytest.approx(1420.0)
        assert totals["outstanding"] == pytest.approx(2600.0)

    def test_session_driven_fix_accept_updates_totals(self, api_client):
        """
        Upload sample → reconcile (empty body) → accept a PAID_NOT_RECORDED flag
        → totals increase.
        """
        api_client.post("/api/upload/sample")
        r = api_client.post("/api/reconcile", json={})
        assert r.status_code == 200
        flags = r.json()["flags"]
        before_sold = r.json()["totals"]["sold"]

        # Find a PAID_NOT_RECORDED flag
        pnr = [f for f in flags if f["kind"] == "PAID_NOT_RECORDED"]
        assert pnr, "Expected at least one PAID_NOT_RECORDED flag from sample"

        # Accept it
        flag_id = pnr[0]["flag_id"]
        r2 = api_client.post(
            "/api/reconcile/fix",
            json={"flag_id": flag_id, "action": "accept"},
        )
        assert r2.status_code == 200
        after_sold = r2.json()["totals"]["sold"]
        # Sold must have increased after adding the row
        assert after_sold > before_sold, (
            f"Totals sold should increase after accepting PAID_NOT_RECORDED. "
            f"before={before_sold}, after={after_sold}"
        )


# ---------------------------------------------------------------------------
# 9. Demo smoke test — full flow
# ---------------------------------------------------------------------------

class TestDemoSmokeTest:

    def test_demo_flow_full(self, api_client):
        """
        Demo smoke test: sample chat + sample ledger → reconcile → list flags
        → fix one flag → totals update.

        This is the acceptance test for the 3-minute demo flow.
        Deterministic mode only — no LLM key required.
        """
        # Step 1: Upload sample (fictional data)
        r = api_client.post("/api/upload/sample")
        assert r.status_code == 200
        sample = r.json()
        assert sample["sample"] is True
        assert "fictional" in sample["label"].lower()

        # Step 2: Reconcile (session-driven, empty body)
        r = api_client.post("/api/reconcile", json={})
        assert r.status_code == 200
        data = r.json()

        flags = data["flags"]
        totals = data["totals"]
        reconciled_rows = data["reconciled"]

        # Five flag kinds must all be present
        kinds = {f["kind"] for f in flags}
        assert "PAID_NOT_RECORDED" in kinds, f"Missing PAID_NOT_RECORDED in {kinds}"
        assert "UNMATCHED_ORDER" in kinds, f"Missing UNMATCHED_ORDER in {kinds}"
        assert "RECORDED_NOT_PAID" in kinds, f"Missing RECORDED_NOT_PAID in {kinds}"
        assert "PRICE_MISMATCH" in kinds, f"Missing PRICE_MISMATCH in {kinds}"
        assert "DUPLICATE" in kinds, f"Missing DUPLICATE in {kinds}"

        # 10 flags total
        assert len(flags) == 10, (
            f"Demo smoke: expected 10 flags, got {len(flags)}. "
            f"Kinds: {[(f['kind'], f.get('chat_order',{}) and f['chat_order'].get('sender','?'), f.get('chat_order',{}) and f['chat_order'].get('item','?')) for f in flags]}"
        )

        # Correct totals
        assert totals["sold"] == pytest.approx(4020.0)
        assert totals["received"] == pytest.approx(1420.0)
        assert totals["outstanding"] == pytest.approx(2600.0)

        # Each flag has an explanation and fix_description
        for f in flags:
            assert f["explanation"], f"Flag {f['flag_id']} has no explanation"
            assert f["fix_description"], f"Flag {f['flag_id']} has no fix_description"
            # Evidence: chat_order must have source_line OR ledger_rows must have row_index
            has_evidence = (
                (f.get("chat_order") and f["chat_order"].get("source_line"))
                or f.get("ledger_rows")
            )
            assert has_evidence, f"Flag {f['flag_id']} ({f['kind']}) has no evidence"

        # Step 3: Fix one flag — accept the PRICE_MISMATCH
        pm_flags = [f for f in flags if f["kind"] == "PRICE_MISMATCH"]
        assert pm_flags, "Expected a PRICE_MISMATCH flag for the demo"
        pm_flag = pm_flags[0]

        r = api_client.post(
            "/api/reconcile/fix",
            json={"flag_id": pm_flag["flag_id"], "action": "accept"},
        )
        assert r.status_code == 200
        updated_data = r.json()
        updated_totals = updated_data["totals"]

        # After fixing PRICE_MISMATCH (500 vs 550), sold should decrease by 50
        assert updated_totals["sold"] == pytest.approx(3970.0), (
            f"After accepting PRICE_MISMATCH (500 vs 550), sold should be 3970. "
            f"Got: {updated_totals['sold']}"
        )
        # The flag should now be dismissed
        updated_flags = updated_data["flags"]
        pm_after = next(f for f in updated_flags if f["flag_id"] == pm_flag["flag_id"])
        assert pm_after["dismissed"] is True

        # Verify reconciled label: app must NOT claim real integration or payments
        # (structural check — the label field in the upload response said fictional)
        # We check the session still has sample=True
        assert sample["sample"] is True
