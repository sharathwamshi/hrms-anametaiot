import io
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, ".")

from config import Config


_folder = tempfile.TemporaryDirectory(prefix="hrms-insurance-")


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    INSURANCE_DOCUMENT_FOLDER = _folder.name
    EXPO_PUSH_ENABLED = False


from app import create_app
from app.extensions import db
from app.models import User
from app.roles import EMPLOYEE, FINANCE_ACCOUNTS, HR_OPERATIONS


app = create_app(TestConfig)


def check(label, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        raise SystemExit(label)


with app.app_context():
    db.create_all()
    hr = User(employee_code="HR-1", full_name="HR", email="hr@test.local", role=HR_OPERATIONS)
    finance = User(employee_code="FIN-1", full_name="Finance", email="finance@test.local", role=FINANCE_ACCOUNTS)
    employee = User(employee_code="EMP-1", full_name="Employee", email="employee@test.local", role=EMPLOYEE)
    for user in (hr, finance, employee):
        user.set_password("test-password")
        db.session.add(user)
    db.session.commit()
    client = app.test_client()

    def login(email):
        response = client.post("/api/auth/login", json={"email": email, "password": "test-password"})
        check(f"login {email}", response.status_code == 200)
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    hr_headers = login(hr.email)
    finance_headers = login(finance.email)
    employee_headers = login(employee.email)
    policy_payload = {
        "employee_id": employee.id,
        "insurance_type": "health",
        "provider_name": "Provider",
        "policy_number": "POL-1",
        "member_id": "MEM-1",
        "certificate_number": "CERT-1",
        "credentials": {"group_code": "GROUP-1"},
        "coverage_amount": 500000,
        "policy_start_date": date.today().isoformat(),
        "policy_expiry_date": (date.today() + timedelta(days=7)).isoformat(),
        "contact_email": "claims@example.test",
    }
    response = client.post("/api/insurance", headers=hr_headers, json=policy_payload)
    check("HR assigns insurance", response.status_code == 201)
    policy_id = response.get_json()["id"]
    response = client.get("/api/insurance", headers=employee_headers)
    check("employee sees only their assigned insurance", response.status_code == 200 and len(response.get_json()) == 1)
    response = client.post("/api/insurance", headers=employee_headers, json=policy_payload)
    check("employee cannot assign insurance", response.status_code == 403)
    response = client.post(
        f"/api/insurance/{policy_id}/documents",
        headers=finance_headers,
        data={"document_type": "policy", "file": (io.BytesIO(b"%PDF-1.4 insurance"), "policy.pdf")},
        content_type="multipart/form-data",
    )
    check("Finance uploads an insurance document", response.status_code == 201)
    document_id = response.get_json()["id"]
    response = client.get(f"/api/insurance/documents/{document_id}/download", headers=employee_headers)
    check("employee downloads their insurance document", response.status_code == 200)
    response = client.patch(f"/api/insurance/{policy_id}/documents/{document_id}/archive", headers=employee_headers)
    check("employee cannot archive insurance documents", response.status_code == 403)
    response = client.post("/api/insurance/internal/expiry-reminders", headers={"X-Internal-Secret": TestConfig.INTERNAL_TASK_SECRET})
    check("expiry reminder task creates reminders", response.status_code == 200 and response.get_json()["created"] >= 1)
    response = client.post("/api/insurance/internal/expiry-reminders", headers={"X-Internal-Secret": TestConfig.INTERNAL_TASK_SECRET})
    check("expiry reminder task prevents duplicate reminders", response.status_code == 200 and response.get_json()["created"] == 0)

print("All insurance management checks passed.")
_folder.cleanup()
