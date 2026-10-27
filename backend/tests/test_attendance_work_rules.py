import sys
import unittest
from datetime import date, datetime, time, timedelta

sys.path.insert(0, ".")

from config import Config
from app import create_app
from app.extensions import db
from app.models import Attendance, AttendanceSession, CompanySettings, Department, User
from app.models.attendance import AUTO_CLOCK_OUT_NOTE
from app.roles import EMPLOYEE, MANAGER
from app.utils.company_time import company_today, to_company_local


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
            "other_manager": self._auth("other@test.com"),
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
                "work_date": company_today().isoformat(),
                "sessions": [{"clock_in": check_in, "clock_out": check_out}],
                "note": "Verified correction",
            },
        )

    def test_inclusive_arrival_buffer_boundaries(self):
        day = company_today()
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

    def test_company_timezone_and_utc_timestamp_conventions(self):
        self.assertEqual(self.app.config["COMPANY_TIMEZONE"], "Asia/Kolkata")
        self.assertEqual(
            to_company_local(datetime(2026, 10, 21, 18, 30)).isoformat(),
            "2026-10-22T00:00:00+05:30",
        )
        response = self.client.get("/api/attendance/policy", headers=self.headers["manager"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["company_timezone"], "Asia/Kolkata")

    def test_team_attendance_records_support_date_filters_and_access_checks(self):
        today = company_today()
        yesterday = today - timedelta(days=1)
        db.session.add_all([
            Attendance(
                user_id=self.employee_id, work_date=today, status="present",
                total_hours=8, clock_in=datetime.combine(today, time(4, 0)),
                clock_out=datetime.combine(today, time(12, 0)),
            ),
            Attendance(
                user_id=self.employee_id, work_date=yesterday, status="half_day",
                total_hours=3.5,
            ),
            Attendance(
                user_id=self.other_employee_id, work_date=today, status="present",
                total_hours=8,
            ),
        ])
        db.session.commit()

        url = f"/api/attendance/team/{self.employee_id}/records"
        response = self.client.get(url, headers=self.headers["manager"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [record["work_date"] for record in response.get_json()],
            [today.isoformat(), yesterday.isoformat()],
        )

        response = self.client.get(
            url, headers=self.headers["manager"],
            query_string={"start_date": today.isoformat(), "end_date": today.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([record["work_date"] for record in response.get_json()], [today.isoformat()])

        response = self.client.get(
            url, headers=self.headers["manager"],
            query_string={"start_date": "2026-02-30"},
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.get(
            url, headers=self.headers["manager"],
            query_string={"start_date": today.isoformat(), "end_date": yesterday.isoformat()},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.get(
                f"/api/attendance/team/{self.employee_id}/records",
                headers=self.headers["other_manager"],
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(url, headers=self.headers["employee"]).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                f"/api/attendance/team/{self.other_employee_id}/records",
                headers=self.headers["employee"],
            ).status_code,
            403,
        )

    def test_manual_correction_replaces_automatic_midnight_clock_out(self):
        today = company_today()
        check_in = datetime.fromisoformat(ist_iso(today, 9, 30).replace("Z", "+00:00")).replace(tzinfo=None)
        midnight = datetime.fromisoformat(ist_iso(today + timedelta(days=1), 0).replace("Z", "+00:00")).replace(tzinfo=None)
        record = Attendance(
            user_id=self.employee_id, work_date=today, status="half_day", total_hours=14.5,
        )
        record.sessions.append(AttendanceSession(
            session_no=1, clock_in=check_in, clock_out=midnight,
            clock_out_note=AUTO_CLOCK_OUT_NOTE,
        ))
        db.session.add(record)
        db.session.commit()

        response = self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["manager"],
            json={
                "user_id": self.employee_id,
                "work_date": today.isoformat(),
                "sessions": [{
                    "id": record.sessions[0].id,
                    "clock_in": ist_iso(today, 9, 30),
                    "clock_out": ist_iso(today, 18, 30),
                }],
                "reason": "Corrected with verified punch time",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        corrected = response.get_json()
        self.assertEqual(corrected["status"], "present")
        self.assertEqual(corrected["total_hours"], 9)
        self.assertFalse(corrected["sessions"][0]["automatic_clock_out"])
        self.assertIsNone(corrected["sessions"][0]["clock_out_note"])

    def test_correcting_legacy_attendance_keeps_punch_evidence(self):
        day = company_today()
        record = Attendance(
            user_id=self.employee_id,
            work_date=day,
            status="present",
            total_hours=8,
            clock_in=datetime.fromisoformat(ist_iso(day, 9, 30).replace("Z", "+00:00")).replace(tzinfo=None),
            clock_out=datetime.fromisoformat(ist_iso(day, 17, 30).replace("Z", "+00:00")).replace(tzinfo=None),
            clock_in_lat=12.9716,
            clock_in_lng=77.5946,
        )
        db.session.add(record)
        db.session.commit()

        response = self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["manager"],
            json={
                "user_id": self.employee_id,
                "work_date": day.isoformat(),
                "sessions": [{
                    "id": None,
                    "clock_in": ist_iso(day, 9, 31),
                    "clock_out": ist_iso(day, 17, 30),
                }],
                "reason": "Verified the original punch",
            },
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["sessions"][0]["clock_in_lat"], 12.9716)
        self.assertEqual(response.get_json()["sessions"][0]["clock_in_lng"], 77.5946)

    def test_updating_only_checkout_preserves_checkin_and_recalculates(self):
        day = company_today()
        response = self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["manager"],
            json={
                "user_id": self.employee_id,
                "work_date": day.isoformat(),
                "sessions": [{
                    "id": None,
                    "clock_in": ist_iso(day, 9, 30),
                    "clock_out": ist_iso(day, 12, 0),
                }],
                "reason": "Initial verified times",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        initial = response.get_json()

        response = self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["manager"],
            json={
                "user_id": self.employee_id,
                "work_date": day.isoformat(),
                "sessions": [{
                    "id": initial["sessions"][0]["id"],
                    "clock_in": initial["sessions"][0]["clock_in"],
                    "clock_out": ist_iso(day, 18, 30),
                }],
                "reason": "Corrected checkout from approved timesheet",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        corrected = response.get_json()
        self.assertEqual(corrected["clock_in"], initial["clock_in"])
        self.assertEqual(corrected["clock_out"], ist_iso(day, 18, 30).removesuffix("Z"))
        self.assertEqual(corrected["total_hours"], 9)
        self.assertEqual(corrected["status"], "present")
        self.assertEqual(corrected["edit_note"], "Corrected checkout from approved timesheet")

    def test_time_only_endpoint_edits_each_field_and_retains_audit(self):
        day = company_today()
        initial = self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["manager"],
            json={
                "user_id": self.employee_id,
                "work_date": day.isoformat(),
                "sessions": [{
                    "id": None,
                    "clock_in": ist_iso(day, 9, 30),
                    "clock_out": ist_iso(day, 18, 30),
                }],
                "reason": "Initial punch correction",
            },
        )
        self.assertEqual(initial.status_code, 200, initial.get_json())
        initial_record = initial.get_json()
        record_id = initial_record["id"]

        updated_checkin = self.client.put(
            f"/api/attendance/manager/records/{record_id}/time",
            headers=self.headers["manager"],
            json={"field": "clock_in", "time": "10:00", "reason": "Verified check-in"},
        )
        self.assertEqual(updated_checkin.status_code, 200, updated_checkin.get_json())
        after_checkin = updated_checkin.get_json()
        self.assertEqual(after_checkin["clock_in"], ist_iso(day, 10, 0).removesuffix("Z"))
        self.assertEqual(after_checkin["clock_out"], initial_record["clock_out"])
        self.assertEqual(after_checkin["total_hours"], 8.5)
        self.assertEqual(after_checkin["status"], "present")
        self.assertEqual(after_checkin["edit_note"], "Verified check-in")

        updated_checkout = self.client.put(
            f"/api/attendance/manager/records/{record_id}/time",
            headers=self.headers["manager"],
            json={"field": "clock_out", "time": "13:30", "reason": "Confirmed early departure"},
        )
        self.assertEqual(updated_checkout.status_code, 200, updated_checkout.get_json())
        after_checkout = updated_checkout.get_json()
        self.assertEqual(after_checkout["clock_in"], after_checkin["clock_in"])
        self.assertEqual(after_checkout["clock_out"], ist_iso(day, 13, 30).removesuffix("Z"))
        self.assertEqual(after_checkout["total_hours"], 3.5)
        self.assertEqual(after_checkout["status"], "half_day")
        self.assertEqual(after_checkout["edited_by_name"], "Manager")
        self.assertEqual(after_checkout["edit_note"], "Confirmed early departure")
        self.assertEqual(len(after_checkout["edit_details"]["history"]), 2)
        self.assertEqual(
            after_checkout["edit_details"]["history"][0]["edit_note"],
            "Initial punch correction",
        )
        self.assertEqual(
            after_checkout["edit_details"]["history"][1]["edit_note"],
            "Verified check-in",
        )
        self.assertEqual(
            Attendance.query.filter_by(user_id=self.employee_id, work_date=day).count(),
            1,
        )

    def test_time_only_endpoint_adds_missing_checkout_and_rejects_bad_requests(self):
        day = company_today()
        open_record = self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["manager"],
            json={
                "user_id": self.employee_id,
                "work_date": day.isoformat(),
                "sessions": [{
                    "id": None,
                    "clock_in": ist_iso(day, 9, 30),
                    "clock_out": None,
                }],
                "reason": "Recorded employee check-in",
            },
        )
        self.assertEqual(open_record.status_code, 200, open_record.get_json())
        initial = open_record.get_json()
        record_id = initial["id"]

        missing_reason = self.client.put(
            f"/api/attendance/manager/records/{record_id}/time",
            headers=self.headers["manager"],
            json={"field": "clock_out", "time": "18:30", "reason": "  "},
        )
        self.assertEqual(missing_reason.status_code, 400)
        invalid_time = self.client.put(
            f"/api/attendance/manager/records/{record_id}/time",
            headers=self.headers["manager"],
            json={"field": "clock_out", "time": "25:90", "reason": "Valid reason"},
        )
        self.assertEqual(invalid_time.status_code, 400)
        unauthorized = self.client.put(
            f"/api/attendance/manager/records/{record_id}/time",
            headers=self.headers["other_manager"],
            json={"field": "clock_out", "time": "18:30", "reason": "Valid reason"},
        )
        self.assertEqual(unauthorized.status_code, 403)

        saved = self.client.put(
            f"/api/attendance/manager/records/{record_id}/time",
            headers=self.headers["manager"],
            json={"field": "clock_out", "time": "18:30", "reason": "Forgotten checkout"},
        )
        self.assertEqual(saved.status_code, 200, saved.get_json())
        result = saved.get_json()
        self.assertEqual(result["id"], record_id)
        self.assertEqual(result["clock_out"], ist_iso(day, 18, 30).removesuffix("Z"))
        self.assertEqual(result["total_hours"], 9)
        self.assertEqual(result["status"], "present")
        self.assertEqual(result["edit_note"], "Forgotten checkout")
        self.assertEqual(
            Attendance.query.filter_by(user_id=self.employee_id, work_date=day).count(),
            1,
        )

    def test_time_only_checkout_supports_overnight_shift(self):
        day = company_today()
        initial = self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["manager"],
            json={
                "user_id": self.employee_id,
                "work_date": day.isoformat(),
                "sessions": [{
                    "id": None,
                    "clock_in": ist_iso(day, 22, 0),
                    "clock_out": None,
                }],
                "reason": "Recorded overnight shift",
            },
        )
        self.assertEqual(initial.status_code, 200, initial.get_json())

        saved = self.client.put(
            f"/api/attendance/manager/records/{initial.get_json()['id']}/time",
            headers=self.headers["manager"],
            json={"field": "clock_out", "time": "06:00", "reason": "Confirmed overnight checkout"},
        )
        self.assertEqual(saved.status_code, 200, saved.get_json())
        self.assertEqual(saved.get_json()["total_hours"], 8)
        self.assertEqual(
            to_company_local(datetime.fromisoformat(saved.get_json()["clock_out"])).date(),
            day + timedelta(days=1),
        )

    def test_time_only_endpoint_can_add_a_missing_checkin_to_existing_record(self):
        day = company_today()
        record = Attendance(
            user_id=self.employee_id,
            work_date=day,
            status="absent",
            total_hours=0,
            clock_out=datetime.fromisoformat(ist_iso(day, 12, 0).replace("Z", "+00:00")).replace(tzinfo=None),
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id

        saved = self.client.put(
            f"/api/attendance/manager/records/{record_id}/time",
            headers=self.headers["manager"],
            json={"field": "clock_in", "time": "09:30", "reason": "Verified sign-in record"},
        )

        self.assertEqual(saved.status_code, 200, saved.get_json())
        result = saved.get_json()
        self.assertEqual(result["id"], record_id)
        self.assertEqual(result["clock_in"], ist_iso(day, 9, 30).removesuffix("Z"))
        self.assertEqual(result["clock_out"], ist_iso(day, 12, 0).removesuffix("Z"))
        self.assertEqual(result["total_hours"], 2.5)
        self.assertEqual(result["status"], "half_day")
        self.assertEqual(
            Attendance.query.filter_by(user_id=self.employee_id, work_date=day).count(),
            1,
        )

    def test_time_only_endpoint_can_add_missing_checkin_for_today(self):
        day = company_today()
        record = Attendance(
            user_id=self.employee_id,
            work_date=day,
            status="absent",
            total_hours=0,
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id

        saved = self.client.put(
            f"/api/attendance/manager/records/{record_id}/time",
            headers=self.headers["manager"],
            json={"field": "clock_in", "time": "09:30", "reason": "Verified sign-in record"},
        )

        self.assertEqual(saved.status_code, 200, saved.get_json())
        self.assertEqual(saved.get_json()["status"], "present")
        self.assertTrue(saved.get_json()["currently_clocked_in"])
        self.assertEqual(
            Attendance.query.filter_by(user_id=self.employee_id, work_date=day).count(),
            1,
        )

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

        day = company_today()
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
        response = self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["manager"],
            json={
                "user_id": self.employee_id, "work_date": day.isoformat(),
                "sessions": [{"clock_in": ist_iso(day, 9, 32), "clock_out": check_out}],
                "reason": "Client site confirmation",
                "note": "Verified with the site lead",
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(
            response.get_json()["edit_note"],
            "Client site confirmation: Verified with the site lead",
        )
        self.assertEqual(len(response.get_json()["edit_details"]["history"]), 2)
        self.assertEqual(
            response.get_json()["edit_details"]["history"][-1]["edit_note"],
            "Verified correction",
        )
        invalid_reason = self.client.put(
            "/api/attendance/manager/day",
            headers=self.headers["manager"],
            json={
                "user_id": self.employee_id, "work_date": day.isoformat(),
                "sessions": [{"clock_in": check_in, "clock_out": check_out}],
                "reason": "  ",
            },
        )
        self.assertEqual(invalid_reason.status_code, 400)
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
            user_id=self.employee_id, work_date=company_today()
        ).first()
        self.assertIsNotNone(record.clock_out)
        self.assertEqual(record.sessions[0].clock_out, record.clock_out)
        self.assertEqual(response.get_json()["clock_out"], record.clock_out.isoformat())


if __name__ == "__main__":
    unittest.main()
