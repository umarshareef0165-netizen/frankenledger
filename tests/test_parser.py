"""
tests/test_parser.py — Spec 02 labelled sample set.

Honest report printed at the end of the module (not a percentage claim):
  extracted / correct / missed / wrong  on this small labelled set only.

Run from apps/api/: apps/api/.venv/bin/python -m pytest tests/test_parser.py -v -s
"""
from __future__ import annotations

import pathlib
import sys
from collections import defaultdict

# Allow importing from apps/api without installing the package
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps" / "api"))

import pytest
from frankenledger.parser import parse_chat
from frankenledger.models import PaymentStatus, Confidence

SAMPLE_FILE = pathlib.Path(__file__).parent.parent / "samples" / "sample-chat-export.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def orders_from(text: str):
    return parse_chat(text).orders


def first_order(text: str):
    ords = orders_from(text)
    assert ords, f"Expected at least one order from: {text!r}"
    return ords[0]


# ---------------------------------------------------------------------------
# 1. Date + sender parsing
# ---------------------------------------------------------------------------

class TestLineSplitter:

    def test_24h_ddmm(self):
        o = first_order("03/11/2026, 09:15 - Ahmed: 2kg cheeni Rs 500")
        assert o.date == "2026-11-03"
        assert o.sender == "Ahmed"

    def test_12h_am(self):
        o = first_order("03/11/2026, 09:15 AM - Ahmed: 2kg cheeni Rs 500")
        assert o.date == "2026-11-03"
        assert o.sender == "Ahmed"

    def test_12h_pm(self):
        o = first_order("03/11/2026, 01:15 PM - Bilal: 3kg atta 450")
        assert o.date == "2026-11-03"
        assert o.sender == "Bilal"

    def test_day_gt_12_disambiguated(self):
        o = first_order("14/11/2026, 10:00 - Sana: 1 litre doodh 220")
        assert o.date == "2026-11-14"

    def test_unparsed_line_not_counted_as_order(self):
        result = parse_chat("just a random line with no date")
        assert result.orders == []
        assert result.unparsed_count == 1

    def test_comment_line_ignored(self):
        result = parse_chat("# this is a comment\n03/11/2026, 09:15 - A: 1kg cheeni Rs 250")
        assert result.unparsed_count == 0

    def test_blank_line_ignored(self):
        result = parse_chat("\n\n03/11/2026, 09:15 - A: 1kg cheeni Rs 250\n\n")
        assert result.unparsed_count == 0


# ---------------------------------------------------------------------------
# 2. Quantity extraction
# ---------------------------------------------------------------------------

class TestQuantityExtraction:

    def test_kg_digit(self):
        o = first_order("03/11/2026, 09:15 - A: 2kg cheeni Rs 500")
        assert o.quantity == 2.0
        assert o.unit == "kg"

    def test_kilo_digit_space(self):
        o = first_order("04/11/2026, 12:30 - A: 2 kilo daal 400")
        assert o.quantity == 2.0
        assert o.unit == "kg"

    def test_litre(self):
        o = first_order("03/11/2026, 11:30 - A: 1 litre doodh 220")
        assert o.quantity == 1.0
        assert o.unit == "litre"

    def test_packet(self):
        o = first_order("04/11/2026, 09:10 - A: 5 packet chai 750")
        assert o.quantity == 5.0
        assert o.unit == "packet"

    def test_darjan(self):
        o = first_order("03/11/2026, 12:40 - A: 2 darjan anda 600")
        assert o.quantity == 2.0
        assert o.unit == "darjan"

    def test_roman_urdu_do_kilo(self):
        o = first_order("05/11/2026, 11:00 - A: do kilo atta 300")
        assert o.quantity == 2.0
        assert o.unit == "kg"

    def test_roman_urdu_ek_kg(self):
        o = first_order("03/11/2026, 09:00 - A: ek kg cheeni Rs 250")
        assert o.quantity == 1.0
        assert o.unit == "kg"

    def test_roman_urdu_teen_packet(self):
        o = first_order("03/11/2026, 09:00 - A: teen packet chai Rs 450")
        assert o.quantity == 3.0
        assert o.unit == "packet"

    def test_roman_urdu_chaar_litre(self):
        o = first_order("03/11/2026, 09:00 - A: chaar litre doodh Rs 880")
        assert o.quantity == 4.0
        assert o.unit == "litre"

    def test_roman_urdu_paanch_kilo(self):
        o = first_order("03/11/2026, 09:00 - A: paanch kilo atta Rs 750")
        assert o.quantity == 5.0
        assert o.unit == "kg"

    def test_fractional_kg(self):
        o = first_order("03/11/2026, 09:00 - A: 1.5kg cheeni Rs 375")
        assert o.quantity == 1.5
        assert o.unit == "kg"


# ---------------------------------------------------------------------------
# 3. Amount extraction
# ---------------------------------------------------------------------------

class TestAmountExtraction:

    def test_rs_prefix(self):
        o = first_order("03/11/2026, 09:15 - A: 2kg cheeni Rs 500")
        assert o.amount_pkr == 500.0

    def test_rs_dot_prefix(self):
        o = first_order("03/11/2026, 09:15 - A: 2kg cheeni Rs. 500")
        assert o.amount_pkr == 500.0

    def test_rupy_suffix(self):
        o = first_order("03/11/2026, 10:05 - A: 3kg atta 450 rupy")
        assert o.amount_pkr == 450.0

    def test_slash_suffix(self):
        o = first_order("03/11/2026, 09:00 - A: 1kg cheeni 250/-")
        assert o.amount_pkr == 250.0

    def test_comma_thousands(self):
        o = first_order("03/11/2026, 09:00 - A: 1kg ghee Rs 1,500")
        assert o.amount_pkr == 1500.0

    def test_bare_number(self):
        o = first_order("03/11/2026, 13:15 - A: 1kg chawal 300")
        assert o.amount_pkr == 300.0

    def test_rs_no_space(self):
        o = first_order("03/11/2026, 09:00 - A: 1kg cheeni Rs500")
        assert o.amount_pkr == 500.0


# ---------------------------------------------------------------------------
# 4. Payment status
# ---------------------------------------------------------------------------

class TestPaymentStatus:

    def test_paid_keyword(self):
        o = first_order("03/11/2026, 12:40 - A: 2 darjan anda 600, paid")
        assert o.payment_status == PaymentStatus.paid

    def test_paise_de_diye(self):
        o = first_order("05/11/2026, 08:50 - A: bhai kal wale 450 de diye")
        assert o.payment_status == PaymentStatus.paid

    def test_de_diya_payment_line(self):
        result = parse_chat("03/11/2026, 09:22 - A: paise de diye, shukriya")
        # payment-only line — if order emitted, it must be paid
        if result.orders:
            assert result.orders[0].payment_status == PaymentStatus.paid

    def test_udhaar_keyword(self):
        o = first_order("03/11/2026, 11:30 - A: 1 litre doodh 220 udhaar")
        assert o.payment_status == PaymentStatus.udhaar

    def test_kal_dunga(self):
        o = first_order("04/11/2026, 09:10 - A: 5 packet chai 750 kal dunga")
        assert o.payment_status == PaymentStatus.udhaar

    def test_kal_paise_dunga_line(self):
        result = parse_chat("03/11/2026, 10:06 - A: kal paise dunga")
        if result.orders:
            assert result.orders[0].payment_status == PaymentStatus.udhaar

    def test_rehta_hai(self):
        o = first_order("04/11/2026, 09:45 - A: doodh ka 220 rehta hai")
        assert o.payment_status == PaymentStatus.udhaar

    def test_baaki(self):
        o = first_order("03/11/2026, 09:00 - A: 1kg cheeni 250 baaki")
        assert o.payment_status == PaymentStatus.udhaar

    def test_unknown(self):
        o = first_order("03/11/2026, 13:15 - A: 1kg chawal 300")
        assert o.payment_status == PaymentStatus.unknown


# ---------------------------------------------------------------------------
# 5. Item catalogue
# ---------------------------------------------------------------------------

class TestItemCatalogue:

    def test_cheeni(self):
        assert first_order("03/11/2026, 09:00 - A: 2kg cheeni Rs 500").item == "cheeni"

    def test_sugar_alias(self):
        assert first_order("03/11/2026, 09:00 - A: 2kg sugar Rs 500").item == "cheeni"

    def test_atta(self):
        assert first_order("03/11/2026, 10:05 - A: 3kg atta 450").item == "atta"

    def test_chawal(self):
        assert first_order("03/11/2026, 13:15 - A: 1kg chawal 300").item == "chawal"

    def test_doodh(self):
        assert first_order("03/11/2026, 11:30 - A: 1 litre doodh 220").item == "doodh"

    def test_anda(self):
        assert first_order("03/11/2026, 12:40 - A: 2 darjan anda 600").item == "anda"

    def test_chai(self):
        assert first_order("04/11/2026, 09:10 - A: 5 packet chai 750").item == "chai"

    def test_ghee(self):
        assert first_order("04/11/2026, 11:00 - A: 1kg ghee Rs 850").item == "ghee"

    def test_daal(self):
        assert first_order("04/11/2026, 12:30 - A: 2 kilo daal 400").item == "daal"

    def test_namak(self):
        assert first_order("03/11/2026, 09:00 - A: 1kg namak Rs 80").item == "namak"

    def test_sabun(self):
        assert first_order("03/11/2026, 09:00 - A: 2 packet sabun Rs 200").item == "sabun"

    def test_item_raw_fallback(self):
        o = first_order("03/11/2026, 09:00 - A: 2kg mashrooms Rs 400")
        assert o.item is None
        assert o.item_raw is not None
        assert len(o.item_raw.split()) <= 6


# ---------------------------------------------------------------------------
# 6. Media / voice note lines
# ---------------------------------------------------------------------------

class TestMediaLines:

    def test_media_omitted_not_order(self):
        result = parse_chat("04/11/2026, 10:20 - Usman: <Media omitted>")
        assert result.orders == []
        assert result.voice_note_count == 1

    def test_voice_message_not_order(self):
        result = parse_chat("04/11/2026, 10:21 - Usman: voice message")
        assert result.orders == []
        assert result.voice_note_count == 1

    def test_image_omitted_not_order(self):
        result = parse_chat("03/11/2026, 09:00 - A: image omitted")
        assert result.orders == []
        assert result.voice_note_count == 1

    def test_video_omitted_not_order(self):
        result = parse_chat("03/11/2026, 09:00 - A: video omitted")
        assert result.orders == []
        assert result.voice_note_count == 1


# ---------------------------------------------------------------------------
# 6b. Shop-sender lines never become orders (Spec 02 regression)
# ---------------------------------------------------------------------------

class TestShopSenderSkip:

    def test_store_sender_not_extracted(self):
        """Sender containing 'store' must never produce a CandidateOrder."""
        result = parse_chat(
            "03/11/2026, 09:20 - Noor General Store: Walaikum salam Ahmed bhai, bhej di, Rs 500"
        )
        assert result.orders == [], (
            "Shop reply line (sender contains 'Store') must not produce an order. "
            f"Got: {result.orders}"
        )

    def test_shop_sender_not_extracted(self):
        """Sender containing 'shop' must never produce a CandidateOrder."""
        result = parse_chat(
            "03/11/2026, 10:00 - My Shop: 2kg cheeni Rs 300"
        )
        assert result.orders == []

    def test_shop_sender_case_insensitive(self):
        """Match is case-insensitive (STORE, SHOP, Shop, etc.)."""
        result = parse_chat(
            "03/11/2026, 10:00 - GENERAL STORE BHAI: 1kg atta 200"
        )
        assert result.orders == []

    def test_noor_sample_line_not_extracted(self):
        """The exact false-positive line from the sample chat produces no order."""
        line = "03/11/2026, 09:20 - Noor General Store: Walaikum salam Ahmed bhai, bhej di, Rs 500"
        result = parse_chat(line)
        assert result.orders == [], (
            "Regression: Noor General Store reply must not yield a CandidateOrder"
        )

    def test_sample_chat_no_store_orders(self):
        """End-to-end: the full sample chat has no orders from store/shop senders."""
        text = SAMPLE_FILE.read_text(encoding="utf-8")
        result = parse_chat(text)
        store_orders = [
            o for o in result.orders
            if o.sender and ("store" in o.sender.lower() or "shop" in o.sender.lower())
        ]
        assert store_orders == [], (
            f"Store-sender orders still present after fix: {store_orders}"
        )

    def test_sample_extract_exactly_14_orders(self):
        """After the fix, the sample chat must yield exactly 14 orders (no extras, no misses)."""
        text = SAMPLE_FILE.read_text(encoding="utf-8")
        result = parse_chat(text)
        assert len(result.orders) == 14, (
            f"Expected 14 orders after parser fix, got {len(result.orders)}. "
            f"Orders: {[(o.sender, o.item, o.source_line) for o in result.orders]}"
        )


# ---------------------------------------------------------------------------
# 7. Confidence levels
# ---------------------------------------------------------------------------

class TestConfidence:

    def test_high_all_three(self):
        o = first_order("03/11/2026, 09:15 - A: 2kg cheeni Rs 500")
        assert o.confidence == Confidence.high

    def test_medium_item_amount_no_qty(self):
        o = first_order("03/11/2026, 09:00 - A: cheeni Rs 500")
        assert o.confidence == Confidence.medium

    def test_medium_qty_amount_no_item(self):
        o = first_order("03/11/2026, 09:00 - A: 2kg Rs 500")
        assert o.confidence == Confidence.medium

    def test_low_or_medium_payment_line(self):
        result = parse_chat("05/11/2026, 08:50 - A: bhai kal wale 450 de diye")
        if result.orders:
            assert result.orders[0].confidence in (Confidence.low, Confidence.medium)


# ---------------------------------------------------------------------------
# 8. Full sample-chat-export.txt line-by-line expected results
# ---------------------------------------------------------------------------

def _load_sample_result():
    text = SAMPLE_FILE.read_text(encoding="utf-8")
    return parse_chat(text)


def test_sample_file_exists():
    assert SAMPLE_FILE.exists(), f"Sample file not found: {SAMPLE_FILE}"


def test_sample_voice_notes_counted():
    result = _load_sample_result()
    assert result.voice_note_count == 2


def test_sample_parsed_lines_nonzero():
    result = _load_sample_result()
    assert result.parsed_line_count >= 18


def test_sample_orders_have_source_lines():
    result = _load_sample_result()
    for o in result.orders:
        assert isinstance(o.source_line, int)
        assert o.source_line > 0


def test_sample_all_orders_have_dates():
    result = _load_sample_result()
    for o in result.orders:
        assert o.date is not None, f"Order on source_line {o.source_line} has no date"


def test_sample_ahmed_cheeni_first():
    result = _load_sample_result()
    match = [o for o in result.orders
             if o.sender == "Ahmed" and o.item == "cheeni" and o.quantity == 2.0]
    assert match, "Expected Ahmed 2kg cheeni order"
    assert match[0].amount_pkr == 500.0


def test_sample_bilal_atta():
    result = _load_sample_result()
    match = [o for o in result.orders if o.sender == "Bilal" and o.item == "atta"]
    assert match
    assert match[0].amount_pkr == 450.0


def test_sample_sana_doodh_udhaar():
    result = _load_sample_result()
    match = [o for o in result.orders
             if o.sender == "Sana" and o.item == "doodh"
             and o.payment_status == PaymentStatus.udhaar]
    assert match, "Expected Sana doodh udhaar order"


def test_sample_usman_anda_paid():
    result = _load_sample_result()
    match = [o for o in result.orders
             if o.sender == "Usman" and o.item == "anda"
             and o.payment_status == PaymentStatus.paid]
    assert match, "Expected Usman anda paid order"


def test_sample_bilal_chai_kal_dunga():
    result = _load_sample_result()
    match = [o for o in result.orders
             if o.sender == "Bilal" and o.item == "chai"
             and o.payment_status == PaymentStatus.udhaar]
    assert match, "Expected Bilal chai kal dunga"


def test_sample_ahmed_ghee_paid():
    result = _load_sample_result()
    match = [o for o in result.orders
             if o.sender == "Ahmed" and o.item == "ghee"
             and o.payment_status == PaymentStatus.paid]
    assert match
    assert match[0].amount_pkr == 850.0


def test_sample_fatima_daal_udhaar():
    result = _load_sample_result()
    match = [o for o in result.orders
             if o.sender == "Fatima" and o.item == "daal"
             and o.payment_status == PaymentStatus.udhaar]
    assert match


def test_sample_usman_chawal_paid():
    result = _load_sample_result()
    match = [o for o in result.orders
             if o.sender == "Usman" and o.item == "chawal"
             and o.payment_status == PaymentStatus.paid]
    assert match
    assert match[0].amount_pkr == 900.0


def test_sample_do_kilo_atta_roman_urdu():
    """05/11: Ahmed says 'do kilo atta' — Roman-Urdu number word."""
    result = _load_sample_result()
    match = [o for o in result.orders
             if o.sender == "Ahmed" and o.item == "atta" and o.quantity == 2.0]
    assert match, "Roman-Urdu 'do' must parse as quantity 2"


def test_sample_sana_cheeni():
    result = _load_sample_result()
    match = [o for o in result.orders
             if o.sender == "Sana" and o.item == "cheeni"]
    assert match
    assert match[0].amount_pkr == 250.0


def test_sample_fatima_chawal():
    result = _load_sample_result()
    match = [o for o in result.orders
             if o.sender == "Fatima" and o.item == "chawal"]
    assert match


# ---------------------------------------------------------------------------
# Honest sample report — printed by pytest -s, never asserted as accuracy
# ---------------------------------------------------------------------------

# Labelled expected orders: (sender, item_or_None, payment_status_or_None)
_LABELLED = [
    ("Ahmed",  "cheeni",  PaymentStatus.unknown),   # 2kg cheeni Rs 500
    ("Bilal",  "atta",    PaymentStatus.unknown),    # 3kg atta 450 rupy
    ("Sana",   "doodh",   PaymentStatus.udhaar),     # 1 litre doodh 220 udhaar
    ("Usman",  "anda",    PaymentStatus.paid),       # 2 darjan anda 600 paid
    ("Fatima", "chawal",  PaymentStatus.unknown),    # 1kg chawal 300
    ("Ahmed",  "cheeni",  PaymentStatus.unknown),    # 2kg cheeni aur 500
    ("Bilal",  "chai",    PaymentStatus.udhaar),     # 5 packet chai 750 kal dunga
    ("Sana",   "doodh",   PaymentStatus.udhaar),     # doodh ka 220 rehta hai
    ("Ahmed",  "ghee",    PaymentStatus.paid),       # 1kg ghee Rs 850 paid
    ("Fatima", "daal",    PaymentStatus.udhaar),     # 2 kilo daal 400 udhaar
    ("Bilal",  None,      PaymentStatus.paid),       # kal wale 450 de diye
    ("Sana",   "cheeni",  PaymentStatus.unknown),    # 1kg cheeni 250
    ("Ahmed",  "atta",    PaymentStatus.unknown),    # do kilo atta 300
    ("Usman",  "chawal",  PaymentStatus.paid),       # 3kg chawal 900 paid
]


def test_honest_sample_report(capsys):
    """
    Prints an honest extraction report for the labelled sample set.
    NOT an accuracy percentage — measured on this small fictional set only.

    After the shop-sender fix:
      Expected 14 | Extracted 14 | Correct 14 | Missed 0 | Extra 0
    """
    result = _load_sample_result()

    by_sender: dict = defaultdict(list)
    for o in result.orders:
        by_sender[o.sender].append(o)

    correct = 0
    missed = 0

    for sender, exp_item, exp_pay in _LABELLED:
        candidates = by_sender.get(sender, [])
        found = any(
            (exp_item is None or o.item == exp_item)
            and (exp_pay is None or o.payment_status == exp_pay)
            for o in candidates
        )
        if found:
            correct += 1
        else:
            missed += 1

    # Extra orders (extracted but not in labelled set)
    extra = 0
    for o in result.orders:
        matched = any(
            o.sender == s and (exp_item is None or o.item == exp_item)
            for s, exp_item, _ in _LABELLED
        )
        if not matched:
            extra += 1

    report = (
        "\n" + "=" * 62 + "\n"
        "HONEST SAMPLE REPORT — labelled set only (fictional data)\n"
        "=" * 62 + "\n"
        f"  Expected orders in labelled set :  {len(_LABELLED)}\n"
        f"  Orders extracted by parser      :  {len(result.orders)}\n"
        f"  Correct (match expected)        :  {correct}\n"
        f"  Missed  (expected, not got)     :  {missed}\n"
        f"  Extra   (extracted, not expected):  {extra}\n"
        f"  Voice notes counted             :  {result.voice_note_count}\n"
        f"  Unparsed lines                  :  {result.unparsed_count}\n"
        "  NOTE: results measured on a small fictional sample only.\n"
        "  No accuracy percentage is claimed beyond this set.\n"
        + "=" * 62
    )
    print(report)
    # Hard assertions after parser fix: exactly 14/14 correct, 0 missed, 0 extra
    assert correct == 14, (
        f"Parser found {correct}/14 expected orders (expected 14 after shop-sender fix)."
    )
    assert missed == 0, f"Missed {missed} expected orders (expected 0 after fix)."
    assert extra == 0, (
        f"Extra {extra} unexpected orders (expected 0 after shop-sender fix). "
        f"Extras: {[o for o in result.orders if not any(o.sender == s and (ei is None or o.item == ei) for s,ei,_ in _LABELLED)]}"
    )
