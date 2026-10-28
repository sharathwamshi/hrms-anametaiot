import sys
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

sys.path.insert(0, ".")

from sqlalchemy.exc import SQLAlchemyError

from config import Config
from app import create_app
from app.extensions import db
from app.models import Department, SalaryStructure, User
from app.roles import (
    EMPLOYEE,
    FINANCE_ACCOUNTS,
    HR_OPERATIONS,
    MANAGER,
    SUPER_ADMIN,
)


class EmployeeCtcTestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


class EmployeeCtcTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(EmployeeCtcTestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        department = Department(name="Engineering")
        db.session.add(department)
        db.session.flush()
        self.hr = self.add_user("HR", "hr@test.com", HR_OPERATIONS, department.id)
        self.super_admin = self.add_user("SA", "super@test.com", SUPER_ADMIN, department.id)
        self.manager = self.add_user("MGR", "manager@test.com", MANAGER, department.id)
        self.finance = self.add_user("FIN", "finance@test.com", FINANCE_ACCOUNTS, department.id)
        self.employee = self.add_user(
            "EMP", "employee@test.com", EMPLOYEE, department.id, manager_id=self.manager.id
        )
        db.session.commit()

        self.client = self.app.test_client()
        self.headers = {
            role: self.login(email)
            for role, email in (
                ("hr", "hr@test.com"),
                ("super_admin", "super@test.com"),
                ("manager", "manager@test.com"),
                ("finance", "finance@test.com"),
                ("employee", "employee@test.com"),
            )
        }

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    @staticmethod
    def add_user(code, email, role, department_id, manager_id=None):
        user = User(
            employee_code=code,
            full_name=code,
            email=email,
            role=role,
            department_id=department_id,
            manager_id=manager_id,
            date_of_joining=date(2024, 1, 1),
        )
        user.set_password("password")
        db.session.add(user)
        db.session.flush()
        return user

    def login(self, email):
        response = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": "password"},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    @staticmethod
    def employee_payload(**overrides):
        payload = {
            "employee_code": "NEW1",
            "full_name": "New Employee",
            "email": "new@test.com",
            "password": "password",
            "role": EMPLOYEE,
        }
        payload.update(overrides)
        return payload

    def create_employee(self, role="hr", **overrides):
        return self.client.post(
            "/api/employees",
            headers=self.headers[role],
            json=self.employee_payload(**overrides),
        )

    def test_create_and_retrieve_ctc_for_authorized_admins(self):
        for role, code, email in (
            ("hr", "NEW1", "new@test.com"),
            ("super_admin", "NEW2", "new2@test.com"),
        ):
            with self.subTest(role=role):
                response = self.create_employee(
                    role,
                    employee_code=code,
                    email=email,
                    annual_ctc=600000,
                )
                self.assertEqual(response.status_code, 201)
                employee_id = response.get_json()["id"]
                self.assertNotIn("annual_ctc", response.get_json())
                structure = SalaryStructure.query.filter_by(user_id=employee_id).one()
                self.assertEqual(structure.annual_ctc, Decimal("600000.00"))

                for accessor in ("hr", "super_admin"):
                    result = self.client.get(
                        f"/api/employees/{employee_id}/compensation",
                        headers=self.headers[accessor],
                    )
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.get_json()["annual_ctc"], "600000.00")

                self.assertNotIn(
                    "annual_ctc",
                    self.client.get(
                        f"/api/employees/{employee_id}",
                        headers=self.headers["hr"],
                    ).get_json(),
                )

    def test_creation_without_ctc_and_zero_ctc_are_supported(self):
        omitted = self.create_employee()
        self.assertEqual(omitted.status_code, 201)
        self.assertIsNone(
            SalaryStructure.query.filter_by(user_id=omitted.get_json()["id"]).first()
        )

        empty = self.create_employee(
            employee_code="NEW2",
            email="new2@test.com",
            annual_ctc="",
        )
        self.assertEqual(empty.status_code, 201)
        self.assertIsNone(
            SalaryStructure.query.filter_by(user_id=empty.get_json()["id"]).first()
        )

        zero = self.create_employee(
            employee_code="NEW3",
            email="new3@test.com",
            annual_ctc=0,
        )
        self.assertEqual(zero.status_code, 201)
        structure = SalaryStructure.query.filter_by(user_id=zero.get_json()["id"]).one()
        self.assertEqual(structure.annual_ctc, Decimal("0.00"))

    def test_update_and_clear_ctc_using_employee_update_flow(self):
        create = self.create_employee(annual_ctc=600000)
        employee_id = create.get_json()["id"]

        update = self.client.put(
            f"/api/employees/{employee_id}",
            headers=self.headers["hr"],
            json={"full_name": "Updated Name", "annual_ctc": 720000},
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.get_json()["full_name"], "Updated Name")
        self.assertNotIn("annual_ctc", update.get_json())
        self.assertEqual(
            SalaryStructure.query.filter_by(user_id=employee_id).one().annual_ctc,
            Decimal("720000.00"),
        )

        super_admin_update = self.client.put(
            f"/api/employees/{employee_id}",
            headers=self.headers["super_admin"],
            json={"annual_ctc": 750000},
        )
        self.assertEqual(super_admin_update.status_code, 200)
        self.assertEqual(
            SalaryStructure.query.filter_by(user_id=employee_id).one().annual_ctc,
            Decimal("750000.00"),
        )

        clear = self.client.put(
            f"/api/employees/{employee_id}",
            headers=self.headers["hr"],
            json={"annual_ctc": None},
        )
        self.assertEqual(clear.status_code, 200)
        self.assertIsNone(
            SalaryStructure.query.filter_by(user_id=employee_id).one().annual_ctc
        )
        self.assertIsNone(
            self.client.get(
                f"/api/employees/{employee_id}/compensation",
                headers=self.headers["hr"],
            ).get_json()["annual_ctc"]
        )

    def test_invalid_and_negative_ctc_are_rejected_on_create_and_update(self):
        invalid_values = [-1, "invalid", "NaN", "Infinity", "-Infinity", True]
        for index, value in enumerate(invalid_values):
            with self.subTest(value=value):
                response = self.create_employee(
                    employee_code=f"BAD{index}",
                    email=f"bad{index}@test.com",
                    annual_ctc=value,
                )
                self.assertEqual(response.status_code, 400)
                self.assertIsNone(User.query.filter_by(employee_code=f"BAD{index}").first())

                response = self.client.put(
                    f"/api/employees/{self.employee.id}",
                    headers=self.headers["hr"],
                    json={"annual_ctc": value},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIsNone(
                    SalaryStructure.query.filter_by(user_id=self.employee.id).first()
                )

        rounded = self.create_employee(
            employee_code="ROUND",
            email="round@test.com",
            annual_ctc="100.125",
        )
        self.assertEqual(rounded.status_code, 201)
        self.assertEqual(
            SalaryStructure.query.filter_by(user_id=rounded.get_json()["id"]).one().annual_ctc,
            Decimal("100.13"),
        )

    def test_unauthorized_roles_cannot_read_or_change_ctc(self):
        for role in ("manager", "finance", "employee"):
            with self.subTest(role=role):
                read = self.client.get(
                    f"/api/employees/{self.employee.id}/compensation",
                    headers=self.headers[role],
                )
                update = self.client.put(
                    f"/api/employees/{self.employee.id}",
                    headers=self.headers[role],
                    json={"annual_ctc": 700000},
                )
                create = self.create_employee(
                    role,
                    employee_code=f"DENY{role}",
                    email=f"deny-{role}@test.com",
                    annual_ctc=700000,
                )
                self.assertEqual(read.status_code, 403)
                self.assertEqual(update.status_code, 403)
                self.assertEqual(create.status_code, 403)

        self.assertIsNone(
            SalaryStructure.query.filter_by(user_id=self.employee.id).first()
        )

    def test_general_employee_responses_never_expose_ctc(self):
        created = self.create_employee(annual_ctc=600000)
        employee_id = created.get_json()["id"]

        detail = self.client.get(
            f"/api/employees/{employee_id}",
            headers=self.headers["manager"],
        )
        rows = self.client.get("/api/employees", headers=self.headers["manager"])
        self.assertNotIn("annual_ctc", detail.get_json())
        self.assertTrue(all("annual_ctc" not in row for row in rows.get_json()))

    def test_ctc_only_structure_does_not_count_as_payroll_structure(self):
        created = self.create_employee(annual_ctc=600000)
        employee_id = created.get_json()["id"]

        coverage = self.client.get(
            "/api/payroll/coverage",
            headers=self.headers["finance"],
        ).get_json()
        row = next(person for person in coverage["people"] if person["id"] == employee_id)
        self.assertFalse(row["has_structure"])
        self.assertEqual(row["payroll_state"], "missing")

        payroll = self.client.post(
            "/api/payroll/generate",
            headers=self.headers["finance"],
            json={"month": 10, "year": 2026},
        )
        self.assertEqual(payroll.status_code, 200)
        self.assertNotIn(employee_id, {item["user_id"] for item in payroll.get_json()})

    def test_failed_ctc_persistence_rolls_back_employee_creation(self):
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("simulated failure")):
            response = self.create_employee(annual_ctc=600000)

        self.assertEqual(response.status_code, 500)
        self.assertIsNone(User.query.filter_by(employee_code="NEW1").first())
        self.assertIsNone(
            SalaryStructure.query.join(User).filter(User.employee_code == "NEW1").first()
        )


if __name__ == "__main__":
    unittest.main()
