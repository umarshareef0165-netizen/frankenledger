"""
FrankenLedger — ledger ingest (Spec 01).
Reads .xlsx (openpyxl) and .csv (stdlib csv module).
Detects column headers via synonym mapping.
Never writes back to the original file.
"""
from __future__ import annotations

import csv
import io
from typing import Optional

import openpyxl

from .models import LedgerFile, LedgerRow

# ---------------------------------------------------------------------------
# Synonym map: canonical field -> list of header aliases (lower-cased)
# ---------------------------------------------------------------------------
_SYNONYMS: dict[str, list[str]] = {
    "date":     ["date", "tarikh", "taarikh", "day", "dt"],
    "customer": ["customer", "name", "party", "naam", "client", "buyer",
                 "grahak", "kharidar"],
    "item":     ["item", "items", "product", "cheez", "maal", "goods",
                 "description", "desc"],
    "quantity": ["quantity", "qty", "miqdar", "units",
                 "how many", "weight"],
    "amount":   ["amount", "rs", "price", "total", "raqam", "paisa",
                 "rupees", "rupay", "payment", "cost", "rate"],
    "paid":     ["paid", "status", "payment_status", "pay_status",
                 "cleared", "settled", "received"],
}

# Flatten to alias -> canonical
_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias: canonical
    for canonical, aliases in _SYNONYMS.items()
    for alias in aliases
}


def _suggest_mapping(columns: list[str]) -> dict[str, Optional[str]]:
    """
    Return {canonical: column_name_or_None} for all six canonical fields.
    Matching is case-insensitive; partial matches are tried as a fallback.
    """
    mapping: dict[str, Optional[str]] = {k: None for k in _SYNONYMS}
    lower_cols = {col.lower().strip(): col for col in columns}

    for lower_col, original_col in lower_cols.items():
        canonical = _ALIAS_TO_CANONICAL.get(lower_col)
        if canonical and mapping[canonical] is None:
            mapping[canonical] = original_col

    # Partial-match fallback: alias must appear as substring of column name
    for canonical, aliases in _SYNONYMS.items():
        if mapping[canonical] is not None:
            continue
        for lower_col, original_col in lower_cols.items():
            for alias in aliases:
                if alias in lower_col:   # alias is contained in column name
                    mapping[canonical] = original_col
                    break
            if mapping[canonical] is not None:
                break

    return mapping


def _rows_to_dicts(headers: list[str], rows: list[list]) -> list[dict]:
    result = []
    for row in rows:
        d = {}
        for i, h in enumerate(headers):
            d[h] = row[i] if i < len(row) else None
        result.append(d)
    return result


def _coerce_cell(val) -> Optional[str]:
    """Convert openpyxl cell value to string or None."""
    if val is None:
        return None
    return str(val).strip()


def read_xlsx(data: bytes) -> LedgerFile:
    """Parse .xlsx bytes; return LedgerFile summary."""
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    if not all_rows:
        return LedgerFile(
            columns=[], row_count=0,
            suggested_mapping={k: None for k in _SYNONYMS},
            preview_rows=[],
        )

    # First row is the header
    headers = [_coerce_cell(c) or f"col_{i}" for i, c in enumerate(all_rows[0])]
    data_rows = all_rows[1:]
    # Drop fully-empty rows (openpyxl can leave trailing None rows)
    data_rows = [r for r in data_rows if any(c is not None for c in r)]
    row_count = len(data_rows)

    str_rows = [[_coerce_cell(c) for c in row] for row in data_rows]
    preview = _rows_to_dicts(headers, str_rows[:5])
    mapping = _suggest_mapping(headers)

    return LedgerFile(
        columns=headers,
        row_count=row_count,
        suggested_mapping=mapping,
        preview_rows=preview,
    )


def read_csv(data: bytes) -> LedgerFile:
    """Parse .csv bytes; return LedgerFile summary."""
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    all_rows = list(reader)
    if not all_rows:
        return LedgerFile(
            columns=[], row_count=0,
            suggested_mapping={k: None for k in _SYNONYMS},
            preview_rows=[],
        )

    headers = [h.strip() or f"col_{i}" for i, h in enumerate(all_rows[0])]
    data_rows = all_rows[1:]
    row_count = len(data_rows)

    preview = _rows_to_dicts(headers, data_rows[:5])
    mapping = _suggest_mapping(headers)

    return LedgerFile(
        columns=headers,
        row_count=row_count,
        suggested_mapping=mapping,
        preview_rows=preview,
    )


def apply_mapping(
    ledger: LedgerFile,
    confirmed_mapping: dict[str, Optional[str]],
    raw_rows: list[dict],
) -> list[LedgerRow]:
    """
    Convert raw preview / full rows to LedgerRow using the owner-confirmed
    column mapping.  Amount is coerced to float; paid to bool.
    """
    result = []
    for idx, raw in enumerate(raw_rows, start=1):
        def _get(field: str) -> Optional[str]:
            col = confirmed_mapping.get(field)
            if col is None:
                return None
            return raw.get(col)

        amt_str = _get("amount")
        try:
            amt = float(str(amt_str).replace(",", "").replace("Rs", "").strip()) if amt_str else None
        except ValueError:
            amt = None

        paid_str = _get("paid")
        paid: Optional[bool] = None
        if paid_str is not None:
            paid = paid_str.strip().lower() in ("yes", "true", "1", "paid", "y")

        result.append(LedgerRow(
            row_index=idx,
            date=_get("date"),
            customer=_get("customer"),
            item=_get("item"),
            quantity=_get("quantity"),
            amount_pkr=amt,
            paid=paid,
            raw=raw,
        ))
    return result
