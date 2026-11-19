import re
from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import EmployeeEmergencyCommunication, EmployeeFamilyMember, User
from app.roles import EMPLOYEE, HR_OPERATIONS, MANAGER, SUPER_ADMIN
from app.utils.security import roles_required

bp = Blueprint("employee_profile", __name__, url_prefix="/api")

PROFILE_FIELDS = {
    "full_name": (150, False),
    "email": (150, False),
    "phone": (20, True),
    "date_of_birth": (None, True),
    "gender": (30, True),
    "residential_address": (2000, True),
    "permanent_address": (2000, True),
    "emergency_contact_name": (150, True),
    "emergency_contact_relationship": (100, True),
    "emergency_contact_phone": (30, True),
}
FAMILY_FIELDS = {
    "name": (150, False),
    "relationship": (100, False),
    "date_of_birth": (None, True),
    "phone": (30, True),
    "is_emergency_contact": (None, True),
    "notes": (500, True),
}
COMMUNICATION_METHODS = {"phone", "sms", "email", "other"}


def _json_object():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None
    return payload


def _text(value, field, max_length, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text.")
    value = value.strip()
    if not value and optional:
        return None
    if not value:
        raise ValueError(f"{field} is required.")
    if max_length and len(value) > max_length:
        raise ValueError(f"{field} must be {max_length} characters or fewer.")
    return value


def _date(value, field, optional=True):
    if value in (None, "") and optional:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must use YYYY-MM-DD format.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must use YYYY-MM-DD format.")
    if parsed > date.today():
        raise ValueError(f"{field} cannot be in the future.")
    return parsed


def _authorize_profile(target_user_id):
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if target_user_id == actor_id:
        return None
    target = db.session.get(User, target_user_id)
    if target is None:
        return jsonify({"message": "Employee not found."}), 404
    if role in (HR_OPERATIONS, SUPER_ADMIN):
        return None
    if role == MANAGER and target.manager_id == actor_id:
        return None
    return jsonify({"message": "You do not have permission to access this employee profile."}), 403


def _authorize_hr_record(employee_id, allow_self=False):
    employee = User.query.get_or_404(employee_id)
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if allow_self and employee.id == actor_id:
        return employee, None
    if role in (HR_OPERATIONS, SUPER_ADMIN):
        return employee, None
    if (
        role == MANAGER
        and employee.id != actor_id
        and employee.manager_id == actor_id
        and employee.role != SUPER_ADMIN
    ):
        return employee, None
    return None, (jsonify({"message": "You can only access HR records for your own direct reports."}), 403)


def _validate_profile(payload):
    unknown = set(payload) - set(PROFILE_FIELDS)
    if unknown:
        protected = ", ".join(sorted(unknown))
        raise ValueError(f"These fields cannot be edited from My Profile: {protected}.")

    values = {}
    for field, (limit, optional) in PROFILE_FIELDS.items():
        if field not in payload:
            continue
        if field == "date_of_birth":
            values[field] = _date(payload[field], "Date of birth")
        else:
            value = _text(payload[field], field.replace("_", " ").title(), limit, optional)
            if field == "email" and value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
                raise ValueError("Enter a valid email address.")
            if field == "phone" and value and not re.fullmatch(r"[+0-9().\-\s]{5,20}", value):
                raise ValueError("Enter a valid phone number.")
            if field == "emergency_contact_phone" and value and not re.fullmatch(r"[+0-9().\-\s]{5,30}", value):
                raise ValueError("Enter a valid emergency contact phone number.")
            values[field] = value.lower() if field == "email" and value else value
    return values


@bp.get("/profile/me")
@jwt_required()
def get_my_profile():
    user = User.query.get_or_404(int(get_jwt_identity()))
    return jsonify(user.personal_profile_dict())


@bp.patch("/profile/me")
@jwt_required()
def update_my_profile():
    user = User.query.get_or_404(int(get_jwt_identity()))
    payload = _json_object()
    if payload is None:
        return jsonify({"message": "Profile data must be a JSON object."}), 400
    try:
        values = _validate_profile(payload)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    if "email" in values:
        duplicate = User.query.filter(
            User.email == values["email"], User.id != user.id
        ).first()
        if duplicate:
            return jsonify({"message": "Email already in use."}), 409
    for field, value in values.items():
        setattr(user, field, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Email already in use."}), 409
    return jsonify({
        "message": "Profile updated successfully.",
        "profile": user.personal_profile_dict(),
        "user": user.to_dict(),
    })


@bp.get("/employees/<int:employee_id>/profile")
@jwt_required()
def get_employee_profile(employee_id):
    user = User.query.get_or_404(employee_id)
    denied = _authorize_profile(user.id)
    if denied:
        return denied
    return jsonify(user.personal_profile_dict())


@bp.patch("/employees/<int:employee_id>/profile")
@jwt_required()
def update_employee_profile(employee_id):
    user = User.query.get_or_404(employee_id)
    denied = _authorize_profile(user.id)
    if denied:
        return denied
    payload = _json_object()
    if payload is None:
        return jsonify({"message": "Profile data must be a JSON object."}), 400
    try:
        values = _validate_profile(payload)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    if "email" in values:
        duplicate = User.query.filter(
            User.email == values["email"], User.id != user.id
        ).first()
        if duplicate:
            return jsonify({"message": "Email already in use."}), 409
    for field, value in values.items():
        setattr(user, field, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Email already in use."}), 409
    return jsonify({
        "message": "Profile updated successfully.",
        "profile": user.personal_profile_dict(),
        "user": user.to_dict(),
    })


def _family_payload(payload, partial=False):
    unknown = set(payload) - set(FAMILY_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported family-member field(s): {', '.join(sorted(unknown))}.")
    values = {}
    for field, (limit, optional) in FAMILY_FIELDS.items():
        if field not in payload:
            if not partial and not optional:
                raise ValueError(f"{field.replace('_', ' ').title()} is required.")
            continue
        if field == "date_of_birth":
            values[field] = _date(payload[field], "Date of birth")
        elif field == "is_emergency_contact":
            if not isinstance(payload[field], bool):
                raise ValueError("is_emergency_contact must be true or false.")
            values[field] = payload[field]
        else:
            values[field] = _text(payload[field], field.replace("_", " ").title(), limit, optional)
    return values


@bp.get("/profile/family")
@jwt_required()
def list_family_members():
    target_user_id = request.args.get("user_id", type=int) or int(get_jwt_identity())
    denied = _authorize_profile(target_user_id)
    if denied:
        return denied
    rows = EmployeeFamilyMember.query.filter_by(user_id=target_user_id).order_by(
        EmployeeFamilyMember.name.asc(), EmployeeFamilyMember.id.asc()
    ).all()
    return jsonify([row.to_dict() for row in rows])


@bp.post("/profile/family")
@jwt_required()
def create_family_member():
    payload = _json_object()
    if payload is None:
        return jsonify({"message": "Family-member data must be a JSON object."}), 400
    target_user_id = request.args.get("user_id", type=int) or int(get_jwt_identity())
    denied = _authorize_profile(target_user_id)
    if denied:
        return denied
    try:
        values = _family_payload(payload)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    member = EmployeeFamilyMember(user_id=target_user_id, **values)
    db.session.add(member)
    db.session.commit()
    return jsonify(member.to_dict()), 201


@bp.put("/profile/family/<int:member_id>")
@jwt_required()
def update_family_member(member_id):
    member = EmployeeFamilyMember.query.get_or_404(member_id)
    denied = _authorize_profile(member.user_id)
    if denied:
        return denied
    payload = _json_object()
    if payload is None:
        return jsonify({"message": "Family-member data must be a JSON object."}), 400
    try:
        values = _family_payload(payload, partial=True)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    for field, value in values.items():
        setattr(member, field, value)
    db.session.commit()
    return jsonify(member.to_dict())


@bp.delete("/profile/family/<int:member_id>")
@jwt_required()
def delete_family_member(member_id):
    member = EmployeeFamilyMember.query.get_or_404(member_id)
    denied = _authorize_profile(member.user_id)
    if denied:
        return denied
    db.session.delete(member)
    db.session.commit()
    return jsonify({"message": "Family member removed."})


@bp.get("/employees/<int:employee_id>/statutory")
@roles_required(HR_OPERATIONS, SUPER_ADMIN, MANAGER, EMPLOYEE)
def get_employee_statutory(employee_id):
    employee, denied = _authorize_hr_record(employee_id, allow_self=True)
    if denied:
        return denied
    return jsonify({"user_id": employee.id, "uan": employee.uan})


@bp.put("/employees/<int:employee_id>/statutory")
@roles_required(HR_OPERATIONS, SUPER_ADMIN, MANAGER)
def update_employee_statutory(employee_id):
    employee, denied = _authorize_hr_record(employee_id)
    if denied:
        return denied
    payload = _json_object()
    if payload is None or set(payload) != {"uan"}:
        return jsonify({"message": "Provide only the uan field."}), 400
    uan = payload["uan"]
    if uan in (None, ""):
        employee.uan = None
    elif not isinstance(uan, str) or not re.fullmatch(r"\d{12}", uan.strip()):
        return jsonify({"message": "UAN must contain exactly 12 digits."}), 400
    else:
        employee.uan = uan.strip()
    db.session.commit()
    return jsonify({"user_id": employee.id, "uan": employee.uan})


@bp.get("/employees/<int:employee_id>/emergency-communications")
@roles_required(HR_OPERATIONS, SUPER_ADMIN, MANAGER)
def list_emergency_communications(employee_id):
    _, denied = _authorize_hr_record(employee_id)
    if denied:
        return denied
    rows = EmployeeEmergencyCommunication.query.filter_by(employee_id=employee_id).order_by(
        EmployeeEmergencyCommunication.contacted_at.desc(),
        EmployeeEmergencyCommunication.id.desc(),
    ).all()
    return jsonify([row.to_dict() for row in rows])


@bp.post("/employees/<int:employee_id>/emergency-communications")
@roles_required(HR_OPERATIONS, SUPER_ADMIN, MANAGER)
def record_emergency_communication(employee_id):
    employee, denied = _authorize_hr_record(employee_id)
    if denied:
        return denied
    payload = _json_object()
    required = {"contact_name", "communication_method", "purpose"}
    allowed = required | {
        "family_member_id", "relationship", "contact_phone", "notes", "outcome",
        "contacted_at",
    }
    if payload is None:
        return jsonify({"message": "Communication data must be a JSON object."}), 400
    if set(payload) - allowed or not required.issubset(payload):
        return jsonify({"message": "Provide contact_name, communication_method, and purpose; unsupported fields are not allowed."}), 400
    try:
        contact_name = _text(payload["contact_name"], "Contact name", 150)
        purpose = _text(payload["purpose"], "Purpose", 255)
        method = _text(payload["communication_method"], "Communication method", 30)
        if method not in COMMUNICATION_METHODS:
            raise ValueError("Communication method must be phone, sms, email, or other.")
        relationship = _text(payload.get("relationship"), "Relationship", 100, True)
        contact_phone = _text(payload.get("contact_phone"), "Contact phone", 30, True)
        notes = _text(payload.get("notes"), "Notes", 1000, True)
        outcome = _text(payload.get("outcome"), "Outcome", 255, True)
        contacted_at = datetime.fromisoformat(payload["contacted_at"]) if payload.get("contacted_at") else datetime.utcnow()
        family_member_id = payload.get("family_member_id")
        if family_member_id is not None:
            family = EmployeeFamilyMember.query.filter_by(
                id=family_member_id, user_id=employee_id
            ).first()
            if family is None:
                raise ValueError("The selected family member does not belong to this employee.")
    except (ValueError, TypeError) as exc:
        return jsonify({"message": str(exc)}), 400
    communication = EmployeeEmergencyCommunication(
        employee_id=employee_id,
        family_member_id=family_member_id,
        contact_name=contact_name,
        relationship=relationship,
        contact_phone=contact_phone,
        communication_method=method,
        purpose=purpose,
        notes=notes,
        outcome=outcome,
        contacted_at=contacted_at,
        recorded_by=int(get_jwt_identity()),
    )
    db.session.add(communication)
    db.session.commit()
    return jsonify(communication.to_dict()), 201
