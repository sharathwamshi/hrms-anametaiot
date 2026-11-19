import sys, io, json
sys.path.insert(0, '.')

from config import Config
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

from app import create_app
from app.extensions import db
from app.models import User, Department, JobPosting, Candidate
from app.roles import MANAGER, HR_OPERATIONS, HR_RECRUITER, EMPLOYEE
from datetime import date, timedelta, datetime

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

    admin = User(employee_code="A1", full_name="Priya Nair", email="admin@test.com",
                 role=HR_OPERATIONS, department_id=dept.id, date_of_joining=date(2024,1,1))
    admin.set_password("pw")
    db.session.add(admin); db.session.flush()

    recruiter = User(employee_code="R1", full_name="Sneha K", email="recruiter@test.com",
                      role=HR_RECRUITER, department_id=dept.id, manager_id=mgr.id,
                      date_of_joining=date(2024,1,1), revalidation_interval_days=60)
    recruiter.set_password("pw")
    db.session.add(recruiter); db.session.commit()

    client = app.test_client()

    def login(email):
        r = client.post('/api/auth/login', json={'email': email, 'password': 'pw'})
        ok(f"login {email}", r.status_code == 200, r.get_json())
        return {'Authorization': f"Bearer {r.get_json()['access_token']}"}

    rh = login('recruiter@test.com')
    mh = login('mgr@test.com')
    ah = login('admin@test.com')

    # --- Job requisition & approval ---
    r = client.post('/api/recruitment/jobs', headers=rh, json={
        'title': 'Backend Engineer', 'department_id': dept.id, 'openings': 2,
        'salary_min': 800000, 'salary_max': 1200000, 'priority': 'urgent',
    })
    ok("create job (recruiter)", r.status_code == 201, r.get_json())
    job_id = r.get_json()['id']
    ok("job starts pending_approval", r.get_json()['requisition_status'] == 'pending_approval')

    r = client.post(f'/api/recruitment/jobs/{job_id}/approve', headers=mh)
    ok("manager approves job", r.status_code == 200 and r.get_json()['requisition_status'] == 'open')

    r = client.post(f'/api/recruitment/jobs/{job_id}/generate-post-image', headers=rh, json={})
    ok("generate post image", r.status_code == 200 and r.get_json().get('post_image_url'), r.get_json())

    r = client.post(f'/api/recruitment/jobs/{job_id}/post-social', headers=rh)
    ok("social post stub responds", r.status_code == 200, r.get_json())
    ok("linkedin flagged not_configured", r.get_json()['linkedin']['status'] == 'not_configured')

    # --- Candidate add + duplicate detection ---
    r = client.post('/api/recruitment/candidates', headers=rh, json={
        'job_id': job_id, 'full_name': 'Arjun Das', 'email': 'arjun@test.com',
        'phone': '+91 98765 43210', 'source': 'referral',
    })
    ok("add candidate 1", r.status_code == 201, r.get_json())
    cand1_id = r.get_json()['id']
    ok("auto-validation flags no resume", r.get_json()['validation_status'] == 'needs_review', r.get_json()['validation_notes'])

    r = client.post('/api/recruitment/candidates', headers=rh, json={
        'job_id': job_id, 'full_name': 'Arjun D.', 'email': 'ARJUN@test.com',
        'phone': '9876543210', 'source': 'linkedin',
    })
    ok("duplicate blocked with 409", r.status_code == 409, r.get_json())

    r = client.post('/api/recruitment/candidates', headers=rh, json={
        'job_id': job_id, 'full_name': 'Arjun D.', 'email': 'ARJUN@test.com',
        'phone': '9876543210', 'source': 'linkedin', 'duplicate_action': 'link_new_application',
    })
    ok("duplicate linked when explicitly confirmed", r.status_code == 201 and r.get_json()['duplicate_of_candidate_id'] == cand1_id)

    # --- Bulk import preview + confirm ---
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(['name', 'email', 'phone', 'job', 'source'])
    ws.append(['Kiran M', 'kiran@test.com', '9123456780', str(job_id), 'naukri'])
    ws.append(['Bad Row', 'not-an-email', '123', str(job_id), 'walk-in'])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)

    r = client.post('/api/recruitment/candidates/bulk-import/preview', headers=rh,
                     data={'file': (buf, 'candidates.xlsx')}, content_type='multipart/form-data')
    ok("bulk preview runs", r.status_code == 200, r.get_json())
    preview = r.get_json()
    ok("bulk preview: 1 valid, 1 flagged", preview['summary']['valid'] == 1 and preview['summary']['flagged'] == 1, preview['summary'])

    r = client.post('/api/recruitment/candidates/bulk-import/confirm', headers=rh, json={
        'rows': preview['valid_rows']
    })
    ok("bulk confirm creates candidate", r.status_code == 201 and len(r.get_json()) == 1, r.get_json())

    # --- Verification: self-verify rights gate ---
    r = client.post(f'/api/recruitment/candidates/{cand1_id}/verify', headers=rh)
    ok("recruiter cannot self-verify by default", r.status_code == 403, r.get_json())

    r = client.post(f'/api/recruitment/candidates/{cand1_id}/verify', headers=mh)
    ok("manager can verify", r.status_code == 200, r.get_json())
    ok("next_revalidation_due set", r.get_json()['next_revalidation_due'] is not None)

    r = client.post(f'/api/recruitment/candidates/{cand1_id}/verify', headers=mh)
    ok("re-verify blocked before interval elapses", r.status_code == 400, r.get_json())

    r = client.post(f'/api/recruitment/recruiters/{recruiter.id}/self-verify', headers=mh, json={'rights': True})
    ok("manager grants self-verify rights", r.status_code == 200 and r.get_json()['self_verify_rights'] is True)

    r = client.post(f'/api/recruitment/recruiters/{recruiter.id}/self-verify', headers=ah, json={'rights': True})
    ok("admin CANNOT grant self-verify rights (manager-only)", r.status_code == 403, r.get_json())

    # --- Screening call (simulated, no Twilio configured) ---
    r = client.post(f'/api/screening/candidates/{cand1_id}/trigger-call', headers=rh)
    ok("screening call triggers (simulated)", r.status_code == 201, r.get_json())
    ok("call has an outcome", r.get_json()['outcome'] in ('yes', 'no', 'neutral'), r.get_json()['outcome'])

    cand = Candidate.query.get(cand1_id)
    print(f"      -> candidate stage after screening: {cand.stage}, outcome: {r.get_json()['outcome']}")

    # Force candidate into mock_test stage regardless of simulated outcome, to test that flow
    cand.stage = 'mock_test'
    db.session.commit()

    # --- Mock test: template, assign, take, submit, rank, retest ---
    r = client.post('/api/mocktest/templates', headers=rh, json={
        'title': 'Java Basics', 'job_id': job_id, 'topics': 'Java,OOP',
        'complexity': 'medium', 'duration_minutes': 20, 'passing_threshold_pct': 50,
        'questions': [
            {'question_text': '2+2=?', 'question_type': 'mcq', 'options': ['3','4'], 'correct_answer': '4', 'marks': 1, 'topic': 'Java'},
            {'question_text': 'Explain polymorphism.', 'question_type': 'subjective', 'marks': 4, 'topic': 'OOP'},
        ],
    })
    ok("create mock test template", r.status_code == 201, r.get_json())
    template_id = r.get_json()['id']

    window_start = datetime.utcnow().strftime('%Y-%m-%dT%H:%M')
    window_end = (datetime.utcnow() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
    r = client.post('/api/mocktest/assign', headers=rh, json={
        'template_id': template_id, 'candidate_ids': [cand1_id],
        'window_start': window_start, 'window_end': window_end,
    })
    ok("assign mock test", r.status_code == 201, r.get_json())
    token = r.get_json()[0]['access_token']

    r = client.get(f'/api/mocktest/take/{token}')
    ok("candidate can fetch test via public token", r.status_code == 200, r.get_json())
    questions = r.get_json()['questions']

    r = client.post(f'/api/mocktest/take/{token}/start')
    ok("candidate starts test", r.status_code == 200)

    r = client.post(f'/api/mocktest/take/{token}/submit', json={
        'answers': [
            {'question_id': questions[0]['id'], 'answer_text': '4'},
            {'question_id': questions[1]['id'], 'answer_text': 'Polymorphism means many forms, e.g. method overriding lets a subclass change behavior.'},
        ]
    })
    ok("submit & auto-grade", r.status_code == 200, r.get_json())
    ok("percentage computed", r.get_json()['percentage'] > 0, r.get_json())

    r = client.get(f'/api/mocktest/templates/{template_id}/rankings', headers=rh)
    ok("rankings computed", r.status_code == 200 and len(r.get_json()) == 1, r.get_json())

    assignment_id = client.get('/api/mocktest/assignments', headers=rh).get_json()[0]['id']
    r = client.post(f'/api/mocktest/assignments/{assignment_id}/retest', headers=rh, json={
        'window_start': window_start, 'window_end': window_end,
    })
    ok("retest assignment created (recruiter-only)", r.status_code == 201 and r.get_json()['attempt_number'] == 2, r.get_json())

    # --- Interview: panel + conflict check ---
    interview_time = (datetime.utcnow() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
    r = client.post(f'/api/recruitment/candidates/{cand1_id}/interviews', headers=rh, json={
        'scheduled_at': interview_time, 'round_name': 'Technical', 'interviewer_ids': [mgr.id],
    })
    ok("schedule panel interview", r.status_code == 201, r.get_json())
    interview_id = r.get_json()['id']
    ok("panelist attached", len(r.get_json()['panelists']) == 1)

    r = client.post(f'/api/recruitment/interviews/{interview_id}/reschedule', headers=rh, json={
        'scheduled_at': interview_time, 'reason': 'Interviewer unavailable'
    })
    ok("reschedule with reason", r.status_code == 200 and r.get_json()['status'] == 'rescheduled')

    # --- Offer: draft -> approve -> send -> accept ---
    cand.stage = 'hired'  # simulate having cleared interview already, per earlier stage tests
    db.session.commit()
    r = client.post('/api/offers', headers=rh, json={
        'candidate_id': cand1_id, 'designation': 'Backend Engineer', 'salary': 1000000,
        'joining_date': '2026-09-01',
    })
    ok("draft offer", r.status_code == 201, r.get_json())
    offer_id = r.get_json()['id']

    r = client.post(f'/api/offers/{offer_id}/approve', headers=mh)
    ok("manager approves offer", r.status_code == 200 and r.get_json()['status'] == 'approved')

    r = client.post(f'/api/offers/{offer_id}/send', headers=rh)
    ok("send offer", r.status_code == 200 and r.get_json()['status'] == 'sent')

    r = client.post(f'/api/offers/{offer_id}/respond', headers=rh, json={'response': 'accepted'})
    ok("candidate accepts offer", r.status_code == 200 and r.get_json()['status'] == 'accepted')

    cand = Candidate.query.get(cand1_id)
    ok("candidate stage -> hired on accept", cand.stage == 'hired')

    # --- Hire -> Employee handoff ---
    r = client.post(f'/api/employees/convert-candidate/{cand1_id}', headers=rh, json={
        'employee_code': 'EMP-9001', 'password': 'Welcome@123', 'role': EMPLOYEE, 'manager_id': mgr.id,
    })
    ok("convert candidate to employee", r.status_code == 201, r.get_json())
    ok("employee designation prefilled from offer", r.get_json()['designation'] == 'Backend Engineer')

    r = client.post(f'/api/employees/convert-candidate/{cand1_id}', headers=rh, json={
        'employee_code': 'EMP-9002', 'password': 'x', 'role': EMPLOYEE,
    })
    ok("cannot convert same candidate twice", r.status_code == 400, r.get_json())

    # --- Recruiter performance dashboard ---
    r = client.get(f'/api/dashboard/recruiter-performance/{recruiter.id}', headers=mh)
    ok("manager views recruiter performance", r.status_code == 200, r.get_json())
    ok("candidates_added counted", r.get_json()['candidates_added'] >= 2, r.get_json())

    r = client.get(f'/api/dashboard/recruiter-performance/{recruiter.id}', headers=rh)
    ok("recruiter CANNOT view own performance dashboard (manager/admin only)", r.status_code == 403)

    # --- Audit trail sanity ---
    r = client.get(f'/api/recruitment/candidates/{cand1_id}', headers=rh)
    audit = r.get_json()['audit_log']
    ok("audit trail has multiple entries", len(audit) >= 5, f"{len(audit)} entries")
    print("      audit actions:", [a['action'] for a in audit])

print("\nALL SMOKE TESTS PASSED")
