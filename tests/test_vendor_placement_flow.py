import sys
sys.path.insert(0, '.')

from config import Config
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True

from app import create_app
from app.extensions import db
from app.models import User, Department, CompanySettings, Vendor, VendorAgreement, VendorAgreementRole, VendorHire
from app.roles import HR_OPERATIONS, HR_RECRUITER, FINANCE_ACCOUNTS, CONTRACT_EMPLOYEE
from datetime import date, timedelta

app = create_app(TestConfig)

def ok(label, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label} {extra}")
    if not cond:
        raise SystemExit(f"STOPPED at: {label}")

with app.app_context():
    db.create_all()
    db.session.add(CompanySettings(company_name="AnametaIOT", state="Karnataka"))
    dept = Department(name="Eng"); db.session.add(dept); db.session.flush()

    admin = User(employee_code="A1", full_name="Priya Nair", email="admin@test.com", role=HR_OPERATIONS,
                 department_id=dept.id, date_of_joining=date(2024, 1, 1))
    admin.set_password("pw")
    recruiter = User(employee_code="R1", full_name="Sneha K", email="recruiter@test.com", role=HR_RECRUITER,
                      department_id=dept.id, date_of_joining=date(2024, 1, 1))
    recruiter.set_password("pw")
    finance = User(employee_code="F1", full_name="Rahul M", email="finance@test.com", role=FINANCE_ACCOUNTS,
                    department_id=dept.id, date_of_joining=date(2024, 1, 1))
    finance.set_password("pw")
    db.session.add_all([admin, recruiter, finance]); db.session.commit()

    client = app.test_client()
    def login(email):
        r = client.post('/api/auth/login', json={'email': email, 'password': 'pw'})
        return {'Authorization': f"Bearer {r.get_json()['access_token']}"}
    ah, rh, fh = login('admin@test.com'), login('recruiter@test.com'), login('finance@test.com')

    # --- Vendor + agreement setup ---
    r = client.post('/api/vendors', headers=fh, json={
        'name': 'Ultracash Technologies', 'state': 'Karnataka', 'gstin': '29AABCU7631F1Z8',
    })
    vendor_id = r.get_json()['id']

    r = client.post('/api/vendors/agreements/confirm', headers=fh, json={
        'token': 'manual-test-token-placeholder',
    })
    # the confirm endpoint needs a real parse token normally; build the agreement directly instead
    agreement = VendorAgreement(vendor_id=vendor_id, file_path='/x', effective_from=date(2024, 1, 1),
                                 uploaded_by=finance.id)
    db.session.add(agreement); db.session.flush()
    role = VendorAgreementRole(agreement_id=agreement.id, role_name="Telesales Executive",
                                service_fee_pct=8.0, replacement_days=30, tenure_days=60)
    db.session.add(role); db.session.commit()

    # ========================================================================
    # 1. Internal vs Client requisitions stay properly separated
    # ========================================================================
    r = client.post('/api/recruitment/jobs', headers=rh, json={'title': 'Internal QA Engineer', 'department_id': dept.id})
    ok("internal job created with default requisition_type", r.status_code == 201 and r.get_json()['requisition_type'] == 'internal', r.get_json())
    internal_job_id = r.get_json()['id']

    r = client.post('/api/recruitment/jobs', headers=rh, json={'title': 'Client Backend Role', 'requisition_type': 'client'})
    ok("client requisition without vendor_id is rejected", r.status_code == 400, r.get_json())

    r = client.post('/api/recruitment/jobs', headers=rh, json={
        'title': 'Client Backend Role', 'requisition_type': 'client', 'vendor_id': vendor_id,
    })
    ok("client requisition with vendor_id created", r.status_code == 201 and r.get_json()['vendor_name'] == 'Ultracash Technologies', r.get_json())
    client_job_id = r.get_json()['id']

    r = client.get('/api/recruitment/jobs', headers=rh, query_string={'requisition_type': 'internal'})
    ok("filtering jobs by requisition_type=internal excludes client jobs",
       all(j['requisition_type'] == 'internal' for j in r.get_json()), r.get_json())

    # --- Candidates in each pipeline stay filterable by requisition_type ---
    client.post('/api/recruitment/candidates', headers=rh, json={
        'job_id': internal_job_id, 'full_name': 'Internal Candidate', 'email': 'intcand@test.com', 'phone': '9800000001',
    })
    client.post('/api/recruitment/candidates', headers=rh, json={
        'job_id': client_job_id, 'full_name': 'Client Candidate', 'email': 'clientcand@test.com', 'phone': '9800000002',
    })
    r = client.get('/api/recruitment/candidates', headers=rh, query_string={'requisition_type': 'client'})
    names = [c['full_name'] for c in r.get_json()]
    ok("All Candidates filter by requisition_type=client isolates the client pipeline",
       names == ['Client Candidate'], names)

    # --- CSV exports work ---
    r = client.get('/api/recruitment/candidates/export', headers=rh)
    ok("all-candidates CSV export returns text/csv", r.status_code == 200 and r.content_type.startswith('text/csv'))
    ok("CSV export includes header + at least one data row", r.data.count(b'\n') >= 2, r.data)

    r = client.get(f'/api/recruitment/jobs/{internal_job_id}/candidates/export', headers=rh)
    ok("per-job CSV export works", r.status_code == 200 and r.content_type.startswith('text/csv'))

    # ========================================================================
    # 2. Direct placement — no internal login created
    # ========================================================================
    r = client.post('/api/vendors/hires', headers=fh, json={
        'vendor_id': vendor_id, 'agreement_id': agreement.id, 'agreement_role_id': role.id,
        'candidate_name': 'Direct Placement Person', 'ctc': 300000,
        'tenure_start_date': (date.today() - timedelta(days=65)).isoformat(),
        'placement_type': 'direct',
    })
    ok("direct placement created", r.status_code == 201, r.get_json())
    direct_hire = r.get_json()
    ok("direct placement has no internal employee_id", direct_hire['employee_id'] is None, direct_hire)
    ok("direct placement defaults to one_time billing", direct_hire['billing_type'] == 'one_time', direct_hire)
    ok("direct placement is billable (tenure already elapsed)", direct_hire['is_billable'] is True, direct_hire)

    user_count_before = User.query.count()

    # ========================================================================
    # 3. Contract placement — creates a real internal Contract Employee login
    # ========================================================================
    r = client.post('/api/vendors/hires', headers=fh, json={
        'vendor_id': vendor_id, 'agreement_id': agreement.id, 'agreement_role_id': role.id,
        'candidate_name': 'Contract Placement Person', 'ctc': 600000,
        'tenure_start_date': date.today().isoformat(),
        'placement_type': 'contract',
        'contract_login_email': 'contractperson@test.com', 'contract_login_password': 'Welcome@123',
    })
    ok("contract placement created", r.status_code == 201, r.get_json())
    contract_hire = r.get_json()
    ok("contract placement HAS an internal employee_id", contract_hire['employee_id'] is not None, contract_hire)
    ok("contract placement defaults to continuous billing", contract_hire['billing_type'] == 'continuous', contract_hire)
    ok("exactly one new internal user was created", User.query.count() == user_count_before + 1)

    contract_user = User.query.get(contract_hire['employee_id'])
    ok("the new internal login has the Contract Employee role (not a real employee role)",
       contract_user.role == CONTRACT_EMPLOYEE, contract_user.role)
    ok("contract login's employee_code was auto-generated and looks right",
       contract_user.employee_code.startswith("CT"), contract_user.employee_code)

    from app.models import SalaryStructure
    struct = SalaryStructure.query.filter_by(user_id=contract_user.id).first()
    ok("payroll starter structure was created for the contract login", struct is not None and struct.basic == 600000)

    # Duplicate email for a second contract login is rejected
    r = client.post('/api/vendors/hires', headers=fh, json={
        'vendor_id': vendor_id, 'agreement_id': agreement.id, 'agreement_role_id': role.id,
        'candidate_name': 'Another Person', 'ctc': 400000, 'tenure_start_date': date.today().isoformat(),
        'placement_type': 'contract',
        'contract_login_email': 'contractperson@test.com', 'contract_login_password': 'pw',
    })
    ok("duplicate contract-login email rejected", r.status_code == 409, r.get_json())

    # Contract placement missing credentials is rejected
    r = client.post('/api/vendors/hires', headers=fh, json={
        'vendor_id': vendor_id, 'agreement_id': agreement.id, 'agreement_role_id': role.id,
        'candidate_name': 'No Creds Person', 'ctc': 400000, 'tenure_start_date': date.today().isoformat(),
        'placement_type': 'contract',
    })
    ok("contract placement without login credentials rejected", r.status_code == 400, r.get_json())

    # ========================================================================
    # 4. All Placements list — separate from Employees, separate from Candidates
    # ========================================================================
    r = client.get('/api/vendors/hires', headers=fh)
    placement_names = [h['candidate_name'] for h in r.get_json()]
    ok("All Placements list contains both direct and contract placements",
       'Direct Placement Person' in placement_names and 'Contract Placement Person' in placement_names, placement_names)

    r = client.get('/api/vendors/hires', headers=fh, query_string={'placement_type': 'contract'})
    ok("filter All Placements by placement_type=contract works",
       all(h['placement_type'] == 'contract' for h in r.get_json()), r.get_json())

    r = client.get('/api/vendors/hires', headers=fh, query_string={'q': 'Direct Placement'})
    ok("search All Placements by candidate name works", len(r.get_json()) == 1, r.get_json())

    r = client.get('/api/vendors/hires/export', headers=fh)
    ok("All Placements CSV export works", r.status_code == 200 and r.content_type.startswith('text/csv'))

    # --- Employees directory must NOT show vendor-placed people ---
    r = client.get('/api/employees', headers=ah)
    emp_names = [e['full_name'] for e in r.get_json()]
    ok("Direct Placement Person never appears in the internal Employees directory",
       'Direct Placement Person' not in emp_names, emp_names)
    ok("Contract Placement Person's internal login DOES appear (by design — tracked, not hidden)",
       'Contract Placement Person' in emp_names, emp_names)

    # ========================================================================
    # 5. Recurring billing for the continuous (contract) placement
    # ========================================================================
    period = date.today().strftime("%Y-%m")
    r = client.post(f'/api/vendors/{vendor_id}/invoices/generate-recurring', headers=fh, json={'period': period})
    ok("recurring invoice generated for continuous placement", r.status_code == 201, r.get_json())
    inv = r.get_json()
    expected_fee = round((600000 / 12) * (8.0 / 100), 2)
    ok("monthly fee computed correctly (CTC/12 x fee%)", inv['subtotal'] == expected_fee, (inv['subtotal'], expected_fee))

    # Billing the SAME period again must not double-charge
    r = client.post(f'/api/vendors/{vendor_id}/invoices/generate-recurring', headers=fh, json={'period': period})
    ok("billing the same period twice is rejected (no double-charge)", r.status_code == 400, r.get_json())

    # The contract hire should still be 'active' (not permanently invoiced like a one-time hire)
    refreshed = VendorHire.query.get(contract_hire['id'])
    ok("continuous placement stays 'active' after billing (bills again next month)", refreshed.status == 'active', refreshed.status)
    ok("last_billed_month recorded correctly", refreshed.last_billed_month == period, refreshed.last_billed_month)

    # --- The one-time direct hire must be completely unaffected by any of this ---
    r = client.post(f'/api/vendors/{vendor_id}/invoices/generate', headers=fh, json={'hire_ids': [direct_hire['id']]})
    ok("one-time invoice still works normally for the direct hire", r.status_code == 201, r.get_json())
    direct_refreshed = VendorHire.query.get(direct_hire['id'])
    ok("direct hire is marked fully invoiced (one-time, never bills again)", direct_refreshed.status == 'invoiced', direct_refreshed.status)

print("\nALL VENDOR-PLACEMENT-FLOW SMOKE TESTS PASSED")
