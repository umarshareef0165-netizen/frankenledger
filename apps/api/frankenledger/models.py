"""
FrankenLedger data models — Spec 01 + Spec 02.
Pure dataclasses; no ORM, no database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Spec 02 — Parser models
# ---------------------------------------------------------------------------

class PaymentStatus(str, Enum):
    paid = "paid"
    udhaar = "udhaar"      # credit / will-pay-later
    promised = "promised"  # future payment mentioned without "kal"
    unknown = "unknown"


class Confidence(str, Enum):
    high = "high"      # quantity + amount + item all found
    medium = "medium"  # two of the three found
    low = "low"        # one of the three found


@dataclass
class CandidateOrder:
    """
    One candidate order extracted from a single WhatsApp chat line.
    Every field links back to source_line so the UI can show evidence.
    """
    date: Optional[str]          # ISO YYYY-MM-DD, or None if not parsed
    sender: Optional[str]
    item: Optional[str]          # matched catalogue keyword, or None
    item_raw: Optional[str]      # fallback: leftover text (≤6 words)
    quantity: Optional[float]
    unit: Optional[str]
    amount_pkr: Optional[float]
    payment_status: PaymentStatus
    source_line: int             # 1-based line number in the chat file
    confidence: Confidence


# ---------------------------------------------------------------------------
# Spec 01 — Ingest models
# ---------------------------------------------------------------------------

@dataclass
class ChatFile:
    """Summary returned after ingesting a WhatsApp chat export."""
    lines: int
    date_range: list[Optional[str]]   # [first_date_iso, last_date_iso]
    senders: list[str]
    parsed_lines: int
    unparsed_lines: int
    voice_notes: int
    preview_lines: list[str]          # first 5 parsed chat lines
    sample: bool = False
    label: str = ""


@dataclass
class LedgerFile:
    """Summary returned after ingesting an Excel / CSV ledger."""
    columns: list[str]
    row_count: int
    suggested_mapping: dict[str, Optional[str]]  # canonical_field -> col name
    preview_rows: list[dict]           # first 5 data rows as col->value dicts
    sample: bool = False
    label: str = ""


@dataclass
class LedgerRow:
    """One row from the uploaded ledger, after column mapping is confirmed."""
    row_index: int            # 1-based row number in the sheet / CSV
    date: Optional[str]
    customer: Optional[str]
    item: Optional[str]
    quantity: Optional[str]
    amount_pkr: Optional[float]
    paid: Optional[bool]
    raw: dict = field(default_factory=dict)  # original col->value for all cols
