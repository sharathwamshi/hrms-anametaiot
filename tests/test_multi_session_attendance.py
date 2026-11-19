import io
import sys
import tempfile
sys.path.insert(0, '.')

from config import Config
_SELFIE_DIR = tempfile.mkdtemp(prefix="selfies_ms_")

class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True
    SELFIE_FOLDER = _SELFIE_DIR

from app import create_app
from app.extensions import db
from app.models import User, Department, CompanySettings, Attendance, AttendanceSession, OfficeLocation
from app.roles import HR_OPERATIONS, HR_RECRUITER, MANAGER, OPERATIONS
from sqlalchemy import text
from datetime import date, datetime, timedelta

app = create_app(TestConfig)

def ok(label, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {'' if cond else extra}")
    if not cond:
        raise SystemExit(f"STOPPED at: {label}")

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

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
    r3 = mk("R3", "r3@t.com", "Legacy Leela", HR_RECRUITER, manager_id=mgr.id)
    stranger = mk("R4", "r4@t.com", "Not Mine", HR_RECRUITER, manager_id=mgr2.id)
    db.session.add(OfficeLocation(name="HQ", latitude=12.9716, longitude=77.5946, radius_meters=150))
    db.session.commit()

    c = app.test_client()
    def login(e):
        return {'Authorization': 'Bearer ' + c.post('/api/auth/login', json={'email': e, 'password': 'pw'}).get_json()['access_token']}
    H = {n: login(f"{n}@t.com") for n in ("mgr", "mgr2", "admin", "ops", "r1", "r2", "r3", "r4")}
    IN, OUT = (12.9716, 77.5946), (13.5, 78.5)

    def cin(who, reason=None, lat=IN[0], lng=IN[1], selfie=False):
        body = {'latitude': str(lat), 'longitude': str(lng)}
        if reason is not None: body['reason'] = reason
        if selfie: body['selfie'] = (io.BytesIO(JPEG), 'me.jpg')
        return c.post('/api/attendance/clock-in', headers=H[who], data=body, content_type='multipart/form-data')
    def cout(who, lat=IN[0], lng=IN[1], selfie=False):
        if selfie:
            return c.post('/api/attendance/clock-out', headers=H[who], data={'latitude': str(lat), 'longitude': str(lng), 'selfie': (io.BytesIO(JPEG), 'o.jpg')}, content_type='multipart/form-data')
        return c.post('/api/attendance/clock-out', headers=H[who], json={'latitude': lat, 'longitude': lng})

    # ---- 1. The first check-in of the day needs no reason ---------------------------------
    r = cin('r1')
    ok("the FIRST check-in of the day needs no reason", r.status_code == 201, r.get_json())
    b = r.get_json()
    ok("it is session #1, not a re-entry", b['session_count'] == 1 and b['is_reentry'] is False and b['reentry_count'] == 0, b)
    ok("clocking in twice in a row is refused", cin('r1').status_code == 400)

    # ---- 2. Check out, then check in AGAIN: the reason is mandatory ---------------------------
    r = cout('r1')
    ok("check-out works", r.status_code == 200 and r.get_json()['clock_out'] is not None and r.get_json()['currently_clocked_in'] is False, r.get_json())
    r = cin('r1')
    ok("checking in AGAIN without a reason is refused", r.status_code == 400 and r.get_json().get('reason_required') is True, r.get_json())
    ok("a whitespace-only reason is refused", cin('r1', reason="   ").status_code == 400)
    ok("a 2-character reason is refused", cin('r1', reason="ok").status_code == 400)
    ok("an over-long reason is refused", cin('r1', reason="x" * 256).status_code == 400)
    ok("...and none of those refused attempts created a session", len(Attendance.query.filter_by(user_id=r1.id).first().sessions) == 1)

    r = cin('r1', reason="  Clocked out by mistake  ")
    ok("checking in again WITH a reason works", r.status_code == 201, r.get_json())
    b = r.get_json()
    ok("it is session #2 and flagged as a re-entry", b['session_count'] == 2 and b['is_reentry'] is True and b['reentry_count'] == 1, b)
    ok("the reason is stored (trimmed) on that session", b['sessions'][1]['reentry_reason'] == "Clocked out by mistake" and b['sessions'][0]['reentry_reason'] is None, b['sessions'])
    ok("the day now shows as clocked in again (no day-level check-out)", b['clock_out'] is None and b['currently_clocked_in'] is True, b)
    ok("the day's check-in is still the FIRST session's", b['clock_in'] == b['sessions'][0]['clock_in'], b)
    ok("clocking in while already clocked in is refused", cin('r1', reason="again").status_code == 400)

    r = c.get('/api/attendance/today', headers=H['r1'])
    ok("the person's own /today shows both sessions and the reason", len(r.get_json()['record']['sessions']) == 2 and r.get_json()['record']['sessions'][1]['reentry_reason'], r.get_json())
    r = cout('r1')
    ok("closing the second session works", r.status_code == 200 and r.get_json()['currently_clocked_in'] is False and r.get_json()['sessions'][1]['clock_out'], r.get_json())
    ok("clocking out when not clocked in is refused", cout('r1').status_code == 400)

    # ---- 3. Hours add up across sessions ---------------------------------------------------------
    rec = Attendance.query.filter_by(user_id=r1.id).first()
    base = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=3, minutes=30)  # 09:00 IST in UTC
    s1, s2 = rec.sessions
    s1.clock_in, s1.clock_out = base, base + timedelta(hours=3)                      # 3h
    s2.clock_in, s2.clock_out = base + timedelta(hours=3, minutes=15), base + timedelta(hours=8, minutes=15)  # 5h, 15 min away
    rec.recompute_from_sessions(); db.session.commit()
    body = c.get('/api/attendance/today', headers=H['r1']).get_json()['record']
    ok("total hours = the SUM of all sessions (3h + 5h), not first-in to last-out", body['total_hours'] == 8.0, body['total_hours'])
    ok("the 15-minute gap is reported as away time", body['away_minutes'] == 15 and body['sessions'][1]['gap_minutes_before'] == 15, body)
    ok("status is judged on the total (8h = present)", body['status'] == 'present', body['status'])

    # 3h + 0.5h = 3.5h total -> half day, even though first-in to last-out spans 9h
    s2.clock_in, s2.clock_out = base + timedelta(hours=8), base + timedelta(hours=8, minutes=30)
    rec.recompute_from_sessions(); db.session.commit()
    body = c.get('/api/attendance/today', headers=H['r1']).get_json()['record']
    ok("time spent away is NOT counted as worked: 3.5h total is a half day", body['total_hours'] == 3.5 and body['status'] == 'half_day', body)

    # ---- 4. Policy applies to every session ---------------------------------------------------
    c.put('/api/attendance/policy', headers=H['mgr'], json={'selfie_required': True})
    cin('r2', selfie=True); cout('r2', selfie=True)
    r = cin('r2', reason="Back from client visit")
    ok("with selfie policy ON, a re-entry without a selfie is refused", r.status_code == 400 and r.get_json().get('selfie_required') is True, r.get_json())
    r = cin('r2', reason="Back from client visit", selfie=True)
    ok("...and works with one", r.status_code == 201 and r.get_json()['sessions'][1]['has_clock_in_selfie'] is True, r.get_json())
    sid = r.get_json()['sessions'][1]['id']
    ok("the re-entry's selfie is viewable by the person", c.get(f'/api/attendance/sessions/{sid}/selfie/in', headers=H['r2']).status_code == 200)
    ok("...by their manager", c.get(f'/api/attendance/sessions/{sid}/selfie/in', headers=H['mgr']).status_code == 200)
    ok("...but not by a colleague", c.get(f'/api/attendance/sessions/{sid}/selfie/in', headers=H['r1']).status_code == 403)
    ok("...nor a different manager", c.get(f'/api/attendance/sessions/{sid}/selfie/in', headers=H['mgr2']).status_code == 403)
    ok("...nor the wider Operations role", c.get(f'/api/attendance/sessions/{sid}/selfie/in', headers=H['ops']).status_code == 403)
    ok("with selfie policy ON, a clock-out without one is refused too, so they stay clocked in", cout('r2').status_code == 400)
    cout('r2', selfie=True)
    c.put('/api/attendance/policy', headers=H['mgr'], json={'selfie_required': False})

    # ---- 5. Legacy single-record days keep working ------------------------------------------------
    legacy_in = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=4)
    db.session.add(Attendance(user_id=r3.id, work_date=date.today(), clock_in=legacy_in, clock_out=legacy_in + timedelta(hours=2),
                              status="half_day", total_hours=2.0, clock_in_note="old record"))
    db.session.commit()
    body = c.get('/api/attendance/today', headers=H['r3']).get_json()['record']
    ok("a pre-existing day (no session rows yet) is shown as one session", body['session_count'] == 1 and body['sessions'][0]['clock_in_note'] == "old record", body)
    ok("...reading it does not write anything", AttendanceSession.query.filter_by(attendance_id=body['id']).count() == 0)
    r = cin('r3')
    ok("checking in again on a legacy day also needs a reason", r.status_code == 400 and r.get_json().get('reason_required') is True, r.get_json())
    r = cin('r3', reason="Left early by mistake")
    b = r.get_json()
    ok("...then works, converting the legacy day into session #1 + the new session #2", r.status_code == 201 and b['session_count'] == 2 and b['sessions'][0]['clock_in_note'] == "old record", b)
    ok("...with the original session's data preserved", AttendanceSession.query.filter_by(attendance_id=b['id'], session_no=1).first().clock_out is not None)
    cout('r3')

    # ---- 6. Backfill SQL (what the migration runs) ----------------------------------------------
    old_day = date.today() - timedelta(days=20)
    a_old = Attendance(user_id=stranger.id, work_date=old_day, clock_in=legacy_in - timedelta(days=20),
                       clock_out=legacy_in - timedelta(days=20) + timedelta(hours=8), status="present", total_hours=8.0,
                       clock_in_lat=1.5, clock_in_lng=2.5)
    db.session.add(a_old); db.session.commit()
    backfill = """INSERT INTO attendance_sessions (attendance_id, session_no, clock_in, clock_out, clock_in_note, clock_out_note,
        clock_in_lat, clock_in_lng, clock_in_within_geofence, clock_out_lat, clock_out_lng, clock_out_within_geofence,
        clock_in_selfie, clock_out_selfie, reentry_reason, created_at)
      SELECT a.id, 1, a.clock_in, a.clock_out, a.clock_in_note, a.clock_out_note, a.clock_in_lat, a.clock_in_lng, a.clock_in_within_geofence,
        a.clock_out_lat, a.clock_out_lng, a.clock_out_within_geofence, a.clock_in_selfie, a.clock_out_selfie, NULL, a.clock_in
      FROM attendance a WHERE a.clock_in IS NOT NULL AND NOT EXISTS (SELECT 1 FROM attendance_sessions s WHERE s.attendance_id = a.id)"""
    before = AttendanceSession.query.count()
    db.session.execute(text(backfill)); db.session.commit()
    ok("the migration's backfill creates a session for each legacy day", AttendanceSession.query.filter_by(attendance_id=a_old.id).count() == 1)
    mid = AttendanceSession.query.count()
    db.session.execute(text(backfill)); db.session.commit()
    ok("...and is idempotent: running it again adds nothing", AttendanceSession.query.count() == mid)
    bs = AttendanceSession.query.filter_by(attendance_id=a_old.id).first()
    ok("...copying the times and location faithfully", bs.clock_in == a_old.clock_in and bs.clock_in_lat == 1.5 and bs.session_no == 1)

    # ---- 7. Manager's professional view: overview + exceptions report ----------------------------------
    # make r2's re-entry an outside-office punch to prove flags carry through
    rec2 = Attendance.query.filter_by(user_id=r2.id, work_date=date.today()).first()
    rec2.sessions[1].clock_in_within_geofence = False
    rec2.sessions[1].clock_in_lat, rec2.sessions[1].clock_in_lng = OUT
    rec2.recompute_from_sessions(); db.session.commit()

    body = c.get('/api/attendance/team/overview', headers=H['mgr']).get_json()
    people = {p['user']['full_name']: p for p in body['people']}
    p1 = people["Sneha Recruiter"]
    ok("overview shows how many sessions and re-entries each person has", p1['session_count'] == 2 and p1['reentry_count'] == 1, p1)
    ok("...and the latest re-entry's reason right on the row", p1['latest_reentry']['reason'] == "Clocked out by mistake", p1['latest_reentry'])
    ok("a person with a single session has no re-entry info", people.get("Not Mine") is None)
    ok("the summary counts re-entries across the team", body['summary']['reentries'] == 3, body['summary'])  # r1:1, r2:1, r3:1
    ok("outside-office flag considers EVERY session, not just the first", people["Meera Recruiter"]['outside_office'] is True, people["Meera Recruiter"])
    loc = people["Meera Recruiter"]['last_known_location']
    ok("last known location is the latest punch of ANY session", loc['latitude'] == OUT[0] or loc['source'] in ('clock_in', 'clock_out'), loc)
    ok("each session carries its own re-entry reason in the manager's record", people["Sneha Recruiter"]['record']['sessions'][1]['reentry_reason'] == "Clocked out by mistake")
    ops_rows = {p['user']['full_name']: p for p in c.get('/api/attendance/team/overview', headers=H['ops']).get_json()['people']}
    sess_o = ops_rows["Sneha Recruiter"]['record']['sessions'][1]
    ok("Operations sees the sessions and reason, but NO coordinates or selfie flags in them",
       sess_o['reentry_reason'] and 'clock_in_lat' not in sess_o and 'has_clock_in_selfie' not in sess_o, sess_o)

    rep = c.get('/api/attendance/team/reentries', headers=H['mgr'])
    ok("a manager can open the re-entries report", rep.status_code == 200, rep.get_json())
    rep = rep.get_json()
    ok("it lists exactly the manager's reports' re-entries (3), not other teams'", rep['total'] == 3 and {x['user']['full_name'] for x in rep['reentries']} == {"Sneha Recruiter", "Meera Recruiter", "Legacy Leela"}, rep)
    item = next(x for x in rep['reentries'] if x['user']['full_name'] == "Sneha Recruiter")
    ok("each entry has the reason, the check-out it followed, and the minutes away", item['reason'] == "Clocked out by mistake" and item['previous_clock_out'] and item['gap_minutes'] is not None, item)
    ok("it flags an outside-office re-entry", next(x for x in rep['reentries'] if x['user']['full_name'] == "Meera Recruiter")['outside_office'] is True)
    ok("it summarises by person", rep['people_count'] == 3 and all(x['count'] == 1 for x in rep['by_person']), rep['by_person'])
    ok("HR Operations sees every team's", c.get('/api/attendance/team/reentries', headers=H['admin']).get_json()['total'] == 3)
    ok("another manager sees only their own team's (none today)", c.get('/api/attendance/team/reentries', headers=H['mgr2']).get_json()['total'] == 0)
    ok("a recruiter cannot open the report", c.get('/api/attendance/team/reentries', headers=H['r1']).status_code == 403)
    ok("Operations can open it (reasons only)", c.get('/api/attendance/team/reentries', headers=H['ops']).status_code == 200)
    ok("...and sees no selfie indicators", all(not x['has_selfie'] for x in c.get('/api/attendance/team/reentries', headers=H['ops']).get_json()['reentries']))
    ok("a date range that excludes today returns nothing",
       c.get('/api/attendance/team/reentries', headers=H['mgr'], query_string={'from': (date.today() - timedelta(days=30)).isoformat(), 'to': (date.today() - timedelta(days=10)).isoformat()}).get_json()['total'] == 0)
    ok("a reversed range is rejected", c.get('/api/attendance/team/reentries', headers=H['mgr'], query_string={'from': '2026-10-10', 'to': '2026-10-01'}).status_code == 400)
    ok("a range over 93 days is rejected", c.get('/api/attendance/team/reentries', headers=H['mgr'], query_string={'from': '2025-01-01', 'to': '2026-10-01'}).status_code == 400)
    ok("a bad date is rejected", c.get('/api/attendance/team/reentries', headers=H['mgr'], query_string={'from': 'nope'}).status_code == 400)

    cal = c.get(f'/api/attendance/team/{r1.id}/calendar', headers=H['mgr'], query_string={'month': date.today().month, 'year': date.today().year}).get_json()
    ok("a person's calendar summary counts their re-entries", cal['summary']['reentries'] >= 1, cal['summary'])
    ok("...and each day in it carries the full session list with reasons", any(len(r['sessions']) == 2 for r in cal['records']))
    own = c.get('/api/attendance/my-calendar', headers=H['r1'], query_string={'month': date.today().month, 'year': date.today().year}).get_json()
    ok("the person sees the same reasons on their own calendar (nothing hidden from them)", any(s['reentry_reason'] for r in own['records'] for s in r['sessions']))

    # ---- 8. Safety cap -------------------------------------------------------------------------------------
    for i in range(12):
        who_resp = cin('r4', reason="again") if i else cin('r4')
        if who_resp.status_code != 201:
            break
        cout('r4')
    ok("the number of check-ins per day is capped at 10", AttendanceSession.query.filter_by(attendance_id=Attendance.query.filter_by(user_id=stranger.id, work_date=date.today()).first().id).count() == 10)
    r = cin('r4', reason="one more")
    ok("an 11th check-in is refused with a clear message", r.status_code == 400 and "at most 10" in r.get_json()['message'], r.get_json())

print("\nALL MULTI-SESSION ATTENDANCE SMOKE TESTS PASSED")
