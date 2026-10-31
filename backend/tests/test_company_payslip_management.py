import io
import os
import sys
import tempfile

sys.path.insert(0, ".")

from config import Config

_payslip_tmp = tempfile.TemporaryDirectory(prefix="hrms-payslips-")


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    PAYSLIP_FOLDER = _payslip_tmp.name


from app import create_app
from app.extensions import db
from app.models import User
from app.utils.payslip_pdf import COMPANY_THEMES
import pdfplumber
from app.roles import (
    CONTRACT_EMPLOYEE,
    EMPLOYEE,
    FINANCE_ACCOUNTS,
    HR_OPERATIONS,
    HR_RECRUITER,
    MANAGER,
    OPERATIONS,
)

app = create_app(TestConfig)


def check(label, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label} {detail}")
    if not condition:
        raise SystemExit(f"Stopped at: {label}")


def create_user(code, name, role):
    user = User(
        employee_code=code,
        full_name=name,
        email=f"{code.lower()}@test.com",
        role=role,
    )
    user.set_password("test-password")
    db.session.add(user)
    db.session.flush()
    return user


with app.app_context():
    db.create_all()
    finance = create_user("FIN1", "Finance User", FINANCE_ACCOUNTS)
    employee = create_user("EMP1", "Payslip Employee", EMPLOYEE)
    other_employee = create_user("EMP2", "Other Employee", EMPLOYEE)
    readonly_users = [
        create_user("HR1", "HR Operations User", HR_OPERATIONS),
        create_user("MGR1", "Manager User", MANAGER),
        create_user("OPS1", "Operations User", OPERATIONS),
        create_user("REC1", "Recruiter User", HR_RECRUITER),
        create_user("CON1", "Contract User", CONTRACT_EMPLOYEE),
    ]
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
    employee_headers = login(employee)
    other_employee_headers = login(other_employee)
    readonly_headers = [login(user) for user in readonly_users]

    initial = {
        "user_id": employee.id,
        "month": 6,
        "year": 2026,
        "company_name": "Acknowledger First Pvt Ltd",
        "employee_info": {
            "pan": "ABCDE1234F",
            "pf_number": "PF-100",
            "bank_name": "Example Bank",
            "bank_account_number": "123456789",
            "pay_mode": "Bank Transfer",
            "location": "Bengaluru",
        },
        "total_working_days": 30,
        "total_paid_days": 29,
        "days_present": 28,
        "lop_days": 1,
        "earnings": [
            {"name": "Basic Salary", "amount": 1000},
            {"name": "Custom Project Bonus", "amount": 500},
        ],
        "deductions": [{"name": "Custom Deduction", "amount": 125}],
    }
    wrong_company = {**initial, "company_name": "Ana Meta IoT"}
    check("payslip creation rejects an employee-company mismatch", client.post(
        "/api/payroll/payslips", headers=finance_headers, json=wrong_company,
    ).status_code == 400)
    response = client.post("/api/payroll/payslips", headers=finance_headers, json=initial)
    check("Finance creates a draft payslip", response.status_code == 201, response.get_json())
    draft = response.get_json()
    payslip_id = draft["id"]
    check("earnings and deductions total correctly", draft["gross_earnings"] == 1500 and draft["total_deductions"] == 125)
    check("net pay and amount in words are calculated", draft["net_pay"] == 1375 and "One Thousand Three Hundred Seventy Five" in draft["amount_in_words"])
    check("company assignment defaults to AFPL", draft["company_name"] == "Acknowledger First Pvt Ltd")
    check("each supported company has a distinct payslip palette", len({tuple(map(str, theme)) for theme in COMPANY_THEMES.values()}) == 3)
    check("created PDF is kept in private storage", draft["pdf_path"] and not draft["pdf_path"].startswith("/static/"))
    private_pdf = os.path.join(TestConfig.PAYSLIP_FOLDER, draft["pdf_path"])
    check("generated PDF exists", os.path.isfile(private_pdf))
    with pdfplumber.open(private_pdf) as document:
        pdf_text = document.pages[0].extract_text()
        check("generated PDF is A4 and includes company and amount words", abs(document.pages[0].width - 595.28) < 1 and "Acknowledger First Pvt Ltd" in pdf_text and "One Thousand Three Hundred Seventy Five Rupees" in pdf_text)

        negative_amount = {
            **initial,
            "month": 10,
            "earnings": [{"name": "Invalid negative", "amount": -1}],
        }
        check("negative amounts are rejected", client.post(
            "/api/payroll/payslips", headers=finance_headers, json=negative_amount,
        ).status_code == 400)

    response = client.get(f"/api/payroll/payslips/{employee.id}", headers=employee_headers)
    check("employee cannot see a draft", response.status_code == 200 and response.get_json() == [])
    check("employee cannot fetch a draft directly", client.get(f"/api/payroll/payslip/{payslip_id}", headers=employee_headers).status_code == 403)
    check("employee cannot download a draft", client.get(f"/api/payroll/payslips/{payslip_id}/pdf", headers=employee_headers).status_code == 403)
    check("employee cannot list another employee's payslips", client.get(f"/api/payroll/payslips/{other_employee.id}", headers=employee_headers).status_code == 403)

    edit_payload = {
        **initial,
        "earnings": [
            {"name": "Basic Salary", "amount": 1200},
            {"name": "Custom Project Bonus", "amount": 500},
        ],
        "deductions": [{"name": "Custom Deduction", "amount": 125}],
    }
    response = client.put(f"/api/payroll/payslips/{payslip_id}", headers=finance_headers, json=edit_payload)
    check("Finance edits a draft payslip", response.status_code == 200 and response.get_json()["net_pay"] == 1575)

    uploaded_bytes = b"%PDF-1.4\n% Existing signed payslip\n%%EOF\n"
    response = client.post(
        f"/api/payroll/payslips/{payslip_id}/upload",
        headers=finance_headers,
        data={"file": (io.BytesIO(uploaded_bytes), "existing-payslip.pdf")},
        content_type="multipart/form-data",
    )
    check("Finance uploads a PDF", response.status_code == 200 and response.get_json()["pdf_is_uploaded"])
    uploaded = response.get_json()
    upload_path = os.path.join(TestConfig.PAYSLIP_FOLDER, uploaded["pdf_path"])
    check("uploaded PDF is private", os.path.isfile(upload_path) and "uploads" in uploaded["pdf_path"])
    check("invalid upload extension is rejected", client.post(
        f"/api/payroll/payslips/{payslip_id}/upload",
        headers=finance_headers,
        data={"file": (io.BytesIO(b"not a pdf"), "bad.txt")},
        content_type="multipart/form-data",
    ).status_code == 400)

    response = client.post(f"/api/payroll/payslips/{payslip_id}/publish", headers=finance_headers)
    check("Finance publishes payslip", response.status_code == 200 and response.get_json()["status"] == "published")
    response = client.get(f"/api/payroll/payslips/{employee.id}", headers=employee_headers)
    check("employee sees only their published payslip", response.status_code == 200 and [row["id"] for row in response.get_json()] == [payslip_id])
    response = client.get(f"/api/payroll/payslips/{payslip_id}/pdf", headers=employee_headers)
    check("employee downloads their published PDF", response.status_code == 200 and response.data == uploaded_bytes)
    check("public uploads route does not expose payslips", client.get(f"/static/uploads/{uploaded['pdf_path']}").status_code == 404)
    check("non-Finance cannot remove an uploaded PDF", client.delete(
        f"/api/payroll/payslips/{payslip_id}/pdf", headers=employee_headers,
    ).status_code == 403)
    replacement_bytes = b"%PDF-1.4\n% Replacement payslip\n%%EOF\n"
    replacement_response = client.post(
        f"/api/payroll/payslips/{payslip_id}/upload",
        headers=finance_headers,
        data={"file": (io.BytesIO(replacement_bytes), "replacement-payslip.pdf")},
        content_type="multipart/form-data",
    )
    replacement = replacement_response.get_json()
    check("Finance can replace an existing uploaded PDF", replacement_response.status_code == 200 and replacement["pdf_is_uploaded"] and replacement["pdf_filename"] == "replacement-payslip.pdf")
    check("replaced uploaded PDF is removed from private storage", not os.path.exists(upload_path))
    replacement_path = os.path.join(TestConfig.PAYSLIP_FOLDER, replacement["pdf_path"])
    remove_response = client.delete(f"/api/payroll/payslips/{payslip_id}/pdf", headers=finance_headers)
    removed = remove_response.get_json()
    check("Finance can remove an uploaded PDF", remove_response.status_code == 200 and not removed["pdf_is_uploaded"])
    check("removing uploaded PDF restores the generated payslip", removed["pdf_path"] != replacement["pdf_path"] and os.path.isfile(os.path.join(TestConfig.PAYSLIP_FOLDER, removed["pdf_path"])))
    check("removed uploaded PDF is deleted from private storage", not os.path.exists(replacement_path))
    check("employee downloads generated PDF after uploaded PDF removal", client.get(
        f"/api/payroll/payslips/{payslip_id}/pdf", headers=employee_headers,
    ).status_code == 200)
    check("employee cannot edit their published payslip", client.put(
        f"/api/payroll/payslips/{payslip_id}", headers=employee_headers, json=edit_payload,
    ).status_code == 403)
    check("employee cannot upload a payslip", client.post(
        f"/api/payroll/payslips/{payslip_id}/upload",
        headers=employee_headers,
        data={"file": (io.BytesIO(uploaded_bytes), "blocked.pdf")},
        content_type="multipart/form-data",
    ).status_code == 403)
    check("employee cannot delete a payslip", client.delete(
        f"/api/payroll/payslips/{payslip_id}", headers=employee_headers,
    ).status_code == 403)

    updated_payload = {
        **edit_payload,
        "company_name": "Acknowledger First Pvt Ltd",
        "month": 6,
        "year": 2026,
        "deductions": [{"name": "Custom Deduction", "amount": 2000}],
    }
    response = client.put(
        f"/api/payroll/payslips/{payslip_id}",
        headers=finance_headers,
        json=updated_payload,
    )
    check("deductions exceeding earnings are rejected", response.status_code == 400)
    check("rejected edits do not change the employee company", employee.company_name == "Acknowledger First Pvt Ltd")

    updated_payload["deductions"] = [{"name": "Custom Deduction", "amount": 125}]
    updated_payload["company_name"] = "Ana Meta IoT"
    response = client.put(
        f"/api/payroll/payslips/{payslip_id}",
        headers=finance_headers,
        json=updated_payload,
    )
    check("payslip edits reject a company/template change", response.status_code == 400)
    updated_payload["company_name"] = "Acknowledger First Pvt Ltd"
    response = client.put(
        f"/api/payroll/payslips/{payslip_id}",
        headers=finance_headers,
        json=updated_payload,
    )
    updated = response.get_json()
    check("editing a published payslip is audited as updated", response.status_code == 200 and updated["status"] == "updated")
    check("updated payslip retains publication and update audit fields", updated["published_by"] == finance.id and updated["updated_by"] == finance.id)
    check("employee can still view an updated published payslip", len(client.get(
        f"/api/payroll/payslips/{employee.id}", headers=employee_headers,
    ).get_json()) == 1)

    for role_user, headers in zip(readonly_users, readonly_headers):
        response = client.get("/api/payroll/payslips", headers=headers)
        check(f"{role_user.role} can view published payslips", response.status_code == 200 and len(response.get_json()) == 1)
        check(f"{role_user.role} cannot edit through the API", client.put(
            f"/api/payroll/payslips/{payslip_id}", headers=headers, json=edit_payload,
        ).status_code == 403)
        check(f"{role_user.role} cannot upload through the API", client.post(
            f"/api/payroll/payslips/{payslip_id}/upload",
            headers=headers,
            data={"file": (io.BytesIO(uploaded_bytes), "blocked.pdf")},
            content_type="multipart/form-data",
        ).status_code == 403)
        check(f"{role_user.role} cannot delete through the API", client.delete(
            f"/api/payroll/payslips/{payslip_id}", headers=headers,
        ).status_code == 403)

    for company_name, month in (
        ("Ana Meta IoT", 7),
        ("Acknowledger First Pvt Ltd", 8),
        ("Vkalpa Innovations", 9),
    ):
        response = client.patch(
            f"/api/payroll/people/{other_employee.id}/company",
            headers=finance_headers,
            json={"company_name": company_name},
        )
        check(f"Finance assigns {company_name}", response.status_code == 200)
        payload = {
            **initial,
            "user_id": other_employee.id,
            "month": month,
            "company_name": company_name,
        }
        response = client.post("/api/payroll/payslips", headers=finance_headers, json=payload)
        check(f"{company_name} template creates a payslip", response.status_code == 201 and response.get_json()["company_name"] == company_name)
        generated = os.path.join(TestConfig.PAYSLIP_FOLDER, response.get_json()["pdf_path"])
        check(f"{company_name} PDF exists", os.path.isfile(generated))
        with pdfplumber.open(generated) as document:
            check(f"{company_name} PDF uses the assigned company header", company_name in document.pages[0].extract_text())

    delete_draft_payload = {
        **initial,
        "user_id": other_employee.id,
        "month": 10,
        "company_name": other_employee.company_name,
    }
    delete_draft_response = client.post(
        "/api/payroll/payslips", headers=finance_headers, json=delete_draft_payload,
    )
    delete_draft_id = delete_draft_response.get_json()["id"]
    check("Finance deletes a draft payslip", client.delete(
        f"/api/payroll/payslips/{delete_draft_id}", headers=finance_headers,
    ).status_code == 200)

    check("employee cannot assign a company", client.patch(
        f"/api/payroll/people/{employee.id}/company",
        headers=employee_headers,
        json={"company_name": "Ana Meta IoT"},
    ).status_code == 403)
    check("non-Finance cannot create a payslip", client.post(
        "/api/payroll/payslips", headers=employee_headers, json=initial,
    ).status_code == 403)
    check("Finance cannot delete an updated published payslip", client.delete(
        f"/api/payroll/payslips/{payslip_id}", headers=finance_headers,
    ).status_code == 409)

print("COMPANY PAYSLIP MANAGEMENT CHECKS PASSED")
