from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models import DeviceToken
from datetime import datetime

bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


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
