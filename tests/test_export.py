"""
tests/test_export.py — Spec 05 backend-export tests.

Covers:
  1. POST /api/export/pdf
       - 200, Content-Type application/pdf
       - response bytes start with b'%PDF-'
       - non-trivial size (>= 1 KB)
       - totals values from the request body are present in the rendered PDF text
       - Content-Disposition carries a sensible filename
  2. POST /api/export/pdf — empty input
       - 200, valid PDF (%PDF- header), does not crash
  3. POST /api/export/xlsx
       - 200, correct Content-Type
       - bytes are a valid .xlsx (openpyxl can open them)
       - workbook has EXACTLY two sheets named "Ledger" and "Flags"
       - Ledger sheet has the right number of data rows
       - Flags sheet has the right number of data rows
       - Content-Disposition carries the filename
  4. POST /api/export/xlsx — empty input
       - 200, valid .xlsx with header rows only (Ledger + Flags sheets present)
  5. Key/secret safety
       - No API key value appears in the PDF or xlsx bytes
  6. End-to-end demo smoke test
       - POST /api/upload/sample  →  POST /api/reconcile
         →  POST /api/export/pdf (with totals from reconcile)
         →  POST /api/export/xlsx (with reconciled + flags from reconcile)
       - Verifies the full pipeline works with fictional sample data

All sample data is fictional — "Noor General Store" does not exist.

Run from repo root:
  apps/api/.venv/bin/python -m pytest tests/test_export.py -v
"""
from __future__ import annotations

import io
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps" / "api"))

import openpyxl
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared fixture data — small but realistic, fictional
# ---------------------------------------------------------------------------

_RECONCILED_ROWS = [
    {
        "row_index": 1,
        "date": "2026-11-03",
        "customer": "Ahmed",
        "item": "cheeni",
        "quantity": "2 kg",
        "amount_pkr": 550.0,
        "paid": False,
        "raw": {},
    },
    {
        "row_index": 2,
        "date": "2026-11-03",
        "customer": "Sana",
        "item": "doodh",
        "quantity": "1 litre",
        "amount_pkr": 220.0,
        "paid": True,
        "raw": {},
    },
    {
        "row_index": 3,
        "date": "2026-11-04",
        "customer": "Bilal",
        "item": "atta",
        "quantity": "5 kg",
        "amount_pkr": 450.0,
        "paid": False,
        "raw": {},
    },
]

_FLAGS = [
    {
        "flag_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "kind": "PRICE_MISMATCH",
        "chat_order": {
            "date": "2026-11-03",
            "sender": "Ahmed",
            "item": "cheeni",
            "item_raw": None,
            "quantity": 2.0,
            "unit": "kg",
            "amount_pkr": 500.0,
            "payment_status": "udhaar",
            "source_line": 3,
            "confidence": "high",
        },
        "ledger_rows": [
            {
                "row_index": 1,
                "date": "2026-11-03",
                "customer": "Ahmed",
                "item": "cheeni",
                "quantity": "2 kg",
                "amount_pkr": 550.0,
                "paid": False,
            }
        ],
        "explanation": "Ahmed cheeni: chat Rs 500 (line 3) vs ledger row 1 Rs 550.",
        "fix_description": "Choose chat or ledger amount.",
        "dismissed": False,
    },
    {
        "flag_id": "aaaaaaaa-0000-0000-0000-000000000002",
        "kind": "UNMATCHED_ORDER",
        "chat_order": {
            "date": "2026-11-04",
            "sender": "Bilal",
            "item": "atta",
            "item_raw": None,
            "quantity": 5.0,
            "unit": "kg",
            "amount_pkr": 450.0,
            "payment_status": "udhaar",
            "source_line": 8,
            "confidence": "high",
        },
        "ledger_rows": [],
        "explanation": "Bilal ordered atta (chat line 8) with no ledger row.",
        "fix_description": "Add a new udhaar ledger row.",
        "dismissed": True,
    },
]

_TOTALS = {"sold": 1220.0, "received": 220.0, "outstanding": 1000.0}


# ---------------------------------------------------------------------------
# 1. POST /api/export/pdf — normal payload
# ---------------------------------------------------------------------------

class TestExportPdf:

    def test_status_200(self):
        r = client.post("/api/export/pdf", json={
            "reconciled": _RECONCILED_ROWS,
            "totals": _TOTALS,
            "date": "2026-11-05",
            "flags": _FLAGS,
        })
        assert r.status_code == 200

    def test_content_type_is_pdf(self):
        r = client.post("/api/export/pdf", json={
            "reconciled": _RECONCILED_ROWS,
            "totals": _TOTALS,
            "date": "2026-11-05",
        })
        assert r.status_code == 200
        assert "application/pdf" in r.headers["content-type"]

    def test_bytes_start_with_pdf_header(self):
        r = client.post("/api/export/pdf", json={
            "reconciled": _RECONCILED_ROWS,
            "totals": _TOTALS,
            "date": "2026-11-05",
        })
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"

    def test_non_trivial_size(self):
        r = client.post("/api/export/pdf", json={
            "reconciled": _RECONCILED_ROWS,
            "totals": _TOTALS,
            "date": "2026-11-05",
        })
        assert r.status_code == 200
        # A real PDF with content should be well over 1 KB
        assert len(r.content) >= 1024

    def test_totals_appear_in_pdf_text(self):
        """
        Extract raw text from the PDF bytes and confirm the totals values
        from the request are present.  We scan for the amount strings that
        build_pdf writes via _fmt_amount(): "Rs 1220", "Rs 220", "Rs 1000".
        """
        r = client.post("/api/export/pdf", json={
            "reconciled": _RECONCILED_ROWS,
            "totals": _TOTALS,
            "date": "2026-11-05",
        })
        assert r.status_code == 200
        pdf_text = r.content.decode("latin-1")  # PDF streams are latin-1 safe
        # The formatted amounts written by _fmt_amount are "Rs 1220" etc.
        # They appear as plain text in the PDF content stream.
        assert "1220" in pdf_text
        assert "220" in pdf_text
        assert "1000" in pdf_text

    def test_date_in_content_disposition(self):
        r = client.post("/api/export/pdf", json={
            "reconciled": [],
            "totals": {},
            "date": "2026-11-05",
        })
        assert r.status_code == 200
        cd = r.headers.get("content-disposition", "")
        assert "2026-11-05" in cd
        assert ".pdf" in cd

    def test_customer_names_in_pdf(self):
        """Customer names from ledger rows should appear somewhere in the PDF."""
        r = client.post("/api/export/pdf", json={
            "reconciled": _RECONCILED_ROWS,
            "totals": _TOTALS,
            "date": "2026-11-05",
        })
        assert r.status_code == 200
        pdf_text = r.content.decode("latin-1")
        assert "Ahmed" in pdf_text
        assert "Bilal" in pdf_text


# ---------------------------------------------------------------------------
# 2. POST /api/export/pdf — empty input
# ---------------------------------------------------------------------------

class TestExportPdfEmpty:

    def test_empty_body_returns_200(self):
        r = client.post("/api/export/pdf", json={})
        assert r.status_code == 200

    def test_empty_body_is_valid_pdf(self):
        r = client.post("/api/export/pdf", json={})
        assert r.content[:5] == b"%PDF-"

    def test_empty_body_non_trivial_size(self):
        # Even an empty PDF should have a header, footer, and totals box
        r = client.post("/api/export/pdf", json={})
        assert len(r.content) >= 512

    def test_zero_totals_does_not_crash(self):
        r = client.post("/api/export/pdf", json={
            "reconciled": [],
            "totals": {"sold": 0, "received": 0, "outstanding": 0},
        })
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# 3. POST /api/export/xlsx — normal payload
# ---------------------------------------------------------------------------

class TestExportXlsx:

    def _get_xlsx(self, reconciled=None, flags=None):
        payload = {}
        if reconciled is not None:
            payload["reconciled"] = reconciled
        if flags is not None:
            payload["flags"] = flags
        return client.post("/api/export/xlsx", json=payload)

    def test_status_200(self):
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        assert r.status_code == 200

    def test_content_type_is_xlsx(self):
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        assert r.status_code == 200
        ct = r.headers["content-type"]
        assert "spreadsheetml" in ct or "xlsx" in ct or "openxmlformats" in ct

    def test_content_disposition_filename(self):
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        assert r.status_code == 200
        cd = r.headers.get("content-disposition", "")
        assert ".xlsx" in cd

    def test_bytes_are_valid_xlsx(self):
        """openpyxl must be able to open the bytes without error."""
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        assert r.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        assert wb is not None

    def test_exactly_two_sheets(self):
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        assert len(wb.sheetnames) == 2

    def test_sheet_names_are_ledger_and_flags(self):
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        assert wb.sheetnames[0] == "Ledger"
        assert wb.sheetnames[1] == "Flags"

    def test_ledger_sheet_has_correct_row_count(self):
        """Header row + 3 data rows = 4 total rows."""
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb["Ledger"]
        # max_row includes the header
        assert ws.max_row == 1 + len(_RECONCILED_ROWS)

    def test_ledger_sheet_header_row(self):
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb["Ledger"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        assert "Customer" in headers
        assert "Amount (Rs)" in headers
        assert "Paid" in headers

    def test_ledger_sheet_data_values(self):
        """Check one row's customer and amount survive the round-trip."""
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb["Ledger"]
        # Row 2 = first data row
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        cust_col = headers.index("Customer") + 1
        amt_col  = headers.index("Amount (Rs)") + 1
        assert ws.cell(2, cust_col).value == "Ahmed"
        assert ws.cell(2, amt_col).value == 550.0

    def test_flags_sheet_has_correct_row_count(self):
        """Header row + 2 flag rows = 3 total rows."""
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb["Flags"]
        assert ws.max_row == 1 + len(_FLAGS)

    def test_flags_sheet_header_row(self):
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb["Flags"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        assert "Kind" in headers
        assert "Status" in headers
        assert "Explanation" in headers

    def test_flags_sheet_status_values(self):
        """First flag is open, second is dismissed."""
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb["Flags"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        status_col = headers.index("Status") + 1
        assert ws.cell(2, status_col).value == "open"
        assert ws.cell(3, status_col).value == "dismissed"

    def test_flags_sheet_kind_values(self):
        r = self._get_xlsx(_RECONCILED_ROWS, _FLAGS)
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb["Flags"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        kind_col = headers.index("Kind") + 1
        assert ws.cell(2, kind_col).value == "PRICE_MISMATCH"
        assert ws.cell(3, kind_col).value == "UNMATCHED_ORDER"


# ---------------------------------------------------------------------------
# 4. POST /api/export/xlsx — empty input
# ---------------------------------------------------------------------------

class TestExportXlsxEmpty:

    def test_empty_body_returns_200(self):
        r = client.post("/api/export/xlsx", json={})
        assert r.status_code == 200

    def test_empty_body_is_valid_xlsx(self):
        r = client.post("/api/export/xlsx", json={})
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        assert wb is not None

    def test_empty_body_has_two_sheets(self):
        r = client.post("/api/export/xlsx", json={})
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        assert len(wb.sheetnames) == 2
        assert wb.sheetnames[0] == "Ledger"
        assert wb.sheetnames[1] == "Flags"

    def test_empty_ledger_sheet_has_only_header(self):
        r = client.post("/api/export/xlsx", json={})
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb["Ledger"]
        assert ws.max_row == 1  # header only

    def test_empty_flags_sheet_has_only_header(self):
        r = client.post("/api/export/xlsx", json={})
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb["Flags"]
        assert ws.max_row == 1  # header only


# ---------------------------------------------------------------------------
# 5. Key / secret safety
# ---------------------------------------------------------------------------

class TestExportSecretSafety:

    def test_pdf_response_contains_no_api_key(self, monkeypatch):
        """A fake API key must never appear in the PDF bytes."""
        fake_key = "FAKE_GEMINI_KEY_DO_NOT_LEAK_abc123xyz"
        monkeypatch.setenv("GEMINI_API_KEY", fake_key)
        r = client.post("/api/export/pdf", json={
            "reconciled": _RECONCILED_ROWS,
            "totals": _TOTALS,
            "date": "2026-11-05",
        })
        assert r.status_code == 200
        assert fake_key.encode() not in r.content

    def test_xlsx_response_contains_no_api_key(self, monkeypatch):
        """A fake API key must never appear in the xlsx bytes."""
        fake_key = "FAKE_GROQ_KEY_DO_NOT_LEAK_def456uvw"
        monkeypatch.setenv("GROQ_API_KEY", fake_key)
        r = client.post("/api/export/xlsx", json={
            "reconciled": _RECONCILED_ROWS,
            "flags": _FLAGS,
        })
        assert r.status_code == 200
        assert fake_key.encode() not in r.content

    def test_pdf_headers_contain_no_secrets(self, monkeypatch):
        fake_key = "FAKE_KEY_HEADER_CHECK_ghi789rst"
        monkeypatch.setenv("GEMINI_API_KEY", fake_key)
        r = client.post("/api/export/pdf", json={})
        header_str = str(r.headers).encode()
        assert fake_key.encode() not in header_str


# ---------------------------------------------------------------------------
# 6. End-to-end demo smoke test
#    sample data (fictional) → reconcile → PDF → xlsx
# ---------------------------------------------------------------------------

class TestDemoSmokeExport:

    def test_sample_reconcile_pdf_xlsx_end_to_end(self):
        """
        Full demo pipeline with the fictional Noor General Store sample data.

        Steps:
          1. Load sample data via POST /api/upload/sample
          2. Reconcile via POST /api/reconcile (session-driven, empty body)
          3. Export PDF via POST /api/export/pdf with reconcile output
          4. Export xlsx via POST /api/export/xlsx with reconcile output
          5. Assert each step succeeds and produces valid output.

        All data is fictional — Noor General Store does not exist.
        """
        # Step 1 — load sample
        r_sample = client.post("/api/upload/sample")
        assert r_sample.status_code == 200
        assert r_sample.json()["sample"] is True
        assert "fictional" in r_sample.json()["label"].lower()

        # Step 2 — reconcile (session-driven)
        r_reconcile = client.post("/api/reconcile", json={})
        assert r_reconcile.status_code == 200
        rec_body = r_reconcile.json()
        reconciled_rows = rec_body["reconciled"]
        flags           = rec_body["flags"]
        totals          = rec_body["totals"]

        # Sanity-check the reconcile output matches known sample expectations
        assert len(reconciled_rows) == 8           # 8 ledger rows in sample
        assert len(flags) == 10                    # 10 flags on sample set
        assert totals["sold"] == 4020.0
        assert totals["received"] == 1420.0
        assert totals["outstanding"] == 2600.0

        # Step 3 — PDF export
        r_pdf = client.post("/api/export/pdf", json={
            "reconciled": reconciled_rows,
            "totals": totals,
            "flags": flags,
            "date": "2026-11-05",
        })
        assert r_pdf.status_code == 200
        assert "application/pdf" in r_pdf.headers["content-type"]
        assert r_pdf.content[:5] == b"%PDF-"
        assert len(r_pdf.content) >= 2048  # real PDF with 8 rows should be >2 KB

        # Totals should appear in the rendered PDF
        pdf_text = r_pdf.content.decode("latin-1")
        assert "4020" in pdf_text
        assert "2600" in pdf_text

        # Step 4 — xlsx export
        r_xlsx = client.post("/api/export/xlsx", json={
            "reconciled": reconciled_rows,
            "flags": flags,
        })
        assert r_xlsx.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(r_xlsx.content))
        assert wb.sheetnames == ["Ledger", "Flags"]

        ws_ledger = wb["Ledger"]
        ws_flags  = wb["Flags"]

        # Header + 8 data rows
        assert ws_ledger.max_row == 1 + len(reconciled_rows)
        # Header + 10 flag rows
        assert ws_flags.max_row == 1 + len(flags)

        # Customer names from the sample appear in the Ledger sheet
        ledger_values = [
            ws_ledger.cell(row, 3).value   # column 3 = Customer
            for row in range(2, ws_ledger.max_row + 1)
        ]
        assert "Ahmed" in ledger_values
        assert "Bilal" in ledger_values

    def test_health_returns_ok_and_mode(self):
        """GET /api/health must return ok=True and a mode field."""
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert body.get("mode") in ("llm", "deterministic")
        assert body.get("status") == "ok"
