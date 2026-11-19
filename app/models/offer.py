from datetime import datetime
from app.extensions import db


class Offer(db.Model):
    __tablename__ = "offers"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=False)

    designation = db.Column(db.String(120), nullable=False)
    salary = db.Column(db.Float, nullable=False)
    joining_date = db.Column(db.Date, nullable=False)

    status = db.Column(db.String(20), default="drafted")
    # drafted, pending_approval, approved, rejected, sent, accepted, declined
    counter_notes = db.Column(db.Text, nullable=True)

    drafted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approval_comment = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "designation": self.designation,
            "salary": self.salary,
            "joining_date": self.joining_date.isoformat() if self.joining_date else None,
            "status": self.status,
            "counter_notes": self.counter_notes,
            "drafted_by": self.drafted_by,
            "approver_id": self.approver_id,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approval_comment": self.approval_comment,
            "created_at": self.created_at.isoformat(),
        }
