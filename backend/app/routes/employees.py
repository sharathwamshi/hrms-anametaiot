from datetime import date, datetime
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import User, Department, DeviceToken, LeaveRequest, SalaryStructure
from app.models.leave import ensure_leave_balances
from app.utils.compensation import normalize_annual_ctc
from app.utils.security import roles_required
from app.roles import ADMIN_ROLES, ALL_ROLES, HR_OPERATIONS, HR_RECRUITER, MANAGER, SUPER_ADMIN
from sqlalchemy.exc import SQLAlchemyError

bp = Blueprint("employees", __name__, url_prefix="/api/employees")


MAX_REMOVAL_REASON = 255
COMPENSATION_FIELDS = {"annual_ctc", "ctc", "compensation"}


def _remove_user(user, actor_id, actor_role, reason):
    """Removes (deactivates) a person, with the same safeguards wherever it's triggered.
    Returns an error response, or None on success (caller commits).

    Never a hard delete: payslips, attendance, leave, documents, placements and 40+ other
    records reference a user and must be retained for compliance."""
    if user.id == actor_id:
        return jsonify({"message": "You can't remove your own account."}), 400
    if user.role == SUPER_ADMIN and actor_role != SUPER_ADMIN:
        return jsonify({"message": "Only a Super Admin can remove a Super Admin."}), 403
    if actor_role == MANAGER:
        if user.manager_id != actor_id:
            return jsonify({"message": "You can only remove your own direct reports."}), 403
        if user.role == HR_OPERATIONS:
            return jsonify({"message": "Only HR Operations can remove an HR Operations user."}), 403
    if not user.is_active:
        return jsonify({"message": f"{user.full_name} has already been removed."}), 400

    reason = (reason or "").strip()
    if len(reason) < 3:
        return jsonify({"message": "Please give a reason for removing this person.", "reason_required": True}), 400
    if len(reason) > MAX_REMOVAL_REASON:
        return jsonify({"message": f"Please keep the reason under {MAX_REMOVAL_REASON} characters.", "reason_required": True}), 400

    reports = User.query.filter_by(manager_id=user.id, is_active=True).count()
    if reports:
        who = "HR Operations can reassign them" if actor_role == MANAGER else "reassign them first"
        return jsonify({
            "message": f"{user.full_name} still has {reports} active direct report{'s' if reports != 1 else ''} — {who} before removing this person.",
            "active_reports": reports,
        }), 409

    user.is_active = False
    user.removed_at = datetime.utcnow()
    user.removed_by = actor_id
    user.removal_reason = reason
    # Stop pushes to their phone, and don't leave their pending leave stuck in approvers' queues.
    DeviceToken.query.filter_by(user_id=user.id).delete()
    for leave in LeaveRequest.query.filter_by(user_id=user.id, status="pending").all():
        leave.status = "cancelled"
        leave.review_comment = "Cancelled automatically — employee was removed."
    return None


@bp.get("")
@jwt_required()
def list_employees():
    q = request.args.get("q", "").strip()
    department_id = request.args.get("department_id", type=int)
    role = request.args.get("role")
    status = request.args.get("status")

    if status == "removed":
        # Removed people: HR Operations sees everyone's, a Manager only their own reports'.
        claims, actor_id = get_jwt(), int(get_jwt_identity())
        if claims.get("role") in (HR_OPERATIONS, SUPER_ADMIN):
            query = User.query.filter_by(is_active=False)
        elif claims.get("role") == MANAGER:
            query = User.query.filter_by(is_active=False, manager_id=actor_id)
        else:
            return jsonify({"message": "You do not have permission to view removed employees."}), 403
    elif status == "resignation_pending":
        claims, actor_id = get_jwt(), int(get_jwt_identity())
        if claims.get("role") in (HR_OPERATIONS, SUPER_ADMIN):
            query = User.query.filter_by(is_active=True, employment_status="resignation_pending")
        elif claims.get("role") == MANAGER:
            query = User.query.filter_by(
                is_active=True,
                employment_status="resignation_pending",
                manager_id=actor_id,
            )
        else:
            return jsonify({"message": "You do not have permission to view pending resignation requests."}), 403
    else:
        query = User.query.filter_by(is_active=True)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(User.full_name.ilike(like), User.employee_code.ilike(like)))
    if department_id:
        query = query.filter_by(department_id=department_id)
    if role:
        query = query.filter_by(role=role)

    if status == "removed":
        rows = query.order_by(User.removed_at.desc(), User.full_name.asc()).all()
    else:
        rows = query.order_by(User.full_name.asc()).all()
    return jsonify([u.to_dict() for u in rows])


@bp.get("/<int:emp_id>")
@jwt_required()
def get_employee(emp_id):
    user = User.query.get_or_404(emp_id)
    return jsonify(user.to_dict())


@bp.get("/<int:emp_id>/compensation")
@roles_required(*ADMIN_ROLES)
def get_employee_compensation(emp_id):
    user = User.query.get_or_404(emp_id)
    structure = SalaryStructure.query.filter_by(user_id=user.id).first()
    annual_ctc = structure.annual_ctc if structure else None
    return jsonify({
        "user_id": user.id,
        "annual_ctc": format(annual_ctc, ".2f") if annual_ctc is not None else None,
    })


@bp.post("")
@roles_required(HR_OPERATIONS, MANAGER, SUPER_ADMIN)
def create_employee():
    """HR Operations can onboard anyone into any reporting line. A Manager can
    onboard someone directly into their own team — the new hire's manager_id is
    forced to the creating Manager, regardless of what's in the payload, so a
    Manager can only ever create their own direct reports."""
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"message": "Employee data must be a JSON object."}), 400
    claims = get_jwt()
    actor_id = int(get_jwt_identity())
    is_manager = claims.get("role") == MANAGER
    has_compensation = bool(COMPENSATION_FIELDS.intersection(payload))

    if has_compensation and claims.get("role") not in ADMIN_ROLES:
        return jsonify({"message": "You do not have permission to set employee compensation."}), 403
    if "ctc" in payload or "compensation" in payload:
        return jsonify({"message": "Use the annual_ctc field to set employee compensation."}), 400
    try:
        annual_ctc = normalize_annual_ctc(payload["annual_ctc"]) if "annual_ctc" in payload and payload["annual_ctc"] not in (None, "") else None
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    required = ["employee_code", "full_name", "email", "password", "role"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return jsonify({"message": f"Missing fields: {', '.join(missing)}"}), 400

    if payload["role"] not in ALL_ROLES:
        return jsonify({"message": "Invalid role."}), 400
    if payload["role"] == SUPER_ADMIN and claims.get("role") != SUPER_ADMIN:
        return jsonify({"message": "Only a Super Admin can create another Super Admin."}), 403

    if User.query.filter_by(email=payload["email"].lower()).first():
        return jsonify({"message": "Email already in use."}), 409

    if User.query.filter_by(employee_code=payload["employee_code"]).first():
        return jsonify({"message": f"Employee code '{payload['employee_code']}' is already in use. Please use a different code."}), 409

    user = User(
        employee_code=payload["employee_code"],
        full_name=payload["full_name"],
        email=payload["email"].lower(),
        phone=payload.get("phone"),
        role=payload["role"],
        designation=payload.get("designation"),
        department_id=payload.get("department_id"),
        manager_id=actor_id if is_manager else payload.get("manager_id"),
        date_of_joining=datetime.strptime(payload["date_of_joining"], "%Y-%m-%d").date()
        if payload.get("date_of_joining")
        else None,
    )
    user.set_password(payload["password"])
    db.session.add(user)
    try:
        db.session.flush()
        if annual_ctc is not None:
            db.session.add(SalaryStructure(user_id=user.id, annual_ctc=annual_ctc))
        ensure_leave_balances(user.id, date.today().year)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Employee creation failed while saving employee data.")
        return jsonify({"message": "Could not create employee. Please try again."}), 500
    return jsonify(user.to_dict()), 201


@bp.put("/<int:emp_id>")
@roles_required(HR_OPERATIONS, MANAGER, SUPER_ADMIN)
def update_employee(emp_id):
    """HR Operations can edit anyone. A Manager can only edit their own direct
    reports, and cannot reassign a report to a different manager (that stays an
    HR Operations action) — this is how a Manager 'gives rights and roles' to
    their own team without being able to reach outside it."""
    user = User.query.get_or_404(emp_id)
    claims = get_jwt()
    actor_id = int(get_jwt_identity())
    is_manager = claims.get("role") == MANAGER
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"message": "Employee data must be a JSON object."}), 400
    has_compensation = bool(COMPENSATION_FIELDS.intersection(payload))
    if has_compensation and claims.get("role") not in ADMIN_ROLES:
        return jsonify({"message": "You do not have permission to change employee compensation."}), 403
    if "ctc" in payload or "compensation" in payload:
        return jsonify({"message": "Use the annual_ctc field to update employee compensation."}), 400
    try:
        annual_ctc = normalize_annual_ctc(payload["annual_ctc"]) if "annual_ctc" in payload and payload["annual_ctc"] not in (None, "") else None
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    if claims.get("role") != SUPER_ADMIN:
        # Only a Super Admin may touch a Super Admin, or hand out the role.
        if user.role == SUPER_ADMIN:
            return jsonify({"message": "Only a Super Admin can change a Super Admin."}), 403
        if payload.get("role") == SUPER_ADMIN:
            return jsonify({"message": "Only a Super Admin can grant the Super Admin role."}), 403

    if is_manager:
        if user.manager_id != actor_id:
            return jsonify({"message": "You can only edit your own direct reports."}), 403
        editable_fields = ["full_name", "phone", "designation", "role"]
    else:
        editable_fields = ["full_name", "phone", "designation", "department_id", "manager_id", "role"]

    for field in editable_fields:
        if field in payload:
            if field == "role" and payload[field] not in ALL_ROLES:
                return jsonify({"message": "Invalid role."}), 400
            setattr(user, field, payload[field])

    if payload.get("date_of_joining"):
        user.date_of_joining = datetime.strptime(payload["date_of_joining"], "%Y-%m-%d").date()
    if "is_active" in payload and not is_manager:
        if payload["is_active"] and not user.is_active:
            user.is_active = True
            user.removed_at = user.removed_by = user.removal_reason = None
        elif not payload["is_active"] and user.is_active:
            err = _remove_user(user, actor_id, claims.get("role"), payload.get("removal_reason") or "Deactivated by HR Operations")
            if err:
                db.session.rollback()
                return err

    if "annual_ctc" in payload:
        structure = SalaryStructure.query.filter_by(user_id=user.id).first()
        if structure is None and annual_ctc is not None:
            structure = SalaryStructure(user_id=user.id)
            db.session.add(structure)
        if structure is not None:
            structure.annual_ctc = annual_ctc

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Employee update failed while saving employee data.")
        return jsonify({"message": "Could not update employee. Please try again."}), 500
    return jsonify(user.to_dict())


@bp.post("/me/resignation")
@jwt_required()
def request_resignation():
    user = User.query.get_or_404(int(get_jwt_identity()))
    if not user.is_active:
        return jsonify({"message": "Your account is inactive."}), 403
    if user.employment_status != "active":
        return jsonify({"message": "A resignation request can only be submitted while your employment status is Active."}), 409

    user.employment_status = "resignation_pending"
    user.resignation_requested_at = datetime.utcnow()
    user.resignation_reviewed_at = None
    user.resignation_reviewed_by = None
    user.resignation_decision = "pending"
    user.notice_period_days = None
    user.last_working_day = None
    user.resignation_withdrawn_at = None
    user.left_company_at = None
    db.session.commit()
    return jsonify({"message": "Your resignation request was sent to your manager.", "user": user.to_dict()}), 201


@bp.post("/me/resignation/withdraw")
@jwt_required()
def withdraw_resignation():
    user = User.query.get_or_404(int(get_jwt_identity()))
    if user.employment_status not in ("resignation_pending", "notice_period"):
        return jsonify({"message": "There is no active resignation to withdraw."}), 409

    user.employment_status = "active"
    user.resignation_decision = "withdrawn"
    user.resignation_withdrawn_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Your resignation has been withdrawn. Your employment status is Active.", "user": user.to_dict()})


@bp.post("/<int:emp_id>/resignation/review")
@jwt_required()
def review_resignation(emp_id):
    user = User.query.get_or_404(emp_id)
    actor_id = int(get_jwt_identity())
    actor_role = get_jwt().get("role")
    can_review = (
        actor_role in (HR_OPERATIONS, SUPER_ADMIN)
        or (actor_role == MANAGER and user.manager_id == actor_id)
    )
    if not can_review:
        return jsonify({"message": "Only the employee's direct manager or HR Operations can review this resignation."}), 403
    if user.employment_status != "resignation_pending":
        return jsonify({"message": "This employee has no pending resignation request."}), 409

    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision")
    if decision not in ("accepted", "rejected"):
        return jsonify({"message": "Decision must be accepted or rejected."}), 400
    last_working_day = None
    if decision == "accepted":
        raw_last_working_day = payload.get("last_working_day")
        try:
            last_working_day = date.fromisoformat(raw_last_working_day)
        except (TypeError, ValueError):
            return jsonify({"message": "Choose a valid notice-period end date."}), 400
        if last_working_day.isoformat() != raw_last_working_day:
            return jsonify({"message": "Choose a valid notice-period end date."}), 400
        if last_working_day < date.today():
            return jsonify({"message": "The notice-period end date cannot be in the past."}), 400

    user.resignation_reviewed_at = datetime.utcnow()
    user.resignation_reviewed_by = actor_id
    user.resignation_decision = decision
    if decision == "accepted":
        user.employment_status = "notice_period"
        user.last_working_day = last_working_day
        user.notice_period_days = (last_working_day - date.today()).days
    else:
        user.employment_status = "active"
        user.notice_period_days = None
        user.last_working_day = None
    db.session.commit()
    return jsonify({"message": f"Resignation {decision}.", "employee": user.to_dict()})


@bp.post("/<int:emp_id>/employment-status")
@jwt_required()
def update_employment_status(emp_id):
    user = User.query.get_or_404(emp_id)
    actor_id = int(get_jwt_identity())
    actor_role = get_jwt().get("role")
    can_manage_status = (
        actor_role in (HR_OPERATIONS, SUPER_ADMIN)
        or (actor_role == MANAGER and user.manager_id == actor_id)
    )
    if not can_manage_status:
        return jsonify({"message": "Only the employee's direct manager or HR Operations can update their employment status."}), 403

    payload = request.get_json(silent=True) or {}
    if payload.get("employment_status") != "left":
        if payload.get("employment_status") == "active" and user.employment_status == "left":
            user.employment_status = "active"
            user.left_company_at = None
            db.session.commit()
            return jsonify({
                "message": f"{user.full_name}'s employment has been reactivated.",
                "employee": user.to_dict(),
            })
        return jsonify({"message": "Employment status can only be changed to Active for an employee marked as Left the company."}), 400
    if user.employment_status == "left":
        return jsonify({"message": "This employee is already marked as having left the company."}), 409

    user.employment_status = "left"
    user.left_company_at = date.today()
    db.session.commit()
    return jsonify({"message": f"{user.full_name} is marked as having left the company.", "employee": user.to_dict()})


@bp.delete("/<int:emp_id>")
@roles_required(HR_OPERATIONS, MANAGER, SUPER_ADMIN)
def remove_employee(emp_id):
    """Remove a person. HR Operations can remove anyone; a Manager only their own direct
    reports. Requires a reason, which is recorded with who/when. Reversible via /restore."""
    user = User.query.get_or_404(emp_id)
    claims = get_jwt()
    payload = request.get_json(silent=True) or {}
    err = _remove_user(user, int(get_jwt_identity()), claims.get("role"), payload.get("reason"))
    if err:
        db.session.rollback()
        return err
    db.session.commit()
    return jsonify({"message": f"{user.full_name} has been removed.", "employee": user.to_dict()})


@bp.post("/<int:emp_id>/restore")
@roles_required(HR_OPERATIONS, MANAGER, SUPER_ADMIN)
def restore_employee(emp_id):
    """Undo a removal. HR Operations can restore anyone; a Manager only someone THEY removed
    (so a manager can't overturn an HR Operations decision)."""
    user = User.query.get_or_404(emp_id)
    claims = get_jwt()
    actor_id = int(get_jwt_identity())
    if user.is_active:
        return jsonify({"message": f"{user.full_name} is not removed."}), 400
    if claims.get("role") == MANAGER and not (user.manager_id == actor_id and user.removed_by == actor_id):
        return jsonify({"message": "You can only restore a direct report that you removed yourself. Ask HR Operations."}), 403
    user.is_active = True
    user.removed_at = user.removed_by = user.removal_reason = None
    db.session.commit()
    return jsonify({"message": f"{user.full_name} has been restored.", "employee": user.to_dict()})


@bp.get("/departments")
@jwt_required()
def list_departments():
    return jsonify([d.to_dict() for d in Department.query.order_by(Department.name).all()])


@bp.post("/departments")
@roles_required(HR_OPERATIONS, SUPER_ADMIN)
def create_department():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"message": "Department name is required."}), 400
    if Department.query.filter_by(name=name).first():
        return jsonify({"message": "Department already exists."}), 409

    dept = Department(name=name)
    db.session.add(dept)
    db.session.commit()
    return jsonify(dept.to_dict()), 201


@bp.post("/convert-candidate/<int:candidate_id>")
@roles_required(HR_OPERATIONS, HR_RECRUITER)
def convert_candidate_to_employee(candidate_id):
    """Hire -> Employee handoff (Section 15 of the Recruiter Specification).
    Pre-fills from the candidate/offer; recruiter/admin supplies the fields the
    candidate record doesn't have (employee code, role, manager, password)."""
    from app.models import Candidate, Offer
    from app.utils.audit import log_action

    candidate = Candidate.query.get_or_404(candidate_id)
    if candidate.stage != "hired":
        return jsonify({"message": "Only a candidate at the Hired stage can be converted."}), 400
    if candidate.linked_employee_id:
        return jsonify({"message": "This candidate has already been converted to an employee."}), 400
    if candidate.job and candidate.job.requisition_type == "client":
        # Sourced for a vendor's role, not for AnametaIOT: they must never become
        # an internal employee. They are placed with the vendor instead (Vendors ->
        # Assign Hire), which creates a limited Contract Employee login only when
        # the placement is a contract one.
        return jsonify({"message": "This candidate was sourced for a client requisition. Place them with the vendor instead of converting them to an AnametaIOT employee."}), 400

    payload = request.get_json(silent=True) or {}
    required = ["employee_code", "password", "role"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return jsonify({"message": f"Missing fields: {', '.join(missing)}"}), 400
    if payload["role"] not in ALL_ROLES:
        return jsonify({"message": "Invalid role."}), 400
    if User.query.filter_by(employee_code=payload["employee_code"]).first():
        return jsonify({"message": f"Employee code '{payload['employee_code']}' is already in use. Please use a different code."}), 409

    accepted_offer = Offer.query.filter_by(candidate_id=candidate.id, status="accepted").first()

    user = User(
        employee_code=payload["employee_code"],
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        role=payload["role"],
        designation=accepted_offer.designation if accepted_offer else payload.get("designation"),
        department_id=candidate.job.department_id if candidate.job else payload.get("department_id"),
        manager_id=payload.get("manager_id"),
        date_of_joining=accepted_offer.joining_date if accepted_offer else None,
    )
    user.set_password(payload["password"])
    db.session.add(user)
    db.session.flush()
    ensure_leave_balances(user.id, date.today().year)

    candidate.linked_employee_id = user.id
    log_action(candidate.id, "converted_to_employee", actor_id=int(get_jwt_identity()),
               detail=f"Employee #{user.id} ({user.employee_code}) created")
    db.session.commit()
    return jsonify(user.to_dict()), 201


# ============================================================================
# Roles & permissions — a Manager can extend specific approval capabilities
# to their own direct reports; HR Operations can do this for anyone.
# ============================================================================

@bp.get("/permissions/catalogue")
@jwt_required()
def permissions_catalogue():
    from app.models.permission import PERMISSION_CATALOGUE
    return jsonify([{"key": k, "label": v} for k, v in PERMISSION_CATALOGUE.items()])


def _can_manage_permissions_for(actor_claims, actor_id, target_user):
    if actor_claims.get("role") == HR_OPERATIONS:
        return True
    return actor_claims.get("role") == MANAGER and target_user.manager_id == actor_id


@bp.get("/<int:emp_id>/permissions")
@jwt_required()
def list_employee_permissions(emp_id):
    from app.models import EmployeePermission
    claims = get_jwt()
    actor_id = int(get_jwt_identity())
    target = User.query.get_or_404(emp_id)

    if actor_id != emp_id and not _can_manage_permissions_for(claims, actor_id, target):
        return jsonify({"message": "You do not have permission to view this."}), 403

    rows = EmployeePermission.query.filter_by(user_id=emp_id).all()
    return jsonify([p.to_dict() for p in rows])


@bp.post("/<int:emp_id>/permissions")
@jwt_required()
def grant_employee_permission(emp_id):
    from app.models import EmployeePermission
    from app.models.permission import PERMISSION_CATALOGUE
    claims = get_jwt()
    actor_id = int(get_jwt_identity())
    target = User.query.get_or_404(emp_id)

    if not _can_manage_permissions_for(claims, actor_id, target):
        return jsonify({"message": "You can only manage permissions for your own direct reports."}), 403

    payload = request.get_json(silent=True) or {}
    key = payload.get("permission_key")
    if key not in PERMISSION_CATALOGUE:
        return jsonify({"message": f"Unknown permission. Valid options: {list(PERMISSION_CATALOGUE.keys())}"}), 400

    if EmployeePermission.query.filter_by(user_id=emp_id, permission_key=key).first():
        return jsonify({"message": "Already granted."}), 409

    grant = EmployeePermission(user_id=emp_id, permission_key=key, granted_by=actor_id)
    db.session.add(grant)
    db.session.commit()
    return jsonify(grant.to_dict()), 201


@bp.delete("/<int:emp_id>/permissions/<string:permission_key>")
@jwt_required()
def revoke_employee_permission(emp_id, permission_key):
    from app.models import EmployeePermission
    claims = get_jwt()
    actor_id = int(get_jwt_identity())
    target = User.query.get_or_404(emp_id)

    if not _can_manage_permissions_for(claims, actor_id, target):
        return jsonify({"message": "You can only manage permissions for your own direct reports."}), 403

    grant = EmployeePermission.query.filter_by(user_id=emp_id, permission_key=permission_key).first()
    if grant:
        db.session.delete(grant)
        db.session.commit()
    return jsonify({"message": "Revoked."})


# ============================================================================
# Performance snapshot — used by the Manager's employee detail view
# ============================================================================

@bp.get("/<int:emp_id>/performance-snapshot")
@jwt_required()
def performance_snapshot(emp_id):
    """A general-purpose performance view for any employee (attendance +
    leave usage). Recruiters additionally get their recruiting stats via
    the existing /api/dashboard/recruiter-performance endpoint — this one
    covers everyone else so a Manager always has something to look at."""
    from datetime import date
    from app.models import Attendance, LeaveRequest

    target = User.query.get_or_404(emp_id)
    today = date.today()
    month_start = today.replace(day=1)

    present_days = Attendance.query.filter(
        Attendance.user_id == emp_id,
        Attendance.work_date >= month_start,
        Attendance.status.in_(["present", "half_day", "regularized"]),
    ).count()

    year_start = date(today.year, 1, 1)
    year_end = date(today.year, 12, 31)
    approved_leave = LeaveRequest.query.filter(
        LeaveRequest.user_id == emp_id,
        LeaveRequest.status == "approved",
        LeaveRequest.start_date <= year_end,
        LeaveRequest.end_date >= year_start,
    ).all()
    leave_taken_this_year = sum(
        (min(leave.end_date, year_end) - max(leave.start_date, year_start)).days + 1
        for leave in approved_leave
    )

    pending_leave_requests = LeaveRequest.query.filter_by(user_id=emp_id, status="pending").count()

    return jsonify({
        "employee": target.to_dict(),
        "present_days_this_month": present_days,
        "leave_days_taken_this_year": leave_taken_this_year,
        "pending_leave_requests": pending_leave_requests,
        "is_recruiter": target.role == "hr_recruiter",
    })
