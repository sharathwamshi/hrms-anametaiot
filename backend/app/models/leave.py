from datetime import date, datetime, timedelta
from app.extensions import db


class LeaveType(db.Model):
    __tablename__ = "leave_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # Casual, Sick, Earned...
    annual_quota = db.Column(db.Float, default=12)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "annual_quota": self.annual_quota}


class LeaveBalance(db.Model):
    __tablename__ = "leave_balances"
    __table_args__ = (
        db.UniqueConstraint("user_id", "leave_type_id", "year", name="uq_balance_user_type_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_types.id"), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    allocated = db.Column(db.Float, default=0)
    used = db.Column(db.Float, default=0)
    exhaustion_acknowledged = db.Column(db.Boolean, nullable=False, default=False)

    leave_type = db.relationship("LeaveType")

    @property
    def balance(self):
        return round(self.allocated - self.used, 2)

    def to_dict(self):
        return {
            "leave_type_id": self.leave_type_id,
            "leave_type": self.leave_type.name,
            "allocated": self.allocated,
            "used": self.used,
            "balance": self.balance,
            "annual_entitlement": self.allocated,
            "approved_leave_taken": self.used,
            "remaining_leave": self.balance,
            "exhaustion_acknowledged": bool(self.exhaustion_acknowledged),
        }


def ensure_leave_balances(user_id, year):
    existing_type_ids = {
        row[0]
        for row in db.session.query(LeaveBalance.leave_type_id)
        .filter_by(user_id=user_id, year=year)
        .all()
    }
    for leave_type in LeaveType.query.all():
        if leave_type.id not in existing_type_ids:
            year_start = date(year, 1, 1)
            year_end = date(year, 12, 31)
            approved_requests = LeaveRequest.query.filter(
                LeaveRequest.user_id == user_id,
                LeaveRequest.leave_type_id == leave_type.id,
                LeaveRequest.status == "approved",
                LeaveRequest.start_date <= year_end,
                LeaveRequest.end_date >= year_start,
            ).all()
            used = 0
            for row in approved_requests:
                day = max(row.start_date, year_start)
                end = min(row.end_date, year_end)
                legacy_inclusive_days = row.days == (row.end_date - row.start_date).days + 1
                while day <= end:
                    if legacy_inclusive_days or day.weekday() != 6:
                        used += 1
                    day += timedelta(days=1)
            db.session.add(
                LeaveBalance(
                    user_id=user_id,
                    leave_type_id=leave_type.id,
                    year=year,
                    allocated=leave_type.annual_quota or 0,
                    used=used,
                )
            )


class LeaveRequest(db.Model):
    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_types.id"), nullable=False)

    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    days = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(500))

    status = db.Column(db.String(20), default="pending")  # pending, approved, rejected, cancelled
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    review_comment = db.Column(db.String(255))
    duration = db.Column(db.String(20), nullable=False, default="full_day")
    final_classification = db.Column(db.String(20), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id], backref="leave_requests")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])
    leave_type = db.relationship("LeaveType")
    review_history = db.relationship(
        "LeaveReviewHistory",
        backref="leave_request",
        order_by="LeaveReviewHistory.created_at",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "employee_id": self.user_id,
            "employee_code": self.user.employee_code if self.user else None,
            "employee_name": self.user.full_name if self.user else None,
            "leave_type_id": self.leave_type_id,
            "leave_type": self.leave_type.name if self.leave_type else None,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "days": self.days,
            "reason": self.reason,
            "status": self.status,
            "reviewer_name": self.reviewer.full_name if self.reviewer else None,
            "review_comment": self.review_comment,
            "created_at": self.created_at.isoformat(),
            "review_history": [entry.to_dict() for entry in self.review_history],
            "duration": self.duration,
            "final_classification": self.final_classification,
        }


class LeaveReviewHistory(db.Model):
    __tablename__ = "leave_review_history"

    id = db.Column(db.Integer, primary_key=True)
    leave_request_id = db.Column(db.Integer, db.ForeignKey("leave_requests.id"), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(20), nullable=False)
    comment = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    reviewer = db.relationship("User")

    def to_dict(self):
        return {
            "action": self.action,
            "comment": self.comment,
            "reviewer_id": self.reviewer_id,
            "reviewer_name": self.reviewer.full_name if self.reviewer else None,
            "created_at": self.created_at.isoformat(),
        }


class LeaveEntitlementAudit(db.Model):
    __tablename__ = "leave_entitlement_audit"

    id = db.Column(db.Integer, primary_key=True)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_types.id"), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    scope = db.Column(db.String(30), nullable=False)
    year = db.Column(db.Integer, nullable=True)
    old_entitlement = db.Column(db.Float, nullable=False)
    new_entitlement = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    leave_type = db.relationship("LeaveType")
    employee = db.relationship("User", foreign_keys=[employee_id])
    actor = db.relationship("User", foreign_keys=[actor_id])
