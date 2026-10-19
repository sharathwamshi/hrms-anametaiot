import sys
sys.path.insert(0, ".")

from datetime import date, timedelta

from config import Config


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


from app import create_app
from app.extensions import db
from app.models import LeaveBalance, LeaveType, User
from app.roles import EMPLOYEE, MANAGER


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
    other_manager = make_user("OTHER_MANAGER", MANAGER)
    employee = make_user("EMPLOYEE", EMPLOYEE, manager.id)
    leave_type = LeaveType(name="Annual")
    db.session.add(leave_type)
    db.session.flush()
    balance = LeaveBalance(
        user_id=employee.id,
        leave_type_id=leave_type.id,
        year=date.today().year,
        allocated=5,
        used=0,
    )
    db.session.add(balance)
    db.session.commit()

    client = app.test_client()

    def auth(email):
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "password"},
        )
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    employee_headers = auth("employee@example.com")
    manager_headers = auth("manager@example.com")
    other_manager_headers = auth("other_manager@example.com")

    today = date.today()
    leave_today = {
        "leave_type_id": leave_type.id,
        "start_date": today.isoformat(),
        "end_date": today.isoformat(),
        "reason": "Personal appointment",
    }
    past = {**leave_today, "start_date": (today - timedelta(days=1)).isoformat(), "end_date": (today - timedelta(days=1)).isoformat()}
    check("past dates are rejected", client.post("/api/leave/apply", headers=employee_headers, json=past).status_code == 400)
    check("a reason is required", client.post("/api/leave/apply", headers=employee_headers, json={**leave_today, "reason": " "}).status_code == 400)

    created = client.post("/api/leave/apply", headers=employee_headers, json=leave_today)
    check("employee can apply for today", created.status_code == 201, created.get_json())
    request_id = created.get_json()["id"]
    check("overlapping pending applications are rejected",
          client.post("/api/leave/apply", headers=employee_headers, json=leave_today).status_code == 409)

    calendar = client.get(
        "/api/attendance/my-calendar",
        headers=employee_headers,
        query_string={"month": today.month, "year": today.year},
    ).get_json()
    check("pending leave is visible on the attendance calendar",
          any(leave["status"] == "pending" for leave in calendar["leaves"]), calendar["leaves"])
    check("manager sees a direct report's request",
          len(client.get("/api/leave/pending-approvals", headers=manager_headers).get_json()) == 1)
    check("another manager cannot approve the request",
          client.post(f"/api/leave/{request_id}/decision", headers=other_manager_headers,
                      json={"decision": "approved"}).status_code == 403)

    approved = client.post(
        f"/api/leave/{request_id}/decision",
        headers=manager_headers,
        json={"decision": "approved"},
    )
    check("manager can approve a direct report's request",
          approved.status_code == 200 and approved.get_json()["status"] == "approved", approved.get_json())
    check("approval deducts the leave balance once", balance.used == 1, balance.used)
    check("a reviewed request cannot be decided twice",
          client.post(f"/api/leave/{request_id}/decision", headers=manager_headers,
                      json={"decision": "approved"}).status_code == 409)

print("ALL LEAVE REQUEST TESTS PASSED")
