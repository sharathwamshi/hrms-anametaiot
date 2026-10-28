import sys
sys.path.insert(0, ".")

from datetime import date, timedelta
from config import Config


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


from app import create_app
from app.extensions import db
from app.models import Department, User
from app.roles import EMPLOYEE, HR_OPERATIONS, MANAGER


app = create_app(TestConfig)


def check(label, condition, details=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        raise SystemExit(f"FAILED: {label} {details}")


with app.app_context():
    db.create_all()
    department = Department(name="Engineering")
    db.session.add(department)
    db.session.flush()

    def create_user(code, role, manager_id=None):
        user = User(
            employee_code=code,
            full_name=code,
            email=f"{code.lower()}@example.com",
            role=role,
            department_id=department.id,
            manager_id=manager_id,
            date_of_joining=date(2024, 1, 1),
        )
        user.set_password("password")
        db.session.add(user)
        db.session.flush()
        return user

    manager = create_user("M1", MANAGER)
    other_manager = create_user("M2", MANAGER)
    hr = create_user("HR", HR_OPERATIONS)
    employee = create_user("E1", EMPLOYEE, manager.id)
    outsider = create_user("E2", EMPLOYEE, other_manager.id)
    db.session.commit()

    client = app.test_client()

    def headers(code):
        response = client.post(
            "/api/auth/login",
            json={"email": f"{code.lower()}@example.com", "password": "password"},
        )
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    employee_headers = headers("E1")
    manager_headers = headers("M1")
    other_manager_headers = headers("M2")
    hr_headers = headers("HR")

    response = client.get("/api/auth/me", headers=employee_headers)
    check("employment status is exposed in the signed-in profile", response.get_json()["user"]["employment_status"] == "active")

    response = client.post("/api/employees/me/resignation", headers=employee_headers)
    check("employee can submit a resignation request", response.status_code == 201)
    check("request sets status to pending", response.get_json()["user"]["employment_status"] == "resignation_pending")
    pending_as_manager = client.get(
        "/api/employees?status=resignation_pending",
        headers=manager_headers,
    )
    check("manager can see pending requests from direct reports", any(row["id"] == employee.id for row in pending_as_manager.get_json()))
    pending_as_other_manager = client.get(
        "/api/employees?status=resignation_pending",
        headers=other_manager_headers,
    )
    check("manager cannot see resignation requests outside their team", pending_as_other_manager.get_json() == [])
    pending_as_hr = client.get(
        "/api/employees?status=resignation_pending",
        headers=hr_headers,
    )
    check("HR Operations can see organization-wide pending requests", any(row["id"] == employee.id for row in pending_as_hr.get_json()))

    response = client.post(
        f"/api/employees/{employee.id}/resignation/review",
        headers=other_manager_headers,
        json={"decision": "accepted", "last_working_day": (date.today() + timedelta(days=14)).isoformat()},
    )
    check("a different manager cannot review the resignation", response.status_code == 403)

    response = client.post(
        f"/api/employees/{employee.id}/resignation/review",
        headers=hr_headers,
        json={"decision": "accepted", "last_working_day": (date.today() + timedelta(days=14)).isoformat()},
    )
    check("HR Operations can review employee resignation requests", response.status_code == 200 and response.get_json()["employee"]["notice_period_days"] == 14)

    client.post("/api/employees/me/resignation/withdraw", headers=employee_headers)
    client.post("/api/employees/me/resignation", headers=employee_headers)

    response = client.post(
        f"/api/employees/{employee.id}/resignation/review",
        headers=manager_headers,
        json={"decision": "accepted", "last_working_day": "not-a-date"},
    )
    check("manager must select a valid notice-period end date", response.status_code == 400)
    response = client.post(
        f"/api/employees/{employee.id}/resignation/review",
        headers=manager_headers,
        json={"decision": "accepted", "last_working_day": (date.today() - timedelta(days=1)).isoformat()},
    )
    check("past notice-period end date is rejected", response.status_code == 400)

    selected_end_date = date.today() + timedelta(days=30)
    response = client.post(
        f"/api/employees/{employee.id}/resignation/review",
        headers=manager_headers,
        json={"decision": "accepted", "last_working_day": selected_end_date.isoformat()},
    )
    body = response.get_json()["employee"]
    check("manager acceptance starts the configured notice period", body["employment_status"] == "notice_period" and body["notice_period_days"] == 30)
    check("selected date is stored as the last working day", body["last_working_day"] == selected_end_date.isoformat())

    response = client.post("/api/employees/me/resignation/withdraw", headers=employee_headers)
    check("employee can withdraw an accepted resignation", response.status_code == 200 and response.get_json()["user"]["employment_status"] == "active")

    client.post("/api/employees/me/resignation", headers=employee_headers)
    response = client.post("/api/employees/me/resignation/withdraw", headers=employee_headers)
    check("employee can also withdraw while manager review is pending", response.status_code == 200 and response.get_json()["user"]["employment_status"] == "active")

    client.post("/api/employees/me/resignation", headers=employee_headers)
    response = client.post(
        f"/api/employees/{employee.id}/resignation/review",
        headers=manager_headers,
        json={"decision": "rejected"},
    )
    check("manager rejection returns status to Active", response.status_code == 200 and response.get_json()["employee"]["employment_status"] == "active")

    client.post("/api/employees/me/resignation", headers=employee_headers)
    accepted = client.post(
        f"/api/employees/{employee.id}/resignation/review",
        headers=manager_headers,
        json={"decision": "accepted", "last_working_day": (date.today() + timedelta(days=90)).isoformat()},
    )
    check("manager can choose a custom notice period", accepted.status_code == 200 and accepted.get_json()["employee"]["notice_period_days"] == 90)
    response = client.post(
        f"/api/employees/{outsider.id}/employment-status",
        headers=manager_headers,
        json={"employment_status": "left"},
    )
    check("manager cannot mark another manager's report as left", response.status_code == 403)
    response = client.post(
        f"/api/employees/{employee.id}/employment-status",
        headers=manager_headers,
        json={"employment_status": "left"},
    )
    check("direct manager can mark an employee as having left", response.status_code == 200 and response.get_json()["employee"]["employment_status"] == "left")

print("All employment-status checks passed.")
