import sys
sys.path.insert(0, '.')

from config import Config
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True

from app import create_app
from app.extensions import db
from app.models import (
    User, Department, CompanySettings, Attendance, AttendanceRegularizationRequest,
    SalaryStructure,
)
from app.roles import HR_OPERATIONS, HR_RECRUITER, MANAGER, EMPLOYEE, CONTRACT_EMPLOYEE
from datetime import date, datetime, timedelta

app = create_app(TestConfig)

def ok(label, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {'' if cond else extra}")
    if not cond:
        raise SystemExit(f"STOPPED at: {label}")

with app.app_context():
    db.create_all()
    db.session.add(CompanySettings(company_name="AnametaIOT", state="Karnataka"))
    dept = Department(name="Eng"); db.session.add(dept); db.session.flush()

    def mk(code, email, name, role, manager_id=None):
        u = User(employee_code=code, full_name=name, email=email, role=role,
                 department_id=dept.id, manager_id=manager_id, date_of_joining=date(2024, 1, 1))
        u.set_password("pw"); db.session.add(u); db.session.flush(); return u

    mgr = mk("M1", "mgr@t.com", "Ananya Manager", MANAGER)
    other_mgr = mk("M2", "mgr2@t.com", "Other Manager", MANAGER)
    admin = mk("A1", "admin@t.com", "Priya Ops", HR_OPERATIONS)
    rec1 = mk("R1", "rec1@t.com", "Sneha Recruiter", HR_RECRUITER, manager_id=mgr.id)
    rec2 = mk("R2", "rec2@t.com", "Meera Recruiter", HR_RECRUITER, manager_id=other_mgr.id)
    con = mk("C1", "con@t.com", "Chitra Contract", CONTRACT_EMPLOYEE)
    db.session.commit()

    client = app.test_client()
    def login(email):
        r = client.post('/api/auth/login', json={'email': email, 'password': 'pw'})
        return {'Authorization': f"Bearer {r.get_json()['access_token']}"}
    H = {n: login(f"{n}@t.com") for n in ("mgr", "mgr2", "admin", "rec1", "rec2", "con")}

    # ---- 1. Reason rules ("manager gonna add the rules") -------------------------------
    ok("recruiter cannot define a reason rule", client.post('/api/attendance/regularization-reasons', headers=H['rec1'], json={'label': 'x'}).status_code == 403)
    r = client.post('/api/attendance/regularization-reasons', headers=H['mgr'], json={'label': 'Forgot to clock in', 'description': 'Punched late by mistake'})
    ok("manager can add a reason rule", r.status_code == 201, r.get_json())
    reason1 = r.get_json()
    r = client.post('/api/attendance/regularization-reasons', headers=H['admin'], json={'label': 'Field visit / on-site'})
    ok("HR Operations can also add a reason rule", r.status_code == 201, r.get_json())
    reason2 = r.get_json()
    ok("duplicate label is rejected", client.post('/api/attendance/regularization-reasons', headers=H['mgr'], json={'label': 'Forgot to clock in'}).status_code == 409)
    ok("everyone (a recruiter) can list the reasons", client.get('/api/attendance/regularization-reasons', headers=H['rec1']).status_code == 200)
    reasons = client.get('/api/attendance/regularization-reasons', headers=H['rec1']).get_json()
    ok("both reasons are visible", {r['label'] for r in reasons} == {"Forgot to clock in", "Field visit / on-site"}, reasons)

    r = client.put(f"/api/attendance/regularization-reasons/{reason2['id']}", headers=H['mgr'], json={'is_active': False})
    ok("manager can retire a reason", r.status_code == 200 and r.get_json()['is_active'] is False, r.get_json())
    active = client.get('/api/attendance/regularization-reasons', headers=H['rec1']).get_json()
    ok("retired reason no longer offered by default", {r['label'] for r in active} == {"Forgot to clock in"}, active)

    # ---- 2. Recruiter sees their own attendance ------------------------------------------
    missed_day = (date.today() - timedelta(days=2)).isoformat()
    r = client.get('/api/attendance/history', headers=H['rec1'])
    ok("recruiter can see their own attendance history", r.status_code == 200, r.get_json())

    # ---- 3. Self-service regularization request ------------------------------------------
    r = client.post('/api/attendance/regularize-request', headers=H['rec1'], json={'work_date': missed_day, 'reason_id': 99999, 'note': 'x'})
    ok("an invalid/retired reason is rejected", r.status_code == 400, r.get_json())
    r = client.post('/api/attendance/regularize-request', headers=H['rec1'], json={'work_date': missed_day, 'reason_id': reason1['id'], 'note': 'Forgot to punch in before the client call'})
    ok("recruiter can request regularization with a valid reason", r.status_code == 201, r.get_json())
    req1 = r.get_json()
    ok("request auto-creates the day's record as pending", req1['regularization_status'] == 'pending' and req1['regularization_reason_label'] == 'Forgot to clock in', req1)
    ok("request date is generated automatically", req1['regularization_request_date'] == date.today().isoformat(), req1.get('regularization_request_date'))
    r = client.post('/api/attendance/regularize-request', headers=H['rec1'], json={'work_date': missed_day, 'reason_id': reason1['id']})
    ok("cannot submit a second request while one is pending", r.status_code == 409, r.get_json())
    quota = client.get('/api/attendance/regularization-limit', headers=H['rec1']).get_json()
    ok("first request leaves four of five monthly submissions", quota == {'limit': 5, 'used': 1, 'remaining': 4}, quota)

    current_month_start = datetime(date.today().year, date.today().month, 1)
    previous_month = current_month_start - timedelta(days=1)
    db.session.add(AttendanceRegularizationRequest(
        user_id=rec1.id,
        attendance_id=req1['id'],
        submitted_at=datetime(previous_month.year, previous_month.month, previous_month.day, 12),
    ))
    for _ in range(4):
        db.session.add(AttendanceRegularizationRequest(
            user_id=rec1.id,
            attendance_id=req1['id'],
            submitted_at=current_month_start.replace(hour=12),
        ))
    db.session.commit()
    quota = client.get('/api/attendance/regularization-limit', headers=H['rec1']).get_json()
    ok("monthly quota excludes the previous month and stops at zero", quota == {'limit': 5, 'used': 5, 'remaining': 0}, quota)
    r = client.post('/api/attendance/regularize-request', headers=H['rec1'], json={
        'work_date': date.today().isoformat(), 'reason_id': reason1['id'],
    })
    ok("a sixth monthly request is rejected with the limit message",
       r.status_code == 429 and r.get_json()['message'] == "your limit is exceeded please contact your manager", r.get_json())

    future = (date.today() + timedelta(days=3)).isoformat()
    r = client.post('/api/attendance/regularize-request', headers=H['rec1'], json={'work_date': future, 'reason_id': reason1['id']})
    ok("cannot request regularization for a future date", r.status_code == 400, r.get_json())

    day2 = (date.today() - timedelta(days=5)).isoformat()
    client.post('/api/attendance/regularize-request', headers=H['rec2'], json={'work_date': day2, 'reason_id': reason1['id'], 'note': 'System was down'})

    # ---- 4. Manager scoping on the review queue --------------------------------------------
    r = client.get('/api/attendance/regularization-requests', headers=H['rec1'])
    ok("a recruiter cannot open the review queue", r.status_code == 403, r.get_json())
    r = client.get('/api/attendance/regularization-requests', headers=H['mgr'])
    names = {x['employee_name'] for x in r.get_json()}
    ok("a manager sees only their own report's pending request", names == {"Sneha Recruiter"}, names)
    r = client.get('/api/attendance/regularization-requests', headers=H['mgr2'])
    ok("the other manager sees only their own report", {x['employee_name'] for x in r.get_json()} == {"Meera Recruiter"}, r.get_json())
    r = client.get('/api/attendance/regularization-requests', headers=H['admin'])
    ok("HR Operations sees every pending request", {x['employee_name'] for x in r.get_json()} == {"Sneha Recruiter", "Meera Recruiter"}, r.get_json())

    # ---- 5. Approve / reject ------------------------------------------------------------
    r = client.post(f"/api/attendance/regularization-requests/{req1['id']}/approve", headers=H['mgr2'])
    ok("a DIFFERENT manager cannot approve someone else's report's request", r.status_code == 403, r.get_json())
    r = client.post(f"/api/attendance/regularization-requests/{req1['id']}/approve", headers=H['mgr'], json={'comment': 'Confirmed with client call log'})
    ok("the correct manager can approve", r.status_code == 200 and r.get_json()['regularization_status'] == 'approved', r.get_json())
    ok("approving sets is_regularized + status", r.get_json()['is_regularized'] is True and r.get_json()['status'] == 'regularized', r.get_json())
    r = client.post(f"/api/attendance/regularization-requests/{req1['id']}/approve", headers=H['mgr'])
    ok("cannot approve an already-decided request", r.status_code == 400, r.get_json())
    r = client.get('/api/attendance/history', headers=H['rec1'])
    row = next(x for x in r.get_json() if x['work_date'] == missed_day)
    ok("recruiter's own history reflects the approval", row['regularization_status'] == 'approved' and row['regularization_reviewed_by_name'] == 'Ananya Manager', row)
    approved_history = client.get(
        '/api/attendance/regularization-requests',
        headers=H['mgr'],
        query_string={'status': 'all'},
    )
    ok("approved requests remain in the review history",
       approved_history.status_code == 200 and
       any(item['id'] == req1['id'] and item['regularization_status'] == 'approved'
           for item in approved_history.get_json()),
       approved_history.get_json())
    ok("status filter returns only approved requests",
       all(item['regularization_status'] == 'approved' for item in
           client.get('/api/attendance/regularization-requests', headers=H['mgr'],
                      query_string={'status': 'approved'}).get_json()))
    ok("invalid regularization status is rejected",
       client.get('/api/attendance/regularization-requests', headers=H['mgr'],
                  query_string={'status': 'unknown'}).status_code == 400)

    r = client.get('/api/attendance/regularization-requests', headers=H['mgr2'])
    pending2 = r.get_json()[0]
    r = client.post(f"/api/attendance/regularization-requests/{pending2['id']}/reject", headers=H['mgr2'], json={})
    ok("rejecting without a comment is refused", r.status_code == 400, r.get_json())
    r = client.post(f"/api/attendance/regularization-requests/{pending2['id']}/reject", headers=H['mgr2'], json={'comment': 'No record of a system outage that day'})
    ok("rejecting with a comment works", r.status_code == 200 and r.get_json()['regularization_status'] == 'rejected', r.get_json())
    ok("a rejected request is NOT regularized", r.get_json()['is_regularized'] is False, r.get_json())
    rejected_history = client.get(
        '/api/attendance/regularization-requests',
        headers=H['mgr2'],
        query_string={'status': 'all'},
    )
    ok("rejected requests remain in the review history",
       rejected_history.status_code == 200 and
       any(item['id'] == pending2['id'] and item['regularization_status'] == 'rejected'
           for item in rejected_history.get_json()),
       rejected_history.get_json())

    # ---- 6. Holiday calendar ("manager adds holidays ... everyone sees it") ------------------
    ok("recruiter cannot add a holiday", client.post('/api/attendance/holidays', headers=H['rec1'], json={'name': 'x', 'holiday_date': '2026-10-02'}).status_code == 403)
    r = client.post('/api/attendance/holidays', headers=H['admin'], json={'name': 'Gandhi Jayanti', 'holiday_date': '2026-10-02'})
    ok("HR Operations can add a holiday", r.status_code == 201, r.get_json())
    hol = r.get_json()
    r = client.post('/api/attendance/holidays', headers=H['mgr'], json={'name': 'Diwali', 'holiday_date': '2026-11-08'})
    ok("manager can also add a holiday", r.status_code == 201, r.get_json())
    r = client.post('/api/attendance/holidays', headers=H['admin'], json={'name': 'Duplicate', 'holiday_date': '2026-10-02'})
    ok("cannot double-book the same date", r.status_code == 409, r.get_json())

    r = client.get('/api/attendance/holidays', headers=H['rec1'], query_string={'year': 2026})
    holidays = r.get_json()
    ok("everyone, including a recruiter, can see the holiday calendar", {h['name'] for h in holidays} == {"Gandhi Jayanti", "Diwali"}, holidays)

    r = client.put(f"/api/attendance/holidays/{hol['id']}", headers=H['mgr'], json={'name': 'Gandhi Jayanti (National Holiday)'})
    ok("a holiday can be edited by either manager or HR Ops", r.status_code == 200 and 'National' in r.get_json()['name'], r.get_json())
    r = client.delete(f"/api/attendance/holidays/{hol['id']}", headers=H['rec1'])
    ok("a recruiter cannot delete a holiday", r.status_code == 403, r.get_json())
    r = client.delete(f"/api/attendance/holidays/{hol['id']}", headers=H['admin'])
    ok("HR Operations can delete a holiday", r.status_code == 200, r.get_json())

    # ---- 7. Holidays reduce loss-of-pay in payroll --------------------------------------
    db.session.add(SalaryStructure(user_id=rec1.id, basic=50000))
    db.session.commit()
    client.post('/api/attendance/holidays', headers=H['admin'], json={'name': 'Company Day', 'holiday_date': '2026-06-15'})
    g = client.post('/api/payroll/generate', headers=H['admin'], json={'month': 6, 'year': 2026})
    ok("payroll generation succeeds with a holiday in the month", g.status_code == 200, g.get_json())
    slip = next(p for p in g.get_json() if p['user_id'] == rec1.id)
    ok("the holiday is not counted as a loss-of-pay day (LOP < days_in_month - present)", slip['lop_days'] < 30, slip)

print("\nALL ATTENDANCE REGULARIZATION / HOLIDAY SMOKE TESTS PASSED")
