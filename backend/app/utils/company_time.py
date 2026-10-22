"""Company-local attendance calendar and display helpers.

Database DATETIME columns contain naive UTC values for compatibility with existing data.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import current_app


def company_timezone():
    return ZoneInfo(current_app.config.get("COMPANY_TIMEZONE", "Asia/Kolkata"))


def company_today():
    return datetime.now(company_timezone()).date()


def utc_now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_company_local(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(company_timezone())
