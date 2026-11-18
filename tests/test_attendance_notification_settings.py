import sys
sys.path.insert(0, ".")

from datetime import date, time
from unittest.mock import Mock, patch

from config import Config


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    INTERNAL_TASK_SECRET = "test-secret"
    EXPO_PUSH_ENABLED = True


from app import create_app
from app.extensions import db
from app.models import AttendanceNotificationSettings, AttendanceReminderRun, DeviceToken, User
from app.roles import EMPLOYEE, MANAGER, SUPER_ADMIN
from app.utils.company_time import company_today
from app.utils.push import send_push


app = create_app(TestConfig)


def check(label, condition, details=""):
    if not condition:
        raise AssertionError(f"{label}: {details}")


with app.app_context():
    db.create_all()

    def make_user(code, role, manager_id=None):
        user = User(
            employee_code=code,
            full_name=code,
            email=f"{code.lower()}@example.com",
            role=role,
            manager_id=manager_id,
        )
        user.set_password("password")
        db.session.add(user)
        db.session.flush()
        return user

    manager = make_user("MANAGER", MANAGER)
    employee = make_user("EMPLOYEE", EMPLOYEE, manager.id)
    super_admin = make_user("SUPER_ADMIN", SUPER_ADMIN)
    db.session.add(DeviceToken(user_id=employee.id, token="ExponentPushToken[test]", platform="android"))
    db.session.commit()

    client = app.test_client()

    def auth(email):
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "password"},
        )
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    manager_headers = auth("manager@example.com")
    employee_headers = auth("employee@example.com")
    super_admin_headers = auth("super_admin@example.com")

    check(
        "employees cannot read company notification settings",
        client.get("/api/notifications/settings", headers=employee_headers).status_code == 403,
    )
    defaults = client.get("/api/notifications/settings", headers=manager_headers)
    check(
        "manager can read enabled defaults and reminder times",
        defaults.status_code == 200
        and defaults.get_json()["regularization_enabled"] is True
        and defaults.get_json()["clock_in_reminder_time"] == "09:30",
        defaults.get_json(),
    )
    updated = client.put(
        "/api/notifications/settings",
        headers=manager_headers,
        json={
            "leave_enabled": False,
            "clock_in_reminder_enabled": True,
            "clock_in_reminder_time": "00:00",
        },
    )
    check(
        "manager can change global toggles and reminder times",
        updated.status_code == 200
        and updated.get_json()["leave_enabled"] is False
        and updated.get_json()["clock_in_reminder_time"] == "00:00",
        updated.get_json(),
    )
    check(
        "super admin can update global notification settings",
        client.put(
            "/api/notifications/settings",
            headers=super_admin_headers,
            json={"leave_enabled": True},
        ).status_code == 200,
    )
    check(
        "invalid reminder times are rejected",
        client.put(
            "/api/notifications/settings",
            headers=manager_headers,
            json={"clock_out_reminder_time": "25:90"},
        ).status_code == 400,
    )
    check(
        "unknown settings are rejected",
        client.put(
            "/api/notifications/settings",
            headers=manager_headers,
            json={"all_notifications": False},
        ).status_code == 400,
    )

    settings = db.session.get(AttendanceNotificationSettings, 1)
    settings.business_alerts_enabled = False
    db.session.commit()
    with patch("app.utils.push.requests.post") as post:
        check(
            "disabled notification categories are not sent",
            send_push(employee.id, "Insurance", "Expiry", data={"type": "insurance_expiry"}) is False
            and not post.called,
        )
        settings.business_alerts_enabled = True
        db.session.commit()
        response = Mock(ok=True)
        response.json.return_value = {"data": [{"status": "ok"}]}
        post.return_value = response
        check(
            "enabled notification categories still send",
            send_push(employee.id, "Insurance", "Expiry", data={"type": "insurance_expiry"}) is True
            and post.called,
        )

    settings.clock_in_reminder_enabled = True
    settings.clock_in_reminder_time = time(0, 0)
    settings.manager_missing_alert_enabled = False
    settings.clock_out_reminder_enabled = False
    db.session.commit()
    with patch("app.routes.attendance.send_push") as reminder_push:
        first_dispatch = client.post(
            "/api/attendance/internal/attendance-reminders",
            headers={"X-Internal-Secret": "test-secret"},
            json={"kind": "dispatch"},
        )
        second_dispatch = client.post(
            "/api/attendance/internal/attendance-reminders",
            headers={"X-Internal-Secret": "test-secret"},
            json={"kind": "dispatch"},
        )
    check(
        "dispatcher runs a due reminder once and deduplicates later calls",
        first_dispatch.status_code == 200
        and len(first_dispatch.get_json()["runs"]) == 1
        and first_dispatch.get_json()["runs"][0]["kind"] == "clock_in_reminder"
        and second_dispatch.get_json()["runs"] == []
        and AttendanceReminderRun.query.filter_by(
            reminder_kind="clock_in_reminder", reminder_date=company_today()
        ).count() == 1
        and reminder_push.call_count == User.query.filter(
            User.is_active.is_(True), User.role != "contract_employee"
        ).count(),
        (first_dispatch.get_json(), second_dispatch.get_json()),
    )
    with patch("app.routes.attendance.company_today", return_value=date(2026, 11, 21)):
        weekend_dispatch = client.post(
            "/api/attendance/internal/attendance-reminders",
            headers={"X-Internal-Secret": "test-secret"},
            json={"kind": "dispatch"},
        )
    check(
        "dispatcher skips weekends",
        weekend_dispatch.status_code == 200
        and weekend_dispatch.get_json()["skipped"] == "weekend"
        and reminder_push.call_count == User.query.filter(
            User.is_active.is_(True), User.role != "contract_employee"
        ).count(),
        weekend_dispatch.get_json(),
    )
