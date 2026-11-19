from datetime import date, datetime
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
            used = sum(
                (min(row.end_date, year_end) - max(row.start_date, year_start)).days + 1
                for row in approved_requests
            )
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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id], backref="leave_requests")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])
    leave_type = db.relationship("LeaveType")

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
