from datetime import date, datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import LeaveRequest, LeaveType, LeaveBalance, User
from app.roles import MANAGER, HR_OPERATIONS, APPROVER_ROLES, CONTRACT_EMPLOYEE

bp = Blueprint("leave", __name__, url_prefix="/api/leave")


@bp.get("/types")
@jwt_required()
def leave_types():
    return jsonify([lt.to_dict() for lt in LeaveType.query.all()])


@bp.get("/balances")
@jwt_required()
def balances():
    user_id = int(get_jwt_identity())
    year = request.args.get("year", type=int) or date.today().year
    rows = LeaveBalance.query.filter_by(user_id=user_id, year=year).all()
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

    balance = LeaveBalance.query.filter_by(
        user_id=user_id, leave_type_id=leave_type_id, year=start.year
    ).first()
    if balance and balance.balance < days:
        return jsonify({"message": f"Insufficient balance. Available: {balance.balance} day(s)."}), 400

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
        report_ids = [u.id for u in User.query.filter_by(manager_id=user_id).all()]
        query = query.filter(LeaveRequest.user_id.in_(report_ids))

    rows = query.order_by(LeaveRequest.created_at.asc()).all()
    return jsonify([r.to_dict() for r in rows])


@bp.post("/<int:request_id>/decision")
@jwt_required()
def decide(request_id):
    claims = get_jwt()
    role = claims.get("role")
    reviewer_id = int(get_jwt_identity())

    if role not in APPROVER_ROLES:
        return jsonify({"message": "You do not have permission to approve or reject leave."}), 403

    leave_request = LeaveRequest.query.get_or_404(request_id)
    if role == MANAGER and leave_request.user.manager_id != reviewer_id:
        return jsonify({"message": "You can only review leave requests from your direct reports."}), 403
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"message": "A valid decision is required."}), 400
    decision = payload.get("decision")  # "approved" | "rejected"

    if decision not in ("approved", "rejected"):
        return jsonify({"message": "decision must be 'approved' or 'rejected'."}), 400
    if leave_request.status != "pending":
        return jsonify({"message": "This leave request has already been reviewed."}), 409

    leave_request.status = decision
    leave_request.reviewed_by = reviewer_id
    leave_request.review_comment = payload.get("comment", "")

    if decision == "approved":
        balance = LeaveBalance.query.filter_by(
            user_id=leave_request.user_id,
            leave_type_id=leave_request.leave_type_id,
            year=leave_request.start_date.year,
        ).first()
        if balance:
            balance.used += leave_request.days

    db.session.commit()
    return jsonify(leave_request.to_dict())
