from datetime import datetime
from app.extensions import db


class ScreeningCall(db.Model):
    """An AI voice-bot screening call attempt against a candidate."""
    __tablename__ = "screening_calls"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=False)
    attempt_number = db.Column(db.Integer, default=1)

    scheduled_at = db.Column(db.DateTime, nullable=False)
    called_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="scheduled")
    # scheduled, in_progress, completed, no_answer, rescheduled

    recording_url = db.Column(db.String(255), nullable=True)
    transcript = db.Column(db.Text, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    outcome = db.Column(db.String(20), nullable=True)  # yes, no, neutral

    triggered_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "attempt_number": self.attempt_number,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "called_at": self.called_at.isoformat() if self.called_at else None,
            "status": self.status,
            "recording_url": self.recording_url,
            "transcript": self.transcript,
            "summary": self.summary,
            "outcome": self.outcome,
            "triggered_by": self.triggered_by,
            "created_at": self.created_at.isoformat(),
        }
