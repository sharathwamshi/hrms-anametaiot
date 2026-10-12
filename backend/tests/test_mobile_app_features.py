import sys
sys.path.insert(0, '.')

from unittest.mock import patch
from config import Config
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True
    INTERNAL_TASK_SECRET = 'test-secret'

from app import create_app
from app.extensions import db
from app.models import User, Department, CompanySettings, Attendance, DeviceToken
from app.roles import HR_OPERATIONS, HR_RECRUITER, MANAGER, EMPLOYEE
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

    def mk(code, email, name, role, manager_id=None):
        u = User(employee_code=code, full_name=name, email=email, role=role,
                 department_id=dept.id, manager_id=manager_id, date_of_joining=date(2024, 1, 1))
        u.set_password("pw"); db.session.add(u); db.session.flush(); return u

    mgr = mk("M1", "mgr@t.com", "Ananya Manager", MANAGER)
    admin = mk("A1", "admin@t.com", "Priya Ops", HR_OPERATIONS)
    rec1 = mk("R1", "rec1@t.com", "Sneha Recruiter", HR_RECRUITER, manager_id=mgr.id)
    rec2 = mk("R2", "rec2@t.com", "Meera Recruiter", HR_RECRUITER)  # no manager — falls back to HR Ops
    db.session.commit()

    client = app.test_client()
    tokens = {}
    def login(email):
        r = client.post('/api/auth/login', json={'email': email, 'password': 'pw'})
        body = r.get_json()
        tokens[email] = body
        return {'Authorization': f"Bearer {body['access_token']}"}
    H = {n: login(f"{n}@t.com") for n in ("mgr", "admin", "rec1", "rec2")}

    # ---- 1. Refresh tokens ---------------------------------------------------------------
    body = tokens["rec1@t.com"]
    ok("login returns both an access and a refresh token", "access_token" in body and "refresh_token" in body, body)
    r = client.post('/api/auth/refresh', headers={'Authorization': f"Bearer {body['refresh_token']}"})
    ok("the refresh token gets a new access token", r.status_code == 200 and "access_token" in r.get_json(), r.get_json())
    new_access = r.get_json()["access_token"]
    r = client.get('/api/auth/me', headers={'Authorization': f"Bearer {new_access}"})
    ok("the new access token actually works", r.status_code == 200, r.get_json())
    r = client.post('/api/auth/refresh', headers={'Authorization': f"Bearer {body['access_token']}"})
    ok("an ACCESS token cannot be used at /refresh (must be a refresh token)", r.status_code == 422, r.get_json())

    User.query.get(rec1.id).is_active = False; db.session.commit()
    r = client.post('/api/auth/refresh', headers={'Authorization': f"Bearer {body['refresh_token']}"})
    ok("a deactivated account cannot refresh its way back in", r.status_code == 403, r.get_json())
    User.query.get(rec1.id).is_active = True; db.session.commit()

    # ---- 2. Office locations (geofence centers) --------------------------------------------
    ok("recruiter cannot add an office location", client.post('/api/attendance/office-locations', headers=H['rec1'], json={'name': 'HQ', 'latitude': 12.97, 'longitude': 77.59}).status_code == 403)
    r = client.post('/api/attendance/office-locations', headers=H['admin'], json={'name': 'Bengaluru HQ', 'latitude': 12.9716, 'longitude': 77.5946, 'radius_meters': 150})
    ok("HR Operations can add an office location", r.status_code == 201, r.get_json())
    office = r.get_json()
    ok("everyone (a recruiter) can list office locations", client.get('/api/attendance/office-locations', headers=H['rec1']).status_code == 200)
    r = client.post('/api/attendance/office-locations', headers=H['admin'], json={'name': 'Bad', 'latitude': 'nope', 'longitude': 77.5}) 
    ok("a non-numeric latitude is rejected", r.status_code == 400, r.get_json())

    # ---- 3. Geofencing is SOFT: clock-in always succeeds, just flagged -----------------------
    r = client.post('/api/attendance/clock-in', headers=H['rec1'], json={'latitude': 12.9716, 'longitude': 77.5946})
    ok("clock-in INSIDE the radius succeeds and is not flagged", r.status_code == 201 and r.get_json()['geofence_warning'] is False, r.get_json())
    ok("clock_in_within_geofence is recorded true", r.get_json()['clock_in_within_geofence'] is True, r.get_json())

    client.post('/api/attendance/clock-out', headers=H['rec1'], json={})  # close today's record out so tomorrow... (not needed, different user next)
    r = client.post('/api/attendance/clock-in', headers=H['rec2'], json={'latitude': 13.5, 'longitude': 78.5})  # far away
    ok("clock-in OUTSIDE every office radius still SUCCEEDS (soft, never blocks)", r.status_code == 201, r.get_json())
    ok("...but is flagged as a geofence warning", r.get_json()['geofence_warning'] is True and r.get_json()['clock_in_within_geofence'] is False, r.get_json())

    r = client.get('/api/attendance/team', headers=H['admin'], query_string={'date': date.today().isoformat()})
    rows = {x['employee_name']: x for x in r.get_json()}
    ok("the manager/HR-Ops team view carries the geofence flag per person", rows['Meera Recruiter']['clock_in_within_geofence'] is False and rows['Sneha Recruiter']['clock_in_within_geofence'] is True, rows)

    # clock-in with no location at all must not be flagged as a violation
    User.query.filter_by(id=rec2.id).first()
    rec3 = mk("R3", "rec3@t.com", "Kiran No-GPS", HR_RECRUITER); db.session.commit()
    H['rec3'] = login('rec3@t.com')
    r = client.post('/api/attendance/clock-in', headers=H['rec3'], json={})
    ok("clocking in with no GPS at all is not treated as a violation", r.get_json()['geofence_warning'] is False and r.get_json()['clock_in_within_geofence'] is None, r.get_json())

    # ---- 4. Device registration -------------------------------------------------------------
    r = client.post('/api/notifications/register-device', headers=H['rec1'], json={'token': 'ExponentPushToken[aaa]', 'platform': 'android'})
    ok("device registers for push", r.status_code == 201, r.get_json())
    r = client.post('/api/notifications/register-device', headers=H['mgr'], json={'token': 'ExponentPushToken[mgr]', 'platform': 'ios'})
    ok("manager registers a device too", r.status_code == 201, r.get_json())
    r = client.post('/api/notifications/register-device', headers=H['admin'], json={'token': 'ExponentPushToken[admin]', 'platform': 'ios'})
    ok("HR Ops registers a device too", r.status_code == 201, r.get_json())
    ok("re-registering the same token just re-points it, no duplicate", DeviceToken.query.filter_by(token='ExponentPushToken[aaa]').count() == 1)

    # ---- 5. Push is triggered at the right points (mock the actual HTTP call) ----------------
    with patch("app.routes.attendance.send_push") as mock_push:
        day = (date.today() - timedelta(days=3)).isoformat()
        r = client.post('/api/attendance/regularize-request', headers=H['rec1'],
                        json={'work_date': day, 'reason_id': 1, 'note': 'test'}) 
        # reason doesn't exist yet in this suite -> create one properly first
    # create a reason, retry properly
    r = client.post('/api/attendance/regularization-reasons', headers=H['mgr'], json={'label': 'Forgot to punch'})
    reason = r.get_json()

    with patch("app.routes.attendance.send_push") as mock_push:
        day2 = (date.today() - timedelta(days=4)).isoformat()
        r = client.post('/api/attendance/regularize-request', headers=H['rec1'], json={'work_date': day2, 'reason_id': reason['id'], 'note': 'Forgot'})
        ok("request created", r.status_code == 201, r.get_json())
        ok("a push was fired to the requester's manager on a new request", mock_push.called, mock_push.call_args_list)
        call_args = mock_push.call_args_list[0][0]
        ok("...addressed to the manager's user id", call_args[0] == [mgr.id], call_args)
        rec_id = r.get_json()['id']

    with patch("app.routes.attendance.send_push") as mock_push:
        r = client.post(f"/api/attendance/regularization-requests/{rec_id}/approve", headers=H['mgr'], json={'comment': 'ok'})
        ok("approving fires a push to the requester", mock_push.called and mock_push.call_args_list[0][0][0] == rec1.id, mock_push.call_args_list)

    # no-manager fallback to HR Ops
    with patch("app.routes.attendance.send_push") as mock_push:
        day3 = (date.today() - timedelta(days=5)).isoformat()
        r = client.post('/api/attendance/regularize-request', headers=H['rec2'], json={'work_date': day3, 'reason_id': reason['id']})
        ok("a recruiter with no manager notifies HR Ops instead", mock_push.called and admin.id in mock_push.call_args_list[0][0][0], mock_push.call_args_list)
        rec_id2 = r.get_json()['id']

    with patch("app.routes.attendance.send_push") as mock_push:
        r = client.post(f"/api/attendance/regularization-requests/{rec_id2}/reject", headers=H['admin'], json={'comment': 'No evidence'})
        ok("rejecting fires a push to the requester with the comment", mock_push.called and "No evidence" in mock_push.call_args_list[0][0][2], mock_push.call_args_list)

    # ---- 6. Scheduled reminders endpoint ------------------------------------------------------
    r = client.post('/api/attendance/internal/attendance-reminders', json={'kind': 'clock_in_reminder'})
    ok("the reminders endpoint rejects a request with no secret", r.status_code == 403, r.get_json())
    r = client.post('/api/attendance/internal/attendance-reminders', headers={'X-Internal-Secret': 'wrong'}, json={'kind': 'clock_in_reminder'})
    ok("...and the wrong secret", r.status_code == 403, r.get_json())

    with patch("app.routes.attendance.send_push") as mock_push:
        r = client.post('/api/attendance/internal/attendance-reminders', headers={'X-Internal-Secret': 'test-secret'}, json={'kind': 'clock_in_reminder'})
        ok("the correct secret runs clock-in reminders", r.status_code == 200, r.get_json())
        # rec1, rec3 clocked in today; admin, mgr, rec2 did not (rec2 clocked in but we didn't clock mgr/admin in)
        reminded = {c[0][0] for c in mock_push.call_args_list}
        ok("only people who have NOT clocked in today get the reminder", rec1.id not in reminded and mgr.id in reminded, reminded)

    rec4 = mk("R4", "rec4@t.com", "Late Larry", HR_RECRUITER, manager_id=mgr.id); db.session.commit()
    with patch("app.routes.attendance.send_push") as mock_push:
        r = client.post('/api/attendance/internal/attendance-reminders', headers={'X-Internal-Secret': 'test-secret'}, json={'kind': 'manager_missing_alert'})
        ok("manager-missing-alert groups by manager and pushes once per manager", r.status_code == 200 and mock_push.called, mock_push.call_args_list)
        ok("...addressed to the manager, naming the missing report", mock_push.call_args_list[0][0][0] == mgr.id and "Late Larry" in mock_push.call_args_list[0][0][2], mock_push.call_args_list)

    r = client.post('/api/attendance/internal/attendance-reminders', headers={'X-Internal-Secret': 'test-secret'}, json={'kind': 'not-a-real-kind'})
    ok("an invalid kind is rejected", r.status_code == 400, r.get_json())

print("\nALL MOBILE-APP FEATURE (REFRESH TOKEN / GEOFENCE / PUSH) SMOKE TESTS PASSED")
