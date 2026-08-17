from datetime import datetime
from app.extensions import db


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (
        db.UniqueConstraint("user_id", "work_date", name="uq_attendance_user_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    work_date = db.Column(db.Date, nullable=False)

    clock_in = db.Column(db.DateTime, nullable=True)
    clock_out = db.Column(db.DateTime, nullable=True)
    clock_in_note = db.Column(db.String(255))
    clock_out_note = db.Column(db.String(255))

    status = db.Column(
        db.String(20), default="present"
    )  # present, half_day, absent, on_leave, regularized
    total_hours = db.Column(db.Float, default=0)

    is_regularized = db.Column(db.Boolean, default=False)
    regularization_reason = db.Column(db.String(255))

    user = db.relationship("User", backref="attendance_records")

    def recompute_hours(self):
        if self.clock_in and self.clock_out:
            delta = self.clock_out - self.clock_in
            self.total_hours = round(delta.total_seconds() / 3600, 2)
            self.status = "present" if self.total_hours >= 4 else "half_day"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "employee_name": self.user.full_name if self.user else None,
            "work_date": self.work_date.isoformat(),
            "clock_in": self.clock_in.isoformat() if self.clock_in else None,
            "clock_out": self.clock_out.isoformat() if self.clock_out else None,
            "status": self.status,
            "total_hours": self.total_hours,
            "is_regularized": self.is_regularized,
        }
