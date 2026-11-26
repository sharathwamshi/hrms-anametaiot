
from datetime import date, datetime, timedelta
import calendar
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import LeaveRequest, LeaveType, LeaveBalance, LeaveEntitlementAudit, LeaveReviewHistory, User, Attendance, Holiday
from app.models.leave import ensure_leave_balances
from app.roles import MANAGER, HR_OPERATIONS, SUPER_ADMIN, APPROVER_ROLES, CONTRACT_EMPLOYEE
from app.utils.company_time import company_today

bp = Blueprint("leave", __name__, url_prefix="/api/leave")


def _category_name(leave_type):
    name = (leave_type.name if leave_type else "").strip().lower()
    if name in ("paid leave", "paid", "pl"):
        return "paid"
    if name in ("casual leave", "casual", "cl"):
        return "casual"
    if name in ("sick leave", "sick", "sl"):
        return "sick"
    return "legacy"


def _paid_leave_eligibility(user):
    joining = user.date_of_joining
    if not joining:
        return None, True, None
    month = joining.month - 1 + 3
    year = joining.year + month // 12
    month_number = month % 12 + 1
    eligibility = date(year, month_number, min(joining.day, calendar.monthrange(year, month_number)[1]))
    eligible = company_today() >= eligibility
    return eligibility, eligible, None


def _sync_approved_leave_attendance(leave_request, final_classification=None):
    category = _category_name(leave_request.leave_type)
    if category == "sick" and final_classification:
        category = final_classification
    if category not in ("paid", "casual"):
        return
    if category in ("paid", "legacy"):
        attendance_status = "on_leave"
    else:
        attendance_status = "absent"
    current = leave_request.start_date
    while current <= leave_request.end_date:
        if current.weekday() == 6:
            current += timedelta(days=1)
            continue
        holiday = Holiday.query.filter_by(holiday_date=current).first()
        if holiday:
            current += timedelta(days=1)
            continue
        record = Attendance.query.filter_by(
            user_id=leave_request.user_id,
            work_date=current,
        ).first()
        if record is None:
            db.session.add(Attendance(
                user_id=leave_request.user_id,
                work_date=current,
                status=attendance_status,
                total_hours=0,
            ))
        elif record.status not in ("regularized", "present", "half_day"):
            record.status = attendance_status
            record.total_hours = 0
        current += timedelta(days=1)


def _remove_approved_leave_attendance(leave_request, final_classification=None):
    category = _category_name(leave_request.leave_type)
    if category == "sick" and final_classification:
        category = final_classification
    if category not in ("paid", "casual"):
        return
    current = leave_request.start_date
    while current <= leave_request.end_date:
        record = Attendance.query.filter_by(
            user_id=leave_request.user_id,
            work_date=current,
        ).first()
        if record and record.status in ("on_leave", "absent"):
            record.status = "not_clocked_in"
            record.total_hours = 0
        current += timedelta(days=1)


def _current_month_leave_start(today=None):
    today = today or company_today()
    return date(today.year, today.month, 1)


def _manager_report_ids(manager_id):
    return [user.id for user in User.query.filter_by(manager_id=manager_id).all()]


def _leave_days_by_year(start, end):
    days_by_year = {}
    current = start
    while current <= end:
        if current.weekday() != 6:
            days_by_year[current.year] = days_by_year.get(current.year, 0) + 1
        current += timedelta(days=1)
    return days_by_year


def _calendar_days_by_year(start, end):
    days_by_year = {}
    current = start
    while current <= end:
        days_by_year[current.year] = days_by_year.get(current.year, 0) + 1
        current += timedelta(days=1)
    return days_by_year


def _leave_request_days_by_year(leave_request):
    if leave_request.duration != "full_day":
        return {leave_request.start_date.year: 0.5}
    calendar_days = _calendar_days_by_year(
        leave_request.start_date, leave_request.end_date
    )
    if leave_request.days == sum(calendar_days.values()):
        return calendar_days
    return _leave_days_by_year(leave_request.start_date, leave_request.end_date)


def _available_balance_error(user_id, leave_type_id, start, end, exclude_request_id=None):
    days_by_year = _leave_days_by_year(start, end)
    if not days_by_year:
        return "The selected date range contains no eligible working days."

    for year, requested_days in days_by_year.items():
        ensure_leave_balances(user_id, year)
    db.session.flush()

    for year, requested_days in days_by_year.items():
        balance = LeaveBalance.query.filter_by(
            user_id=user_id, leave_type_id=leave_type_id, year=year
        ).with_for_update().first()
        available = balance.balance if balance else 0
        pending_requests = LeaveRequest.query.filter(
            LeaveRequest.user_id == user_id,
            LeaveRequest.leave_type_id == leave_type_id,
            LeaveRequest.status == "pending",
            LeaveRequest.start_date <= date(year, 12, 31),
            LeaveRequest.end_date >= date(year, 1, 1),
        )
        if exclude_request_id is not None:
            pending_requests = pending_requests.filter(LeaveRequest.id != exclude_request_id)
        reserved_days = sum(
            _leave_request_days_by_year(row).get(year, 0)
            for row in pending_requests.all()
        )
        available = max(0, available - reserved_days)
        if requested_days > available:
            return (
                f"Insufficient leave balance for {year}. "
                f"Available after pending requests: {available} day(s); "
                f"requested: {requested_days}."
            )
    return None


def _validated_leave_fields(
    payload, user_id, exclude_request_id=None, restrict_backdating=False
):
    try:
        start = datetime.strptime(payload.get("start_date"), "%Y-%m-%d").date()
        end = datetime.strptime(payload.get("end_date"), "%Y-%m-%d").date()
        leave_type_id = int(payload.get("leave_type_id"))
    except (TypeError, ValueError):
        return None, "start_date, end_date and leave_type_id are required."

    if end < start:
        return None, "End date cannot be before start date."
    if start.weekday() == 6 or end.weekday() == 6:
        return None, "Leave start and end dates cannot be Sundays."

    if restrict_backdating and start < _current_month_leave_start():
        return None, (
            "You can apply for leave only from the first day of the current "
            "month onward. Applications for previous months are not allowed."
        )

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None, "A reason is required."
    reason = reason.strip()
    if len(reason) > 500:
        return None, "Reason cannot exceed 500 characters."

    leave_type = db.session.get(LeaveType, leave_type_id)
    if leave_type is None:
        return None, "The selected leave type is invalid."
    category = _category_name(leave_type)
    duration = str(payload.get("duration", "full_day"))
    if duration not in ("full_day", "first_half", "second_half"):
        return None, "Duration must be full_day, first_half or second_half."
    if duration != "full_day" and start != end:
        return None, "Half-day leave must use the same start and end date."

    employee = db.session.get(User, user_id)
    if category == "paid":
        eligibility, eligible, _ = _paid_leave_eligibility(employee)
        if not eligible:
            message = "Paid Leave is unavailable during the first three months."
            if eligibility:
                message += f" Eligibility begins on {eligibility.isoformat()}."
            return None, message

    overlap_query = LeaveRequest.query.filter(
        LeaveRequest.user_id == user_id,
        LeaveRequest.status.in_(("pending", "approved")),
        LeaveRequest.start_date <= end,
        LeaveRequest.end_date >= start,
    )
    if exclude_request_id is not None:
        overlap_query = overlap_query.filter(LeaveRequest.id != exclude_request_id)
    overlap = overlap_query.first()
    if overlap:
        return None, (
            "You already have a pending or approved leave request "
            "for part of this date range."
        )

    days_by_year = _leave_days_by_year(start, end)
    if not days_by_year:
        return None, "The selected date range contains no eligible working days."
    if category in ("paid", "legacy"):
        balance_error = _available_balance_error(
            user_id, leave_type.id, start, end, exclude_request_id
        )
        if balance_error:
            return None, balance_error

    return {
        "leave_type_id": leave_type.id,
        "start_date": start,
        "end_date": end,
        "days": 0.5 if duration != "full_day" else sum(days_by_year.values()),
        "reason": reason,
        "duration": duration,
    }, None


def _validated_entitlements(payload, field_name="annual_quota"):
    if not isinstance(payload, dict) or not isinstance(payload.get("entitlements"), list):
        return None, "A list of leave entitlements is required."
    if not payload["entitlements"]:
        return None, "At least one leave entitlement is required."

    updates = {}
    for item in payload["entitlements"]:
        if not isinstance(item, dict):
            return None, "Each leave entitlement must be an object."
        try:
            leave_type_id = int(item.get("leave_type_id"))
            entitlement = float(item.get(field_name))
        except (TypeError, ValueError):
            return None, "Each entitlement requires a valid leave type and quota."
        if entitlement < 0 or entitlement != entitlement or entitlement in (float("inf"), float("-inf")):
            return None, "Leave entitlement must be a non-negative number."
        if leave_type_id in updates:
            return None, "A leave type can only be updated once per request."
        leave_type = db.session.get(LeaveType, leave_type_id)
        if leave_type is None:
            return None, "The selected leave type is invalid."
        updates[leave_type_id] = (leave_type, entitlement)
    return updates, None


def _eligible_manager_reports(manager_id):
    return User.query.filter(
        User.manager_id == manager_id,
        User.is_active.is_(True),
        User.role != CONTRACT_EMPLOYEE,
    ).all()


def _entitlement_conflict(balance, entitlement, employee):
    if balance.used <= entitlement:
        return None
    return {
        "employee_id": employee.id,
        "employee_name": employee.full_name,
        "leave_type_id": balance.leave_type_id,
        "approved_leave_taken": balance.used,
        "requested_entitlement": entitlement,
    }


def _parse_filter_date(value, field_name):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.")


@bp.get("/types")
@jwt_required()
def leave_types():
    return jsonify([lt.to_dict() for lt in LeaveType.query.all()])


@bp.get("/balances")
@jwt_required()
def balances():
    user_id = int(get_jwt_identity())
    year = request.args.get("year", type=int) or date.today().year
    employee = db.session.get(User, user_id)
    ensure_leave_balances(user_id, year)
    rows = LeaveBalance.query.filter_by(user_id=user_id, year=year).all()
    results = []
    for row in rows:
        pending = LeaveRequest.query.filter_by(
            user_id=user_id, leave_type_id=row.leave_type_id, status="pending"
        ).filter(
            LeaveRequest.start_date <= date(year, 12, 31),
            LeaveRequest.end_date >= date(year, 1, 1),
        ).all()
        reserved = sum(_leave_request_days_by_year(item).get(year, 0) for item in pending)
        result = row.to_dict()
        result["pending_reserved"] = reserved
        result["available"] = max(0, row.balance - reserved)
        results.append(result)
    paid_types = [row for row in results if row.get("leave_type") == "Paid Leave"]
    eligibility, eligible, _ = _paid_leave_eligibility(employee)
    for result in paid_types:
        result["eligibility_status"] = "eligible" if eligible else "not_eligible"
        result["eligibility_date"] = eligibility.isoformat() if eligibility else None
    if paid_types and paid_types[0]["remaining_leave"] <= 0 and eligible:
        paid_types[0]["exhausted"] = True
    db.session.commit()
    return jsonify(results)


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
        return jsonify({
            "message": (
                "Contract Employees manage their documents and payroll only "
                "— leave isn't part of this engagement type."
            )
        }), 403

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({"message": "A valid leave request is required."}), 400

    User.query.filter_by(id=user_id).with_for_update().first()
    fields, error = _validated_leave_fields(
        payload,
        user_id,
        restrict_backdating=True,
    )

    if error:
        # Preserve the conflict response for overlapping requests.
        if (
            "already have a pending or approved leave request" in error
            or "Insufficient leave balance" in error
        ):
            return jsonify({"message": error}), 409

        return jsonify({"message": error}), 400

    leave_request = LeaveRequest(
        user_id=user_id,
        **fields,
        status="pending",
    )

    db.session.add(leave_request)
    db.session.commit()

    return jsonify(leave_request.to_dict()), 201


@bp.put("/<int:request_id>")
@jwt_required()
def update_leave(request_id):
    user_id = int(get_jwt_identity())
    claims = get_jwt()

    if claims.get("role") == CONTRACT_EMPLOYEE:
        return jsonify({
            "message": (
                "Contract Employees manage their documents and payroll only "
                "— leave isn't part of this engagement type."
            )
        }), 403

    leave_request = LeaveRequest.query.filter_by(id=request_id).with_for_update().first_or_404()

    if leave_request.user_id != user_id:
        return jsonify({
            "message": "You can only edit your own leave requests."
        }), 403

    if leave_request.status != "pending":
        return jsonify({
            "message": "Only pending leave requests can be edited."
        }), 400

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "A valid leave request is required."}), 400

    User.query.filter_by(id=user_id).with_for_update().first()
    fields, error = _validated_leave_fields(
        payload,
        user_id,
        exclude_request_id=leave_request.id,
        restrict_backdating=True,
    )
    if error:
        status = 409 if (
            "already have a pending or approved leave request" in error
            or "Insufficient leave balance" in error
        ) else 400
        return jsonify({"message": error}), status

    for field, value in fields.items():
        setattr(leave_request, field, value)

    db.session.commit()

    return jsonify(leave_request.to_dict())


@bp.post("/<int:request_id>/cancel")
@jwt_required()
def cancel_leave(request_id):
    user_id = int(get_jwt_identity())

    if get_jwt().get("role") == CONTRACT_EMPLOYEE:
        return jsonify({
            "message": (
                "Contract Employees manage their documents and payroll only "
                "— leave isn't part of this engagement type."
            )
        }), 403

    leave_request = LeaveRequest.query.filter_by(id=request_id).with_for_update().first_or_404()

    if leave_request.user_id != user_id:
        return jsonify({
            "message": "You can only cancel your own leave requests."
        }), 403

    if leave_request.status == "cancelled":
        return jsonify({"message": "This leave request has already been cancelled."}), 409
    if leave_request.status not in ("pending", "approved"):
        return jsonify({"message": "Only pending or approved leave requests can be cancelled."}), 400
    if leave_request.status == "approved" and leave_request.start_date < date.today():
        return jsonify({"message": "Approved leave can only be cancelled before it starts."}), 400

    if leave_request.status == "approved":
        days_by_year = _leave_request_days_by_year(leave_request)
        balance_type = leave_request.leave_type
        if _category_name(leave_request.leave_type) == "sick" and leave_request.final_classification == "paid":
            balance_type = LeaveType.query.filter_by(name="Paid Leave").first() or balance_type
        elif _category_name(leave_request.leave_type) == "paid":
            balance_type = LeaveType.query.filter_by(name="Paid Leave").first() or balance_type
        for year in days_by_year:
            ensure_leave_balances(user_id, year)
        db.session.flush()
        for year, days_in_year in days_by_year.items():
            balance = LeaveBalance.query.filter_by(
                user_id=user_id,
                leave_type_id=balance_type.id,
                year=year,
            ).first()
            if balance:
                balance.used = max(0, balance.used - days_in_year)
        _remove_approved_leave_attendance(leave_request, leave_request.final_classification)

    leave_request.status = "cancelled"
    db.session.commit()

    return jsonify(leave_request.to_dict())


@bp.get("/my-requests")
@jwt_required()
def my_requests():
    user_id = int(get_jwt_identity())

    rows = (
        LeaveRequest.query
        .filter_by(user_id=user_id)
        .order_by(LeaveRequest.created_at.desc())
        .all()
    )

    return jsonify([row.to_dict() for row in rows])


@bp.get("/pending-approvals")
@jwt_required()
def pending_approvals():
    claims = get_jwt()
    role = claims.get("role")
    user_id = int(get_jwt_identity())

    if role not in APPROVER_ROLES:
        return jsonify({
            "message": "You do not have permission to view approvals."
        }), 403

    query = LeaveRequest.query.filter_by(status="pending").filter(
        LeaveRequest.user_id != user_id
    )

    if role == MANAGER:
        report_ids = [u.id for u in User.query.filter_by(manager_id=user_id).all()]
        query = query.filter(LeaveRequest.user_id.in_(report_ids))

    rows = query.order_by(LeaveRequest.created_at.asc()).all()

    return jsonify([row.to_dict() for row in rows])


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
        return jsonify({
            "message": "You do not have permission to approve or reject leave."
        }), 403

    leave_request = LeaveRequest.query.filter_by(id=request_id).with_for_update().first_or_404()
    if leave_request.user_id == reviewer_id:
        return jsonify({"message": "You cannot approve or reject your own leave request."}), 403
    if role == MANAGER and leave_request.user.manager_id != reviewer_id:
        return jsonify({"message": "You can only review leave requests from your direct reports."}), 403
    payload = request.get_json(silent=True) or {}

    if not isinstance(payload, dict):
        return jsonify({"message": "A valid decision is required."}), 400

    decision = payload.get("decision")

    if decision not in ("approved", "rejected"):
        return jsonify({
            "message": "decision must be 'approved' or 'rejected'."
        }), 400
    comment = payload.get("comment", "")
    if not isinstance(comment, str):
        return jsonify({"message": "Review comment must be text."}), 400
    comment = comment.strip()[:255]

    # A cancelled request cannot be reviewed. Return 400 to indicate that
    # the attempted action is invalid for this request's state.
    if leave_request.status == "cancelled":
        return jsonify({
            "message": "Cancelled leave requests cannot be approved or rejected."
        }), 400

    # Approved or rejected requests have already been reviewed. A repeated
    # decision conflicts with the existing review, so return 409.
    if leave_request.status != "pending":
        return jsonify({"message": "This leave request has already been reviewed."}), 409

    if decision == "approved":
        if leave_request.start_date.weekday() == 6 or leave_request.end_date.weekday() == 6:
            db.session.rollback()
            return jsonify({
                "message": "This request starts or ends on a Sunday. Ask the employee to correct and resubmit it."
            }), 409
        days_by_year = (
            {leave_request.start_date.year: 0.5}
            if leave_request.duration != "full_day"
            else _leave_days_by_year(leave_request.start_date, leave_request.end_date)
        )
        leave_request.days = sum(days_by_year.values())
        category = _category_name(leave_request.leave_type)
        final_classification = None
        if category == "sick":
            final_classification = payload.get("final_classification")
            if final_classification not in ("paid", "casual"):
                db.session.rollback()
                return jsonify({"message": "Sick Leave must be approved as Paid Leave or Casual Leave."}), 400
            eligibility, eligible, _ = _paid_leave_eligibility(leave_request.user)
            if final_classification == "paid" and not eligible:
                db.session.rollback()
                return jsonify({"message": "Sick Leave cannot be converted to Paid Leave during the first three months."}), 409
            leave_request.final_classification = final_classification
        elif category == "paid":
            final_classification = "paid"
        elif category == "casual":
            final_classification = "casual"

        consumed_balance_category = "paid" if (
            category in ("paid", "legacy")
            or (category == "sick" and final_classification == "paid")
        ) else None
        balance_type = leave_request.leave_type
        if consumed_balance_category:
            balance_type = LeaveType.query.filter_by(name="Paid Leave").first() or leave_request.leave_type
        if consumed_balance_category:
            for year in days_by_year:
                ensure_leave_balances(leave_request.user_id, year)
            db.session.flush()
            yearly_balances = []
            for year, days_in_year in days_by_year.items():
                balance = LeaveBalance.query.filter_by(
                    user_id=leave_request.user_id,
                    leave_type_id=balance_type.id,
                    year=year,
                ).with_for_update().first()
                if balance is None or balance.balance < days_in_year:
                    db.session.rollback()
                    available = balance.balance if balance else 0
                    return jsonify({
                        "message": f"Insufficient balance for {year}. Available: {available} day(s)."
                    }), 409
                yearly_balances.append((balance, days_in_year))
            for balance, days_in_year in yearly_balances:
                balance.used += days_in_year

    leave_request.status = decision
    leave_request.reviewed_by = reviewer_id
    leave_request.review_comment = comment
    leave_request.review_history.append(LeaveReviewHistory(
        reviewer_id=reviewer_id,
        action=decision,
        comment=comment,
    ))
    if decision == "approved":
        _sync_approved_leave_attendance(leave_request, final_classification)

    db.session.commit()

    return jsonify(leave_request.to_dict())


@bp.post("/<int:request_id>/reapprove")
@jwt_required()
def reapprove(request_id):
    role = get_jwt().get("role")
    reviewer_id = int(get_jwt_identity())
    if role not in APPROVER_ROLES:
        return jsonify({"message": "You do not have permission to reapprove leave."}), 403

    leave_request = LeaveRequest.query.filter_by(id=request_id).with_for_update().first_or_404()
    if leave_request.user_id == reviewer_id:
        return jsonify({"message": "You cannot approve your own leave request."}), 403
    if role == MANAGER and leave_request.user.manager_id != reviewer_id:
        return jsonify({"message": "You can only review leave requests from your direct reports."}), 403
    if leave_request.status != "rejected":
        return jsonify({"message": "Only rejected leave requests can be reapproved."}), 409
    if leave_request.start_date.weekday() == 6 or leave_request.end_date.weekday() == 6:
        db.session.rollback()
        return jsonify({
            "message": "This request starts or ends on a Sunday. Ask the employee to submit a corrected request."
        }), 409

    days_by_year = _leave_days_by_year(leave_request.start_date, leave_request.end_date)
    leave_request.days = sum(days_by_year.values())
    for year in days_by_year:
        ensure_leave_balances(leave_request.user_id, year)
    db.session.flush()
    yearly_balances = []
    for year, days_in_year in days_by_year.items():
        balance = LeaveBalance.query.filter_by(
            user_id=leave_request.user_id,
            leave_type_id=leave_request.leave_type_id,
            year=year,
        ).with_for_update().first()
        if balance is None or balance.balance < days_in_year:
            db.session.rollback()
            available = balance.balance if balance else 0
            return jsonify({
                "message": f"Insufficient balance for {year}. Available: {available} day(s)."
            }), 409
        yearly_balances.append((balance, days_in_year))

    for balance, days_in_year in yearly_balances:
        balance.used += days_in_year

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or not isinstance(payload.get("comment", ""), str):
        db.session.rollback()
        return jsonify({"message": "Review comment must be text."}), 400
    comment = payload.get("comment", "")
    comment = comment.strip()[:255]
    leave_request.status = "approved"
    leave_request.reviewed_by = reviewer_id
    leave_request.review_comment = comment
    leave_request.review_history.append(LeaveReviewHistory(
        reviewer_id=reviewer_id,
        action="reapproved",
        comment=comment,
    ))
    db.session.commit()
    return jsonify(leave_request.to_dict())
