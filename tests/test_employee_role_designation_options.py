import sys
import unittest

sys.path.insert(0, ".")

from config import Config
from app import create_app
from app.extensions import db
from app.models import User
from app.roles import (
    ADMIN,
    BUSINESS_ANALYST,
    DEVELOPER,
    EMPLOYEE,
    HR,
    HR_EXECUTIVE,
    HR_OPERATIONS,
    ROLE_LABELS,
    SCRUM_MASTER,
    TEAM_LEAD,
    TESTER_QA,
)


class EmployeeRoleOptionsTestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


class EmployeeRoleDesignationOptionsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(EmployeeRoleOptionsTestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        hr = User(
            employee_code="HR-1",
            full_name="HR Operations",
            email="hr@test.local",
            role=HR_OPERATIONS,
        )
        hr.set_password("test-password")
        db.session.add(hr)
        db.session.commit()
        self.client = self.app.test_client()
        response = self.client.post(
            "/api/auth/login",
            json={"email": hr.email, "password": "test-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.hr_headers = {
            "Authorization": f"Bearer {response.get_json()['access_token']}"
        }

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    @staticmethod
    def employee_payload(employee_code, role, designation):
        return {
            "employee_code": employee_code,
            "full_name": f"Employee {employee_code}",
            "email": f"{employee_code.lower()}@test.local",
            "password": "test-password",
            "role": role,
            "designation": designation,
        }

    def test_new_roles_save_and_update_without_restricting_designations(self):
        new_roles = (
            ADMIN,
            TEAM_LEAD,
            DEVELOPER,
            TESTER_QA,
            SCRUM_MASTER,
            BUSINESS_ANALYST,
            HR,
            HR_EXECUTIVE,
        )
        for index, role in enumerate(new_roles):
            with self.subTest(role=role):
                original_designation = f"Custom title {index}"
                response = self.client.post(
                    "/api/employees",
                    headers=self.hr_headers,
                    json=self.employee_payload(
                        f"NEW-{index}", role, original_designation
                    ),
                )
                self.assertEqual(response.status_code, 201)
                employee_id = response.get_json()["id"]
                employee = db.session.get(User, employee_id)
                self.assertEqual(employee.role, role)
                self.assertEqual(employee.designation, original_designation)
                self.assertTrue(ROLE_LABELS[role])

                login = self.client.post(
                    "/api/auth/login",
                    json={
                        "email": f"new-{index}@test.local",
                        "password": "test-password",
                    },
                )
                self.assertEqual(login.status_code, 200)
                self.assertFalse(login.get_json()["has_clock_in_out"])

                new_designation = f"Updated custom title {index}"
                update = self.client.put(
                    f"/api/employees/{employee_id}",
                    headers=self.hr_headers,
                    json={"role": role, "designation": new_designation},
                )
                self.assertEqual(update.status_code, 200)
                self.assertEqual(update.get_json()["role"], role)
                self.assertEqual(update.get_json()["designation"], new_designation)

    def test_invalid_roles_are_rejected_on_create_and_update(self):
        response = self.client.post(
            "/api/employees",
            headers=self.hr_headers,
            json=self.employee_payload("VALID", EMPLOYEE, "HR Generalist"),
        )
        self.assertEqual(response.status_code, 201)
        employee_id = response.get_json()["id"]

        invalid_create = self.client.post(
            "/api/employees",
            headers=self.hr_headers,
            json=self.employee_payload("INVALID", "not_a_role", "HR Intern"),
        )
        self.assertEqual(invalid_create.status_code, 400)

        invalid_update = self.client.put(
            f"/api/employees/{employee_id}",
            headers=self.hr_headers,
            json={"role": "not_a_role"},
        )
        self.assertEqual(invalid_update.status_code, 400)
        self.assertEqual(db.session.get(User, employee_id).role, EMPLOYEE)

    def test_admin_label_does_not_grant_employee_management_access(self):
        response = self.client.post(
            "/api/employees",
            headers=self.hr_headers,
            json=self.employee_payload("NEW-ADMIN", ADMIN, "HR Manager"),
        )
        self.assertEqual(response.status_code, 201)
        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "new-admin@test.local",
                "password": "test-password",
            },
        )
        self.assertEqual(login.status_code, 200)
        auth_data = login.get_json()
        self.assertEqual(auth_data["role_label"], "Admin")
        self.assertFalse(auth_data["has_clock_in_out"])

        response = self.client.post(
            "/api/employees",
            headers={
                "Authorization": f"Bearer {auth_data['access_token']}"
            },
            json=self.employee_payload("CREATED-BY-ADMIN", EMPLOYEE, "Developer"),
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
