from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models import Offer, Candidate
from app.utils.security import roles_required
from app.utils.audit import log_action
from app.utils.permissions import role_or_permission_required
from app.roles import RECRUITMENT_ROLES, MANAGER, HR_OPERATIONS

bp = Blueprint("offers", __name__, url_prefix="/api/offers")

APPROVER_ROLES = (MANAGER, HR_OPERATIONS)


@bp.get("")
@jwt_required()
def list_offers():
    candidate_id = request.args.get("candidate_id", type=int)
    status = request.args.get("status")
    query = Offer.query
    if candidate_id:
        query = query.filter_by(candidate_id=candidate_id)
    if status:
        query = query.filter_by(status=status)
    rows = query.order_by(Offer.created_at.desc()).all()
    return jsonify([o.to_dict() for o in rows])


@bp.post("")
@roles_required(*RECRUITMENT_ROLES)
def draft_offer():
    payload = request.get_json(silent=True) or {}
    required = ["candidate_id", "designation", "salary", "joining_date"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return jsonify({"message": f"Missing fields: {', '.join(missing)}"}), 400

    candidate = Candidate.query.get_or_404(payload["candidate_id"])
    offer = Offer(
        candidate_id=candidate.id,
        designation=payload["designation"],
        salary=float(payload["salary"]),
        joining_date=datetime.strptime(payload["joining_date"], "%Y-%m-%d").date(),
        status="drafted",
        drafted_by=int(get_jwt_identity()),
    )
    db.session.add(offer)
    candidate.stage = "offer"
    db.session.flush()
    log_action(candidate.id, "offer_drafted", actor_id=int(get_jwt_identity()),
               detail=f"{offer.designation} @ {offer.salary}")
    db.session.commit()
    return jsonify(offer.to_dict()), 201


@bp.post("/<int:offer_id>/submit-for-approval")
@roles_required(*RECRUITMENT_ROLES)
def submit_for_approval(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    offer.status = "pending_approval"
    db.session.commit()
    return jsonify(offer.to_dict())


@bp.post("/<int:offer_id>/approve")
@role_or_permission_required(*APPROVER_ROLES, permission_key="approve_offers")
def approve_offer(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    payload = request.get_json(silent=True) or {}
    offer.status = "approved"
    offer.approver_id = int(get_jwt_identity())
    offer.approved_at = datetime.utcnow()
    offer.approval_comment = payload.get("comment", "")
    log_action(offer.candidate_id, "offer_approved", actor_id=int(get_jwt_identity()))
    db.session.commit()
    return jsonify(offer.to_dict())


@bp.post("/<int:offer_id>/reject")
@role_or_permission_required(*APPROVER_ROLES, permission_key="approve_offers")
def reject_offer(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    payload = request.get_json(silent=True) or {}
    offer.status = "rejected"
    offer.approver_id = int(get_jwt_identity())
    offer.approved_at = datetime.utcnow()
    offer.approval_comment = payload.get("comment", "")
    log_action(offer.candidate_id, "offer_rejected", actor_id=int(get_jwt_identity()),
               detail=payload.get("comment", ""))
    db.session.commit()
    return jsonify(offer.to_dict())


@bp.post("/<int:offer_id>/send")
@roles_required(*RECRUITMENT_ROLES)
def send_offer(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    if offer.status != "approved":
        return jsonify({"message": "Only an approved offer can be sent."}), 400
    offer.status = "sent"
    db.session.commit()
    return jsonify(offer.to_dict())


@bp.post("/<int:offer_id>/respond")
@roles_required(*RECRUITMENT_ROLES)
def respond_offer(offer_id):
    """Records the candidate's response — accepted or declined — along with any
    counter-offer notes."""
    offer = Offer.query.get_or_404(offer_id)
    payload = request.get_json(silent=True) or {}
    response = payload.get("response")
    if response not in ("accepted", "declined"):
        return jsonify({"message": "response must be 'accepted' or 'declined'."}), 400

    offer.status = response
    if payload.get("counter_notes"):
        offer.counter_notes = payload["counter_notes"]

    candidate = Candidate.query.get(offer.candidate_id)
    if response == "accepted" and candidate:
        candidate.stage = "hired"

    log_action(offer.candidate_id, f"offer_{response}", actor_id=int(get_jwt_identity()))
    db.session.commit()
    return jsonify(offer.to_dict())
