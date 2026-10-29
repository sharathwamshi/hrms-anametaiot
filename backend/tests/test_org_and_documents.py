import sys, io
sys.path.insert(0, '.')

from config import Config
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

from app import create_app
from app.extensions import db
from app.models import User, Department, MockTestTemplate
from app.roles import MANAGER, HR_OPERATIONS, HR_RECRUITER, EMPLOYEE, CONTRACT_EMPLOYEE
from datetime import date

app = create_app(TestConfig)

def ok(label, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label} {extra}")
    if not cond:
        raise SystemExit(f"STOPPED at: {label}")

with app.app_context():
    db.create_all()

    dept = Department(name="Engineering")
    db.session.add(dept); db.session.flush()

    mgr = User(employee_code="M1", full_name="Ananya Rao", email="mgr@test.com",
               role=MANAGER, department_id=dept.id, date_of_joining=date(2024,1,1))
    mgr.set_password("pw")
    db.session.add(mgr); db.session.flush()

    contractor = User(employee_code="C1", full_name="Vikram S", email="contract@test.com",
                       role=CONTRACT_EMPLOYEE, department_id=dept.id, manager_id=mgr.id,
                       date_of_joining=date(2024,1,1))
    contractor.set_password("pw")
    db.session.add(contractor); db.session.commit()

    client = app.test_client()

    def login(email):
        r = client.post('/api/auth/login', json={'email': email, 'password': 'pw'})
        ok(f"login {email}", r.status_code == 200)
        return {'Authorization': f"Bearer {r.get_json()['access_token']}"}

    mh = login('mgr@test.com')
    ch = login('contract@test.com')

    # --- Manager can onboard a direct report ---
    r = client.post('/api/employees', headers=mh, json={
        'employee_code': 'E2', 'full_name': 'New Hire', 'email': 'newhire@test.com',
        'password': 'pw', 'role': EMPLOYEE, 'manager_id': 999,  # should be ignored/forced
    })
    ok("manager creates employee", r.status_code == 201, r.get_json())
    ok("manager_id forced to the creating manager", r.get_json()['manager_id'] == mgr.id, r.get_json())
    new_hire_id = r.get_json()['id']

    # --- Manager can edit own report's role, not others ---
    r = client.put(f'/api/employees/{new_hire_id}', headers=mh, json={'role': HR_RECRUITER, 'designation': 'Recruiter'})
    ok("manager edits own report's role", r.status_code == 200 and r.get_json()['role'] == HR_RECRUITER, r.get_json())

    outsider = User(employee_code="O1", full_name="Outsider", email="outsider@test.com",
                     role=EMPLOYEE, department_id=dept.id, date_of_joining=date(2024,1,1))
    outsider.set_password("pw")
    db.session.add(outsider); db.session.commit()
    r = client.put(f'/api/employees/{outsider.id}', headers=mh, json={'role': MANAGER})
    ok("manager CANNOT edit a non-report", r.status_code == 403, r.get_json())

    # --- Contract Employee blocked from leave ---
    r = client.post('/api/leave/apply', headers=ch, json={
        'leave_type_id': 1, 'start_date': '2026-09-01', 'end_date': '2026-09-02',
    })
    ok("contract employee blocked from applying leave", r.status_code == 403, r.get_json())

    # --- Documents: contract employee uploads their own ---
    data = {'doc_type': 'academic', 'title': 'B.Tech Certificate'}
    data['file'] = (io.BytesIO(b'%PDF-1.4\n% test document\n'), 'degree.pdf')
    r = client.post('/api/documents', headers=ch, data=data, content_type='multipart/form-data')
    ok("contract employee uploads a document", r.status_code == 201, r.get_json())

    r = client.get('/api/documents', headers=ch)
    ok("contract employee sees own documents", r.status_code == 200 and len(r.get_json()) == 1, r.get_json())

    # Manager (their own manager) can view the contractor's documents
    r = client.get('/api/documents', headers=mh, query_string={'user_id': contractor.id})
    ok("manager views own report's documents", r.status_code == 200 and len(r.get_json()) == 1, r.get_json())

    # A different manager should NOT be able to view (simulate via outsider, who has no reports)
    oh = login('outsider@test.com')
    r = client.get('/api/documents', headers=oh, query_string={'user_id': contractor.id})
    ok("non-manager cannot view someone else's documents", r.status_code == 403, r.get_json())

    # --- Candidate skills ---
    job = client.post('/api/recruitment/jobs', headers=mh, json={'title': 'Java Developer', 'department_id': dept.id})
    # manager isn't a recruiter, so this should fail — use recruiter instead
    recruiter = User.query.filter_by(role=HR_RECRUITER).first()
    rh = login('newhire@test.com')  # this user's role was changed to hr_recruiter above
    r = client.post('/api/recruitment/jobs', headers=rh, json={'title': 'Java Developer', 'department_id': dept.id})
    ok("recruiter creates job", r.status_code == 201, r.get_json())
    job_id = r.get_json()['id']

    r = client.post('/api/recruitment/candidates', headers=rh, json={
        'job_id': job_id, 'full_name': 'Skilled Dev', 'email': 'dev@test.com', 'phone': '9876543210',
        'source': 'referral', 'skills': 'Java, Spring Boot, SQL, Docker',
    })
    ok("candidate created with skills", r.status_code == 201, r.get_json())
    ok("skills parsed into a list", r.get_json()['skills'] == ['Java', 'Spring Boot', 'SQL', 'Docker'], r.get_json()['skills'])

    # --- Java question bank exists in DB after seeding logic pattern ---
    # (seed.py itself seeds this; here we just verify the model/route can serve a manually created one)
    template = MockTestTemplate(title="Java Fundamentals — 100 Questions", topics="Java", complexity="medium",
                                 duration_minutes=60, passing_threshold_pct=60, created_by=recruiter.id if recruiter else None)
    db.session.add(template); db.session.commit()
    r = client.get('/api/mocktest/templates', headers=rh)
    ok("mock test templates listable", r.status_code == 200 and any(t['title'].startswith('Java Fundamentals') for t in r.get_json()))

print("\nALL ORG-MODEL / DOCUMENTS / SKILLS SMOKE TESTS PASSED")
