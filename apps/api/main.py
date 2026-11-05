"""
FrankenLedger — FastAPI backend, Spec 01 + Spec 02 + Spec 03 + Spec 04 + Spec 05.
Endpoints:
  GET  /api/health
  POST /api/upload/chat
  POST /api/upload/ledger
  POST /api/upload/sample
  POST /api/upload/confirm-mapping
  POST /api/parse
  POST /api/reconcile
  POST /api/reconcile/fix
  GET  /api/agent/status
  POST /api/agent/explain
  POST /api/agent/draft-reply
  POST /api/agent/structure
  POST /api/export/pdf
  POST /api/export/xlsx

Uploaded files live only for the session (in-memory).
The original ledger file is NEVER overwritten.
"""
from __future__ import annotations

import io
import os
import pathlib

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Any, Optional

from frankenledger.parser import parse_chat
from frankenledger.ledger_io import read_xlsx, read_csv, apply_mapping
from frankenledger.reconciler import reconcile, apply_fix, ReconciledLedger
from frankenledger.models import CandidateOrder, LedgerRow, PaymentStatus, Confidence
from frankenledger import agent as _agent
from frankenledger.ledger_export import build_pdf, build_xlsx as _build_xlsx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = pathlib.Path(__file__).parent
_SAMPLES_DIR = _HERE.parent.parent / "samples"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="FrankenLedger API",
    description=(
        "Deterministic WhatsApp chat + Excel ledger reconciler. "
        "No accounts, no database, no retained data. "
        "Sample data is fictional — Noor General Store does not exist."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory session state (single-process; ephemeral)
# ---------------------------------------------------------------------------
_SESSION: dict = {
    "chat_text": None,          # str
    "chat_summary": None,       # dict
    "ledger_bytes": None,       # bytes
    "ledger_ext": None,         # ".xlsx" | ".csv"
    "ledger_summary": None,     # dict
    "confirmed_mapping": None,  # dict
    "is_sample": False,
    "reconciled": None,         # ReconciledLedger (Spec 03)
}


def _reset_session() -> None:
    for key in _SESSION:
        _SESSION[key] = None
    _SESSION["is_sample"] = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chat_summary_dict(text: str, sample: bool = False) -> dict:
    from frankenledger.parser import parse_chat as _pc
    result = _pc(text)
    dates = sorted(set(result.dates))
    date_range = [dates[0], dates[-1]] if len(dates) >= 2 else (
        [dates[0], dates[0]] if dates else [None, None]
    )
    lines_total = len([l for l in text.splitlines() if l.strip() and not l.startswith("#")])
    senders = sorted(result.senders)
    preview = []
    for ln in text.splitlines()[:30]:
        s = ln.strip()
        if s and not s.startswith("#"):
            preview.append(s)
        if len(preview) == 5:
            break
    return {
        "lines": lines_total,
        "date_range": date_range,
        "senders": senders,
        "parsed_lines": result.parsed_line_count,
        "unparsed_lines": result.unparsed_count,
        "voice_notes": result.voice_note_count,
        "preview_lines": preview,
        "sample": sample,
        "label": "fictional sample data — Noor General Store" if sample else "",
    }


def _ledger_summary_dict(file_obj, sample: bool = False) -> dict:
    data = file_obj if isinstance(file_obj, bytes) else file_obj
    # already bytes at call site
    return data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    """
    Service health check.

    Response: {ok: true, status: "ok", mode: "llm"|"deterministic",
               service: str, version: str}

    `mode` mirrors /api/agent/status so the frontend can show the mode badge
    without a second round-trip.  Existing callers that only read `status`
    are unaffected.
    """
    agent_mode = _agent.get_mode()
    return {
        "ok": True,
        "status": "ok",
        "mode": agent_mode["mode"],
        "service": "FrankenLedger API",
        "version": "0.1.0",
    }


@app.post("/api/upload/chat")
async def upload_chat(file: UploadFile = File(...)) -> dict:
    """Accept a WhatsApp chat export (.txt)."""
    filename = file.filename or ""
    if not filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=422,
            detail=f"Expected a .txt file, got: '{filename}'. "
                   "Please export your WhatsApp chat as a .txt file.",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read file: {exc}") from exc

    summary = _chat_summary_dict(text, sample=False)
    _SESSION["chat_text"] = text
    _SESSION["chat_summary"] = summary
    _SESSION["is_sample"] = False
    return summary


@app.post("/api/upload/ledger")
async def upload_ledger(file: UploadFile = File(...)) -> dict:
    """Accept a ledger file (.xlsx or .csv)."""
    filename = file.filename or ""
    ext = pathlib.Path(filename).suffix.lower()
    if ext not in (".xlsx", ".csv"):
        raise HTTPException(
            status_code=422,
            detail=f"Expected .xlsx or .csv, got: '{filename}'. "
                   "Please upload an Excel or CSV file.",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    try:
        if ext == ".xlsx":
            ledger_file = read_xlsx(raw)
        else:
            ledger_file = read_csv(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not read ledger file: {exc}",
        ) from exc

    _SESSION["ledger_bytes"] = raw
    _SESSION["ledger_ext"] = ext
    _SESSION["ledger_summary"] = ledger_file
    summary = {
        "columns": ledger_file.columns,
        "row_count": ledger_file.row_count,
        "suggested_mapping": ledger_file.suggested_mapping,
        "preview_rows": ledger_file.preview_rows,
        "sample": ledger_file.sample,
        "label": ledger_file.label,
    }
    return summary


@app.post("/api/upload/sample")
async def upload_sample() -> dict:
    """Load the fictional sample files. labelled sample=true."""
    chat_path = _SAMPLES_DIR / "sample-chat-export.txt"
    ledger_path = _SAMPLES_DIR / "sample-ledger.xlsx"

    if not chat_path.exists():
        raise HTTPException(
            status_code=500,
            detail="Sample chat file not found. Check samples/ directory.",
        )
    if not ledger_path.exists():
        raise HTTPException(
            status_code=500,
            detail="Sample ledger file not found. Check samples/ directory.",
        )

    chat_text = chat_path.read_text(encoding="utf-8")
    ledger_raw = ledger_path.read_bytes()

    chat_summary = _chat_summary_dict(chat_text, sample=True)
    ledger_obj = read_xlsx(ledger_raw)
    ledger_obj.sample = True
    ledger_obj.label = "fictional sample data — Noor General Store"

    _SESSION["chat_text"] = chat_text
    _SESSION["chat_summary"] = chat_summary
    _SESSION["ledger_bytes"] = ledger_raw
    _SESSION["ledger_ext"] = ".xlsx"
    _SESSION["ledger_summary"] = ledger_obj
    _SESSION["is_sample"] = True

    return {
        "sample": True,
        "label": "fictional sample data — Noor General Store",
        "chat": chat_summary,
        "ledger": {
            "columns": ledger_obj.columns,
            "row_count": ledger_obj.row_count,
            "suggested_mapping": ledger_obj.suggested_mapping,
            "preview_rows": ledger_obj.preview_rows,
            "sample": True,
            "label": "fictional sample data — Noor General Store",
        },
    }


class ConfirmMappingRequest(BaseModel):
    mapping: dict[str, Optional[str]]


@app.post("/api/upload/confirm-mapping")
def confirm_mapping(body: ConfirmMappingRequest) -> dict:
    """
    Owner-confirmed column mapping.
    Accepted fields: date, customer, item, quantity, amount, paid.
    Any may be None (missing column).
    """
    if _SESSION["ledger_summary"] is None:
        raise HTTPException(
            status_code=400,
            detail="No ledger uploaded yet. Upload a ledger first.",
        )
    allowed = {"date", "customer", "item", "quantity", "amount", "paid"}
    unknown = set(body.mapping) - allowed
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown mapping fields: {sorted(unknown)}. "
                   f"Allowed: {sorted(allowed)}.",
        )
    _SESSION["confirmed_mapping"] = body.mapping
    missing = [f for f, col in body.mapping.items() if col is None]
    return {
        "status": "ok",
        "confirmed_mapping": body.mapping,
        "missing_fields": missing,
        "note": (
            f"Missing columns: {missing}. "
            "These fields will be empty in the reconciler."
            if missing else "All fields mapped."
        ),
    }


@app.post("/api/parse")
def parse() -> dict:
    """
    Run the deterministic parser on the uploaded chat.
    Returns candidate orders with source line numbers.
    No LLM is used; if no key is configured, this is the only mode.
    """
    if _SESSION["chat_text"] is None:
        raise HTTPException(
            status_code=400,
            detail="No chat file uploaded. Upload a chat export first.",
        )

    result = parse_chat(_SESSION["chat_text"])

    orders = []
    for o in result.orders:
        orders.append({
            "date": o.date,
            "sender": o.sender,
            "item": o.item,
            "item_raw": o.item_raw,
            "quantity": o.quantity,
            "unit": o.unit,
            "amount_pkr": o.amount_pkr,
            "payment_status": o.payment_status.value,
            "source_line": o.source_line,
            "confidence": o.confidence.value,
        })

    return {
        "mode": "deterministic",
        "label": "deterministic mode — parser + rules only",
        "sample": _SESSION.get("is_sample", False),
        "parsed_lines": result.parsed_line_count,
        "unparsed_lines": result.unparsed_count,
        "voice_notes": result.voice_note_count,
        "orders": orders,
        "order_count": len(orders),
    }


# ---------------------------------------------------------------------------
# Spec 03 — Reconciliation endpoints
# ---------------------------------------------------------------------------

def _serialise_reconciled(result: ReconciledLedger) -> dict:
    """Convert a ReconciledLedger to a JSON-safe dict."""
    rows = []
    for r in result.rows:
        rows.append({
            "row_index": r.row_index,
            "date": r.date,
            "customer": r.customer,
            "item": r.item,
            "quantity": r.quantity,
            "amount_pkr": r.amount_pkr,
            "paid": r.paid,
            "raw": r.raw,
        })

    flags = []
    for f in result.flags:
        chat_order = None
        if f.chat_order is not None:
            o = f.chat_order
            chat_order = {
                "date": o.date,
                "sender": o.sender,
                "item": o.item,
                "item_raw": o.item_raw,
                "quantity": o.quantity,
                "unit": o.unit,
                "amount_pkr": o.amount_pkr,
                "payment_status": o.payment_status.value,
                "source_line": o.source_line,
                "confidence": o.confidence.value,
            }
        flags.append({
            "flag_id": f.flag_id,
            "kind": f.kind,
            "chat_order": chat_order,
            "ledger_rows": [
                {
                    "row_index": lr.row_index,
                    "date": lr.date,
                    "customer": lr.customer,
                    "item": lr.item,
                    "quantity": lr.quantity,
                    "amount_pkr": lr.amount_pkr,
                    "paid": lr.paid,
                }
                for lr in f.ledger_rows
            ],
            "explanation": f.explanation,
            "fix_description": f.fix_description,
            "dismissed": f.dismissed,
        })

    totals = {
        "sold": result.totals.sold,
        "received": result.totals.received,
        "outstanding": result.totals.outstanding,
    }

    return {"reconciled": rows, "flags": flags, "totals": totals}


def _deserialise_orders(raw_orders: list[dict]) -> list[CandidateOrder]:
    """Rebuild CandidateOrder objects from the JSON payload."""
    orders = []
    for o in raw_orders:
        orders.append(CandidateOrder(
            date=o.get("date"),
            sender=o.get("sender"),
            item=o.get("item"),
            item_raw=o.get("item_raw"),
            quantity=o.get("quantity"),
            unit=o.get("unit"),
            amount_pkr=float(o["amount_pkr"]) if o.get("amount_pkr") is not None else None,
            payment_status=PaymentStatus(o.get("payment_status", "unknown")),
            source_line=int(o.get("source_line", 0)),
            confidence=Confidence(o.get("confidence", "low")),
        ))
    return orders


def _deserialise_ledger_rows(raw_rows: list[dict]) -> list[LedgerRow]:
    """Rebuild LedgerRow objects from the JSON payload."""
    rows = []
    for r in raw_rows:
        rows.append(LedgerRow(
            row_index=int(r.get("row_index", 0)),
            date=r.get("date"),
            customer=r.get("customer"),
            item=r.get("item"),
            quantity=r.get("quantity"),
            amount_pkr=float(r["amount_pkr"]) if r.get("amount_pkr") is not None else None,
            paid=r.get("paid"),
            raw=r.get("raw", {}),
        ))
    return rows


class ReconcileRequest(BaseModel):
    orders: list[dict] = []
    ledger_rows: list[dict] = []
    mapping: Optional[dict] = None  # accepted but unused — mapping already applied upstream


class FixRequest(BaseModel):
    flag_id: str
    action: str          # "accept" | "edit" | "dismiss"
    patch: Optional[dict] = None


def _read_all_ledger_rows() -> list[LedgerRow]:
    """
    Re-read ALL rows from the session's uploaded ledger bytes using the
    confirmed (or suggested) column mapping.  Raises HTTPException 400 if
    no ledger is in session.
    """
    ledger_bytes = _SESSION.get("ledger_bytes")
    ledger_ext   = _SESSION.get("ledger_ext")
    if not ledger_bytes or not ledger_ext:
        raise HTTPException(
            status_code=400,
            detail="No ledger in session. Upload a ledger file first.",
        )

    # Parse the raw file to get the full column list and ALL data rows
    if ledger_ext == ".xlsx":
        import openpyxl, io as _io
        wb = openpyxl.load_workbook(_io.BytesIO(ledger_bytes), read_only=True, data_only=True)
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            return []
        headers = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(all_rows[0])]
        data_rows = all_rows[1:]
        data_rows = [r for r in data_rows if any(c is not None for c in r)]
        raw_dicts = [
            {headers[i]: (str(c).strip() if c is not None else None) for i, c in enumerate(row)}
            for row in data_rows
        ]
    else:  # .csv
        import csv as _csv, io as _io
        text = ledger_bytes.decode("utf-8-sig", errors="replace")
        reader = _csv.reader(_io.StringIO(text))
        all_rows = list(reader)
        if not all_rows:
            return []
        headers = [h.strip() or f"col_{i}" for i, h in enumerate(all_rows[0])]
        data_rows = all_rows[1:]
        raw_dicts = [{headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))} for row in data_rows]

    # Use confirmed mapping if available, else fall back to suggested
    mapping = _SESSION.get("confirmed_mapping")
    if not mapping:
        ledger_summary = _SESSION.get("ledger_summary")
        if ledger_summary is not None:
            mapping = ledger_summary.suggested_mapping
        else:
            # Build mapping from headers directly
            from frankenledger.ledger_io import _suggest_mapping
            mapping = _suggest_mapping(headers)

    return apply_mapping(None, mapping, raw_dicts)  # ledger param unused in apply_mapping


@app.post("/api/reconcile")
def reconcile_endpoint(body: ReconcileRequest) -> dict:
    """
    Run the deterministic reconciler.

    Session-driven mode (preferred for the demo flow):
      POST with an empty body (or omit orders/ledger_rows).
      The endpoint re-reads ALL ledger rows from the session's uploaded file,
      re-parses the session's chat text, and reconciles.
      Returns 400 if no chat or no ledger is in session.

    Explicit mode (forward-compat):
      POST with non-empty orders + ledger_rows lists; those are used directly.

    Request body (all optional):
      orders      – list of CandidateOrder dicts
      ledger_rows – list of LedgerRow dicts
      mapping     – accepted, unused (mapping applied upstream)

    Response:
      { reconciled: [...rows], flags: [...flags], totals: {sold, received, outstanding} }

    The result is stored in the session so /api/reconcile/fix can update it.
    """
    # Decide whether to use explicit body data or session-driven mode
    use_explicit = bool(body.orders) and bool(body.ledger_rows)

    if use_explicit:
        try:
            orders = _deserialise_orders(body.orders)
            rows = _deserialise_ledger_rows(body.ledger_rows)
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid payload: {exc}") from exc
    else:
        # Session-driven mode
        if _SESSION.get("chat_text") is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No chat in session and no orders provided in request body. "
                    "Upload a chat export first (POST /api/upload/chat or /api/upload/sample)."
                ),
            )
        if _SESSION.get("ledger_bytes") is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No ledger in session and no ledger_rows provided in request body. "
                    "Upload a ledger file first (POST /api/upload/ledger or /api/upload/sample)."
                ),
            )

        # Re-parse chat and re-read all ledger rows from session
        from frankenledger.parser import parse_chat as _parse_chat
        parse_result = _parse_chat(_SESSION["chat_text"])
        orders = parse_result.orders
        rows = _read_all_ledger_rows()

    result = reconcile(orders, rows)
    _SESSION["reconciled"] = result

    return _serialise_reconciled(result)


@app.post("/api/reconcile/fix")
def reconcile_fix(body: FixRequest) -> dict:
    """
    Apply a fix to the current reconciled ledger held in session.

    Request body:
      flag_id – UUID of the flag to act on
      action  – "accept" | "edit" | "dismiss"
      patch   – optional dict for "edit" action, e.g. {"amount_pkr": 150, "paid": true}

    Response:
      { reconciled: [...rows], flags: [...flags], totals: {sold, received, outstanding} }

    Totals recompute after every fix. The reconciled session state is updated in place.
    """
    if _SESSION.get("reconciled") is None:
        raise HTTPException(
            status_code=400,
            detail="No reconciled ledger in session. Run POST /api/reconcile first.",
        )

    action = body.action
    if action not in ("accept", "edit", "dismiss"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action {action!r}. Must be one of: accept, edit, dismiss.",
        )

    try:
        updated = apply_fix(
            reconciled=_SESSION["reconciled"],
            flag_id=body.flag_id,
            action=action,
            patch=body.patch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _SESSION["reconciled"] = updated
    return _serialise_reconciled(updated)


# ---------------------------------------------------------------------------
# Spec 04 — Agent endpoints
# ---------------------------------------------------------------------------

@app.get("/api/agent/status")
def agent_status() -> dict:
    """
    Return the current agent mode.

    Response: {mode: "llm"|"deterministic", provider?: "gemini"|"groq"}

    When no LLM key is configured (GEMINI_API_KEY or GROQ_API_KEY), mode is
    "deterministic" and the UI must show "Deterministic mode — parser + rules
    only, no AI key configured".  The key value is never returned.
    """
    status = _agent.get_mode()
    if status["mode"] == "deterministic":
        status["label"] = (
            "Deterministic mode — parser + rules only, no AI key configured."
        )
    else:
        status["label"] = (
            f"LLM mode — {status.get('provider', 'unknown')} (hosted API). "
            "No fine-tuning. Agent output is a suggestion only."
        )
    return status


class ExplainRequest(BaseModel):
    flag: dict


@app.post("/api/agent/explain")
def agent_explain(body: ExplainRequest) -> dict:
    """
    Explain a reconciliation flag in plain language.

    Request:  {flag: <flag dict from /api/reconcile>}
    Response: {explanation: str, source: "llm"|"template", agent_note?: str}

    When no key is set, source is "template" and a deterministic explanation
    is generated from the flag kind and evidence (chat line + ledger row).
    Agent output is always a suggestion — it never changes the ledger.
    """
    result = _agent.explain(body.flag)
    return result


class DraftReplyRequest(BaseModel):
    order: dict


@app.post("/api/agent/draft-reply")
def agent_draft_reply(body: DraftReplyRequest) -> dict:
    """
    Draft a short WhatsApp reply for an unpaid order.

    Request:  {order: <CandidateOrder dict>}
    Response: {draft: str, source: "llm"|"template", agent_note?: str}

    Draft is in Roman Urdu/English mix (e.g. "Salam Ahmed bhai,
    cheeni ka Rs 500 rehta hai, kal de dena. Shukriya.").
    When no key is set, source is "template".
    Agent output is always a suggestion — it never sends a message.
    """
    result = _agent.draft_reply(body.order)
    return result


class StructureRequest(BaseModel):
    candidate_orders: list[dict]


@app.post("/api/agent/structure")
def agent_structure(body: StructureRequest) -> dict:
    """
    Attempt to structure / clean candidate orders.

    Request:  {candidate_orders: [<CandidateOrder dict>, ...]}
    Response: {orders: [...], source: "llm"|"deterministic", agent_note?: str}

    When no key is set (or LLM fails), source is "deterministic" and the
    candidate orders are returned as-is from the parser.
    Agent output is always a suggestion — it never changes the ledger.
    """
    result = _agent.structure(body.candidate_orders)
    return result


# ---------------------------------------------------------------------------
# Spec 05 — Export endpoints
# ---------------------------------------------------------------------------

class ExportPdfRequest(BaseModel):
    reconciled: list[dict] = []
    totals: Optional[dict] = None
    date: Optional[str] = None
    flags: list[dict] = []
    shop_name: Optional[str] = None


@app.post("/api/export/pdf")
def export_pdf(body: ExportPdfRequest) -> Response:
    """
    Generate a daily A4 paper ledger as a real PDF.

    Request body (all fields optional — empty input returns a valid PDF):
      reconciled : list of reconciled ledger-row dicts
      totals     : {sold, received, outstanding}
      date       : ISO date string for the report header (default: today)
      flags      : list of flag dicts (dismissed flags appear in PDF)
      shop_name  : overrides "Noor General Store (sample)" in the header

    Response: application/pdf bytes.
    Content-Disposition: attachment; filename="frankenledger-YYYY-MM-DD.pdf"
    """
    from datetime import date as _date

    payload = {
        "reconciled": body.reconciled,
        "totals": body.totals or {},
        "date": body.date or str(_date.today()),
        "flags": body.flags,
        "shop_name": body.shop_name,
    }
    try:
        pdf_bytes = build_pdf(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {exc}",
        ) from exc

    report_date = payload["date"]
    filename = f"frankenledger-{report_date}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class ExportXlsxRequest(BaseModel):
    reconciled: list[dict] = []
    flags: list[dict] = []


@app.post("/api/export/xlsx")
def export_xlsx(body: ExportXlsxRequest) -> Response:
    """
    Export a clean .xlsx workbook with two sheets: Ledger and Flags.

    Request body (all fields optional — empty input returns a valid workbook):
      reconciled : list of reconciled ledger-row dicts
      flags      : list of flag dicts

    Response: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet bytes.
    Content-Disposition: attachment; filename="frankenledger-ledger.xlsx"

    The original uploaded file is NEVER overwritten — this is a fresh download.
    """
    payload = {
        "reconciled": body.reconciled,
        "flags": body.flags,
    }
    try:
        xlsx_bytes = _build_xlsx(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"XLSX generation failed: {exc}",
        ) from exc

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="frankenledger-ledger.xlsx"'},
    )
