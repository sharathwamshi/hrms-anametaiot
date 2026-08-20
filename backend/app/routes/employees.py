from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import User, Department
from app.utils.security import roles_required
from app.roles import ALL_ROLES, HR_OPERATIONS, HR_RECRUITER, MANAGER

bp = Blueprint("employees", __name__, url_prefix="/api/employees")


@bp.get("")
@jwt_required()
def list_employees():
    q = request.args.get("q", "").strip()
    department_id = request.args.get("department_id", type=int)
    role = request.args.get("role")

    query = User.query.filter_by(is_active=True)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(User.full_name.ilike(like), User.employee_code.ilike(like)))
    if department_id:
        query = query.filter_by(department_id=department_id)
    if role:
        query = query.filter_by(role=role)

    rows = query.order_by(User.full_name.asc()).all()
    return jsonify([u.to_dict() for u in rows])


@bp.get("/<int:emp_id>")
@jwt_required()
def get_employee(emp_id):
    user = User.query.get_or_404(emp_id)
    return jsonify(user.to_dict())


@bp.post("")
@roles_required(HR_OPERATIONS, MANAGER)
def create_employee():
    """HR Operations can onboard anyone into any reporting line. A Manager can
    onboard someone directly into their own team — the new hire's manager_id is
    forced to the creating Manager, regardless of what's in the payload, so a
    Manager can only ever create their own direct reports."""
    payload = request.get_json(silent=True) or {}
    claims = get_jwt()
    actor_id = int(get_jwt_identity())
    is_manager = claims.get("role") == MANAGER

    required = ["employee_code", "full_name", "email", "password", "role"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return jsonify({"message": f"Missing fields: {', '.join(missing)}"}), 400

    if payload["role"] not in ALL_ROLES:
        return jsonify({"message": "Invalid role."}), 400

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
    db.session.commit()
    return jsonify(user.to_dict()), 201


@bp.put("/<int:emp_id>")
@roles_required(HR_OPERATIONS, MANAGER)
def update_employee(emp_id):
    """HR Operations can edit anyone. A Manager can only edit their own direct
    reports, and cannot reassign a report to a different manager (that stays an
    HR Operations action) — this is how a Manager 'gives rights and roles' to
    their own team without being able to reach outside it."""
    user = User.query.get_or_404(emp_id)
    claims = get_jwt()
    actor_id = int(get_jwt_identity())
    is_manager = claims.get("role") == MANAGER

    if is_manager:
        if user.manager_id != actor_id:
            return jsonify({"message": "You can only edit your own direct reports."}), 403
        editable_fields = ["full_name", "phone", "designation", "role"]
    else:
        editable_fields = ["full_name", "phone", "designation", "department_id", "manager_id", "role"]

    payload = request.get_json(silent=True) or {}
    for field in editable_fields:
        if field in payload:
            if field == "role" and payload[field] not in ALL_ROLES:
                return jsonify({"message": "Invalid role."}), 400
            setattr(user, field, payload[field])

    if payload.get("date_of_joining"):
        user.date_of_joining = datetime.strptime(payload["date_of_joining"], "%Y-%m-%d").date()
    if "is_active" in payload and not is_manager:
        user.is_active = bool(payload["is_active"])

    db.session.commit()
    return jsonify(user.to_dict())


@bp.delete("/<int:emp_id>")
@roles_required(HR_OPERATIONS)
def deactivate_employee(emp_id):
    """Soft delete — HRMS records must be retained for compliance."""
    user = User.query.get_or_404(emp_id)
    user.is_active = False
    db.session.commit()
    return jsonify({"message": "Employee deactivated."})


@bp.get("/departments")
@jwt_required()
def list_departments():
    return jsonify([d.to_dict() for d in Department.query.order_by(Department.name).all()])


@bp.post("/departments")
@roles_required(HR_OPERATIONS)
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
    from app.models import Attendance, LeaveRequest, LeaveBalance

    target = User.query.get_or_404(emp_id)
    today = date.today()
    month_start = today.replace(day=1)

    present_days = Attendance.query.filter(
        Attendance.user_id == emp_id,
        Attendance.work_date >= month_start,
        Attendance.status.in_(["present", "half_day", "regularized"]),
    ).count()

    leave_taken_this_year = db.session.query(db.func.coalesce(db.func.sum(LeaveRequest.days), 0)).filter(
        LeaveRequest.user_id == emp_id, LeaveRequest.status == "approved",
        db.extract("year", LeaveRequest.start_date) == today.year,
    ).scalar()

    pending_leave_requests = LeaveRequest.query.filter_by(user_id=emp_id, status="pending").count()

    return jsonify({
        "employee": target.to_dict(),
        "present_days_this_month": present_days,
        "leave_days_taken_this_year": leave_taken_this_year,
        "pending_leave_requests": pending_leave_requests,
        "is_recruiter": target.role == "hr_recruiter",
    })
