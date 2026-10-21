import sys
sys.path.insert(0, ".")

from datetime import date, timedelta

from config import Config


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


from app import create_app
from app.extensions import db
from app.models import LeaveBalance, LeaveEntitlementAudit, LeaveRequest, LeaveType, User
from app.roles import EMPLOYEE, HR_OPERATIONS, MANAGER


app = create_app(TestConfig)


def check(label, condition, details=""):
    if not condition:
        raise AssertionError(f"{label}: {details}")


with app.app_context():
    db.create_all()

    def make_user(code, role, manager_id=None):
        user = User(
            employee_code=code,
            full_name=code,
            email=f"{code.lower()}@example.com",
            role=role,
            manager_id=manager_id,
        )
        user.set_password("password")
        db.session.add(user)
        db.session.flush()
        return user

    manager = make_user("MANAGER", MANAGER)
    other_manager = make_user("OTHER_MANAGER", MANAGER)
    hr_operations = make_user("HR_OPERATIONS", HR_OPERATIONS)
    employee = make_user("EMPLOYEE", EMPLOYEE, manager.id)
    employee2 = make_user("EMPLOYEE2", EMPLOYEE, manager.id)
    leave_type = LeaveType(name="Annual", annual_quota=3)
    db.session.add(leave_type)
    db.session.flush()
    balance = LeaveBalance(
        user_id=employee.id,
        leave_type_id=leave_type.id,
        year=date.today().year,
        allocated=5,
        used=0,
    )
    db.session.add(balance)
    db.session.add(LeaveBalance(
        user_id=employee2.id,
        leave_type_id=leave_type.id,
        year=date.today().year,
        allocated=3,
        used=0,
    ))
    db.session.commit()

    client = app.test_client()

    def auth(email):
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "password"},
        )
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    employee_headers = auth("employee@example.com")
    manager_headers = auth("manager@example.com")
    other_manager_headers = auth("other_manager@example.com")
    hr_headers = auth("hr_operations@example.com")

    own_balance = client.get("/api/leave/balances", headers=employee_headers).get_json()[0]
    check("balance reports entitlement, approved leave and remaining leave",
          own_balance["annual_entitlement"] == 5 and
          own_balance["approved_leave_taken"] == 0 and
          own_balance["remaining_leave"] == 5, own_balance)
    check("employees cannot view another employee's balance",
          client.get(f"/api/leave/balances/{employee2.id}", headers=employee_headers).status_code == 403)
    check("manager can view direct report balances",
          client.get(f"/api/leave/balances/{employee.id}", headers=manager_headers).status_code == 200)
    check("manager cannot view balances outside their team",
          client.get(f"/api/leave/balances/{employee.id}", headers=other_manager_headers).status_code == 403)
    check("only managers can read the manager team summary",
          client.get("/api/leave/team-summary", headers=employee_headers).status_code == 403)
    check("only managers can read team leave history",
          client.get("/api/leave/team-requests", headers=hr_headers).status_code == 403)
    check("HR Operations can view employee balances",
          client.get(f"/api/leave/balances/{employee2.id}", headers=hr_headers).status_code == 200)
    check("employees cannot update default leave policy",
          client.put("/api/leave/policy/defaults", headers=employee_headers,
                     json={"entitlements": [{"leave_type_id": leave_type.id, "annual_quota": 4}]}).status_code == 403)
    check("employees cannot update team leave entitlements",
          client.put("/api/leave/policy/team", headers=employee_headers,
                     json={"entitlements": [{"leave_type_id": leave_type.id, "annual_entitlement": 4}]}).status_code == 403)
    check("managers cannot update an employee outside their team",
          client.put(f"/api/leave/policy/employees/{employee.id}", headers=other_manager_headers,
                     json={"leave_type_id": leave_type.id, "annual_entitlement": 4}).status_code == 403)

    default_update = client.put(
        "/api/leave/policy/defaults",
        headers=manager_headers,
        json={"entitlements": [{"leave_type_id": leave_type.id, "annual_quota": 4}]},
    )
    check("default policy changes future allocation only",
          default_update.status_code == 200 and
          leave_type.annual_quota == 4 and
          balance.allocated == 5 and
          LeaveEntitlementAudit.query.filter_by(scope="default", leave_type_id=leave_type.id).count() == 1,
          default_update.get_json())
    check("negative policy defaults are rejected",
          client.put("/api/leave/policy/defaults", headers=manager_headers,
                     json={"entitlements": [{"leave_type_id": leave_type.id, "annual_quota": -1}]}).status_code == 400)
    check("duplicate leave types in a policy update are rejected",
          client.put("/api/leave/policy/defaults", headers=manager_headers,
                     json={"entitlements": [
                         {"leave_type_id": leave_type.id, "annual_quota": 5},
                         {"leave_type_id": leave_type.id, "annual_quota": 6},
                     ]}).status_code == 400)

    created_employee = client.post(
        "/api/employees",
        headers=manager_headers,
        json={
            "employee_code": "NEW_EMPLOYEE",
            "full_name": "New Employee",
            "email": "new.employee@example.com",
            "password": "password",
            "role": EMPLOYEE,
        },
    )
    new_employee_headers = auth("new.employee@example.com")
    new_employee_balance = client.get(
        "/api/leave/balances", headers=new_employee_headers
    ).get_json()
    check("new employees receive their annual leave allocation",
          created_employee.status_code == 201 and
          len(new_employee_balance) == 1 and
          new_employee_balance[0]["annual_entitlement"] == leave_type.annual_quota,
          new_employee_balance)
    legacy_balance = LeaveBalance.query.filter_by(user_id=employee2.id).first()
    db.session.delete(legacy_balance)
    db.session.add(LeaveRequest(
        user_id=employee2.id,
        leave_type_id=leave_type.id,
        start_date=date.today(),
        end_date=date.today(),
        days=1,
        reason="Legacy approved leave",
        status="approved",
    ))
    db.session.commit()
    backfilled = client.get(
        f"/api/leave/balances/{employee2.id}", headers=manager_headers
    ).get_json()[0]
    check("missing balance rows include prior approved leave",
          backfilled["approved_leave_taken"] == 1 and backfilled["remaining_leave"] == 3,
          backfilled)

    team_entitlement = client.put(
        "/api/leave/policy/team",
        headers=manager_headers,
        json={"entitlements": [{"leave_type_id": leave_type.id, "annual_entitlement": 5}]},
    )
    check("team entitlement update changes eligible direct reports and is audited",
          team_entitlement.status_code == 200 and
          balance.allocated == 5 and
          LeaveBalance.query.filter_by(user_id=employee2.id, leave_type_id=leave_type.id).first().allocated == 5 and
          LeaveEntitlementAudit.query.filter_by(scope="team", leave_type_id=leave_type.id).count() == 2,
          team_entitlement.get_json())
    individual_entitlement = client.put(
        f"/api/leave/policy/employees/{employee.id}",
        headers=manager_headers,
        json={"leave_type_id": leave_type.id, "annual_entitlement": 6},
    )
    check("individual entitlement changes only the selected employee",
          individual_entitlement.status_code == 200 and
          balance.allocated == 6 and
          LeaveBalance.query.filter_by(user_id=employee2.id, leave_type_id=leave_type.id).first().allocated == 5 and
          individual_entitlement.get_json()["remaining_leave"] == 6 and
          LeaveEntitlementAudit.query.filter_by(scope="employee", employee_id=employee.id).count() == 1,
          individual_entitlement.get_json())
    balance.used = 6
    db.session.commit()
    conflict_response = client.put(
        f"/api/leave/policy/employees/{employee.id}",
        headers=manager_headers,
        json={"leave_type_id": leave_type.id, "annual_entitlement": 5},
    )
    check("entitlement cannot be lowered below approved leave already taken",
          conflict_response.status_code == 409 and balance.allocated == 6,
          conflict_response.get_json())
    balance.used = 0
    db.session.commit()

    employee2_balance = LeaveBalance.query.filter_by(
        user_id=employee2.id, leave_type_id=leave_type.id
    ).first()
    employee2_balance.used = 5
    db.session.commit()
    atomic_update = client.put(
        "/api/leave/policy/team",
        headers=manager_headers,
        json={"entitlements": [{"leave_type_id": leave_type.id, "annual_entitlement": 4}]},
    )
    check("team entitlement updates roll back entirely when a member conflicts",
          atomic_update.status_code == 409 and
          balance.allocated == 6 and
          employee2_balance.allocated == 5,
          atomic_update.get_json())
    employee2_balance.used = 1
    db.session.commit()

    today = date.today()
    leave_today = {
        "leave_type_id": leave_type.id,
        "start_date": today.isoformat(),
        "end_date": today.isoformat(),
        "reason": "Personal appointment",
    }
    past = {**leave_today, "start_date": (today - timedelta(days=1)).isoformat(), "end_date": (today - timedelta(days=1)).isoformat()}
    check("past dates are rejected", client.post("/api/leave/apply", headers=employee_headers, json=past).status_code == 400)
    check("a reason is required", client.post("/api/leave/apply", headers=employee_headers, json={**leave_today, "reason": " "}).status_code == 400)

    created = client.post("/api/leave/apply", headers=employee_headers, json=leave_today)
    check("employee can apply for today", created.status_code == 201, created.get_json())
    check("pending requests do not reduce the leave balance", balance.used == 0, balance.used)
    request_id = created.get_json()["id"]
    team_requests = client.get("/api/leave/team-requests", headers=manager_headers, query_string={
        "employee_id": employee.id,
        "status": "pending",
    })
    check("manager team history includes employee identity and remaining balance",
          team_requests.status_code == 200 and
          team_requests.get_json()[0]["employee_code"] == employee.employee_code and
          team_requests.get_json()[0]["remaining_leave"] == 6,
          team_requests.get_json())
    team_summary = client.get("/api/leave/team-summary", headers=manager_headers).get_json()
    check("manager dashboard counts team requests and exposes team balances",
          team_summary["counts"]["pending"] == 1 and
          any(row["employee_id"] == employee.id for row in team_summary["employees"]),
          team_summary)
    check("manager cannot filter team history to an employee outside their team",
          client.get("/api/leave/team-requests", headers=manager_headers,
                     query_string={"employee_id": 999999}).status_code == 403)
    check("manager history rejects invalid date ranges",
          client.get("/api/leave/team-requests", headers=manager_headers,
                     query_string={"start_date": "not-a-date"}).status_code == 400)
    check("overlapping pending applications are rejected",
          client.post("/api/leave/apply", headers=employee_headers, json=leave_today).status_code == 409)

    calendar = client.get(
        "/api/attendance/my-calendar",
        headers=employee_headers,
        query_string={"month": today.month, "year": today.year},
    ).get_json()
    check("pending leave is visible on the attendance calendar",
          any(leave["status"] == "pending" for leave in calendar["leaves"]), calendar["leaves"])
    check("manager sees a direct report's request",
          len(client.get("/api/leave/pending-approvals", headers=manager_headers).get_json()) == 1)
    check("another manager cannot approve the request",
          client.post(f"/api/leave/{request_id}/decision", headers=other_manager_headers,
                      json={"decision": "approved"}).status_code == 403)

    approved = client.post(
        f"/api/leave/{request_id}/decision",
        headers=manager_headers,
        json={"decision": "approved"},
    )
    check("manager can approve a direct report's request",
          approved.status_code == 200 and approved.get_json()["status"] == "approved", approved.get_json())
    check("approval deducts the leave balance once", balance.used == 1, balance.used)
    check("a reviewed request cannot be decided twice",
          client.post(f"/api/leave/{request_id}/decision", headers=manager_headers,
                      json={"decision": "approved"}).status_code == 409)
    check("employee can cancel approved future leave",
          client.post(f"/api/leave/{request_id}/cancel", headers=employee_headers).status_code == 200)
    check("cancellation restores the approved leave balance", balance.used == 0, balance.used)
    check("a cancelled request cannot be cancelled or approved again",
          client.post(f"/api/leave/{request_id}/cancel", headers=employee_headers).status_code == 409)

    rejected = client.post("/api/leave/apply", headers=employee_headers, json=leave_today)
    rejected_id = rejected.get_json()["id"]
    check("rejected leave does not deduct balance",
          client.post(f"/api/leave/{rejected_id}/decision", headers=manager_headers,
                      json={"decision": "rejected", "comment": "Coverage unavailable."}).status_code == 200 and
          balance.used == 0 and
          db.session.get(LeaveRequest, rejected_id).review_comment == "Coverage unavailable.")

    manager_own_request = client.post(
        "/api/leave/apply", headers=manager_headers, json=leave_today
    )
    check("manager cannot approve their own leave request",
          manager_own_request.status_code == 201 and
          client.post(
              f"/api/leave/{manager_own_request.get_json()['id']}/decision",
              headers=manager_headers,
              json={"decision": "approved"},
          ).status_code == 403)

    future = {**leave_today, "start_date": (today + timedelta(days=10)).isoformat(),
              "end_date": (today + timedelta(days=10)).isoformat()}
    pending = client.post("/api/leave/apply", headers=employee_headers, json=future)
    pending_id = pending.get_json()["id"]
    balance.used = balance.allocated
    db.session.commit()
    denied = client.post(f"/api/leave/{pending_id}/decision", headers=manager_headers,
                         json={"decision": "approved"})
    check("approval cannot overdraw an employee's balance",
          denied.status_code == 409 and
          db.session.get(LeaveRequest, pending_id).status == "pending" and balance.used == balance.allocated,
          denied.get_json())
    balance.used = 0
    db.session.commit()
    client.post(f"/api/leave/{pending_id}/decision", headers=manager_headers, json={"decision": "rejected"})

    year_end = date(today.year, 12, 31)
    cross_year = {
        **leave_today,
        "start_date": year_end.isoformat(),
        "end_date": date(today.year + 1, 1, 1).isoformat(),
    }
    cross_year_created = client.post("/api/leave/apply", headers=employee_headers, json=cross_year)
    check("a request spanning two calendar years is accepted",
          cross_year_created.status_code == 201, cross_year_created.get_json())
    cross_year_id = cross_year_created.get_json()["id"]
    cross_year_approved = client.post(
        f"/api/leave/{cross_year_id}/decision",
        headers=manager_headers,
        json={"decision": "approved"},
    )
    next_year_balance = LeaveBalance.query.filter_by(
        user_id=employee.id, leave_type_id=leave_type.id, year=today.year + 1
    ).first()
    check("cross-year approval deducts each calendar year's balance separately",
          cross_year_approved.status_code == 200 and balance.used == 1 and
          next_year_balance.used == 1, cross_year_approved.get_json())
    snapshot = client.get(
        f"/api/employees/{employee.id}/performance-snapshot",
        headers=manager_headers,
    ).get_json()
    check("employee performance view reports only this year's cross-year leave",
          snapshot["leave_days_taken_this_year"] == 1, snapshot)
    check("cross-year cancellation restores each year's balance",
          client.post(f"/api/leave/{cross_year_id}/cancel", headers=employee_headers).status_code == 200 and
          balance.used == 0 and next_year_balance.used == 0)

print("ALL LEAVE REQUEST TESTS PASSED")
