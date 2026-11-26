from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_

from app.models import Announcement, Department, User
from app.roles import ALL_ROLES, ROLE_LABELS


IST = ZoneInfo("Asia/Kolkata")
VALID_CATEGORIES = {"general", "hr", "policy", "events", "operations"}
VALID_PRIORITIES = {"normal", "important", "urgent"}
VALID_DURATIONS = {"minutes", "hours", "days", "custom", "indefinite"}


def now_ist():
    return datetime.now(IST)


def utc_naive(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=IST)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def iso_utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def parse_datetime(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a valid date and time.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid date and time.") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return utc_naive(parsed)


def normalize_audiences(value):
    if not isinstance(value, dict):
        raise ValueError("Select at least one recipient.")
    everyone = value.get("everyone", False)
    user_ids = value.get("user_ids", [])
    department_ids = value.get("department_ids", [])
    roles = value.get("roles", [])
    if not isinstance(everyone, bool):
        raise ValueError("Invalid everyone audience.")
    if not isinstance(user_ids, list) or not isinstance(department_ids, list) or not isinstance(roles, list):
        raise ValueError("Recipient selections must be lists.")

    def normalized_ids(values, label):
        output = []
        for item in values:
            if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
                raise ValueError(f"Invalid {label} recipient.")
            if item not in output:
                output.append(item)
        return output

    user_ids = normalized_ids(user_ids, "user")
    department_ids = normalized_ids(department_ids, "department")
    if any(not isinstance(role, str) or role not in ALL_ROLES for role in roles):
        raise ValueError("Select valid roles.")
    roles = list(dict.fromkeys(roles))

    if user_ids:
        valid_users = {
            row[0] for row in User.query.with_entities(User.id).filter(
                User.id.in_(user_ids),
                User.is_active.is_(True),
                User.employment_status != "left",
            ).all()
        }
        if valid_users != set(user_ids):
            raise ValueError("One or more selected users are unavailable.")
    if department_ids:
        valid_departments = {
            row[0] for row in Department.query.with_entities(Department.id)
            .filter(Department.id.in_(department_ids)).all()
        }
        if valid_departments != set(department_ids):
            raise ValueError("One or more selected departments are unavailable.")
    if not (everyone or user_ids or department_ids or roles):
        raise ValueError("Select at least one recipient.")
    return {
        "everyone": everyone,
        "user_ids": user_ids,
        "department_ids": department_ids,
        "roles": roles,
    }


def validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Announcement data must be an object.")
    title = payload.get("title")
    message = payload.get("message")
    category = payload.get("category", "general")
    priority = payload.get("priority", "normal")
    duration_unit = payload.get("duration_unit", "indefinite")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
        raise ValueError("Title is required and must be 200 characters or fewer.")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Message is required.")
    if len(message) > 20000:
        raise ValueError("Message must be 20,000 characters or fewer.")
    if not isinstance(category, str) or category not in VALID_CATEGORIES:
        raise ValueError("Select a valid announcement category.")
    if not isinstance(priority, str) or priority not in VALID_PRIORITIES:
        raise ValueError("Select a valid priority.")
    if not isinstance(duration_unit, str) or duration_unit not in VALID_DURATIONS:
        raise ValueError("Select a valid display duration.")

    publish_at = (
        parse_datetime(payload["publish_at"], "Publish date and time")
        if payload.get("publish_at")
        else utc_naive(now_ist())
    )
    if duration_unit == "indefinite":
        expires_at = None
    elif duration_unit == "custom":
        expires_at = parse_datetime(payload.get("expires_at"), "Expiry date and time")
    else:
        try:
            duration_value = float(payload.get("duration_value", 1))
        except (TypeError, ValueError) as error:
            raise ValueError("Display duration must be a positive number.") from error
        if not 0 < duration_value <= 365:
            raise ValueError("Display duration must be greater than zero and at most 365.")
        duration = {
            "minutes": timedelta(minutes=duration_value),
            "hours": timedelta(hours=duration_value),
            "days": timedelta(days=duration_value),
        }[duration_unit]
        expires_at = publish_at + duration
    if expires_at is not None and expires_at <= publish_at:
        raise ValueError("Expiry must be after the publish date and time.")

    return {
        "title": title.strip(),
        "message": message.strip(),
        "category": category,
        "priority": priority,
        "audiences": normalize_audiences(payload.get("audiences")),
        "publish_at": publish_at,
        "expires_at": expires_at,
    }


def announcement_status(announcement, current=None):
    current = current or utc_naive(now_ist())
    publish_at = announcement.publish_at or announcement.created_at or current
    if publish_at > current:
        return "scheduled"
    if announcement.expires_at is not None and announcement.expires_at <= current:
        return "expired"
    return "active"


def audience_applies(audiences, user):
    return bool(
        audiences.get("everyone")
        or user.id in audiences.get("user_ids", [])
        or user.role in audiences.get("roles", [])
        or (
            user.department_id is not None
            and user.department_id in audiences.get("department_ids", [])
        )
    )


def announcement_audiences(announcement):
    if isinstance(announcement.audiences, dict):
        return announcement.audiences
    if announcement.audience_role:
        return {
            "everyone": False,
            "user_ids": [],
            "department_ids": [],
            "roles": [announcement.audience_role],
        }
    return {"everyone": True, "user_ids": [], "department_ids": [], "roles": []}


def serialize_announcement(announcement, status=None):
    author = announcement.author
    return {
        "id": announcement.id,
        "kind": "official",
        "title": announcement.title,
        "message": announcement.body,
        "category": announcement.category or "general",
        "priority": announcement.priority or "normal",
        "audiences": announcement_audiences(announcement),
        "publish_at": iso_utc(announcement.publish_at or announcement.created_at),
        "expires_at": iso_utc(announcement.expires_at),
        "status": status or announcement_status(announcement),
        "created_at": iso_utc(announcement.created_at),
        "author_name": author.full_name if author else "Unknown",
        "author_designation": author.designation if author else None,
        "author_role": author.role if author else None,
        "author_role_label": ROLE_LABELS.get(author.role, author.role) if author else None,
    }


def sort_announcements_by_publication(items):
    def publication_time(item):
        value = item.get("publish_at")
        if not value:
            return datetime.min.replace(tzinfo=timezone.utc)
        published = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return published.astimezone(timezone.utc)

    return sorted(items, key=publication_time, reverse=True)


def _sort_dashboard_officials(items):
    def display_time(item):
        value = item.get("created_at") if item.get("expires_at") is None else item.get("publish_at")
        if not value:
            return datetime.min.replace(tzinfo=timezone.utc)
        published = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return published.astimezone(timezone.utc)

    return sorted(
        items,
        key=lambda item: (display_time(item), int(item["id"])),
        reverse=True,
    )


def birthday_occurs_on(dob, current_date):
    if dob.month == current_date.month and dob.day == current_date.day:
        return True
    return (
        dob.month == 2
        and dob.day == 29
        and current_date.month == 3
        and current_date.day == 1
        and not _is_leap_year(current_date.year)
    )


def _is_leap_year(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def birthday_announcements(current_date=None):
    current_date = current_date or now_ist().date()
    celebrants = User.query.filter(
        User.is_active.is_(True),
        User.employment_status != "left",
        User.date_of_birth.is_not(None),
    ).order_by(User.full_name.asc(), User.id.asc()).all()
    employees = [
        {
            "id": user.id,
            "name": user.full_name,
            "designation": user.designation,
            "avatar_url": user.avatar_url,
        }
        for user in celebrants
        if birthday_occurs_on(user.date_of_birth, current_date)
    ]
    if not employees:
        return []

    day_start = datetime.combine(current_date, time.min, tzinfo=IST)
    next_day = day_start + timedelta(days=1)
    return [{
        "id": f"birthday-{current_date.isoformat()}",
        "kind": "birthday",
        "title": "Today's Birthdays",
        "message": "Join us in wishing your colleagues a happy birthday!",
        "category": "birthday",
        "priority": "birthday",
        "employees": employees,
        "publish_at": iso_utc(day_start.astimezone(timezone.utc).replace(tzinfo=None)),
        "expires_at": iso_utc(next_day.astimezone(timezone.utc).replace(tzinfo=None)),
        "status": "active",
        "author_name": None,
        "author_designation": None,
        "author_role": None,
        "author_role_label": None,
    }]


def _active_announcement_rows(current):
    return Announcement.query.filter(
        Announcement.deleted_at.is_(None),
        or_(Announcement.publish_at <= current, Announcement.publish_at.is_(None)),
        or_(Announcement.expires_at > current, Announcement.expires_at.is_(None)),
    ).order_by(
        Announcement.publish_at.desc(),
        Announcement.created_at.desc(),
        Announcement.id.desc(),
    ).all()


def _birthday_announcements_at(current):
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return birthday_announcements(current.astimezone(IST).date())


def _select_dashboard_announcements(official_items, birthdays, limit):
    remaining = max(0, limit)
    selected = birthdays[:remaining]
    remaining -= len(selected)

    selected.extend(_sort_dashboard_officials(official_items)[:remaining])
    return selected


def dashboard_announcements(user, limit=2):
    current = utc_naive(now_ist())
    rows = _active_announcement_rows(current)
    official_items = [
        serialize_announcement(row, "active")
        for row in rows
        if audience_applies(announcement_audiences(row), user)
    ]
    return _select_dashboard_announcements(
        official_items,
        _birthday_announcements_at(current),
        limit,
    )


def displaced_no_expiry_announcement_ids(user=None, current=None):
    current = current or utc_naive(now_ist())
    rows = _active_announcement_rows(current)
    official_items = [
        serialize_announcement(row, "active")
        for row in rows
        if user is None or audience_applies(announcement_audiences(row), user)
    ]
    selected_ids = {
        item["id"]
        for item in _select_dashboard_announcements(
            official_items,
            _birthday_announcements_at(current),
            2,
        )
        if item["kind"] == "official"
    }
    return {
        row.id
        for row in rows
        if row.expires_at is None
        and row.id not in selected_ids
        and (user is None or audience_applies(announcement_audiences(row), user))
    }
