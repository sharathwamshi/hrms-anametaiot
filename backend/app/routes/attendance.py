from datetime import datetime, date, time, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import (Attendance, AttendanceSession, AttendanceRegularizationReason,
                        AttendanceRegularizationRequest, User, Holiday, OfficeLocation,
                        CompanySettings, LeaveRequest, WorkLocation)
from app.models.attendance import AUTO_CLOCK_OUT_NOTE
from app.utils.push import send_push
from app.utils.company_time import company_today, company_timezone, utc_now_naive, to_company_local
from math import radians, sin, cos, asin, sqrt, isfinite
from flask import current_app, send_from_directory
import os
import uuid
from datetime import timedelta
import json
from app.roles import ROLES_WITH_CLOCK_IN_OUT, MANAGER, HR_OPERATIONS, OPERATIONS, SUPER_ADMIN

FULL_ACCESS = (HR_OPERATIONS, SUPER_ADMIN)          # every active person, incl. locations + selfies
APPROVER_ROLES = (MANAGER, HR_OPERATIONS, SUPER_ADMIN)
CALENDAR_MANAGER_ROLES = (MANAGER, HR_OPERATIONS, SUPER_ADMIN)
OFFICE_ADMIN_ROLES = (SUPER_ADMIN,)
WORK_LOCATION_ADMIN_ROLES = (MANAGER, HR_OPERATIONS, SUPER_ADMIN)
VIEWER_ROLES = (MANAGER, HR_OPERATIONS, OPERATIONS, SUPER_ADMIN)

bp = Blueprint("attendance", __name__, url_prefix="/api/attendance")


def _guard_clock_eligibility(role):
    if role not in ROLES_WITH_CLOCK_IN_OUT:
        return jsonify(
            {"message": "Contract employees log hours via timesheets, not clock in/out."}
        ), 403
    return None


def _haversine_meters(lat1, lng1, lat2, lng2):
    r = 6371000  # Earth radius in meters
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _check_geofence(lat, lng):
    """Returns True/False against the nearest active office, or None if no
    location was sent or no office is configured. This is advisory only —
    callers never reject a punch because of it, only flag it."""
    if lat is None or lng is None:
        return None
    offices = OfficeLocation.query.filter_by(is_active=True).all()
    if not offices:
        return None
    return any(_haversine_meters(lat, lng, o.latitude, o.longitude) <= o.radius_meters for o in offices)


@bp.post("/location-check")
@jwt_required()
def check_location():
    eligibility_error = _guard_clock_eligibility(get_jwt().get("role"))
    if eligibility_error:
        return eligibility_error
    payload = request.get_json(silent=True) or {}
    try:
        lat, lng = float(payload["latitude"]), float(payload["longitude"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"message": "Valid latitude and longitude are required."}), 400
    if not isfinite(lat) or not isfinite(lng) or not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return jsonify({"message": "Latitude and longitude are out of range."}), 400

    within_office = _check_geofence(lat, lng)
    return jsonify({
        "within_office": within_office,
        "office_configured": within_office is not None,
    })


def _ensure_default_work_locations():
    locations = WorkLocation.query.order_by(WorkLocation.id.asc()).all()
    all_names = {location.name.casefold() for location in locations}
    if not locations:
        office = OfficeLocation.query.filter_by(is_active=True).order_by(OfficeLocation.id.asc()).first()
        main_office_name = office.name.strip() if office and office.name.strip() else "Main Office"
        main_office = WorkLocation(name=main_office_name, is_active=True, is_default=True)
        db.session.add(main_office)
        locations.append(main_office)
    if "work from home" not in all_names:
        home = WorkLocation(name="Work From Home", is_active=True, is_default=False)
        db.session.add(home)
        locations.append(home)
    active = [location for location in locations if location.is_active]
    defaults = [location for location in active if location.is_default]
    if not defaults and active:
        active[0].is_default = True
        defaults = [active[0]]
    for location in defaults[1:]:
        location.is_default = False
    db.session.flush()
    return locations


def _office_restriction_block(user_id, lat, lng, kind_label):
    """If this person is restricted to punching from the office, returns a 403 response unless
    the position sent is inside an active office. Unrestricted people (the default) and the
    case where no office has been configured yet are never blocked."""
    user = db.session.get(User, user_id)
    if not user or not user.restrict_to_office:
        return None
    if not OfficeLocation.query.filter_by(is_active=True).first():
        return None  # nothing to compare against — don't lock people out over a missing setup
    if lat is None or lng is None:
        return jsonify({"message": f"Your manager requires you to {kind_label} from the office. Turn on location (use the mobile app) and try again.",
                        "office_restricted": True, "reason": "no_location"}), 403
    if _check_geofence(lat, lng) is not True:
        return jsonify({"message": f"You are not at the office. Your manager requires you to {kind_label} from an office location.",
                        "office_restricted": True, "reason": "outside_office"}), 403
    return None


def _work_location_admin_required():
    if get_jwt().get("role") not in WORK_LOCATION_ADMIN_ROLES:
        return jsonify({"message": "Only Managers, HR Operations, and Super Admins can manage work locations."}), 403
    return None


# ============================================================================
# Office locations — the geofence centers the Super Admin defines
# ============================================================================

@bp.get("/office-locations")
@jwt_required()
def list_office_locations():
    only_active = request.args.get("active_only", "true") != "false"
    query = OfficeLocation.query
    if only_active:
        query = query.filter_by(is_active=True)
    return jsonify([o.to_dict() for o in query.order_by(OfficeLocation.name.asc()).all()])


@bp.post("/office-locations")
@jwt_required()
def create_office_location():
    claims = get_jwt()
    if claims.get("role") not in OFFICE_ADMIN_ROLES:
        return jsonify({"message": "Only a Super Admin can add an office location."}), 403
    payload = request.get_json(silent=True) or {}
    try:
        lat, lng = float(payload["latitude"]), float(payload["longitude"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"message": "Valid latitude and longitude are required."}), 400
    if not (payload.get("name") or "").strip():
        return jsonify({"message": "A name is required."}), 400
    loc = OfficeLocation(
        name=payload["name"].strip(), latitude=lat, longitude=lng,
        radius_meters=int(payload.get("radius_meters") or 200), created_by=int(get_jwt_identity()),
    )
    db.session.add(loc)
    db.session.commit()
    return jsonify(loc.to_dict()), 201


@bp.put("/office-locations/<int:location_id>")
@jwt_required()
def update_office_location(location_id):
    claims = get_jwt()
    if claims.get("role") not in OFFICE_ADMIN_ROLES:
        return jsonify({"message": "Only a Super Admin can edit an office location."}), 403
    loc = OfficeLocation.query.get_or_404(location_id)
    payload = request.get_json(silent=True) or {}
    if payload.get("name", "").strip():
        loc.name = payload["name"].strip()
    for field in ("latitude", "longitude"):
        if field in payload:
            try:
                setattr(loc, field, float(payload[field]))
            except (TypeError, ValueError):
                return jsonify({"message": f"{field} must be a number."}), 400
    if "radius_meters" in payload:
        loc.radius_meters = int(payload["radius_meters"])
    if "is_active" in payload:
        loc.is_active = bool(payload["is_active"])
    db.session.commit()
    return jsonify(loc.to_dict())


@bp.delete("/office-locations/<int:location_id>")
@jwt_required()
def delete_office_location(location_id):
    claims = get_jwt()
    if claims.get("role") not in OFFICE_ADMIN_ROLES:
        return jsonify({"message": "Only a Super Admin can remove an office location."}), 403
    loc = OfficeLocation.query.get_or_404(location_id)
    db.session.delete(loc)
    db.session.commit()
    return jsonify({"message": "Office location removed."})


# ============================================================================
# Work location choices — labels saved on each attendance session
# ============================================================================

@bp.get("/work-locations")
@jwt_required()
def list_work_locations():
    locations = _ensure_default_work_locations()
    db.session.commit()
    active_only = request.args.get("active_only", "true").lower() != "false"
    if active_only or get_jwt().get("role") not in WORK_LOCATION_ADMIN_ROLES:
        locations = [location for location in locations if location.is_active]
    return jsonify([location.to_dict() for location in locations])


@bp.post("/work-locations")
@jwt_required()
def create_work_location():
    blocked = _work_location_admin_required()
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"message": "Work location details must be provided as an object."}), 400
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        return jsonify({"message": "A work location name of 1 to 100 characters is required."}), 400
    if "is_default" in payload and not isinstance(payload["is_default"], bool):
        return jsonify({"message": "is_default must be a boolean."}), 400
    locations = _ensure_default_work_locations()
    clean_name = name.strip()
    if WorkLocation.query.filter(db.func.lower(WorkLocation.name) == clean_name.lower()).first():
        return jsonify({"message": "A work location with that name already exists."}), 409
    is_default = payload.get("is_default") is True or not any(
        location.is_default for location in locations if location.is_active
    )
    if is_default:
        WorkLocation.query.update({WorkLocation.is_default: False}, synchronize_session=False)
    location = WorkLocation(
        name=clean_name,
        is_active=True,
        is_default=is_default,
        created_by=int(get_jwt_identity()),
    )
    db.session.add(location)
    db.session.commit()
    return jsonify(location.to_dict()), 201


@bp.put("/work-locations/<int:location_id>")
@jwt_required()
def update_work_location(location_id):
    blocked = _work_location_admin_required()
    if blocked:
        return blocked
    location = WorkLocation.query.get_or_404(location_id)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"message": "Work location updates must be provided as an object."}), 400
    if "name" in payload:
        name = payload["name"]
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            return jsonify({"message": "A work location name of 1 to 100 characters is required."}), 400
        clean_name = name.strip()
        duplicate = WorkLocation.query.filter(
            db.func.lower(WorkLocation.name) == clean_name.lower(),
            WorkLocation.id != location.id,
        ).first()
        if duplicate:
            return jsonify({"message": "A work location with that name already exists."}), 409
        location.name = clean_name
    if "is_active" in payload:
        if not isinstance(payload["is_active"], bool):
            return jsonify({"message": "is_active must be a boolean."}), 400
        if location.is_default and not payload["is_active"]:
            return jsonify({"message": "Choose another default location before deactivating this one."}), 400
        location.is_active = payload["is_active"]
    if "is_default" in payload:
        if not isinstance(payload["is_default"], bool):
            return jsonify({"message": "is_default must be a boolean."}), 400
        if payload["is_default"]:
            if not location.is_active:
                return jsonify({"message": "An inactive location cannot be the default."}), 400
            WorkLocation.query.filter(WorkLocation.id != location.id).update(
                {WorkLocation.is_default: False}, synchronize_session=False
            )
            location.is_default = True
        elif location.is_default:
            return jsonify({"message": "Set another default location before removing the current default."}), 400
    db.session.commit()
    return jsonify(location.to_dict())



# ============================================================================
# Attendance policy (selfie) + punch helpers
# ============================================================================

MAX_SELFIE_BYTES = 5 * 1024 * 1024


def _get_settings():
    settings = CompanySettings.query.first()
    if not settings:
        settings = CompanySettings()
        db.session.add(settings)
        db.session.commit()
    return settings


def _to_coord(value, limit):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if -limit <= f <= limit else None


def _read_punch():
    """A punch arrives either as JSON (no selfie) or as multipart form data (with a
    selfie). Returns (note, lat, lng, selfie_file, reason, work_location_id).
    Coordinates are only kept if both are valid, so a half-sent location can never be stored."""
    data = (request.get_json(silent=True) or {}) if request.is_json else request.form
    lat = _to_coord(data.get("latitude"), 90)
    lng = _to_coord(data.get("longitude"), 180)
    if lat is None or lng is None:
        lat = lng = None
    return (
        data.get("note"), lat, lng, request.files.get("selfie"),
        (data.get("reason") or "").strip(), data.get("work_location_id"),
    )


def _save_selfie(file, user_id, work_date, kind):
    """Validates by file CONTENT (not the client's claimed name/type) and stores in
    the private folder. Returns (filename, None) or (None, error_message)."""
    content = file.read(MAX_SELFIE_BYTES + 1)
    if not content:
        return None, "The selfie file was empty."
    if len(content) > MAX_SELFIE_BYTES:
        return None, "The selfie is too large (5 MB max)."
    if content[:3] == b"\xff\xd8\xff":
        ext = "jpg"
    elif content[:8] == b"\x89PNG\r\n\x1a\n":
        ext = "png"
    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        ext = "webp"
    else:
        return None, "The selfie must be a JPEG, PNG or WebP image."
    folder = current_app.config["SELFIE_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    filename = f"{user_id}_{work_date.isoformat()}_{kind}_{uuid.uuid4().hex[:10]}.{ext}"
    with open(os.path.join(folder, filename), "wb") as fh:
        fh.write(content)
    return filename, None


def _selfie_check(kind_label, selfie_file, user_id, work_date, kind):
    """Enforces the company policy. Returns (filename_or_None, error_response_or_None)."""
    required = _get_settings().selfie_required
    if selfie_file is None or not selfie_file.filename:
        if required:
            return None, (jsonify({
                "message": f"A selfie is required to {kind_label}.", "selfie_required": True,
            }), 400)
        return None, None
    filename, err = _save_selfie(selfie_file, user_id, work_date, kind)
    if err:
        return None, (jsonify({"message": err, "selfie_required": required}), 400)
    return filename, None


@bp.get("/policy")
@jwt_required()
def get_policy():
    settings = _get_settings()
    return jsonify({
        "selfie_required": bool(settings.selfie_required),
        "attendance_buffer_minutes": settings.attendance_buffer_minutes,
        "official_check_in": "09:30",
        "official_check_out": "18:30",
        "company_timezone": current_app.config.get("COMPANY_TIMEZONE", "Asia/Kolkata"),
    })


@bp.put("/policy")
@jwt_required()
def update_policy():
    claims = get_jwt()
    if claims.get("role") not in APPROVER_ROLES:
        return jsonify({"message": "Only a manager or HR Operations can change the attendance policy."}), 403
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"message": "Attendance policy settings must be provided as an object."}), 400
    if not payload:
        return jsonify({"message": "At least one attendance policy setting is required."}), 400
    if "selfie_required" in payload and not isinstance(payload["selfie_required"], bool):
        return jsonify({"message": "selfie_required must be true or false."}), 400
    if "attendance_buffer_minutes" in payload:
        buffer_minutes = payload["attendance_buffer_minutes"]
        if isinstance(buffer_minutes, bool) or not isinstance(buffer_minutes, int) or buffer_minutes not in (5, 10, 15):
            return jsonify({"message": "attendance_buffer_minutes must be 5, 10, or 15."}), 400
    settings = _get_settings()
    if "selfie_required" in payload:
        settings.selfie_required = payload["selfie_required"]
    if "attendance_buffer_minutes" in payload:
        settings.attendance_buffer_minutes = buffer_minutes
    settings.updated_by = int(get_jwt_identity())
    db.session.commit()
    return jsonify({
        "selfie_required": bool(settings.selfie_required),
        "attendance_buffer_minutes": settings.attendance_buffer_minutes,
        "official_check_in": "09:30",
        "official_check_out": "18:30",
        "company_timezone": current_app.config.get("COMPANY_TIMEZONE", "Asia/Kolkata"),
    })


MAX_SESSIONS_PER_DAY = 10
MAX_REASON_LENGTH = 255


def _ensure_sessions(record):
    """A day recorded before multi-session support has no session rows. Turn its own
    fields into session #1 the first time it's modified, so nothing is lost."""
    if record.sessions or not record.clock_in:
        return
    record.sessions.append(AttendanceSession(
        session_no=1, clock_in=record.clock_in, clock_out=record.clock_out,
        clock_in_note=record.clock_in_note, clock_out_note=record.clock_out_note,
        clock_in_lat=record.clock_in_lat, clock_in_lng=record.clock_in_lng, clock_in_within_geofence=record.clock_in_within_geofence,
        clock_out_lat=record.clock_out_lat, clock_out_lng=record.clock_out_lng, clock_out_within_geofence=record.clock_out_within_geofence,
        clock_in_selfie=record.clock_in_selfie, clock_out_selfie=record.clock_out_selfie,
    ))
    db.session.flush()


@bp.post("/clock-in")
@jwt_required()
def clock_in():
    """Starts a session. The first of the day needs nothing extra. If the person already
    has a closed session today (e.g. they clocked out by mistake), this is a RE-ENTRY and
    must come with a reason, which is stored and shown to their manager."""
    claims = get_jwt()
    blocked = _guard_clock_eligibility(claims.get("role"))
    if blocked:
        return blocked

    user_id = int(get_jwt_identity())
    today = company_today()
    record = Attendance.query.filter_by(user_id=user_id, work_date=today).first()
    if record:
        _ensure_sessions(record)
        if record.open_session():
            return jsonify({"message": "You are already clocked in. Clock out first."}), 400

    is_reentry = bool(record and record.sessions)
    note, lat, lng, selfie_file, reason, raw_work_location_id = _read_punch()
    available_work_locations = _ensure_default_work_locations()
    if raw_work_location_id in (None, ""):
        work_location = next(
            (location for location in available_work_locations if location.is_active and location.is_default),
            None,
        )
    else:
        try:
            work_location_id = int(raw_work_location_id)
        except (TypeError, ValueError):
            return jsonify({"message": "Choose a valid work location before clocking in."}), 400
        work_location = WorkLocation.query.filter_by(id=work_location_id, is_active=True).first()
    if not work_location:
        return jsonify({"message": "Choose an active work location before clocking in."}), 400
    blocked = _office_restriction_block(user_id, lat, lng, "clock in")
    if blocked:
        return blocked
    if is_reentry:
        if len(record.sessions) >= MAX_SESSIONS_PER_DAY:
            return jsonify({"message": f"You can have at most {MAX_SESSIONS_PER_DAY} check-ins in a day. Please contact your manager."}), 400
        if len(reason) < 3:
            return jsonify({"message": "Please give a reason for checking in again — your manager will see it.", "reason_required": True}), 400
        if len(reason) > MAX_REASON_LENGTH:
            return jsonify({"message": f"Please keep the reason under {MAX_REASON_LENGTH} characters.", "reason_required": True}), 400

    selfie_name, err = _selfie_check("clock in", selfie_file, user_id, today, "in")
    if err:
        return err

    if not record:
        record = Attendance(user_id=user_id, work_date=today)
        db.session.add(record)
        db.session.flush()
    session = AttendanceSession(
        session_no=len(record.sessions) + 1, clock_in=utc_now_naive(), clock_in_note=note,
        clock_in_lat=lat, clock_in_lng=lng, clock_in_within_geofence=_check_geofence(lat, lng),
        work_location_id=work_location.id, work_location_name=work_location.name,
        clock_in_selfie=selfie_name, reentry_reason=reason if is_reentry else None,
    )
    record.sessions.append(session)
    db.session.flush()
    record.recompute_from_sessions()
    if not (is_reentry and (record.is_regularized or record.status == "regularized")):
        record.status = "present"
    db.session.commit()

    out = record.to_dict()
    out["geofence_warning"] = session.clock_in_within_geofence is False
    out["is_reentry"] = is_reentry
    return jsonify(out), 201


def _claim_session_clock_out(session_id, clock_out_at, note, lat=None, lng=None, within_geofence=None, selfie=None):
    """Atomically close only an open session, so manual and scheduled punches cannot overwrite each other."""
    changed = (
        db.session.query(AttendanceSession)
        .filter(AttendanceSession.id == session_id, AttendanceSession.clock_out.is_(None))
        .update(
            {
                AttendanceSession.clock_out: clock_out_at,
                AttendanceSession.clock_out_note: note,
                AttendanceSession.clock_out_lat: lat,
                AttendanceSession.clock_out_lng: lng,
                AttendanceSession.clock_out_within_geofence: within_geofence,
                AttendanceSession.clock_out_selfie: selfie,
            },
            synchronize_session=False,
        )
    )
    return changed == 1


@bp.post("/clock-out")
@jwt_required()
def clock_out():
    claims = get_jwt()
    blocked = _guard_clock_eligibility(claims.get("role"))
    if blocked:
        return blocked

    user_id = int(get_jwt_identity())
    today = company_today()
    record = Attendance.query.filter_by(user_id=user_id, work_date=today).first()

    if not record or not record.clock_in:
        return jsonify({"message": "You need to clock in before clocking out."}), 400
    _ensure_sessions(record)
    session = record.open_session()
    if not session:
        return jsonify({"message": "You are not clocked in right now. If you clocked out by mistake, check in again."}), 400

    note, lat, lng, selfie_file, _reason, _work_location_id = _read_punch()
    if note is not None and not isinstance(note, str):
        return jsonify({"message": "note must be text."}), 400
    if note == AUTO_CLOCK_OUT_NOTE:
        return jsonify({"message": "This clock-out note is reserved for the attendance system."}), 400
    blocked = _office_restriction_block(user_id, lat, lng, "clock out")
    if blocked:
        return blocked
    selfie_name, err = _selfie_check("clock out", selfie_file, user_id, today, "out")
    if err:
        return err
    clock_out_at = utc_now_naive()
    if not _claim_session_clock_out(
        session.id, clock_out_at, note, lat, lng, _check_geofence(lat, lng), selfie_name
    ):
        db.session.rollback()
        return jsonify({"message": "This session was already clocked out. Refresh and try again."}), 409
    db.session.refresh(session)
    record.recompute_from_sessions()
    db.session.commit()

    out = record.to_dict()
    out["geofence_warning"] = session.clock_out_within_geofence is False
    return jsonify(out)


@bp.get("/today")
@jwt_required()
def today_status():
    user_id = int(get_jwt_identity())
    record = Attendance.query.filter_by(user_id=user_id, work_date=company_today()).first()
    claims = get_jwt()
    return jsonify(
        {
            "record": record.to_dict() if record else None,
            "has_clock_in_out": claims.get("role") in ROLES_WITH_CLOCK_IN_OUT,
            "restrict_to_office": bool((db.session.get(User, user_id) or User()).restrict_to_office),
        }
    )


@bp.get("/history")
@jwt_required()
def history():
    user_id = int(get_jwt_identity())
    month = request.args.get("month", type=int) or company_today().month
    year = request.args.get("year", type=int) or company_today().year

    records = (
        Attendance.query.filter(
            Attendance.user_id == user_id,
            db.extract("month", Attendance.work_date) == month,
            db.extract("year", Attendance.work_date) == year,
        )
        .order_by(Attendance.work_date.desc())
        .all()
    )
    return jsonify([r.to_dict() for r in records])


@bp.get("/team")
@jwt_required()
def team_attendance():
    """Managers see direct reports; HR Operations / Operations see everyone."""
    claims = get_jwt()
    role = claims.get("role")
    user_id = int(get_jwt_identity())
    target_date = request.args.get("date", company_today().isoformat())

    if role in (HR_OPERATIONS, OPERATIONS, SUPER_ADMIN):
        user_ids = [u.id for u in User.query.filter_by(is_active=True).all()]
    elif role == MANAGER:
        user_ids = [u.id for u in User.query.filter_by(manager_id=user_id).all()]
    else:
        return jsonify({"message": "You do not have permission to view team attendance."}), 403

    records = Attendance.query.filter(
        Attendance.user_id.in_(user_ids), Attendance.work_date == target_date
    ).all()
    # Exact coordinates and selfies are only for the person, their manager and HR Ops.
    return jsonify([
        r.to_dict() if (r.user and _can_view_sensitive(claims, user_id, r.user)) else _redact(r.to_dict())
        for r in records
    ])


@bp.post("/regularize/<int:record_id>")
@jwt_required()
def regularize(record_id):
    """Manager / HR Operations approves a missed-punch regularization request."""
    claims = get_jwt()
    if claims.get("role") not in APPROVER_ROLES:
        return jsonify({"message": "You do not have permission to regularize attendance."}), 403

    record = Attendance.query.get_or_404(record_id)
    if not _authorize_reviewer(claims, int(get_jwt_identity()), record):
        return jsonify({"message": "You can only regularize attendance for your own direct reports."}), 403
    payload = request.get_json(silent=True) or {}
    record.is_regularized = True
    record.regularization_reason = payload.get("reason", "")
    record.status = "regularized"
    db.session.commit()
    return jsonify(record.to_dict())


# ============================================================================
# Regularization reasons — the "rules" a manager/HR Ops defines; an employee
# must pick one of these when asking for a missed punch to be excused.
# ============================================================================

@bp.get("/regularization-reasons")
@jwt_required()
def list_regularization_reasons():
    only_active = request.args.get("active_only", "true") != "false"
    query = AttendanceRegularizationReason.query
    if only_active:
        query = query.filter_by(is_active=True)
    rows = query.order_by(AttendanceRegularizationReason.label.asc()).all()
    return jsonify([r.to_dict() for r in rows])


@bp.post("/regularization-reasons")
@jwt_required()
def create_regularization_reason():
    claims = get_jwt()
    if claims.get("role") not in APPROVER_ROLES:
        return jsonify({"message": "Only a manager or HR Operations can define regularization reasons."}), 403
    payload = request.get_json(silent=True) or {}
    label = (payload.get("label") or "").strip()
    if not label:
        return jsonify({"message": "A label is required."}), 400
    if AttendanceRegularizationReason.query.filter_by(label=label).first():
        return jsonify({"message": f"'{label}' already exists."}), 409
    reason = AttendanceRegularizationReason(
        label=label, description=payload.get("description"), created_by=int(get_jwt_identity())
    )
    db.session.add(reason)
    db.session.commit()
    return jsonify(reason.to_dict()), 201


@bp.put("/regularization-reasons/<int:reason_id>")
@jwt_required()
def update_regularization_reason(reason_id):
    claims = get_jwt()
    if claims.get("role") not in APPROVER_ROLES:
        return jsonify({"message": "Only a manager or HR Operations can edit regularization reasons."}), 403
    reason = AttendanceRegularizationReason.query.get_or_404(reason_id)
    payload = request.get_json(silent=True) or {}
    if "label" in payload and payload["label"].strip():
        reason.label = payload["label"].strip()
    if "description" in payload:
        reason.description = payload["description"]
    if "is_active" in payload:
        reason.is_active = bool(payload["is_active"])
    db.session.commit()
    return jsonify(reason.to_dict())


# ============================================================================
# Self-service regularization: employee requests -> manager/HR Ops reviews
# ============================================================================

REGULARIZATION_MONTHLY_LIMIT = 5


def _regularization_month_bounds(today=None):
    today = today or company_today()
    start = datetime(today.year, today.month, 1)
    end_year = today.year + 1 if today.month == 12 else today.year
    end_month = 1 if today.month == 12 else today.month + 1
    end = datetime(end_year, end_month, 1)
    return start, end


def _regularization_month_usage(user_id, today=None):
    start, end = _regularization_month_bounds(today)
    used = AttendanceRegularizationRequest.query.filter(
        AttendanceRegularizationRequest.user_id == user_id,
        AttendanceRegularizationRequest.submitted_at >= start,
        AttendanceRegularizationRequest.submitted_at < end,
    ).count()
    return {
        "limit": REGULARIZATION_MONTHLY_LIMIT,
        "used": used,
        "remaining": max(0, REGULARIZATION_MONTHLY_LIMIT - used),
    }


@bp.get("/regularization-limit")
@jwt_required()
def regularization_limit():
    return jsonify(_regularization_month_usage(int(get_jwt_identity())))


@bp.post("/regularize-request")
@jwt_required()
def request_regularization():
    """An employee (any role with clock in/out, including recruiters) asks for a
    date to be excused, with a reason picked from the manager-defined list."""
    user_id = int(get_jwt_identity())
    payload = request.get_json(silent=True) or {}
    try:
        work_date = datetime.strptime(payload.get("work_date", ""), "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"message": "A valid work_date (YYYY-MM-DD) is required."}), 400
    if work_date > company_today():
        return jsonify({"message": "You cannot request regularization for a future date."}), 400

    User.query.filter_by(id=user_id).with_for_update().first()

    reason_id = payload.get("reason_id")
    reason = AttendanceRegularizationReason.query.get(reason_id) if reason_id else None
    if not reason or not reason.is_active:
        return jsonify({"message": "Please pick a valid reason."}), 400

    quota = _regularization_month_usage(user_id)
    if quota["remaining"] == 0:
        return jsonify({
            "message": "your limit is exceeded please contact your manager",
            **quota,
        }), 429

    record = Attendance.query.filter_by(user_id=user_id, work_date=work_date).first()
    if record and record.regularization_status == "pending":
        return jsonify({"message": "There is already a pending request for this date."}), 409
    if record and record.is_regularized:
        return jsonify({"message": "This date has already been regularized."}), 400

    if not record:
        record = Attendance(user_id=user_id, work_date=work_date, status="absent")
        db.session.add(record)

    record.regularization_status = "pending"
    record.regularization_reason_id = reason.id
    record.regularization_note = (payload.get("note") or "").strip()[:255]
    record.regularization_requested_at = utc_now_naive()
    record.regularization_reviewed_by = None
    record.regularization_reviewed_at = None
    record.regularization_review_comment = None
    db.session.flush()
    db.session.add(AttendanceRegularizationRequest(
        user_id=user_id,
        attendance_id=record.id,
    ))
    db.session.commit()

    requester = User.query.get(user_id)
    notify_ids = [requester.manager_id] if requester.manager_id else [u.id for u in User.query.filter(User.role.in_(FULL_ACCESS), User.is_active.is_(True)).all()]
    send_push(notify_ids, "New regularization request",
               f"{requester.full_name} requested {work_date.isoformat()} be regularized.",
               data={"type": "regularization_request", "record_id": record.id})

    return jsonify(record.to_dict()), 201


def _scoped_regularization_query(claims, user_id, status):
    query = Attendance.query.join(User, User.id == Attendance.user_id).filter(User.is_active.is_(True))
    if status:
        query = query.filter(Attendance.regularization_status == status)
    else:
        query = query.filter(Attendance.regularization_status.isnot(None))
    role = claims.get("role")
    if role in FULL_ACCESS:
        return query
    if role == MANAGER:
        return query.filter(User.manager_id == user_id)
    return None


@bp.get("/regularization-requests")
@jwt_required()
def list_regularization_requests():
    """A manager sees their own reports' requests; HR Operations sees everyone's."""
    claims = get_jwt()
    status = request.args.get("status", "pending")
    if status not in ("pending", "approved", "rejected", "all"):
        return jsonify({"message": "status must be pending, approved, rejected, or all."}), 400
    query = _scoped_regularization_query(
        claims,
        int(get_jwt_identity()),
        None if status == "all" else status,
    )
    if query is None:
        return jsonify({"message": "You do not have permission to review regularization requests."}), 403
    rows = query.order_by(Attendance.regularization_requested_at.desc()).all()
    return jsonify([r.to_dict() for r in rows])


def _authorize_reviewer(claims, user_id, record):
    role = claims.get("role")
    if role in FULL_ACCESS:
        return True
    if role == MANAGER and record.user and record.user.manager_id == user_id:
        return True
    return False


@bp.post("/regularization-requests/<int:record_id>/approve")
@jwt_required()
def approve_regularization_request(record_id):
    claims = get_jwt()
    reviewer_id = int(get_jwt_identity())
    record = Attendance.query.get_or_404(record_id)
    if not _authorize_reviewer(claims, reviewer_id, record):
        return jsonify({"message": "You do not have permission to review this request."}), 403
    if record.regularization_status != "pending":
        return jsonify({"message": f"This request is '{record.regularization_status or 'not requested'}', not pending."}), 400

    payload = request.get_json(silent=True) or {}
    record.regularization_status = "approved"
    record.is_regularized = True
    record.status = "regularized"
    record.regularization_reviewed_by = reviewer_id
    record.regularization_reviewed_at = utc_now_naive()
    record.regularization_review_comment = payload.get("comment")
    db.session.commit()
    send_push(record.user_id, "Regularization approved", f"Your request for {record.work_date.isoformat()} was approved.",
               data={"type": "regularization_approved", "record_id": record.id})
    return jsonify(record.to_dict())


@bp.post("/regularization-requests/<int:record_id>/reject")
@jwt_required()
def reject_regularization_request(record_id):
    claims = get_jwt()
    reviewer_id = int(get_jwt_identity())
    record = Attendance.query.get_or_404(record_id)
    if not _authorize_reviewer(claims, reviewer_id, record):
        return jsonify({"message": "You do not have permission to review this request."}), 403
    if record.regularization_status != "pending":
        return jsonify({"message": f"This request is '{record.regularization_status or 'not requested'}', not pending."}), 400

    payload = request.get_json(silent=True) or {}
    comment = (payload.get("comment") or "").strip()
    if not comment:
        return jsonify({"message": "A comment explaining the rejection is required."}), 400
    record.regularization_status = "rejected"
    record.regularization_reviewed_by = reviewer_id
    record.regularization_reviewed_at = utc_now_naive()
    record.regularization_review_comment = comment
    db.session.commit()
    send_push(record.user_id, "Regularization rejected", f"Your request for {record.work_date.isoformat()} was rejected: {comment}",
               data={"type": "regularization_rejected", "record_id": record.id})
    return jsonify(record.to_dict())


# ============================================================================
# Holiday calendar — Manager/HR Ops set it, everyone sees it
# ============================================================================

@bp.get("/holidays")
@jwt_required()
def list_holidays():
    year = request.args.get("year", type=int)
    query = Holiday.query
    if year:
        query = query.filter(db.extract("year", Holiday.holiday_date) == year)
    rows = query.order_by(Holiday.holiday_date.asc()).all()
    return jsonify([h.to_dict() for h in rows])


@bp.post("/holidays")
@jwt_required()
def create_holiday():
    claims = get_jwt()
    if claims.get("role") not in CALENDAR_MANAGER_ROLES:
        return jsonify({"message": "Only a manager or HR Operations can add holidays."}), 403
    payload = request.get_json(silent=True) or {}
    try:
        holiday_date = datetime.strptime(payload.get("holiday_date", ""), "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"message": "A valid holiday_date (YYYY-MM-DD) is required."}), 400
    if not (payload.get("name") or "").strip():
        return jsonify({"message": "A name for the holiday is required."}), 400
    if Holiday.query.filter_by(holiday_date=holiday_date).first():
        return jsonify({"message": f"A holiday is already set for {holiday_date.isoformat()}."}), 409
    holiday = Holiday(
        name=payload["name"].strip(), holiday_date=holiday_date,
        description=payload.get("description"), created_by=int(get_jwt_identity()),
    )
    db.session.add(holiday)
    db.session.commit()
    return jsonify(holiday.to_dict()), 201


@bp.put("/holidays/<int:holiday_id>")
@jwt_required()
def update_holiday(holiday_id):
    claims = get_jwt()
    if claims.get("role") not in CALENDAR_MANAGER_ROLES:
        return jsonify({"message": "Only a manager or HR Operations can edit holidays."}), 403
    holiday = Holiday.query.get_or_404(holiday_id)
    payload = request.get_json(silent=True) or {}
    if payload.get("name", "").strip():
        holiday.name = payload["name"].strip()
    if "description" in payload:
        holiday.description = payload["description"]
    if payload.get("holiday_date"):
        try:
            holiday.holiday_date = datetime.strptime(payload["holiday_date"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"message": "holiday_date must be YYYY-MM-DD."}), 400
    db.session.commit()
    return jsonify(holiday.to_dict())


@bp.delete("/holidays/<int:holiday_id>")
@jwt_required()
def delete_holiday(holiday_id):
    claims = get_jwt()
    if claims.get("role") not in CALENDAR_MANAGER_ROLES:
        return jsonify({"message": "Only a manager or HR Operations can remove holidays."}), 403
    holiday = Holiday.query.get_or_404(holiday_id)
    db.session.delete(holiday)
    db.session.commit()
    return jsonify({"message": "Holiday removed."})


# ============================================================================
# Scheduled reminders — called by an external cron hitting this once per
# trigger time (e.g. 9:30am clock-in check, 6:30pm clock-out check), not run
# in-process, so it works the same whether the app runs on one worker or many.
# Guarded by a shared secret, not a login, since nobody is signed in when cron runs.
# ============================================================================

@bp.post("/internal/attendance-reminders")
def run_attendance_reminders():
    secret = request.headers.get("X-Internal-Secret")
    if not secret or secret != current_app.config.get("INTERNAL_TASK_SECRET"):
        return jsonify({"message": "Not authorized."}), 403

    kind = (request.get_json(silent=True) or {}).get("kind")
    if kind not in ("clock_in_reminder", "clock_out_reminder", "manager_missing_alert"):
        return jsonify({"message": "kind must be clock_in_reminder, clock_out_reminder, or manager_missing_alert."}), 400

    today = company_today()
    if today.isoformat() in {h.holiday_date.isoformat() for h in Holiday.query.filter_by(holiday_date=today).all()}:
        return jsonify({"sent": 0, "skipped": "today is a holiday"})

    eligible_ids = {u.id for u in User.query.filter(User.is_active.is_(True), User.role != "contract_employee").all()}
    punched_in_ids = {r.user_id for r in Attendance.query.filter(Attendance.work_date == today, Attendance.clock_in.isnot(None)).all()}
    punched_out_ids = {r.user_id for r in Attendance.query.filter(Attendance.work_date == today, Attendance.clock_out.isnot(None)).all()}

    sent = 0
    if kind == "clock_in_reminder":
        for uid in eligible_ids - punched_in_ids:
            send_push(uid, "Don't forget to clock in", "You haven't clocked in yet today.", data={"type": "clock_in_reminder"})
            sent += 1
    elif kind == "clock_out_reminder":
        for uid in (eligible_ids & punched_in_ids) - punched_out_ids:
            send_push(uid, "Don't forget to clock out", "You're still clocked in from this morning.", data={"type": "clock_out_reminder"})
            sent += 1
    else:  # manager_missing_alert
        missing = eligible_ids - punched_in_ids
        managers_to_missing = {}
        for u in User.query.filter(User.id.in_(missing)).all():
            if u.manager_id:
                managers_to_missing.setdefault(u.manager_id, []).append(u.full_name)
        for manager_id, names in managers_to_missing.items():
            who = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
            send_push(manager_id, "Team attendance", f"Not yet clocked in: {who}", data={"type": "manager_missing_alert"})
            sent += 1

    return jsonify({"sent": sent})


@bp.post("/internal/auto-midnight-clockout")
def run_auto_midnight_clockouts():
    secret = request.headers.get("X-Internal-Secret")
    if not secret or secret != current_app.config.get("INTERNAL_TASK_SECRET"):
        return jsonify({"message": "Not authorized."}), 403

    closing_date = company_today() - timedelta(days=1)
    local_midnight = datetime.combine(
        closing_date + timedelta(days=1), time.min, tzinfo=company_timezone()
    )
    midnight_utc = local_midnight.astimezone(timezone.utc).replace(tzinfo=None)
    records = Attendance.query.filter_by(work_date=closing_date).all()
    closed_sessions = 0

    for record in records:
        _ensure_sessions(record)
        closed_for_record = 0
        for session in list(record.sessions):
            if session.clock_out is not None or session.clock_in >= midnight_utc:
                continue
            if _claim_session_clock_out(session.id, midnight_utc, AUTO_CLOCK_OUT_NOTE):
                db.session.refresh(session)
                closed_for_record += 1
        if closed_for_record:
            record.recompute_from_sessions()
            closed_sessions += closed_for_record

    db.session.commit()
    return jsonify({"work_date": closing_date.isoformat(), "closed_sessions": closed_sessions})


# ============================================================================
# Calendar + manager's full view
# ============================================================================

def _viewer_scope(claims, viewer_id):
    """Who the viewer may look at: HR Ops / Operations -> everyone active; a Manager
    -> their direct reports; anyone else -> nobody (only themselves, handled separately)."""
    role = claims.get("role")
    if role in (HR_OPERATIONS, OPERATIONS, SUPER_ADMIN):
        return {u.id for u in User.query.filter_by(is_active=True).all()}
    if role == MANAGER:
        return {u.id for u in User.query.filter_by(manager_id=viewer_id).all()}
    return set()


def _can_view_user(claims, viewer_id, target_id):
    return target_id == viewer_id or target_id in _viewer_scope(claims, viewer_id)


def _can_view_sensitive(claims, viewer_id, target):
    """Selfies and exact coordinates are for the person themselves, their manager and
    HR Operations / Super Admin — deliberately NOT the wider Operations role."""
    role = claims.get("role")
    if target.id == viewer_id or role in FULL_ACCESS:
        return True
    return role == MANAGER and target.manager_id == viewer_id


_SENSITIVE_KEYS = ("clock_in_lat", "clock_in_lng", "clock_out_lat", "clock_out_lng",
                   "has_clock_in_selfie", "has_clock_out_selfie")


def _redact(record_dict):
    out = {k: v for k, v in record_dict.items() if k not in _SENSITIVE_KEYS}
    if "sessions" in out:
        out["sessions"] = [{k: v for k, v in sess.items() if k not in _SENSITIVE_KEYS} for sess in out["sessions"]]
    return out


def _month_bounds(month, year):
    first = date(year, month, 1)
    last = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    return first, last


def _calendar_payload(target, month, year, redact=False):
    """One person's whole month: every punch, holidays, approved leave and a summary —
    everything a calendar view needs in a single call."""
    first, last = _month_bounds(month, year)
    records = (Attendance.query.filter(Attendance.user_id == target.id, Attendance.work_date >= first, Attendance.work_date <= last)
               .order_by(Attendance.work_date.asc()).all())
    automatic_clockout_bell_dates = set()

    def add_automatic_bell_date(record):
        following_day = record.work_date + timedelta(days=1)
        for session in record.effective_sessions():
            if not session.is_automatic_clock_out:
                continue
            local_clock_out = to_company_local(session.clock_out)
            if (
                local_clock_out.date() == following_day
                and local_clock_out.time().replace(tzinfo=None) == time.min
                and first <= following_day <= last
            ):
                automatic_clockout_bell_dates.add(following_day.isoformat())

    for record in records:
        add_automatic_bell_date(record)
    previous_record = Attendance.query.filter_by(
        user_id=target.id, work_date=first - timedelta(days=1)
    ).first()
    if previous_record:
        add_automatic_bell_date(previous_record)

    holidays = Holiday.query.filter(Holiday.holiday_date >= first, Holiday.holiday_date <= last).order_by(Holiday.holiday_date.asc()).all()
    leaves = LeaveRequest.query.filter(
        LeaveRequest.user_id == target.id, LeaveRequest.status.in_(("pending", "approved")),
        LeaveRequest.start_date <= last, LeaveRequest.end_date >= first,
    ).all()
    leave_requests = LeaveRequest.query.filter(
        LeaveRequest.user_id == target.id,
        LeaveRequest.start_date <= last, LeaveRequest.end_date >= first,
    ).order_by(LeaveRequest.created_at.desc()).all()

    leave_days = set()
    for lv in leaves:
        if lv.status != "approved":
            continue
        d = max(lv.start_date, first)
        while d <= min(lv.end_date, last):
            leave_days.add(d)
            d += timedelta(days=1)

    rec_dicts = [_redact(r.to_dict()) if redact else r.to_dict() for r in records]
    summary = {
        "present": sum(1 for r in records if r.status in ("present", "regularized")),
        "half_day": sum(1 for r in records if r.status == "half_day"),
        "absent": sum(1 for r in records if r.status == "absent"),
        "on_leave": len(leave_days),
        "holidays": len(holidays),
        "total_hours": round(sum((r.total_hours or 0) for r in records), 2),
        "pending_regularizations": sum(1 for r in records if r.regularization_status == "pending"),
        "outside_office": sum(1 for r in records if any(
            x is False for sess in r.effective_sessions() for x in (sess.clock_in_within_geofence, sess.clock_out_within_geofence))),
        "reentries": sum(max(0, len(r.effective_sessions()) - 1) for r in records),
    }
    return {
        "user": {"id": target.id, "full_name": target.full_name, "employee_code": target.employee_code,
                 "role": target.role, "designation": target.designation},
        "month": month, "year": year,
        "records": rec_dicts,
        "automatic_clockout_bell_dates": sorted(automatic_clockout_bell_dates),
        "holidays": [h.to_dict() for h in holidays],
        "leaves": [
            {
                "start_date": lv.start_date.isoformat(),
                "end_date": lv.end_date.isoformat(),
                "leave_type": lv.leave_type.name if lv.leave_type else None,
                "days": lv.days,
                "status": lv.status,
                "reason": lv.reason,
            }
            for lv in leaves
        ],
        "leave_requests": [
            {
                "start_date": lv.start_date.isoformat(),
                "end_date": lv.end_date.isoformat(),
                "leave_type": lv.leave_type.name if lv.leave_type else None,
                "status": lv.status,
            }
            for lv in leave_requests
        ],
        "summary": summary,
    }


def _month_year_args():
    month = request.args.get("month", type=int) or company_today().month
    year = request.args.get("year", type=int) or company_today().year
    return (month, year) if 1 <= month <= 12 and 2000 <= year <= 2100 else (None, None)


@bp.get("/my-calendar")
@jwt_required()
def my_calendar():
    """The signed-in person's own calendar for ANY month — every check-in/out time,
    holidays, approved leave, and a monthly summary."""
    month, year = _month_year_args()
    if not month:
        return jsonify({"message": "A valid month (1-12) and year are required."}), 400
    return jsonify(_calendar_payload(User.query.get(int(get_jwt_identity())), month, year))


@bp.get("/team/<int:user_id>/calendar")
@jwt_required()
def team_member_calendar(user_id):
    """A manager's (or HR Ops') complete calendar view of one team member."""
    claims, viewer_id = get_jwt(), int(get_jwt_identity())
    if not _can_view_user(claims, viewer_id, user_id):
        return jsonify({"message": "You do not have permission to view this person's attendance."}), 403
    month, year = _month_year_args()
    if not month:
        return jsonify({"message": "A valid month (1-12) and year are required."}), 400
    target = User.query.get_or_404(user_id)
    return jsonify(_calendar_payload(target, month, year, redact=not _can_view_sensitive(claims, viewer_id, target)))


@bp.get("/team/<int:user_id>/records")
@jwt_required()
def team_member_attendance_records(user_id):
    claims, viewer_id = get_jwt(), int(get_jwt_identity())
    target, err = _manager_target(claims, viewer_id, user_id)
    if err:
        return err

    def parse_filter_date(name):
        value = request.args.get(name)
        if not value:
            return None, None
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None, (jsonify({"message": f"{name} must be a valid date (YYYY-MM-DD)."}), 400)
        if parsed.isoformat() != value:
            return None, (jsonify({"message": f"{name} must be a valid date (YYYY-MM-DD)."}), 400)
        return parsed, None

    start_date, err = parse_filter_date("start_date")
    if err:
        return err
    end_date, err = parse_filter_date("end_date")
    if err:
        return err
    if start_date and end_date and start_date > end_date:
        return jsonify({"message": "start_date cannot be after end_date."}), 400

    query = Attendance.query.filter_by(user_id=user_id)
    if start_date:
        query = query.filter(Attendance.work_date >= start_date)
    if end_date:
        query = query.filter(Attendance.work_date <= end_date)
    records = query.order_by(Attendance.work_date.desc()).all()
    can_view_sensitive = _can_view_sensitive(claims, viewer_id, target)
    return jsonify([
        record.to_dict() if can_view_sensitive else _redact(record.to_dict())
        for record in records
    ])


def _build_overview(claims, viewer_id, target_date):
    scope = _viewer_scope(claims, viewer_id)
    users = (User.query.filter(User.id.in_(scope or {0}), User.is_active.is_(True), User.role != "contract_employee")
             .order_by(User.full_name.asc()).all())
    records = {r.user_id: r for r in Attendance.query.filter(Attendance.user_id.in_(scope or {0}), Attendance.work_date == target_date).all()}
    on_leave = {lv.user_id for lv in LeaveRequest.query.filter(
        LeaveRequest.user_id.in_(scope or {0}), LeaveRequest.status == "approved",
        LeaveRequest.start_date <= target_date, LeaveRequest.end_date >= target_date).all()}
    holiday = Holiday.query.filter_by(holiday_date=target_date).first()
    is_today = target_date == company_today()

    rows, counts = [], {"present": 0, "not_clocked_in": 0, "absent": 0, "on_leave": 0, "outside_office": 0,
                        "clocked_in_now": 0, "reentries": 0}
    for u in users:
        rec = records.get(u.id)
        if rec and rec.clock_in:
            status = rec.status
        elif u.id in on_leave:
            status = "on_leave"
        elif holiday:
            status = "holiday"
        elif rec and rec.status:
            status = rec.status
        else:
            status = "not_clocked_in" if is_today else "absent"

        sensitive_ok = _can_view_sensitive(claims, viewer_id, u)
        sessions = rec.effective_sessions() if rec else []

        # last known location = the most recent punch with coordinates across ALL sessions
        location = None
        if sensitive_ok:
            punches = []
            for sess in sessions:
                if sess.clock_in and sess.clock_in_lat is not None:
                    punches.append((sess.clock_in, "clock_in", sess.clock_in_lat, sess.clock_in_lng, sess.clock_in_within_geofence))
                if sess.clock_out and sess.clock_out_lat is not None:
                    punches.append((sess.clock_out, "clock_out", sess.clock_out_lat, sess.clock_out_lng, sess.clock_out_within_geofence))
            if punches:
                at, source, lat, lng, within = max(punches, key=lambda p: p[0])
                location = {"latitude": lat, "longitude": lng, "as_of": at.isoformat() + "Z", "source": source, "within_geofence": within}

        outside = any(x is False for sess in sessions for x in (sess.clock_in_within_geofence, sess.clock_out_within_geofence))
        clocked_in_now = any(sess.clock_out is None for sess in sessions)
        reentries = [sess for sess in sessions if (sess.session_no or 1) > 1]
        latest_reentry = reentries[-1] if reentries else None

        if status in ("present", "regularized", "half_day"):
            counts["present"] += 1
        elif status in counts:
            counts[status] += 1
        counts["outside_office"] += int(outside)
        counts["clocked_in_now"] += int(clocked_in_now)
        counts["reentries"] += len(reentries)

        rec_dict = rec.to_dict() if rec else None
        rows.append({
            "user": {"id": u.id, "full_name": u.full_name, "employee_code": u.employee_code, "role": u.role, "designation": u.designation,
                     "restrict_to_office": bool(u.restrict_to_office)},
            "status": status, "record": (rec_dict if sensitive_ok or not rec_dict else _redact(rec_dict)),
            "clocked_in_now": clocked_in_now, "last_known_location": location, "outside_office": outside,
            "session_count": len(sessions), "reentry_count": len(reentries),
            "latest_reentry": ({"at": latest_reentry.clock_in.isoformat() + "Z", "reason": latest_reentry.reentry_reason} if latest_reentry else None),
        })
    return {"date": target_date.isoformat(), "is_holiday": bool(holiday), "holiday_name": holiday.name if holiday else None,
            "summary": counts, "people": rows}


@bp.get("/team/overview")
@jwt_required()
def team_overview():
    """Everyone in the viewer's scope for one day — INCLUDING people who haven't
    punched in — with status, times and last-known location (where they were at their
    most recent punch). The existing /team endpoint only lists people with a record."""
    claims, viewer_id = get_jwt(), int(get_jwt_identity())
    if claims.get("role") not in VIEWER_ROLES:
        return jsonify({"message": "You do not have permission to view team attendance."}), 403
    try:
        target_date = datetime.strptime(request.args.get("date", company_today().isoformat()), "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"message": "date must be YYYY-MM-DD."}), 400
    return jsonify(_build_overview(claims, viewer_id, target_date))


@bp.get("/team/analytics")
@jwt_required()
def team_attendance_analytics():
    """Attendance rows for the viewer's authorized team and a bounded date range.

    The response intentionally contains only dashboard fields; location and selfie
    metadata remain on the individual calendar endpoints.
    """
    claims, viewer_id = get_jwt(), int(get_jwt_identity())
    if claims.get("role") not in VIEWER_ROLES:
        return jsonify({"message": "You do not have permission to view team attendance."}), 403
    date_range, error = _parse_range(default_days=0, max_days=92)
    if error:
        return error
    start, end = date_range
    scope = _viewer_scope(claims, viewer_id)
    users = (
        User.query.filter(
            User.id.in_(scope or {0}),
            User.is_active.is_(True),
            User.role != "contract_employee",
        )
        .order_by(User.full_name.asc())
        .all()
    )
    user_ids = [user.id for user in users]
    records = (
        Attendance.query.filter(
            Attendance.user_id.in_(user_ids or {0}),
            Attendance.work_date >= start,
            Attendance.work_date <= end,
        )
        .order_by(Attendance.work_date.asc())
        .all()
    )
    holidays = Holiday.query.filter(
        Holiday.holiday_date >= start, Holiday.holiday_date <= end
    ).order_by(Holiday.holiday_date.asc()).all()
    approved_leaves = LeaveRequest.query.filter(
        LeaveRequest.user_id.in_(user_ids or {0}),
        LeaveRequest.status == "approved",
        LeaveRequest.start_date <= end,
        LeaveRequest.end_date >= start,
    ).all()
    settings = _get_settings()

    records_by_user = {}
    for record in records:
        records_by_user.setdefault(record.user_id, []).append({
            "id": record.id,
            "work_date": record.work_date.isoformat(),
            "clock_in": record.clock_in.isoformat() if record.clock_in else None,
            "clock_out": record.clock_out.isoformat() if record.clock_out else None,
            "status": record.status,
        })

    leave_days_by_user = {}
    for leave in approved_leaves:
        current = max(leave.start_date, start)
        last = min(leave.end_date, end)
        days = leave_days_by_user.setdefault(leave.user_id, set())
        while current <= last:
            days.add(current.isoformat())
            current += timedelta(days=1)

    return jsonify({
        "from": start.isoformat(),
        "to": end.isoformat(),
        "company_timezone": current_app.config.get("COMPANY_TIMEZONE", "Asia/Kolkata"),
        "policy": {
            "official_check_in": "09:30",
            "official_check_out": "18:30",
            "attendance_buffer_minutes": settings.attendance_buffer_minutes,
        },
        "holidays": [holiday.to_dict() for holiday in holidays],
        "employees": [
            {
                "id": user.id,
                "employee_code": user.employee_code,
                "full_name": user.full_name,
                "designation": user.designation,
                "department": user.department.name if user.department else "Unassigned",
                "records": records_by_user.get(user.id, []),
                "approved_leave_dates": sorted(leave_days_by_user.get(user.id, set())),
            }
            for user in users
        ],
    })



@bp.get("/records/<int:record_id>/selfie/<kind>")
@jwt_required()
def get_selfie(record_id, kind):
    """Selfies are private: only the person, their manager, and HR Operations may view."""
    if kind not in ("in", "out"):
        return jsonify({"message": "kind must be 'in' or 'out'."}), 400
    claims, viewer_id = get_jwt(), int(get_jwt_identity())
    record = Attendance.query.get_or_404(record_id)
    if not record.user or not _can_view_sensitive(claims, viewer_id, record.user):
        return jsonify({"message": "You do not have permission to view this selfie."}), 403
    filename = record.clock_in_selfie if kind == "in" else record.clock_out_selfie
    if not filename:
        return jsonify({"message": "No selfie was captured for this punch."}), 404
    response = send_from_directory(current_app.config["SELFIE_FOLDER"], filename)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _parse_range(default_days=6, max_days=92):
    """Reads ?from&to. Returns ((start, end), None) or (None, error_response)."""
    try:
        end = datetime.strptime(request.args["to"], "%Y-%m-%d").date() if request.args.get("to") else company_today()
        start = datetime.strptime(request.args["from"], "%Y-%m-%d").date() if request.args.get("from") else end - timedelta(days=default_days)
    except ValueError:
        return None, (jsonify({"message": "from/to must be YYYY-MM-DD."}), 400)
    if start > end:
        return None, (jsonify({"message": "'from' must not be after 'to'."}), 400)
    if (end - start).days > max_days:
        return None, (jsonify({"message": f"Please choose a range of {max_days + 1} days or less."}), 400)
    return (start, end), None


def _build_reentries(claims, viewer_id, start, end):
    scope = _viewer_scope(claims, viewer_id)
    rows = (AttendanceSession.query.join(Attendance, Attendance.id == AttendanceSession.attendance_id)
            .filter(Attendance.user_id.in_(scope or {0}), Attendance.work_date >= start, Attendance.work_date <= end,
                    AttendanceSession.session_no > 1)
            .order_by(Attendance.work_date.desc(), AttendanceSession.clock_in.desc()).all())

    items, per_person = [], {}
    for sess in rows:
        att = sess.attendance
        prev = next((x for x in att.sessions if x.session_no == sess.session_no - 1), None)
        gap = round((sess.clock_in - prev.clock_out).total_seconds() / 60) if prev and prev.clock_out else None
        sensitive_ok = _can_view_sensitive(claims, viewer_id, att.user)
        items.append({
            "session_id": sess.id, "attendance_id": att.id, "work_date": att.work_date.isoformat(),
            "user": {"id": att.user.id, "full_name": att.user.full_name, "employee_code": att.user.employee_code, "designation": att.user.designation},
            "session_no": sess.session_no,
            "previous_clock_out": prev.clock_out.isoformat() + "Z" if prev and prev.clock_out else None,
            "clock_in": sess.clock_in.isoformat() + "Z",
            "gap_minutes": gap, "reason": sess.reentry_reason,
            "outside_office": sess.clock_in_within_geofence is False,
            "has_selfie": bool(sess.clock_in_selfie) and sensitive_ok,
            "still_clocked_in": sess.clock_out is None,
        })
        entry = per_person.setdefault(att.user.id, {"user": {"id": att.user.id, "full_name": att.user.full_name}, "count": 0})
        entry["count"] += 1
    return {
        "from": start.isoformat(), "to": end.isoformat(), "total": len(items),
        "people_count": len(per_person),
        "by_person": sorted(per_person.values(), key=lambda x: -x["count"]),
        "reentries": items,
    }


@bp.get("/team/reentries")
@jwt_required()
def team_reentries():
    """Every time someone in the viewer's scope checked in AGAIN after checking out, with
    the reason they gave — the manager's exceptions report. Defaults to the last 7 days."""
    claims, viewer_id = get_jwt(), int(get_jwt_identity())
    if claims.get("role") not in VIEWER_ROLES:
        return jsonify({"message": "You do not have permission to view this report."}), 403
    rng, err = _parse_range()
    if err:
        return err
    return jsonify(_build_reentries(claims, viewer_id, *rng))




@bp.get("/sessions/<int:session_id>/selfie/<kind>")
@jwt_required()
def get_session_selfie(session_id, kind):
    """Selfie for one specific check-in/out session (same privacy rules as the day-level one)."""
    if kind not in ("in", "out"):
        return jsonify({"message": "kind must be 'in' or 'out'."}), 400
    claims, viewer_id = get_jwt(), int(get_jwt_identity())
    sess = AttendanceSession.query.get_or_404(session_id)
    owner = sess.attendance.user
    if not owner or not _can_view_sensitive(claims, viewer_id, owner):
        return jsonify({"message": "You do not have permission to view this selfie."}), 403
    filename = sess.clock_in_selfie if kind == "in" else sess.clock_out_selfie
    if not filename:
        return jsonify({"message": "No selfie was captured for this punch."}), 404
    response = send_from_directory(current_app.config["SELFIE_FOLDER"], filename)
    response.headers["Cache-Control"] = "private, no-store"
    return response


# ============================================================================
# Manager / HR Ops: correct a day directly — no employee request needed
# ============================================================================

_EDIT_STATUSES = ("present", "half_day", "absent", "regularized")


def _parse_when(value):
    """ISO date-time -> naive UTC datetime (how every timestamp is stored). A value with a
    zone (…Z / +05:30) is converted; a bare value is taken as UTC, matching the API."""
    if not value or not isinstance(value, str):
        raise ValueError("missing time")
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _audit_session_times(sessions):
    return [
        {
            "session_no": session.session_no,
            "clock_in": session.clock_in.isoformat() if session.clock_in else None,
            "clock_out": session.clock_out.isoformat() if session.clock_out else None,
        }
        for session in sessions
    ]


def _local_date(dt):
    return to_company_local(dt).date()


def _manager_target(claims, actor_id, user_id):
    """Resolves who the actor may correct. Returns (user, None) or (None, error_response).
    A manager acts on their direct reports, HR Ops on anyone active; nobody corrects their
    own attendance (that would defeat the audit trail)."""
    if claims.get("role") not in APPROVER_ROLES:
        return None, (jsonify({"message": "Only a manager or HR Operations can correct attendance."}), 403)
    target = db.session.get(User, user_id) if isinstance(user_id, int) and not isinstance(user_id, bool) else None
    if not target or not target.is_active:
        return None, (jsonify({"message": "That person was not found."}), 404)
    if target.id == actor_id:
        return None, (jsonify({"message": "You cannot correct your own attendance — ask another approver."}), 403)
    if claims.get("role") == MANAGER and target.manager_id != actor_id:
        return None, (jsonify({"message": "You can only correct attendance for your own direct reports."}), 403)
    if target.role not in ROLES_WITH_CLOCK_IN_OUT:
        return None, (jsonify({"message": "Contract employees log hours via timesheets, not attendance."}), 400)
    return target, None


def _reason_and_note(payload, require=True):
    """Returns (reason_obj_or_None, note, error_response_or_None)."""
    reason = None
    reason_id = payload.get("reason_id")
    if reason_id not in (None, ""):
        if isinstance(reason_id, bool) or not isinstance(reason_id, int):
            return None, "", (jsonify({"message": "reason_id must identify an active reason."}), 400)
        reason = db.session.get(AttendanceRegularizationReason, reason_id)
        if not reason or not reason.is_active:
            return None, "", (jsonify({"message": "Please pick a valid reason."}), 400)
    note_value = payload.get("note")
    if note_value is None:
        note_value = ""
    if not isinstance(note_value, str):
        return None, "", (jsonify({"message": "note must be text."}), 400)
    note = note_value.strip()[:255]
    if require and not reason and len(note) < 3:
        return None, "", (jsonify({"message": "Please choose a reason (or write one) — it is kept on the audit trail."}), 400)
    return reason, note, None


def _parse_work_date(payload):
    try:
        work_date = datetime.strptime(payload.get("work_date", ""), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None, (jsonify({"message": "A valid work_date (YYYY-MM-DD) is required."}), 400)
    if work_date > company_today():
        return None, (jsonify({"message": "You cannot correct a future date."}), 400)
    return work_date, None


def _finalize_pending_request(record, actor_id, comment):
    """If the employee had asked for this day to be regularized, a direct correction settles it."""
    if record.regularization_status == "pending":
        record.regularization_status = "approved"
        record.regularization_reviewed_by = actor_id
        record.regularization_reviewed_at = utc_now_naive()
        record.regularization_review_comment = comment[:255]
        return True
    return False


def _company_time_as_utc(work_date, wall_time):
    local_value = datetime.combine(work_date, wall_time, tzinfo=company_timezone())
    return local_value.astimezone(timezone.utc).replace(tzinfo=None)


@bp.put("/manager/records/<int:record_id>/time")
@jwt_required()
def manager_edit_record_time(record_id):
    """Correct one punch time on an existing attendance day using company-local HH:MM."""
    claims, actor_id = get_jwt(), int(get_jwt_identity())
    record = db.session.get(Attendance, record_id)
    if not record:
        return jsonify({"message": "Attendance record was not found."}), 404
    target, err = _manager_target(claims, actor_id, record.user_id)
    if err:
        return err
    if record.work_date > company_today():
        return jsonify({"message": "You cannot correct a future date."}), 400

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Attendance correction must be provided as an object."}), 400
    field = payload.get("field")
    if field not in ("clock_in", "clock_out"):
        return jsonify({"message": "field must be clock_in or clock_out."}), 400
    raw_time = payload.get("time")
    if not isinstance(raw_time, str):
        return jsonify({"message": "time must be a valid HH:MM value."}), 400
    try:
        wall_time = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        return jsonify({"message": "time must be a valid HH:MM value."}), 400
    if wall_time.strftime("%H:%M") != raw_time:
        return jsonify({"message": "time must be a valid HH:MM value."}), 400
    reason = payload.get("reason")
    if not isinstance(reason, str) or len(reason.strip()) < 3:
        return jsonify({"message": "Enter a correction reason of at least 3 characters."}), 400
    reason = reason.strip()[:255]

    _ensure_sessions(record)
    sessions = list(record.sessions)
    before_times = _audit_session_times(sessions)
    if not sessions:
        if field == "clock_out":
            return jsonify({"message": "Add a check-in before adding a check-out."}), 400
        new_check_in = _company_time_as_utc(record.work_date, wall_time)
        if record.clock_out and record.clock_out <= new_check_in:
            return jsonify({"message": "Check-in must be earlier than the existing check-out."}), 400
        if not record.clock_out and record.work_date != company_today():
            return jsonify({"message": "A check-in can only be left open for today."}), 400
        if record.clock_out and record.clock_out - new_check_in > timedelta(hours=24):
            return jsonify({"message": "A check-in session cannot be longer than 24 hours."}), 400
        session = AttendanceSession(
            session_no=1,
            clock_in=new_check_in,
            clock_out=record.clock_out,
            clock_in_note=record.clock_in_note,
            clock_in_lat=record.clock_in_lat,
            clock_in_lng=record.clock_in_lng,
            clock_in_within_geofence=record.clock_in_within_geofence,
            clock_in_selfie=record.clock_in_selfie,
            clock_out_note=record.clock_out_note,
            clock_out_lat=record.clock_out_lat,
            clock_out_lng=record.clock_out_lng,
            clock_out_within_geofence=record.clock_out_within_geofence,
            clock_out_selfie=record.clock_out_selfie,
        )
        record.sessions.append(session)
        sessions = [session]
    else:
        selected_session = sessions[0] if field == "clock_in" else sessions[-1]
        old_value = selected_session.clock_in if field == "clock_in" else selected_session.clock_out
        if field == "clock_in":
            new_value = _company_time_as_utc(record.work_date, wall_time)
            if old_value == new_value:
                return jsonify({"message": "The check-in time is unchanged."}), 400
            selected_session.clock_in = new_value
        else:
            check_in_local = to_company_local(selected_session.clock_in)
            checkout_date = record.work_date + (
                timedelta(days=1) if wall_time <= check_in_local.timetz().replace(tzinfo=None) else timedelta()
            )
            new_value = _company_time_as_utc(checkout_date, wall_time)
            if old_value == new_value:
                return jsonify({"message": "The check-out time is unchanged."}), 400
            if selected_session.is_automatic_clock_out:
                selected_session.clock_out_note = None
            selected_session.clock_out = new_value

    for index, session in enumerate(sessions):
        if _local_date(session.clock_in) != record.work_date:
            return jsonify({"message": "Check-in must fall on the attendance date."}), 400
        if session.clock_out and session.clock_out <= session.clock_in:
            return jsonify({"message": "Check-out must be later than its check-in."}), 400
        if session.clock_out and session.clock_out - session.clock_in > timedelta(hours=24):
            return jsonify({"message": "A check-in session cannot be longer than 24 hours."}), 400
        if session.clock_out is None and (index != len(sessions) - 1 or record.work_date != company_today()):
            return jsonify({"message": "Only the final session for today can be left without a check-out."}), 400
        if index and sessions[index - 1].clock_out and session.clock_in < sessions[index - 1].clock_out:
            return jsonify({"message": "Attendance sessions cannot overlap."}), 400

    record.recompute_from_sessions()
    if (
        record.open_session()
        and not record.is_regularized
        and record.status != "regularized"
    ):
        record.status = "present"
    previous_details = json.loads(record.edit_details) if record.edit_details else {}
    audit_history = previous_details.get("history", []) if isinstance(previous_details, dict) else []
    if not isinstance(audit_history, list):
        audit_history = []
    if isinstance(previous_details, dict) and "before" in previous_details and "after" in previous_details:
        audit_history = [
            *audit_history,
            {
                "edited_by": record.edited_by,
                "edited_at": record.edited_at.isoformat() if record.edited_at else None,
                "edit_note": record.edit_note,
                "before": previous_details["before"],
                "after": previous_details["after"],
            },
        ]
    record.edit_details = json.dumps({
        "before": before_times,
        "after": _audit_session_times(record.sessions),
        "history": audit_history,
    }, separators=(",", ":"))
    record.edited_by = actor_id
    record.edited_at = utc_now_naive()
    record.edit_note = reason
    db.session.commit()

    actor = db.session.get(User, actor_id)
    send_push(
        target.id,
        "Attendance updated",
        f"{actor.full_name} corrected your attendance for {record.work_date.isoformat()}.",
        data={"type": "attendance_corrected", "record_id": record.id},
    )
    return jsonify(record.to_dict())


@bp.put("/manager/day")
@jwt_required()
def manager_edit_day():
    """Replace a person's check-in/check-out times for one day. Body:
    {user_id, work_date, sessions: [{id?, clock_in, clock_out|null, reentry_reason?}],
     status?, reason?, note?}. Existing sessions (matched by id) keep their GPS/photo
    evidence; times are what change. Every edit is stamped with who/when/why."""
    claims, actor_id = get_jwt(), int(get_jwt_identity())
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"message": "Attendance correction must be provided as an object."}), 400
    target, err = _manager_target(claims, actor_id, payload.get("user_id"))
    if err:
        return err
    work_date, err = _parse_work_date(payload)
    if err:
        return err
    custom_reason = payload.get("reason")
    if custom_reason is not None:
        if not isinstance(custom_reason, str):
            return jsonify({"message": "reason must be text."}), 400
        custom_reason = custom_reason.strip()[:255]
        if len(custom_reason) < 3:
            return jsonify({"message": "Enter a reason for the correction (at least 3 characters)."}), 400
        reason, note, err = None, payload.get("note", ""), None
        if not isinstance(note, str):
            return jsonify({"message": "note must be text."}), 400
        note = note.strip()[:255]
    else:
        reason, note, err = _reason_and_note(payload)
        if err:
            return err
        custom_reason = reason.label if reason else ""

    raw = payload.get("sessions")
    if not isinstance(raw, list):
        return jsonify({"message": "sessions must be a list."}), 400
    if len(raw) > MAX_SESSIONS_PER_DAY:
        return jsonify({"message": f"At most {MAX_SESSIONS_PER_DAY} check-ins are allowed in a day."}), 400
    status = payload.get("status")
    if status is not None and status not in _EDIT_STATUSES:
        return jsonify({"message": f"status must be one of: {', '.join(_EDIT_STATUSES)}."}), 400

    parsed = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            return jsonify({"message": f"Check-in {i} must be an object."}), 400
        session_id = item.get("id")
        if session_id is not None and (
            isinstance(session_id, bool) or not isinstance(session_id, int) or session_id < 1
        ):
            return jsonify({"message": f"Check-in {i}: session id must be a positive integer."}), 400
        checkout_value = item.get("clock_out")
        if checkout_value is not None and (
            not isinstance(checkout_value, str) or not checkout_value.strip()
        ):
            return jsonify({"message": f"Check-in {i}: check-out must be a valid date-time or null."}), 400
        try:
            cin = _parse_when(item.get("clock_in"))
            cout = _parse_when(checkout_value) if checkout_value is not None else None
        except (ValueError, AttributeError):
            return jsonify({"message": f"Check-in {i}: please give valid date-times."}), 400
        reason_value = item.get("reentry_reason")
        if reason_value is None:
            reason_value = ""
        if not isinstance(reason_value, str):
            return jsonify({"message": f"Check-in {i}: re-entry reason must be text."}), 400
        if _local_date(cin) != work_date:
            return jsonify({"message": f"Check-in {i} must fall on {work_date.isoformat()}."}), 400
        if cout and cout <= cin:
            return jsonify({"message": f"Check-in {i}: the check-out must be after the check-in."}), 400
        if cout and cout - cin > timedelta(hours=24):
            return jsonify({"message": f"Check-in {i}: a session cannot be longer than 24 hours."}), 400
        parsed.append({"id": session_id, "in": cin, "out": cout, "reason": reason_value.strip()[:MAX_REASON_LENGTH]})
    parsed.sort(key=lambda x: x["in"])
    for i, item in enumerate(parsed):
        if item["out"] is None:
            if i != len(parsed) - 1:
                return jsonify({"message": "Only the last check-in can be left open (still clocked in)."}), 400
            if work_date != company_today():
                return jsonify({"message": "A check-in can only be left open for today."}), 400
        if i and parsed[i - 1]["out"] and item["in"] < parsed[i - 1]["out"]:
            return jsonify({"message": f"Check-in {i + 1} starts before the previous check-out — sessions cannot overlap."}), 400
    if not parsed and status != "absent":
        return jsonify({"message": "Add at least one check-in, or mark the day as absent."}), 400
    if parsed and status == "absent":
        return jsonify({"message": "A day with check-ins cannot be marked absent."}), 400

    record = Attendance.query.filter_by(user_id=target.id, work_date=work_date).first()
    if not record:
        record = Attendance(user_id=target.id, work_date=work_date, status="absent")
        db.session.add(record)
        db.session.flush()
    was_legacy_record = not record.sessions and record.clock_in is not None
    _ensure_sessions(record)

    existing = {s.id: s for s in record.sessions}
    if was_legacy_record and len(parsed) == 1 and parsed[0]["id"] is None:
        parsed[0]["id"] = record.sessions[0].id
    before_times = _audit_session_times(record.sessions)
    keep_ids = {item["id"] for item in parsed if item["id"] in existing}
    if any(item["id"] is not None and item["id"] not in existing for item in parsed):
        return jsonify({"message": "One of the sessions does not belong to this day."}), 400
    if len(keep_ids) != len([i for i in parsed if i["id"] is not None]):
        return jsonify({"message": "A session was listed twice."}), 400

    # Delete removed sessions first, then park the survivors on temporary numbers so the
    # (attendance_id, session_no) unique key never collides while we renumber.
    for s in list(record.sessions):
        if s.id not in keep_ids:
            record.sessions.remove(s)
    db.session.flush()
    for s in record.sessions:
        s.session_no = -s.id
    db.session.flush()

    for n, item in enumerate(parsed, 1):
        sess = existing.get(item["id"]) if item["id"] in keep_ids else None
        if sess is None:
            sess = AttendanceSession(clock_in=item["in"], session_no=n)
            record.sessions.append(sess)
        if sess.is_automatic_clock_out and item["out"] != sess.clock_out:
            sess.clock_out_note = None
        sess.clock_in, sess.clock_out, sess.session_no = item["in"], item["out"], n
        if n > 1:
            sess.reentry_reason = item["reason"] or sess.reentry_reason or "Added by manager"
        else:
            sess.reentry_reason = None
    db.session.flush()

    if parsed:
        record.recompute_from_sessions()
    else:
        record.clock_in = record.clock_out = None
        record.clock_in_note = record.clock_out_note = None
        record.clock_in_lat = record.clock_in_lng = record.clock_in_within_geofence = None
        record.clock_out_lat = record.clock_out_lng = record.clock_out_within_geofence = None
        record.clock_in_selfie = record.clock_out_selfie = None
        record.total_hours = 0

    previous_details = json.loads(record.edit_details) if record.edit_details else {}
    audit_history = previous_details.get("history", []) if isinstance(previous_details, dict) else []
    if not isinstance(audit_history, list):
        audit_history = []
    if isinstance(previous_details, dict) and "before" in previous_details and "after" in previous_details:
        audit_history = [
            *audit_history,
            {
                "edited_by": record.edited_by,
                "edited_at": record.edited_at.isoformat() if record.edited_at else None,
                "edit_note": record.edit_note,
                "before": previous_details["before"],
                "after": previous_details["after"],
            },
        ]
    record.edit_details = json.dumps(
        {
            "before": before_times,
            "after": _audit_session_times(record.sessions),
            "history": audit_history,
        },
        separators=(",", ":"),
    )

    # Status: the manager's explicit choice wins; otherwise keep a regularization, else judge by hours.
    if status:
        record.status = status
        record.is_regularized = status == "regularized"
    elif not record.is_regularized and parsed:
        still_open = any(x["out"] is None for x in parsed)
        record.status = "present" if (still_open or (record.total_hours or 0) >= 4) else "half_day"
    audit = f"{custom_reason}: {note}" if (custom_reason and note) else (custom_reason or note)
    record.edited_by, record.edited_at, record.edit_note = actor_id, utc_now_naive(), audit[:255]
    settled = _finalize_pending_request(record, actor_id, f"Resolved by direct correction — {audit}")
    db.session.commit()

    actor = db.session.get(User, actor_id)
    send_push(target.id, "Attendance updated",
              f"{actor.full_name} corrected your attendance for {work_date.isoformat()}.",
              data={"type": "attendance_corrected", "record_id": record.id})
    out = record.to_dict()
    out["request_settled"] = settled
    return jsonify(out)


@bp.post("/manager/regularize")
@jwt_required()
def manager_regularize_day():
    """Regularize a day directly by picking one of the defined reasons — no request from the
    employee needed. For a day with no check-ins, optional clock_in/clock_out set the times
    that are being excused. Body: {user_id, work_date, reason_id, note?, clock_in?, clock_out?}."""
    claims, actor_id = get_jwt(), int(get_jwt_identity())
    payload = request.get_json(silent=True) or {}
    target, err = _manager_target(claims, actor_id, payload.get("user_id"))
    if err:
        return err
    work_date, err = _parse_work_date(payload)
    if err:
        return err
    if not payload.get("reason_id"):
        return jsonify({"message": "Please pick a reason."}), 400
    reason, note, err = _reason_and_note(payload)
    if err:
        return err

    record = Attendance.query.filter_by(user_id=target.id, work_date=work_date).first()
    if record and record.is_regularized:
        return jsonify({"message": "This day has already been regularized."}), 400
    if not record:
        record = Attendance(user_id=target.id, work_date=work_date, status="absent")
        db.session.add(record)
        db.session.flush()

    if payload.get("clock_in"):
        _ensure_sessions(record)
        if record.sessions:
            return jsonify({"message": "This day already has check-ins — use Edit times to change them."}), 400
        try:
            cin = _parse_when(payload["clock_in"])
            cout = _parse_when(payload["clock_out"]) if payload.get("clock_out") else None
        except (ValueError, AttributeError):
            return jsonify({"message": "Please give valid check-in / check-out times."}), 400
        if _local_date(cin) != work_date:
            return jsonify({"message": f"The check-in must fall on {work_date.isoformat()}."}), 400
        if cout is not None and cout <= cin:
            return jsonify({"message": "The check-out must be after the check-in."}), 400
        record.sessions.append(AttendanceSession(session_no=1, clock_in=cin, clock_out=cout))
        db.session.flush()
        record.recompute_from_sessions()

    record.is_regularized = True
    record.status = "regularized"
    record.regularization_status = "approved"
    record.regularization_reason_id = reason.id
    record.regularization_note = note
    record.regularization_requested_at = record.regularization_requested_at or utc_now_naive()
    record.regularization_reviewed_by = actor_id
    record.regularization_reviewed_at = utc_now_naive()
    record.regularization_review_comment = "Regularized directly by the manager."
    record.edited_by, record.edited_at, record.edit_note = actor_id, utc_now_naive(), f"Regularized: {reason.label}"[:255]
    db.session.commit()

    send_push(target.id, "Attendance regularized",
              f"Your attendance for {work_date.isoformat()} was regularized ({reason.label}).",
              data={"type": "regularization_approved", "record_id": record.id})
    return jsonify(record.to_dict()), 201


# ============================================================================
# Office-only punching — a manager can require a person to clock in/out from the office
# ============================================================================

@bp.put("/team/<int:user_id>/office-restriction")
@jwt_required()
def set_office_restriction(user_id):
    """Body: {restricted: bool}. A manager sets it for their direct reports, HR Operations / Super
    Admin for anyone active. Nobody can change their own. The person is told by push."""
    claims, actor_id = get_jwt(), int(get_jwt_identity())
    target, err = _manager_target(claims, actor_id, user_id)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload.get("restricted"), bool):
        return jsonify({"message": "restricted (true/false) is required."}), 400
    target.restrict_to_office = payload["restricted"]
    target.restrict_set_by, target.restrict_set_at = actor_id, utc_now_naive()
    db.session.commit()
    actor = db.session.get(User, actor_id)
    send_push(target.id, "Clock-in rule changed",
              (f"{actor.full_name} now requires you to clock in and out from the office." if target.restrict_to_office
               else f"{actor.full_name} removed the office-only rule for clock in/out."),
              data={"type": "office_restriction", "restricted": target.restrict_to_office})
    return jsonify({"user": target.to_dict(), "no_active_office": not OfficeLocation.query.filter_by(is_active=True).first()})
