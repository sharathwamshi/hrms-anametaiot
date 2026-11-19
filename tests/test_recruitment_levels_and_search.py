import sys
sys.path.insert(0, '.')

from config import Config
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True

from app import create_app
from app.extensions import db
from app.models import User, Department, JobPosting, Candidate
from app.roles import HR_OPERATIONS, HR_RECRUITER
from datetime import date

app = create_app(TestConfig)

def ok(label, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label} {extra}")
    if not cond:
        raise SystemExit(f"STOPPED at: {label}")

with app.app_context():
    db.create_all()
    dept = Department(name="Eng"); db.session.add(dept); db.session.flush()

    admin = User(employee_code="A1", full_name="Priya Nair", email="admin@test.com", role=HR_OPERATIONS,
                 department_id=dept.id, date_of_joining=date(2024, 1, 1))
    admin.set_password("pw")
    recruiter = User(employee_code="R1", full_name="Sneha K", email="recruiter@test.com", role=HR_RECRUITER,
                      department_id=dept.id, date_of_joining=date(2024, 1, 1))
    recruiter.set_password("pw")
    db.session.add_all([admin, recruiter]); db.session.commit()

    client = app.test_client()
    def login(email):
        r = client.post('/api/auth/login', json={'email': email, 'password': 'pw'})
        return {'Authorization': f"Bearer {r.get_json()['access_token']}"}
    ah, rh = login('admin@test.com'), login('recruiter@test.com')

    # --- Duplicate employee_code gives a clean message ---
    r = client.post('/api/employees', headers=ah, json={
        'employee_code': 'A1', 'full_name': 'Dup', 'email': 'dup@test.com', 'password': 'pw', 'role': HR_OPERATIONS,
    })
    ok("duplicate employee_code returns 409 with clear message", r.status_code == 409 and "already in use" in r.get_json()['message'], r.get_json())

    # --- Job with interview levels ---
    r = client.post('/api/recruitment/jobs', headers=rh, json={
        'title': 'Backend Engineer', 'department_id': dept.id,
        'interview_levels': 'Screening, Tech L1, Tech L2, HR Round, Offer',
    })
    ok("job created with interview_levels", r.status_code == 201, r.get_json())
    job_id = r.get_json()['id']
    ok("interview_levels parsed into list", r.get_json()['interview_levels'] == ['Screening', 'Tech L1', 'Tech L2', 'HR Round', 'Offer'], r.get_json()['interview_levels'])

    client.post(f'/api/recruitment/jobs/{job_id}/approve', headers=ah)

    # --- Candidates with levels ---
    names = ["Ritika Sharma", "Aman Gupta", "Priyanka Reddy"]
    cand_ids = []
    for i, n in enumerate(names):
        r = client.post('/api/recruitment/candidates', headers=rh, json={
            'job_id': job_id, 'full_name': n, 'email': f"{n.split()[0].lower()}@test.com",
            'phone': f"98000000{i:02d}", 'source': 'linkedin', 'skills': 'Java, SQL',
        })
        if r.status_code != 201:
            print("CANDIDATE CREATE FAILED:", r.status_code, r.get_json())
        cand_ids.append(r.get_json().get('id'))
    ok("3 candidates created", len(cand_ids) == 3)

    # --- Set candidate level ---
    r = client.put(f'/api/recruitment/candidates/{cand_ids[0]}/level', headers=rh, json={'level': 'Tech L1'})
    ok("candidate level set", r.status_code == 200 and r.get_json()['current_level'] == 'Tech L1', r.get_json())

    # Invalid level rejected
    r = client.put(f'/api/recruitment/candidates/{cand_ids[1]}/level', headers=rh, json={'level': 'Not A Real Level'})
    ok("invalid level rejected", r.status_code == 400, r.get_json())

    # --- All-candidates search/sort/filter ---
    r = client.get('/api/recruitment/candidates', headers=rh, query_string={'q': 'ritika'})
    ok("search by name works", r.status_code == 200 and len(r.get_json()) == 1 and r.get_json()[0]['full_name'] == 'Ritika Sharma', r.get_json())

    r = client.get('/api/recruitment/candidates', headers=rh, query_string={'sort': 'name_asc'})
    names_sorted = [c['full_name'] for c in r.get_json()]
    ok("sort by name_asc works", names_sorted == sorted(names_sorted), names_sorted)

    r = client.get('/api/recruitment/candidates', headers=rh, query_string={'job_id': job_id})
    ok("filter by job_id works", len(r.get_json()) == 3, r.get_json())

    # --- Dashboard stats ---
    client.put(f'/api/recruitment/candidates/{cand_ids[0]}/stage', headers=rh, json={'stage': 'screening'})
    r = client.get('/api/recruitment/candidates/dashboard-stats', headers=rh)
    ok("dashboard stats returns today count", r.status_code == 200 and r.get_json()['added_today'] == 3, r.get_json())
    ok("dashboard stats includes recent stage change", len(r.get_json()['recent_stage_changes']) >= 1, r.get_json()['recent_stage_changes'])

    # --- Manager without permission blocked from approving jobs (regression guard) ---
    from app.roles import MANAGER
    mgr = User(employee_code="M1", full_name="Ananya Rao", email="mgr@test.com", role=MANAGER,
               department_id=dept.id, date_of_joining=date(2024, 1, 1))
    mgr.set_password("pw")
    emp = User(employee_code="E1", full_name="Random Employee", email="emp@test.com", role="employee",
               department_id=dept.id, date_of_joining=date(2024, 1, 1))
    emp.set_password("pw")
    db.session.add_all([mgr, emp]); db.session.commit()
    eh = login('emp@test.com')

    r2 = client.post('/api/recruitment/jobs', headers=rh, json={'title': 'QA Engineer', 'department_id': dept.id})
    job2_id = r2.get_json()['id']
    r = client.post(f'/api/recruitment/jobs/{job2_id}/approve', headers=eh)
    ok("plain employee blocked from approving job", r.status_code == 403, r.get_json())

print("\nALL RECRUITMENT-FEATURE SMOKE TESTS PASSED")
