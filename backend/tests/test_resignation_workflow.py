import io
import os
import sys
import tempfile
import unittest
from datetime import timedelta

from flask_jwt_extended import create_access_token

sys.path.insert(0, ".")

from config import Config


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESTING = True
    EXPO_PUSH_ENABLED = False


from app import create_app
from app.extensions import db
from app.models import Department, User
from app.models.payroll import SalaryStructure
from app.models.resignation import (
    ResignationChecklistItem, ResignationPolicy, ResignationRequest, ResignationRouting,
)
from app.roles import EMPLOYEE, FINANCE_ACCOUNTS, HR_OPERATIONS, MANAGER
from app.utils.company_time import company_today


class ResignationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app.config["RESIGNATION_DOCUMENT_FOLDER"] = self.temp_dir.name
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.department = Department(name="Engineering")
        db.session.add(self.department)
        db.session.flush()
        self.manager = self._user("MGR", "Manager", MANAGER)
        self.other_manager = self._user("OMGR", "Other Manager", MANAGER)
        self.hr = self._user("HR", "HR Operations", HR_OPERATIONS)
        self.finance = self._user("FIN", "Finance", FINANCE_ACCOUNTS)
        self.l2 = self._user("L2", "L2 Approver", EMPLOYEE)
        self.employee = self._user("EMP", "Employee", EMPLOYEE, self.manager.id)
        self.outsider = self._user("OUT", "Outsider", EMPLOYEE, self.other_manager.id)
        db.session.add(ResignationRouting(
            company_name=self.employee.company_name,
            approver_user_id=self.l2.id,
            created_by=self.hr.id,
        ))
        db.session.add(ResignationPolicy(
            company_name=self.employee.company_name,
            notice_period_days=30,
            buyback_daily_divisor=365,
            buyback_multiplier="1.0000",
            version=1,
            updated_by=self.hr.id,
        ))
        db.session.commit()
        self.client = self.app.test_client()
        self.employee_headers = self._headers(self.employee)
        self.manager_headers = self._headers(self.manager)
        self.other_manager_headers = self._headers(self.other_manager)
        self.hr_headers = self._headers(self.hr)
        self.finance_headers = self._headers(self.finance)
        self.l2_headers = self._headers(self.l2)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        self.temp_dir.cleanup()

    def _user(self, code, name, role, manager_id=None):
        user = User(
            employee_code=code,
            full_name=name,
            email=f"{code.lower()}@example.com",
            role=role,
            manager_id=manager_id,
            department_id=self.department.id,
            company_name="Acknowledger First Pvt Ltd",
            is_active=True,
        )
        user.set_password("password")
        db.session.add(user)
        db.session.flush()
        db.session.add(SalaryStructure(user_id=user.id, annual_ctc="1200000.00"))
        return user

    def _headers(self, user):
        response = self.client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "password"},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    def _submit(self, headers=None, file=False, exit_choice="serve_full_notice", extra=None):
        body = {
            "proposed_last_working_date": (company_today() + timedelta(days=30)).isoformat(),
            "exit_choice": exit_choice,
            "policy_version": "1",
            "reason": "A new opportunity",
            "comments": "Thank you for the support.",
        }
        body.update(extra or {})
        if file:
            body["document"] = (io.BytesIO(b"%PDF-1.4\nresignation letter"), "letter.pdf")
        return self.client.post(
            "/api/resignations",
            headers=headers or self.employee_headers,
            data=body if file else None,
            json=None if file else body,
            content_type="multipart/form-data" if file else "application/json",
        )

    def test_hr_can_revoke_with_audited_reason_and_restore_employee_status(self):
        submitted = self._submit()
        resignation_id = submitted.get_json()["id"]
        denied = self.client.post(
            f"/api/resignations/{resignation_id}/revoke",
            headers=self.manager_headers,
            json={"reason": "Not authorized"},
        )
        self.assertEqual(denied.status_code, 403)
        missing_reason = self.client.post(
            f"/api/resignations/{resignation_id}/revoke",
            headers=self.hr_headers,
            json={"reason": " "},
        )
        self.assertEqual(missing_reason.status_code, 400)

        revoked = self.client.post(
            f"/api/resignations/{resignation_id}/revoke",
            headers=self.hr_headers,
            json={"reason": "Employee and HR agreed to cancel the request."},
        )
        self.assertEqual(revoked.status_code, 200, revoked.get_json())
        self.assertEqual(revoked.get_json()["status"], "revoked")
        self.assertIsNone(revoked.get_json()["active_key"])
        self.assertEqual(self.employee.employment_status, "active")
        self.assertEqual(self.employee.resignation_decision, "revoked")
        self.assertEqual(
            self.client.get(
                f"/api/resignations/{resignation_id}", headers=self.hr_headers
            ).get_json()["history"][-1]["comments"],
            "Employee and HR agreed to cancel the request.",
        )

    def test_revoke_is_blocked_after_full_buyback_payment_is_verified(self):
        submitted = self._submit(exit_choice="full_notice_buyback")
        resignation = ResignationRequest.query.get(submitted.get_json()["id"])
        resignation.buyback_payment_status = "verified"
        db.session.commit()
        response = self.client.post(
            f"/api/resignations/{resignation.id}/revoke",
            headers=self.hr_headers,
            json={"reason": "Testing restriction"},
        )
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual(resignation.status, "manager_pending")
        self.assertEqual(self.employee.employment_status, "resignation_pending")

    def test_full_approval_finance_and_exit_checklist(self):
        response = self._submit()
        self.assertEqual(response.status_code, 201, response.get_json())
        resignation_id = response.get_json()["id"]
        self.assertEqual(response.get_json()["status"], "manager_pending")
        self.assertEqual(response.get_json()["active_key"], f"employee:{self.employee.id}")
        self.assertIsNone(response.get_json()["remaining_notice_period_days"])

        duplicate = self._submit()
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.get_json()["message"], "You already have an active resignation request.")
        self.assertEqual(len(self.client.get("/api/resignations/my", headers=self.employee_headers).get_json()), 1)

        own_decision = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.employee_headers,
            json={"decision": "approve"},
        )
        self.assertEqual(own_decision.status_code, 403)
        wrong_manager = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.other_manager_headers,
            json={"decision": "approve"},
        )
        self.assertEqual(wrong_manager.status_code, 403)

        self.assertEqual(self.client.get("/api/resignations/queue", headers=self.manager_headers).get_json()[0]["id"], resignation_id)
        for headers, expected_stage in (
            (self.manager_headers, "l2"),
            (self.l2_headers, "hr"),
        ):
            response = self.client.post(
                f"/api/resignations/{resignation_id}/decision",
                headers=headers,
                json={"decision": "approve"},
            )
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(response.get_json()["current_stage"], expected_stage)

        too_early = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.hr_headers,
            json={
                "decision": "approve",
                "approved_last_working_date": (company_today() + timedelta(days=29)).isoformat(),
            },
        )
        self.assertEqual(too_early.status_code, 400)
        end_date = (company_today() + timedelta(days=30)).isoformat()
        response = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.hr_headers,
            json={"decision": "approve", "approved_last_working_date": end_date},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["current_stage"], "finance")
        self.assertEqual(response.get_json()["approved_last_working_date"], end_date)
        self.assertEqual(response.get_json()["remaining_notice_period_days"], 30)

        response = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.finance_headers,
            json={"decision": "approve"},
        )
        self.assertEqual(response.status_code, 400)
        finance_payload = {
            "decision": "approve",
            "final_settlement_status": "cleared",
            "pending_salary": "1000",
            "advances": "0",
            "reimbursements": "200",
            "other_dues": "0",
            "final_settlement_amount": "1200",
        }
        saved = self.client.patch(
            f"/api/resignations/{resignation_id}/finance",
            headers=self.finance_headers,
            json={**finance_payload, "final_settlement_status": "pending"},
        )
        self.assertEqual(saved.status_code, 200, saved.get_json())
        self.assertEqual(saved.get_json()["finance"]["final_settlement_status"], "pending")
        response = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.finance_headers,
            json=finance_payload,
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["current_stage"], "exit")
        self.assertEqual(response.get_json()["finance"]["final_settlement_status"], "cleared")

        denied = self.client.patch(
            f"/api/resignations/{resignation_id}/checklist/knowledge_transfer",
            headers=self.manager_headers,
            json={"status": "completed"},
        )
        self.assertEqual(denied.status_code, 403)
        employee_headers = self.employee_headers
        hr_items = {
            "assets_returned", "system_access_revocation",
            "hr_clearance", "relieving_letter",
        }
        for key in ("knowledge_transfer", "project_handover"):
            response = self.client.patch(
                f"/api/resignations/{resignation_id}/checklist/{key}",
                headers=employee_headers,
                json={"status": "completed"},
            )
            self.assertEqual(response.status_code, 200, response.get_json())
        for key in hr_items:
            response = self.client.patch(
                f"/api/resignations/{resignation_id}/checklist/{key}",
                headers=self.hr_headers,
                json={"status": "completed"},
            )
            self.assertEqual(response.status_code, 200, response.get_json())
        resignation = db.session.get(ResignationRequest, resignation_id)
        self.assertEqual(resignation.status, "completed")
        self.assertEqual(self.employee.employment_status, "left")
        self.assertIsNone(resignation.active_key)
        self.assertEqual(ResignationChecklistItem.query.filter_by(
            resignation_id=resignation_id, status="completed"
        ).count(), 7)

    def test_each_active_employee_can_submit_but_inactive_employment_is_blocked(self):
        first = self._submit()
        self.assertEqual(first.status_code, 201, first.get_json())

        outsider_headers = self._headers(self.outsider)
        second = self._submit(headers=outsider_headers)
        self.assertEqual(second.status_code, 201, second.get_json())
        self.assertNotEqual(first.get_json()["active_key"], second.get_json()["active_key"])

        inactive = self._user("LEFT", "Former Employee", EMPLOYEE, self.manager.id)
        inactive.employment_status = "left"
        db.session.commit()
        inactive_response = self._submit(headers=self._headers(inactive))
        self.assertEqual(inactive_response.status_code, 409)
        self.assertIn("current employment status is left", inactive_response.get_json()["message"].lower())
        self.assertEqual(ResignationRequest.query.filter_by(employee_id=inactive.id).count(), 0)

    def test_missing_authenticated_employee_record_has_clear_error(self):
        token = create_access_token(identity="999999")
        response = self.client.post(
            "/api/resignations",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.get_json()["message"],
            "The employee record for this account could not be found.",
        )

    def test_date_reapproval_withdrawal_and_document_permissions(self):
        response = self._submit(file=True)
        self.assertEqual(response.status_code, 201, response.get_json())
        data = response.get_json()
        resignation_id = data["id"]
        self.assertTrue(data["document_available"])
        self.assertEqual(data["document_filename"], "letter.pdf")
        document = self.client.get(
            f"/api/resignations/{resignation_id}/document",
            headers=self.manager_headers,
        )
        self.assertEqual(document.status_code, 200)
        self.assertTrue(document.data.startswith(b"%PDF-"))
        document.close()
        denied_document = self.client.get(
            f"/api/resignations/{resignation_id}/document",
            headers=self.other_manager_headers,
        )
        self.assertEqual(denied_document.status_code, 403)

        edited = self.client.patch(
            f"/api/resignations/{resignation_id}/details",
            headers=self.employee_headers,
            json={"reason": "Updated reason", "comments": "Updated comments"},
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.get_json()["reason"], "Updated reason")

        self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.manager_headers,
            json={"decision": "approve"},
        )
        new_date = (company_today() + timedelta(days=45)).isoformat()
        changed = self.client.post(
            f"/api/resignations/{resignation_id}/date-change",
            headers=self.employee_headers,
            json={"proposed_last_working_date": new_date, "reason": "Project handover extension"},
        )
        self.assertEqual(changed.status_code, 201, changed.get_json())
        self.assertEqual(changed.get_json()["current_stage"], "manager")
        self.assertEqual(changed.get_json()["status"], "manager_pending")
        self.assertEqual(changed.get_json()["proposed_last_working_date"], data["proposed_last_working_date"])

        self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.manager_headers,
            json={"decision": "approve"},
        )
        rejected_revision = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.l2_headers,
            json={"decision": "reject", "comment": "Please revise the extension."},
        )
        self.assertEqual(rejected_revision.status_code, 200, rejected_revision.get_json())
        self.assertEqual(rejected_revision.get_json()["current_stage"], "l2")
        self.assertIsNone(rejected_revision.get_json()["pending_revision"])

        withdrawal = self.client.post(
            f"/api/resignations/{resignation_id}/withdrawal",
            headers=self.employee_headers,
        )
        self.assertEqual(withdrawal.status_code, 201, withdrawal.get_json())
        self.assertEqual(withdrawal.get_json()["status"], "withdrawal_pending")
        denied_withdrawal = self.client.post(
            f"/api/resignations/{resignation_id}/withdrawal-decision",
            headers=self.other_manager_headers,
            json={"decision": "approve"},
        )
        self.assertEqual(denied_withdrawal.status_code, 403)
        approved_withdrawal = self.client.post(
            f"/api/resignations/{resignation_id}/withdrawal-decision",
            headers=self.l2_headers,
            json={"decision": "approve"},
        )
        self.assertEqual(approved_withdrawal.status_code, 200, approved_withdrawal.get_json())
        self.assertEqual(approved_withdrawal.get_json()["status"], "withdrawn")
        self.assertEqual(self.employee.employment_status, "active")

    def test_routing_admin_access_and_rejection_comment(self):
        response = self.client.get("/api/resignations/routing", headers=self.employee_headers)
        self.assertEqual(response.status_code, 403)
        response = self.client.get("/api/resignations/routing", headers=self.hr_headers)
        self.assertEqual(response.status_code, 200)
        submitted = self._submit()
        resignation_id = submitted.get_json()["id"]
        missing_comment = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.manager_headers,
            json={"decision": "reject"},
        )
        self.assertEqual(missing_comment.status_code, 400)
        rejected = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.manager_headers,
            json={"decision": "reject", "comment": "Request declined."},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.get_json()["status"], "rejected")
        self.assertEqual(self.employee.employment_status, "active")

    def test_company_policy_configuration_and_missing_policy_blocks_submission(self):
        forbidden = self.client.get("/api/resignations/policy", headers=self.employee_headers)
        self.assertEqual(forbidden.status_code, 403)

        updated = self.client.put(
            "/api/resignations/policy",
            headers=self.hr_headers,
            json={
                "company_name": self.employee.company_name,
                "notice_period_days": 45,
                "buyback_daily_divisor": 360,
                "buyback_multiplier": "1.25",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.get_json())
        self.assertEqual(updated.get_json()["version"], 2)

        quote = self.client.get("/api/resignations/policy/quote", headers=self.employee_headers)
        self.assertEqual(quote.status_code, 200)
        self.assertEqual(quote.get_json()["notice_period_days"], 45)
        self.assertEqual(
            quote.get_json()["expected_last_working_date"],
            (company_today() + timedelta(days=45)).isoformat(),
        )

        db.session.delete(ResignationPolicy.query.filter_by(company_name=self.employee.company_name).first())
        db.session.commit()
        missing_quote = self.client.get("/api/resignations/policy/quote", headers=self.employee_headers)
        self.assertEqual(missing_quote.status_code, 409)
        self.assertIn("not been configured", missing_quote.get_json()["message"])
        blocked = self._submit()
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("not been configured", blocked.get_json()["message"])
        self.assertEqual(ResignationRequest.query.count(), 0)

    def test_incomplete_legacy_policy_returns_clear_error_until_hr_configures_it(self):
        policy = ResignationPolicy.query.filter_by(company_name=self.employee.company_name).first()
        policy.buyback_daily_divisor = None
        policy.buyback_multiplier = None
        db.session.commit()

        quote = self.client.get("/api/resignations/policy/quote", headers=self.employee_headers)
        self.assertEqual(quote.status_code, 409)
        self.assertIn("policy is incomplete", quote.get_json()["message"].lower())
        blocked = self._submit()
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("policy is incomplete", blocked.get_json()["message"].lower())

        saved = self.client.put(
            "/api/resignations/policy",
            headers=self.hr_headers,
            json={
                "company_name": self.employee.company_name,
                "notice_period_days": 30,
                "buyback_daily_divisor": 365,
                "buyback_multiplier": "1.0",
            },
        )
        self.assertEqual(saved.status_code, 200, saved.get_json())
        repaired_quote = self.client.get(
            "/api/resignations/policy/quote",
            headers=self.employee_headers,
        )
        self.assertEqual(repaired_quote.status_code, 200, repaired_quote.get_json())
        self.assertTrue(repaired_quote.get_json()["buyback_available"])

    def test_full_notice_buyback_requires_hr_and_finance_verification(self):
        submitted = self._submit(
            exit_choice="full_notice_buyback",
            extra={"buyback_estimated_amount": "0.01", "buyback_unserved_days": "1"},
        )
        self.assertEqual(submitted.status_code, 201, submitted.get_json())
        data = submitted.get_json()
        resignation_id = data["id"]
        self.assertEqual(data["buyback_estimated_amount"], "98630.14")
        self.assertEqual(data["buyback_unserved_days"], 30)
        self.assertEqual(data["remaining_notice_period_days"], None)

        policy = ResignationPolicy.query.filter_by(company_name=self.employee.company_name).first()
        policy.notice_period_days = 90
        policy.buyback_daily_divisor = 30
        policy.buyback_multiplier = "2.0000"
        policy.version = 2
        db.session.commit()
        unchanged = self.client.get(
            f"/api/resignations/{resignation_id}",
            headers=self.employee_headers,
        ).get_json()
        self.assertEqual(unchanged["buyback_estimated_amount"], "98630.14")
        self.assertEqual(unchanged["exit_policy_snapshot"]["notice_period_days"], 30)

        manager_view = self.client.get(
            f"/api/resignations/{resignation_id}",
            headers=self.manager_headers,
        )
        self.assertIsNone(manager_view.get_json()["buyback_estimated_amount"])
        self.assertNotIn("annual_ctc", manager_view.get_json()["exit_policy_snapshot"])

        for headers in (self.manager_headers, self.l2_headers):
            decision = self.client.post(
                f"/api/resignations/{resignation_id}/decision",
                headers=headers,
                json={"decision": "approve"},
            )
            self.assertEqual(decision.status_code, 200, decision.get_json())

        missing_hr_check = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.hr_headers,
            json={"decision": "approve"},
        )
        self.assertEqual(missing_hr_check.status_code, 400)
        hr_approval = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.hr_headers,
            json={"decision": "approve", "buyback_calculation_verified": True},
        )
        self.assertEqual(hr_approval.status_code, 200, hr_approval.get_json())
        self.assertIsNone(hr_approval.get_json()["approved_last_working_date"])
        self.assertIsNone(hr_approval.get_json()["dates_approved_at"])
        self.assertIsNotNone(hr_approval.get_json()["buyback_calculation_verified_at"])
        self.assertIsNone(hr_approval.get_json()["remaining_notice_period_days"])

        finance_values = {
            "pending_salary": "1000",
            "advances": "0",
            "reimbursements": "0",
            "other_dues": "0",
            "final_settlement_amount": "1000",
            "buyback_payment_reference": "PAY-12345",
        }
        saved = self.client.patch(
            f"/api/resignations/{resignation_id}/finance",
            headers=self.finance_headers,
            json={**finance_values, "final_settlement_status": "pending"},
        )
        self.assertEqual(saved.status_code, 200, saved.get_json())

        finance_payload = {
            **finance_values,
            "decision": "approve",
            "final_settlement_status": "cleared",
            "buyback_payment_verified": False,
        }
        missing_finance_check = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.finance_headers,
            json=finance_payload,
        )
        self.assertEqual(missing_finance_check.status_code, 400)
        finance_payload["buyback_payment_verified"] = True
        finance_clearance = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.finance_headers,
            json=finance_payload,
        )
        self.assertEqual(finance_clearance.status_code, 200, finance_clearance.get_json())
        result = finance_clearance.get_json()
        self.assertEqual(result["approved_last_working_date"], company_today().isoformat())
        self.assertEqual(result["buyback_payment_status"], "verified")
        self.assertEqual(result["buyback_payment_reference"], "PAY-12345")
        self.assertIsNone(result["remaining_notice_period_days"])
        self.assertEqual(result["current_stage"], "exit")

        withdrawal = self.client.post(
            f"/api/resignations/{resignation_id}/withdrawal",
            headers=self.employee_headers,
        )
        self.assertEqual(withdrawal.status_code, 409)

    def test_buyback_is_unavailable_without_employee_salary_data(self):
        salary = SalaryStructure.query.filter_by(user_id=self.employee.id).first()
        salary.annual_ctc = None
        db.session.commit()
        quote = self.client.get("/api/resignations/policy/quote", headers=self.employee_headers)
        self.assertEqual(quote.status_code, 200)
        self.assertFalse(quote.get_json()["buyback_available"])
        blocked = self._submit(exit_choice="full_notice_buyback")
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("annual CTC is not configured", blocked.get_json()["message"])
        self.assertEqual(ResignationRequest.query.count(), 0)

    def test_notice_countdown_waits_for_hr_reapproval_of_revised_date(self):
        submitted = self._submit()
        resignation_id = submitted.get_json()["id"]
        for headers in (self.manager_headers, self.l2_headers, self.hr_headers):
            approved = self.client.post(
                f"/api/resignations/{resignation_id}/decision",
                headers=headers,
                json={"decision": "approve"},
            )
            self.assertEqual(approved.status_code, 200, approved.get_json())
        self.assertEqual(approved.get_json()["remaining_notice_period_days"], 30)

        revised_date = (company_today() + timedelta(days=45)).isoformat()
        revision = self.client.post(
            f"/api/resignations/{resignation_id}/date-change",
            headers=self.employee_headers,
            json={
                "proposed_last_working_date": revised_date,
                "reason": "Additional transition time",
            },
        )
        self.assertEqual(revision.status_code, 201, revision.get_json())
        self.assertIsNone(revision.get_json()["remaining_notice_period_days"])
        self.assertIsNone(revision.get_json()["approved_last_working_date"])

        for headers in (self.manager_headers, self.l2_headers):
            revision = self.client.post(
                f"/api/resignations/{resignation_id}/decision",
                headers=headers,
                json={"decision": "approve"},
            )
            self.assertEqual(revision.status_code, 200, revision.get_json())
        hr_approval = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.hr_headers,
            json={"decision": "approve"},
        )
        self.assertEqual(hr_approval.status_code, 200, hr_approval.get_json())
        self.assertEqual(hr_approval.get_json()["approved_last_working_date"], revised_date)
        self.assertEqual(hr_approval.get_json()["remaining_notice_period_days"], 45)

        finance_clearance = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.finance_headers,
            json={
                "decision": "approve",
                "final_settlement_status": "cleared",
                "pending_salary": "0",
                "advances": "0",
                "reimbursements": "0",
                "other_dues": "0",
                "final_settlement_amount": "0",
            },
        )
        self.assertEqual(finance_clearance.status_code, 200, finance_clearance.get_json())
        self.assertEqual(finance_clearance.get_json()["current_stage"], "exit")
        self.assertEqual(finance_clearance.get_json()["proposed_last_working_date"], revised_date)

    def test_rejected_date_revision_restores_hr_approved_date(self):
        response = self._submit()
        resignation_id = response.get_json()["id"]
        original_date = response.get_json()["proposed_last_working_date"]
        for headers in (self.manager_headers, self.l2_headers):
            response = self.client.post(
                f"/api/resignations/{resignation_id}/decision",
                headers=headers,
                json={"decision": "approve"},
            )
            self.assertEqual(response.status_code, 200, response.get_json())
        response = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.hr_headers,
            json={"decision": "approve"},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["approved_last_working_date"], original_date)

        extended_date = (company_today() + timedelta(days=50)).isoformat()
        response = self.client.post(
            f"/api/resignations/{resignation_id}/date-change",
            headers=self.employee_headers,
            json={"proposed_last_working_date": extended_date, "reason": "Additional transition time"},
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        for headers in (self.manager_headers, self.l2_headers):
            response = self.client.post(
                f"/api/resignations/{resignation_id}/decision",
                headers=headers,
                json={"decision": "approve"},
            )
            self.assertEqual(response.status_code, 200, response.get_json())
        response = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.hr_headers,
            json={"decision": "approve"},
        )
        self.assertEqual(response.get_json()["approved_last_working_date"], extended_date)

        response = self.client.post(
            f"/api/resignations/{resignation_id}/decision",
            headers=self.finance_headers,
            json={"decision": "reject", "comment": "Please review settlement details."},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["status"], "finance_pending")
        self.assertEqual(response.get_json()["approved_last_working_date"], original_date)
        self.assertEqual(response.get_json()["proposed_last_working_date"], original_date)
        self.assertEqual(self.employee.last_working_day.isoformat(), original_date)


if __name__ == "__main__":
    unittest.main()
