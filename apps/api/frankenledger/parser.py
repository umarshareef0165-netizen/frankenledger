"""
FrankenLedger — deterministic WhatsApp chat parser.
Spec 02.  Pure Python stdlib (re, datetime).  No LLM, no network.

Pipeline (per line):
  1. Split into (date, time, sender, text) via WhatsApp export regex.
  2. Skip media / voice-note placeholders → counted as needs_listening.
  3. Extract quantity (number + unit, Roman-Urdu number words).
  4. Extract amount (Rs / rupy / /- / bare-number).
  5. Classify payment status (paid / udhaar / promised / unknown).
  6. Match item catalogue keyword; fallback to item_raw.
  7. Assign confidence (high/medium/low).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from .models import CandidateOrder, Confidence, PaymentStatus

# ---------------------------------------------------------------------------
# WhatsApp line regex
# Tolerates:
#   DD/MM/YYYY, HH:MM         (24-hour)
#   MM/DD/YYYY, HH:MM         (disambiguated: if day field > 12 → DD/MM)
#   DD/MM/YYYY, HH:MM AM/PM   (12-hour)
# ---------------------------------------------------------------------------
_LINE_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{4}),?\s+"     # groups 1-3: d1/d2/YYYY
    r"(\d{1,2}):(\d{2})(?:\s*([AaPp][Mm]))?"  # groups 4-5: HH:MM, group 6: AM/PM
    r"\s*[-\u2013]\s*"                         # separator
    r"([^:]+):\s*"                             # group 7: sender
    r"(.+)$",                                  # group 8: text
    re.UNICODE,
)

# Media / voice-note placeholders
_MEDIA_RE = re.compile(
    r"<[Mm]edia omitted>|"
    r"\bvoice\s+message\b|"
    r"\bimage\s+omitted\b|"
    r"\bvideo\s+omitted\b|"
    r"\baudio\s+omitted\b|"
    r"\bsticker\s+omitted\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Roman-Urdu number words → float
# ---------------------------------------------------------------------------
_URDU_NUM: dict[str, float] = {
    "ek": 1, "do": 2, "teen": 3, "chaar": 4, "char": 4, "paanch": 5,
    "panch": 5, "chhay": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
}

# ---------------------------------------------------------------------------
# Units  (canonical form)
# ---------------------------------------------------------------------------
_UNIT_MAP = {
    "kg": "kg", "kilo": "kg", "kilos": "kg",
    "g": "g", "gram": "g", "grams": "g",
    "packet": "packet", "pack": "packet", "packets": "packet",
    "darjan": "darjan", "dozen": "darjan", "darzin": "darjan",
    "litre": "litre", "liter": "litre", "litres": "litre", "liters": "litre",
    "piece": "piece", "pieces": "piece", "pcs": "piece",
    "bottle": "bottle", "bottles": "bottle",
}

# quantity pattern: optional number-word OR digit, then unit
_QTY_RE = re.compile(
    r"(?:"
    # Roman-Urdu word number + unit
    r"(?P<urdu_num>ek|do|teen|chaar|char|paanch|panch|chhay|saat|aath|nau|das)"
    r"\s+(?P<urdu_unit>" + "|".join(re.escape(u) for u in _UNIT_MAP) + r")"
    r"|"
    # digit(s) + optional fraction + unit
    r"(?P<dig_num>\d+(?:\.\d+)?)\s*"
    r"(?P<dig_unit>" + "|".join(re.escape(u) for u in _UNIT_MAP) + r")"
    r")",
    re.IGNORECASE,
)

# plain number (no unit) — only used as quantity fallback when item present
_PLAIN_NUM_RE = re.compile(r"\b(\d+)\b")

# ---------------------------------------------------------------------------
# Amount
# ---------------------------------------------------------------------------
_AMT_RE = re.compile(
    r"(?:"
    r"[Rr][Ss]\.?\s*(?P<rs>[\d,]+)"   # Rs 500 / Rs. 500 / Rs500
    r"|"
    r"(?P<rupy>[\d,]+)\s*rupy[a-z]*"  # 500 rupy / 500 rupay
    r"|"
    r"(?P<slash>[\d,]+)\s*/-"         # 500/-
    r"|"
    r"(?P<bare>[\d,]+(?:\.\d+)?)"     # bare number — matched last
    r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Item catalogue
# ---------------------------------------------------------------------------
_CATALOGUE: dict[str, list[str]] = {
    "cheeni": ["cheeni", "chini", "sugar"],
    "atta": ["atta", "flour"],
    "chawal": ["chawal", "rice"],
    "doodh": ["doodh", "dudh", "milk"],
    "anda": ["anda", "egg", "eggs", "anday"],
    "chai": ["chai", "tea"],
    "ghee": ["ghee"],
    "daal": ["daal", "dal", "lentil", "lentils"],
    "namak": ["namak", "salt"],
    "sabun": ["sabun", "soap"],
}
# flat lookup: alias -> canonical
_ITEM_LOOKUP: dict[str, str] = {
    alias: canonical
    for canonical, aliases in _CATALOGUE.items()
    for alias in aliases
}

# ---------------------------------------------------------------------------
# Payment-status keywords (order matters — more specific first)
# ---------------------------------------------------------------------------
_PAID_PATTERNS = [
    re.compile(r"paise\s+de\s+diye", re.IGNORECASE),
    re.compile(r"de\s+diye", re.IGNORECASE),
    re.compile(r"de\s+diya", re.IGNORECASE),
    re.compile(r"\bpaid\b", re.IGNORECASE),
    re.compile(r"\bpayment\s+done\b", re.IGNORECASE),
]
_UDHAAR_PATTERNS = [
    re.compile(r"kal\s+paise\s+dunga", re.IGNORECASE),
    re.compile(r"kal\s+dunga", re.IGNORECASE),
    re.compile(r"\budhaar\b", re.IGNORECASE),
    re.compile(r"\budhar\b", re.IGNORECASE),
    re.compile(r"rehta\s+hai", re.IGNORECASE),
    re.compile(r"\bbaaki\b", re.IGNORECASE),
    re.compile(r"\bbaki\b", re.IGNORECASE),
    re.compile(r"\bkal\b", re.IGNORECASE),
]
_PROMISED_PATTERNS = [
    re.compile(r"\bpromised\b", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Helper: strip currency / qty noise from text to get item_raw fallback
# ---------------------------------------------------------------------------
_NOISE_RE = re.compile(
    r"(?:[Rr][Ss]\.?\s*[\d,]+|[\d,]+\s*rupy[a-z]*|[\d,]+\s*/-"
    r"|(?:ek|do|teen|chaar|char|paanch|panch)\s+(?:" + "|".join(re.escape(u) for u in _UNIT_MAP) + r")"
    r"|[\d,]+(?:\.\d+)?\s*(?:" + "|".join(re.escape(u) for u in _UNIT_MAP) + r")?"
    r"|paise\s+de\s+diye|de\s+diye|de\s+diya"
    r"|kal\s+paise\s+dunga|kal\s+dunga"
    r"|\budhaar\b|\budhar\b|rehta\s+hai|\bbaaki\b|\bbaki\b|\bkal\b"
    r"|\bpaid\b|\bpayment\s+done\b|\bpromised\b"
    r"|please|shukriya|bhai|yaar|jaldi|bhej\s+do|chahiye|aur|bhej\s+di"
    r"|[,;!?])",
    re.IGNORECASE,
)


def _parse_date(d1: str, d2: str, yyyy: str) -> Optional[str]:
    """
    Return ISO date string or None.
    If d1 > 12, it must be the day; else assume DD/MM/YYYY (WhatsApp default).
    """
    n1, n2, year = int(d1), int(d2), int(yyyy)
    if n1 > 12:
        day, month = n1, n2
    elif n2 > 12:
        day, month = n2, n1
    else:
        day, month = n1, n2   # default: DD/MM (WhatsApp standard)
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _extract_quantity(text: str) -> tuple[Optional[float], Optional[str]]:
    """Return (quantity, unit) or (None, None)."""
    m = _QTY_RE.search(text)
    if not m:
        return None, None
    if m.group("urdu_num"):
        qty = _URDU_NUM[m.group("urdu_num").lower()]
        unit = _UNIT_MAP.get(m.group("urdu_unit").lower(), m.group("urdu_unit").lower())
    else:
        qty = float(m.group("dig_num"))
        unit = _UNIT_MAP.get(m.group("dig_unit").lower(), m.group("dig_unit").lower())
    return qty, unit


def _extract_amount(text: str) -> Optional[float]:
    """
    Return the first confidently-matched amount, or None.
    Bare numbers are only returned when another signal (item/qty) is present —
    that guard is done by the caller.
    """
    # Try non-bare patterns first
    for pattern_name in ("rs", "rupy", "slash"):
        m = _AMT_RE.search(text)
        while m:
            val = m.group("rs") or m.group("rupy") or m.group("slash")
            if val:
                return float(val.replace(",", ""))
            m = _AMT_RE.search(text, m.end())

    # Bare number fallback — pick the LAST standalone number (avoids quantity)
    bare_matches = list(_PLAIN_NUM_RE.finditer(text))
    if bare_matches:
        return float(bare_matches[-1].group(1))
    return None


def _extract_amount_full(text: str) -> Optional[float]:
    """
    Full amount extraction: Rs/rupy/slash first, then bare-number fallback.
    Returns None only if nothing found.
    """
    # Prefer explicit currency markers
    for m in _AMT_RE.finditer(text):
        for key in ("rs", "rupy", "slash"):
            if m.group(key):
                return float(m.group(key).replace(",", ""))
    # Bare number fallback
    bare = list(_PLAIN_NUM_RE.finditer(text))
    if bare:
        return float(bare[-1].group(1))
    return None


def _classify_payment(text: str) -> PaymentStatus:
    for p in _PAID_PATTERNS:
        if p.search(text):
            return PaymentStatus.paid
    for p in _UDHAAR_PATTERNS:
        if p.search(text):
            return PaymentStatus.udhaar
    for p in _PROMISED_PATTERNS:
        if p.search(text):
            return PaymentStatus.promised
    return PaymentStatus.unknown


def _find_item(text: str) -> Optional[str]:
    """Return canonical catalogue keyword or None."""
    lower = text.lower()
    # longest alias first to avoid substring shadowing
    for alias in sorted(_ITEM_LOOKUP, key=len, reverse=True):
        if re.search(r"\b" + re.escape(alias) + r"\b", lower):
            return _ITEM_LOOKUP[alias]
    return None


def _item_raw_fallback(text: str) -> Optional[str]:
    """Strip noise, return up to 6 words."""
    cleaned = _NOISE_RE.sub(" ", text)
    words = cleaned.split()
    if not words:
        return None
    return " ".join(words[:6]).strip()


def _confidence(item: Optional[str], item_raw: Optional[str],
                qty: Optional[float], amt: Optional[float]) -> Confidence:
    """high = item+qty+amt; medium = two; low = one."""
    has_item = bool(item or item_raw)
    score = sum([has_item, qty is not None, amt is not None])
    if score >= 3:
        return Confidence.high
    if score == 2:
        return Confidence.medium
    return Confidence.low


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ParseResult:
    """Full result of parsing a chat file."""
    __slots__ = ("orders", "unparsed_count", "voice_note_count",
                 "parsed_line_count", "senders", "dates")

    def __init__(self) -> None:
        self.orders: list[CandidateOrder] = []
        self.unparsed_count: int = 0
        self.voice_note_count: int = 0
        self.parsed_line_count: int = 0
        self.senders: set[str] = set()
        self.dates: list[str] = []


def parse_chat(text: str) -> ParseResult:
    """
    Parse a full WhatsApp chat export string.
    Returns a ParseResult with all candidate orders and summary counts.
    """
    result = ParseResult()
    lines = text.splitlines()

    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue  # comment / blank — skip silently

        m = _LINE_RE.match(line)
        if not m:
            result.unparsed_count += 1
            continue

        d1, d2, yyyy = m.group(1), m.group(2), m.group(3)
        sender = m.group(7).strip()
        text_body = m.group(8).strip()
        date_iso = _parse_date(d1, d2, yyyy)

        result.parsed_line_count += 1
        result.senders.add(sender)
        if date_iso:
            result.dates.append(date_iso)

        # --- Skip lines sent by the shop itself ---
        # Sender names containing 'store' or 'shop' are the shop owner's
        # replies, not customer orders. Never emit a CandidateOrder for them.
        sender_lower = sender.lower()
        if "store" in sender_lower or "shop" in sender_lower:
            continue

        # --- Media / voice note ---
        if _MEDIA_RE.search(text_body):
            result.voice_note_count += 1
            continue

        # --- Extract fields ---
        qty, unit = _extract_quantity(text_body)
        item = _find_item(text_body)
        payment = _classify_payment(text_body)

        # Amount: prefer explicit markers; bare number allowed only when
        # item or qty is present (to avoid treating order numbers as amounts)
        amt: Optional[float] = None
        # First pass: explicit currency
        for am in _AMT_RE.finditer(text_body):
            for key in ("rs", "rupy", "slash"):
                if am.group(key):
                    amt = float(am.group(key).replace(",", ""))
                    break
            if amt is not None:
                break
        # Second pass: bare number only if something else is found OR
        # this is a payment-confirmation line (paid/de-diye)
        is_payment_confirm = payment == PaymentStatus.paid
        if amt is None and (item or qty is not None or is_payment_confirm):
            bare = list(_PLAIN_NUM_RE.finditer(text_body))
            if bare:
                # pick last bare number
                amt = float(bare[-1].group(1))

        # Item raw fallback
        item_raw: Optional[str] = None
        if not item:
            item_raw = _item_raw_fallback(text_body)

        conf = _confidence(item, item_raw, qty, amt)

        # Only emit a CandidateOrder if at least one signal found
        if item or qty is not None or amt is not None:
            result.orders.append(CandidateOrder(
                date=date_iso,
                sender=sender,
                item=item,
                item_raw=item_raw,
                quantity=qty,
                unit=unit,
                amount_pkr=amt,
                payment_status=payment,
                source_line=lineno,
                confidence=conf,
            ))

    return result


def parse_chat_file(path: str) -> ParseResult:
    """Convenience wrapper: read a file then parse it."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_chat(fh.read())
