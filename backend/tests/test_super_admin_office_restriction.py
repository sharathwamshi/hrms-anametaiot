import sys, tempfile
sys.path.insert(0, '.')
from config import Config

class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True
    SELFIE_FOLDER = tempfile.mkdtemp(prefix="selfies_sa_")

from app import create_app
from app.extensions import db
from app.models import User, Department, CompanySettings, OfficeLocation, AttendanceRegularizationReason, Attendance
from app.roles import HR_OPERATIONS, HR_RECRUITER, MANAGER, OPERATIONS, EMPLOYEE, SUPER_ADMIN, ALL_ROLES, ROLE_LABELS
from datetime import date, timedelta
from io import BytesIO
from openpyxl import load_workbook

app = create_app(TestConfig)
N = [0]
def ok(label, cond, extra=""):
    N[0] += 1
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {'' if cond else extra}")
    if not cond:
        raise SystemExit(f"STOPPED at: {label}")

with app.app_context():
    db.create_all()
    db.session.add(CompanySettings(company_name="AnametaIOT", state="Karnataka"))
    dept = Department(name="Eng"); db.session.add(dept); db.session.flush()
    def mk(code, email, name, role, manager_id=None):
        u = User(employee_code=code, full_name=name, email=email, role=role, department_id=dept.id, manager_id=manager_id, date_of_joining=date(2024, 1, 1))
        u.set_password("pw"); db.session.add(u); db.session.flush(); return u
    sa = mk("S1", "sa@t.com", "Sia SuperAdmin", SUPER_ADMIN)
    sa2 = mk("S2", "sa2@t.com", "Sam SuperAdmin", SUPER_ADMIN)
    mgr = mk("M1", "mgr@t.com", "Ananya Manager", MANAGER)
    mgr2 = mk("M2", "mgr2@t.com", "Other Manager", MANAGER)
    hr = mk("A1", "hr@t.com", "Priya HR", HR_OPERATIONS)
    ops = mk("O1", "ops@t.com", "Oscar Ops", OPERATIONS)
    e1 = mk("E1", "e1@t.com", "Kiran Employee", EMPLOYEE, mgr.id)
    e2 = mk("E2", "e2@t.com", "Other Employee", EMPLOYEE, mgr2.id)
    reason = AttendanceRegularizationReason(label="Forgot to clock in", is_active=True)
    db.session.add(reason); db.session.commit()
    ids = dict(sa=sa.id, sa2=sa2.id, mgr=mgr.id, mgr2=mgr2.id, hr=hr.id, ops=ops.id, e1=e1.id, e2=e2.id); RID = reason.id
    c = app.test_client()
    H = {n: {'Authorization': 'Bearer ' + c.post('/api/auth/login', json={'email': f'{n}@t.com', 'password': 'pw'}).get_json()['access_token']} for n in ids}
    T = date.today(); TS = T.isoformat()
    HQ, FAR = (12.9716, 77.5946), (13.5, 78.5)
    def pj(path, who, body=None, m="post"): return getattr(c, m)(path, json=body or {}, headers=H[who])
    def punch(who, kind, pos=None, **extra):
        body = dict(extra)
        if pos: body.update(latitude=pos[0], longitude=pos[1])
        return pj(f"/api/attendance/{kind}", who, body)

    # ---------------- Role basics ----------------
    ok("S1 super_admin is a known role with a label", SUPER_ADMIN in ALL_ROLES and ROLE_LABELS[SUPER_ADMIN] == "Super Admin")
    me = c.get("/api/auth/me", headers=H["sa"]).get_json()
    ok("S2 super admin signs in and /me shows the role", me["user"]["role"] == "super_admin" and me["role_label"] == "Super Admin", me)

    # ---------------- Office locations: Super Admin only ----------------
    body = {"name": "Bengaluru HQ", "latitude": HQ[0], "longitude": HQ[1], "radius_meters": 150}
    ok("S3 Super Admin adds an office geofence", pj("/api/attendance/office-locations", "sa", body).status_code == 201)
    for who in ("mgr", "hr", "ops", "e1"):
        ok(f"S4 {who} cannot add an office location", pj("/api/attendance/office-locations", who, {**body, "name": "X"}).status_code == 403)
    lid = c.get("/api/attendance/office-locations", headers=H["e1"]).get_json()[0]["id"]
    ok("S5 everyone can still READ office locations (the app needs them)", len(c.get("/api/attendance/office-locations", headers=H["e1"]).get_json()) == 1)
    ok("S6 manager cannot edit or delete one", pj(f"/api/attendance/office-locations/{lid}", "mgr", {"radius_meters": 5000}, "put").status_code == 403 and c.delete(f"/api/attendance/office-locations/{lid}", headers=H["mgr"]).status_code == 403)
    ok("S7 Super Admin edits the radius", pj(f"/api/attendance/office-locations/{lid}", "sa", {"radius_meters": 200}, "put").get_json()["radius_meters"] == 200)

    # ---------------- Overall access ----------------
    ok("S8 Super Admin sees everyone in the team overview", len(c.get(f"/api/attendance/team/overview?date={TS}", headers=H["sa"]).get_json()["people"]) >= 6)
    punch("e2", "clock-in", HQ)           # a person who reports to the OTHER manager
    ov = c.get(f"/api/attendance/team/overview?date={TS}", headers=H["sa"]).get_json()["people"]
    row = [p for p in ov if p["user"]["id"] == ids["e2"]][0]
    ok("S9 ...with exact locations (same privilege as HR Ops)", row["last_known_location"] and abs(row["last_known_location"]["latitude"] - HQ[0]) < 1e-6, row)
    opsrow = [p for p in c.get(f"/api/attendance/team/overview?date={TS}", headers=H["ops"]).get_json()["people"] if p["user"]["id"] == ids["e2"]][0]
    ok("S10 Operations still sees no coordinates", opsrow["last_known_location"] is None)
    ok("S11 Super Admin opens any person's calendar", c.get(f"/api/attendance/team/{ids['e2']}/calendar?month={T.month}&year={T.year}", headers=H["sa"]).status_code == 200)
    ok("S12 manager still limited to their own reports", c.get(f"/api/attendance/team/{ids['e2']}/calendar?month={T.month}&year={T.year}", headers=H["mgr"]).status_code == 403)
    ok("S13 Super Admin edits anyone's day", pj("/api/attendance/manager/regularize", "sa", {"user_id": ids["e1"], "work_date": (T - timedelta(days=2)).isoformat(), "reason_id": RID}).status_code == 201)
    ok("S14 Super Admin cannot correct their OWN attendance", pj("/api/attendance/manager/regularize", "sa", {"user_id": ids["sa"], "work_date": (T - timedelta(days=2)).isoformat(), "reason_id": RID}).status_code == 403)
    # request review across teams
    pj("/api/attendance/regularize-request", "e2", {"work_date": (T - timedelta(days=3)).isoformat(), "reason_id": RID, "note": "x"})
    pend = c.get("/api/attendance/regularization-requests?status=pending", headers=H["sa"]).get_json()
    ok("S15 Super Admin sees every team's pending requests", any(r["user_id"] == ids["e2"] for r in pend), pend)
    rid = [r for r in pend if r["user_id"] == ids["e2"]][0]["id"]
    ok("S16 ...and can approve one", pj(f"/api/attendance/regularization-requests/{rid}/approve", "sa", {"comment": "ok"}).status_code == 200)
    ok("S17 Super Admin can export team attendance", c.get("/api/attendance/export/team", headers=H["sa"]).status_code == 200)
    ok("S18 Super Admin can change the selfie policy", pj("/api/attendance/policy", "sa", {"selfie_required": False}, "put").status_code == 200)
    ok("S19 Super Admin has the HR-style dashboard", "headcount" in c.get("/api/dashboard/summary", headers=H["sa"]).get_json())

    # ---------------- Role hygiene (no privilege escalation) ----------------
    mk_body = {"employee_code": "N1", "full_name": "New Person", "email": "n1@t.com", "password": "pw12345", "role": SUPER_ADMIN}
    ok("S20 HR Ops cannot create a Super Admin", pj("/api/employees", "hr", mk_body).status_code == 403)
    ok("S21 manager cannot create a Super Admin", pj("/api/employees", "mgr", mk_body).status_code == 403)
    ok("S22 HR Ops cannot promote themselves", pj(f"/api/employees/{ids['hr']}", "hr", {"role": SUPER_ADMIN}, "put").status_code == 403)
    ok("S23 HR Ops cannot edit or demote a Super Admin", pj(f"/api/employees/{ids['sa']}", "hr", {"role": EMPLOYEE}, "put").status_code == 403 and pj(f"/api/employees/{ids['sa']}", "hr", {"designation": "x"}, "put").status_code == 403)
    ok("S24 HR Ops cannot remove a Super Admin", c.delete(f"/api/employees/{ids['sa']}", json={"reason": "x"}, headers=H["hr"]).status_code == 403)
    ok("S25 Super Admin can create another Super Admin", pj("/api/employees", "sa", mk_body).status_code == 201)
    ok("S26 Super Admin manages employees like HR Ops (edit)", pj(f"/api/employees/{ids['e1']}", "sa", {"designation": "Lead"}, "put").status_code == 200)
    ok("S27 a Super Admin can't remove their own account", c.delete(f"/api/employees/{ids['sa']}", json={"reason": "x"}, headers=H["sa"]).status_code == 400)

    # ---------------- Office-only punching ----------------
    r = punch("e1", "clock-in", FAR)
    ok("S30 default: punching far from the office is allowed but flagged (soft geofence unchanged)", r.status_code == 201 and r.get_json()["geofence_warning"] is True, r.get_json())
    punch("e1", "clock-out", FAR)
    # (e1 now has a closed session today)
    ok("S31 default flag is off", c.get("/api/attendance/today", headers=H["e1"]).get_json()["restrict_to_office"] is False)

    ok("S32 manager turns office-only ON for a direct report", pj(f"/api/attendance/team/{ids['e1']}/office-restriction", "mgr", {"restricted": True}, "put").get_json()["user"]["restrict_to_office"] is True)
    ok("S33 the employee sees the rule on /today", c.get("/api/attendance/today", headers=H["e1"]).get_json()["restrict_to_office"] is True)
    r = punch("e1", "clock-in", FAR, reason="Back again")
    ok("S34 restricted + outside office -> clock-in REFUSED with a clear message", r.status_code == 403 and r.get_json()["office_restricted"] and r.get_json()["reason"] == "outside_office" and "not at the office" in r.get_json()["message"], r.get_json())
    r = punch("e1", "clock-in", None, reason="Back again")
    ok("S35 restricted + no location sent (e.g. web) -> refused, asks to use the phone", r.status_code == 403 and r.get_json()["reason"] == "no_location", r.get_json())
    sessions_before = len(Attendance.query.filter_by(user_id=ids["e1"], work_date=T).first().sessions)
    ok("S36 nothing was recorded by the refused attempts", sessions_before == 1)
    r = punch("e1", "clock-in", HQ, reason="Back again")
    ok("S37 restricted + inside the office -> allowed", r.status_code == 201 and r.get_json()["geofence_warning"] is False, r.get_json())
    r = punch("e1", "clock-out", FAR)
    ok("S38 clock-OUT outside the office is refused too", r.status_code == 403 and r.get_json()["office_restricted"], r.get_json())
    ok("S39 ...so the session stays open until they are back", c.get("/api/attendance/today", headers=H["e1"]).get_json()["record"]["currently_clocked_in"] is True)
    ok("S40 clock-out from the office works", punch("e1", "clock-out", HQ).status_code == 200)
    # permissions
    ok("S41 another manager cannot restrict someone else's report", pj(f"/api/attendance/team/{ids['e1']}/office-restriction", "mgr2", {"restricted": False}, "put").status_code == 403)
    ok("S42 the employee cannot lift their own restriction", pj(f"/api/attendance/team/{ids['e1']}/office-restriction", "e1", {"restricted": False}, "put").status_code == 403)
    ok("S43 Operations (view-only) cannot set it", pj(f"/api/attendance/team/{ids['e1']}/office-restriction", "ops", {"restricted": False}, "put").status_code == 403)
    ok("S44 manager cannot restrict themselves", pj(f"/api/attendance/team/{ids['mgr']}/office-restriction", "mgr", {"restricted": True}, "put").status_code == 403)
    ok("S45 non-boolean value rejected", pj(f"/api/attendance/team/{ids['e1']}/office-restriction", "mgr", {"restricted": "yes"}, "put").status_code == 400)
    ok("S46 HR Ops can set it for anyone (other team)", pj(f"/api/attendance/team/{ids['e2']}/office-restriction", "hr", {"restricted": True}, "put").status_code == 200)
    ok("S47 Super Admin can lift it for anyone", pj(f"/api/attendance/team/{ids['e2']}/office-restriction", "sa", {"restricted": False}, "put").get_json()["user"]["restrict_to_office"] is False)
    ok("S48 audit: who/when recorded", User.query.get(ids["e1"]).restrict_set_by == ids["mgr"] and User.query.get(ids["e1"]).restrict_set_at is not None)
    ok("S49 the overview carries the flag for the manager's badge", [p for p in c.get(f"/api/attendance/team/overview?date={TS}", headers=H["mgr"]).get_json()["people"] if p["user"]["id"] == ids["e1"]][0]["user"]["restrict_to_office"] is True)
    # turning it off restores soft behaviour
    pj(f"/api/attendance/team/{ids['e1']}/office-restriction", "mgr", {"restricted": False}, "put")
    ok("S50 turned off -> far punches allowed again (flagged only)", punch("e1", "clock-in", FAR, reason="again").status_code == 201)
    punch("e1", "clock-out", FAR)
    # no office configured -> never lock people out
    OfficeLocation.query.delete(); db.session.commit()
    pj(f"/api/attendance/team/{ids['e1']}/office-restriction", "mgr", {"restricted": True}, "put")
    j = pj(f"/api/attendance/team/{ids['e1']}/office-restriction", "mgr", {"restricted": True}, "put").get_json()
    ok("S51 the API warns when no office exists yet", j["no_active_office"] is True)
    ok("S52 ...and a restricted person is not locked out by that missing setup", punch("e1", "clock-in", FAR, reason="again2").status_code == 201)
    # retired office doesn't count
    punch("e1", "clock-out", FAR)
    db.session.add(OfficeLocation(name="Old", latitude=HQ[0], longitude=HQ[1], radius_meters=100, is_active=False)); db.session.commit()
    ok("S53 only ACTIVE offices count (retired ones are ignored)", punch("e1", "clock-in", HQ, reason="again3").status_code == 201)

print(f"\nAll {N[0]} checks passed.")
