import sys
import unittest
from datetime import date, datetime, time, timedelta

sys.path.insert(0, ".")

from config import Config
from app import create_app
from app.extensions import db
from app.models import Attendance, CompanySettings, Department, User
from app.roles import EMPLOYEE, MANAGER


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


def ist_iso(day, hour, minute=0, second=0):
    local = datetime.combine(day, time(hour, minute, second))
    return (local - timedelta(minutes=330)).isoformat() + "Z"


class AttendanceWorkRuleTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        department = Department(name="Engineering")
        db.session.add(department)
        db.session.flush()

        manager = User(
            employee_code="M1", full_name="Manager", email="manager@test.com",
            role=MANAGER, department_id=department.id, date_of_joining=date(2024, 1, 1),
        )
        manager.set_password("password")
        db.session.add(manager)
        db.session.flush()
        employee = User(
            employee_code="E1", full_name="Employee", email="employee@test.com",
            role=EMPLOYEE, manager_id=manager.id, department_id=department.id,
            date_of_joining=date(2024, 1, 1),
        )
        employee.set_password("password")
        other_manager = User(
            employee_code="M2", full_name="Other Manager", email="other@test.com",
            role=MANAGER, department_id=department.id, date_of_joining=date(2024, 1, 1),
        )
        other_manager.set_password("password")
        db.session.add(other_manager)
        db.session.flush()
        other_employee = User(
            employee_code="E2", full_name="Other Employee", email="other-employee@test.com",
            role=EMPLOYEE, manager_id=other_manager.id, department_id=department.id,
            date_of_joining=date(2024, 1, 1),
        )
        other_employee.set_password("password")
        db.session.add_all([employee, other_employee, CompanySettings(company_name="AnametaIOT")])
        db.session.commit()

        self.employee_id = employee.id
        self.other_employee_id = other_employee.id
        self.client = self.app.test_client()
        self.headers = {
            "manager": self._auth("manager@test.com"),
            "employee": self._auth("employee@test.com"),
            "other_employee": self._auth("other-employee@test.com"),
        }

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _auth(self, email):
        response = self.client.post(
            "/api/auth/login", json={"email": email, "password": "password"}
        )
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    def _correct(self, employee_id, check_in, check_out):
        return self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["manager"],
            json={
                "user_id": employee_id,
                "work_date": date.today().isoformat(),
                "sessions": [{"clock_in": check_in, "clock_out": check_out}],
                "note": "Verified correction",
            },
        )

    def test_inclusive_arrival_buffer_boundaries(self):
        day = date.today()
        for buffer_minutes in (5, 10, 15):
            with self.subTest(buffer=buffer_minutes):
                response = self.client.put(
                    "/api/attendance/policy",
                    headers=self.headers["manager"],
                    json={"attendance_buffer_minutes": buffer_minutes},
                )
                self.assertEqual(response.status_code, 200)
                for hour, minute, expected in (
                    (9, 25, "in_time"),
                    (9, 30, "in_time"),
                    (9, 30 + buffer_minutes, "in_time"),
                    (9, 31 + buffer_minutes, "late"),
                ):
                    response = self._correct(
                        self.employee_id,
                        ist_iso(day, hour, minute),
                        ist_iso(day, 18, 30),
                    )
                    self.assertEqual(response.status_code, 200, response.get_json())
                    self.assertEqual(response.get_json()["check_in_status"], expected)
                response = self._correct(
                    self.employee_id,
                    ist_iso(day, 9, 30 + buffer_minutes, 1),
                    ist_iso(day, 18, 30),
                )
                self.assertEqual(response.get_json()["check_in_status"], "late")

    def test_policy_validation_and_manager_edit_permissions(self):
        response = self.client.put(
            "/api/attendance/policy",
            headers=self.headers["employee"],
            json={"attendance_buffer_minutes": 5},
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.put(
            "/api/attendance/policy",
            headers=self.headers["manager"],
            json={"attendance_buffer_minutes": 7},
        )
        self.assertEqual(response.status_code, 400)

        day = date.today()
        check_in, check_out = ist_iso(day, 9, 30), ist_iso(day, 18, 30)
        response = self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["employee"],
            json={
                "user_id": self.employee_id, "work_date": day.isoformat(),
                "sessions": [{"clock_in": check_in, "clock_out": check_out}],
                "note": "Self edit attempt",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            self._correct(self.other_employee_id, check_in, check_out).status_code, 403
        )

        self.assertEqual(self._correct(self.employee_id, check_in, check_out).status_code, 200)
        response = self._correct(
            self.employee_id, ist_iso(day, 9, 31), check_out
        )
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertIsNotNone(result["edited_at"])
        self.assertNotEqual(
            result["edit_details"]["before"][0]["clock_in"],
            result["edit_details"]["after"][0]["clock_in"],
        )
        self.assertEqual(result["edited_by_name"], "Manager")
        bad_checkout = self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["manager"],
            json={
                "user_id": self.employee_id, "work_date": day.isoformat(),
                "sessions": [{"clock_in": check_in, "clock_out": False}],
                "note": "Bad checkout",
            },
        )
        self.assertEqual(bad_checkout.status_code, 400)

    def test_clock_out_records_actual_timestamp(self):
        response = self.client.post(
            "/api/attendance/clock-in", headers=self.headers["employee"], json={}
        )
        self.assertEqual(response.status_code, 201)
        response = self.client.post(
            "/api/attendance/clock-out", headers=self.headers["employee"], json={}
        )
        self.assertEqual(response.status_code, 200)
        record = Attendance.query.filter_by(
            user_id=self.employee_id, work_date=date.today()
        ).first()
        self.assertIsNotNone(record.clock_out)
        self.assertEqual(record.sessions[0].clock_out, record.clock_out)
        self.assertEqual(response.get_json()["clock_out"], record.clock_out.isoformat())


if __name__ == "__main__":
    unittest.main()
