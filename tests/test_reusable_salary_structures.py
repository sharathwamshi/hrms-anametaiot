import sys
import os
import tempfile
from datetime import date
from unittest.mock import patch

sys.path.insert(0, ".")

from config import Config
import pdfplumber

_payslip_tmp = tempfile.TemporaryDirectory(prefix="hrms-reusable-payslips-")


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    PAYSLIP_FOLDER = _payslip_tmp.name


from app import create_app
from app.extensions import db
from app.models import Attendance, Payslip, SalaryStructure, SalaryTemplate, User
from app.roles import EMPLOYEE, FINANCE_ACCOUNTS, OPERATIONS


app = create_app(TestConfig)


def create_user(code, name, role):
    user = User(
        employee_code=code,
        full_name=name,
        email=f"{code.lower()}@test.com",
        role=role,
        company_name="Ana Meta IoT",
    )
    user.set_password("test-password")
    db.session.add(user)
    db.session.flush()
    return user


with app.app_context():
    db.create_all()
    finance = create_user("FIN1", "Finance User", FINANCE_ACCOUNTS)
    operations = create_user("OPS1", "Operations User", OPERATIONS)
    employee = create_user("EMP1", "Employee One", EMPLOYEE)
    second_employee = create_user("EMP2", "Employee Two", EMPLOYEE)
    employee.employee_category = "full_time"
    second_employee.employee_category = "full_time"
    db.session.add_all([
        SalaryStructure(user_id=employee.id, annual_ctc=1_200_000),
        SalaryStructure(user_id=second_employee.id, annual_ctc=1_200_000),
    ])
    db.session.add_all([
        Attendance(user_id=user.id, work_date=date(2026, 1, day), status="present")
        for user in (employee, second_employee)
        for day in range(1, 31)
    ])
    db.session.add_all([
        Attendance(user_id=user.id, work_date=date(2026, 3, day), status="present")
        for user in (employee, second_employee)
        for day in range(1, 32)
    ])
    db.session.add_all([
        Attendance(user_id=user.id, work_date=date(2026, 6, day), status="present")
        for user in (employee, second_employee)
        for day in range(1, 31)
    ])
    db.session.add_all([
        Attendance(user_id=user.id, work_date=date(2026, 7, day), status="present")
        for user in (employee, second_employee)
        for day in range(1, 32)
    ])
    db.session.add_all([
        Attendance(user_id=employee.id, work_date=date(2026, 2, day), status="present")
        for day in range(1, 29)
    ])
    db.session.add_all([
        Attendance(user_id=second_employee.id, work_date=date(2026, 2, day), status="present")
        for day in range(1, 29)
    ])
    db.session.commit()

    client = app.test_client()
    login_response = client.post(
        "/api/auth/login",
        json={"email": finance.email, "password": "test-password"},
    )
    assert login_response.status_code == 200
    finance_headers = {"Authorization": f"Bearer {login_response.get_json()['access_token']}"}

    operations_login = client.post(
        "/api/auth/login",
        json={"email": operations.email, "password": "test-password"},
    )
    operations_headers = {"Authorization": f"Bearer {operations_login.get_json()['access_token']}"}

    employee_login = client.post(
        "/api/auth/login",
        json={"email": employee.email, "password": "test-password"},
    )
    employee_headers = {"Authorization": f"Bearer {employee_login.get_json()['access_token']}"}

    profile_update = client.put(
        f"/api/payroll/people/{employee.id}/payroll-profile",
        headers=finance_headers,
        json={
            "employee_category": "full_time",
            "bank_account_name": "Employee One",
        },
    )
    assert profile_update.status_code == 200, profile_update.get_json()
    assert profile_update.get_json()["employee_info"]["bank_account_name"] == "Employee One"

    structure_payload = {
        "name": "Ana Standard",
        "description": "Reusable company salary structure",
        "company_name": "Ana Meta IoT",
        "basic_pct": 50,
        "hra_pct": 20,
        "special_allowance_pct": 20,
        "other_allowance_pct": 10,
        "transport_flat": 1200,
        "employee_pf_rate_pct": 12,
        "employer_pf_rate_pct": 12,
        "employer_pf_flat": 6000,
        "professional_tax_flat": 200,
        "tds_flat": 100,
        "insurance_months": [1],
        "insurance_amounts": {"1": 1000},
        "earnings_confirmed": True,
        "deductions_confirmed": True,
    }
    unsaved_preview = client.post(
        "/api/payroll/templates/preview",
        headers=finance_headers,
        json={**structure_payload, "user_id": employee.id, "month": 1, "year": 2026},
    )
    assert unsaved_preview.status_code == 200, unsaved_preview.get_json()
    basic_preview = next(
        row for row in unsaved_preview.get_json()["components"]
        if row["category"] == "earnings" and row["name"] == "Basic Salary"
    )
    assert basic_preview["projected"] == 50_000
    assert unsaved_preview.get_json()["employee_info"]["annual_ctc"] == 1_200_000
    absent_preview = client.post(
        "/api/payroll/templates/preview",
        headers=finance_headers,
        json={**structure_payload, "user_id": employee.id, "month": 4, "year": 2026},
    )
    assert absent_preview.status_code == 200, absent_preview.get_json()
    absent_components = absent_preview.get_json()["components"]
    absent_gross = sum(
        row["projected"] for row in absent_components if row["category"] == "earnings"
    )
    absent_deductions = sum(
        row["projected"] for row in absent_components if row["category"] == "deductions"
    )
    assert absent_deductions > absent_gross

    created = client.post("/api/payroll/templates", headers=finance_headers, json=structure_payload)
    assert created.status_code == 201, created.get_json()
    salary_template = created.get_json()

    assigned = client.post(
        f"/api/payroll/templates/{salary_template['id']}/assign",
        headers=finance_headers,
        json={"employee_ids": [employee.id, second_employee.id]},
    )
    assert assigned.status_code == 200, assigned.get_json()
    assert SalaryStructure.query.filter_by(user_id=employee.id).count() == 1

    invalid_payroll_preview = client.post(
        "/api/payroll/preview-bulk",
        headers=finance_headers,
        json={
            "salary_template_id": salary_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 4,
            "year": 2026,
            "user_ids": [employee.id],
        },
    )
    assert invalid_payroll_preview.status_code == 400
    assert "deductions exceed gross earnings" in invalid_payroll_preview.get_json()["message"]

    override = client.put(
        f"/api/payroll/templates/{salary_template['id']}/employees/{second_employee.id}",
        headers=finance_headers,
        json={"transport_flat": 2500, "insurance_amounts": {"1": 1250}},
    )
    assert override.status_code == 200

    preview = client.post(
        "/api/payroll/preview-bulk",
        headers=finance_headers,
        json={
            "salary_template_id": salary_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 1,
            "year": 2026,
            "user_ids": [employee.id, second_employee.id],
        },
    )
    assert preview.status_code == 200, preview.get_json()
    by_id = {row["user_id"]: row for row in preview.get_json()["previews"]}
    first = by_id[employee.id]
    second = by_id[second_employee.id]
    assert first["gross_earnings"] == 101_200
    assert first["total_deductions"] == 16_564.52
    assert first["net_pay"] == 84_635.48
    assert second["gross_earnings"] == 102_500
    first_deductions = {row["name"]: row["amount"] for row in first["deductions"]}
    assert first_deductions["Insurance"] == 1000
    assert first_deductions["Employee PF"] == 6000
    assert first_deductions["Employer PF"] == 6000
    assert first_deductions["Absent"] == 3264.52
    second_deductions = {row["name"]: row["amount"] for row in second["deductions"]}
    assert second_deductions["Insurance"] == 1250

    march_preview = client.post(
        "/api/payroll/preview-bulk",
        headers=finance_headers,
        json={
            "salary_template_id": salary_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 3,
            "year": 2026,
            "user_ids": [employee.id],
        },
    )
    assert march_preview.status_code == 200
    march_deductions = {
        row["name"]: row["amount"]
        for row in march_preview.get_json()["previews"][0]["deductions"]
    }
    assert march_deductions["Insurance"] == 0
    assert march_deductions["Absent"] == 0
    unassigned_for_bulk_apply = client.delete(
        f"/api/payroll/templates/{salary_template['id']}/employees/{second_employee.id}",
        headers=finance_headers,
    )
    assert unassigned_for_bulk_apply.status_code == 200
    bulk_assignment = client.post(
        f"/api/payroll/templates/{salary_template['id']}/assign",
        headers=finance_headers,
        json={"employee_ids": [employee.id, second_employee.id]},
    )
    assert bulk_assignment.status_code == 200, bulk_assignment.get_json()
    bulk_generated = client.post(
        "/api/payroll/generate-selected",
        headers=finance_headers,
        json={
            "salary_template_id": salary_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 3,
            "year": 2026,
            "user_ids": [employee.id, second_employee.id],
        },
    )
    assert bulk_generated.status_code == 201, bulk_generated.get_json()
    assert {row["user_id"] for row in bulk_generated.get_json()} == {
        employee.id, second_employee.id,
    }
    assert all(row["status"] == "draft" for row in bulk_generated.get_json())

    generated = client.post(
        "/api/payroll/generate-selected",
        headers=finance_headers,
        json={
            "salary_template_id": salary_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 1,
            "year": 2026,
            "user_ids": [employee.id],
            "adjustments": [{
                "user_id": employee.id,
                "earnings": first["earnings"] + [{
                    "name": "Arrears - Prior period (December 2025)",
                    "amount": 750,
                }],
                "deductions": first["deductions"],
            }],
        },
    )
    assert generated.status_code == 201, generated.get_json()
    payslip = Payslip.query.filter_by(user_id=employee.id, month=1, year=2026).one()
    assert payslip.employee_info["salary_structure_name"] == "Ana Standard"
    assert payslip.employee_info["employee_category"] == "full_time"
    assert payslip.template_snapshot["layout_key"] == "ana_meta_iot"
    assert payslip.gross_earnings == 101_950
    assert any("Arrears - Prior period" in row["name"] for row in payslip.earnings)
    assert SalaryStructure.query.filter_by(user_id=employee.id).one().salary_template_id == salary_template["id"]
    with pdfplumber.open(os.path.join(TestConfig.PAYSLIP_FOLDER, payslip.pdf_path)) as document:
        pdf_text = document.pages[0].extract_text()
    for component in (
        "Basic Salary", "ERA", "Special Allowance", "Other Allowance", "Transport",
        "Employee PF", "Insurance", "Professional Tax", "TDS", "Employer PF", "Absent",
        "Arrears - Prior period", "YTD", "MTD", "Amount in Words",
    ):
        assert component in pdf_text
    assert "Rupees and Forty Eight Paise Only" in pdf_text

    actual_preview = client.get(
        f"/api/payroll/templates/{salary_template['id']}/employees/{employee.id}/preview",
        headers=finance_headers,
        query_string={"month": 1, "year": 2026},
    )
    assert actual_preview.status_code == 200
    assert actual_preview.get_json()["has_current_month_payslip"] is True
    assert any(
        row["name"] == "Basic Salary" and row["mtd"] == 50_000 and row["ytd"] == 50_000
        for row in actual_preview.get_json()["components"]
    )
    assert client.put(
        f"/api/payroll/templates/{salary_template['id']}/employees/{employee.id}",
        headers=employee_headers,
        json={"transport_flat": 1},
    ).status_code == 403
    assert client.patch(
        f"/api/payroll/people/{employee.id}/ctc",
        headers=employee_headers,
        json={"annual_ctc": 1_500_000},
    ).status_code == 403

    personal_structure_payload = {
        **structure_payload,
        "basic_pct": 45,
        "employee_pf_rate_pct": 10,
        "insurance_months": [2],
        "insurance_amounts": {"2": 1500},
    }
    personal_structure_payload.pop("name")
    personal_structure = client.put(
        f"/api/payroll/people/{employee.id}/salary-structure",
        headers=finance_headers,
        json=personal_structure_payload,
    )
    assert personal_structure.status_code == 200, personal_structure.get_json()
    personal_template_id = personal_structure.get_json()["salary_template"]["id"]
    saved_people = client.get("/api/payroll/people", headers=finance_headers)
    assert saved_people.status_code == 200
    saved_employee = next(row for row in saved_people.get_json() if row["id"] == employee.id)
    assert saved_employee["salary_structure_name"] == personal_structure.get_json()["salary_template"]["name"]
    assert saved_employee["salary_structure_published_at"] is None
    assert personal_template_id != salary_template["id"]
    assert personal_structure.get_json()["salary_template"]["basic_pct"] == 45
    assert SalaryStructure.query.filter_by(user_id=employee.id).one().salary_template_id == personal_template_id
    assert db.session.get(SalaryTemplate, salary_template["id"]).basic_pct == 50
    assert SalaryStructure.query.filter_by(user_id=second_employee.id).one().salary_template_id == salary_template["id"]
    assert client.post(
        f"/api/payroll/people/{employee.id}/salary-structure/publish",
        headers=employee_headers,
    ).status_code == 403
    with patch("app.routes.payroll.send_push", return_value=True) as send_push:
        published = client.post(
            f"/api/payroll/people/{employee.id}/salary-structure/publish",
            headers=finance_headers,
        )
    assert published.status_code == 200, published.get_json()
    assert published.get_json()["already_published"] is False
    assert published.get_json()["published_at"] is not None
    assert published.get_json()["notification_sent"] is True
    send_push.assert_called_once_with(
        employee.id,
        "Salary structure published",
        "Your salary structure has been published. Contact Finance & Operations if you have questions.",
        data={"type": "salary_structure_published", "employee_id": employee.id},
    )
    saved_people = client.get("/api/payroll/people", headers=finance_headers)
    saved_employee = next(row for row in saved_people.get_json() if row["id"] == employee.id)
    assert saved_employee["salary_structure_published_at"] == published.get_json()["published_at"]
    with patch("app.routes.payroll.send_push") as send_push:
        duplicate_publish = client.post(
            f"/api/payroll/people/{employee.id}/salary-structure/publish",
            headers=operations_headers,
        )
    assert duplicate_publish.status_code == 200
    assert duplicate_publish.get_json()["already_published"] is True
    assert duplicate_publish.get_json()["notification_sent"] is False
    send_push.assert_not_called()
    personal_structure = client.put(
        f"/api/payroll/people/{employee.id}/salary-structure",
        headers=finance_headers,
        json=personal_structure_payload,
    )
    assert personal_structure.status_code == 200
    saved_people = client.get("/api/payroll/people", headers=finance_headers)
    saved_employee = next(row for row in saved_people.get_json() if row["id"] == employee.id)
    assert saved_employee["salary_structure_published_at"] is None
    effective_structure = client.get(
        f"/api/payroll/structure/{employee.id}",
        headers=finance_headers,
        query_string={"month": 2, "year": 2026},
    )
    assert effective_structure.status_code == 200
    assert effective_structure.get_json()["salary_template"]["insurance_amounts"] == {"2": 1500}
    updated_employee_preview = client.post(
        "/api/payroll/preview-bulk",
        headers=finance_headers,
        json={
            "company_name": "Ana Meta IoT",
            "employee_category": "full_time",
            "month": 2,
            "year": 2026,
            "user_ids": [employee.id],
        },
    )
    assert updated_employee_preview.status_code == 200, updated_employee_preview.get_json()
    updated_employee_components = {
        row["name"]: row["amount"]
        for row in updated_employee_preview.get_json()["previews"][0]["earnings"]
    }
    assert updated_employee_components["Basic Salary"] == 45_000
    updated_employee_deductions = {
        row["name"]: row["amount"]
        for row in updated_employee_preview.get_json()["previews"][0]["deductions"]
    }
    assert updated_employee_deductions["Employee PF"] == 4_500
    assert updated_employee_deductions["Insurance"] == 1_500

    missing_confirmation = client.post(
        "/api/payroll/templates",
        headers=finance_headers,
        json={**structure_payload, "name": "Unconfirmed", "deductions_confirmed": False},
    )
    assert missing_confirmation.status_code == 400
    invalid_months = client.post(
        "/api/payroll/templates",
        headers=finance_headers,
        json={**structure_payload, "name": "Invalid Insurance", "insurance_months": [3]},
    )
    assert invalid_months.status_code == 400
    multiple_insurance_months = client.post(
        "/api/payroll/templates",
        headers=finance_headers,
        json={**structure_payload, "name": "Multiple Insurance Months", "insurance_months": [1, 2]},
    )
    assert multiple_insurance_months.status_code == 400
    unconfigured_payload = {**structure_payload, "name": "Unconfigured Rates"}
    for field in (
        "employee_pf_rate_pct", "employer_pf_rate_pct", "employer_pf_flat",
        "professional_tax_flat", "tds_flat",
    ):
        unconfigured_payload.pop(field, None)
    unconfigured_template = client.post(
        "/api/payroll/templates",
        headers=finance_headers,
        json=unconfigured_payload,
    )
    assert unconfigured_template.status_code == 201
    assert unconfigured_template.get_json()["employee_pf_rate_pct"] == 0
    assert unconfigured_template.get_json()["pf_employee_pct"] == 0
    assert unconfigured_template.get_json()["professional_tax_flat"] == 0

    operations_template = client.post(
        "/api/payroll/templates",
        headers=operations_headers,
        json={
            **structure_payload,
            "name": "Operations February Structure",
            "insurance_months": [2],
            "insurance_amounts": {"2": 1750},
        },
    )
    assert operations_template.status_code == 201, operations_template.get_json()
    ctc_update = client.patch(
        f"/api/payroll/people/{second_employee.id}/ctc",
        headers=operations_headers,
        json={"annual_ctc": 1_500_000},
    )
    assert ctc_update.status_code == 200
    assert ctc_update.get_json()["annual_ctc"] == 1_500_000
    assert float(SalaryStructure.query.filter_by(user_id=second_employee.id).one().annual_ctc) == 1_500_000
    ctc_preview = client.post(
        "/api/payroll/preview-bulk",
        headers=finance_headers,
        json={
            "salary_template_id": salary_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 2,
            "year": 2026,
            "user_ids": [second_employee.id],
        },
    )
    assert ctc_preview.status_code == 200, ctc_preview.get_json()
    updated_basic = next(
        row for row in ctc_preview.get_json()["previews"][0]["earnings"]
        if row["name"] == "Basic Salary"
    )
    assert updated_basic["amount"] == 62_500
    assert client.get("/api/payroll/templates", headers=operations_headers).status_code == 200
    assert client.get("/api/payroll/templates", headers=employee_headers).status_code == 403
    unassign = client.delete(
        f"/api/payroll/templates/{salary_template['id']}/employees/{second_employee.id}",
        headers=operations_headers,
    )
    assert unassign.status_code == 200
    second_structure = SalaryStructure.query.filter_by(user_id=second_employee.id).one()
    assert second_structure.salary_template_id is None
    assert float(second_structure.annual_ctc) == 1_500_000
    operations_structure_payload = {**structure_payload}
    operations_structure_payload.pop("name")
    operations_save = client.put(
        f"/api/payroll/people/{second_employee.id}/salary-structure",
        headers=operations_headers,
        json=operations_structure_payload,
    )
    assert operations_save.status_code == 200, operations_save.get_json()
    assert SalaryStructure.query.filter_by(user_id=second_employee.id).one().salary_template_id == operations_save.get_json()["salary_template"]["id"]
    assert float(SalaryStructure.query.filter_by(user_id=second_employee.id).one().annual_ctc) == 1_500_000
    assert client.put(
        f"/api/payroll/people/{second_employee.id}/salary-structure",
        headers=employee_headers,
        json=operations_structure_payload,
    ).status_code == 403

    arrears_template_response = client.post(
        "/api/payroll/templates",
        headers=finance_headers,
        json={
            **structure_payload,
            "name": "Employee One February Arrears",
            "arrears_employee_id": employee.id,
            "arrears_description": "February adjustment",
            "arrears_amount": 1350,
            "arrears_month": 2,
            "arrears_year": 2026,
        },
    )
    assert arrears_template_response.status_code == 201, arrears_template_response.get_json()
    arrears_template = arrears_template_response.get_json()
    assert arrears_template["arrears_employee_id"] == employee.id
    wrong_employee_assignment = client.post(
        f"/api/payroll/templates/{arrears_template['id']}/assign",
        headers=finance_headers,
        json={"employee_ids": [second_employee.id]},
    )
    assert wrong_employee_assignment.status_code == 400
    arrears_assignment = client.post(
        f"/api/payroll/templates/{arrears_template['id']}/assign",
        headers=finance_headers,
        json={"employee_ids": [employee.id]},
    )
    assert arrears_assignment.status_code == 200, arrears_assignment.get_json()
    february_preview = client.post(
        "/api/payroll/preview-bulk",
        headers=finance_headers,
        json={
            "salary_template_id": arrears_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 2,
            "year": 2026,
            "user_ids": [employee.id],
        },
    )
    assert february_preview.status_code == 200, february_preview.get_json()
    february_earnings = february_preview.get_json()["previews"][0]["earnings"]
    arrears_row = next(row for row in february_earnings if row["name"] == "Arrears - February adjustment (February 2026)")
    assert arrears_row["amount"] == 1350
    other_month_preview = client.post(
        "/api/payroll/preview-bulk",
        headers=finance_headers,
        json={
            "salary_template_id": arrears_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 6,
            "year": 2026,
            "user_ids": [employee.id],
        },
    )
    assert other_month_preview.status_code == 200, other_month_preview.get_json()
    assert not any(
        row["name"].startswith("Arrears -")
        for row in other_month_preview.get_json()["previews"][0]["earnings"]
    )
    arrears_generation = client.post(
        "/api/payroll/generate-selected",
        headers=finance_headers,
        json={
            "salary_template_id": arrears_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 2,
            "year": 2026,
            "user_ids": [employee.id],
        },
    )
    assert arrears_generation.status_code == 201, arrears_generation.get_json()
    arrears_payslip = Payslip.query.filter_by(
        user_id=employee.id, month=2, year=2026,
    ).one()
    assert arrears_payslip.gross_earnings == 102_550
    assert any(
        row["name"] == "Arrears - February adjustment (February 2026)"
        and row["amount"] == 1350
        for row in arrears_payslip.earnings
    )

    multi_arrears_template_response = client.post(
        "/api/payroll/templates",
        headers=finance_headers,
        json={
            **structure_payload,
            "name": "Selected Employees June Arrears",
            "arrears_by_employee": {
                str(employee.id): {"description": "Individual arrears", "amount": 700},
                str(second_employee.id): {"description": "Back pay", "amount": 1250},
            },
            "arrears_month": 6,
            "arrears_year": 2026,
        },
    )
    assert multi_arrears_template_response.status_code == 201, multi_arrears_template_response.get_json()
    multi_arrears_template = multi_arrears_template_response.get_json()
    wrong_multi_arrears_assignment = client.post(
        f"/api/payroll/templates/{multi_arrears_template['id']}/assign",
        headers=finance_headers,
        json={"employee_ids": [operations.id]},
    )
    assert wrong_multi_arrears_assignment.status_code == 400
    multi_arrears_assignment = client.post(
        f"/api/payroll/templates/{multi_arrears_template['id']}/assign",
        headers=finance_headers,
        json={"employee_ids": [employee.id, second_employee.id]},
    )
    assert multi_arrears_assignment.status_code == 200, multi_arrears_assignment.get_json()
    multi_arrears_preview = client.post(
        "/api/payroll/preview-bulk",
        headers=finance_headers,
        json={
            "salary_template_id": multi_arrears_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 6,
            "year": 2026,
            "user_ids": [employee.id, second_employee.id],
        },
    )
    assert multi_arrears_preview.status_code == 200, multi_arrears_preview.get_json()
    previews_by_employee = {
        row["user_id"]: row for row in multi_arrears_preview.get_json()["previews"]
    }
    arrears_by_employee = {
        user_id: {
            row["name"]: row["amount"]
            for row in preview["earnings"]
            if row["name"].startswith("Arrears -")
        }
        for user_id, preview in previews_by_employee.items()
    }
    assert arrears_by_employee[employee.id] == {"Arrears - Individual arrears (June 2026)": 700}
    assert arrears_by_employee[second_employee.id] == {"Arrears - Back pay (June 2026)": 1250}
    july_preview = client.post(
        "/api/payroll/preview-bulk",
        headers=finance_headers,
        json={
            "salary_template_id": multi_arrears_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 7,
            "year": 2026,
            "user_ids": [employee.id, second_employee.id],
        },
    )
    assert july_preview.status_code == 200, july_preview.get_json()
    assert all(
        not any(row["name"].startswith("Arrears -") for row in preview["earnings"])
        for preview in july_preview.get_json()["previews"]
    )
    multi_arrears_generation = client.post(
        "/api/payroll/generate-selected",
        headers=finance_headers,
        json={
            "salary_template_id": multi_arrears_template["id"],
            "company_name": "Ana Meta IoT",
            "month": 6,
            "year": 2026,
            "user_ids": [employee.id, second_employee.id],
        },
    )
    assert multi_arrears_generation.status_code == 201, multi_arrears_generation.get_json()
    assert Payslip.query.filter_by(
        user_id=employee.id, month=6, year=2026,
    ).one().gross_earnings == 101_900
    assert Payslip.query.filter_by(
        user_id=second_employee.id, month=6, year=2026,
    ).one().gross_earnings == 127_450

    invalid_payroll_employee = create_user("EMP3", "Invalid Payroll", EMPLOYEE)
    db.session.add(SalaryStructure(
        user_id=invalid_payroll_employee.id,
        annual_ctc=120_000,
        basic=100,
        pf_employee=200,
    ))
    db.session.commit()
    payroll_run = client.post(
        "/api/payroll/generate",
        headers=finance_headers,
        json={"month": 5, "year": 2026},
    )
    assert payroll_run.status_code == 200
    skipped_employee = next(
        row for row in payroll_run.get_json()["skipped"]
        if row["user_id"] == invalid_payroll_employee.id
    )
    assert skipped_employee["reason"] == "Total deductions exceed gross earnings."
    assert Payslip.query.filter_by(
        user_id=invalid_payroll_employee.id, month=5, year=2026,
    ).first() is None

    print("Reusable salary structures, overrides, insurance, payroll preview and authorization passed.")
