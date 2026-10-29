import io
import os
import sys
import tempfile
from datetime import date, datetime, timedelta

sys.path.insert(0, ".")

from config import Config


_document_dir = tempfile.TemporaryDirectory(prefix="hrms-employee-documents-")


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    EMPLOYEE_DOCUMENT_FOLDER = _document_dir.name


from app import create_app
from app.extensions import db
from app.models import Attendance, EmployeeDocument, EmployeeFamilyMember, User
from app.roles import EMPLOYEE, HR_OPERATIONS, MANAGER


app = create_app(TestConfig)


def check(label, condition, details=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label} {details}")
    if not condition:
        raise SystemExit(f"Stopped at: {label}")


with app.app_context():
    db.create_all()
    manager = User(employee_code="MGR-1", full_name="Manager", email="manager@test.local", role=MANAGER)
    hr = User(employee_code="HR-1", full_name="HR", email="hr@test.local", role=HR_OPERATIONS)
    employee = User(
        employee_code="EMP-1",
        full_name="Employee",
        email="employee@test.local",
        role=EMPLOYEE,
        manager=manager,
    )
    outsider = User(employee_code="EMP-2", full_name="Outsider", email="outsider@test.local", role=EMPLOYEE)
    for user in (manager, hr, employee, outsider):
        user.set_password("test-password")
        db.session.add(user)
    db.session.commit()

    client = app.test_client()

    def login(email):
        response = client.post("/api/auth/login", json={"email": email, "password": "test-password"})
        check(f"login {email}", response.status_code == 200)
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    employee_headers = login(employee.email)
    manager_headers = login(manager.email)
    hr_headers = login(hr.email)
    outsider_headers = login(outsider.email)

    response = client.patch(
        "/api/profile/me",
        headers=employee_headers,
        json={
            "full_name": "Updated Employee",
            "email": "updated.employee@test.local",
            "date_of_birth": "1994-06-15",
            "residential_address": "10 Main Street",
        },
    )
    check("employee updates permitted personal fields", response.status_code == 200)
    check("updated profile fields persisted", response.get_json()["profile"]["date_of_birth"] == "1994-06-15")
    response = client.patch(
        f"/api/employees/{employee.id}/profile",
        headers=manager_headers,
        json={"phone": "+1 555 0101"},
    )
    check("direct manager can update a report's personal contact information", response.status_code == 200)
    response = client.get(
        f"/api/employees/{employee.id}/profile",
        headers=outsider_headers,
    )
    check("unrelated employee cannot view personal profile fields", response.status_code == 403)

    response = client.patch(
        "/api/profile/me",
        headers=employee_headers,
        json={"employee_code": "ROOT", "role": "super_admin", "designation": "CEO"},
    )
    check("self-service rejects protected HR fields", response.status_code == 400)
    check("protected employee fields remain unchanged", db.session.get(User, employee.id).employee_code == "EMP-1")

    response = client.patch("/api/profile/me", headers=employee_headers, json={"uan": "123456789012"})
    check("self-service rejects UAN updates", response.status_code == 400)

    response = client.post(
        "/api/profile/family",
        headers=employee_headers,
        json={
            "name": "Family Member",
            "relationship": "Parent",
            "date_of_birth": "1960-01-02",
            "phone": "+1 555 0100",
            "is_emergency_contact": True,
        },
    )
    check("employee adds family member", response.status_code == 201)
    family_member_id = response.get_json()["id"]
    response = client.put(
        f"/api/profile/family/{family_member_id}",
        headers=outsider_headers,
        json={"name": "Hijacked"},
    )
    check("other employee cannot edit family member", response.status_code == 403)
    response = client.get("/api/profile/family", headers=manager_headers, query_string={"user_id": employee.id})
    check("direct manager can view family record", response.status_code == 200 and len(response.get_json()) == 1)

    response = client.put(
        f"/api/employees/{employee.id}/statutory",
        headers=employee_headers,
        json={"uan": "123456789012"},
    )
    check("employee cannot set UAN", response.status_code == 403)
    response = client.get(f"/api/employees/{employee.id}/statutory", headers=employee_headers)
    check("employee can view their own UAN without edit access", response.status_code == 200 and response.get_json()["uan"] is None)
    response = client.put(
        f"/api/employees/{employee.id}/statutory",
        headers=hr_headers,
        json={"uan": "123456789012"},
    )
    check("HR sets valid UAN", response.status_code == 200)
    response = client.get(f"/api/employees/{employee.id}/statutory", headers=manager_headers)
    check("direct manager can view a report's UAN", response.status_code == 200)
    response = client.put(
        f"/api/employees/{employee.id}/statutory",
        headers=manager_headers,
        json={"uan": "210987654321"},
    )
    check("direct manager can update a report's UAN", response.status_code == 200)
    response = client.get(f"/api/employees/{employee.id}/statutory", headers=employee_headers)
    check("employee sees the UAN set by HR or manager", response.status_code == 200 and response.get_json()["uan"] == "210987654321")
    response = client.get(f"/api/employees/{outsider.id}/statutory", headers=manager_headers)
    check("manager cannot view unrelated employee UAN", response.status_code == 403)
    response = client.get(f"/api/employees/{manager.id}/statutory", headers=manager_headers)
    check("manager can view their own UAN", response.status_code == 200)
    response = client.put(
        f"/api/employees/{employee.id}/statutory",
        headers=hr_headers,
        json={"uan": "invalid"},
    )
    check("HR UAN validation requires 12 digits", response.status_code == 400)
    response = client.get(f"/api/employees/{employee.id}", headers=employee_headers)
    check("UAN is not exposed in general employee serialization", "uan" not in response.get_json())

    pdf_content = b"%PDF-1.4\n% employee document\n"
    response = client.post(
        "/api/documents",
        headers=employee_headers,
        data={
            "doc_type": "education_10th",
            "title": "Certificate",
            "file": (io.BytesIO(pdf_content), "certificate.pdf"),
        },
        content_type="multipart/form-data",
    )
    check("employee uploads a validated private document", response.status_code == 201)
    document = response.get_json()
    check("document URL is relative to the configured API base path", document["file_path"].startswith("/documents/"))
    stored_path = os.path.join(
        TestConfig.EMPLOYEE_DOCUMENT_FOLDER,
        *db.session.get(EmployeeDocument, document["id"]).storage_key.split("/"),
    )
    check("document is stored outside public upload folder", os.path.isfile(stored_path))
    response = client.get(f"/api{document['file_path']}", headers=employee_headers)
    check("employee downloads their document", response.status_code == 200 and response.data == pdf_content)
    response = client.get(f"/api{document['file_path']}", headers=outsider_headers)
    check("unrelated employee cannot download document", response.status_code == 403)
    response = client.get(
        "/static/uploads/documents/legacy/secret.pdf",
        headers=employee_headers,
    )
    check("legacy public document path is blocked", response.status_code == 404)
    response = client.get(
        "/static/uploads/Documents/legacy/secret.pdf",
        headers=employee_headers,
    )
    check("legacy document path is blocked case-insensitively", response.status_code == 404)
    response = client.patch(
        f"/api/documents/{document['id']}/verification",
        headers=employee_headers,
        json={"status": "verified"},
    )
    check("employee cannot verify documents", response.status_code == 403)
    response = client.patch(
        f"/api/documents/{document['id']}/verification",
        headers=manager_headers,
        json={"status": "verified", "note": "Checked original"},
    )
    check("direct manager can verify a report's document", response.status_code == 200 and response.get_json()["verification_status"] == "verified")
    response = client.post(
        "/api/documents",
        headers=outsider_headers,
        data={
            "doc_type": "education_10th",
            "title": "Outsider Certificate",
            "file": (io.BytesIO(pdf_content), "outsider-certificate.pdf"),
        },
        content_type="multipart/form-data",
    )
    outsider_document_id = response.get_json()["id"]
    response = client.patch(
        f"/api/documents/{outsider_document_id}/verification",
        headers=manager_headers,
        json={"status": "verified"},
    )
    check("manager cannot verify an unrelated employee's document", response.status_code == 403)
    response = client.patch(
        f"/api/documents/{document['id']}/verification",
        headers=hr_headers,
        json={"status": "verified", "note": "Checked original"},
    )
    check("HR verifies a document", response.status_code == 200 and response.get_json()["verification_status"] == "verified")

    response = client.post(
        f"/api/employees/{employee.id}/emergency-communications",
        headers=hr_headers,
        json={
            "family_member_id": family_member_id,
            "contact_name": "Family Member",
            "communication_method": "phone",
            "purpose": "Emergency notification",
            "outcome": "Reached",
        },
    )
    check("HR records emergency communication", response.status_code == 201)
    response = client.get(
        f"/api/employees/{employee.id}/emergency-communications",
        headers=manager_headers,
    )
    check("direct manager can view a report's emergency communication history", response.status_code == 200 and len(response.get_json()) == 1)
    response = client.post(
        f"/api/employees/{employee.id}/emergency-communications",
        headers=manager_headers,
        json={
            "contact_name": "Family Member",
            "communication_method": "phone",
            "purpose": "Manager follow-up",
        },
    )
    check("direct manager can record a report's emergency communication", response.status_code == 201)
    response = client.get(
        f"/api/employees/{employee.id}/emergency-communications",
        headers=outsider_headers,
    )
    check("unrelated employee cannot view emergency communications", response.status_code == 403)
    response = client.get(
        f"/api/employees/{employee.id}/emergency-communications",
        headers=employee_headers,
    )
    check("employee cannot view emergency communication history", response.status_code == 403)

    absence_date = date.today() - timedelta(days=2)
    response = client.post(
        "/api/attendance/absence",
        headers=hr_headers,
        json={"user_id": employee.id, "work_date": absence_date.isoformat(), "reason": "Unreported absence"},
    )
    check(
        "HR records absence through attendance",
        response.status_code == 201 and response.get_json()["status"] == "absent",
        f"status={response.status_code}, body={response.get_json()}",
    )
    response = client.post(
        "/api/attendance/absence",
        headers=manager_headers,
        json={"user_id": employee.id, "work_date": absence_date.isoformat(), "reason": "Not authorized"},
    )
    check("manager cannot directly record absence", response.status_code == 403)

    punch_date = date.today() - timedelta(days=1)
    db.session.add(Attendance(
        user_id=employee.id,
        work_date=punch_date,
        clock_in=datetime.combine(punch_date, datetime.min.time()),
        status="present",
    ))
    db.session.commit()
    response = client.post(
        "/api/attendance/absence",
        headers=hr_headers,
        json={"user_id": employee.id, "work_date": punch_date.isoformat(), "reason": "Incorrect"},
    )
    check("absence update cannot overwrite existing punches", response.status_code == 409)

print("All employee profile and document checks passed.")
_document_dir.cleanup()
