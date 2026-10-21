from datetime import date, datetime
from math import isfinite
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import LeaveRequest, LeaveType, LeaveBalance, LeaveEntitlementAudit, User
from app.models.leave import ensure_leave_balances
from app.roles import MANAGER, HR_OPERATIONS, SUPER_ADMIN, APPROVER_ROLES, CONTRACT_EMPLOYEE
from sqlalchemy.exc import SQLAlchemyError

bp = Blueprint("leave", __name__, url_prefix="/api/leave")


def _days_by_year(start, end):
    days = {}
    current = start
    while current <= end:
        segment_end = min(end, date(current.year, 12, 31))
        days[current.year] = (segment_end - current).days + 1
        current = date(current.year + 1, 1, 1)
    return days


def _balances_for_range(user_id, leave_type_id, start, end, lock=False):
    balances = {}
    for year in _days_by_year(start, end):
        query = LeaveBalance.query.filter_by(
            user_id=user_id, leave_type_id=leave_type_id, year=year
        )
        if lock:
            query = query.with_for_update()
        balance = query.first()
        if balance is None:
            ensure_leave_balances(user_id, year)
            db.session.flush()
            balance = query.first()
        balances[year] = balance
    return balances


def _manager_report_ids(manager_id):
    return [
        user.id
        for user in User.query.filter_by(manager_id=manager_id).filter(User.id != manager_id).all()
    ]


def _parse_filter_date(value, field_name):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.")


def _eligible_manager_reports(manager_id):
    return (
        User.query.filter_by(manager_id=manager_id, is_active=True)
        .filter(User.id != manager_id, User.role != CONTRACT_EMPLOYEE)
        .order_by(User.id.asc())
        .all()
    )


def _validated_entitlements(payload, field_name="annual_quota"):
    if not isinstance(payload, dict) or not isinstance(payload.get("entitlements"), list):
        return None, "entitlements must be a list of leave type entitlements."
    if not payload["entitlements"]:
        return None, "At least one leave type entitlement is required."

    updates = {}
    for item in payload["entitlements"]:
        if not isinstance(item, dict):
            return None, "Each entitlement must include a leave_type_id and entitlement."
        try:
            leave_type_id = int(item["leave_type_id"])
            raw_value = item[field_name]
            if isinstance(raw_value, bool):
                raise ValueError
            value = float(raw_value)
        except (KeyError, TypeError, ValueError, OverflowError):
            return None, f"Each entitlement requires a valid leave_type_id and {field_name}."
        if not isfinite(value) or value < 0 or value > 365:
            return None, "Annual entitlement must be between 0 and 365 days."
        if leave_type_id in updates:
            return None, "A leave type can only be changed once per request."
        leave_type = db.session.get(LeaveType, leave_type_id)
        if leave_type is None:
            return None, "One or more leave types are invalid."
        updates[leave_type_id] = (leave_type, value)
    return updates, None


def _entitlement_conflict(balance, entitlement, employee):
    if balance.used > entitlement:
        return {
            "employee_id": employee.id,
            "employee_name": employee.full_name,
            "leave_type": balance.leave_type.name,
            "approved_leave_taken": balance.used,
            "requested_entitlement": entitlement,
        }
    return None


@bp.get("/types")
@jwt_required()
def leave_types():
    return jsonify([lt.to_dict() for lt in LeaveType.query.all()])


@bp.get("/balances")
@jwt_required()
def balances():
    user_id = int(get_jwt_identity())
    year = request.args.get("year", type=int) or date.today().year
    ensure_leave_balances(user_id, year)
    db.session.commit()
    rows = LeaveBalance.query.filter_by(user_id=user_id, year=year).all()
    return jsonify([r.to_dict() for r in rows])


@bp.get("/balances/<int:employee_id>")
@jwt_required()
def employee_balances(employee_id):
    claims = get_jwt()
    actor_id = int(get_jwt_identity())
    role = claims.get("role")
    employee = User.query.get_or_404(employee_id)
    if actor_id != employee_id:
        if role in (HR_OPERATIONS, SUPER_ADMIN):
            pass
        elif role == MANAGER and employee.manager_id == actor_id:
            pass
        else:
            return jsonify({"message": "You do not have permission to view this employee's leave balance."}), 403

    year = request.args.get("year", type=int) or date.today().year
    ensure_leave_balances(employee_id, year)
    db.session.commit()
    rows = LeaveBalance.query.filter_by(user_id=employee_id, year=year).all()
    return jsonify([r.to_dict() for r in rows])


@bp.post("/apply")
@jwt_required()
def apply_leave():
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    if claims.get("role") == CONTRACT_EMPLOYEE:
        return jsonify({"message": "Contract Employees manage their documents and payroll only — leave isn't part of this engagement type."}), 403
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"message": "A valid leave request is required."}), 400

    try:
        start = datetime.strptime(payload["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(payload["end_date"], "%Y-%m-%d").date()
        leave_type_id = int(payload["leave_type_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"message": "start_date, end_date and leave_type_id are required."}), 400

    if end < start:
        return jsonify({"message": "End date cannot be before start date."}), 400
    if start < date.today():
        return jsonify({"message": "Leave can only be requested for today or a future date."}), 400

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return jsonify({"message": "A reason is required."}), 400
    if len(reason.strip()) > 500:
        return jsonify({"message": "Reason cannot exceed 500 characters."}), 400

    leave_type = LeaveType.query.get(leave_type_id)
    if not leave_type:
        return jsonify({"message": "The selected leave type is invalid."}), 400

    overlap = LeaveRequest.query.filter(
        LeaveRequest.user_id == user_id,
        LeaveRequest.status.in_(("pending", "approved")),
        LeaveRequest.start_date <= end,
        LeaveRequest.end_date >= start,
    ).first()
    if overlap:
        return jsonify({"message": "You already have a pending or approved leave request for part of this date range."}), 409

    days = (end - start).days + 1

    balances = _balances_for_range(user_id, leave_type_id, start, end)
    for year, days_in_year in _days_by_year(start, end).items():
        balance = balances[year]
        if balance.balance < days_in_year:
            return jsonify({
                "message": f"Insufficient balance for {year}. Available: {balance.balance} day(s)."
            }), 400

    leave_request = LeaveRequest(
        user_id=user_id,
        leave_type_id=leave_type_id,
        start_date=start,
        end_date=end,
        days=days,
        reason=reason.strip(),
        status="pending",
    )
    db.session.add(leave_request)
    db.session.commit()
    return jsonify(leave_request.to_dict()), 201


@bp.get("/my-requests")
@jwt_required()
def my_requests():
    user_id = int(get_jwt_identity())
    rows = (
        LeaveRequest.query.filter_by(user_id=user_id)
        .order_by(LeaveRequest.created_at.desc())
        .all()
    )
    return jsonify([r.to_dict() for r in rows])


@bp.get("/pending-approvals")
@jwt_required()
def pending_approvals():
    claims = get_jwt()
    role = claims.get("role")
    user_id = int(get_jwt_identity())

    if role not in APPROVER_ROLES:
        return jsonify({"message": "You do not have permission to view approvals."}), 403

    query = LeaveRequest.query.filter_by(status="pending")
    if role == MANAGER:
        report_ids = _manager_report_ids(user_id)
        query = query.filter(LeaveRequest.user_id.in_(report_ids))

    rows = query.order_by(LeaveRequest.created_at.asc()).all()
    return jsonify([r.to_dict() for r in rows])


@bp.get("/team-summary")
@jwt_required()
def team_summary():
    manager_id = int(get_jwt_identity())
    if get_jwt().get("role") != MANAGER:
        return jsonify({"message": "Only managers can view team leave summaries."}), 403

    report_ids = _manager_report_ids(manager_id)
    users = User.query.filter(User.id.in_(report_ids)).order_by(User.full_name.asc()).all()
    year = date.today().year
    for employee in users:
        ensure_leave_balances(employee.id, year)
    db.session.flush()

    rows = LeaveRequest.query.filter(LeaveRequest.user_id.in_(report_ids)).all()
    counts = {
        "total": len(rows),
        "pending": sum(row.status == "pending" for row in rows),
        "approved": sum(row.status == "approved" for row in rows),
        "rejected": sum(row.status == "rejected" for row in rows),
    }
    balance_rows = LeaveBalance.query.filter(
        LeaveBalance.user_id.in_(report_ids), LeaveBalance.year == year
    ).all()
    balances_by_user = {}
    for balance in balance_rows:
        balances_by_user.setdefault(balance.user_id, []).append(balance.to_dict())

    db.session.commit()
    return jsonify({
        "year": year,
        "counts": counts,
        "employees": [
            {
                "employee_id": employee.id,
                "employee_code": employee.employee_code,
                "employee_name": employee.full_name,
                "eligible_for_entitlement_edit": (
                    employee.is_active and employee.role != CONTRACT_EMPLOYEE
                ),
                "balances": balances_by_user.get(employee.id, []),
            }
            for employee in users
        ],
    })


@bp.put("/policy/defaults")
@jwt_required()
def update_leave_defaults():
    manager_id = int(get_jwt_identity())
    if get_jwt().get("role") != MANAGER:
        return jsonify({"message": "Only managers can update leave defaults."}), 403
    updates, error = _validated_entitlements(request.get_json(silent=True))
    if error:
        return jsonify({"message": error}), 400

    try:
        for leave_type, entitlement in updates.values():
            locked = LeaveType.query.filter_by(id=leave_type.id).with_for_update().one()
            old_entitlement = float(locked.annual_quota or 0)
            if old_entitlement == entitlement:
                continue
            locked.annual_quota = entitlement
            db.session.add(LeaveEntitlementAudit(
                leave_type_id=locked.id,
                employee_id=None,
                actor_id=manager_id,
                scope="default",
                year=None,
                old_entitlement=old_entitlement,
                new_entitlement=entitlement,
            ))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"message": "Could not save leave defaults. No changes were applied."}), 500
    return jsonify({"message": "Default leave policy updated.", "leave_types": [
        leave_type.to_dict() for leave_type in LeaveType.query.order_by(LeaveType.id).all()
    ]})


@bp.put("/policy/team")
@jwt_required()
def update_team_entitlements():
    manager_id = int(get_jwt_identity())
    if get_jwt().get("role") != MANAGER:
        return jsonify({"message": "Only managers can update team leave entitlements."}), 403
    updates, error = _validated_entitlements(
        request.get_json(silent=True), field_name="annual_entitlement"
    )
    if error:
        return jsonify({"message": error}), 400

    employees = _eligible_manager_reports(manager_id)
    if not employees:
        return jsonify({"message": "There are no eligible active employees on your team."}), 409
    year = date.today().year

    try:
        for employee in employees:
            for leave_type, _ in updates.values():
                ensure_leave_balances(employee.id, year)
        db.session.flush()

        balances = {}
        conflicts = []
        for employee in employees:
            for leave_type_id, (_, entitlement) in updates.items():
                balance = (
                    LeaveBalance.query.filter_by(
                        user_id=employee.id, leave_type_id=leave_type_id, year=year
                    )
                    .with_for_update()
                    .one()
                )
                balances[(employee.id, leave_type_id)] = balance
                conflict = _entitlement_conflict(balance, entitlement, employee)
                if conflict:
                    conflicts.append(conflict)

        if conflicts:
            db.session.rollback()
            return jsonify({
                "message": "Some employees have already used more leave than the requested entitlement. No changes were applied.",
                "conflicts": conflicts,
            }), 409

        for employee in employees:
            for leave_type_id, (_, entitlement) in updates.items():
                balance = balances[(employee.id, leave_type_id)]
                old_entitlement = float(balance.allocated or 0)
                if old_entitlement == entitlement:
                    continue
                balance.allocated = entitlement
                db.session.add(LeaveEntitlementAudit(
                    leave_type_id=leave_type_id,
                    employee_id=employee.id,
                    actor_id=manager_id,
                    scope="team",
                    year=year,
                    old_entitlement=old_entitlement,
                    new_entitlement=entitlement,
                ))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"message": "Could not update team entitlements. No changes were applied."}), 500

    return jsonify({
        "message": "Leave entitlements updated for your team.",
        "affected_employees": len(employees),
        "year": year,
    })


@bp.put("/policy/employees/<int:employee_id>")
@jwt_required()
def update_employee_entitlement(employee_id):
    manager_id = int(get_jwt_identity())
    if get_jwt().get("role") != MANAGER:
        return jsonify({"message": "Only managers can update employee leave entitlements."}), 403
    employee = User.query.filter_by(
        id=employee_id, manager_id=manager_id, is_active=True
    ).first()
    if employee is None or employee.role == CONTRACT_EMPLOYEE:
        return jsonify({"message": "You can only update leave entitlements for eligible active direct reports."}), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "A valid entitlement update is required."}), 400
    updates, error = _validated_entitlements({
        "entitlements": [{
            "leave_type_id": payload.get("leave_type_id"),
            "annual_entitlement": payload.get("annual_entitlement"),
        }]
    }, field_name="annual_entitlement")
    if error:
        return jsonify({"message": error}), 400
    leave_type_id, (_, entitlement) = next(iter(updates.items()))
    year = date.today().year

    try:
        ensure_leave_balances(employee.id, year)
        db.session.flush()
        balance = (
            LeaveBalance.query.filter_by(
                user_id=employee.id, leave_type_id=leave_type_id, year=year
            )
            .with_for_update()
            .one()
        )
        conflict = _entitlement_conflict(balance, entitlement, employee)
        if conflict:
            db.session.rollback()
            return jsonify({
                "message": "The requested entitlement is lower than approved leave already taken. Existing leave policy does not allow a negative balance.",
                "conflict": conflict,
            }), 409

        old_entitlement = float(balance.allocated or 0)
        if old_entitlement != entitlement:
            balance.allocated = entitlement
            db.session.add(LeaveEntitlementAudit(
                leave_type_id=leave_type_id,
                employee_id=employee.id,
                actor_id=manager_id,
                scope="employee",
                year=year,
                old_entitlement=old_entitlement,
                new_entitlement=entitlement,
            ))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"message": "Could not update this employee's entitlement. No changes were applied."}), 500

    return jsonify({
        "message": "Employee leave entitlement updated.",
        "employee_id": employee.id,
        "leave_type_id": leave_type_id,
        "year": year,
        "old_entitlement": old_entitlement,
        "annual_entitlement": entitlement,
        "approved_leave_taken": balance.used,
        "remaining_leave": balance.balance,
    })


@bp.get("/team-requests")
@jwt_required()
def team_requests():
    manager_id = int(get_jwt_identity())
    if get_jwt().get("role") != MANAGER:
        return jsonify({"message": "Only managers can view team leave requests."}), 403

    report_ids = _manager_report_ids(manager_id)
    query = LeaveRequest.query.filter(LeaveRequest.user_id.in_(report_ids))

    employee_id = request.args.get("employee_id", type=int)
    if employee_id is not None:
        if employee_id not in report_ids:
            return jsonify({"message": "You can only view leave requests from your direct reports."}), 403
        query = query.filter(LeaveRequest.user_id == employee_id)

    leave_type_id = request.args.get("leave_type_id", type=int)
    if request.args.get("leave_type_id") and (
        leave_type_id is None or LeaveType.query.get(leave_type_id) is None
    ):
        return jsonify({"message": "The selected leave type is invalid."}), 400
    if leave_type_id is not None:
        query = query.filter(LeaveRequest.leave_type_id == leave_type_id)

    status = request.args.get("status")
    if status and status != "all":
        if status not in ("pending", "approved", "rejected", "cancelled"):
            return jsonify({"message": "The selected request status is invalid."}), 400
        query = query.filter(LeaveRequest.status == status)

    try:
        start_date = _parse_filter_date(request.args.get("start_date"), "start_date")
        end_date = _parse_filter_date(request.args.get("end_date"), "end_date")
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    if start_date and end_date and end_date < start_date:
        return jsonify({"message": "End date cannot be before start date."}), 400
    if start_date:
        query = query.filter(LeaveRequest.end_date >= start_date)
    if end_date:
        query = query.filter(LeaveRequest.start_date <= end_date)

    rows = query.order_by(LeaveRequest.created_at.desc()).all()
    balance_keys = {
        (row.user_id, row.leave_type_id, row.start_date.year)
        for row in rows
    }
    for user_id, _, year in balance_keys:
        ensure_leave_balances(user_id, year)
    db.session.flush()
    balance_rows = LeaveBalance.query.filter(
        LeaveBalance.user_id.in_(report_ids),
        LeaveBalance.year.in_({year for _, _, year in balance_keys}),
    ).all() if balance_keys else []
    balances_by_key = {
        (row.user_id, row.leave_type_id, row.year): row
        for row in balance_rows
    }
    results = []
    for row in rows:
        result = row.to_dict()
        balance = balances_by_key.get((row.user_id, row.leave_type_id, row.start_date.year))
        result["remaining_leave"] = balance.balance if balance else None
        results.append(result)
    db.session.commit()
    return jsonify(results)


@bp.post("/<int:request_id>/decision")
@jwt_required()
def decide(request_id):
    claims = get_jwt()
    role = claims.get("role")
    reviewer_id = int(get_jwt_identity())

    if role not in APPROVER_ROLES:
        return jsonify({"message": "You do not have permission to approve or reject leave."}), 403

    leave_request = (
        LeaveRequest.query.filter_by(id=request_id)
        .with_for_update()
        .first_or_404()
    )
    if role == MANAGER:
        if leave_request.user_id == reviewer_id:
            return jsonify({"message": "Managers cannot review their own leave requests."}), 403
        if leave_request.user.manager_id != reviewer_id:
            return jsonify({"message": "You can only review leave requests from your direct reports."}), 403
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"message": "A valid decision is required."}), 400
    decision = payload.get("decision")  # "approved" | "rejected"

    if decision not in ("approved", "rejected"):
        return jsonify({"message": "decision must be 'approved' or 'rejected'."}), 400
    if leave_request.status != "pending":
        return jsonify({"message": "This leave request has already been reviewed."}), 409
    comment = payload.get("comment", "")
    if comment is None:
        comment = ""
    if not isinstance(comment, str) or len(comment) > 255:
        return jsonify({"message": "Review comment must be 255 characters or fewer."}), 400

    if decision == "approved":
        balances = _balances_for_range(
            leave_request.user_id,
            leave_request.leave_type_id,
            leave_request.start_date,
            leave_request.end_date,
            lock=True,
        )
        for year, days_in_year in _days_by_year(
            leave_request.start_date, leave_request.end_date
        ).items():
            balance = balances[year]
            if balance.balance < days_in_year:
                db.session.rollback()
                return jsonify({
                    "message": f"Insufficient balance for {year}. Available: {balance.balance} day(s)."
                }), 409
        for year, days_in_year in _days_by_year(
            leave_request.start_date, leave_request.end_date
        ).items():
            balances[year].used += days_in_year

    leave_request.status = decision
    leave_request.reviewed_by = reviewer_id
    leave_request.review_comment = comment.strip()
    db.session.commit()
    return jsonify(leave_request.to_dict())


@bp.post("/<int:request_id>/cancel")
@jwt_required()
def cancel_leave(request_id):
    user_id = int(get_jwt_identity())
    leave_request = (
        LeaveRequest.query.filter_by(id=request_id)
        .with_for_update()
        .first_or_404()
    )
    if leave_request.user_id != user_id:
        return jsonify({"message": "You can only cancel your own leave requests."}), 403
    if leave_request.status not in ("pending", "approved"):
        return jsonify({"message": "Only pending or approved leave requests can be cancelled."}), 409
    if leave_request.status == "approved" and leave_request.start_date < date.today():
        return jsonify({"message": "Approved leave cannot be cancelled after it has started."}), 409

    if leave_request.status == "approved":
        balances = _balances_for_range(
            user_id,
            leave_request.leave_type_id,
            leave_request.start_date,
            leave_request.end_date,
            lock=True,
        )
        days_by_year = _days_by_year(leave_request.start_date, leave_request.end_date)
        if any(balances[year].used < days for year, days in days_by_year.items()):
            db.session.rollback()
            return jsonify({"message": "The leave balance is inconsistent; this request cannot be cancelled."}), 409
        for year, days in days_by_year.items():
            balances[year].used -= days

    leave_request.status = "cancelled"
    leave_request.review_comment = "Cancelled by employee."
    db.session.commit()
    return jsonify(leave_request.to_dict())
