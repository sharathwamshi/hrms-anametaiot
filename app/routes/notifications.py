import re
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from app.extensions import db
from app.models import AttendanceNotificationSettings, DeviceToken
from app.roles import MANAGER, SUPER_ADMIN

bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")
_NOTIFICATION_ADMIN_ROLES = (MANAGER, SUPER_ADMIN)
_BOOLEAN_SETTINGS = (
    "regularization_enabled",
    "leave_enabled",
    "attendance_updates_enabled",
    "business_alerts_enabled",
    "clock_in_reminder_enabled",
    "manager_missing_alert_enabled",
    "clock_out_reminder_enabled",
)
_TIME_SETTINGS = (
    "clock_in_reminder_time",
    "manager_missing_alert_time",
    "clock_out_reminder_time",
)


def _notification_settings_for_update():
    settings = AttendanceNotificationSettings.query.filter_by(id=1).first()
    if settings is None:
        settings = AttendanceNotificationSettings(id=1)
        db.session.add(settings)
        db.session.flush()
    return settings


def _notification_admin_required():
    if get_jwt().get("role") not in _NOTIFICATION_ADMIN_ROLES:
        return jsonify({"message": "Only a Manager or Super Admin can manage notification settings."}), 403
    return None


@bp.get("/settings")
@jwt_required()
def get_notification_settings():
    blocked = _notification_admin_required()
    if blocked:
        return blocked
    settings = _notification_settings_for_update()
    db.session.commit()
    return jsonify(settings.to_dict())


@bp.put("/settings")
@jwt_required()
def update_notification_settings():
    blocked = _notification_admin_required()
    if blocked:
        return blocked

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        return jsonify({"message": "Provide at least one notification setting to update."}), 400
    allowed_fields = set(_BOOLEAN_SETTINGS + _TIME_SETTINGS)
    unknown_fields = set(payload) - allowed_fields
    if unknown_fields:
        return jsonify({"message": "Unknown notification setting.", "fields": sorted(unknown_fields)}), 400

    parsed_times = {}
    for field in _BOOLEAN_SETTINGS:
        if field in payload and not isinstance(payload[field], bool):
            return jsonify({"message": f"{field} must be true or false."}), 400
    for field in _TIME_SETTINGS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            return jsonify({"message": f"{field} must use 24-hour HH:MM format."}), 400
        parsed_times[field] = datetime.strptime(value, "%H:%M").time()

    settings = _notification_settings_for_update()
    for field in _BOOLEAN_SETTINGS:
        if field in payload:
            setattr(settings, field, payload[field])
    for field, value in parsed_times.items():
        setattr(settings, field, value)
    settings.updated_by = int(get_jwt_identity())
    db.session.commit()
    return jsonify(settings.to_dict())


@bp.post("/register-device")
@jwt_required()
def register_device():
    """The mobile app calls this once it has an Expo push token, so the
    backend knows where to send clock-in/out reminders and status pushes."""
    user_id = int(get_jwt_identity())
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return jsonify({"message": "A push token is required."}), 400

    existing = DeviceToken.query.filter_by(token=token).first()
    if existing:
        # The same physical device can switch accounts (e.g. a shared
        # handset) — re-point the existing row rather than erroring.
        existing.user_id = user_id
        existing.platform = payload.get("platform")
        existing.last_seen_at = datetime.utcnow()
    else:
        db.session.add(DeviceToken(user_id=user_id, token=token, platform=payload.get("platform")))
    db.session.commit()
    return jsonify({"message": "Registered."}), 201


@bp.post("/unregister-device")
@jwt_required()
def unregister_device():
    """Called on logout so a shared/reset device stops getting this person's pushes."""
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if token:
        DeviceToken.query.filter_by(token=token, user_id=int(get_jwt_identity())).delete()
        db.session.commit()
    return jsonify({"message": "Unregistered."})
