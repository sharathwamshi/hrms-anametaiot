import sys
sys.path.insert(0, '.')

from config import Config
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True

from app import create_app
from app.extensions import db
from app.models import (User, Department, CompanySettings, Attendance, SalaryStructure, Payslip,
                        LeaveRequest, LeaveType, DeviceToken)
from app.roles import HR_OPERATIONS, HR_RECRUITER, MANAGER, EMPLOYEE, FINANCE_ACCOUNTS
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
        u = User(employee_code=code, full_name=name, email=email, role=role, department_id=dept.id,
                 manager_id=manager_id, date_of_joining=date(2024, 1, 1))
        u.set_password("pw"); db.session.add(u); db.session.flush(); return u

    mgr = mk("M1", "mgr@t.com", "Ananya Manager", MANAGER)
    mgr2 = mk("M2", "mgr2@t.com", "Other Manager", MANAGER)
    admin = mk("A1", "admin@t.com", "Priya Ops", HR_OPERATIONS)
    fin = mk("F1", "fin@t.com", "Rahul Finance", FINANCE_ACCOUNTS)
    r1 = mk("R1", "r1@t.com", "Sneha Recruiter", HR_RECRUITER, manager_id=mgr.id)
    r2 = mk("R2", "r2@t.com", "Meera Recruiter", HR_RECRUITER, manager_id=mgr.id)
    r3 = mk("R3", "r3@t.com", "Kiran Employee", EMPLOYEE, manager_id=mgr.id)
    r4 = mk("R4", "r4@t.com", "Dev Employee", EMPLOYEE, manager_id=mgr.id)
    outsider = mk("R5", "r5@t.com", "Not Mine", EMPLOYEE, manager_id=mgr2.id)
    submgr = mk("S1", "sub@t.com", "Sub Manager", MANAGER, manager_id=mgr.id)
    subrep = mk("S2", "subrep@t.com", "Sub Report", EMPLOYEE, manager_id=submgr.id)
    ops_report = mk("A2", "ops2@t.com", "Second Ops", HR_OPERATIONS, manager_id=mgr.id)
    lt = LeaveType(name="Casual Leave", annual_quota=12); db.session.add(lt); db.session.flush()
    db.session.commit()

    c = app.test_client()
    def login(e):
        r = c.post('/api/auth/login', json={'email': e, 'password': 'pw'})
        return r, ({'Authorization': 'Bearer ' + r.get_json()['access_token']} if r.status_code == 200 else None)
    H = {n: login(f"{n}@t.com")[1] for n in ("mgr", "mgr2", "admin", "fin", "r1", "r2", "r3", "r4", "r5", "sub", "ops2")}
    refresh = {n: c.post('/api/auth/login', json={'email': f'{n}@t.com', 'password': 'pw'}).get_json()['refresh_token'] for n in ("r1", "r2")}

    def remove(who, target, reason="Left the company"):
        body = {} if reason is None else {'reason': reason}
        return c.delete(f'/api/employees/{target.id}', headers=H[who], json=body)

    # ---- 1. Who may remove whom ------------------------------------------------------------
    ok("an employee cannot remove anyone", remove('r3', r4).status_code == 403)
    ok("a recruiter cannot remove anyone", remove('r1', r4).status_code == 403)
    ok("Finance cannot remove anyone", remove('fin', r4).status_code == 403)
    r = remove('mgr', outsider)
    ok("a manager CANNOT remove someone on another manager's team", r.status_code == 403 and "direct reports" in r.get_json()['message'], r.get_json())
    ok("...and that person is untouched", User.query.get(outsider.id).is_active is True)
    ok("a manager cannot remove themselves", remove('mgr', mgr).status_code == 400)
    ok("HR Operations cannot remove themselves either", remove('admin', admin).status_code == 400)
    r = remove('mgr', ops_report)
    ok("a manager cannot remove an HR Operations user, even a direct report", r.status_code == 403, r.get_json())

    # ---- 2. Safeguards on the request itself -----------------------------------------------------
    r = remove('mgr', r4, reason=None)
    ok("removal without a reason is refused", r.status_code == 400 and r.get_json().get('reason_required') is True, r.get_json())
    ok("a whitespace-only reason is refused", remove('mgr', r4, reason="   ").status_code == 400)
    ok("an over-long reason is refused", remove('mgr', r4, reason="x" * 256).status_code == 400)
    ok("...and none of those refusals removed anyone", User.query.get(r4.id).is_active is True)
    r = remove('mgr', submgr)
    ok("a person who still has active direct reports cannot be removed", r.status_code == 409 and r.get_json()['active_reports'] == 1, r.get_json())
    ok("...and the manager is told HR Operations can reassign them", "HR Operations can reassign" in r.get_json()['message'], r.get_json())
    r = remove('admin', submgr)
    ok("HR Operations gets the same protection (told to reassign first)", r.status_code == 409 and "reassign them first" in r.get_json()['message'], r.get_json())

    # ---- 3. A real removal: effects ---------------------------------------------------------------------
    # give r1 data that must survive, and pending things that must be tidied up
    db.session.add(Attendance(user_id=r1.id, work_date=date.today() - timedelta(days=3), status="present", total_hours=8.0,
                              clock_in=datetime.utcnow() - timedelta(days=3, hours=8), clock_out=datetime.utcnow() - timedelta(days=3)))
    db.session.add(SalaryStructure(user_id=r1.id, basic=40000))
    db.session.flush()
    db.session.add(Payslip(user_id=r1.id, month=8, year=2026, gross_earnings=40000, net_pay=38000, status="paid"))
    db.session.add(LeaveRequest(user_id=r1.id, leave_type_id=lt.id, start_date=date.today() + timedelta(days=5),
                                end_date=date.today() + timedelta(days=6), days=2, status="pending"))
    db.session.add(LeaveRequest(user_id=r1.id, leave_type_id=lt.id, start_date=date.today() - timedelta(days=40),
                                end_date=date.today() - timedelta(days=39), days=2, status="approved"))
    db.session.add(DeviceToken(user_id=r1.id, token="ExponentPushToken[r1phone]", platform="android"))
    db.session.commit()
    att_before = Attendance.query.filter_by(user_id=r1.id).count()

    ok("before removal r1 is in the directory", "Sneha Recruiter" in {e['full_name'] for e in c.get('/api/employees', headers=H['mgr']).get_json()})
    r = remove('mgr', r1, reason="  Resigned — last working day today  ")
    ok("a manager CAN remove their own direct report", r.status_code == 200, r.get_json())
    body = r.get_json()['employee']
    ok("the person is marked inactive", body['is_active'] is False, body)
    ok("the audit trail records who, when and why (reason trimmed)",
       body['removed_by_name'] == "Ananya Manager" and body['removed_at'] and body['removal_reason'] == "Resigned — last working day today", body)
    ok("they disappear from the normal directory", "Sneha Recruiter" not in {e['full_name'] for e in c.get('/api/employees', headers=H['mgr']).get_json()})
    ok("removing someone twice is refused", remove('mgr', r1).status_code == 400)

    ok("their existing access token stops working IMMEDIATELY (not after 12 hours)",
       c.get('/api/auth/me', headers=H['r1']).status_code == 401)
    ok("...with a clear message", "no longer active" in c.get('/api/attendance/today', headers=H['r1']).get_json()['message'])
    ok("they cannot log in again", c.post('/api/auth/login', json={'email': 'r1@t.com', 'password': 'pw'}).status_code in (401, 403))
    ok("their refresh token cannot bring them back either", c.post('/api/auth/refresh', headers={'Authorization': 'Bearer ' + refresh['r1']}).status_code == 403)
    ok("other people's sessions are unaffected", c.get('/api/auth/me', headers=H['r2']).status_code == 200)

    ok("their pending leave request was cancelled (not left stuck in approvers' queues)",
       LeaveRequest.query.filter_by(user_id=r1.id, status="pending").count() == 0 and LeaveRequest.query.filter_by(user_id=r1.id, status="cancelled").count() == 1)
    ok("...but their approved leave history is untouched", LeaveRequest.query.filter_by(user_id=r1.id, status="approved").count() == 1)
    ok("their phone is unregistered from push notifications", DeviceToken.query.filter_by(user_id=r1.id).count() == 0)

    ok("NOTHING was hard-deleted: attendance history is intact", Attendance.query.filter_by(user_id=r1.id).count() == att_before)
    ok("...payslips are intact", Payslip.query.filter_by(user_id=r1.id).count() == 1)
    ok("...salary structure is intact", SalaryStructure.query.filter_by(user_id=r1.id).count() == 1)
    ok("...and the user record itself still exists", User.query.get(r1.id) is not None)

    ok("payroll no longer generates new payslips for a removed person",
       r1.id not in {p['user_id'] for p in c.post('/api/payroll/generate', headers=H['admin'], json={'month': 9, 'year': 2026}).get_json()})

    # a removed person's pending regularization request shouldn't clutter the approvals queue
    reason = c.post('/api/attendance/regularization-reasons', headers=H['mgr'], json={'label': 'Forgot to punch'}).get_json()
    day = (date.today() - timedelta(days=4)).isoformat()
    c.post('/api/attendance/regularize-request', headers=H['r3'], json={'work_date': day, 'reason_id': reason['id']})
    c.post('/api/attendance/regularize-request', headers=H['r4'], json={'work_date': day, 'reason_id': reason['id']})
    q = lambda: {x['employee_name'] for x in c.get('/api/attendance/regularization-requests', headers=H['mgr']).get_json()}
    ok("before removal, the manager's approvals queue has both pending requests", q() == {"Kiran Employee", "Dev Employee"}, q())
    remove('mgr', r3, reason="Left the company")
    ok("after removal, a removed person's pending request disappears from the approvals queue", q() == {"Dev Employee"}, q())
    c.post(f'/api/employees/{r3.id}/restore', headers=H['mgr'])
    ok("...and returns if they are restored (the request itself was never deleted)", q() == {"Kiran Employee", "Dev Employee"}, q())

    # ---- 4. Removed list ---------------------------------------------------------------------------------------
    rem = c.get('/api/employees', headers=H['mgr'], query_string={'status': 'removed'})
    ok("a manager can list the people THEY removed", rem.status_code == 200 and [e['full_name'] for e in rem.get_json()] == ["Sneha Recruiter"], rem.get_json())
    ok("...with the reason visible", rem.get_json()[0]['removal_reason'].startswith("Resigned"))
    ok("another manager sees none of them", c.get('/api/employees', headers=H['mgr2'], query_string={'status': 'removed'}).get_json() == [])
    ok("HR Operations sees all removed people", [e['full_name'] for e in c.get('/api/employees', headers=H['admin'], query_string={'status': 'removed'}).get_json()] == ["Sneha Recruiter"])
    ok("an ordinary employee cannot list removed people", c.get('/api/employees', headers=H['r3'], query_string={'status': 'removed'}).status_code == 403)

    # ---- 5. Restore -----------------------------------------------------------------------------------------------------
    ok("an employee cannot restore anyone", c.post(f'/api/employees/{r1.id}/restore', headers=H['r3']).status_code == 403)
    ok("another manager cannot restore them", c.post(f'/api/employees/{r1.id}/restore', headers=H['mgr2']).status_code == 403)
    ok("restoring an active person is refused", c.post(f'/api/employees/{r3.id}/restore', headers=H['mgr']).status_code == 400)
    r = c.post(f'/api/employees/{r1.id}/restore', headers=H['mgr'])
    ok("the manager who removed someone can restore them", r.status_code == 200 and r.get_json()['employee']['is_active'] is True, r.get_json())
    ok("restoring clears the removal record", r.get_json()['employee']['removed_at'] is None and r.get_json()['employee']['removal_reason'] is None, r.get_json())
    ok("they can log in again", c.post('/api/auth/login', json={'email': 'r1@t.com', 'password': 'pw'}).status_code == 200)
    ok("their data is all still there", Attendance.query.filter_by(user_id=r1.id).count() == att_before and Payslip.query.filter_by(user_id=r1.id).count() == 1)

    # a manager cannot overturn an HR Operations decision
    remove('admin', r2, reason="Terminated — policy violation")
    ok("a manager CANNOT restore someone that HR Operations removed",
       c.post(f'/api/employees/{r2.id}/restore', headers=H['mgr']).status_code == 403)
    ok("HR Operations can", c.post(f'/api/employees/{r2.id}/restore', headers=H['admin']).status_code == 200)

    # ---- 6. Re-parenting protection after removing the last report ----------------------------------------------------------
    r = remove('admin', subrep, reason="Contract ended")
    ok("a sub-manager's last report can be removed", r.status_code == 200)
    ok("...after which the sub-manager CAN be removed by their manager", remove('mgr', submgr, reason="Role eliminated").status_code == 200)

    # ---- 7. Older deactivate-by-edit path uses the same rules -------------------------------------------------------------------------
    r = c.put(f'/api/employees/{r4.id}', headers=H['admin'], json={'is_active': False})
    ok("HR Operations deactivating via the edit form still works and now records an audit trail",
       r.status_code == 200 and r.get_json()['is_active'] is False and r.get_json()['removal_reason'] == "Deactivated by HR Operations" and r.get_json()['removed_by_name'] == "Priya Ops", r.get_json())
    r = c.put(f'/api/employees/{r4.id}', headers=H['admin'], json={'is_active': True})
    ok("...and reactivating clears it", r.get_json()['is_active'] is True and r.get_json()['removed_at'] is None, r.get_json())
    lead = mk("L1", "lead@t.com", "Team Lead", MANAGER, manager_id=mgr.id); mk("L2", "leadrep@t.com", "Lead Report", EMPLOYEE, manager_id=lead.id); db.session.commit()
    r = c.put(f'/api/employees/{lead.id}', headers=H['admin'], json={'is_active': False})
    ok("the edit-form path ALSO refuses to orphan active reports (409)", r.status_code == 409 and User.query.get(lead.id).is_active is True, r.get_json())
    ok("a manager cannot deactivate through the edit form (unchanged)", c.put(f'/api/employees/{r3.id}', headers=H['mgr'], json={'is_active': False}).get_json()['is_active'] is True)

print("\nALL EMPLOYEE REMOVAL SMOKE TESTS PASSED")
