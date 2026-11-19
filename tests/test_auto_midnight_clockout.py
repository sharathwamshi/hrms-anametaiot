import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from config import Config
from app import create_app
from app.extensions import db
from app.models import Attendance, AttendanceSession, CompanySettings, Department, User
from app.models.attendance import AUTO_CLOCK_OUT_NOTE
from app.roles import EMPLOYEE


class AutoClockoutTestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    INTERNAL_TASK_SECRET = "test-internal-secret"
    COMPANY_TIMEZONE = "Asia/Kolkata"


class AutoMidnightClockoutTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(AutoClockoutTestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        department = Department(name="Engineering")
        db.session.add(department)
        db.session.flush()
        self.user = User(
            employee_code="E1",
            full_name="Employee",
            email="employee@test.com",
            role=EMPLOYEE,
            department_id=department.id,
            date_of_joining=date(2024, 1, 1),
        )
        self.user.set_password("password")
        self.other_user = User(
            employee_code="E2",
            full_name="Other Employee",
            email="other@test.com",
            role=EMPLOYEE,
            department_id=department.id,
            date_of_joining=date(2024, 1, 1),
        )
        self.other_user.set_password("password")
        db.session.add_all([self.user, self.other_user, CompanySettings(company_name="AnametaIOT")])
        db.session.commit()
        self.client = self.app.test_client()
        login = self.client.post(
            "/api/auth/login",
            json={"email": "employee@test.com", "password": "password"},
        )
        self.headers = {"Authorization": f"Bearer {login.get_json()['access_token']}"}
        self.next_day = date(2026, 11, 1)
        self.closing_day = self.next_day - timedelta(days=1)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def add_record(self, user, work_date, sessions):
        record = Attendance(user_id=user.id, work_date=work_date, status="present")
        db.session.add(record)
        db.session.flush()
        for index, (clock_in, clock_out, note) in enumerate(sessions, 1):
            record.sessions.append(
                AttendanceSession(
                    session_no=index,
                    clock_in=clock_in,
                    clock_out=clock_out,
                    clock_out_note=note,
                )
            )
        db.session.flush()
        record.recompute_from_sessions()
        db.session.commit()
        return record

    def run_task(self, today=None):
        with patch("app.routes.attendance.company_today", return_value=today or self.next_day):
            return self.client.post(
                "/api/attendance/internal/auto-midnight-clockout",
                headers={"X-Internal-Secret": "test-internal-secret"},
            )

    def test_closes_previous_day_at_local_midnight_and_forces_half_day(self):
        manual_checkout = datetime(2026, 10, 31, 10, 0)
        record = self.add_record(
            self.user,
            self.closing_day,
            [
                (datetime(2026, 10, 31, 4, 0), manual_checkout, "Manual checkout"),
                (datetime(2026, 10, 31, 11, 0), None, None),
            ],
        )
        self.add_record(
            self.user,
            self.closing_day - timedelta(days=1),
            [(datetime(2026, 10, 30, 9, 0), datetime(2026, 10, 30, 18, 30), "Manual")],
        )
        midnight_utc = datetime(2026, 10, 31, 18, 30)

        response = self.run_task()

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json(), {
            "work_date": "2026-10-31",
            "closed_sessions": 1,
        })
        db.session.refresh(record)
        self.assertEqual(record.sessions[0].clock_out, manual_checkout)
        self.assertEqual(record.sessions[0].clock_out_note, "Manual checkout")
        self.assertEqual(record.sessions[1].clock_out, midnight_utc)
        self.assertEqual(record.sessions[1].clock_out_note, AUTO_CLOCK_OUT_NOTE)
        self.assertTrue(record.sessions[1].is_automatic_clock_out)
        self.assertEqual(record.total_hours, 13.5)
        self.assertEqual(record.status, "half_day")
        record.recompute_from_sessions()
        self.assertEqual(record.status, "half_day")

        october = self.client.get(
            "/api/attendance/my-calendar",
            headers=self.headers,
            query_string={"month": 10, "year": 2026},
        ).get_json()
        self.assertEqual(october["summary"]["half_day"], 1)
        self.assertEqual(october["automatic_clockout_bell_dates"], [])

        november = self.client.get(
            "/api/attendance/my-calendar",
            headers=self.headers,
            query_string={"month": 11, "year": 2026},
        ).get_json()
        self.assertEqual(november["automatic_clockout_bell_dates"], ["2026-11-01"])
        self.assertEqual(november["records"], [])

    def test_task_is_idempotent_and_does_not_backfill_older_records(self):
        old_record = self.add_record(
            self.other_user,
            self.closing_day - timedelta(days=1),
            [(datetime(2026, 10, 30, 10, 0), None, None)],
        )
        record = self.add_record(
            self.user,
            self.closing_day,
            [(datetime(2026, 10, 31, 10, 0), None, None)],
        )

        first = self.run_task()
        second = self.run_task()

        self.assertEqual(first.get_json()["closed_sessions"], 1)
        self.assertEqual(second.get_json()["closed_sessions"], 0)
        self.assertEqual(record.sessions[0].clock_out, datetime(2026, 10, 31, 18, 30))
        self.assertIsNone(old_record.sessions[0].clock_out)

    def test_does_not_close_session_that_started_at_midnight_or_manual_checkout(self):
        manual_time = datetime(2026, 10, 31, 18, 0)
        self.add_record(
            self.user,
            self.closing_day,
            [(datetime(2026, 10, 31, 10, 0), manual_time, "Manual")],
        )
        midnight_user = User(
            employee_code="E3",
            full_name="Midnight Employee",
            email="midnight@test.com",
            role=EMPLOYEE,
            department_id=self.user.department_id,
            date_of_joining=date(2024, 1, 1),
        )
        midnight_user.set_password("password")
        db.session.add(midnight_user)
        db.session.commit()
        midnight_record = self.add_record(
            midnight_user,
            self.closing_day,
            [(datetime(2026, 10, 31, 18, 30), None, None)],
        )

        response = self.run_task()

        self.assertEqual(response.get_json()["closed_sessions"], 0)
        self.assertEqual(self.user.attendance_records[0].sessions[0].clock_out, manual_time)
        self.assertIsNone(midnight_record.sessions[0].clock_out)

    def test_january_calendar_includes_december_closure_and_is_user_scoped(self):
        december_day = date(2026, 12, 31)
        self.add_record(
            self.user,
            december_day,
            [(datetime(2026, 12, 31, 10, 0), None, None)],
        )
        self.add_record(
            self.other_user,
            december_day,
            [(datetime(2026, 12, 31, 10, 0), datetime(2026, 12, 31, 18, 30), AUTO_CLOCK_OUT_NOTE)],
        )

        response = self.run_task(today=date(2027, 1, 1))

        self.assertEqual(response.get_json()["closed_sessions"], 1)
        january = self.client.get(
            "/api/attendance/my-calendar",
            headers=self.headers,
            query_string={"month": 1, "year": 2027},
        ).get_json()
        self.assertEqual(january["automatic_clockout_bell_dates"], ["2027-01-01"])
        self.assertEqual(january["records"], [])

    def test_endpoint_auth_and_manual_notes_cannot_impersonate_marker(self):
        denied = self.client.post("/api/attendance/internal/auto-midnight-clockout")
        self.assertEqual(denied.status_code, 403)

        record = self.add_record(
            self.user,
            self.next_day,
            [(datetime(2026, 11, 1, 12, 0), None, None)],
        )
        with patch("app.routes.attendance.company_today", return_value=self.next_day):
            response = self.client.post(
                "/api/attendance/clock-out",
                headers=self.headers,
                json={"note": AUTO_CLOCK_OUT_NOTE},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(record.sessions[0].clock_out)

    def test_manual_and_automatic_checkout_updates_are_compare_and_set(self):
        record = self.add_record(
            self.user,
            self.closing_day,
            [(datetime(2026, 10, 31, 10, 0), None, None)],
        )
        session = record.sessions[0]
        manual_time = datetime(2026, 10, 31, 17, 0)
        automatic_time = datetime(2026, 10, 31, 18, 30)

        from app.routes.attendance import _claim_session_clock_out

        self.assertTrue(_claim_session_clock_out(session.id, manual_time, "Manual"))
        self.assertFalse(_claim_session_clock_out(session.id, automatic_time, AUTO_CLOCK_OUT_NOTE))
        db.session.refresh(session)
        self.assertEqual(session.clock_out, manual_time)
        self.assertEqual(session.clock_out_note, "Manual")

        second_record = self.add_record(
            self.other_user,
            self.closing_day,
            [(datetime(2026, 10, 31, 10, 0), None, None)],
        )
        second_session = second_record.sessions[0]
        self.assertTrue(_claim_session_clock_out(second_session.id, automatic_time, AUTO_CLOCK_OUT_NOTE))
        self.assertFalse(_claim_session_clock_out(second_session.id, manual_time, "Manual"))
        db.session.refresh(second_session)
        self.assertEqual(second_session.clock_out, automatic_time)
        self.assertEqual(second_session.clock_out_note, AUTO_CLOCK_OUT_NOTE)


if __name__ == "__main__":
    unittest.main()
