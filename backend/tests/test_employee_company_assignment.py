import sys
import unittest

sys.path.insert(0, ".")

from config import Config
from app import create_app
from app.extensions import db
from app.models import User, Payslip
from app.roles import EMPLOYEE, FINANCE_ACCOUNTS, MANAGER
from app.utils.companies import PAYROLL_COMPANIES


class EmployeeCompanyTestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


class EmployeeCompanyAssignmentTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(EmployeeCompanyTestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.manager = self.add_user("MGR", "manager@test.com", MANAGER)
        self.employee = self.add_user("EMP", "employee@test.com", EMPLOYEE, self.manager.id)
        self.other_employee = self.add_user("EMP2", "other@test.com", EMPLOYEE)
        self.finance = self.add_user("FIN", "finance@test.com", FINANCE_ACCOUNTS)
        db.session.commit()
        self.client = self.app.test_client()
        self.headers = {
            "manager": self.login("manager@test.com"),
            "finance": self.login("finance@test.com"),
        }

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    @staticmethod
    def add_user(code, email, role, manager_id=None):
        user = User(
            employee_code=code,
            full_name=code,
            email=email,
            role=role,
            manager_id=manager_id,
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
        return {"Authorization": "Bearer " + response.get_json()["access_token"]}

    def test_manager_can_assign_and_change_direct_report_company(self):
        for company in PAYROLL_COMPANIES[:2]:
            response = self.client.put(
                f"/api/employees/{self.employee.id}",
                headers=self.headers["manager"],
                json={"company_name": company},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["company_name"], company)

            refreshed = self.client.get(
                f"/api/employees/{self.employee.id}",
                headers=self.headers["manager"],
            )
            self.assertEqual(refreshed.get_json()["company_name"], company)

        self.assertEqual(self.employee.company_name, PAYROLL_COMPANIES[1])

    def test_manager_cannot_assign_outside_their_team_or_use_unknown_company(self):
        outside_team = self.client.put(
            f"/api/employees/{self.other_employee.id}",
            headers=self.headers["manager"],
            json={"company_name": PAYROLL_COMPANIES[0]},
        )
        self.assertEqual(outside_team.status_code, 403)

        invalid_company = self.client.put(
            f"/api/employees/{self.employee.id}",
            headers=self.headers["manager"],
            json={"company_name": "Unknown Company"},
        )
        self.assertEqual(invalid_company.status_code, 400)
        self.assertEqual(self.employee.company_name, PAYROLL_COMPANIES[1])

    def test_company_directory_filter_and_payroll_employee_filter(self):
        self.employee.company_name = PAYROLL_COMPANIES[0]
        self.other_employee.company_name = PAYROLL_COMPANIES[1]
        db.session.commit()

        directory = self.client.get(
            "/api/employees",
            headers=self.headers["manager"],
            query_string={"company_name": PAYROLL_COMPANIES[0]},
        )
        self.assertEqual(directory.status_code, 200)
        self.assertEqual([row["id"] for row in directory.get_json()], [self.employee.id])
        self.assertEqual(directory.get_json()[0]["company_name"], PAYROLL_COMPANIES[0])

        payroll_people = self.client.get(
            "/api/payroll/people",
            headers=self.headers["finance"],
            query_string={"company_name": PAYROLL_COMPANIES[0], "q": "EMP"},
        )
        self.assertEqual(payroll_people.status_code, 200)
        self.assertEqual([row["id"] for row in payroll_people.get_json()], [self.employee.id])
        self.assertEqual(payroll_people.get_json()[0]["company_name"], PAYROLL_COMPANIES[0])

    def test_company_change_does_not_rewrite_existing_payslip_company(self):
        historical = Payslip(
            user_id=self.employee.id,
            month=1,
            year=2026,
            company_name=PAYROLL_COMPANIES[1],
            status="published",
        )
        db.session.add(historical)
        db.session.commit()

        response = self.client.put(
            f"/api/employees/{self.employee.id}",
            headers=self.headers["manager"],
            json={"company_name": PAYROLL_COMPANIES[0]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(historical.company_name, PAYROLL_COMPANIES[1])
        self.assertEqual(self.employee.company_name, PAYROLL_COMPANIES[0])


if __name__ == "__main__":
    unittest.main()
