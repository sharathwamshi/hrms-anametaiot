import io
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from config import Config


class VendorAgreementTestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    EXPO_PUSH_ENABLED = True
    INTERNAL_TASK_SECRET = "test-internal-secret"


from app import create_app
from app.extensions import db
from app.models import (
    Department, JobPosting, User, Vendor, VendorAgreement, VendorAgreementReminder,
    VendorAgreementRole, VendorCompany, VendorHire, VendorInvoice,
)
from app.roles import (
    CONTRACT_EMPLOYEE, EMPLOYEE, FINANCE_ACCOUNTS, HR_OPERATIONS,
    HR_RECRUITER, MANAGER, OPERATIONS,
)
from app.services.vendor_agreements import (
    REMINDER_MONTH, REMINDER_WEEK, _reminder_date, agreement_status, send_expiry_reminders,
)
from app.utils.agreement_parser import parse_agreement
from app.routes.vendors import _PENDING_AGREEMENTS


class VendorAgreementApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        VendorAgreementTestConfig.VENDOR_AGREEMENT_FOLDER = cls.temp_dir.name
        cls.app = create_app(VendorAgreementTestConfig)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        department = Department(name="Operations")
        db.session.add(department)
        db.session.flush()
        self.finance = self._make_user("FIN-1", "finance@test.invalid", FINANCE_ACCOUNTS, department.id)
        self.hr = self._make_user("HR-1", "hr@test.invalid", HR_OPERATIONS, department.id)
        self.manager = self._make_user("MGR-1", "manager@test.invalid", MANAGER, department.id)
        self.employee = self._make_user("EMP-1", "employee@test.invalid", EMPLOYEE, department.id)
        self.recruiter = self._make_user("REC-1", "recruiter@test.invalid", HR_RECRUITER, department.id)
        self.contract_employee = self._make_user(
            "CON-1", "contract@test.invalid", CONTRACT_EMPLOYEE, department.id
        )
        self.operations = self._make_user(
            "OPS-1", "operations@anametaiot.com", OPERATIONS, department.id
        )
        self.company = VendorCompany(name="Ana Meta IOT")
        db.session.add_all([
            VendorCompany(name="Acknowledger First Private Limited"),
            self.company,
            VendorCompany(name="VKALPA"),
        ])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _make_user(self, code, email, role, department_id):
        user = User(
            employee_code=code,
            full_name=code,
            email=email,
            role=role,
            department_id=department_id,
        )
        user.set_password("test-password")
        db.session.add(user)
        db.session.flush()
        return user

    def headers(self, email):
        response = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": "test-password"},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": "Bearer " + response.get_json()["access_token"]}

    def create_vendor(self, headers=None, name="Vendor One"):
        response = self.client.post(
            "/api/vendors",
            headers=headers or self.headers("finance@test.invalid"),
            json={"name": name, "contact_email": "vendor@example.com", "bank_account_no": "1234567890"},
        )
        return response

    def create_agreement(self, vendor_id, expiry, status="active", file_path="contract.pdf"):
        file_path_abs = os.path.join(VendorAgreementTestConfig.VENDOR_AGREEMENT_FOLDER, file_path)
        with open(file_path_abs, "wb") as agreement_file:
            agreement_file.write(b"%PDF-test document")
        agreement = VendorAgreement(
            vendor_id=vendor_id,
            title="Recruitment Agreement",
            file_path=file_path,
            effective_from=expiry - timedelta(days=30),
            effective_to=expiry,
            status=status,
            uploaded_by=self.finance.id,
        )
        db.session.add(agreement)
        db.session.commit()
        return agreement

    def combined_vendor_form(
        self, company_id=None, new_company_name=None, roles=None, vendor_name="Combined Vendor"
    ):
        data = {
            "name": vendor_name,
            "contact_person": "Vendor Contact",
            "contact_email": "contact@combined.example",
            "contact_phone": "+91 9876543210",
            "gstin": "",
            "pan": "",
            "title": "Recruitment Agreement",
            "effective_from": "2026-10-28",
            "effective_to": "2027-10-27",
            "termination_notice_days": "90",
            "confidentiality_days": "60",
            "feedback_days": "2",
            "roles": json.dumps(roles if roles is not None else [{
                "role_name": "Recruiter",
                "service_fee_pct": 8.5,
                "replacement_days": 30,
                "tenure_days": 60,
            }]),
            "file": (io.BytesIO(b"%PDF-1.4 combined agreement"), "combined.pdf"),
        }
        if company_id is not None:
            data["company_id"] = str(company_id)
        if new_company_name is not None:
            data["new_company_name"] = new_company_name
        return data

    def test_agreement_status_boundaries_and_termination(self):
        today = date(2026, 10, 28)
        cases = (
            (today + timedelta(days=1), today + timedelta(days=7), "upcoming"),
            (today - timedelta(days=1), today + timedelta(days=7), "expiring_soon"),
            (today - timedelta(days=1), today, "expiring_soon"),
            (today - timedelta(days=2), today - timedelta(days=1), "expired"),
        )
        for start, expiry, expected in cases:
            agreement = VendorAgreement(
                effective_from=start,
                effective_to=expiry,
                status="active",
            )
            self.assertEqual(agreement_status(agreement, today), expected)
        terminated = VendorAgreement(
            effective_from=today - timedelta(days=1),
            effective_to=today + timedelta(days=2),
            status="terminated",
        )
        self.assertEqual(agreement_status(terminated, today), "terminated")
        stale_expired = VendorAgreement(
            effective_from=today - timedelta(days=1),
            effective_to=today + timedelta(days=10),
            status="expired",
        )
        self.assertEqual(agreement_status(stale_expired, today), "active")

    def test_agreement_parser_reports_only_fields_found_in_document(self):
        text = (
            "This agreement is made on 1 January 2026 between Company A and Vendor B. Located at "
            "effective from 1 January 2026 till to 31 December 2026, on the following "
            "giving 30 days notice for the period of 10 days from the date of first receipt "
            "within 2 days from the date of receipt"
        )
        with patch(
            "app.utils.agreement_parser.extract_pdf_text_and_tables",
            return_value=(text, []),
        ):
            parsed = parse_agreement(io.BytesIO(b"unused"))

        self.assertEqual(
            set(parsed["extracted_fields"]),
            {
                "party_a", "party_b", "effective_from", "effective_to",
                "termination_notice_days", "confidentiality_days", "feedback_days",
            },
        )
        self.assertEqual(parsed["termination_notice_days"], 30)
        self.assertEqual(parsed["confidentiality_days"], 10)
        self.assertEqual(parsed["feedback_days"], 2)

    def test_vendor_search_duplicate_validation_and_sensitive_data(self):
        finance_headers = self.headers("finance@test.invalid")
        response = self.create_vendor(finance_headers)
        self.assertEqual(response.status_code, 201)
        vendor_id = response.get_json()["id"]

        duplicate = self.create_vendor(finance_headers, "Vendor-One")
        self.assertEqual(duplicate.status_code, 409)

        invalid = self.client.post(
            "/api/vendors",
            headers=finance_headers,
            json={"name": "Bad Email", "contact_email": "not-an-email"},
        )
        self.assertEqual(invalid.status_code, 400)

        listing = self.client.get("/api/vendors?q=vendor%40example.com", headers=finance_headers)
        self.assertEqual(listing.status_code, 200, listing.get_json())
        self.assertEqual([row["id"] for row in listing.get_json()], [vendor_id])
        self.assertNotIn("bank_account_no", listing.get_json()[0])

        manager_detail = self.client.get(
            f"/api/vendors/{vendor_id}",
            headers=self.headers("manager@test.invalid"),
        )
        self.assertEqual(manager_detail.status_code, 200)
        self.assertNotIn("bank_account_no", manager_detail.get_json())

        employee_detail = self.client.get(
            f"/api/vendors/{vendor_id}",
            headers=self.headers("employee@test.invalid"),
        )
        self.assertEqual(employee_detail.status_code, 403)
        employee_headers = self.headers("employee@test.invalid")
        self.assertEqual(self.client.get("/api/vendors/hires", headers=employee_headers).status_code, 403)
        self.assertEqual(self.client.get("/api/vendors/invoices", headers=employee_headers).status_code, 403)
        self.assertEqual(
            self.client.put(f"/api/vendors/{vendor_id}", headers=employee_headers, json={"name": "Changed"}).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/vendors", headers=employee_headers).status_code, 403)
        self.assertEqual(
            self.client.get("/api/vendors", headers=self.headers("recruiter@test.invalid")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/vendors", headers=self.headers("contract@test.invalid")).status_code,
            403,
        )
        manager_headers = self.headers("manager@test.invalid")
        self.assertEqual(
            self.client.post("/api/vendors", headers=manager_headers, json={"name": "Denied Vendor"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.put(
                f"/api/vendors/{vendor_id}", headers=manager_headers, json={"name": "Denied Change"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.put(
                f"/api/vendors/{vendor_id}",
                headers=finance_headers,
                json={"name": "Finance Cannot Edit"},
            ).status_code,
            403,
        )

    def test_vendor_overview_endpoints_allow_finance_and_manager_with_list_responses(self):
        created = self.create_vendor(name="Overview Vendor")
        self.assertEqual(created.status_code, 201)
        vendor_id = created.get_json()["id"]

        for email in ("finance@test.invalid", "manager@test.invalid"):
            headers = self.headers(email)
            for path in ("/api/vendors", "/api/vendors/hires", "/api/vendors/invoices"):
                with self.subTest(email=email, path=path):
                    response = self.client.get(path, headers=headers)
                    self.assertEqual(response.status_code, 200, response.get_json())
                    self.assertIsInstance(response.get_json(), list)
            vendor_list = self.client.get("/api/vendors", headers=headers).get_json()
            self.assertIn(vendor_id, [vendor["id"] for vendor in vendor_list])

        employee_headers = self.headers("employee@test.invalid")
        for path in ("/api/vendors", "/api/vendors/hires", "/api/vendors/invoices"):
            with self.subTest(email="employee@test.invalid", path=path):
                self.assertEqual(
                    self.client.get(path, headers=employee_headers).status_code,
                    403,
                )

    def test_operations_role_can_manage_vendor_and_agreements(self):
        operations_headers = self.headers("operations@anametaiot.com")
        created = self.client.post(
            "/api/vendors",
            headers=operations_headers,
            json={"name": "Operations Vendor", "contact_email": "ops-vendor@example.com"},
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        vendor_id = created.get_json()["id"]

        listing = self.client.get(
            "/api/vendors?q=ops-vendor%40example.com",
            headers=operations_headers,
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([vendor["id"] for vendor in listing.get_json()], [vendor_id])

        update_denied = self.client.put(
            f"/api/vendors/{vendor_id}",
            headers=operations_headers,
            json={"name": "Operations Vendor Updated"},
        )
        self.assertEqual(update_denied.status_code, 403)

        with patch(
            "app.routes.vendors.parse_agreement",
            return_value={
                "party_a": "AnametaIOT",
                "party_b": "Operations Vendor",
                "effective_from": "2026-10-28",
                "effective_to": "2026-11-27",
                "termination_notice_days": 30,
                "confidentiality_days": 30,
                "feedback_days": 2,
                "roles": [],
                "used_ai_fallback": False,
                "raw_text": "agreement",
            },
        ):
            parsed = self.client.post(
                "/api/vendors/agreements/parse",
                headers=operations_headers,
                data={"file": (io.BytesIO(b"%PDF-1.4 sample"), "operations-agreement.pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(parsed.status_code, 200, parsed.get_json())
        confirmed = self.client.post(
            "/api/vendors/agreements/confirm",
            headers=operations_headers,
            json={
                "token": parsed.get_json()["token"],
                "vendor_id": vendor_id,
                "title": "Operations Agreement",
                "effective_from": "2026-10-28",
                "effective_to": "2026-11-27",
                "roles": [],
            },
        )
        self.assertEqual(confirmed.status_code, 201, confirmed.get_json())
        agreement = confirmed.get_json()["agreements"][0]

        updated_agreement = self.client.put(
            f"/api/vendors/agreements/{agreement['id']}",
            headers=operations_headers,
            data={
                "title": "Updated Operations Agreement",
                "effective_from": "2026-10-28",
                "effective_to": "2026-12-27",
                "termination_notice_days": "30",
                "confidentiality_days": "30",
                "feedback_days": "2",
                "status": "active",
                "file": (io.BytesIO(b"%PDF-1.4 replacement"), "replacement.pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(updated_agreement.status_code, 200, updated_agreement.get_json())
        self.assertEqual(updated_agreement.get_json()["title"], "Updated Operations Agreement")
        self.assertEqual(updated_agreement.get_json()["effective_to"], "2026-12-27")

        detail = self.client.get(f"/api/vendors/{vendor_id}", headers=operations_headers)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["agreements"][0]["id"], agreement["id"])
        download_url = detail.get_json()["agreements"][0]["download_url"]
        download = self.client.get(f"/api{download_url}", headers=operations_headers)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, b"%PDF-1.4 replacement")
        download.close()

    def test_combined_vendor_agreement_creation_company_roles_and_download(self):
        finance_headers = self.headers("finance@test.invalid")
        companies = self.client.get("/api/vendors/companies", headers=finance_headers)
        self.assertEqual(companies.status_code, 200)
        self.assertEqual(
            {company["name"] for company in companies.get_json()},
            {"Acknowledger First Private Limited", "Ana Meta IOT", "VKALPA"},
        )
        for index, name in enumerate(("Acknowledger First Private Limited", "VKALPA"), start=1):
            company = next(company for company in companies.get_json() if company["name"] == name)
            selected = self.client.post(
                "/api/vendors/create-with-agreement",
                headers=finance_headers,
                data=self.combined_vendor_form(
                    company_id=company["id"],
                    vendor_name=f"Predefined Company Vendor {index}",
                ),
                content_type="multipart/form-data",
            )
            self.assertEqual(selected.status_code, 201, selected.get_json())
            self.assertEqual(selected.get_json()["company_name"], name)

        created = self.client.post(
            "/api/vendors/create-with-agreement",
            headers=finance_headers,
            data=self.combined_vendor_form(self.company.id),
            content_type="multipart/form-data",
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        payload = created.get_json()
        self.assertEqual(payload["company_name"], "Ana Meta IOT")
        self.assertEqual(len(payload["agreements"]), 1)
        agreement = payload["agreements"][0]
        self.assertEqual(agreement["roles"][0]["role_name"], "Recruiter")
        self.assertEqual(agreement["roles"][0]["service_fee_pct"], 8.5)
        self.assertEqual(agreement["roles"][0]["replacement_days"], 30)
        self.assertEqual(agreement["roles"][0]["tenure_days"], 60)
        response = self.client.get(f"/api{agreement['download_url']}", headers=finance_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"%PDF-1.4 combined agreement")
        response.close()

        added_company = self.client.post(
            "/api/vendors/create-with-agreement",
            headers=finance_headers,
            data=self.combined_vendor_form(
                new_company_name="New Legal Entity",
                vendor_name="Combined Vendor With New Company",
            ),
            content_type="multipart/form-data",
        )
        self.assertEqual(added_company.status_code, 201, added_company.get_json())
        self.assertEqual(added_company.get_json()["company_name"], "New Legal Entity")
        self.assertIsNotNone(VendorCompany.query.filter_by(name="New Legal Entity").first())
        listed_companies = self.client.get("/api/vendors/companies", headers=finance_headers).get_json()
        self.assertIn("New Legal Entity", {company["name"] for company in listed_companies})
        self.assertEqual(self.client.get("/api/vendors", headers=finance_headers).status_code, 200)

    def test_combined_creation_uses_staged_pdf_from_extraction_and_keeps_audit_text(self):
        finance_headers = self.headers("finance@test.invalid")
        with patch(
            "app.routes.vendors.parse_agreement",
            return_value={
                "party_a": "New Vendor",
                "party_b": "Ana Meta IOT",
                "effective_from": "2026-10-28",
                "effective_to": "2027-10-27",
                "termination_notice_days": 90,
                "confidentiality_days": 60,
                "feedback_days": 2,
                "roles": [],
                "used_ai_fallback": True,
                "raw_text": "Parsed agreement text",
                "extracted_fields": ["party_a", "party_b", "effective_from", "effective_to"],
            },
        ):
            parsed = self.client.post(
                "/api/vendors/agreements/parse",
                headers=finance_headers,
                data={"file": (io.BytesIO(b"%PDF-1.4 staged agreement"), "staged.pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(parsed.status_code, 200, parsed.get_json())
        self.assertEqual(
            parsed.get_json()["extracted_fields"],
            ["party_a", "party_b", "effective_from", "effective_to"],
        )
        payload = self.combined_vendor_form(
            company_id=self.company.id,
            vendor_name="Created From Staged PDF",
        )
        payload.pop("file")
        payload["extraction_token"] = parsed.get_json()["token"]

        created = self.client.post(
            "/api/vendors/create-with-agreement",
            headers=finance_headers,
            data=payload,
            content_type="multipart/form-data",
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        agreement = VendorAgreement.query.one()
        self.assertTrue(agreement.parsed_with_ai)
        self.assertEqual(agreement.raw_extracted_text, "Parsed agreement text")
        self.assertTrue(os.path.isfile(
            os.path.join(VendorAgreementTestConfig.VENDOR_AGREEMENT_FOLDER, agreement.file_path)
        ))
        with open(
            os.path.join(VendorAgreementTestConfig.VENDOR_AGREEMENT_FOLDER, agreement.file_path),
            "rb",
        ) as staged_file:
            self.assertEqual(staged_file.read(), b"%PDF-1.4 staged agreement")
        self.assertNotIn(parsed.get_json()["token"], _PENDING_AGREEMENTS)

    def test_combined_creation_validation_and_failure_roll_back_vendor_company_and_file(self):
        finance_headers = self.headers("finance@test.invalid")
        invalid_roles = self.client.post(
            "/api/vendors/create-with-agreement",
            headers=finance_headers,
            data=self.combined_vendor_form(
                self.company.id,
                roles=[{
                    "role_name": "Invalid Role",
                    "service_fee_pct": 101,
                    "replacement_days": 30,
                    "tenure_days": 60,
                }],
            ),
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid_roles.status_code, 400)
        self.assertEqual(Vendor.query.count(), 0)
        self.assertEqual(VendorAgreement.query.count(), 0)

        missing_company = self.client.post(
            "/api/vendors/create-with-agreement",
            headers=finance_headers,
            data=self.combined_vendor_form(),
            content_type="multipart/form-data",
        )
        self.assertEqual(missing_company.status_code, 400)
        empty_custom_company = self.client.post(
            "/api/vendors/create-with-agreement",
            headers=finance_headers,
            data=self.combined_vendor_form(new_company_name="   "),
            content_type="multipart/form-data",
        )
        self.assertEqual(empty_custom_company.status_code, 400)

        files_before = set(os.listdir(VendorAgreementTestConfig.VENDOR_AGREEMENT_FOLDER))
        with patch("app.routes.vendors.db.session.commit", side_effect=RuntimeError("test commit failure")):
            failed = self.client.post(
                "/api/vendors/create-with-agreement",
                headers=finance_headers,
                data=self.combined_vendor_form(new_company_name="Uncommitted Company"),
                content_type="multipart/form-data",
            )
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(Vendor.query.count(), 0)
        self.assertEqual(VendorAgreement.query.count(), 0)
        self.assertIsNone(VendorCompany.query.filter_by(name="Uncommitted Company").first())
        self.assertEqual(set(os.listdir(VendorAgreementTestConfig.VENDOR_AGREEMENT_FOLDER)), files_before)

    def test_vendor_delete_is_hr_only_and_preserves_associated_records(self):
        vendor_response = self.create_vendor()
        vendor_id = vendor_response.get_json()["id"]
        hr_headers = self.headers("hr@test.invalid")

        for email in (
            "manager@test.invalid",
            "finance@test.invalid",
            "operations@anametaiot.com",
            "employee@test.invalid",
            "recruiter@test.invalid",
            "contract@test.invalid",
        ):
            denied = self.client.delete(f"/api/vendors/{vendor_id}", headers=self.headers(email))
            self.assertEqual(denied.status_code, 403, email)
        self.assertIsNotNone(db.session.get(Vendor, vendor_id))

        deleted = self.client.delete(f"/api/vendors/{vendor_id}", headers=hr_headers)
        self.assertEqual(deleted.status_code, 200, deleted.get_json())
        self.assertIsNone(db.session.get(Vendor, vendor_id))

    def test_vendor_delete_blocks_agreement_hire_invoice_and_requisition_dependencies(self):
        hr_headers = self.headers("hr@test.invalid")
        vendor_response = self.create_vendor()
        vendor_id = vendor_response.get_json()["id"]
        agreement = self.create_agreement(vendor_id, date.today() + timedelta(days=30))
        agreement_path = os.path.join(VendorAgreementTestConfig.VENDOR_AGREEMENT_FOLDER, agreement.file_path)
        agreement_role = VendorAgreementRole(
            agreement_id=agreement.id,
            role_name="Recruiter",
            service_fee_pct=8.5,
            replacement_days=30,
            tenure_days=60,
        )
        db.session.add(agreement_role)
        db.session.flush()
        hire = VendorHire(
            vendor_id=vendor_id,
            agreement_id=agreement.id,
            agreement_role_id=agreement_role.id,
            candidate_name="Placed Candidate",
            ctc=500000,
            tenure_start_date=date.today(),
        )
        db.session.add(hire)
        db.session.commit()

        blocked = self.client.delete(f"/api/vendors/{vendor_id}", headers=hr_headers)
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.get_json()["dependencies"]["agreements"], 1)
        self.assertEqual(blocked.get_json()["dependencies"]["hires"], 1)
        self.assertTrue(os.path.isfile(agreement_path))
        self.assertIsNotNone(db.session.get(Vendor, vendor_id))
        self.assertIsNotNone(db.session.get(VendorAgreement, agreement.id))
        self.assertIsNotNone(db.session.get(VendorHire, hire.id))

        invoice_vendor = self.create_vendor(name="Invoice Vendor").get_json()
        invoice = VendorInvoice(
            vendor_id=invoice_vendor["id"],
            invoice_number="TEST-DELETE-1",
            invoice_date=date.today(),
        )
        db.session.add(invoice)
        db.session.commit()
        invoice_blocked = self.client.delete(
            f"/api/vendors/{invoice_vendor['id']}", headers=hr_headers
        )
        self.assertEqual(invoice_blocked.status_code, 409)
        self.assertEqual(invoice_blocked.get_json()["dependencies"]["invoices"], 1)
        self.assertIsNotNone(db.session.get(VendorInvoice, invoice.id))

        requisition_vendor = self.create_vendor(name="Requisition Vendor").get_json()
        requisition = JobPosting(
            title="Vendor Requisition",
            vendor_id=requisition_vendor["id"],
            created_by=self.hr.id,
        )
        db.session.add(requisition)
        db.session.commit()
        requisition_blocked = self.client.delete(
            f"/api/vendors/{requisition_vendor['id']}", headers=hr_headers
        )
        self.assertEqual(requisition_blocked.status_code, 409)
        self.assertEqual(requisition_blocked.get_json()["dependencies"]["requisitions"], 1)
        self.assertIsNotNone(db.session.get(JobPosting, requisition.id))

        manager_headers = self.headers("manager@test.invalid")
        self.assertEqual(
            self.client.put(
                f"/api/vendors/agreements/{agreement.id}",
                headers=manager_headers,
                json={"title": "Unauthorized"},
            ).status_code,
            403,
        )

    def test_agreement_upload_confirm_download_and_access_control(self):
        finance_headers = self.headers("finance@test.invalid")
        with patch(
            "app.routes.vendors.parse_agreement",
            return_value={
                "party_a": "Company",
                "party_b": "Vendor Two",
                "effective_from": "2026-10-28",
                "effective_to": "2026-11-27",
                "termination_notice_days": 30,
                "confidentiality_days": 30,
                "feedback_days": 2,
                "roles": [],
                "used_ai_fallback": False,
                "raw_text": "agreement",
            },
        ):
            parsed = self.client.post(
                "/api/vendors/agreements/parse",
                headers=finance_headers,
                data={"file": (io.BytesIO(b"%PDF-1.4 sample"), "agreement.pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(parsed.status_code, 200)
        self.assertNotIn("file_path", parsed.get_json())

        confirmed = self.client.post(
            "/api/vendors/agreements/confirm",
            headers=finance_headers,
            json={
                "token": parsed.get_json()["token"],
                "new_vendor": {"name": "Vendor Two"},
                "title": "Recruitment Agreement",
                "effective_from": "2026-10-28",
                "effective_to": "2026-11-27",
                "roles": [],
            },
        )
        self.assertEqual(confirmed.status_code, 201, confirmed.get_json())
        agreement = confirmed.get_json()["agreements"][0]
        self.assertEqual(agreement["status"], "active")
        self.assertIn("/download", agreement["download_url"])

        download = self.client.get(f"/api{agreement['download_url']}", headers=finance_headers)
        self.assertEqual(download.status_code, 200, download.get_json(silent=True))
        self.assertTrue(download.data.startswith(b"%PDF-"))
        download.close()

        denied = self.client.get(
            f"/api{agreement['download_url']}",
            headers=self.headers("employee@test.invalid"),
        )
        self.assertEqual(denied.status_code, 403)

    def test_agreement_metadata_update_keeps_existing_file(self):
        vendor = self.create_vendor().get_json()
        agreement = self.create_agreement(vendor["id"], date.today() + timedelta(days=20))
        existing_file = os.path.join(VendorAgreementTestConfig.VENDOR_AGREEMENT_FOLDER, agreement.file_path)

        response = self.client.put(
            f"/api/vendors/agreements/{agreement.id}",
            headers=self.headers("finance@test.invalid"),
            data={
                "title": "Renewal Agreement",
                "effective_from": agreement.effective_from.isoformat(),
                "effective_to": agreement.effective_to.isoformat(),
                "termination_notice_days": str(agreement.termination_notice_days),
                "confidentiality_days": str(agreement.confidentiality_days),
                "feedback_days": str(agreement.feedback_days),
                "status": agreement.status,
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["title"], "Renewal Agreement")
        self.assertEqual(response.get_json()["download_url"], f"/vendors/agreements/{agreement.id}/download")
        self.assertTrue(os.path.isfile(existing_file))
        invalid = self.client.put(
            f"/api/vendors/agreements/{agreement.id}",
            headers=self.headers("finance@test.invalid"),
            data={
                "title": "Invalid Dates",
                "effective_from": agreement.effective_to.isoformat(),
                "effective_to": agreement.effective_from.isoformat(),
                "termination_notice_days": "90",
                "confidentiality_days": "60",
                "feedback_days": "2",
                "status": "active",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertTrue(os.path.isfile(existing_file))

    def test_expiry_reminders_are_deduplicated_and_retry_failed_delivery(self):
        vendor = self.create_vendor().get_json()
        today = date(2026, 10, 28)
        agreement = self.create_agreement(vendor["id"], today + timedelta(days=7))
        with patch("app.services.vendor_agreements.send_push", return_value=True) as send:
            first = send_expiry_reminders(today)
            second = send_expiry_reminders(today)
        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(send.call_count, 1)
        reminder = VendorAgreementReminder.query.one()
        self.assertEqual(reminder.status, "sent")
        self.assertEqual(reminder.expiry_date, agreement.effective_to)

        agreement.effective_to = today + timedelta(days=14)
        db.session.commit()
        with patch("app.services.vendor_agreements.send_push", return_value=True) as send_again:
            new_window = send_expiry_reminders(today + timedelta(days=7))
        self.assertEqual(new_window["sent"], 1)
        self.assertEqual(send_again.call_count, 1)
        self.assertEqual(VendorAgreementReminder.query.count(), 2)

    def test_failed_reminder_delivery_can_be_retried(self):
        vendor = self.create_vendor().get_json()
        today = date(2026, 10, 28)
        self.create_agreement(vendor["id"], today + timedelta(days=7))
        with patch("app.services.vendor_agreements.send_push", return_value=False):
            failed = send_expiry_reminders(today)
        self.assertEqual(failed["failed"], 1)
        self.assertEqual(VendorAgreementReminder.query.one().status, "failed")

        with patch("app.services.vendor_agreements.send_push", return_value=True) as send:
            retried = send_expiry_reminders(today)
        self.assertEqual(retried["sent"], 1)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(VendorAgreementReminder.query.one().status, "sent")

    def test_calendar_month_and_seven_day_reminder_dates(self):
        self.assertEqual(_reminder_date(date(2027, 3, 31), REMINDER_MONTH), date(2027, 2, 28))
        self.assertEqual(_reminder_date(date(2028, 3, 31), REMINDER_MONTH), date(2028, 2, 29))
        self.assertEqual(_reminder_date(date(2026, 11, 4), REMINDER_WEEK), date(2026, 10, 28))

        vendor = self.create_vendor().get_json()
        today = date(2026, 10, 28)
        agreement = self.create_agreement(vendor["id"], date(2026, 11, 28))
        with patch("app.services.vendor_agreements.send_push", return_value=True) as send:
            result = send_expiry_reminders(today)
            duplicate = send_expiry_reminders(today)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(duplicate["skipped"], 1)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(
            VendorAgreementReminder.query.one().reminder_type,
            REMINDER_MONTH,
        )
        self.assertEqual(VendorAgreementReminder.query.one().expiry_date, agreement.effective_to)

    def test_internal_reminder_endpoint_requires_secret(self):
        denied = self.client.post("/api/vendors/internal/agreement-expiry-reminders")
        self.assertEqual(denied.status_code, 403)
        accepted = self.client.post(
            "/api/vendors/internal/agreement-expiry-reminders",
            headers={"X-Internal-Secret": "test-internal-secret"},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json(), {"sent": 0, "failed": 0, "skipped": 0})


if __name__ == "__main__":
    unittest.main()
