import sys, io
sys.path.insert(0, '.')

from config import Config
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True

from app import create_app
from app.extensions import db
from app.models import User, Department, CompanySettings, Vendor, VendorHire
from app.roles import MANAGER, HR_OPERATIONS, FINANCE_ACCOUNTS, EMPLOYEE
from datetime import date, timedelta

app = create_app(TestConfig)

def ok(label, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label} {extra}")
    if not cond:
        raise SystemExit(f"STOPPED at: {label}")

with app.app_context():
    db.create_all()

    db.session.add(CompanySettings(
        company_name="Ultracash Technologies Pvt Ltd", state="Karnataka",
        gstin="29AABCU7631F1Z8", address="HSR Layout, Bangalore",
    ))

    dept = Department(name="Operations")
    db.session.add(dept); db.session.flush()

    mgr = User(employee_code="M1", full_name="Ananya Rao", email="mgr@test.com",
               role=MANAGER, department_id=dept.id, date_of_joining=date(2024,1,1))
    mgr.set_password("pw")
    finance = User(employee_code="F1", full_name="Rahul Menon", email="finance@test.com",
                    role=FINANCE_ACCOUNTS, department_id=dept.id, manager_id=None,
                    date_of_joining=date(2024,1,1))
    finance.set_password("pw")
    recruiter = User(employee_code="R1", full_name="Sneha K", email="recruiter@test.com",
                      role=EMPLOYEE, department_id=dept.id, date_of_joining=date(2024,1,1))
    recruiter.set_password("pw")
    db.session.add_all([mgr, finance, recruiter])
    db.session.commit()

    client = app.test_client()

    def login(email):
        r = client.post('/api/auth/login', json={'email': email, 'password': 'pw'})
        ok(f"login {email}", r.status_code == 200)
        return {'Authorization': f"Bearer {r.get_json()['access_token']}"}

    fh_header = login('finance@test.com')
    mh = login('mgr@test.com')
    eh = login('recruiter@test.com')

    # --- Non-finance role blocked from parsing agreements ---
    with open('/mnt/user-data/uploads/Agreement_AFPL-Ultracash.pdf', 'rb') as f:
        r = client.post('/api/vendors/agreements/parse', headers=eh,
                         data={'file': (f, 'agreement.pdf')}, content_type='multipart/form-data')
    ok("non-finance blocked from parsing agreement", r.status_code == 403, r.get_json())

    # --- Parse the REAL Ultracash agreement (new vendor) ---
    with open('/mnt/user-data/uploads/Agreement_AFPL-Ultracash.pdf', 'rb') as f:
        r = client.post('/api/vendors/agreements/parse', headers=fh_header,
                         data={'file': (f, 'agreement.pdf')}, content_type='multipart/form-data')
    ok("parse real Ultracash agreement", r.status_code == 200, r.get_json())
    parsed1 = r.get_json()
    ok("correctly identifies Acknowledger as the vendor (not us)",
       parsed1['likely_vendor_name'] == 'Acknowledger First Pvt Ltd', parsed1['likely_vendor_name'])
    ok("no existing vendor match (new vendor)", parsed1['matched_vendor'] is None)
    ok("2 roles parsed", len(parsed1['roles']) == 2, parsed1['roles'])
    ok("Telesales fee is 7.55%", parsed1['roles'][0]['service_fee_pct'] == 7.55)
    ok("effective dates parsed", parsed1['effective_from'] == '2024-07-01' and parsed1['effective_to'] == '2025-07-01')

    # --- Confirm as a NEW vendor ---
    r = client.post('/api/vendors/agreements/confirm', headers=fh_header, json={
        'token': parsed1['token'],
        'new_vendor': {
            'name': 'Acknowledger First Pvt Ltd', 'gstin': '29AASCA1487A1ZJ',
            'address': 'Bengaluru', 'state': 'Karnataka',
            'bank_name': 'IDFC FIRST Bank', 'bank_account_no': '10248098396', 'bank_ifsc': 'IDFB0080167',
        },
        'effective_from': parsed1['effective_from'], 'effective_to': parsed1['effective_to'],
        'termination_notice_days': parsed1['termination_notice_days'],
        'confidentiality_days': parsed1['confidentiality_days'], 'feedback_days': parsed1['feedback_days'],
        'roles': parsed1['roles'],
    })
    ok("new vendor + agreement created", r.status_code == 201, r.get_json())
    vendor_id = r.get_json()['id']
    agreement_id = r.get_json()['agreements'][0]['id']
    role_id = r.get_json()['agreements'][0]['roles'][0]['id']  # Telesales Executive

    # --- Manager blocked from managing vendors (not a VENDOR_MANAGEMENT_ROLE) ---
    r = client.put(f'/api/vendors/{vendor_id}', headers=mh, json={'contact_person': 'X'})
    ok("manager blocked from editing vendor", r.status_code == 403)

    # --- Re-uploading another agreement for the SAME vendor should match ---
    with open('/mnt/user-data/uploads/Agreement_AFPL-Ultracash.pdf', 'rb') as f:
        r = client.post('/api/vendors/agreements/parse', headers=fh_header,
                         data={'file': (f, 'agreement3.pdf')}, content_type='multipart/form-data')
    parsed3 = r.get_json()
    ok("re-uploading same vendor's agreement matches existing vendor",
       parsed3['matched_vendor'] is not None and parsed3['matched_vendor']['id'] == vendor_id,
       parsed3['matched_vendor'])

    r = client.post('/api/vendors/agreements/confirm', headers=fh_header, json={
        'token': parsed3['token'], 'vendor_id': vendor_id,
        'effective_from': parsed3['effective_from'], 'effective_to': parsed3['effective_to'],
        'termination_notice_days': parsed3['termination_notice_days'],
        'confidentiality_days': parsed3['confidentiality_days'], 'feedback_days': parsed3['feedback_days'],
        'roles': parsed3['roles'],
    })
    ok("second agreement added to EXISTING vendor", r.status_code == 201 and len(r.get_json()['agreements']) == 2,
       f"agreement count: {len(r.get_json()['agreements'])}")

    # --- Assign a hire to the vendor role ---
    tenure_start = (date.today() - timedelta(days=65)).isoformat()  # already past 60-day tenure
    r = client.post('/api/vendors/hires', headers=fh_header, json={
        'vendor_id': vendor_id, 'agreement_id': agreement_id, 'agreement_role_id': role_id,
        'employee_id': recruiter.id, 'candidate_name': 'Saniya Banu',
        'ctc': 240000, 'tenure_start_date': tenure_start,
    })
    ok("hire assigned to vendor role", r.status_code == 201, r.get_json())
    hire_id = r.get_json()['id']
    ok("hire is billable (tenure already elapsed)", r.get_json()['is_billable'] is True, r.get_json())

    # --- Payroll auto-started check ---
    from app.models import SalaryStructure
    structure = SalaryStructure.query.filter_by(user_id=recruiter.id).first()
    ok("salary structure auto-created on assignment", structure is not None and structure.basic == 240000)

    # --- Generate invoice ---
    r = client.post(f'/api/vendors/{vendor_id}/invoices/generate', headers=fh_header, json={})
    ok("invoice generated", r.status_code == 201, r.get_json())
    invoice = r.get_json()
    ok("fee = 7.55% of 240000 = 18120", invoice['subtotal'] == 18120.0, invoice['subtotal'])
    ok("CGST = 9% of subtotal", abs(invoice['cgst_amount'] - 1630.8) < 0.01, invoice['cgst_amount'])
    ok("PDF generated", invoice['pdf_path'] is not None, invoice['pdf_path'])
    import os
    pdf_disk_path = invoice['pdf_path'].replace('/static/uploads/', 'app/static/uploads/')
    ok("PDF file actually exists on disk", os.path.exists(pdf_disk_path), pdf_disk_path)
    invoice_id = invoice['id']

    # --- Hire should no longer be billable (already invoiced) ---
    r = client.get('/api/vendors/hires', headers=fh_header, query_string={'vendor_id': vendor_id})
    hire_after = [h for h in r.get_json() if h['id'] == hire_id][0]
    ok("hire status is now 'invoiced'", hire_after['status'] == 'invoiced', hire_after['status'])

    # --- Approval flow ---
    r = client.post(f'/api/vendors/invoices/{invoice_id}/submit-for-approval', headers=fh_header)
    ok("submitted for approval", r.get_json()['status'] == 'pending_approval')

    r = client.post(f'/api/vendors/invoices/{invoice_id}/approve', headers=fh_header)
    ok("finance CANNOT approve their own invoice (approver-only)", r.status_code == 403, r.get_json())

    r = client.post(f'/api/vendors/invoices/{invoice_id}/approve', headers=mh)
    ok("manager approves invoice", r.status_code == 200 and r.get_json()['status'] == 'approved', r.get_json())

    r = client.post(f'/api/vendors/invoices/{invoice_id}/mark-paid', headers=fh_header)
    ok("finance marks invoice paid", r.status_code == 200 and r.get_json()['status'] == 'paid', r.get_json())

    # --- Replacement flow ---
    r = client.post(f'/api/vendors/hires/{hire_id}/replace', headers=fh_header, json={
        'candidate_name': 'Replacement Candidate', 'ctc': 250000,
    })
    ok("replacement hire created", r.status_code == 201, r.get_json())

print("\nALL VENDOR MANAGEMENT SMOKE TESTS PASSED")
