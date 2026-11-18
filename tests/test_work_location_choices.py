import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, ".")

from config import Config
from app import create_app
from app.extensions import db
from app.models import Attendance, Department, OfficeLocation, User, WorkLocation
from app.roles import EMPLOYEE, MANAGER


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    SELFIE_FOLDER = tempfile.mkdtemp(prefix="work_locations_")


class WorkLocationChoiceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        department = Department(name="Engineering")
        db.session.add(department)
        db.session.flush()
        manager = User(
            employee_code="M1", full_name="Manager", email="manager@example.test",
            role=MANAGER, department_id=department.id, date_of_joining=date(2024, 1, 1),
        )
        manager.set_password("password")
        db.session.add(manager)
        db.session.flush()
        employee = User(
            employee_code="E1", full_name="Employee", email="employee@example.test",
            role=EMPLOYEE, manager_id=manager.id, department_id=department.id,
            date_of_joining=date(2024, 1, 1),
        )
        employee.set_password("password")
        db.session.add(employee)
        db.session.add(OfficeLocation(name="Main Office", latitude=12.97, longitude=77.59, radius_meters=200))
        db.session.commit()

        self.manager_id = manager.id
        self.employee_id = employee.id
        self.client = self.app.test_client()
        self.manager_headers = self._login("manager@example.test")
        self.employee_headers = self._login("employee@example.test")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _login(self, email):
        response = self.client.post("/api/auth/login", json={"email": email, "password": "password"})
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    def test_manager_can_manage_choices_and_default_office_is_seeded(self):
        response = self.client.get("/api/attendance/work-locations", headers=self.employee_headers)
        self.assertEqual(response.status_code, 200)
        locations = response.get_json()
        office = next(location for location in locations if location["name"] == "Main Office")
        home = next(location for location in locations if location["name"] == "Work From Home")
        self.assertTrue(office["is_default"])
        self.assertFalse(home["is_default"])

        denied = self.client.post(
            "/api/attendance/work-locations",
            headers=self.employee_headers,
            json={"name": "Secondary Office"},
        )
        self.assertEqual(denied.status_code, 403)

        added = self.client.post(
            "/api/attendance/work-locations",
            headers=self.manager_headers,
            json={"name": "Secondary Office"},
        )
        self.assertEqual(added.status_code, 201)
        location_id = added.get_json()["id"]
        made_default = self.client.put(
            f"/api/attendance/work-locations/{location_id}",
            headers=self.manager_headers,
            json={"is_default": True, "name": "Satellite Office"},
        )
        self.assertEqual(made_default.status_code, 200)
        self.assertTrue(made_default.get_json()["is_default"])
        self.assertEqual(
            self.client.put(
                f"/api/attendance/work-locations/{location_id}",
                headers=self.manager_headers,
                json={"is_active": False},
            ).status_code,
            400,
        )
        retired_home = self.client.put(
            f"/api/attendance/work-locations/{home['id']}",
            headers=self.manager_headers,
            json={"is_active": False},
        )
        self.assertEqual(retired_home.status_code, 200)
        active_after_retire = self.client.get(
            "/api/attendance/work-locations", headers=self.employee_headers
        ).get_json()
        self.assertNotIn(home["id"], [location["id"] for location in active_after_retire])

    def test_clock_in_persists_selected_location_and_manager_can_view_it(self):
        options = self.client.get("/api/attendance/work-locations", headers=self.employee_headers).get_json()
        home = next(location for location in options if location["name"] == "Work From Home")
        response = self.client.post(
            "/api/attendance/clock-in",
            headers=self.employee_headers,
            json={"work_location_id": home["id"]},
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        session = response.get_json()["sessions"][0]
        self.assertEqual(session["work_location_id"], home["id"])
        self.assertEqual(session["work_location_name"], "Work From Home")

        overview = self.client.get("/api/attendance/team/overview", headers=self.manager_headers)
        self.assertEqual(overview.status_code, 200, overview.get_json())
        person = next(row for row in overview.get_json()["people"] if row["user"]["id"] == self.employee_id)
        self.assertEqual(person["record"]["sessions"][0]["work_location_name"], "Work From Home")

        renamed = self.client.put(
            f"/api/attendance/work-locations/{home['id']}",
            headers=self.manager_headers,
            json={"name": "Remote Work"},
        )
        self.assertEqual(renamed.status_code, 200)
        today = self.client.get("/api/attendance/today", headers=self.employee_headers).get_json()
        self.assertEqual(today["record"]["sessions"][0]["work_location_name"], "Work From Home")

        inactive = self.client.post(
            "/api/attendance/work-locations",
            headers=self.manager_headers,
            json={"name": "Temporary Office"},
        ).get_json()
        self.client.put(
            f"/api/attendance/work-locations/{inactive['id']}",
            headers=self.manager_headers,
            json={"is_active": False},
        )
        invalid_punch = self.client.post(
            "/api/attendance/clock-in",
            headers=self.manager_headers,
            json={"work_location_id": inactive["id"]},
        )
        self.assertEqual(invalid_punch.status_code, 400)


if __name__ == "__main__":
    unittest.main()
