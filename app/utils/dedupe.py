import re


def normalize_email(email):
    if not email:
        return None
    return email.strip().lower()


def normalize_phone(phone):
    """Strip spaces, dashes, and a leading +91/0091/91 country code so the same
    number in different formats matches during duplicate detection."""
    if not phone:
        return None
    digits = re.sub(r"[^\d]", "", phone)
    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else digits


def find_duplicate(Candidate, email, phone, exclude_id=None):
    """Company-wide duplicate search by normalized email/phone. Returns the first
    matching Candidate row, or None."""
    norm_email = normalize_email(email)
    norm_phone = normalize_phone(phone)
    if not norm_email and not norm_phone:
        return None

    query = Candidate.query
    if exclude_id:
        query = query.filter(Candidate.id != exclude_id)

    conditions = []
    if norm_email:
        conditions.append(Candidate.email_normalized == norm_email)
    if norm_phone:
        conditions.append(Candidate.phone_normalized == norm_phone)

    from app.extensions import db
    match = query.filter(db.or_(*conditions)).first()
    return match
