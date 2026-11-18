import os
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models import Candidate, ScreeningCall
from app.utils.security import roles_required
from app.utils.audit import log_action
from app.utils.ai_grading import classify_call_outcome, summarize_call
from app.roles import RECRUITMENT_ROLES

bp = Blueprint("screening", __name__, url_prefix="/api/screening")

DEFAULT_QUESTIONS = (
    "Are you currently available to join, and what is your notice period? "
    "What are your salary expectations? Are you still interested in this role?"
)


def _place_call(candidate, call):
    """Places the AI voice-bot call. Uses Twilio when TWILIO_ACCOUNT_SID /
    TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER are configured; otherwise runs a
    clearly-labeled simulation so the rest of the screening flow (recording
    storage, summary, Yes/No/Neutral branching, reschedule loop) can be built,
    tested, and used end to end before real telephony credentials exist."""
    twilio_configured = all(
        os.environ.get(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER")
    )

    if not twilio_configured:
        call.status = "completed"
        call.called_at = datetime.utcnow()
        call.transcript = (
            f"[SIMULATED — no Twilio credentials configured] Call to {candidate.full_name} "
            f"({candidate.phone}) covering: {DEFAULT_QUESTIONS}"
        )
        call.summary = summarize_call(call.transcript)
        call.outcome = classify_call_outcome(call.transcript)
        return call

    # Real Twilio call would be placed here once credentials are configured —
    # left as a clear integration point rather than a fake implementation.
    call.status = "scheduled"
    return call


@bp.get("/candidates/<int:candidate_id>/calls")
@jwt_required()
def call_history(candidate_id):
    Candidate.query.get_or_404(candidate_id)
    rows = ScreeningCall.query.filter_by(candidate_id=candidate_id).order_by(ScreeningCall.attempt_number).all()
    return jsonify([c.to_dict() for c in rows])


@bp.post("/candidates/<int:candidate_id>/trigger-call")
@roles_required(*RECRUITMENT_ROLES)
def trigger_call(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    if candidate.verification_status != "verified":
        return jsonify({"message": "Candidate must be Verified before a screening call can be triggered."}), 400

    attempt_number = ScreeningCall.query.filter_by(candidate_id=candidate_id).count() + 1
    call = ScreeningCall(
        candidate_id=candidate_id,
        attempt_number=attempt_number,
        scheduled_at=datetime.utcnow(),
        triggered_by=int(get_jwt_identity()),
    )
    _place_call(candidate, call)
    db.session.add(call)
    db.session.flush()

    if call.outcome == "yes":
        candidate.stage = "mock_test"
    elif call.outcome == "no":
        candidate.stage = "rejected"
    # neutral: stage unchanged, stays pending review

    log_action(candidate_id, "screening_call", actor_id=int(get_jwt_identity()),
               detail=f"Attempt #{attempt_number} — outcome: {call.outcome or 'pending'}")
    db.session.commit()
    return jsonify(call.to_dict()), 201


@bp.post("/calls/<int:call_id>/reschedule")
@roles_required(*RECRUITMENT_ROLES)
def reschedule_call(call_id):
    """Used for a Neutral outcome (auto-eligible for another attempt) or a
    manual reschedule the recruiter triggers themselves."""
    old_call = ScreeningCall.query.get_or_404(call_id)
    candidate = Candidate.query.get_or_404(old_call.candidate_id)

    attempt_number = ScreeningCall.query.filter_by(candidate_id=candidate.id).count() + 1
    new_call = ScreeningCall(
        candidate_id=candidate.id,
        attempt_number=attempt_number,
        scheduled_at=datetime.utcnow(),
        triggered_by=int(get_jwt_identity()),
    )
    _place_call(candidate, new_call)
    db.session.add(new_call)
    db.session.flush()

    if new_call.outcome == "yes":
        candidate.stage = "mock_test"
    elif new_call.outcome == "no":
        candidate.stage = "rejected"

    log_action(candidate.id, "screening_call_rescheduled", actor_id=int(get_jwt_identity()),
               detail=f"Attempt #{attempt_number} — outcome: {new_call.outcome or 'pending'}")
    db.session.commit()
    return jsonify(new_call.to_dict()), 201
