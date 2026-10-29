"""
Parses a vendor recruitment agreement PDF into structured fields.

Deliberately deterministic-first: the fee table (service %, replacement
days, tenure days) is read straight out of the PDF's actual table
structure via pdfplumber, not guessed by an LLM — these are money numbers,
and a hallucinated percentage is a real financial risk. Free-text fields
(party names, notice periods) use regex against the fixed phrasing this
agreement template uses, with an optional AI-assisted pass to fill in
anything regex genuinely can't find. Nothing here is ever auto-saved —
every field returned is meant for human review before it's confirmed.
"""
import re
from datetime import datetime

from dateutil import parser as dateparser

from app.utils.pdf_text import extract_pdf_text_and_tables
from app.utils.ai_grading import _ask_model, _ANTHROPIC_AVAILABLE


def _strip_ordinal(text):
    return re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text, flags=re.IGNORECASE)


def _parse_date(raw):
    if not raw:
        return None
    try:
        return dateparser.parse(_strip_ordinal(raw), fuzzy=True, dayfirst=False).date()
    except (ValueError, OverflowError):
        return None


def _extract_party_names(text):
    """'This agreement is made on <date> between <A> and <B>[.] Located at'"""
    m = re.search(
        r"agreement is made on\s+(.+?)\s+between\s+(.+?)\s+and\s+(.+?)(?:\.|,)?\s*(?:[Ll]ocated at)",
        text, re.DOTALL,
    )
    if not m:
        return None, None, None
    made_date = m.group(1).strip()
    party_a = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(".")
    party_b = re.sub(r"\s+", " ", m.group(3)).strip().rstrip(".")
    return made_date, party_a, party_b


def _extract_effective_dates(text):
    m = re.search(
        r"effective\s+(?:with\s+)?from\s+(.+?)\s+till\s+(?:to\s+)?(.+?)\s*,?\s*on the following",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None, None
    return _parse_date(m.group(1)), _parse_date(m.group(2))


def _extract_int(pattern, text, group=1):
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(group))
    except ValueError:
        return None


def _extract_termination_notice_days(text):
    m = re.search(r"giving\s+(\d+)\s*(day|month)s?\s*['’]?\s*notice", text, re.IGNORECASE)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return n * 30 if unit == "month" else n


def _extract_confidentiality_days(text):
    return _extract_int(r"for the period of\s+(\d+)\s*days? from the date of first receipt", text)


def _extract_feedback_days(text):
    return _extract_int(r"within\s+(\d+)\s*days?\s+from the date of receipt", text)


def _find_fee_table(tables):
    """Finds the 'Details / Role A / Role B...' rate-card table among every
    table pdfplumber found on the page."""
    for table in tables:
        if not table:
            continue
        first_col = [str(row[0] or "").strip().lower() for row in table]
        if "service fees" in first_col and "replacement" in first_col:
            return table
    return None


def _pct_from_cell(cell):
    m = re.search(r"([\d.]+)\s*%", cell or "")
    return float(m.group(1)) if m else None


def _days_from_cell(cell, pattern=r"(\d+)\s*days?"):
    m = re.search(pattern, cell or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


def _parse_fee_table(table):
    if not table:
        return []
    header = table[0]
    role_names = [str(c).strip() for c in header[1:] if c and str(c).strip()]

    rows_by_label = {}
    for row in table[1:]:
        label = str(row[0] or "").strip().lower()
        rows_by_label[label] = row[1:]

    fee_row = rows_by_label.get("service fees", [])
    replacement_row = rows_by_label.get("replacement", [])
    payment_row = rows_by_label.get("payment terms", [])

    roles = []
    for i, role_name in enumerate(role_names):
        fee_pct = _pct_from_cell(fee_row[i]) if i < len(fee_row) else None
        replacement_days = _days_from_cell(replacement_row[i]) if i < len(replacement_row) else 30
        tenure_days = (
            _days_from_cell(payment_row[i], r"tenure of\s*(\d+)\s*days?")
            if i < len(payment_row) else 60
        )
        if fee_pct is not None:
            roles.append({
                "role_name": role_name,
                "service_fee_pct": fee_pct,
                "replacement_days": replacement_days or 30,
                "tenure_days": tenure_days or 60,
            })
    return roles


def _ai_fill_gaps(text, parsed):
    """Only called for fields regex couldn't find. Never touches the fee
    table — that stays purely deterministic."""
    if not _ANTHROPIC_AVAILABLE:
        return parsed

    missing = [k for k in ("party_a", "party_b", "effective_from", "effective_to") if not parsed.get(k)]
    if not missing:
        return parsed

    prompt = (
        "Extract these fields from the recruitment agreement text below. "
        "Respond ONLY with JSON, no other text: "
        '{"party_a": "...", "party_b": "...", "effective_from": "YYYY-MM-DD", "effective_to": "YYYY-MM-DD"}. '
        "Use null for anything not present.\n\n" + text[:4000]
    )
    result = _ask_model(prompt, max_tokens=300)
    if not result:
        return parsed
    try:
        import json
        cleaned = re.sub(r"^```json|```$", "", result.strip(), flags=re.MULTILINE).strip()
        ai_data = json.loads(cleaned)
        for k in missing:
            if ai_data.get(k):
                parsed[k] = ai_data[k]
    except Exception:
        pass
    return parsed


def parse_agreement(file_stream):
    """Returns a dict with every field the confirm-step UI needs, plus
    raw_text for full transparency/audit."""
    text, tables = extract_pdf_text_and_tables(file_stream)

    made_date, party_a, party_b = _extract_party_names(text)
    effective_from, effective_to = _extract_effective_dates(text)
    termination_notice_days = _extract_termination_notice_days(text)
    confidentiality_days = _extract_confidentiality_days(text)
    feedback_days = _extract_feedback_days(text)

    parsed = {
        "party_a": party_a,
        "party_b": party_b,
        "made_date": made_date,
        "effective_from": effective_from.isoformat() if effective_from else None,
        "effective_to": effective_to.isoformat() if effective_to else None,
        "termination_notice_days": termination_notice_days or 90,
        "confidentiality_days": confidentiality_days or 60,
        "feedback_days": feedback_days or 2,
        "roles": _parse_fee_table(_find_fee_table(tables)),
        "raw_text": text,
        "used_ai_fallback": False,
    }

    if not parsed["party_a"] or not parsed["party_b"] or not parsed["effective_from"]:
        before = dict(parsed)
        parsed = _ai_fill_gaps(text, parsed)
        parsed["used_ai_fallback"] = parsed != before

    parsed["extracted_fields"] = [
        field for field, value in (
            ("party_a", parsed["party_a"]),
            ("party_b", parsed["party_b"]),
            ("effective_from", parsed["effective_from"]),
            ("effective_to", parsed["effective_to"]),
            ("termination_notice_days", termination_notice_days),
            ("confidentiality_days", confidentiality_days),
            ("feedback_days", feedback_days),
            ("roles", parsed["roles"]),
        )
        if value
    ]
    return parsed
