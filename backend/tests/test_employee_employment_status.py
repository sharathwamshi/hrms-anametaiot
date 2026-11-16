import sys
sys.path.insert(0, ".")

from datetime import date
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
    response = client.get("/api/auth/me", headers=employee_headers)
    check("employment status is exposed in the signed-in profile", response.get_json()["user"]["employment_status"] == "active")

    response = client.post("/api/employees/me/resignation", headers=employee_headers)
    check("legacy submission API cannot bypass resignation workflow", response.status_code == 410)
    response = client.post("/api/employees/me/resignation/withdraw", headers=employee_headers)
    check("legacy withdrawal API cannot bypass approval", response.status_code == 410)
    response = client.post(
        f"/api/employees/{employee.id}/resignation/review",
        headers=manager_headers,
        json={"decision": "accepted"},
    )
    check("legacy review API cannot bypass staged approvals", response.status_code == 410)
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
    check("marking employee as left records departure date", response.get_json()["employee"]["left_company_at"] == date.today().isoformat())
    response = client.post(
        f"/api/employees/{employee.id}/employment-status",
        headers=employee_headers,
        json={"employment_status": "active"},
    )
    check("employee cannot reactivate their own employment", response.status_code == 403)
    response = client.post(
        f"/api/employees/{employee.id}/employment-status",
        headers=manager_headers,
        json={"employment_status": "active"},
    )
    check("direct manager can reactivate employment", response.status_code == 200 and response.get_json()["employee"]["employment_status"] == "active")
    check("reactivation clears the departure date", response.get_json()["employee"]["left_company_at"] is None)

print("All employment-status checks passed.")
