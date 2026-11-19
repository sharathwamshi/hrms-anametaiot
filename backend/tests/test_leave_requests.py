import sys
sys.path.insert(0, ".")

from datetime import date, timedelta

from config import Config


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


from app import create_app
from app.extensions import db
from app.models import LeaveBalance, LeaveEntitlementAudit, LeaveRequest, LeaveReviewHistory, LeaveType, User
from app.roles import EMPLOYEE, HR_OPERATIONS, MANAGER, SUPER_ADMIN
from app.routes.leave import _current_month_leave_start
from app.utils.company_time import company_today


app = create_app(TestConfig)


def check(label, condition, details=""):
    if not condition:
        raise AssertionError(f"{label}: {details}")


with app.app_context():
    db.create_all()

    check("current-month start handles month, leap-year, and year changes",
          _current_month_leave_start(date(2026, 11, 19)) == date(2026, 11, 1) and
          _current_month_leave_start(date(2026, 11, 2)) == date(2026, 11, 1) and
          _current_month_leave_start(date(2024, 2, 29)) == date(2024, 2, 1) and
          _current_month_leave_start(date(2025, 1, 3)) == date(2025, 1, 1))

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
    super_admin = make_user("SUPER_ADMIN", SUPER_ADMIN)
    employee = make_user("EMPLOYEE", EMPLOYEE, manager.id)
    employee2 = make_user("EMPLOYEE2", EMPLOYEE, manager.id)
    leave_type = LeaveType(name="Annual", annual_quota=3)
    db.session.add(leave_type)
    db.session.flush()
    balance = LeaveBalance(
        user_id=employee.id,
        leave_type_id=leave_type.id,
        year=company_today().year,
        allocated=5,
        used=0,
    )
    db.session.add(balance)
    db.session.add(LeaveBalance(
        user_id=employee2.id,
        leave_type_id=leave_type.id,
        year=company_today().year,
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
    super_admin_headers = auth("super_admin@example.com")

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
        start_date=company_today(),
        end_date=company_today(),
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

    company_current_date = company_today()
    today_is_sunday = company_current_date.weekday() == 6
    today = company_current_date + timedelta(days=1) if today_is_sunday else company_current_date
    leave_today = {
        "leave_type_id": leave_type.id,
        "start_date": today.isoformat(),
        "end_date": today.isoformat(),
        "reason": "Personal appointment",
    }
    cutoff = _current_month_leave_start(company_current_date)
    recent_backdate = cutoff
    while recent_backdate.weekday() == 6:
        recent_backdate += timedelta(days=1)
    recent_payload = {
        **leave_today,
        "start_date": recent_backdate.isoformat(),
        "end_date": recent_backdate.isoformat(),
    }
    recent_request = client.post(
        "/api/leave/apply", headers=employee_headers, json=recent_payload
    )
    check("employee can apply at the current-month boundary",
          recent_request.status_code == 201, recent_request.get_json())
    recent_request_id = recent_request.get_json()["id"]
    rejected_recent = client.post(
        f"/api/leave/{recent_request_id}/decision",
        headers=manager_headers,
        json={"decision": "rejected", "comment": "Recent backdate test."},
    )
    reapplied_recent = client.post(
        "/api/leave/apply", headers=employee_headers, json=recent_payload
    )
    check("employee can reapply for an eligible date from a rejected request",
          rejected_recent.status_code == 200 and
          reapplied_recent.status_code == 201 and
          reapplied_recent.get_json()["status"] == "pending",
          reapplied_recent.get_json())
    client.post(
        f"/api/leave/{reapplied_recent.get_json()['id']}/decision",
        headers=manager_headers,
        json={"decision": "rejected", "comment": "Reapplication test cleanup."},
    )

    previous_month_day = cutoff - timedelta(days=1)
    previous_month_payload = {
        **leave_today,
        "start_date": previous_month_day.isoformat(),
        "end_date": previous_month_day.isoformat(),
    }
    previous_month_response = client.post(
        "/api/leave/apply", headers=employee_headers, json=previous_month_payload
    )
    check("employee cannot apply for dates in the previous month",
          previous_month_response.status_code == 400,
          previous_month_response.get_json())

    too_old = previous_month_day
    while too_old.weekday() == 6:
        too_old -= timedelta(days=1)
    too_old_payload = {
        **leave_today,
        "start_date": too_old.isoformat(),
        "end_date": too_old.isoformat(),
    }
    too_old_response = client.post(
        "/api/leave/apply", headers=employee_headers, json=too_old_payload
    )
    error_message = (
        "You can apply for leave only from the first day of the current "
        "month onward. Applications for previous months are not allowed."
    )
    check("employee cannot apply for dates in the previous month",
          too_old_response.status_code == 400 and
          too_old_response.get_json()["message"] == error_message,
          too_old_response.get_json())

    historical_rejection = LeaveRequest(
        user_id=employee.id,
        leave_type_id=leave_type.id,
        start_date=too_old,
        end_date=too_old,
        days=1,
        reason="Historical rejected request",
        status="rejected",
    )
    db.session.add(historical_rejection)
    db.session.commit()
    rejected_old_reapplication = client.post(
        "/api/leave/apply", headers=employee_headers, json=too_old_payload
    )
    check("employee cannot reapply for a rejected date from a previous month",
          rejected_old_reapplication.status_code == 400 and
          rejected_old_reapplication.get_json()["message"] == error_message,
          rejected_old_reapplication.get_json())

    current_month_backdate = company_current_date - timedelta(days=1)
    if current_month_backdate >= cutoff and current_month_backdate.weekday() != 6:
        current_month_response = client.post(
            "/api/leave/apply",
            headers=employee_headers,
            json={
                **leave_today,
                "start_date": current_month_backdate.isoformat(),
                "end_date": current_month_backdate.isoformat(),
            },
        )
        check("employee can apply for an eligible past date in the current month",
              current_month_response.status_code == 201,
              current_month_response.get_json())
        client.post(
            f"/api/leave/{current_month_response.get_json()['id']}/decision",
            headers=manager_headers,
            json={"decision": "rejected", "comment": "Recent backdate test cleanup."},
        )
    manager_backdate = client.post(
        "/api/leave/apply", headers=manager_headers, json=too_old_payload
    )
    check("manager self-service leave applications follow the same month boundary",
          manager_backdate.status_code == 400 and
          manager_backdate.get_json()["message"] == error_message,
          manager_backdate.get_json())
    sunday = today + timedelta(days=(6 - today.weekday()) % 7 or 7)
    sunday_payload = {**leave_today, "start_date": sunday.isoformat(), "end_date": sunday.isoformat()}
    check("Sunday leave dates are rejected",
          client.post("/api/leave/apply", headers=employee_headers, json=sunday_payload).status_code == 400)
    check("a reason is required", client.post("/api/leave/apply", headers=employee_headers, json={**leave_today, "reason": " "}).status_code == 400)

    created = client.post("/api/leave/apply", headers=employee_headers, json=leave_today)
    check("employee can apply for today or the next eligible date",
          created.status_code == 201, created.get_json())
    if today_is_sunday:
        sunday_today_payload = {
            **leave_today,
            "start_date": company_current_date.isoformat(),
            "end_date": company_current_date.isoformat(),
        }
        check("Sunday today remains unavailable",
              client.post(
                  "/api/leave/apply",
                  headers=employee_headers,
                  json=sunday_today_payload,
              ).status_code == 400)
    check("pending requests do not reduce the leave balance", balance.used == 0, balance.used)
    request_id = created.get_json()["id"]
    displayed_balance = client.get("/api/leave/balances", headers=employee_headers).get_json()[0]
    check("leave balance response shows pending reservations separately",
          displayed_balance["remaining_leave"] == 6 and
          displayed_balance["pending_reserved"] == 1 and
          displayed_balance["available"] == 5,
          displayed_balance)
    range_start = today + timedelta(days=1)
    while range_start.weekday() != 4:
        range_start += timedelta(days=1)
    range_end = range_start + timedelta(days=3)
    weekend_range = client.post(
        "/api/leave/apply",
        headers=employee_headers,
        json={
            **leave_today,
            "start_date": range_start.isoformat(),
            "end_date": range_end.isoformat(),
        },
    )
    check("leave duration excludes Sundays inside a date range",
          weekend_range.status_code == 201 and weekend_range.get_json()["days"] == 3,
          weekend_range.get_json())
    client.post(
        f"/api/leave/{weekend_range.get_json()['id']}/decision",
        headers=manager_headers,
        json={"decision": "rejected", "comment": "Weekend range test cleanup."},
    )
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
    overbook_start = today + timedelta(days=20)
    while overbook_start.weekday() == 6:
        overbook_start += timedelta(days=1)
    overbook_end = overbook_start + timedelta(days=10)
    while overbook_end.weekday() == 6:
        overbook_end += timedelta(days=1)
    overbook = client.post(
        "/api/leave/apply",
        headers=employee_headers,
        json={
            **leave_today,
            "start_date": overbook_start.isoformat(),
            "end_date": overbook_end.isoformat(),
        },
    )
    check("submission rejects a request exceeding available balance",
          overbook.status_code == 409 and "Insufficient leave balance" in overbook.get_json()["message"],
          overbook.get_json())

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
    rejected_history = LeaveReviewHistory.query.filter_by(leave_request_id=rejected_id).all()
    reapproved = client.post(
        f"/api/leave/{rejected_id}/reapprove",
        headers=manager_headers,
        json={"comment": "Coverage confirmed."},
    )
    check("manager can reapprove a rejected direct-report request and retain both reviews",
          reapproved.status_code == 200 and reapproved.get_json()["status"] == "approved" and
          [entry.action for entry in LeaveReviewHistory.query.filter_by(
              leave_request_id=rejected_id
          ).order_by(LeaveReviewHistory.id).all()] == ["rejected", "reapproved"] and
          len(rejected_history) == 1 and balance.used == 1,
          reapproved.get_json())
    check("reapproving an approved request cannot deduct balance twice",
          client.post(f"/api/leave/{rejected_id}/reapprove", headers=manager_headers,
                      json={}).status_code == 409 and balance.used == 1)
    check("unassigned manager cannot reapprove a rejected request",
          client.post(f"/api/leave/{rejected_id}/reapprove", headers=other_manager_headers,
                      json={}).status_code == 403)
    client.post(f"/api/leave/{rejected_id}/cancel", headers=employee_headers)
    check("cancelling reapproved leave restores its balance", balance.used == 0, balance.used)

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
    hr_own_request = client.post("/api/leave/apply", headers=hr_headers, json=leave_today)
    check("HR Operations cannot approve their own leave request",
          hr_own_request.status_code == 201 and
          client.post(
              f"/api/leave/{hr_own_request.get_json()['id']}/decision",
              headers=hr_headers,
              json={"decision": "approved"},
          ).status_code == 403 and
          all(row["id"] != hr_own_request.get_json()["id"]
              for row in client.get("/api/leave/pending-approvals", headers=hr_headers).get_json()))
    admin_own_request = client.post("/api/leave/apply", headers=super_admin_headers, json=leave_today)
    check("Super Admin cannot approve their own leave request",
          admin_own_request.status_code == 201 and
          client.post(
              f"/api/leave/{admin_own_request.get_json()['id']}/decision",
              headers=super_admin_headers,
              json={"decision": "approved"},
          ).status_code == 403 and
          all(row["id"] != admin_own_request.get_json()["id"]
              for row in client.get("/api/leave/pending-approvals", headers=super_admin_headers).get_json()))

    future_day = today + timedelta(days=10)
    while future_day.weekday() == 6:
        future_day += timedelta(days=1)
    future = {**leave_today, "start_date": future_day.isoformat(),
              "end_date": future_day.isoformat()}
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
    while year_end.weekday() == 6:
        year_end -= timedelta(days=1)
    next_year_start = date(today.year + 1, 1, 1)
    while next_year_start.weekday() == 6:
        next_year_start += timedelta(days=1)
    cross_year = {
        **leave_today,
        "start_date": year_end.isoformat(),
        "end_date": next_year_start.isoformat(),
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
