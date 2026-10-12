import sys
sys.path.insert(0, '.')
from config import Config
class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True
from app import create_app
from app.extensions import db
from app.models import User, Department, CompanySettings, SalaryStructure
from app.roles import HR_OPERATIONS, HR_RECRUITER, FINANCE_ACCOUNTS, MANAGER, EMPLOYEE, CONTRACT_EMPLOYEE
from datetime import date

app = create_app(TestConfig)
def ok(label, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {'' if cond else extra}")
    if not cond: raise SystemExit(f"STOPPED at: {label}")

with app.app_context():
    db.create_all()
    db.session.add(CompanySettings(company_name="AnametaIOT", state="Karnataka"))
    d = Department(name="Eng"); db.session.add(d); db.session.flush()
    def mk(code, name, role, mgr=None, active=True):
        u = User(employee_code=code, full_name=name, email=f"{code.lower()}@t.com", role=role, department_id=d.id,
                 manager_id=mgr, date_of_joining=date(2024,1,1), is_active=active)
        u.set_password("pw"); db.session.add(u); db.session.flush(); return u
    mgr = mk("M1","Ananya Manager",MANAGER); fin = mk("F1","Rahul Finance",FINANCE_ACCOUNTS)
    rec = mk("R1","Sneha Recruiter",HR_RECRUITER,mgr.id); emp = mk("E1","Kiran Employee",EMPLOYEE,mgr.id)
    con = mk("C1","Chitra Contract",CONTRACT_EMPLOYEE); gone = mk("G1","Left Company",EMPLOYEE,active=False)
    for u in (rec, mgr):
        db.session.add(SalaryStructure(user_id=u.id, basic=50000))
    db.session.commit()

    c = app.test_client()
    def hdr(e): return {'Authorization': 'Bearer ' + c.post('/api/auth/login', json={'email': e, 'password': 'pw'}).get_json()['access_token']}
    F, R = hdr('f1@t.com'), hdr('r1@t.com')

    ok("recruiter cannot see payroll coverage", c.get('/api/payroll/coverage', headers=R).status_code == 403)
    r = c.get('/api/payroll/coverage', headers=F); b = r.get_json()
    ok("Finance can", r.status_code == 200)
    names = {p['full_name'] for p in b['people']}
    ok("lists every ACTIVE user of every role (recruiter, manager, employee, contract, finance)",
       names == {"Ananya Manager","Rahul Finance","Sneha Recruiter","Kiran Employee","Chitra Contract"}, names)
    ok("inactive user excluded", "Left Company" not in names)
    ok("summary: 5 active, 2 set up, 3 would be skipped", b['summary']['total_active']==5 and b['summary']['with_structure']==2 and b['summary']['missing_structure']==3, b['summary'])
    by = {p['full_name']: p for p in b['people']}
    ok("recruiter shows salary + manager", by["Sneha Recruiter"]['has_structure'] and by["Sneha Recruiter"]['monthly_gross']==50000 and by["Sneha Recruiter"]['manager_name']=="Ananya Manager", by["Sneha Recruiter"])
    ok("unset user flagged 'missing'", by["Kiran Employee"]['payroll_state']=="missing")

    ok("filter payroll=missing", {p['full_name'] for p in c.get('/api/payroll/coverage?payroll=missing', headers=F).get_json()['people']} == {"Rahul Finance","Kiran Employee","Chitra Contract"})
    ok("filter role=hr_recruiter", [p['full_name'] for p in c.get('/api/payroll/coverage?role=hr_recruiter', headers=F).get_json()['people']] == ["Sneha Recruiter"])

    # Same payment flow works for a recruiter: generate -> processed -> paid
    g = c.post('/api/payroll/generate', headers=F, json={'month': 6, 'year': 2026})
    ok("generate only produced payslips for people with a structure (recruiter + manager)",
       g.status_code == 200 and {p['user_id'] for p in g.get_json()} == {rec.id, mgr.id}, g.get_json())
    b = c.get('/api/payroll/coverage?month=6&year=2026', headers=F).get_json()
    by = {p['full_name']: p for p in b['people']}
    ok("coverage reflects processed payslips", by["Sneha Recruiter"]['payroll_state']=="processed" and b['summary']['payslips_processed']==2, b['summary'])
    r = c.post(f"/api/payroll/payslips/{by['Sneha Recruiter']['payslip_id']}/mark-paid", headers=F)
    b = c.get('/api/payroll/coverage?month=6&year=2026', headers=F).get_json()
    ok("marking the recruiter's payslip paid shows as paid", {p['full_name']:p for p in b['people']}["Sneha Recruiter"]['payroll_state']=="paid" and b['summary']['payslips_paid']==1, b['summary'])
print("\nALL PAYROLL COVERAGE SMOKE TESTS PASSED")
