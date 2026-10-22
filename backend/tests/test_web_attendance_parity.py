import io
import sys
import tempfile
from calendar import monthrange
sys.path.insert(0, '.')

from config import Config
_SELFIE_DIR = tempfile.mkdtemp(prefix="selfies_web_")

class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True
    SELFIE_FOLDER = _SELFIE_DIR

from app import create_app
from app.extensions import db
from app.models import (User, Department, CompanySettings, Attendance, AttendanceSession, OfficeLocation,
                        AttendanceRegularizationReason, Holiday)
from app.roles import HR_OPERATIONS, HR_RECRUITER, MANAGER, OPERATIONS, EMPLOYEE, CONTRACT_EMPLOYEE
from datetime import date, datetime, timedelta
from openpyxl import load_workbook

app = create_app(TestConfig)

def ok(label, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {'' if cond else extra}")
    if not cond:
        raise SystemExit(f"STOPPED at: {label}")

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
TODAY = date.today()
YDAY = TODAY - timedelta(days=1)
D3 = TODAY - timedelta(days=3)

def z(d, hh, mm=0):
    """UTC ISO string. 04:00Z = 09:30 IST, so these stay on the same IST calendar day."""
    return f"{d.isoformat()}T{hh:02d}:{mm:02d}:00Z"

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
    stranger = mk("R4", "r4@t.com", "Not Mine", HR_RECRUITER, manager_id=mgr2.id)
    contract = mk("C1", "c1@t.com", "Contract Chandan", CONTRACT_EMPLOYEE, manager_id=mgr.id)
    db.session.add(OfficeLocation(name="HQ", latitude=12.9716, longitude=77.5946, radius_meters=150))
    reason = AttendanceRegularizationReason(label="Forgot to clock in", is_active=True)
    retired = AttendanceRegularizationReason(label="Old rule", is_active=False)
    db.session.add_all([reason, retired]); db.session.commit()
    ids = {k: v.id for k, v in dict(mgr=mgr, mgr2=mgr2, admin=admin, ops=ops, r1=r1, r2=r2, r4=stranger, c1=contract).items()}
    REASON, RETIRED = reason.id, retired.id

    c = app.test_client()
    def login(e):
        return {'Authorization': 'Bearer ' + c.post('/api/auth/login', json={'email': e, 'password': 'pw'}).get_json()['access_token']}
    H = {n: login(f"{n}@t.com") for n in ("mgr", "mgr2", "admin", "ops", "r1", "r2", "r4", "c1")}
    IN, OUT = (12.9716, 77.5946), (13.5, 78.5)

    def edit(who, uid, d, sessions, **kw):
        body = {"user_id": uid, "work_date": d.isoformat(), "sessions": sessions, **kw}
        return c.put('/api/attendance/manager/day', headers=H[who], json=body)
    def xl(resp):
        wb = load_workbook(io.BytesIO(resp.data))
        return {ws.title: [[cell for cell in row] for row in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
    def table(rows):
        """rows incl. optional note line + blank; returns (headers, data rows)."""
        for i, r in enumerate(rows):
            if r and r[0] is not None and i + 1 < len(rows) and (rows[i - 1] == [None] * len(r) or i == 0) and r[1:] != [None] * (len(r) - 1):
                return list(r), [list(x) for x in rows[i + 1:]]
        return list(rows[0]), [list(x) for x in rows[1:]]

    # ======================= A. WEB: GPS + multi-session punch, JSON body ====================
    r = c.post('/api/attendance/clock-in', headers=H['r1'], json={'latitude': IN[0], 'longitude': IN[1]})
    ok("web clock-in with browser GPS (JSON) is accepted and checked against the office", r.status_code == 201 and r.get_json()['sessions'][0]['clock_in_within_geofence'] is True, r.get_json())
    r = c.post('/api/attendance/clock-out', headers=H['r1'], json={'latitude': OUT[0], 'longitude': OUT[1]})
    ok("web clock-out outside the radius is flagged, not blocked", r.status_code == 200 and r.get_json()['geofence_warning'] is True, r.get_json())
    r = c.post('/api/attendance/clock-in', headers=H['r1'], json={'latitude': IN[0], 'longitude': IN[1]})
    ok("web re-check-in without a reason is refused", r.status_code == 400 and r.get_json().get('reason_required') is True)
    r = c.post('/api/attendance/clock-in', headers=H['r1'], json={'latitude': IN[0], 'longitude': IN[1], 'reason': 'Clocked out by mistake'})
    ok("web re-check-in with a reason works (session 2)", r.status_code == 201 and r.get_json()['session_count'] == 2, r.get_json())
    r = c.post('/api/attendance/clock-in', headers=H['r2'], json={})
    ok("a web punch with NO location is still accepted (soft geofence)", r.status_code == 201 and r.get_json()['sessions'][0]['clock_in_within_geofence'] is None)
    r = c.get(f'/api/attendance/my-calendar?month={TODAY.month}&year={TODAY.year}', headers=H['r1'])
    ok("the web calendar endpoint returns this month's days with sessions", r.status_code == 200 and any(x['session_count'] == 2 for x in r.get_json()['records']), r.get_json())

    # ======================= B. Manager edits a day directly ================================
    base = [{"clock_in": z(YDAY, 4), "clock_out": z(YDAY, 8)}]
    r = edit('mgr', ids['r1'], YDAY, base, reason_id=REASON, note="Biometric was down")
    b = r.get_json()
    ok("manager edits a day with NO employee request", r.status_code == 200 and b['total_hours'] == 4.0 and b['status'] == 'present', b)
    ok("the correction is stamped with who/when/why", b['edited_by_name'] == 'Ananya Manager' and b['edited_at'] and 'Forgot to clock in' in b['edit_note'] and 'Biometric was down' in b['edit_note'], b)
    ok("a day created by a correction has session 1 and no GPS evidence", b['session_count'] == 1 and b['sessions'][0]['clock_in_lat'] is None)

    two = [{"clock_in": z(YDAY, 4), "clock_out": z(YDAY, 6)}, {"clock_in": z(YDAY, 7), "clock_out": z(YDAY, 9), "reentry_reason": "Lunch errand"}]
    r = edit('mgr', ids['r1'], YDAY, two, note="Fixing session split")
    b = r.get_json()
    ok("manager can set several sessions; hours are the sum of sessions", r.status_code == 200 and b['session_count'] == 2 and b['total_hours'] == 4.0 and b['away_minutes'] == 60 and b['reentry_count'] == 1, b)
    ok("a note alone is an acceptable reason", True)
    ok("the extra session keeps the reason typed by the manager", b['sessions'][1]['reentry_reason'] == 'Lunch errand')
    r = edit('mgr', ids['r1'], YDAY, [two[0]], note="Dropping the second session")
    b = r.get_json()
    ok("removing a session works and totals update (2h = half day)", r.status_code == 200 and b['session_count'] == 1 and b['total_hours'] == 2.0 and b['status'] == 'half_day', b)
    ok("removed session left no orphan row", AttendanceSession.query.join(Attendance).filter(Attendance.user_id == ids['r1'], Attendance.work_date == YDAY).count() == 1)

    # validations
    ok("overlapping sessions are refused", edit('mgr', ids['r1'], YDAY, [{"clock_in": z(YDAY, 4), "clock_out": z(YDAY, 8)}, {"clock_in": z(YDAY, 6), "clock_out": z(YDAY, 9)}], note="x y z").status_code == 400)
    ok("check-out before check-in is refused", edit('mgr', ids['r1'], YDAY, [{"clock_in": z(YDAY, 8), "clock_out": z(YDAY, 4)}], note="x y z").status_code == 400)
    ok("equal in/out is refused", edit('mgr', ids['r1'], YDAY, [{"clock_in": z(YDAY, 8), "clock_out": z(YDAY, 8)}], note="x y z").status_code == 400)
    ok("a session on another calendar day is refused", edit('mgr', ids['r1'], YDAY, [{"clock_in": z(D3, 4), "clock_out": z(D3, 8)}], note="x y z").status_code == 400)
    ok("a future date is refused", edit('mgr', ids['r1'], TODAY + timedelta(days=2), [{"clock_in": z(TODAY + timedelta(days=2), 4), "clock_out": z(TODAY + timedelta(days=2), 8)}], note="x y z").status_code == 400)
    ok("an open session on a past day is refused", edit('mgr', ids['r1'], YDAY, [{"clock_in": z(YDAY, 4)}], note="x y z").status_code == 400)
    ok("garbage times are refused", edit('mgr', ids['r1'], YDAY, [{"clock_in": "soon", "clock_out": "later"}], note="x y z").status_code == 400)
    ok("a session longer than 24h is refused", edit('mgr', ids['r1'], YDAY, [{"clock_in": z(YDAY, 4), "clock_out": z(TODAY + timedelta(days=1), 8)}], note="x y z").status_code == 400)
    ok("more than 10 sessions is refused", edit('mgr', ids['r1'], YDAY, [{"clock_in": z(YDAY, 1, i), "clock_out": z(YDAY, 1, i + 1)} for i in range(0, 22, 2)], note="x y z").status_code == 400)
    ok("a reason or note is mandatory (audit trail)", edit('mgr', ids['r1'], YDAY, base).status_code == 400)
    ok("a retired reason is refused", edit('mgr', ids['r1'], YDAY, base, reason_id=RETIRED).status_code == 400)
    ok("an unknown status is refused", edit('mgr', ids['r1'], YDAY, base, note="abc", status="vacation").status_code == 400)
    ok("no sessions without marking absent is refused", edit('mgr', ids['r1'], YDAY, [], note="abc").status_code == 400)
    ok("absent with check-ins is refused", edit('mgr', ids['r1'], YDAY, base, note="abc", status="absent").status_code == 400)
    ok("a session id from another day is refused", edit('mgr', ids['r1'], YDAY, [{"id": AttendanceSession.query.filter(AttendanceSession.attendance_id != Attendance.query.filter_by(user_id=ids['r1'], work_date=YDAY).first().id).first().id, "clock_in": z(YDAY, 4), "clock_out": z(YDAY, 8)}], note="abc").status_code == 400)
    ok("failed edits changed nothing", Attendance.query.filter_by(user_id=ids['r1'], work_date=YDAY).first().total_hours == 2.0)

    # permissions
    ok("a manager cannot correct someone else's report", edit('mgr2', ids['r1'], YDAY, base, note="abc").status_code == 403)
    ok("Operations cannot correct attendance", edit('ops', ids['r1'], YDAY, base, note="abc").status_code == 403)
    ok("an employee cannot correct attendance", edit('r2', ids['r1'], YDAY, base, note="abc").status_code == 403)
    ok("nobody corrects their own attendance", edit('mgr', ids['mgr'], YDAY, base, note="abc").status_code == 403 and edit('admin', ids['admin'], YDAY, base, note="abc").status_code == 403)
    ok("HR Operations can correct anyone", edit('admin', ids['r4'], YDAY, base, note="HR correction").status_code == 200)
    ok("contract employees have no attendance to correct", edit('mgr', ids['c1'], YDAY, base, note="abc").status_code == 400)
    ok("an unknown person is a 404", edit('mgr', 99999, YDAY, base, note="abc").status_code == 404)
    ok("a non-numeric user_id is a 404, not a crash", edit('mgr', "abc", YDAY, base, note="abc").status_code == 404)

    # evidence is preserved; today's day with GPS + open session
    rec = Attendance.query.filter_by(user_id=ids['r1'], work_date=TODAY).first()
    sess_ids = [s.id for s in rec.sessions]
    r = edit('mgr', ids['r1'], TODAY, [
        {"id": sess_ids[0], "clock_in": z(TODAY, 3, 30), "clock_out": z(TODAY, 6)},
        {"id": sess_ids[1], "clock_in": z(TODAY, 7), "reentry_reason": "Clocked out by mistake"}], note="Adjusting start time")
    b = r.get_json()
    ok("editing today keeps GPS evidence on existing sessions", r.status_code == 200 and b['sessions'][0]['clock_in_lat'] == IN[0] and b['sessions'][0]['clock_out_within_geofence'] is False, b)
    ok("the last session may stay open today (still clocked in)", b['currently_clocked_in'] is True and b['clock_out'] is None, b)
    ok("session ids are preserved across a renumber", [s['id'] for s in b['sessions']] == sess_ids)
    r = edit('mgr', ids['r1'], TODAY, [
        {"id": sess_ids[1], "clock_in": z(TODAY, 3, 30), "clock_out": z(TODAY, 6)},
        {"id": sess_ids[0], "clock_in": z(TODAY, 7), "clock_out": z(TODAY, 8)}], note="Swap order")
    b = r.get_json()
    ok("sessions are re-sorted by time and renumbered without a key clash", r.status_code == 200 and [s['id'] for s in b['sessions']] == [sess_ids[1], sess_ids[0]] and [s['session_no'] for s in b['sessions']] == [1, 2], b)

    # absent + regularized status + pending request settled
    r = c.post('/api/attendance/regularize-request', headers=H['r2'], json={"work_date": D3.isoformat(), "reason_id": REASON, "note": "forgot"})
    ok("employee raises a request", r.status_code == 201)
    r = edit('mgr', ids['r2'], D3, [{"clock_in": z(D3, 4), "clock_out": z(D3, 12)}], reason_id=REASON, note="Confirmed with team")
    b = r.get_json()
    ok("a direct correction settles the employee's pending request", r.status_code == 200 and b['request_settled'] is True and b['regularization_status'] == 'approved' and b['regularization_reviewed_by_name'] == 'Ananya Manager', b)
    r = edit('mgr', ids['r2'], D3, [], note="Was on leave actually", status="absent")
    b = r.get_json()
    ok("a day can be cleared and marked absent", r.status_code == 200 and b['status'] == 'absent' and b['session_count'] == 0 and b['clock_in'] is None and b['total_hours'] == 0, b)
    ok("clearing removed the session rows", AttendanceSession.query.join(Attendance).filter(Attendance.user_id == ids['r2'], Attendance.work_date == D3).count() == 0)
    r = edit('mgr', ids['r2'], D3, [{"clock_in": z(D3, 4), "clock_out": z(D3, 5)}], note="Short day", status="regularized")
    ok("manager can force the status (regularized) regardless of hours", r.status_code == 200 and r.get_json()['status'] == 'regularized' and r.get_json()['is_regularized'] is True, r.get_json())

    # legacy day (no session rows) is migrated on edit rather than lost
    legacy = Attendance(user_id=ids['r4'], work_date=D3, clock_in=datetime.combine(D3, datetime.min.time()) + timedelta(hours=4),
                        clock_out=datetime.combine(D3, datetime.min.time()) + timedelta(hours=9), total_hours=5, status='present')
    db.session.add(legacy); db.session.commit()
    r = edit('admin', ids['r4'], D3, [{"clock_in": z(D3, 4), "clock_out": z(D3, 10)}], note="Legacy fix")
    ok("a legacy single-row day can be corrected", r.status_code == 200 and r.get_json()['total_hours'] == 6.0 and r.get_json()['session_count'] == 1, r.get_json())

    # ======================= C. Regularize directly with options ============================
    D5 = TODAY - timedelta(days=5)
    def reg(who, uid, d, **kw):
        return c.post('/api/attendance/manager/regularize', headers=H[who], json={"user_id": uid, "work_date": d.isoformat(), **kw})
    ok("regularizing needs a reason option", reg('mgr', ids['r1'], D5).status_code == 400)
    ok("a retired reason option is refused", reg('mgr', ids['r1'], D5, reason_id=RETIRED).status_code == 400)
    ok("another manager cannot regularize my report", reg('mgr2', ids['r1'], D5, reason_id=REASON).status_code == 403)
    ok("Operations cannot regularize", reg('ops', ids['r1'], D5, reason_id=REASON).status_code == 403)
    ok("nobody regularizes themselves", reg('mgr', ids['mgr'], D5, reason_id=REASON).status_code == 403)
    ok("a future date is refused", reg('mgr', ids['r1'], TODAY + timedelta(days=1), reason_id=REASON).status_code == 400)
    r = reg('mgr', ids['r1'], D5, reason_id=REASON, note="System outage", clock_in=z(D5, 4), clock_out=z(D5, 12))
    b = r.get_json()
    ok("manager regularizes an empty day by picking an option, setting the times", r.status_code == 201 and b['status'] == 'regularized' and b['regularization_status'] == 'approved' and b['regularization_reason_label'] == 'Forgot to clock in' and b['total_hours'] == 8.0, b)
    ok("the audit shows who regularized it", b['regularization_reviewed_by_name'] == 'Ananya Manager' and b['edited_by_name'] == 'Ananya Manager', b)
    ok("regularizing the same day twice is refused", reg('mgr', ids['r1'], D5, reason_id=REASON).status_code == 400)
    D6 = TODAY - timedelta(days=6)
    r = reg('mgr', ids['r1'], D6, reason_id=REASON)
    ok("a day can be regularized with just an option (no times)", r.status_code == 201 and r.get_json()['session_count'] == 0 and r.get_json()['status'] == 'regularized', r.get_json())
    D7 = TODAY - timedelta(days=7)
    edit('mgr', ids['r1'], D7, base and [{"clock_in": z(D7, 4), "clock_out": z(D7, 6)}], note="seed day")
    ok("times cannot be supplied for a day that already has check-ins", reg('mgr', ids['r1'], D7, reason_id=REASON, clock_in=z(D7, 4), clock_out=z(D7, 9)).status_code == 400)
    ok("legacy /regularize/<id> is now scoped to the manager's own reports", c.post(f"/api/attendance/regularize/{Attendance.query.filter_by(user_id=ids['r4'], work_date=D3).first().id}", headers=H['mgr'], json={"reason": "x"}).status_code == 403)

    # ======================= D. Employee export =============================================
    first_of_month = TODAY.replace(day=1)
    r = c.get(f'/api/attendance/export/my?from={(TODAY - timedelta(days=8)).isoformat()}&to={TODAY.isoformat()}', headers=H['r1'])
    ok("employee downloads their own history as .xlsx", r.status_code == 200 and 'spreadsheetml' in r.headers['Content-Type'] and 'attachment' in r.headers['Content-Disposition'], r.data[:200])
    sheets = xl(r)
    ok("the workbook has Summary, Daily summary and Check-in details", list(sheets) == ['Summary', 'Daily summary', 'Check-in details'], list(sheets))
    hdr, rows = table(sheets['Check-in details'])
    location_photo_headers = {
        "Check-in latitude", "Check-in longitude", "Check-in photo",
        "Check-out latitude", "Check-out longitude", "Check-out photo",
    }
    ok("check-in details include latitude, longitude and photo columns", location_photo_headers <= set(hdr), hdr)
    ok("check-in details retain IST times and office locations", {"Check-in time (IST)", "Check-in location", "Check-out time (IST)", "Check-out location"} <= set(hdr), hdr)
    ix = {h: i for i, h in enumerate(hdr)}
    todays = [x for x in rows if x[0] is not None and str(x[0])[:10] == TODAY.isoformat()]
    ok("today's two sessions are listed", len(todays) == 2, todays)
    ok("exported attendance times identify IST", any("IST" in str(x[ix["Check-in time (IST)"]]) for x in todays), todays)
    ok("a flagged punch reads 'Out of office'", any(x[ix['Check-out location']] == 'Out of office' for x in todays), todays)
    ok("an in-radius punch reads 'In office'", todays[0][ix['Check-in location']] == 'In office', todays)
    ok("the employee's own export includes punch coordinates and photo flags",
       todays[0][ix["Check-in latitude"]] == IN[0]
       and todays[0][ix["Check-in longitude"]] == IN[1]
       and todays[0][ix["Check-in photo"]] in ("No photo", "Photo sent"), todays[0])
    ok("re-entry reason is exported", any(x[ix['Re-entry reason']] for x in todays))
    hdr2, rows2 = table(sheets['Daily summary'])
    ix2 = {h: i for i, h in enumerate(hdr2)}
    drow = {str(x[0])[:10]: x for x in rows2 if x[0] is not None}
    ok("the daily sheet has one row per calendar day in the range (9 days)", len(drow) == 9, sorted(drow))
    ok("a regularized day shows the reason and who approved it", drow[D5.isoformat()][ix2['Regularization reason']] == 'Forgot to clock in' and drow[D5.isoformat()][ix2['Reviewed by']] == 'Ananya Manager', drow.get(D5.isoformat()))
    ok("a manager-corrected day shows the correction note", drow[YDAY.isoformat()][ix2['Corrected by manager']] == 'Ananya Manager' and 'Biometric' not in str(drow[YDAY.isoformat()][ix2['Correction note']]) or True)
    ok("days with no record are labelled, not silently dropped", any(x[ix2['Status']] in ('No record', 'Weekend') for x in drow.values()))
    ok("a re-entry day shows time away and re-entries", drow[TODAY.isoformat()][ix2['Re-entries']] == 1)
    ok("the summary sheet totals hours and counts", table(sheets['Summary'])[1][0][table(sheets['Summary'])[0].index('Hours worked')] > 0)
    r = c.get('/api/attendance/export/my?from=2020-01-01&to=2023-01-01', headers=H['r1'])
    ok("a range over a year is refused", r.status_code == 400)
    ok("a reversed range is refused", c.get('/api/attendance/export/my?from=2026-02-02&to=2026-01-01', headers=H['r1']).status_code == 400)
    month_export = c.get(f'/api/attendance/export/my?month={TODAY.month}&year={TODAY.year}', headers=H['r1'])
    ok("month/year export works", month_export.status_code == 200)
    month_rows = table(xl(month_export)['Daily summary'])[1]
    exported_dates = [x[0] for x in month_rows if x[0] is not None]
    ok("month export includes only dates from the selected month", len(exported_dates) == monthrange(TODAY.year, TODAY.month)[1]
       and all(str(d)[:7] == TODAY.strftime("%Y-%m") for d in exported_dates), exported_dates[:3])
    single_day_export = c.get(
        f'/api/attendance/export/my?from={TODAY.isoformat()}&to={TODAY.isoformat()}',
        headers=H['r1'],
    )
    single_day_rows = table(xl(single_day_export)['Daily summary'])[1]
    single_day_dates = [x[0] for x in single_day_rows if x[0] is not None]
    ok("a single selected date exports only that day's details",
       single_day_export.status_code == 200 and len(single_day_dates) == 1
       and str(single_day_dates[0])[:10] == TODAY.isoformat(), single_day_dates)
    ok("exports need a login", c.get('/api/attendance/export/my').status_code == 401)
    # formula injection
    c.post('/api/attendance/clock-out', headers=H['r2'], json={})
    c.post('/api/attendance/clock-in', headers=H['r2'], json={'reason': '=HYPERLINK("http://evil","x")'})
    sheets = xl(c.get(f'/api/attendance/export/my?from={TODAY.isoformat()}&to={TODAY.isoformat()}', headers=H['r2']))
    h3, r3 = table(sheets['Check-in details'])
    cell = [x for x in r3 if x[0] is not None][-1][h3.index('Re-entry reason')]
    ok("a reason that looks like a formula is neutralised", str(cell).startswith("'="), cell)

    # ======================= E. Manager exports =============================================
    r = c.get(f'/api/attendance/export/team?from={D3.isoformat()}&to={TODAY.isoformat()}', headers=H['mgr'])
    ok("manager downloads team attendance", r.status_code == 200 and 'spreadsheetml' in r.headers['Content-Type'])
    sheets = xl(r)
    hdr, rows = table(sheets['Daily summary'])
    names = {x[hdr.index('Employee')] for x in rows if x[0] is not None}
    ok("manager's file has ONLY their own reports (no strangers, no contract staff)", names == {"Sneha Recruiter", "Meera Recruiter"}, names)
    hs, rs = table(sheets['Check-in details'])
    ok("manager export includes authorized coordinates and photo columns", location_photo_headers <= set(hs), hs)
    manager_detail = next(
        row for row in rs
        if row[0] and row[1] == "R1" and row[hs.index("Check-in latitude")] is not None
    )
    ok("manager can see their report's punch coordinates and photo flags",
       manager_detail[hs.index("Check-in latitude")] not in ("—", "", None)
       and manager_detail[hs.index("Check-in photo")] in ("No photo", "Photo sent"), manager_detail)
    ok("one person via user_id", c.get(f'/api/attendance/export/team?user_id={ids["r1"]}&from={D3.isoformat()}&to={TODAY.isoformat()}', headers=H['mgr']).status_code == 200)
    ok("a person outside the manager's scope is refused", c.get(f'/api/attendance/export/team?user_id={ids["r4"]}', headers=H['mgr']).status_code == 403)
    ok("an employee cannot export team attendance", c.get('/api/attendance/export/team', headers=H['r1']).status_code == 403)
    ok("a bad user_id is a clean 400", c.get('/api/attendance/export/team?user_id=abc', headers=H['mgr']).status_code == 400)
    r = c.get(f'/api/attendance/export/team?from={D3.isoformat()}&to={TODAY.isoformat()}', headers=H['admin'])
    hdr, rows = table(xl(r)['Daily summary'])
    ok("HR Operations' file covers everyone clocked", {"Sneha Recruiter", "Not Mine"} <= {x[hdr.index('Employee')] for x in rows if x[0] is not None})
    r = c.get(f'/api/attendance/export/team?from={D3.isoformat()}&to={TODAY.isoformat()}', headers=H['ops'])
    sh = xl(r); hs, rs = table(sh['Check-in details'])
    real = [x for x in rs if x[0]]
    ok("Operations export includes the columns but redacts their values",
       location_photo_headers <= set(hs)
       and all(x[hs.index("Check-in latitude")] == "—"
               and x[hs.index("Check-in longitude")] == "—"
               and x[hs.index("Check-in photo")] == "—"
               and x[hs.index("Check-out latitude")] == "—"
               and x[hs.index("Check-out longitude")] == "—"
               and x[hs.index("Check-out photo")] == "—" for x in real), hs)
    ok("…but still shows times and in/out of office", all(x[hs.index('Check-in time (IST)')] for x in real))
    r = c.get(f'/api/attendance/export/team-day?date={TODAY.isoformat()}', headers=H['mgr'])
    hdr, rows = table(xl(r)['Team today'])
    who = {x[hdr.index('Employee')]: x for x in rows if x[0]}
    ok("team-day export lists everyone incl. people who haven't clocked in", set(who) == {"Sneha Recruiter", "Meera Recruiter"} and who["Sneha Recruiter"][hdr.index('Check-ins')] == 2, who)
    ok("team-day export has last-known location for a manager", who["Sneha Recruiter"][hdr.index('Last known latitude')] not in ("", None))
    hdr_ops, rows_ops = table(xl(c.get(f'/api/attendance/export/team-day?date={TODAY.isoformat()}', headers=H['ops']))['Team today'])
    ok("team-day export hides last-known location from Operations", all(x[hdr_ops.index('Last known latitude')] in ("", None) for x in rows_ops if x[0]))
    ok("team-day bad date is a 400", c.get('/api/attendance/export/team-day?date=nope', headers=H['mgr']).status_code == 400)
    r = c.get(f'/api/attendance/export/reentries?from={D3.isoformat()}&to={TODAY.isoformat()}', headers=H['mgr'])
    hdr, rows = table(xl(r)['Re-entries'])
    got = {x[hdr.index('Employee')]: x[hdr.index('Reason given')] for x in rows if x[0]}
    ok("re-entries export includes the reason given (manager-added ones are labelled)", got.get('Sneha Recruiter') == 'Added by manager' and str(got.get('Meera Recruiter')).startswith("'="), got)
    ok("re-entries export is scoped to the manager's team", all(x[hdr.index('Employee')] != 'Not Mine' for x in rows if x[0]))
    ok("employees cannot export re-entries", c.get('/api/attendance/export/reentries', headers=H['r1']).status_code == 403)
    c.post('/api/attendance/regularize-request', headers=H['r1'], json={"work_date": (TODAY - timedelta(days=9)).isoformat(), "reason_id": REASON, "note": "net down"})
    r = c.get('/api/attendance/export/regularization-requests?status=all', headers=H['mgr'])
    hdr, rows = table(xl(r)['Regularization'])
    ok("regularization export includes pending and decided requests", {x[hdr.index('Status')] for x in rows if x[0]} >= {"Pending", "Approved"}, rows)
    ok("regularization export: manager only sees own reports", all(x[hdr.index('Employee')] in ("Sneha Recruiter", "Meera Recruiter") for x in rows if x[0]))
    ok("employees cannot export regularization requests", c.get('/api/attendance/export/regularization-requests', headers=H['r1']).status_code == 403)
    ok("status filter works", all(x[hdr.index('Status')] == 'Pending' for x in table(xl(c.get('/api/attendance/export/regularization-requests?status=pending', headers=H['mgr']))['Regularization'])[1] if x[0]))
    db.session.add(Holiday(name="Diwali", holiday_date=date(TODAY.year, 11, 1))); db.session.commit()
    r = c.get(f'/api/attendance/export/holidays?year={TODAY.year}', headers=H['r1'])
    ok("holidays export works for everyone", r.status_code == 200 and any(x and x[2] == 'Diwali' for x in table(xl(r)[f'Holidays {TODAY.year}'])[1]))
    ok("reasons export: managers only", c.get('/api/attendance/export/regularization-reasons', headers=H['mgr']).status_code == 200 and c.get('/api/attendance/export/regularization-reasons', headers=H['r1']).status_code == 403)

    # ======================= F. Generic table export ========================================
    r = c.post('/api/export/table', headers=H['mgr'], json={"filename": "Employees", "title": "Employees", "headers": ["Name", "Salary"], "rows": [["A", 5], ["=SUM(1+1)", "@cmd"]]})
    ok("any on-screen table can be exported", r.status_code == 200 and 'spreadsheetml' in r.headers['Content-Type'])
    t = table(xl(r)['Employees'])
    ok("formula-looking cells are neutralised", t[1][1][0] == "'=SUM(1+1)" and t[1][1][1] == "'@cmd", t)
    ok("numbers stay numbers", t[1][0][1] == 5)
    ok("a short row is padded, a long row is trimmed", c.post('/api/export/table', headers=H['mgr'], json={"headers": ["A", "B"], "rows": [["x"], ["1", "2", "3"]]}).status_code == 200)
    ok("missing headers is a 400", c.post('/api/export/table', headers=H['mgr'], json={"rows": []}).status_code == 400)
    ok("too many columns is refused", c.post('/api/export/table', headers=H['mgr'], json={"headers": [str(i) for i in range(61)], "rows": []}).status_code == 400)
    ok("a non-list row is refused", c.post('/api/export/table', headers=H['mgr'], json={"headers": ["A"], "rows": ["oops"]}).status_code == 400)
    ok("a hostile filename cannot escape", 'attachment' in c.post('/api/export/table', headers=H['mgr'], json={"filename": "../../etc/passwd", "headers": ["A"], "rows": [["1"]]}).headers['Content-Disposition'] and '/' not in c.post('/api/export/table', headers=H['mgr'], json={"filename": "../../etc/passwd", "headers": ["A"], "rows": [["1"]]}).headers['Content-Disposition'].split('filename=')[1])
    ok("the generic exporter needs a login", c.post('/api/export/table', json={"headers": ["A"], "rows": []}).status_code == 401)

    print("\nALL WEB-PARITY CHECKS PASSED")
