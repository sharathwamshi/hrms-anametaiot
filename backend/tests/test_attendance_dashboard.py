import sys
import unittest
from datetime import date, datetime

sys.path.insert(0, ".")

from config import Config


class DashboardTestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


from app import create_app
from app.extensions import db
from app.models import Attendance, CompanySettings, Department, User
from app.roles import EMPLOYEE, MANAGER


class AttendanceDashboardApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(DashboardTestConfig)
        cls.client = cls.app.test_client()

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        department = Department(name="Development")
        db.session.add(department)
        db.session.flush()

        def make_user(code, email, name, role, manager_id=None):
            user = User(
                employee_code=code,
                email=email,
                full_name=name,
                role=role,
                manager_id=manager_id,
                department_id=department.id,
            )
            user.set_password("test-password")
            db.session.add(user)
            db.session.flush()
            return user

        self.manager = make_user("MGR-1", "manager@test.invalid", "Manager One", MANAGER)
        self.employee = make_user("EMP-1", "employee@test.invalid", "Employee One", EMPLOYEE, self.manager.id)
        other_manager = make_user("MGR-2", "other-manager@test.invalid", "Manager Two", MANAGER)
        self.other_employee = make_user("EMP-2", "other@test.invalid", "Other Employee", EMPLOYEE, other_manager.id)
        db.session.add(CompanySettings(company_name="Test HRMS", state="Karnataka"))
        db.session.add(Attendance(
            user_id=self.employee.id,
            work_date=date(2026, 10, 23),
            clock_in=datetime(2026, 10, 23, 4, 5),
            clock_out=datetime(2026, 10, 23, 13, 0),
            status="present",
            clock_in_lat=12.9,
            clock_in_lng=77.5,
            clock_in_selfie="private.jpg",
        ))
        db.session.add(Attendance(
            user_id=self.other_employee.id,
            work_date=date(2026, 10, 23),
            clock_in=datetime(2026, 10, 23, 4, 0),
            status="present",
        ))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def headers(self, email):
        response = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": "test-password"},
        )
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    def test_manager_analytics_is_scoped_and_returns_dashboard_fields_only(self):
        response = self.client.get(
            "/api/attendance/team/analytics?from=2026-10-23&to=2026-10-23",
            headers=self.headers("manager@test.invalid"),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual([person["employee_code"] for person in payload["employees"]], ["EMP-1"])
        self.assertEqual(payload["policy"]["official_check_in"], "09:30")
        self.assertEqual(payload["employees"][0]["records"][0]["clock_in"], "2026-10-23T04:05:00")
        self.assertNotIn("clock_in_lat", payload["employees"][0]["records"][0])
        self.assertNotIn("clock_in_selfie", payload["employees"][0]["records"][0])

    def test_employee_cannot_access_team_analytics(self):
        response = self.client.get(
            "/api/attendance/team/analytics?from=2026-10-23&to=2026-10-23",
            headers=self.headers("employee@test.invalid"),
        )
        self.assertEqual(response.status_code, 403)

    def test_employee_calendar_contains_only_the_signed_in_employees_records(self):
        response = self.client.get(
            "/api/attendance/my-calendar?month=10&year=2026",
            headers=self.headers("employee@test.invalid"),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["user"]["id"], self.employee.id)
        self.assertEqual(len(payload["records"]), 1)
        self.assertEqual(payload["records"][0]["clock_in"], "2026-10-23T04:05:00")

    def test_manager_analytics_returns_only_records_in_selected_range(self):
        response = self.client.get(
            "/api/attendance/team/analytics?from=2026-10-24&to=2026-10-24",
            headers=self.headers("manager@test.invalid"),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["from"], "2026-10-24")
        self.assertEqual(payload["to"], "2026-10-24")
        self.assertEqual(payload["employees"][0]["records"], [])

    def test_analytics_rejects_invalid_and_oversized_ranges(self):
        headers = self.headers("manager@test.invalid")
        invalid = self.client.get(
            "/api/attendance/team/analytics?from=not-a-date&to=2026-10-23",
            headers=headers,
        )
        oversized = self.client.get(
            "/api/attendance/team/analytics?from=2026-01-01&to=2026-04-10",
            headers=headers,
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(oversized.status_code, 400)


if __name__ == "__main__":
    unittest.main()
