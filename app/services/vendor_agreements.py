import logging
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, or_, update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import VendorAgreement, VendorAgreementReminder, User
from app.roles import FINANCE_ACCOUNTS, HR_OPERATIONS, OPERATIONS
from app.utils.company_time import company_today
from app.utils.push import send_push

logger = logging.getLogger(__name__)
REMINDER_MONTH = "expiry_1_month"
REMINDER_WEEK = "expiry_7_day"
REMINDER_TYPES = (REMINDER_MONTH, REMINDER_WEEK)


def agreement_status(agreement, today=None):
    """Return a display status without overwriting approval/termination state."""
    stored_status = (agreement.status or "active").lower()
    if stored_status not in ("active", "expired"):
        return stored_status

    today = today or company_today()
    if agreement.effective_from and agreement.effective_from > today:
        return "upcoming"
    if agreement.effective_to:
        days_remaining = (agreement.effective_to - today).days
        if days_remaining < 0:
            return "expired"
        if days_remaining <= 7:
            return "expiring_soon"
    return "active"


def agreement_days_remaining(agreement, today=None):
    if not agreement.effective_to:
        return None
    today = today or company_today()
    return (agreement.effective_to - today).days


def _one_calendar_month_before(expiry_date):
    month = expiry_date.month - 1
    year = expiry_date.year
    if month == 0:
        month = 12
        year -= 1
    return date(year, month, min(expiry_date.day, monthrange(year, month)[1]))


def _reminder_date(expiry_date, reminder_type):
    if reminder_type == REMINDER_MONTH:
        return _one_calendar_month_before(expiry_date)
    if reminder_type == REMINDER_WEEK:
        return expiry_date - timedelta(days=7)
    raise ValueError(f"Unknown vendor agreement reminder type: {reminder_type}")


def _reminder_agreements(today, reminder_type):
    active_agreements = VendorAgreement.query.filter(
        VendorAgreement.effective_to >= today,
        VendorAgreement.status == "active",
    ).all()
    agreements = {
        row.id: row
        for row in active_agreements
        if _reminder_date(row.effective_to, reminder_type) == today
    }

    retryable = VendorAgreementReminder.query.filter(
        VendorAgreementReminder.reminder_type == reminder_type,
        VendorAgreementReminder.expiry_date >= today,
        VendorAgreementReminder.status.in_(("failed", "pending")),
    ).all()
    for reminder in retryable:
        agreement = db.session.get(VendorAgreement, reminder.agreement_id)
        if (
            agreement
            and agreement.status == "active"
            and agreement.effective_to == reminder.expiry_date
            and _reminder_date(agreement.effective_to, reminder_type) <= today
        ):
            agreements[agreement.id] = agreement
    return list(agreements.values())


def _claim_reminder(agreement, reminder_type, now):
    reminder = VendorAgreementReminder.query.filter_by(
        agreement_id=agreement.id,
        reminder_type=reminder_type,
        expiry_date=agreement.effective_to,
    ).first()
    if reminder and reminder.status == "sent":
        return None, False
    if (
        reminder
        and reminder.status == "pending"
        and reminder.attempted_at
        and reminder.attempted_at > now - timedelta(minutes=10)
    ):
        return None, False

    if reminder is None:
        reminder = VendorAgreementReminder(
            agreement_id=agreement.id,
            reminder_type=reminder_type,
            expiry_date=agreement.effective_to,
            status="pending",
            attempted_at=now,
        )
        db.session.add(reminder)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return None, False
    else:
        stale_pending = and_(
            VendorAgreementReminder.status == "pending",
            or_(
                VendorAgreementReminder.attempted_at.is_(None),
                VendorAgreementReminder.attempted_at <= now - timedelta(minutes=10),
            ),
        )
        claimed = db.session.execute(
            update(VendorAgreementReminder)
            .where(
                VendorAgreementReminder.id == reminder.id,
                or_(
                    VendorAgreementReminder.status == "failed",
                    stale_pending,
                ),
            )
            .values(status="pending", attempted_at=now, error_message=None)
        ).rowcount
        db.session.commit()
        if not claimed:
            return None, False
        db.session.expire(reminder)
    return reminder, True


def send_expiry_reminders(today=None):
    """Send duplicate-safe one-calendar-month and seven-day expiry reminders."""
    today = today or company_today()
    recipient_ids = [
        user.id
        for user in User.query.filter(
            User.is_active.is_(True),
            User.role.in_((HR_OPERATIONS, FINANCE_ACCOUNTS, OPERATIONS)),
        ).all()
    ]
    results = {"sent": 0, "failed": 0, "skipped": 0}
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for reminder_type in REMINDER_TYPES:
        for agreement in _reminder_agreements(today, reminder_type):
            reminder, claimed = _claim_reminder(agreement, reminder_type, now)
            if not claimed:
                results["skipped"] += 1
                continue

            if not recipient_ids:
                reminder.status = "failed"
                reminder.error_message = "No active vendor-management recipients."
                db.session.commit()
                results["failed"] += 1
                continue

            if reminder_type == REMINDER_MONTH:
                title = "Vendor agreement expires in one month"
                window = "one calendar month"
            else:
                title = "Vendor agreement expiring in seven days"
                window = "seven days"
            try:
                accepted = send_push(
                    recipient_ids,
                    title,
                    f"{agreement.vendor.name}: {agreement.title or 'Agreement'} expires on "
                    f"{agreement.effective_to.isoformat()} (in {window}). Review or renew the agreement.",
                    data={
                        "type": "vendor_agreement_expiry",
                        "reminder_type": reminder_type,
                        "vendor_id": agreement.vendor_id,
                        "agreement_id": agreement.id,
                        "url": f"/vendors?agreement={agreement.id}",
                    },
                )
            except Exception:
                logger.exception("Agreement expiry reminder failed for agreement %s", agreement.id)
                accepted = False

            reminder.status = "sent" if accepted else "failed"
            reminder.sent_at = datetime.now(timezone.utc).replace(tzinfo=None) if accepted else None
            reminder.error_message = None if accepted else "Push delivery was unavailable or rejected."
            db.session.commit()
            results[reminder.status] += 1

    return results
