from datetime import datetime
import json
from app.extensions import db
from app.models.vendor import CompanySettings
from app.utils.company_time import to_company_local, utc_now_naive


AUTO_CLOCK_OUT_NOTE = "[SYSTEM:AUTO_MIDNIGHT_CLOCK_OUT]"


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (
        db.UniqueConstraint("user_id", "work_date", name="uq_attendance_user_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    work_date = db.Column(db.Date, nullable=False)

    # MySQL DATETIME stores naive UTC; convert only at company-local display/rule boundaries.
    clock_in = db.Column(db.DateTime, nullable=True)
    clock_out = db.Column(db.DateTime, nullable=True)
    clock_in_note = db.Column(db.String(255))
    clock_out_note = db.Column(db.String(255))

    status = db.Column(
        db.String(20), default="present"
    )  # present, half_day, absent, on_leave, regularized
    total_hours = db.Column(db.Float, default=0)

    is_regularized = db.Column(db.Boolean, default=False)
    regularization_reason = db.Column(db.String(255))  # legacy: set when a manager regularizes directly

    # Self-service regularization: the employee requests it with a reason (chosen
    # from the manager-defined list) and a note; a manager or HR Ops then reviews it.
    regularization_status = db.Column(db.String(20), nullable=True)  # pending, approved, rejected
    regularization_reason_id = db.Column(db.Integer, db.ForeignKey("attendance_regularization_reasons.id"), nullable=True)
    regularization_note = db.Column(db.String(255), nullable=True)
    regularization_requested_at = db.Column(db.DateTime, nullable=True)
    regularization_reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    regularization_reviewed_at = db.Column(db.DateTime, nullable=True)
    regularization_review_comment = db.Column(db.String(255), nullable=True)

    # Geofencing is advisory ("soft") by design: the punch is always accepted,
    # but if it's outside every active office's radius we record that and flag
    # it for the manager — never block someone from clocking in or out.
    clock_in_lat = db.Column(db.Float, nullable=True)
    clock_in_lng = db.Column(db.Float, nullable=True)
    clock_in_within_geofence = db.Column(db.Boolean, nullable=True)  # NULL = no location sent
    clock_out_lat = db.Column(db.Float, nullable=True)
    clock_out_lng = db.Column(db.Float, nullable=True)
    clock_out_within_geofence = db.Column(db.Boolean, nullable=True)

    # Selfie proof (only captured when the company policy requires it). The value
    # is a filename inside the PRIVATE selfie folder — never served publicly; the
    # image is only reachable through an authenticated, access-checked endpoint.
    clock_in_selfie = db.Column(db.String(255), nullable=True)
    clock_out_selfie = db.Column(db.String(255), nullable=True)

    # Direct manager/HR Ops correction (no employee request needed): who, when, and why.
    edited_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    edited_at = db.Column(db.DateTime, nullable=True)
    edit_note = db.Column(db.String(255), nullable=True)
    edit_details = db.Column(db.Text, nullable=True)

    user = db.relationship("User", backref="attendance_records", foreign_keys=[user_id])
    reason = db.relationship("AttendanceRegularizationReason")
    reviewed_by_user = db.relationship("User", foreign_keys=[regularization_reviewed_by])
    edited_by_user = db.relationship("User", foreign_keys=[edited_by])

    # A day can have several check-in/check-out sessions (e.g. someone clocks out by
    # mistake and checks in again). This row stays the DAY'S SUMMARY — clock_in is the
    # first check-in, clock_out is the last check-out (None while currently clocked in),
    # total_hours is the sum of all closed sessions — so payroll, the dashboard and every
    # existing screen keep working unchanged. The sessions hold the detail.
    sessions = db.relationship(
        "AttendanceSession", backref="attendance", order_by="AttendanceSession.session_no",
        cascade="all, delete-orphan", lazy="select",
    )

    def recompute_hours(self):
        """Legacy single-session helper, kept for older callers."""
        if self.clock_in and self.clock_out:
            delta = self.clock_out - self.clock_in
            self.total_hours = round(delta.total_seconds() / 3600, 2)
            self.status = "present" if self.total_hours >= 4 else "half_day"

    def _check_in_status(self, buffer_minutes=None):
        sessions = self.effective_sessions()
        if not sessions:
            return None
        first_check_in = min(sessions, key=lambda session: session.clock_in).clock_in
        local_check_in = to_company_local(first_check_in)
        check_in_seconds = (
            local_check_in.hour * 3600 + local_check_in.minute * 60
            + local_check_in.second + local_check_in.microsecond / 1_000_000
        )
        official_check_in_seconds = (9 * 60 + 30) * 60
        if check_in_seconds <= official_check_in_seconds:
            return "in_time"
        if buffer_minutes is None:
            settings = CompanySettings.query.order_by(CompanySettings.id.asc()).first()
            buffer_minutes = settings.attendance_buffer_minutes if settings else 10
        buffer_boundary_seconds = (9 * 60 + 30 + buffer_minutes) * 60
        return "in_time" if check_in_seconds <= buffer_boundary_seconds else "late"

    def effective_sessions(self):
        """The sessions to show. A day that predates multi-session support (and hasn't
        been migrated) is presented as one session built from its own fields — read-only,
        never added to the database session."""
        if self.sessions:
            return list(self.sessions)
        if not self.clock_in:
            return []
        return [AttendanceSession(
            id=None, attendance_id=self.id, session_no=1, clock_in=self.clock_in, clock_out=self.clock_out,
            clock_in_note=self.clock_in_note, clock_out_note=self.clock_out_note,
            clock_in_lat=self.clock_in_lat, clock_in_lng=self.clock_in_lng, clock_in_within_geofence=self.clock_in_within_geofence,
            clock_out_lat=self.clock_out_lat, clock_out_lng=self.clock_out_lng, clock_out_within_geofence=self.clock_out_within_geofence,
            clock_in_selfie=self.clock_in_selfie, clock_out_selfie=self.clock_out_selfie,
        )]

    def open_session(self):
        for s in self.sessions:
            if s.clock_out is None:
                return s
        return None

    def recompute_from_sessions(self):
        """Rebuild the day's summary from its sessions."""
        sessions = list(self.sessions)
        if not sessions:
            return
        first, last = sessions[0], sessions[-1]
        self.clock_in = first.clock_in
        self.clock_in_note = first.clock_in_note
        self.clock_in_lat, self.clock_in_lng = first.clock_in_lat, first.clock_in_lng
        self.clock_in_within_geofence = first.clock_in_within_geofence
        self.clock_in_selfie = first.clock_in_selfie

        if last.clock_out is None:  # currently clocked in
            self.clock_out = None
            self.clock_out_note = self.clock_out_selfie = None
            self.clock_out_lat = self.clock_out_lng = self.clock_out_within_geofence = None
        else:
            self.clock_out = last.clock_out
            self.clock_out_note = last.clock_out_note
            self.clock_out_lat, self.clock_out_lng = last.clock_out_lat, last.clock_out_lng
            self.clock_out_within_geofence = last.clock_out_within_geofence
            self.clock_out_selfie = last.clock_out_selfie

        worked = sum((s.clock_out - s.clock_in).total_seconds() for s in sessions if s.clock_out)
        self.total_hours = round(worked / 3600, 2)
        # An automatic midnight closure is always a half day, regardless of its duration.
        if any(session.is_automatic_clock_out for session in sessions):
            if not self.is_regularized and self.status != "regularized":
                self.status = "half_day"
        # Only judge the day once nobody is clocked in, and never overwrite a regularization.
        elif last.clock_out is not None and not self.is_regularized and self.status != "regularized":
            self.status = "present" if self.total_hours >= 4 else "half_day"

    def to_dict(self):
        sessions = self.effective_sessions()
        edit_details = json.loads(self.edit_details) if self.edit_details else None
        return {
            "id": self.id,
            "user_id": self.user_id,
            "employee_name": self.user.full_name if self.user else None,
            "employee_code": self.user.employee_code if self.user else None,
            "work_date": self.work_date.isoformat(),
            "clock_in": self.clock_in.isoformat() if self.clock_in else None,
            "clock_out": self.clock_out.isoformat() if self.clock_out else None,
            "status": self.status,
            "total_hours": self.total_hours,
            "check_in_status": self._check_in_status(),
            "is_regularized": self.is_regularized,
            "regularization_status": self.regularization_status,
            "regularization_reason_id": self.regularization_reason_id,
            "regularization_reason_label": self.reason.label if self.reason else None,
            "regularization_note": self.regularization_note,
            "regularization_requested_at": self.regularization_requested_at.isoformat() if self.regularization_requested_at else None,
            "regularization_request_date": (
                to_company_local(self.regularization_requested_at).date().isoformat()
                if self.regularization_requested_at else None
            ),
            "regularization_reviewed_by_name": self.reviewed_by_user.full_name if self.reviewed_by_user else None,
            "regularization_reviewed_at": self.regularization_reviewed_at.isoformat() if self.regularization_reviewed_at else None,
            "regularization_review_comment": self.regularization_review_comment,
            "edited_by_name": self.edited_by_user.full_name if self.edited_by_user else None,
            "edited_at": self.edited_at.isoformat() if self.edited_at else None,
            "edit_note": self.edit_note,
            "edit_details": edit_details,
            "clock_in_within_geofence": self.clock_in_within_geofence,
            "clock_out_within_geofence": self.clock_out_within_geofence,
            "clock_in_note": self.clock_in_note,
            "clock_out_note": self.clock_out_note,
            "clock_in_lat": self.clock_in_lat,
            "clock_in_lng": self.clock_in_lng,
            "clock_out_lat": self.clock_out_lat,
            "clock_out_lng": self.clock_out_lng,
            "has_clock_in_selfie": bool(self.clock_in_selfie),
            "has_clock_out_selfie": bool(self.clock_out_selfie),
            **self._session_summary(),
        }

    def _session_summary(self):
        sessions = self.effective_sessions()
        dicts, away_minutes, prev = [], 0, None
        for s in sessions:
            d = s.to_dict()
            if prev is not None and prev.clock_out:
                gap = max(0, round((s.clock_in - prev.clock_out).total_seconds() / 60))
                d["gap_minutes_before"] = gap
                away_minutes += gap
            else:
                d["gap_minutes_before"] = None
            dicts.append(d)
            prev = s
        punches_outside = any(
            x is False for s in sessions for x in (s.clock_in_within_geofence, s.clock_out_within_geofence)
        )
        return {
            "sessions": dicts,
            "session_count": len(dicts),
            "reentry_count": max(0, len(dicts) - 1),
            "currently_clocked_in": any(s.clock_out is None for s in sessions),
            "away_minutes": away_minutes,
            "outside_office_any": punches_outside,
        }


class AttendanceRegularizationReason(db.Model):
    """A regularization reason type — the manager/HR Ops-defined 'rules' an
    employee must pick from when asking for a missed punch to be excused."""
    __tablename__ = "attendance_regularization_reasons"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive)

    def to_dict(self):
        return {
            "id": self.id, "label": self.label, "description": self.description,
            "is_active": self.is_active,
        }


class AttendanceRegularizationRequest(db.Model):
    __tablename__ = "attendance_regularization_requests"
    __table_args__ = (
        db.Index("ix_regularization_request_user_submitted", "user_id", "submitted_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    attendance_id = db.Column(db.Integer, db.ForeignKey("attendance.id"), nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)


class Holiday(db.Model):
    """The organization's holiday calendar — set by Manager/HR Ops, visible to everyone."""
    __tablename__ = "holidays"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    holiday_date = db.Column(db.Date, nullable=False, unique=True)
    description = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "holiday_date": self.holiday_date.isoformat(),
            "description": self.description,
        }


class OfficeLocation(db.Model):
    """A geofence center — Manager/HR Ops define where "the office" is, and
    clock-in/out is checked against every active one (nearest wins)."""
    __tablename__ = "office_locations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    radius_meters = db.Column(db.Integer, nullable=False, default=200)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "latitude": self.latitude, "longitude": self.longitude,
            "radius_meters": self.radius_meters, "is_active": self.is_active,
        }


class WorkLocation(db.Model):
    """Selectable work-location labels, separate from GPS office geofences."""
    __tablename__ = "attendance_work_locations"
    __table_args__ = (db.UniqueConstraint("name", name="uq_attendance_work_location_name"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "is_active": self.is_active,
            "is_default": self.is_default,
        }


class DeviceToken(db.Model):
    """A phone registered for push notifications (Expo push token)."""
    __tablename__ = "device_tokens"
    __table_args__ = (db.UniqueConstraint("token", name="uq_device_token"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String(255), nullable=False)
    platform = db.Column(db.String(20), nullable=True)  # ios, android
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="device_tokens")

    def to_dict(self):
        return {"id": self.id, "token": self.token, "platform": self.platform, "last_seen_at": self.last_seen_at.isoformat()}


class AttendanceSession(db.Model):
    """One check-in -> check-out stretch within a day. The first session of a day needs
    no explanation; every later one is a "re-entry" and must carry the reason the person
    gave for checking in again, which managers can see."""
    __tablename__ = "attendance_sessions"
    __table_args__ = (db.UniqueConstraint("attendance_id", "session_no", name="uq_attendance_session_no"),)

    id = db.Column(db.Integer, primary_key=True)
    attendance_id = db.Column(db.Integer, db.ForeignKey("attendance.id", ondelete="CASCADE"), nullable=False)
    session_no = db.Column(db.Integer, nullable=False)  # 1 = first of the day

    clock_in = db.Column(db.DateTime, nullable=False)
    clock_out = db.Column(db.DateTime, nullable=True)  # None = still clocked in
    clock_in_note = db.Column(db.String(255))
    clock_out_note = db.Column(db.String(255))

    clock_in_lat = db.Column(db.Float, nullable=True)
    clock_in_lng = db.Column(db.Float, nullable=True)
    clock_in_within_geofence = db.Column(db.Boolean, nullable=True)
    work_location_id = db.Column(db.Integer, db.ForeignKey("attendance_work_locations.id"), nullable=True)
    work_location_name = db.Column(db.String(100), nullable=True)
    clock_out_lat = db.Column(db.Float, nullable=True)
    clock_out_lng = db.Column(db.Float, nullable=True)
    clock_out_within_geofence = db.Column(db.Boolean, nullable=True)
    clock_in_selfie = db.Column(db.String(255), nullable=True)
    clock_out_selfie = db.Column(db.String(255), nullable=True)

    # Why they checked in AGAIN. NULL for the first session of the day.
    reentry_reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive)

    def duration_hours(self):
        if self.clock_in and self.clock_out:
            return round((self.clock_out - self.clock_in).total_seconds() / 3600, 2)
        return None

    @property
    def is_automatic_clock_out(self):
        return self.clock_out is not None and self.clock_out_note == AUTO_CLOCK_OUT_NOTE

    def to_dict(self):
        return {
            "id": self.id, "session_no": self.session_no,
            "clock_in": self.clock_in.isoformat() if self.clock_in else None,
            "clock_out": self.clock_out.isoformat() if self.clock_out else None,
            "clock_in_note": self.clock_in_note, "clock_out_note": self.clock_out_note,
            "clock_in_lat": self.clock_in_lat, "clock_in_lng": self.clock_in_lng,
            "clock_in_within_geofence": self.clock_in_within_geofence,
            "work_location_id": self.work_location_id,
            "work_location_name": self.work_location_name,
            "clock_out_lat": self.clock_out_lat, "clock_out_lng": self.clock_out_lng,
            "clock_out_within_geofence": self.clock_out_within_geofence,
            "has_clock_in_selfie": bool(self.clock_in_selfie),
            "has_clock_out_selfie": bool(self.clock_out_selfie),
            "reentry_reason": self.reentry_reason,
            "is_reentry": (self.session_no or 1) > 1,
            "duration_hours": self.duration_hours(),
            "automatic_clock_out": self.is_automatic_clock_out,
        }
