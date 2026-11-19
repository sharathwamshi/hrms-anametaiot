import sys
from datetime import date
from pathlib import Path

# backend/tests/test_leave_editing.py -> repository root/backend
BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from config import Config
from app import create_app
from app.extensions import db
from app.models import Department, LeaveBalance, LeaveRequest, LeaveType, User
from app.roles import EMPLOYEE, MANAGER


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


def test_leave_editing_api():
    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        try:
            department = Department(name="Engineering")
            db.session.add(department)
            db.session.flush()

            manager = User(
                employee_code="M1",
                full_name="Manager",
                email="manager@test.com",
                role=MANAGER,
                department_id=department.id,
                date_of_joining=date(2024, 1, 1),
            )
            employee = User(
                employee_code="E1",
                full_name="Employee",
                email="employee@test.com",
                role=EMPLOYEE,
                department_id=department.id,
                manager=manager,
                date_of_joining=date(2024, 1, 1),
            )
            other_employee = User(
                employee_code="E2",
                full_name="Other Employee",
                email="other@test.com",
                role=EMPLOYEE,
                department_id=department.id,
                date_of_joining=date(2024, 1, 1),
            )
            leave_type = LeaveType(name="Casual Leave", annual_quota=12)

            for user in (manager, employee, other_employee):
                user.set_password("pw")

            db.session.add_all([manager, employee, other_employee, leave_type])
            db.session.flush()

            db.session.add(
                LeaveBalance(
                    user_id=employee.id,
                    leave_type_id=leave_type.id,
                    year=2026,
                    allocated=12,
                    used=0,
                )
            )

            pending = LeaveRequest(
                user_id=employee.id,
                leave_type_id=leave_type.id,
                start_date=date(2026, 11, 2),
                end_date=date(2026, 11, 3),
                days=2,
                reason="Initial reason",
                status="pending",
            )
            approved = LeaveRequest(
                user_id=employee.id,
                leave_type_id=leave_type.id,
                start_date=date(2026, 11, 9),
                end_date=date(2026, 11, 9),
                days=1,
                reason="Approved reason",
                status="approved",
            )
            rejected = LeaveRequest(
                user_id=employee.id,
                leave_type_id=leave_type.id,
                start_date=date(2026, 11, 10),
                end_date=date(2026, 11, 10),
                days=1,
                reason="Rejected reason",
                status="rejected",
            )
            db.session.add_all([pending, approved, rejected])
            db.session.commit()

            # Keep IDs before requests are changed or the session is closed.
            pending_id = pending.id
            approved_id = approved.id
            rejected_id = rejected.id
            employee_id = employee.id
            leave_type_id = leave_type.id

            client = app.test_client()

            def login(email):
                response = client.post(
                    "/api/auth/login",
                    json={"email": email, "password": "pw"},
                )
                assert response.status_code == 200, response.get_json()
                return {
                    "Authorization": (
                        f"Bearer {response.get_json()['access_token']}"
                    )
                }

            employee_headers = login("employee@test.com")
            other_headers = login("other@test.com")
            manager_headers = login("manager@test.com")

            edited_fields = {
                "leave_type_id": leave_type_id,
                "start_date": "2026-11-04",
                "end_date": "2026-11-06",
                "reason": "Updated reason",
            }

            response = client.put(
                f"/api/leave/{pending_id}",
                headers=employee_headers,
                json=edited_fields,
            )
            assert response.status_code == 200, response.get_json()
            assert response.get_json()["id"] == pending_id
            assert response.get_json()["days"] == 3
            assert response.get_json()["reason"] == "Updated reason"
            assert response.get_json()["status"] == "pending"
            assert (
                LeaveRequest.query.filter_by(user_id=employee_id).count() == 3
            )

            history = client.get(
                "/api/leave/my-requests", headers=employee_headers
            ).get_json()
            edited_history = next(
                item for item in history if item["id"] == pending_id
            )
            assert edited_history["start_date"] == "2026-11-04"
            assert edited_history["leave_type_id"] == leave_type_id

            approvals = client.get(
                "/api/leave/pending-approvals",
                headers=manager_headers,
            ).get_json()
            edited_approval = next(
                item for item in approvals if item["id"] == pending_id
            )
            assert edited_approval["reason"] == "Updated reason"

            assert client.put(
                f"/api/leave/{pending_id}",
                headers=employee_headers,
                json={
                    **edited_fields,
                    "start_date": "2026-11-07",
                    "end_date": "2026-11-06",
                },
            ).status_code == 400

            assert client.put(
                f"/api/leave/{pending_id}",
                headers=other_headers,
                json=edited_fields,
            ).status_code == 403

            assert client.put(
                f"/api/leave/{approved_id}",
                headers=employee_headers,
                json=edited_fields,
            ).status_code == 400

            assert client.put(
                f"/api/leave/{rejected_id}",
                headers=employee_headers,
                json=edited_fields,
            ).status_code == 400

            assert client.post(
                f"/api/leave/{pending_id}/cancel",
                headers=other_headers,
            ).status_code == 403

            response = client.post(
                f"/api/leave/{pending_id}/cancel",
                headers=employee_headers,
            )
            assert response.status_code == 200, response.get_json()
            assert response.get_json()["status"] == "cancelled"

            assert client.post(
                f"/api/leave/{pending_id}/cancel",
                headers=employee_headers,
            ).status_code == 409

            assert client.put(
                f"/api/leave/{pending_id}",
                headers=employee_headers,
                json=edited_fields,
            ).status_code == 400

            # Cancelled requests cannot be approved or rejected.
            assert client.post(
                f"/api/leave/{pending_id}/decision",
                headers=manager_headers,
                json={"decision": "approved"},
            ).status_code == 400

            approved_cancellation = client.post(
                f"/api/leave/{approved_id}/cancel",
                headers=employee_headers,
            )
            assert approved_cancellation.status_code == 200, approved_cancellation.get_json()

            calendar_response = client.get(
                "/api/attendance/my-calendar?month=11&year=2026",
                headers=employee_headers,
            )
            assert calendar_response.status_code == 200, calendar_response.get_json()
            calendar = calendar_response.get_json()
            calendar_statuses = {
                item["status"] for item in calendar["leave_requests"]
            }
            assert calendar_statuses == {"rejected", "cancelled"}
            assert len(calendar["leaves"]) == 0
        finally:
            db.session.remove()
            db.drop_all()
