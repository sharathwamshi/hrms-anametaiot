from app.models import EmployeePermission


def has_permission(user_id, permission_key):
    return EmployeePermission.query.filter_by(
        user_id=user_id, permission_key=permission_key
    ).first() is not None


def role_or_permission_required(*roles, permission_key):
    """Like roles_required, but also lets through anyone individually
    granted the given permission — additive, never removes access from
    the roles that already had it."""
    from functools import wraps
    from flask import jsonify
    from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            role = claims.get("role")
            if role in roles:
                return fn(*args, **kwargs)
            actor_id = int(get_jwt_identity())
            if has_permission(actor_id, permission_key):
                return fn(*args, **kwargs)
            return jsonify({"message": "You do not have permission to perform this action."}), 403
        return wrapper
    return decorator
