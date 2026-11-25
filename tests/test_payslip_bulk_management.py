import io
import os
import sys
import tempfile
import zipfile
from datetime import date

sys.path.insert(0, ".")

from config import Config

_payslip_tmp = tempfile.TemporaryDirectory(prefix="hrms-bulk-payslips-")


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    PAYSLIP_FOLDER = _payslip_tmp.name


from app import create_app
from app.extensions import db
from app.models import Attendance, Payslip, SalaryStructure, User
from app.roles import EMPLOYEE, FINANCE_ACCOUNTS, MANAGER

app = create_app(TestConfig)


def check(label, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label} {detail}")
    if not condition:
        raise SystemExit(f"Stopped at: {label}")


def create_user(code, name, role, *, manager_id=None, category=None):
    user = User(
        employee_code=code,
        full_name=name,
        email=f"{code.lower()}@test.com",
        role=role,
        company_name="Ana Meta IoT",
        manager_id=manager_id,
        employee_category=category,
    )
    user.set_password("test-password")
    db.session.add(user)
    db.session.flush()
    return user


with app.app_context():
    db.create_all()
    finance = create_user("FIN1", "Finance User", FINANCE_ACCOUNTS)
    manager = create_user("MGR1", "Manager One", MANAGER)
    other_manager = create_user("MGR2", "Manager Two", MANAGER)
    employee = create_user("EMP1", "Direct Employee", EMPLOYEE, manager_id=manager.id, category="full_time")
    other_employee = create_user("EMP2", "Other Employee", EMPLOYEE, manager_id=other_manager.id, category="full_time")
    part_time = create_user("EMP3", "Part Time Employee", EMPLOYEE, manager_id=manager.id, category="part_time")
    db.session.add_all([
        SalaryStructure(
            user_id=employee.id,
            basic=31000,
            custom_earnings=[{"name": "Bonus", "amount": 3100}],
            pf_employee=100,
        ),
        SalaryStructure(user_id=other_employee.id, basic=31000),
        SalaryStructure(user_id=part_time.id, basic=31000),
    ])
    db.session.add_all([
        Attendance(user_id=employee.id, work_date=date(2026, 1, 1), status="present"),
        Attendance(user_id=other_employee.id, work_date=date(2026, 1, 1), status="present"),
        Attendance(user_id=other_employee.id, work_date=date(2026, 1, 2), status="present"),
    ])
    db.session.commit()

    client = app.test_client()

    def login(user):
        response = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "test-password"},
        )
        check(f"login {user.role}", response.status_code == 200)
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    finance_headers = login(finance)
    manager_headers = login(manager)
    other_manager_headers = login(other_manager)
    employee_headers = login(employee)

    templates_response = client.get("/api/payroll/payslip-templates", headers=finance_headers)
    templates = templates_response.get_json()
    check("all three company-specific templates are configured", templates_response.status_code == 200 and len(templates) == 3)
    check("company templates keep three distinct PDF layouts", len({item["layout_key"] for item in templates}) == 3)

    payload = {
        "company_name": "Ana Meta IoT",
        "employee_category": "full_time",
        "month": 1,
        "year": 2026,
        "user_ids": [employee.id, other_employee.id],
    }
    preview_response = client.post("/api/payroll/preview-bulk", headers=finance_headers, json=payload)
    previews = preview_response.get_json()["previews"]
    check("bulk preview loads matching employees and salary data", preview_response.status_code == 200 and len(previews) == 2)
    preview_by_id = {row["user_id"]: row for row in previews}
    check("bulk preview prorates earnings using attendance", preview_by_id[employee.id]["gross_earnings"] == 1100)
    check("bulk preview includes saved employee details and template snapshot", preview_by_id[employee.id]["employee_info"]["employee_code"] == "EMP1" and preview_by_id[employee.id]["template_snapshot"]["layout_key"] == "ana_meta_iot")
    check("employee category mismatch is rejected", client.post(
        "/api/payroll/preview-bulk",
        headers=finance_headers,
        json={**payload, "employee_category": "part_time"},
    ).status_code == 400)

    adjustments = [{
        "user_id": employee.id,
        "earnings": [{"name": "Basic Pay", "amount": 1000}, {"name": "Bonus", "amount": 100}],
        "deductions": [{"name": "PF", "amount": 50}],
    }]
    generated_response = client.post(
        "/api/payroll/generate-selected",
        headers=finance_headers,
        json={**payload, "adjustments": adjustments},
    )
    generated = generated_response.get_json()
    check("Finance can generate multiple payslips", generated_response.status_code == 201 and len(generated) == 2)
    by_user = {row["user_id"]: row for row in generated}
    check("bulk salary edits update earnings, deductions, and net pay", by_user[employee.id]["gross_earnings"] == 1100 and by_user[employee.id]["total_deductions"] == 50 and by_user[employee.id]["net_pay"] == 1050)
    check("bulk generation stores private PDFs and revisions", all(
        os.path.isfile(os.path.join(TestConfig.PAYSLIP_FOLDER, row["pdf_path"])) and row["revision_count"] == 1
        for row in generated
    ))
    db.session.add_all([
        Payslip(
            user_id=employee.id, month=5, year=2025, status="paid",
            earnings=[{"name": "Basic Salary", "amount": 2000}],
            deductions=[{"name": "PF", "amount": 25}],
        ),
        Payslip(
            user_id=employee.id, month=3, year=2025, status="paid",
            earnings=[{"name": "Basic Salary", "amount": 500}],
        ),
    ])
    db.session.commit()
    structure_response = client.get(
        f"/api/payroll/structure/{employee.id}",
        headers=finance_headers,
        query_string={"month": 1, "year": 2026},
    )
    component_rows = {row["name"]: row for row in structure_response.get_json()["salary_components"]}
    check("salary structure identifies an existing selected-month payslip", structure_response.get_json()["has_current_month_payslip"])
    check("YTD sums actual payslip records in the April-to-March financial year", component_rows["Basic Salary"]["ytd"] == 3000)
    check("MTD includes only the selected payroll month", component_rows["Basic Salary"]["mtd"] == 1000)
    check("deduction YTD recognizes existing PF payroll rows", component_rows["Employee PF"]["ytd"] == 75)
    check("duplicate employee-period generation is rejected", client.post(
        "/api/payroll/generate-selected", headers=finance_headers, json=payload,
    ).status_code == 400)
    check("duplicate employee adjustments are rejected", client.post(
        "/api/payroll/generate-selected",
        headers=finance_headers,
        json={**{**payload, "user_ids": [part_time.id], "employee_category": "part_time"},
              "adjustments": [{"user_id": part_time.id}, {"user_id": part_time.id}]},
    ).status_code == 400)

    first_payslip_id = by_user[employee.id]["id"]
    other_payslip_id = by_user[other_employee.id]["id"]
    published_response = client.post(
        f"/api/payroll/payslips/{first_payslip_id}/publish",
        headers=finance_headers,
    )
    check("Finance can publish a generated payslip", published_response.status_code == 200)
    check("Finance can publish a second selected payslip", client.post(
        f"/api/payroll/payslips/{other_payslip_id}/publish",
        headers=finance_headers,
    ).status_code == 200)
    historical_template = db.session.get(Payslip, first_payslip_id).template_snapshot
    updated_template = {
        **templates[0],
        "address": "New Ana Meta address",
    }
    template_change = client.put(
        "/api/payroll/payslip-templates/Ana%20Meta%20IoT",
        headers=finance_headers,
        json=updated_template,
    )
    check("Finance can update a company template", template_change.status_code == 200)
    historical = db.session.get(Payslip, first_payslip_id)
    check("template updates do not alter historical payslips", historical.template_snapshot == historical_template)

    archive_response = client.post(
        "/api/payroll/payslips/bulk-download",
        headers=finance_headers,
        json={"payslip_ids": [first_payslip_id, other_payslip_id]},
    )
    with zipfile.ZipFile(io.BytesIO(archive_response.data)) as archive:
        check("Finance can download an archive containing each selected PDF", archive_response.status_code == 200 and len(archive.namelist()) == 2)

    profile = client.get(
        f"/api/payroll/people/{employee.id}/payroll-profile",
        headers=finance_headers,
    ).get_json()
    salary_structure = profile["salary_structure"]
    salary_structure["basic"] = 32000
    salary_update = client.put(
        f"/api/payroll/people/{employee.id}/payroll-profile",
        headers=finance_headers,
        json={"salary_structure": salary_structure},
    )
    check("Finance can edit an employee salary structure", salary_update.status_code == 200)
    audit_response = client.get(
        f"/api/payroll/audit?employee_id={employee.id}",
        headers=finance_headers,
    )
    check("salary structure changes are available in the audit history", audit_response.status_code == 200 and any(
        row["action"] == "salary_structure_updated" for row in audit_response.get_json()
    ))

    check("Manager sees only assigned employees", {
        row["id"] for row in client.get("/api/payroll/manager/people", headers=manager_headers).get_json()
    } == {employee.id, part_time.id})
    check("Manager can view an assigned published payslip", client.get(
        f"/api/payroll/payslip/{first_payslip_id}", headers=manager_headers,
    ).status_code == 200)
    check("Manager cannot access another manager's payslip", client.get(
        f"/api/payroll/payslip/{other_payslip_id}", headers=manager_headers,
    ).status_code == 403)
    check("Manager cannot access template management", client.get(
        "/api/payroll/payslip-templates", headers=manager_headers,
    ).status_code == 403)
    check("Manager cannot access Finance audit history", client.get(
        "/api/payroll/audit", headers=manager_headers,
    ).status_code == 403)
    check("Manager cannot generate payslips", client.post(
        "/api/payroll/generate-selected", headers=manager_headers, json=payload,
    ).status_code == 403)
    profile_update = {
        "employee_category": "part_time",
        "designation": "Updated Role",
        "pan": "ABCDE1234F",
    }
    check("Manager can edit an assigned employee profile", client.put(
        f"/api/payroll/people/{employee.id}/payroll-profile",
        headers=manager_headers,
        json=profile_update,
    ).status_code == 200)
    check("Manager cannot edit another team's employee profile", client.put(
        f"/api/payroll/people/{other_employee.id}/payroll-profile",
        headers=manager_headers,
        json=profile_update,
    ).status_code == 403)
    check("Manager cannot change finalized salary amounts", client.put(
        f"/api/payroll/people/{employee.id}/payroll-profile",
        headers=manager_headers,
        json={"salary_structure": {"basic": 999999}},
    ).status_code == 403)

    check("Employee can download only their own published payslip", client.get(
        f"/api/payroll/payslips/{first_payslip_id}/pdf", headers=employee_headers,
    ).status_code == 200)
    check("Employee cannot access another employee's payslip PDF", client.get(
        f"/api/payroll/payslips/{other_payslip_id}/pdf", headers=employee_headers,
    ).status_code == 403)

print("BULK PAYSLIP MANAGEMENT CHECKS PASSED")
