import io
import os
import sys
import tempfile
sys.path.insert(0, '.')

from config import Config
_SELFIE_DIR = tempfile.mkdtemp(prefix="selfies_test_")

class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True
    SELFIE_FOLDER = _SELFIE_DIR

from app import create_app
from app.extensions import db
from app.models import (User, Department, CompanySettings, Attendance, OfficeLocation,
                        Holiday, LeaveRequest, LeaveType)
from app.roles import HR_OPERATIONS, HR_RECRUITER, MANAGER, OPERATIONS
from datetime import date, datetime, timedelta

app = create_app(TestConfig)

def ok(label, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {'' if cond else extra}")
    if not cond:
        raise SystemExit(f"STOPPED at: {label}")

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

def selfie(data=JPEG, name="me.jpg"):
    return (io.BytesIO(data), name)

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
    ops = mk("O1", "ops@t.com", "Oscar Operations", OPERATIONS)
    r1 = mk("R1", "r1@t.com", "Sneha Recruiter", HR_RECRUITER, manager_id=mgr.id)
    r2 = mk("R2", "r2@t.com", "Meera Recruiter", HR_RECRUITER, manager_id=mgr.id)
    r3 = mk("R3", "r3@t.com", "Leave Larry", HR_RECRUITER, manager_id=mgr.id)
    stranger = mk("R4", "r4@t.com", "Not Mine", HR_RECRUITER, manager_id=mgr2.id)
    db.session.add(OfficeLocation(name="HQ", latitude=12.9716, longitude=77.5946, radius_meters=150))
    lt = LeaveType(name="Casual Leave", annual_quota=12); db.session.add(lt); db.session.flush()
    db.session.commit()

    c = app.test_client()
    def login(e):
        return {'Authorization': 'Bearer ' + c.post('/api/auth/login', json={'email': e, 'password': 'pw'}).get_json()['access_token']}
    H = {n: login(f"{n}@t.com") for n in ("mgr", "mgr2", "admin", "ops", "r1", "r2", "r3", "r4")}
    def punch(kind, who, with_selfie=True, lat=12.9716, lng=77.5946, data=None):
        form = {'latitude': str(lat), 'longitude': str(lng)}
        if with_selfie:
            form['selfie'] = data or selfie()
        return c.post(f'/api/attendance/{kind}', headers=H[who], data=form, content_type='multipart/form-data')

    # ---- 1. Policy: off by default, only managers/HR Ops can change it ---------------------
    ok("selfie policy is OFF by default", c.get('/api/attendance/policy', headers=H['r1']).get_json()['selfie_required'] is False)
    r = c.post('/api/attendance/clock-in', headers=H['r1'], json={'latitude': 12.9716, 'longitude': 77.5946})
    ok("with the policy off, a plain JSON clock-in (no selfie) works exactly as before", r.status_code == 201, r.get_json())
    c.post('/api/attendance/clock-out', headers=H['r1'], json={})
    ok("a recruiter cannot change the policy", c.put('/api/attendance/policy', headers=H['r1'], json={'selfie_required': True}).status_code == 403)
    ok("a non-boolean value is rejected", c.put('/api/attendance/policy', headers=H['mgr'], json={'selfie_required': 'yes'}).status_code == 400)
    r = c.put('/api/attendance/policy', headers=H['mgr'], json={'selfie_required': True})
    ok("a manager can turn the policy ON", r.status_code == 200 and r.get_json()['selfie_required'] is True, r.get_json())
    ok("everyone can read the policy (so the app knows to open the camera)", c.get('/api/attendance/policy', headers=H['r2']).get_json()['selfie_required'] is True)

    # ---- 2. With the policy ON the selfie is mandatory -----------------------------------------
    r = punch('clock-in', 'r2', with_selfie=False)
    ok("policy ON: clock-in WITHOUT a selfie is refused", r.status_code == 400 and r.get_json().get('selfie_required') is True, r.get_json())
    ok("...and no attendance record was created by the refused attempt",
       Attendance.query.filter_by(user_id=r2.id, work_date=date.today()).first() is None)
    r = c.post('/api/attendance/clock-in', headers=H['r2'], json={})
    ok("policy ON: a plain JSON clock-in is refused too", r.status_code == 400, r.get_json())
    r = punch('clock-in', 'r2', data=selfie(b"this is not an image", "evil.jpg"))
    ok("a non-image file renamed .jpg is refused (checked by content, not name)", r.status_code == 400, r.get_json())
    r = punch('clock-in', 'r2', data=selfie(b"", "empty.jpg"))
    ok("an empty file is refused", r.status_code == 400, r.get_json())
    r = punch('clock-in', 'r2', data=selfie(JPEG + b"\x00" * (5 * 1024 * 1024), "big.jpg"))
    ok("an oversized selfie is refused", r.status_code == 400, r.get_json())

    r = punch('clock-in', 'r2')
    ok("policy ON: clock-in WITH a valid selfie works", r.status_code == 201, r.get_json())
    ok("the record says a clock-in selfie exists", r.get_json()['has_clock_in_selfie'] is True and r.get_json()['has_clock_out_selfie'] is False, r.get_json())
    ok("the selfie file is stored in the private folder", len(os.listdir(_SELFIE_DIR)) == 1, os.listdir(_SELFIE_DIR))
    ok("...and NOT under the publicly served uploads folder",
       not any(f.endswith('.jpg') for f in (os.listdir(app.config['UPLOAD_FOLDER']) if os.path.isdir(app.config['UPLOAD_FOLDER']) else [])))

    r = punch('clock-out', 'r2', with_selfie=False)
    ok("policy ON: clock-OUT without a selfie is refused as well", r.status_code == 400 and r.get_json().get('selfie_required') is True, r.get_json())
    ok("...and the person is still clocked in (nothing half-applied)", Attendance.query.filter_by(user_id=r2.id).first().clock_out is None)
    r = punch('clock-out', 'r2', data=selfie(PNG, "out.png"))
    ok("clock-out with a PNG selfie works", r.status_code == 200 and r.get_json()['has_clock_out_selfie'] is True, r.get_json())

    # ---- 3. Selfie privacy ------------------------------------------------------------------------
    rid = r.get_json()['id']
    g = c.get(f'/api/attendance/records/{rid}/selfie/in', headers=H['r2'])
    ok("the owner can view their own selfie", g.status_code == 200 and g.data.startswith(b"\xff\xd8\xff"), g.status_code)
    ok("their manager can view it", c.get(f'/api/attendance/records/{rid}/selfie/in', headers=H['mgr']).status_code == 200)
    ok("HR Operations can view it", c.get(f'/api/attendance/records/{rid}/selfie/out', headers=H['admin']).status_code == 200)
    ok("a colleague cannot view it", c.get(f'/api/attendance/records/{rid}/selfie/in', headers=H['r1']).status_code == 403)
    ok("a DIFFERENT manager cannot view it", c.get(f'/api/attendance/records/{rid}/selfie/in', headers=H['mgr2']).status_code == 403)
    ok("the wider Operations role cannot view it", c.get(f'/api/attendance/records/{rid}/selfie/in', headers=H['ops']).status_code == 403)
    ok("an unauthenticated request cannot view it", c.get(f'/api/attendance/records/{rid}/selfie/in').status_code == 401)
    ok("a bogus kind is rejected", c.get(f'/api/attendance/records/{rid}/selfie/sideways', headers=H['mgr']).status_code == 400)
    ok("path traversal via the URL cannot reach files", c.get('/api/attendance/records/1/selfie/../../../config', headers=H['mgr']).status_code in (404, 400))
    ok("the selfie is not reachable through the public /static/uploads route",
       c.get('/static/uploads/' + os.listdir(_SELFIE_DIR)[0]).status_code == 404)

    # turn the policy off again: selfie becomes optional again
    c.put('/api/attendance/policy', headers=H['admin'], json={'selfie_required': False})
    r = c.post('/api/attendance/clock-in', headers=H['r3'], json={})
    ok("policy turned OFF again: no selfie needed", r.status_code == 201, r.get_json())
    c.post('/api/attendance/clock-out', headers=H['r3'], json={})

    # ---- 4. Manager's full view: everyone in scope, incl. people not yet in ---------------------
    # r1 clocked in earlier (inside office); make r2 outside office for a flag
    rec2 = Attendance.query.filter_by(user_id=r2.id).first()
    sess2 = rec2.sessions[0]  # sessions are the source of truth; the day row is rebuilt from them
    sess2.clock_in_within_geofence = False
    sess2.clock_out_lat, sess2.clock_out_lng, sess2.clock_out_within_geofence = 13.5, 78.5, False
    rec2.recompute_from_sessions()
    # r3 on approved leave today instead
    Attendance.query.filter_by(user_id=r3.id).delete()
    db.session.add(LeaveRequest(user_id=r3.id, leave_type_id=lt.id, start_date=date.today() - timedelta(days=1),
                                end_date=date.today() + timedelta(days=1), days=3, status="approved"))
    db.session.commit()

    r = c.get('/api/attendance/team/overview', headers=H['mgr'])
    body = r.get_json()
    ok("manager can open the team overview", r.status_code == 200, body)
    people = {p['user']['full_name']: p for p in body['people']}
    ok("it lists exactly the manager's reports (not other teams)", set(people) == {"Sneha Recruiter", "Meera Recruiter", "Leave Larry"}, set(people))
    ok("someone on approved leave shows as on_leave", people["Leave Larry"]['status'] == 'on_leave', people["Leave Larry"])
    ok("a person who clocked in shows with their real status (a same-second punch pair is a half day) and a record", people["Sneha Recruiter"]['status'] in ('present', 'half_day') and people["Sneha Recruiter"]['record'] is not None, people["Sneha Recruiter"])
    loc = people["Sneha Recruiter"]['last_known_location']
    ok("present location = where they last punched, with the time it was recorded",
       loc and abs(loc['latitude'] - 12.9716) < 1e-6 and loc['source'] == 'clock_in' and loc['as_of'].endswith('Z'), loc)
    loc2 = people["Meera Recruiter"]['last_known_location']
    ok("after clock-out, the last known location is the clock-out point", loc2['source'] == 'clock_out' and loc2['latitude'] == 13.5, loc2)
    ok("outside-office people are flagged", people["Meera Recruiter"]['outside_office'] is True and people["Sneha Recruiter"]['outside_office'] is False)
    ok("clocked_in_now is true only while still clocked in", people["Sneha Recruiter"]['clocked_in_now'] is False and people["Meera Recruiter"]['clocked_in_now'] is False)
    ok("summary counts add up", body['summary']['on_leave'] == 1 and body['summary']['outside_office'] == 1 and body['summary']['present'] == 2, body['summary'])

    # someone who never punched in today shows as not_clocked_in (today) / absent (past)
    r4b = mk("R5", "r5@t.com", "Never Punched", HR_RECRUITER, manager_id=mgr.id); db.session.commit()
    body = c.get('/api/attendance/team/overview', headers=H['mgr']).get_json()
    ok("a report who hasn't punched in appears as not_clocked_in today (the old /team endpoint hid them)",
       {p['user']['full_name']: p for p in body['people']}["Never Punched"]['status'] == 'not_clocked_in')
    yday = (date.today() - timedelta(days=9)).isoformat()
    body = c.get('/api/attendance/team/overview', headers=H['mgr'], query_string={'date': yday}).get_json()
    ok("...and as absent for a past date", {p['user']['full_name']: p for p in body['people']}["Never Punched"]['status'] == 'absent')

    ok("a recruiter cannot open the team overview", c.get('/api/attendance/team/overview', headers=H['r1']).status_code == 403)
    ok("a bad date is rejected", c.get('/api/attendance/team/overview', headers=H['mgr'], query_string={'date': 'nope'}).status_code == 400)
    body = c.get('/api/attendance/team/overview', headers=H['admin']).get_json()
    ok("HR Operations sees everyone, across teams", "Not Mine" in {p['user']['full_name'] for p in body['people']})
    body = c.get('/api/attendance/team/overview', headers=H['ops']).get_json()
    ops_people = {p['user']['full_name']: p for p in body['people']}
    ok("Operations can see attendance status/times...", ops_people["Sneha Recruiter"]['record']['clock_in'] is not None)
    ok("...but NOT locations or selfies", ops_people["Sneha Recruiter"]['last_known_location'] is None and 'clock_in_lat' not in ops_people["Sneha Recruiter"]['record'] and 'has_clock_in_selfie' not in ops_people["Sneha Recruiter"]['record'], ops_people["Sneha Recruiter"])
    team = c.get('/api/attendance/team', headers=H['ops'], query_string={'date': date.today().isoformat()}).get_json()
    ok("the older /team endpoint also hides coordinates from Operations", all('clock_in_lat' not in x for x in team), team[:1])
    team = c.get('/api/attendance/team', headers=H['mgr'], query_string={'date': date.today().isoformat()}).get_json()
    ok("...but a manager's /team includes them", any('clock_in_lat' in x for x in team))

    # ---- 5. Complete calendar for any month, any team member ---------------------------------
    today = date.today()
    # a record 70 days ago, to prove "any day"
    old = today - timedelta(days=70)
    cin = datetime(old.year, old.month, old.day, 4, 3, 21)
    db.session.add(Attendance(user_id=r1.id, work_date=old, clock_in=cin, clock_out=cin + timedelta(hours=8, minutes=30),
                              status="present", total_hours=8.5, clock_in_note="early start"))
    db.session.add(Holiday(name="Test Holiday", holiday_date=today.replace(day=1)))
    db.session.commit()

    r = c.get('/api/attendance/my-calendar', headers=H['r1'], query_string={'month': old.month, 'year': old.year})
    cal = r.get_json()
    ok("a person can open their OWN calendar for a month 70 days back", r.status_code == 200, cal)
    row = next(x for x in cal['records'] if x['work_date'] == old.isoformat())
    ok("...and see the exact check-in / check-out times for that day", row['clock_in'].startswith(cin.isoformat()[:19]) and row['clock_out'] is not None and row['total_hours'] == 8.5, row)
    ok("...including the note they left", row['clock_in_note'] == "early start")
    r = c.get('/api/attendance/my-calendar', headers=H['r1'], query_string={'month': today.month, 'year': today.year})
    ok("the calendar carries holidays and a summary", len(r.get_json()['holidays']) >= 1 and 'summary' in r.get_json(), r.get_json())
    ok("an invalid month is rejected", c.get('/api/attendance/my-calendar', headers=H['r1'], query_string={'month': 13, 'year': 2026}).status_code == 400)

    r = c.get('/api/attendance/team/%d/calendar' % r3.id, headers=H['mgr'], query_string={'month': today.month, 'year': today.year})
    cal = r.get_json()
    ok("a manager can open a report's complete calendar", r.status_code == 200 and cal['user']['full_name'] == "Leave Larry", cal)
    ok("approved leave appears in that calendar and in the summary", len(cal['leaves']) == 1 and cal['summary']['on_leave'] >= 1, cal)
    r = c.get('/api/attendance/team/%d/calendar' % r2.id, headers=H['mgr'], query_string={'month': today.month, 'year': today.year})
    cal = r.get_json()
    ok("the calendar's summary counts outside-office punches", cal['summary']['outside_office'] == 1, cal['summary'])
    ok("the manager sees coordinates and selfie flags in it", cal['records'][0]['has_clock_in_selfie'] is True and 'clock_in_lat' in cal['records'][0], cal['records'][0])
    ok("a manager CANNOT open another team's calendar", c.get('/api/attendance/team/%d/calendar' % stranger.id, headers=H['mgr'], query_string={'month': today.month, 'year': today.year}).status_code == 403)
    ok("a colleague cannot open someone's calendar", c.get('/api/attendance/team/%d/calendar' % r2.id, headers=H['r1'], query_string={'month': today.month, 'year': today.year}).status_code == 403)
    ok("HR Operations can open anyone's", c.get('/api/attendance/team/%d/calendar' % stranger.id, headers=H['admin'], query_string={'month': today.month, 'year': today.year}).status_code == 200)
    r = c.get('/api/attendance/team/%d/calendar' % r2.id, headers=H['ops'], query_string={'month': today.month, 'year': today.year})
    ok("Operations can open it but with locations/selfies redacted", r.status_code == 200 and 'clock_in_lat' not in r.get_json()['records'][0], r.get_json()['records'][0])

print("\nALL SELFIE / MANAGER-VIEW / CALENDAR SMOKE TESTS PASSED")
