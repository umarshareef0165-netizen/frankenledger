"""
FrankenLedger — export helpers, Spec 05.

Two functions:
  build_pdf(payload: dict) -> bytes
      Renders a daily A4 paper ledger as a real PDF using reportlab.
  build_xlsx(payload: dict) -> bytes
      Produces a clean .xlsx with two sheets (Ledger, Flags) using openpyxl.

Neither function touches the original uploaded file.
Sample data is labelled "fictional — Noor General Store" wherever it appears.

Dependencies (already in requirements.txt): reportlab==5.1.0, openpyxl==3.1.5
"""
from __future__ import annotations

import io
from datetime import date as _date
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_amount(val: Any) -> str:
    """Format a numeric amount as 'Rs X' or 'Rs X.XX'."""
    if val is None:
        return "—"
    try:
        f = float(val)
        return f"Rs {int(f)}" if f == int(f) else f"Rs {f:.2f}"
    except (TypeError, ValueError):
        return str(val)


def _fmt_date(val: Any) -> str:
    if val is None:
        return "—"
    return str(val)


def _flag_status(flag: dict) -> str:
    if flag.get("dismissed"):
        # Distinguish edit (patch applied) vs plain dismiss
        return "fixed" if flag.get("_patched") else "dismissed"
    return "open"


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------

def build_pdf(payload: dict) -> bytes:
    """
    Build a daily A4 paper ledger PDF.

    Expected payload keys (all optional — empty input → valid PDF with zero rows):
      reconciled : list of reconciled ledger-row dicts
                   (keys: row_index, date, customer, item, quantity,
                          amount_pkr, paid)
      totals     : dict with sold, received, outstanding (floats)
      date       : ISO date string for the report header (defaults to today)
      shop_name  : str — overrides default "Noor General Store (sample)"

    Returns raw PDF bytes starting with b'%PDF'.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    rows: list[dict] = payload.get("reconciled") or []
    totals: dict = payload.get("totals") or {}
    report_date: str = payload.get("date") or str(_date.today())
    shop_name: str = payload.get("shop_name") or "Noor General Store (sample)"
    flags: list[dict] = payload.get("flags") or []

    # --- styles ---
    styles = getSampleStyleSheet()

    style_title = ParagraphStyle(
        "FL_Title",
        parent=styles["Normal"],
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    )
    style_subtitle = ParagraphStyle(
        "FL_Subtitle",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        alignment=TA_CENTER,
        fontName="Helvetica",
        textColor=colors.HexColor("#555555"),
        spaceAfter=2,
    )
    style_label = ParagraphStyle(
        "FL_Label",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        fontName="Helvetica-Oblique",
        textColor=colors.HexColor("#888888"),
        spaceAfter=10,
    )
    style_section = ParagraphStyle(
        "FL_Section",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        fontName="Helvetica-Bold",
        spaceBefore=12,
        spaceAfter=4,
    )
    style_footer = ParagraphStyle(
        "FL_Footer",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        fontName="Helvetica-Oblique",
        textColor=colors.HexColor("#888888"),
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2.5 * cm,
        title=f"FrankenLedger Daily Ledger — {report_date}",
        author="FrankenLedger",
        pageCompression=0,   # keep content streams uncompressed so text is grep-able
    )

    story: list = []

    # --- Header ---
    story.append(Paragraph(shop_name, style_title))
    story.append(Paragraph(f"Daily Ledger — {report_date}", style_subtitle))
    story.append(Paragraph(
        "Fictional sample data — Noor General Store does not exist.",
        style_label,
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CCCCCC")))
    story.append(Spacer(1, 0.3 * cm))

    # --- Totals box ---
    sold = totals.get("sold", 0.0) or 0.0
    received = totals.get("received", 0.0) or 0.0
    outstanding = totals.get("outstanding", 0.0) or 0.0

    totals_data = [
        ["Sold (total)", "Received", "Outstanding (udhaar)"],
        [_fmt_amount(sold), _fmt_amount(received), _fmt_amount(outstanding)],
    ]
    col_w = (doc.width) / 3
    totals_table = Table(totals_data, colWidths=[col_w, col_w, col_w])
    totals_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 9),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME",     (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 1), (-1, 1), 13),
        ("TEXTCOLOR",    (2, 1), (2, 1), colors.HexColor("#C0392B")),  # outstanding in red
        ("BACKGROUND",   (0, 1), (-1, 1), colors.HexColor("#F8F9FA")),
        ("BOX",          (0, 0), (-1, -1), 1, colors.HexColor("#2C3E50")),
        ("INNERGRID",    (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 0.4 * cm))

    # --- Udhaar table (unpaid rows) ---
    story.append(Paragraph("Udhaar (Outstanding)", style_section))

    udhaar_rows = [r for r in rows if not r.get("paid")]
    udhaar_header = ["Customer", "Item", "Amount", "Date"]
    udhaar_body = []
    for r in udhaar_rows:
        udhaar_body.append([
            r.get("customer") or "—",
            r.get("item") or "—",
            _fmt_amount(r.get("amount_pkr")),
            _fmt_date(r.get("date")),
        ])
    if not udhaar_body:
        udhaar_body.append(["(no outstanding items)", "", "", ""])

    udhaar_table_data = [udhaar_header] + udhaar_body
    uc_w = [doc.width * f for f in (0.30, 0.25, 0.22, 0.23)]
    udhaar_table = Table(udhaar_table_data, colWidths=uc_w, repeatRows=1)
    udhaar_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8),
        ("ALIGN",        (2, 0), (2, -1), "RIGHT"),  # Amount
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(udhaar_table)
    story.append(Spacer(1, 0.4 * cm))

    # --- Full reconciled ledger table ---
    story.append(Paragraph("Full Ledger (Reconciled)", style_section))

    ledger_header = ["#", "Date", "Customer", "Item", "Qty", "Amount", "Paid"]
    ledger_body = []
    for r in rows:
        paid_str = "Yes" if r.get("paid") else "No"
        ledger_body.append([
            str(r.get("row_index", "")),
            _fmt_date(r.get("date")),
            r.get("customer") or "—",
            r.get("item") or "—",
            str(r.get("quantity") or "—"),
            _fmt_amount(r.get("amount_pkr")),
            paid_str,
        ])
    if not ledger_body:
        ledger_body.append(["—", "—", "(no rows)", "—", "—", "—", "—"])

    ledger_col_w = [doc.width * f for f in (0.06, 0.13, 0.20, 0.16, 0.10, 0.16, 0.09)]
    # Pad last col to use remaining width
    ledger_col_w[-1] = doc.width - sum(ledger_col_w[:-1])

    ledger_table_data = [ledger_header] + ledger_body
    ledger_table = Table(ledger_table_data, colWidths=ledger_col_w, repeatRows=1)
    ledger_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("ALIGN",         (0, 0), (0, -1), "CENTER"),   # row #
        ("ALIGN",         (5, 0), (5, -1), "RIGHT"),    # amount
        ("ALIGN",         (6, 0), (6, -1), "CENTER"),   # paid
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ]))
    story.append(ledger_table)
    story.append(Spacer(1, 0.4 * cm))

    # --- Flags resolved today ---
    resolved_flags = [f for f in flags if f.get("dismissed")]
    if resolved_flags:
        story.append(Paragraph("Flags Resolved Today", style_section))
        flags_header = ["Kind", "Explanation", "Status"]
        flags_body = []
        for f in resolved_flags:
            flags_body.append([
                f.get("kind") or "—",
                (f.get("explanation") or "—")[:80],
                _flag_status(f),
            ])
        flags_col_w = [doc.width * f for f in (0.22, 0.64, 0.14)]
        flags_table_data = [flags_header] + flags_body
        flags_table = Table(flags_table_data, colWidths=flags_col_w, repeatRows=1)
        flags_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 7),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("WORDWRAP",      (1, 0), (1, -1), True),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ]))
        story.append(flags_table)
        story.append(Spacer(1, 0.3 * cm))

    # --- Footer ---
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CCCCCC")))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "Built with Kiro — FrankenLedger, Kiroween 2026 | "
        "Sample data is fictional — Noor General Store does not exist | "
        "No WhatsApp API, no payments, no real users.",
        style_footer,
    ))

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# XLSX builder
# ---------------------------------------------------------------------------

def build_xlsx(payload: dict) -> bytes:
    """
    Build a clean .xlsx workbook with two sheets.

    Expected payload keys (all optional — empty input → valid xlsx with headers only):
      reconciled : list of reconciled ledger-row dicts
      flags      : list of flag dicts

    Sheet "Ledger" columns:
      Row #, Date, Customer, Item, Quantity, Amount (Rs), Paid

    Sheet "Flags" columns:
      Flag ID, Kind, Explanation, Status (open/fixed/dismissed), Chat Line,
      Ledger Row(s)

    Returns raw .xlsx bytes.
    The original uploaded file is NEVER touched.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    rows: list[dict] = payload.get("reconciled") or []
    flags: list[dict] = payload.get("flags") or []

    wb = openpyxl.Workbook()
    wb.properties.title = "FrankenLedger Export"
    wb.properties.subject = "Reconciled Ledger — fictional sample data"
    wb.properties.creator = "FrankenLedger (Kiroween 2026)"

    # --- shared style helpers ---
    HEADER_FILL   = PatternFill("solid", fgColor="2C3E50")
    HEADER_FONT   = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
    BODY_FONT     = Font(name="Calibri", size=10)
    ALT_FILL      = PatternFill("solid", fgColor="F2F2F2")
    THIN_BORDER   = Border(
        left=Side(style="thin", color="CCCCCC"),
        right=Side(style="thin", color="CCCCCC"),
        top=Side(style="thin", color="CCCCCC"),
        bottom=Side(style="thin", color="CCCCCC"),
    )
    CENTER        = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT          = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    RIGHT         = Alignment(horizontal="right",  vertical="center", wrap_text=True)

    def _style_header_row(ws, row_num: int, ncols: int) -> None:
        for col in range(1, ncols + 1):
            cell = ws.cell(row=row_num, column=col)
            cell.fill   = HEADER_FILL
            cell.font   = HEADER_FONT
            cell.border = THIN_BORDER
            cell.alignment = CENTER

    def _style_data_row(ws, row_num: int, ncols: int, alt: bool) -> None:
        fill = ALT_FILL if alt else PatternFill("solid", fgColor="FFFFFF")
        for col in range(1, ncols + 1):
            cell = ws.cell(row=row_num, column=col)
            cell.fill   = fill
            cell.font   = BODY_FONT
            cell.border = THIN_BORDER
            cell.alignment = LEFT

    # -----------------------------------------------------------------------
    # Sheet 1 — Ledger
    # -----------------------------------------------------------------------
    ws_ledger = wb.active
    ws_ledger.title = "Ledger"

    ledger_headers = ["Row #", "Date", "Customer", "Item", "Quantity",
                      "Amount (Rs)", "Paid"]
    ws_ledger.append(ledger_headers)
    _style_header_row(ws_ledger, 1, len(ledger_headers))

    for i, r in enumerate(rows):
        paid_val = "Yes" if r.get("paid") else "No"
        ws_ledger.append([
            r.get("row_index"),
            r.get("date"),
            r.get("customer"),
            r.get("item"),
            r.get("quantity"),
            r.get("amount_pkr"),
            paid_val,
        ])
        _style_data_row(ws_ledger, i + 2, len(ledger_headers), alt=(i % 2 == 1))

    # Right-align the Amount column (col 6)
    for row_cells in ws_ledger.iter_rows(min_row=2, min_col=6, max_col=6):
        for cell in row_cells:
            cell.alignment = RIGHT

    # Column widths
    ledger_col_widths = [8, 13, 18, 15, 12, 14, 8]
    for col_idx, width in enumerate(ledger_col_widths, start=1):
        ws_ledger.column_dimensions[get_column_letter(col_idx)].width = width

    ws_ledger.freeze_panes = "A2"

    # -----------------------------------------------------------------------
    # Sheet 2 — Flags
    # -----------------------------------------------------------------------
    ws_flags = wb.create_sheet(title="Flags")

    flags_headers = ["Flag ID", "Kind", "Explanation", "Status",
                     "Chat Line", "Ledger Row(s)"]
    ws_flags.append(flags_headers)
    _style_header_row(ws_flags, 1, len(flags_headers))

    for i, f in enumerate(flags):
        chat_order = f.get("chat_order") or {}
        ledger_rows_f = f.get("ledger_rows") or []
        chat_line = chat_order.get("source_line") if chat_order else None
        ledger_row_ids = ", ".join(
            str(lr.get("row_index")) for lr in ledger_rows_f
            if lr.get("row_index") is not None
        )
        ws_flags.append([
            f.get("flag_id") or "",
            f.get("kind") or "",
            f.get("explanation") or "",
            _flag_status(f),
            chat_line,
            ledger_row_ids or "",
        ])
        _style_data_row(ws_flags, i + 2, len(flags_headers), alt=(i % 2 == 1))

    # Column widths
    flags_col_widths = [38, 22, 60, 12, 10, 14]
    for col_idx, width in enumerate(flags_col_widths, start=1):
        ws_flags.column_dimensions[get_column_letter(col_idx)].width = width

    ws_flags.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
