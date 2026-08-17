from datetime import datetime, date
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import Attendance, User
from app.roles import ROLES_WITH_CLOCK_IN_OUT, MANAGER, HR_OPERATIONS, OPERATIONS

bp = Blueprint("attendance", __name__, url_prefix="/api/attendance")


def _guard_clock_eligibility(role):
    if role not in ROLES_WITH_CLOCK_IN_OUT:
        return jsonify(
            {"message": "Contract employees log hours via timesheets, not clock in/out."}
        ), 403
    return None


@bp.post("/clock-in")
@jwt_required()
def clock_in():
    claims = get_jwt()
    blocked = _guard_clock_eligibility(claims.get("role"))
    if blocked:
        return blocked

    user_id = int(get_jwt_identity())
    today = date.today()
    record = Attendance.query.filter_by(user_id=user_id, work_date=today).first()

    if record and record.clock_in:
        return jsonify({"message": "You have already clocked in today."}), 400

    note = (request.get_json(silent=True) or {}).get("note")
    if not record:
        record = Attendance(user_id=user_id, work_date=today)
        db.session.add(record)

    record.clock_in = datetime.utcnow()
    record.clock_in_note = note
    record.status = "present"
    db.session.commit()
    return jsonify(record.to_dict()), 201


@bp.post("/clock-out")
@jwt_required()
def clock_out():
    claims = get_jwt()
    blocked = _guard_clock_eligibility(claims.get("role"))
    if blocked:
        return blocked

    user_id = int(get_jwt_identity())
    today = date.today()
    record = Attendance.query.filter_by(user_id=user_id, work_date=today).first()

    if not record or not record.clock_in:
        return jsonify({"message": "You need to clock in before clocking out."}), 400
    if record.clock_out:
        return jsonify({"message": "You have already clocked out today."}), 400

    note = (request.get_json(silent=True) or {}).get("note")
    record.clock_out = datetime.utcnow()
    record.clock_out_note = note
    record.recompute_hours()
    db.session.commit()
    return jsonify(record.to_dict())


@bp.get("/today")
@jwt_required()
def today_status():
    user_id = int(get_jwt_identity())
    record = Attendance.query.filter_by(user_id=user_id, work_date=date.today()).first()
    claims = get_jwt()
    return jsonify(
        {
            "record": record.to_dict() if record else None,
            "has_clock_in_out": claims.get("role") in ROLES_WITH_CLOCK_IN_OUT,
        }
    )


@bp.get("/history")
@jwt_required()
def history():
    user_id = int(get_jwt_identity())
    month = request.args.get("month", type=int) or date.today().month
    year = request.args.get("year", type=int) or date.today().year

    records = (
        Attendance.query.filter(
            Attendance.user_id == user_id,
            db.extract("month", Attendance.work_date) == month,
            db.extract("year", Attendance.work_date) == year,
        )
        .order_by(Attendance.work_date.desc())
        .all()
    )
    return jsonify([r.to_dict() for r in records])


@bp.get("/team")
@jwt_required()
def team_attendance():
    """Managers see direct reports; HR Operations / Operations see everyone."""
    claims = get_jwt()
    role = claims.get("role")
    user_id = int(get_jwt_identity())
    target_date = request.args.get("date", date.today().isoformat())

    if role in (HR_OPERATIONS, OPERATIONS):
        user_ids = [u.id for u in User.query.filter_by(is_active=True).all()]
    elif role == MANAGER:
        user_ids = [u.id for u in User.query.filter_by(manager_id=user_id).all()]
    else:
        return jsonify({"message": "You do not have permission to view team attendance."}), 403

    records = Attendance.query.filter(
        Attendance.user_id.in_(user_ids), Attendance.work_date == target_date
    ).all()
    return jsonify([r.to_dict() for r in records])


@bp.post("/regularize/<int:record_id>")
@jwt_required()
def regularize(record_id):
    """Manager / HR Operations approves a missed-punch regularization request."""
    claims = get_jwt()
    if claims.get("role") not in (MANAGER, HR_OPERATIONS):
        return jsonify({"message": "You do not have permission to regularize attendance."}), 403

    record = Attendance.query.get_or_404(record_id)
    payload = request.get_json(silent=True) or {}
    record.is_regularized = True
    record.regularization_reason = payload.get("reason", "")
    record.status = "regularized"
    db.session.commit()
    return jsonify(record.to_dict())
