import sys
sys.path.insert(0, '.')

from config import Config
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True

from app import create_app
from app.extensions import db
from app.models import User, Department, Candidate, JobPosting, CompanySettings
from app.roles import MANAGER, HR_OPERATIONS, FINANCE_ACCOUNTS, EMPLOYEE
from datetime import date

app = create_app(TestConfig)

def ok(label, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label} {extra}")
    if not cond:
        raise SystemExit(f"STOPPED at: {label}")

with app.app_context():
    db.create_all()
    db.session.add(CompanySettings(company_name="AnametaIOT", state="Karnataka"))
    dept = Department(name="Ops"); db.session.add(dept); db.session.flush()

    mgr = User(employee_code="M1", full_name="Ananya Rao", email="mgr@test.com", role=MANAGER,
               department_id=dept.id, date_of_joining=date(2024,1,1))
    mgr.set_password("pw")
    admin = User(employee_code="A1", full_name="Priya Nair", email="admin@test.com", role=HR_OPERATIONS,
                 department_id=dept.id, date_of_joining=date(2024,1,1))
    admin.set_password("pw")
    finance = User(employee_code="F1", full_name="Rahul Menon", email="finance@test.com", role=FINANCE_ACCOUNTS,
                    department_id=dept.id, date_of_joining=date(2024,1,1))
    finance.set_password("pw")
    db.session.add_all([mgr, admin, finance]); db.session.flush()

    emp = User(employee_code="E1", full_name="Karthik Iyer", email="emp@test.com", role=EMPLOYEE,
               department_id=dept.id, manager_id=mgr.id, date_of_joining=date(2024,1,1))
    emp.set_password("pw")
    outsider = User(employee_code="E2", full_name="Outsider", email="out@test.com", role=EMPLOYEE,
                     department_id=dept.id, date_of_joining=date(2024,1,1))
    outsider.set_password("pw")
    db.session.add_all([emp, outsider]); db.session.commit()

    client = app.test_client()
    def login(email):
        r = client.post('/api/auth/login', json={'email': email, 'password': 'pw'})
        ok(f"login {email}", r.status_code == 200)
        return {'Authorization': f"Bearer {r.get_json()['access_token']}"}

    mh, ah, fh, eh = login('mgr@test.com'), login('admin@test.com'), login('finance@test.com'), login('emp@test.com')

    # --- Permissions catalogue ---
    r = client.get('/api/employees/permissions/catalogue', headers=eh)
    ok("permissions catalogue accessible", r.status_code == 200 and len(r.get_json()) == 3, r.get_json())

    # --- Create a job posting to test approval gating ---
    r = client.post('/api/recruitment/jobs', headers=ah, json={'title': 'Test Role', 'department_id': dept.id})
    job_id = r.get_json()['id']

    # Employee cannot approve (no role, no permission)
    r = client.post(f'/api/recruitment/jobs/{job_id}/approve', headers=eh)
    ok("employee without permission blocked from approving job", r.status_code == 403, r.get_json())

    # Manager grants employee 'approve_job_postings' permission
    r = client.post(f'/api/employees/{emp.id}/permissions', headers=mh, json={'permission_key': 'approve_job_postings'})
    ok("manager grants permission to own report", r.status_code == 201, r.get_json())

    # Manager CANNOT grant permission to someone who isn't their report
    r = client.post(f'/api/employees/{outsider.id}/permissions', headers=mh, json={'permission_key': 'approve_job_postings'})
    ok("manager blocked from granting permission to a non-report", r.status_code == 403, r.get_json())

    # Now employee CAN approve the job (via granted permission, not role)
    r = client.post(f'/api/recruitment/jobs/{job_id}/approve', headers=eh)
    ok("employee WITH granted permission can now approve job", r.status_code == 200, r.get_json())

    # Revoke and confirm it's gone
    r = client.delete(f'/api/employees/{emp.id}/permissions/approve_job_postings', headers=mh)
    ok("manager revokes permission", r.status_code == 200)
    r = client.get(f'/api/employees/{emp.id}/permissions', headers=mh)
    ok("permission list now empty", r.get_json() == [], r.get_json())

    # --- Performance snapshot ---
    r = client.get(f'/api/employees/{emp.id}/performance-snapshot', headers=mh)
    ok("manager views report's performance snapshot", r.status_code == 200, r.get_json())

    # --- Standalone vendor creation ---
    r = client.post('/api/vendors', headers=fh, json={
        'name': 'Direct Vendor Co', 'gstin': '29AAAAA0000A1Z1', 'state': 'Karnataka',
        'bank_name': 'HDFC', 'bank_account_no': '123456', 'bank_ifsc': 'HDFC0001',
    })
    ok("finance creates a vendor directly (no agreement yet)", r.status_code == 201, r.get_json())
    ok("new vendor has zero agreements", r.get_json()['agreement_count'] == 0)

    # Duplicate name blocked
    r = client.post('/api/vendors', headers=fh, json={'name': 'Direct Vendor Co'})
    ok("duplicate vendor name blocked", r.status_code == 409, r.get_json())

    # --- Payroll templates ---
    r = client.post('/api/payroll/templates', headers=fh, json={
        'name': 'Standard Employee', 'basic_pct': 50, 'hra_pct': 20,
        'special_allowance_pct': 20, 'other_allowance_pct': 10,
        'pf_employee_pct': 6, 'professional_tax_flat': 200,
    })
    ok("finance creates salary template", r.status_code == 201, r.get_json())
    template_id = r.get_json()['id']
    ok("earnings total to 100%", r.get_json()['earnings_total_pct'] == 100)

    r = client.post(f'/api/payroll/templates/{template_id}/apply/{emp.id}', headers=fh, json={'ctc': 600000})
    ok("template applied to employee", r.status_code == 200, r.get_json())
    structure = r.get_json()
    ok("basic = 50% of monthly (600000/12*0.5=25000)", structure['basic'] == 25000.0, structure['basic'])
    ok("hra = 20% of monthly = 10000", structure['hra'] == 10000.0, structure['hra'])

    # --- Full payroll run generates a real PDF ---
    r = client.post('/api/payroll/generate', headers=fh, json={'month': 8, 'year': 2026})
    ok("payroll generation runs", r.status_code == 200, r.get_json())
    matching = [p for p in r.get_json() if p['user_id'] == emp.id]
    ok("employee's payslip generated with a PDF", len(matching) == 1 and matching[0]['pdf_path'] is not None, matching)
    import os
    pdf_path = matching[0]['pdf_path'].replace('/static/uploads/', 'app/static/uploads/')
    ok("payslip PDF actually exists on disk", os.path.exists(pdf_path), pdf_path)

print("\nALL PERMISSIONS / PAYROLL TEMPLATE / VENDOR-CREATE SMOKE TESTS PASSED")
