"""
tests/test_ingest.py — Spec 01 backend ingest tests.

Covers: empty file, wrong extension, unreadable file, missing columns,
        voice-note lines, 12-hour dates, sample endpoint.

Run from apps/api/:
  apps/api/.venv/bin/python -m pytest tests/test_ingest.py -v
"""
from __future__ import annotations

import io
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps" / "api"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

SAMPLES_DIR = pathlib.Path(__file__).parent.parent / "samples"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xlsx_bytes_minimal(headers: list[str], rows: list[list]) -> bytes:
    """Build a minimal .xlsx in memory."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _csv_bytes(headers: list[str], rows: list[list]) -> bytes:
    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for row in rows:
        w.writerow(row)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/upload/chat — wrong extension
# ---------------------------------------------------------------------------

def test_chat_wrong_extension():
    r = client.post(
        "/api/upload/chat",
        files={"file": ("ledger.xlsx", b"fake content", "application/octet-stream")},
    )
    assert r.status_code == 422
    assert "txt" in r.json()["detail"].lower()


def test_chat_empty_file():
    r = client.post(
        "/api/upload/chat",
        files={"file": ("chat.txt", b"", "text/plain")},
    )
    assert r.status_code == 422
    assert "empty" in r.json()["detail"].lower()


def test_chat_valid_txt():
    txt = b"03/11/2026, 09:15 - Ahmed: 2kg cheeni Rs 500\n"
    r = client.post(
        "/api/upload/chat",
        files={"file": ("chat.txt", txt, "text/plain")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["lines"] >= 1
    assert data["parsed_lines"] >= 1
    assert isinstance(data["senders"], list)
    assert "Ahmed" in data["senders"]


def test_chat_with_voice_notes():
    txt = (
        b"03/11/2026, 09:15 - Ahmed: 2kg cheeni Rs 500\n"
        b"04/11/2026, 10:20 - Usman: <Media omitted>\n"
        b"04/11/2026, 10:21 - Usman: voice message\n"
    )
    r = client.post(
        "/api/upload/chat",
        files={"file": ("chat.txt", txt, "text/plain")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["voice_notes"] == 2


def test_chat_12h_dates():
    txt = b"03/11/2026, 09:15 AM - Ahmed: 2kg cheeni Rs 500\n"
    r = client.post(
        "/api/upload/chat",
        files={"file": ("chat.txt", txt, "text/plain")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["parsed_lines"] >= 1
    assert data["date_range"][0] == "2026-11-03"


# ---------------------------------------------------------------------------
# POST /api/upload/ledger — wrong extension
# ---------------------------------------------------------------------------

def test_ledger_wrong_extension():
    r = client.post(
        "/api/upload/ledger",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 422
    assert "xlsx" in r.json()["detail"].lower() or "csv" in r.json()["detail"].lower()


def test_ledger_empty_file():
    r = client.post(
        "/api/upload/ledger",
        files={"file": ("ledger.csv", b"", "text/csv")},
    )
    assert r.status_code == 422
    assert "empty" in r.json()["detail"].lower()


def test_ledger_xlsx_all_columns():
    data = _xlsx_bytes_minimal(
        ["Date", "Customer", "Item", "Quantity", "Amount (Rs)", "Paid"],
        [["03/11/2026", "Ahmed", "cheeni", "2kg", 500, "No"]],
    )
    r = client.post(
        "/api/upload/ledger",
        files={"file": ("ledger.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] == 1
    m = body["suggested_mapping"]
    assert m["date"] is not None
    assert m["customer"] is not None
    assert m["amount"] is not None


def test_ledger_csv_all_columns():
    data = _csv_bytes(
        ["Date", "Customer", "Item", "Quantity", "Amount (Rs)", "Paid"],
        [["03/11/2026", "Bilal", "atta", "3kg", "450", "No"]],
    )
    r = client.post(
        "/api/upload/ledger",
        files={"file": ("ledger.csv", data, "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] == 1
    assert body["suggested_mapping"]["customer"] is not None


def test_ledger_missing_columns():
    """Ledger with only Date and Amount — customer/item/quantity/paid missing."""
    data = _xlsx_bytes_minimal(
        ["Date", "Amount"],
        [["03/11/2026", 500]],
    )
    r = client.post(
        "/api/upload/ledger",
        files={"file": ("ledger.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    body = r.json()
    m = body["suggested_mapping"]
    # Missing ones must be None, not guessed
    assert m["customer"] is None
    assert m["item"] is None
    assert m["quantity"] is None
    assert m["paid"] is None


def test_ledger_unreadable_file():
    """Corrupt bytes that are not valid xlsx."""
    r = client.post(
        "/api/upload/ledger",
        files={"file": ("ledger.xlsx", b"\x00\x01\x02JUNK", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 422
    assert "read" in r.json()["detail"].lower() or "ledger" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /api/upload/sample
# ---------------------------------------------------------------------------

def test_upload_sample_returns_fictional_label():
    r = client.post("/api/upload/sample")
    assert r.status_code == 200
    body = r.json()
    assert body["sample"] is True
    assert "fictional" in body["label"].lower()


def test_upload_sample_chat_has_lines():
    r = client.post("/api/upload/sample")
    assert r.status_code == 200
    chat = r.json()["chat"]
    assert chat["lines"] >= 15
    assert chat["sample"] is True


def test_upload_sample_ledger_has_rows():
    r = client.post("/api/upload/sample")
    assert r.status_code == 200
    ledger = r.json()["ledger"]
    assert ledger["row_count"] == 8


# ---------------------------------------------------------------------------
# POST /api/upload/confirm-mapping
# ---------------------------------------------------------------------------

def _upload_sample_ledger():
    data = _xlsx_bytes_minimal(
        ["Date", "Customer", "Item", "Quantity", "Amount (Rs)", "Paid"],
        [["03/11/2026", "Ahmed", "cheeni", "2kg", 500, "No"]],
    )
    client.post(
        "/api/upload/ledger",
        files={"file": ("ledger.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def test_confirm_mapping_ok():
    _upload_sample_ledger()
    r = client.post(
        "/api/upload/confirm-mapping",
        json={"mapping": {
            "date": "Date",
            "customer": "Customer",
            "item": "Item",
            "quantity": "Quantity",
            "amount": "Amount (Rs)",
            "paid": "Paid",
        }},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_confirm_mapping_with_nulls():
    _upload_sample_ledger()
    r = client.post(
        "/api/upload/confirm-mapping",
        json={"mapping": {
            "date": "Date",
            "customer": None,
            "item": None,
            "quantity": None,
            "amount": "Amount (Rs)",
            "paid": None,
        }},
    )
    assert r.status_code == 200
    body = r.json()
    assert "customer" in body["missing_fields"]


def test_confirm_mapping_no_ledger_uploaded():
    # Reset session by uploading a sample first, then call confirm without ledger
    from main import _SESSION
    _SESSION["ledger_summary"] = None
    r = client.post(
        "/api/upload/confirm-mapping",
        json={"mapping": {"date": "Date", "customer": None, "item": None,
                          "quantity": None, "amount": None, "paid": None}},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/parse
# ---------------------------------------------------------------------------

def test_parse_no_chat_uploaded():
    from main import _SESSION
    _SESSION["chat_text"] = None
    r = client.post("/api/parse")
    assert r.status_code == 400


def test_parse_returns_orders():
    txt = (
        b"03/11/2026, 09:15 - Ahmed: 2kg cheeni Rs 500\n"
        b"03/11/2026, 11:30 - Sana: 1 litre doodh 220 udhaar\n"
        b"04/11/2026, 10:20 - Usman: <Media omitted>\n"
    )
    client.post(
        "/api/upload/chat",
        files={"file": ("chat.txt", txt, "text/plain")},
    )
    r = client.post("/api/parse")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "deterministic"
    assert body["voice_notes"] == 1
    orders = body["orders"]
    assert len(orders) >= 2
    # Each order must have source_line
    for o in orders:
        assert "source_line" in o
        assert o["source_line"] > 0
        assert "confidence" in o
        assert o["confidence"] in ("high", "medium", "low")


def test_parse_sample_end_to_end():
    """Full demo flow: upload sample, parse, get orders."""
    client.post("/api/upload/sample")
    r = client.post("/api/parse")
    assert r.status_code == 200
    body = r.json()
    assert body["sample"] is True
    assert body["order_count"] >= 10
    senders = {o["sender"] for o in body["orders"]}
    assert "Ahmed" in senders
    assert "Bilal" in senders
