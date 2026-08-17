from datetime import datetime
from app.extensions import db


class CandidateAuditLog(db.Model):
    """Full audit trail: who did what to a candidate, and when."""
    __tablename__ = "candidate_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    # created, reassigned, stage_changed, verified, screening_call, mock_test_assigned,
    # mock_test_graded, interview_scheduled, offer_drafted, offer_approved, converted_to_employee...
    detail = db.Column(db.String(500), nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    actor = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "action": self.action,
            "detail": self.detail,
            "actor_id": self.actor_id,
            "actor_name": self.actor.full_name if self.actor else "System",
            "created_at": self.created_at.isoformat(),
        }


class CandidateNote(db.Model):
    """Free-text collaboration thread on a candidate."""
    __tablename__ = "candidate_notes"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "author_id": self.author_id,
            "author_name": self.author.full_name if self.author else None,
            "body": self.body,
            "created_at": self.created_at.isoformat(),
        }
