from datetime import datetime, time

from app.extensions import db


class AttendanceNotificationSettings(db.Model):
    __tablename__ = "attendance_notification_settings"

    id = db.Column(db.Integer, primary_key=True)
    regularization_enabled = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    leave_enabled = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    attendance_updates_enabled = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    business_alerts_enabled = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    clock_in_reminder_enabled = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    manager_missing_alert_enabled = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    clock_out_reminder_enabled = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    clock_in_reminder_time = db.Column(db.Time, nullable=False, default=time(9, 30))
    manager_missing_alert_time = db.Column(db.Time, nullable=False, default=time(10, 0))
    clock_out_reminder_time = db.Column(db.Time, nullable=False, default=time(18, 30))
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        boolean_fields = (
            "regularization_enabled",
            "leave_enabled",
            "attendance_updates_enabled",
            "business_alerts_enabled",
            "clock_in_reminder_enabled",
            "manager_missing_alert_enabled",
            "clock_out_reminder_enabled",
        )
        time_fields = (
            "clock_in_reminder_time",
            "manager_missing_alert_time",
            "clock_out_reminder_time",
        )
        return {
            **{field: bool(getattr(self, field)) for field in boolean_fields},
            **{field: getattr(self, field).strftime("%H:%M") for field in time_fields},
        }


class AttendanceReminderRun(db.Model):
    __tablename__ = "attendance_reminder_runs"
    __table_args__ = (
        db.UniqueConstraint("reminder_kind", "reminder_date", name="uq_attendance_reminder_run_day"),
    )

    id = db.Column(db.Integer, primary_key=True)
    reminder_kind = db.Column(db.String(40), nullable=False)
    reminder_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
