import json
import os
import sys
import unittest
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from app import create_app
from app.extensions import db
from app.models import Announcement, Department, User
from app.roles import (
    CONTRACT_EMPLOYEE,
    EMPLOYEE,
    FINANCE_ACCOUNTS,
    HR_OPERATIONS,
    MANAGER,
    OPERATIONS,
)
from app.utils.official_announcements import utc_naive


IST = ZoneInfo("Asia/Kolkata")
FIXED_NOW = datetime(2026, 4, 4, 12, 0, tzinfo=IST)


class AnnouncementTestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    COMPANY_TIMEZONE = "Asia/Kolkata"


class FreshAnnouncementTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(AnnouncementTestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.department = Department(name="Engineering")
        db.session.add(self.department)
        db.session.flush()
        self.hr = self.add_user("hr", "HR Publisher", HR_OPERATIONS)
        self.employee = self.add_user(
            "employee",
            "Employee Recipient",
            EMPLOYEE,
            department_id=self.department.id,
        )
        self.other_employee = self.add_user("other", "Other Employee", EMPLOYEE)
        self.manager = self.add_user("manager", "Team Manager", MANAGER)
        self.finance = self.add_user("finance", "Finance User", FINANCE_ACCOUNTS)
        self.operations = self.add_user("operations", "Operations User", OPERATIONS)
        self.contract_employee = self.add_user("contract", "Contract User", CONTRACT_EMPLOYEE)
        db.session.commit()
        self.client = self.app.test_client()
        self.headers = {
            "hr": self.login(self.hr),
            "employee": self.login(self.employee),
            "other": self.login(self.other_employee),
            "manager": self.login(self.manager),
            "finance": self.login(self.finance),
            "operations": self.login(self.operations),
            "contract": self.login(self.contract_employee),
        }

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def add_user(self, code, name, role, **kwargs):
        user = User(
            employee_code=code,
            full_name=name,
            email=f"{code}@test.local",
            role=role,
            **kwargs,
        )
        user.set_password("test-password")
        db.session.add(user)
        db.session.flush()
        return user

    def login(self, user):
        response = self.client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "test-password"},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    def payload(self, **overrides):
        result = {
            "title": "Scheduled company update",
            "message": "A message for selected recipients.",
            "category": "general",
            "priority": "normal",
            "audiences": {
                "everyone": False,
                "user_ids": [self.employee.id],
                "department_ids": [],
                "roles": [],
            },
            "duration_unit": "days",
            "duration_value": 1,
        }
        result.update(overrides)
        return result

    def request_at_fixed_time(self, method, url, **kwargs):
        with (
            patch("app.routes.announcements.now_ist", return_value=FIXED_NOW),
            patch("app.utils.official_announcements.now_ist", return_value=FIXED_NOW),
        ):
            return getattr(self.client, method)(url, **kwargs)

    def test_non_employee_roles_can_manage_and_sender_is_from_authenticated_profile(self):
        for role, key in (
            (MANAGER, "manager"),
            (FINANCE_ACCOUNTS, "finance"),
            (OPERATIONS, "operations"),
            (CONTRACT_EMPLOYEE, "contract"),
        ):
            response = self.request_at_fixed_time(
                "post",
                "/api/announcements",
                headers=self.headers[key],
                json=self.payload(title=f"{role} announcement"),
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.get_json()["author_name"], {
                MANAGER: "Team Manager",
                FINANCE_ACCOUNTS: "Finance User",
                OPERATIONS: "Operations User",
                CONTRACT_EMPLOYEE: "Contract User",
            }[role])
            self.assertEqual(response.get_json()["author_role"], role)

    def test_employee_cannot_create_edit_or_delete(self):
        created = self.request_at_fixed_time(
            "post",
            "/api/announcements",
            headers=self.headers["hr"],
            json=self.payload(),
        )
        announcement_id = created.get_json()["id"]
        self.assertEqual(
            self.client.post(
                "/api/announcements",
                headers=self.headers["employee"],
                json=self.payload(),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.put(
                f"/api/announcements/{announcement_id}",
                headers=self.headers["employee"],
                json=self.payload(),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/announcements/{announcement_id}",
                headers=self.headers["employee"],
            ).status_code,
            403,
        )

    def test_visibility_uses_selected_users_departments_and_roles(self):
        cases = [
            ({"user_ids": [self.employee.id]}, self.headers["employee"], self.headers["other"]),
            ({"department_ids": [self.department.id]}, self.headers["employee"], self.headers["other"]),
            ({"roles": [EMPLOYEE]}, self.headers["employee"], self.headers["manager"]),
        ]
        for index, (selection, visible_headers, hidden_headers) in enumerate(cases):
            audiences = {
                "everyone": False,
                "user_ids": [],
                "department_ids": [],
                "roles": [],
                **selection,
            }
            response = self.client.post(
                "/api/announcements",
                headers=self.headers["hr"],
                json=self.payload(title=f"Targeted {index}", audiences=audiences),
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(
                len(self.client.get("/api/announcements", headers=visible_headers).get_json()),
                index + 1,
            )
            self.assertEqual(
                len(self.client.get("/api/announcements", headers=hidden_headers).get_json()),
                0,
            )

    def test_schedule_expiry_history_and_soft_delete(self):
        active = self.client.post(
            "/api/announcements",
            headers=self.headers["hr"],
            json=self.payload(
                publish_at="2026-04-04T11:00",
                duration_unit="hours",
                duration_value=3,
            ),
        )
        scheduled = self.client.post(
            "/api/announcements",
            headers=self.headers["hr"],
            json=self.payload(
                title="Future message",
                publish_at="2026-04-04T13:00",
                expires_at="2026-04-05T13:00+05:30",
                duration_unit="custom",
            ),
        )
        expired = self.client.post(
            "/api/announcements",
            headers=self.headers["hr"],
            json=self.payload(
                title="Past message",
                publish_at="2026-04-04T09:00",
                expires_at="2026-04-04T11:00+05:30",
                duration_unit="custom",
            ),
        )
        self.assertEqual([active.status_code, scheduled.status_code, expired.status_code], [201, 201, 201])

        with (
            patch("app.routes.announcements.now_ist", return_value=FIXED_NOW),
            patch("app.utils.official_announcements.now_ist", return_value=FIXED_NOW),
        ):
            visible = self.client.get("/api/announcements", headers=self.headers["employee"]).get_json()
            self.assertEqual([item["title"] for item in visible], ["Scheduled company update"])
            for status, expected in (("active", 1), ("scheduled", 1), ("expired", 1), ("all", 3)):
                response = self.client.get(
                    "/api/announcements?scope=manage&status=" + status,
                    headers=self.headers["hr"],
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.get_json()), expected)

        announcement_id = active.get_json()["id"]
        self.assertEqual(
            self.client.put(
                f"/api/announcements/{announcement_id}",
                headers=self.headers["hr"],
                json=self.payload(title="Updated in place"),
            ).status_code,
            200,
        )
        self.assertEqual(Announcement.query.count(), 3)
        self.assertEqual(
            self.client.delete(
                f"/api/announcements/{announcement_id}",
                headers=self.headers["hr"],
            ).status_code,
            200,
        )
        self.assertEqual(
            len(self.client.get(
                "/api/announcements?scope=manage&status=all",
                headers=self.headers["hr"],
            ).get_json()),
            2,
        )

    def test_dashboard_priority_and_displaced_no_expiry_history(self):
        publication_times = [
            ("Expiring newest", 11, 0, 15, 0, 11, 0),
            ("Expiring older", 10, 0, 18, 0, 10, 0),
            ("Permanent newest", 11, 30, None, None, 11, 30),
            ("Permanent older", 8, 0, None, None, 8, 0),
            ("Future notice", 13, 0, 14, 0, 13, 0),
            ("Expired notice", 7, 0, 11, 0, 7, 0),
        ]
        for title, publish_hour, publish_minute, expiry_hour, expiry_minute, created_hour, created_minute in publication_times:
            publish_at = datetime(2026, 4, 4, publish_hour, publish_minute, tzinfo=IST)
            expires_at = (
                datetime(2026, 4, 4, expiry_hour, expiry_minute, tzinfo=IST)
                if expiry_hour is not None
                else None
            )
            created_at = datetime(2026, 4, 4, created_hour, created_minute, tzinfo=IST)
            db.session.add(Announcement(
                title=title,
                body=title,
                category="general",
                priority="normal",
                audiences={"everyone": True, "user_ids": [], "department_ids": [], "roles": []},
                publish_at=utc_naive(publish_at),
                expires_at=utc_naive(expires_at) if expires_at else None,
                created_at=utc_naive(created_at),
                posted_by=self.hr.id,
            ))
        db.session.commit()

        dashboard = self.request_at_fixed_time(
            "get",
            "/api/dashboard/summary",
            headers=self.headers["employee"],
        )
        self.assertEqual(dashboard.status_code, 200)
        recent = dashboard.get_json()["recent_announcements"]
        self.assertEqual([item["title"] for item in recent], ["Permanent newest", "Expiring newest"])
        self.assertLessEqual(len(recent), 2)

        full_page = self.request_at_fixed_time(
            "get",
            "/api/announcements?scope=manage&status=all",
            headers=self.headers["hr"],
        )
        self.assertEqual(
            [item["title"] for item in full_page.get_json()],
            [
                "Future notice",
                "Permanent newest",
                "Expiring newest",
                "Expiring older",
                "Permanent older",
                "Expired notice",
            ],
        )
        self.assertEqual(
            {
                item["title"]: item["status"]
                for item in full_page.get_json()
                if item["title"].startswith("Permanent")
            },
            {"Permanent newest": "active", "Permanent older": "history"},
        )
        self.assertEqual(
            [
                item["title"]
                for item in self.request_at_fixed_time(
                    "get",
                    "/api/announcements?scope=manage&status=history",
                    headers=self.headers["hr"],
                ).get_json()
            ],
            ["Permanent older", "Expired notice"],
        )
        self.assertEqual(
            [
                item["title"]
                for item in self.request_at_fixed_time(
                    "get",
                    "/api/announcements?scope=visible&status=history",
                    headers=self.headers["employee"],
                ).get_json()
            ],
            ["Permanent older", "Expired notice"],
        )

        one_expiring_left = datetime(2026, 4, 4, 15, 30, tzinfo=IST)
        with (
            patch("app.routes.announcements.now_ist", return_value=one_expiring_left),
            patch("app.utils.official_announcements.now_ist", return_value=one_expiring_left),
        ):
            later_dashboard = self.client.get(
                "/api/dashboard/summary",
                headers=self.headers["employee"],
            ).get_json()["recent_announcements"]
        self.assertEqual(
            [item["title"] for item in later_dashboard],
            ["Permanent newest", "Expiring older"],
        )

        all_expiring_expired = datetime(2026, 4, 4, 19, 0, tzinfo=IST)
        with (
            patch("app.routes.announcements.now_ist", return_value=all_expiring_expired),
            patch("app.utils.official_announcements.now_ist", return_value=all_expiring_expired),
        ):
            final_dashboard = self.client.get(
                "/api/dashboard/summary",
                headers=self.headers["employee"],
            ).get_json()["recent_announcements"]
        self.assertEqual(
            [item["title"] for item in final_dashboard],
            ["Permanent newest", "Permanent older"],
        )
        self.assertEqual(Announcement.query.count(), 6)

    def test_indefinite_announcement_has_no_expiry_and_remains_visible(self):
        payload = self.payload(
            title="Ongoing company notice",
            publish_at="2026-04-04T11:00",
        )
        payload.pop("duration_unit")
        payload.pop("duration_value")
        created = self.request_at_fixed_time(
            "post",
            "/api/announcements",
            headers=self.headers["hr"],
            json=payload,
        )
        self.assertEqual(created.status_code, 201)
        self.assertIsNone(created.get_json()["expires_at"])

        later = datetime(2030, 4, 4, 12, 0, tzinfo=IST)
        with (
            patch("app.routes.announcements.now_ist", return_value=later),
            patch("app.utils.official_announcements.now_ist", return_value=later),
        ):
            visible = self.client.get("/api/announcements", headers=self.headers["employee"]).get_json()
            dashboard = self.client.get(
                "/api/dashboard/summary",
                headers=self.headers["employee"],
            ).get_json()["recent_announcements"]
        self.assertEqual([item["title"] for item in visible], ["Ongoing company notice"])
        self.assertEqual([item["title"] for item in dashboard], ["Ongoing company notice"])

    def test_invalid_audience_and_expiry_are_rejected(self):
        invalid_id = self.client.post(
            "/api/announcements",
            headers=self.headers["hr"],
            json=self.payload(audiences={
                "everyone": False,
                "user_ids": [999999],
                "department_ids": [],
                "roles": [],
            }),
        )
        self.assertEqual(invalid_id.status_code, 400)
        invalid_expiry = self.client.post(
            "/api/announcements",
            headers=self.headers["hr"],
            json=self.payload(
                duration_unit="custom",
                expires_at="2026-04-04T10:00+05:30",
            ),
        )
        self.assertEqual(invalid_expiry.status_code, 400)

    def test_birthdays_are_private_dynamic_and_use_ist_date_with_leap_day_policy(self):
        self.employee.designation = "Designer"
        self.employee.avatar_url = "/static/uploads/employee.png"
        leap_day = self.add_user(
            "DOB-2",
            "Rahul Das",
            MANAGER,
            date_of_birth=date(1988, 2, 29),
            designation="Team Lead",
        )
        inactive = self.add_user(
            "DOB-3",
            "Inactive Person",
            EMPLOYEE,
            date_of_birth=date(1994, 3, 1),
            is_active=False,
        )
        departed = self.add_user(
            "DOB-4",
            "Departed Person",
            EMPLOYEE,
            date_of_birth=date(1995, 3, 1),
            employment_status="left",
        )
        db.session.commit()
        profile_update = self.client.patch(
            "/api/profile/me",
            headers=self.headers["employee"],
            json={"date_of_birth": "1990-03-01"},
        )
        self.assertEqual(profile_update.status_code, 200)
        self.assertEqual(profile_update.get_json()["profile"]["date_of_birth"], "1990-03-01")

        headers = self.headers["other"]
        day_before = datetime(2025, 2, 28, 23, 59, 59, tzinfo=IST)
        with (
            patch("app.routes.announcements.now_ist", return_value=day_before),
            patch("app.utils.official_announcements.now_ist", return_value=day_before),
        ):
            day_before_feed = self.client.get("/api/announcements", headers=headers).get_json()
        self.assertFalse(any(item["kind"] == "birthday" for item in day_before_feed))

        with (
            patch("app.routes.announcements.now_ist", return_value=datetime(2025, 3, 1, 12, 0, tzinfo=IST)),
            patch("app.utils.official_announcements.now_ist", return_value=datetime(2025, 3, 1, 12, 0, tzinfo=IST)),
        ):
            response = self.client.get("/api/announcements", headers=headers)
        birthdays = [item for item in response.get_json() if item["kind"] == "birthday"]
        self.assertEqual(len(birthdays), 1)
        birthday = birthdays[0]
        self.assertEqual(
            [(person["name"], person["designation"]) for person in birthday["employees"]],
            [("Employee Recipient", "Designer"), ("Rahul Das", "Team Lead")],
        )
        self.assertEqual(birthday["employees"][0]["avatar_url"], "/static/uploads/employee.png")
        self.assertEqual(birthday["publish_at"], "2025-02-28T18:30:00Z")
        self.assertEqual(birthday["expires_at"], "2025-03-01T18:30:00Z")
        serialized = json.dumps(birthday)
        self.assertNotIn("date_of_birth", serialized)
        self.assertNotIn("1990-03-01", serialized)
        self.assertNotIn("1988-02-29", serialized)
        self.assertEqual(
            set(birthday["employees"][0]),
            {"id", "name", "designation", "avatar_url"},
        )
        self.assertEqual(Announcement.query.count(), 0)

        db.session.add(Announcement(
            title="Birthday-day official update",
            body="An expiring announcement.",
            category="general",
            priority="normal",
            audiences={"everyone": True, "user_ids": [], "department_ids": [], "roles": []},
            publish_at=utc_naive(datetime(2025, 3, 1, 9, 0, tzinfo=IST)),
            expires_at=utc_naive(datetime(2025, 3, 2, 0, 0, tzinfo=IST)),
            created_at=utc_naive(datetime(2025, 3, 1, 9, 0, tzinfo=IST)),
            posted_by=self.hr.id,
        ))
        db.session.commit()

        for boundary in (
            datetime(2025, 3, 1, 0, 0, tzinfo=IST),
            datetime(2025, 3, 1, 23, 59, 59, tzinfo=IST),
        ):
            with (
                patch("app.routes.announcements.now_ist", return_value=boundary),
                patch("app.utils.official_announcements.now_ist", return_value=boundary),
            ):
                dashboard = self.client.get("/api/dashboard/summary", headers=headers).get_json()
            self.assertTrue(any(
                item["kind"] == "birthday"
                for item in dashboard["recent_announcements"]
            ))
            self.assertEqual(dashboard["recent_announcements"][0]["kind"], "birthday")

        with (
            patch("app.routes.announcements.now_ist", return_value=datetime(2025, 3, 2, 0, 0, tzinfo=IST)),
            patch("app.utils.official_announcements.now_ist", return_value=datetime(2025, 3, 2, 0, 0, tzinfo=IST)),
        ):
            next_day = self.client.get("/api/announcements", headers=headers).get_json()
            dashboard_next_day = self.client.get("/api/dashboard/summary", headers=headers).get_json()
        self.assertFalse(any(item["kind"] == "birthday" for item in next_day))
        self.assertFalse(any(
            item["kind"] == "birthday"
            for item in dashboard_next_day["recent_announcements"]
        ))


if __name__ == "__main__":
    unittest.main()
