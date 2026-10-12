from datetime import date
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import User
from app.roles import ROLE_LABELS, ROLES_WITH_CLOCK_IN_OUT

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        return jsonify({"message": "Email and password are required."}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"message": "Invalid email or password."}), 401
    if not user.is_active:
        return jsonify({"message": "This account has been deactivated. Contact HR Operations."}), 403

    claims = {"role": user.role, "name": user.full_name, "employee_code": user.employee_code}
    token = create_access_token(identity=str(user.id), additional_claims=claims)
    # The refresh token is what lets the mobile app stay signed in across days
    # without asking for a password again — it's long-lived (30 days) and only
    # good for getting a new access token at /auth/refresh, nothing else.
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims=claims)

    return jsonify(
        {
            "access_token": token,
            "refresh_token": refresh_token,
            "user": user.to_dict(),
            "role_label": ROLE_LABELS.get(user.role, user.role),
            "has_clock_in_out": user.role in ROLES_WITH_CLOCK_IN_OUT,
        }
    )


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    """Mobile app calls this with the refresh token when an access token
    expires, instead of asking the person to log in again. Re-checks
    is_active so a deactivated account can't refresh its way back in."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not user.is_active:
        return jsonify({"message": "This account is no longer active."}), 403
    claims = {"role": user.role, "name": user.full_name, "employee_code": user.employee_code}
    token = create_access_token(identity=str(user.id), additional_claims=claims)
    return jsonify({"access_token": token})


@bp.get("/me")
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    claims = get_jwt()
    return jsonify(
        {
            "user": user.to_dict(),
            "role_label": ROLE_LABELS.get(user.role, user.role),
            "has_clock_in_out": user.role in ROLES_WITH_CLOCK_IN_OUT,
        }
    )


@bp.post("/change-password")
@jwt_required()
def change_password():
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    payload = request.get_json(silent=True) or {}
    current_password = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""

    if not user.check_password(current_password):
        return jsonify({"message": "Current password is incorrect."}), 400
    if len(new_password) < 8:
        return jsonify({"message": "New password must be at least 8 characters."}), 400

    user.set_password(new_password)
    db.session.commit()
    return jsonify({"message": "Password updated successfully."})
