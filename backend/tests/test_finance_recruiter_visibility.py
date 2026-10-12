import sys
sys.path.insert(0, '.')

from config import Config
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True

from app import create_app
from app.extensions import db
from app.models import (User, Department, CompanySettings, Vendor, VendorAgreement,
                        VendorAgreementRole, VendorHire, Candidate, JobPosting)
from app.roles import (HR_OPERATIONS, HR_RECRUITER, FINANCE_ACCOUNTS, MANAGER,
                       EMPLOYEE, CONTRACT_EMPLOYEE)
from datetime import date, timedelta

app = create_app(TestConfig)

def ok(label, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {'' if cond else extra}")
    if not cond:
        raise SystemExit(f"STOPPED at: {label}")

with app.app_context():
    db.create_all()
    db.session.add(CompanySettings(company_name="AnametaIOT", state="Karnataka"))
    dept = Department(name="Eng"); db.session.add(dept); db.session.flush()

    def mk(code, name, email, role, manager_id=None):
        u = User(employee_code=code, full_name=name, email=email, role=role, department_id=dept.id,
                 manager_id=manager_id, date_of_joining=date(2024, 1, 1))
        u.set_password("pw"); db.session.add(u); db.session.flush(); return u

    mgr = mk("M1", "Ananya Rao", "mgr@t.com", MANAGER)
    other_mgr = mk("M2", "Other Manager", "mgr2@t.com", MANAGER)
    admin = mk("A1", "Priya Nair", "admin@t.com", HR_OPERATIONS)
    fin = mk("F1", "Rahul M", "fin@t.com", FINANCE_ACCOUNTS)
    rec1 = mk("R1", "Sneha K", "rec1@t.com", HR_RECRUITER, manager_id=mgr.id)
    rec2 = mk("R2", "Meera K", "rec2@t.com", HR_RECRUITER, manager_id=other_mgr.id)
    emp = mk("E1", "Plain Employee", "emp@t.com", EMPLOYEE)
    db.session.commit()

    client = app.test_client()
    def login(email):
        r = client.post('/api/auth/login', json={'email': email, 'password': 'pw'})
        return {'Authorization': f"Bearer {r.get_json()['access_token']}"}
    H = {n: login(f"{n}@t.com") for n in ("fin", "admin", "rec1", "rec2", "emp", "mgr", "mgr2")}

    # vendors: A (the one we place with) and B (a different client)
    va = Vendor(name="Vendor A", state="Karnataka"); vb = Vendor(name="Vendor B", state="Karnataka")
    db.session.add_all([va, vb]); db.session.flush()
    ag = VendorAgreement(vendor_id=va.id, file_path="/x", effective_from=date(2024, 1, 1), uploaded_by=fin.id)
    db.session.add(ag); db.session.flush()
    role = VendorAgreementRole(agreement_id=ag.id, role_name="Telesales", service_fee_pct=8.0,
                                replacement_days=30, tenure_days=60)
    db.session.add(role); db.session.commit()

    def job(title, rtype, vendor_id, headers):
        body = {'title': title, 'requisition_type': rtype}
        if vendor_id: body['vendor_id'] = vendor_id
        r = client.post('/api/recruitment/jobs', headers=headers, json=body)
        assert r.status_code == 201, r.get_json(); return r.get_json()['id']

    job_a = job("Client A Role", "client", va.id, H['rec1'])
    job_b = job("Client B Role", "client", vb.id, H['rec2'])
    job_int = job("Internal QA", "internal", None, H['rec1'])

    n = [0]
    def cand(job_id, name, headers, stage="hired"):
        n[0] += 1
        r = client.post('/api/recruitment/candidates', headers=headers, json={
            'job_id': job_id, 'full_name': name, 'email': f"c{n[0]}@x.com", 'phone': f"98000{n[0]:05d}"})
        assert r.status_code == 201, r.get_json()
        cid = r.get_json()['id']
        Candidate.query.get(cid).stage = stage; db.session.commit()
        return cid

    c1 = cand(job_a, "Asha (rec1, vendor A)", H['rec1'])
    c2 = cand(job_a, "Bala (rec1, vendor A, still interviewing)", H['rec1'], stage="interview")
    c3 = cand(job_a, "Chitra (rec2, vendor A)", H['rec2'])
    c4 = cand(job_b, "Dev (rec2, vendor B)", H['rec2'])
    c5 = cand(job_int, "Esha (internal)", H['rec1'])
    c6 = cand(job_a, "Farah (added by HR Ops)", H['admin'])

    # ---- 1. Who can see the recruiter overview ---------------------------------------
    r = client.get('/api/recruitment/recruiters', headers=H['fin'])
    ok("Finance can open the recruiter overview", r.status_code == 200, r.get_json())
    ok("recruiter role is blocked from the overview", client.get('/api/recruitment/recruiters', headers=H['rec1']).status_code == 403)
    ok("plain employee is blocked from the overview", client.get('/api/recruitment/recruiters', headers=H['emp']).status_code == 403)
    names = {x['full_name'] for x in r.get_json()['recruiters']}
    ok("overview lists both in-house recruiters", {"Sneha K", "Meera K"} <= names, names)
    ok("HR Ops user who added a candidate is included too (sourcing, not just role)", "Priya Nair" in names, names)

    r = client.get('/api/recruitment/recruiters', headers=H['mgr'])
    ok("a Manager sees only their own direct reports",
       {x['full_name'] for x in r.get_json()['recruiters']} == {"Sneha K"}, r.get_json())

    # ---- 2. Candidate filters Finance needs -------------------------------------------
    r = client.get('/api/recruitment/candidates', headers=H['fin'], query_string={'recruiter_id': rec1.id})
    ok("filter candidates by recruiter", {c['full_name'].split()[0] for c in r.get_json()} == {"Asha", "Bala", "Esha"}, r.get_json())
    ok("candidate rows carry the recruiter's name", all(c['recruiter_name'] == "Sneha K" for c in r.get_json()))
    r = client.get('/api/recruitment/candidates', headers=H['fin'], query_string={'vendor_id': vb.id})
    ok("filter candidates by vendor", [c['full_name'].split()[0] for c in r.get_json()] == ["Dev"], r.get_json())

    # ---- 3. Placement rules ------------------------------------------------------------
    def place(candidate_id, headers=None, **over):
        body = {'vendor_id': va.id, 'agreement_id': ag.id, 'agreement_role_id': role.id,
                'candidate_id': candidate_id, 'candidate_name': 'X', 'ctc': 300000,
                'tenure_start_date': (date.today() - timedelta(days=65)).isoformat()}
        body.update(over)
        return client.post('/api/vendors/hires', headers=headers or H['fin'], json=body)

    ok("cannot place a candidate who is not hired yet", place(c2).status_code == 400)
    r = place(c4)
    ok("cannot place a candidate sourced for a DIFFERENT vendor", r.status_code == 400 and "not sourced for this vendor" in r.get_json()['message'], r.get_json())
    ok("cannot place an internal-requisition candidate with a vendor", place(c5).status_code == 400)

    r = place(c1, candidate_name="Asha")
    ok("hired candidate of this vendor's requisition can be placed", r.status_code == 201, r.get_json())
    h_direct = r.get_json()
    ok("placement is auto-credited to the recruiter who sourced the candidate",
       h_direct['recruiter_id'] == rec1.id and h_direct['recruiter_name'] == "Sneha K", h_direct)
    ok("cannot place the same candidate twice", place(c1).status_code == 409)

    r = client.get('/api/recruitment/candidates', headers=H['fin'], query_string={'vendor_id': va.id, 'unplaced': 'true'})
    left = {c['full_name'].split()[0] for c in r.get_json()}
    ok("'unplaced' filter hides already-placed candidates", "Asha" not in left and "Chitra" in left, left)

    r = place(c3, candidate_name="Chitra", placement_type="contract", contract_login_email="chitra@x.com", contract_login_password="pw")
    ok("contract placement from a candidate works and credits rec2", r.status_code == 201 and r.get_json()['recruiter_id'] == rec2.id, r.get_json())
    h_contract = r.get_json()

    r = client.post('/api/vendors/hires', headers=H['fin'], json={
        'vendor_id': va.id, 'agreement_id': ag.id, 'agreement_role_id': role.id, 'candidate_name': 'Manual Entry',
        'ctc': 200000, 'tenure_start_date': date.today().isoformat()})
    ok("a hand-entered placement (no candidate) is allowed but has no recruiter", r.status_code == 201 and r.get_json()['recruiter_id'] is None, r.get_json())

    r = client.post('/api/vendors/hires', headers=H['fin'], json={
        'vendor_id': va.id, 'agreement_id': ag.id, 'agreement_role_id': role.id, 'candidate_name': 'Manual Two',
        'ctc': 200000, 'tenure_start_date': date.today().isoformat(), 'recruiter_id': rec2.id})
    ok("Finance can credit a hand-entered placement to a recruiter", r.get_json()['recruiter_id'] == rec2.id, r.get_json())
    r = client.post('/api/vendors/hires', headers=H['fin'], json={
        'vendor_id': va.id, 'agreement_id': ag.id, 'agreement_role_id': role.id, 'candidate_name': 'Manual Three',
        'ctc': 200000, 'tenure_start_date': date.today().isoformat(), 'recruiter_id': 99999})
    ok("crediting a non-existent recruiter is rejected", r.status_code == 400, r.get_json())

    # ---- 4. Overview numbers -----------------------------------------------------------
    r = client.get('/api/recruitment/recruiters', headers=H['fin'])
    body = r.get_json()
    by = {x['full_name']: x for x in body['recruiters']}
    s1, s2 = by["Sneha K"], by["Meera K"]
    ok("Sneha: candidates added = 3 (Asha, Bala, Esha)", s1['candidates_added'] == 3, s1)
    ok("Sneha: hired = 2 (Asha, Esha), active pipeline = 1", s1['candidates_hired'] == 2 and s1['candidates_active'] == 1, s1)
    ok("Sneha: 1 placement, direct", s1['placements_total'] == 1 and s1['placements_direct'] == 1 and s1['placements_contract'] == 0, s1)
    ok("Meera: 2 placements (1 contract from a candidate + 1 credited by hand)",
       s2['placements_total'] == 2 and s2['placements_contract'] == 1, s2)
    ok("unattributed placements are counted for Finance", body['unattributed_placements'] == 1, body)

    # fees: generate + approve an invoice for Sneha's direct placement
    r = client.post(f'/api/vendors/{va.id}/invoices/generate', headers=H['fin'], json={'hire_ids': [h_direct['id']]})
    ok("invoice generated for the direct placement", r.status_code == 201, r.get_json())
    inv = r.get_json(); fee = round(300000 * 8 / 100, 2)
    s1 = {x['full_name']: x for x in client.get('/api/recruitment/recruiters', headers=H['fin']).get_json()['recruiters']}["Sneha K"]
    ok("draft invoice shows as fees PENDING for the recruiter", s1['fees_pending'] == fee and s1['fees_billed'] == 0, s1)
    client.post(f"/api/vendors/invoices/{inv['id']}/submit-for-approval", headers=H['fin'])
    client.post(f"/api/vendors/invoices/{inv['id']}/approve", headers=H['admin'])
    s1 = {x['full_name']: x for x in client.get('/api/recruitment/recruiters', headers=H['fin']).get_json()['recruiters']}["Sneha K"]
    ok("approved invoice moves the fee to BILLED", s1['fees_billed'] == fee and s1['fees_pending'] == 0, s1)

    # ---- 5. Filters/exports on placements & recruiters ---------------------------------
    r = client.get('/api/vendors/hires', headers=H['fin'], query_string={'recruiter_id': rec2.id})
    ok("filter placements by recruiter", len(r.get_json()) == 2 and all(h['recruiter_id'] == rec2.id for h in r.get_json()), r.get_json())
    r = client.get('/api/vendors/hires/export', headers=H['fin'], query_string={'recruiter_id': rec1.id})
    ok("placements CSV has a Recruiter column with the name", b"Recruiter" in r.data and b"Sneha K" in r.data and b"Meera K" not in r.data, r.data)
    r = client.get('/api/recruitment/candidates/export', headers=H['fin'], query_string={'recruiter_id': rec1.id})
    ok("candidates CSV has a Recruiter column with the name", b"Recruiter" in r.data and b"Sneha K" in r.data, r.data)
    r = client.get('/api/recruitment/recruiters/export', headers=H['fin'])
    ok("recruiters CSV export works", r.status_code == 200 and b"Sneha K" in r.data and b"Fees Billed" in r.data, r.data)
    ok("recruiters CSV is blocked for a recruiter", client.get('/api/recruitment/recruiters/export', headers=H['rec1']).status_code == 403)

    # ---- 6. A former recruiter must not vanish from Finance's view ---------------------
    User.query.get(rec2.id).is_active = False; db.session.commit()
    r = client.get('/api/recruitment/recruiters', headers=H['fin'])
    m = {x['full_name']: x for x in r.get_json()['recruiters']}
    ok("an inactive recruiter is still listed (their placements/fees still matter), flagged inactive",
       "Meera K" in m and m["Meera K"]['is_active'] is False and m["Meera K"]['placements_total'] == 2, m.get("Meera K"))
    User.query.get(rec2.id).is_active = True; db.session.commit()

    # ---- 7. The internal-employee leak is closed --------------------------------------
    r = client.post(f'/api/employees/convert-candidate/{c6}', headers=H['admin'],
                    json={'employee_code': 'X900', 'password': 'pw', 'role': EMPLOYEE})
    ok("a client-requisition candidate can NOT be converted into an internal employee",
       r.status_code == 400 and "client requisition" in r.get_json()['message'], r.get_json())
    ok("no internal user was created by that attempt", User.query.filter_by(employee_code='X900').first() is None)
    r = client.post(f'/api/employees/convert-candidate/{c5}', headers=H['admin'],
                    json={'employee_code': 'X901', 'password': 'pw', 'role': EMPLOYEE})
    ok("an INTERNAL-requisition candidate still converts normally (existing flow intact)", r.status_code == 201, r.get_json())

    # ---- 8. Replacement keeps the deal --------------------------------------------------
    r = client.post(f"/api/vendors/hires/{h_contract['id']}/replace", headers=H['fin'],
                    json={'candidate_name': 'Contract Replacement', 'ctc': 310000})
    ok("replacing a CONTRACT placement without a login for the new person is rejected", r.status_code == 400, r.get_json())
    r = client.post(f"/api/vendors/hires/{h_contract['id']}/replace", headers=H['fin'],
                    json={'candidate_name': 'Contract Replacement', 'ctc': 310000,
                          'contract_login_email': 'repl@x.com', 'contract_login_password': 'pw'})
    ok("contract replacement created", r.status_code == 201, r.get_json())
    rep = r.get_json()
    ok("replacement stays a contract / monthly placement", rep['placement_type'] == 'contract' and rep['billing_type'] == 'continuous', rep)
    ok("replacement gets its own contract login", rep['employee_id'] and rep['employee_id'] != h_contract['employee_id'], rep)
    ok("replacement stays credited to the original recruiter", rep['recruiter_id'] == rec2.id, rep)
    ok("original is marked replaced", VendorHire.query.get(h_contract['id']).status == 'replaced')
    r = client.post(f"/api/vendors/hires/{h_contract['id']}/replace", headers=H['fin'], json={'candidate_name': 'Again'})
    ok("an already-replaced placement cannot be replaced twice", r.status_code == 400, r.get_json())
    r = client.post(f"/api/vendors/hires/{h_direct['id']}/replace", headers=H['fin'], json={'candidate_name': 'After-billing swap', 'ctc': 300000})
    ok("an INVOICED placement can still be replaced (replacement guarantee)", r.status_code == 201, r.get_json())

    # ---- 9. Regression: the recurring-billing marker endpoint exists and works ---------
    period = date.today().strftime("%Y-%m")
    r = client.post(f"/api/vendors/hires/{rep['id']}/bill-recurring", headers=H['fin'], json={'period': period})
    ok("bill-recurring marks a continuous placement as billed for the month", r.status_code == 200 and r.get_json()['last_billed_month'] == period, r.get_json())
    r = client.post(f"/api/vendors/hires/{rep['id']}/bill-recurring", headers=H['fin'], json={'period': period})
    ok("...and refuses to bill the same month twice", r.status_code == 400, r.get_json())

print("\nALL FINANCE / RECRUITER VISIBILITY SMOKE TESTS PASSED")
