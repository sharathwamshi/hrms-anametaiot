from app.extensions import db
from app.models import CandidateAuditLog


def log_action(candidate_id, action, actor_id=None, detail=None):
    """Append one entry to a candidate's audit trail. Call this from every route
    that changes candidate state, so the trail in Section 14/17 of the spec stays
    complete without relying on anyone remembering to log it manually."""
    entry = CandidateAuditLog(
        candidate_id=candidate_id, action=action, actor_id=actor_id, detail=detail
    )
    db.session.add(entry)
    return entry
