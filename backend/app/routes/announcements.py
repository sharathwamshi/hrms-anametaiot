from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models import Announcement, Department, User
from app.roles import ALL_ROLES, EMPLOYEE, ROLE_LABELS
from app.utils.official_announcements import (
    announcement_status,
    audience_applies,
    announcement_audiences as get_announcement_audiences,
    birthday_announcements,
    displaced_no_expiry_announcement_ids,
    now_ist,
    serialize_announcement,
    sort_announcements_by_publication,
    utc_naive,
    validate_payload,
)


bp = Blueprint("official_announcements", __name__, url_prefix="/api/announcements")


def _current_user():
    return db.session.get(User, int(get_jwt_identity()))


def _management_denied(user):
    if user is None:
        return jsonify({"message": "User not found."}), 404
    if user.role == EMPLOYEE:
        return jsonify({"message": "Employees can view announcements but cannot manage them."}), 403
    return None


@bp.get("")
@jwt_required()
def list_announcements():
    user = _current_user()
    if user is None:
        return jsonify({"message": "User not found."}), 404
    scope = request.args.get("scope", "visible")
    status_filter = request.args.get("status", "all" if scope == "manage" else "active")
    if status_filter not in {"all", "active", "scheduled", "expired", "history"}:
        return jsonify({"message": "Select a valid announcement status."}), 400

    current = utc_naive(now_ist())
    query = Announcement.query.filter(Announcement.deleted_at.is_(None))
    if scope == "manage":
        denied = _management_denied(user)
        if denied:
            return denied
    elif scope == "visible":
        query = query.filter(
            db.or_(Announcement.publish_at <= current, Announcement.publish_at.is_(None))
        )
        if status_filter == "active":
            query = query.filter(
                db.or_(Announcement.expires_at > current, Announcement.expires_at.is_(None))
            )
        elif status_filter == "expired":
            query = query.filter(Announcement.expires_at <= current)
        elif status_filter == "scheduled":
            query = query.filter(db.false())
    else:
        return jsonify({"message": "Select a valid announcement scope."}), 400

    rows = query.order_by(Announcement.publish_at.desc(), Announcement.id.desc()).all()
    displaced_ids = displaced_no_expiry_announcement_ids(
        user if scope == "visible" else None,
        current,
    )
    announcements = []
    for row in rows:
        status = announcement_status(row, current)
        if status == "active" and row.id in displaced_ids:
            status = "history"
        if scope == "visible":
            if not audience_applies(get_announcement_audiences(row), user):
                continue
            if status_filter == "history":
                if status not in {"expired", "history"}:
                    continue
            elif status_filter != "all" and status != status_filter:
                continue
        if scope == "manage" and status_filter != "all":
            if status_filter == "history":
                if status not in {"expired", "history"}:
                    continue
            elif status != status_filter:
                continue
        announcements.append(serialize_announcement(row, status))
    if status_filter in {"all", "active"}:
        announcements.extend(birthday_announcements())
    return jsonify(sort_announcements_by_publication(announcements))


@bp.get("/audiences")
@jwt_required()
def announcement_audiences():
    user = _current_user()
    denied = _management_denied(user)
    if denied:
        return denied
    active_users = User.query.filter(
        User.is_active.is_(True),
        User.employment_status != "left",
    ).order_by(User.full_name.asc(), User.id.asc()).all()
    departments = Department.query.order_by(Department.name.asc(), Department.id.asc()).all()
    return jsonify({
        "roles": [{"value": role, "label": ROLE_LABELS.get(role, role)} for role in ALL_ROLES],
        "departments": [{"id": department.id, "name": department.name} for department in departments],
        "users": [{
            "id": person.id,
            "full_name": person.full_name,
            "role": person.role,
            "role_label": ROLE_LABELS.get(person.role, person.role),
            "designation": person.designation,
            "department": person.department.name if person.department else None,
            "department_id": person.department_id,
            "avatar_url": person.avatar_url,
        } for person in active_users],
    })


@bp.post("")
@jwt_required()
def create_announcement():
    user = _current_user()
    denied = _management_denied(user)
    if denied:
        return denied
    try:
        values = validate_payload(request.get_json(silent=True))
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    announcement = Announcement(
        title=values["title"],
        body=values["message"],
        category=values["category"],
        priority=values["priority"],
        audiences=values["audiences"],
        publish_at=values["publish_at"],
        expires_at=values["expires_at"],
        posted_by=user.id,
    )
    db.session.add(announcement)
    db.session.commit()
    return jsonify(serialize_announcement(announcement)), 201


@bp.put("/<int:announcement_id>")
@jwt_required()
def update_announcement(announcement_id):
    user = _current_user()
    denied = _management_denied(user)
    if denied:
        return denied
    announcement = Announcement.query.filter_by(
        id=announcement_id,
        deleted_at=None,
    ).first()
    if announcement is None:
        return jsonify({"message": "Announcement not found."}), 404
    try:
        values = validate_payload(request.get_json(silent=True))
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    announcement.title = values["title"]
    announcement.body = values["message"]
    announcement.category = values["category"]
    announcement.priority = values["priority"]
    announcement.audiences = values["audiences"]
    announcement.audience_role = None
    announcement.publish_at = values["publish_at"]
    announcement.expires_at = values["expires_at"]
    announcement.updated_by = user.id
    announcement.updated_at = utc_naive(now_ist())
    db.session.commit()
    return jsonify(serialize_announcement(announcement))


@bp.delete("/<int:announcement_id>")
@jwt_required()
def delete_announcement(announcement_id):
    user = _current_user()
    denied = _management_denied(user)
    if denied:
        return denied
    announcement = Announcement.query.filter_by(
        id=announcement_id,
        deleted_at=None,
    ).first()
    if announcement is None:
        return jsonify({"message": "Announcement not found."}), 404
    announcement.deleted_at = utc_naive(now_ist())
    announcement.updated_by = user.id
    db.session.commit()
    return jsonify({"message": "Announcement archived."})
