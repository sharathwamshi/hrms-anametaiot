from datetime import date
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import Announcement, Asset
from app.utils.security import roles_required
from app.roles import HR_OPERATIONS, OPERATIONS, SUPER_ADMIN

bp = Blueprint("misc", __name__, url_prefix="/api")


@bp.get("/announcements")
@jwt_required()
def list_announcements():
    claims = get_jwt()
    role = claims.get("role")
    rows = Announcement.query.filter(
        db.or_(Announcement.audience_role.is_(None), Announcement.audience_role == role)
    ).order_by(Announcement.created_at.desc()).all()
    return jsonify([a.to_dict() for a in rows])


@bp.post("/announcements")
@roles_required(HR_OPERATIONS)
def create_announcement():
    payload = request.get_json(silent=True) or {}
    if not payload.get("title") or not payload.get("body"):
        return jsonify({"message": "title and body are required."}), 400

    announcement = Announcement(
        title=payload["title"],
        body=payload["body"],
        audience_role=payload.get("audience_role"),
        posted_by=int(get_jwt_identity()),
    )
    db.session.add(announcement)
    db.session.commit()
    return jsonify(announcement.to_dict()), 201


@bp.get("/assets")
@roles_required(HR_OPERATIONS, OPERATIONS, SUPER_ADMIN)
def list_assets():
    rows = Asset.query.order_by(Asset.asset_tag).all()
    return jsonify([a.to_dict() for a in rows])


@bp.post("/assets")
@roles_required(HR_OPERATIONS, OPERATIONS, SUPER_ADMIN)
def create_asset():
    payload = request.get_json(silent=True) or {}
    if not payload.get("asset_tag"):
        return jsonify({"message": "asset_tag is required."}), 400
    if Asset.query.filter_by(asset_tag=payload["asset_tag"]).first():
        return jsonify({"message": "Asset tag already exists."}), 409

    asset = Asset(
        asset_tag=payload["asset_tag"],
        category=payload.get("category"),
        description=payload.get("description"),
        status="available",
    )
    db.session.add(asset)
    db.session.commit()
    return jsonify(asset.to_dict()), 201


@bp.post("/assets/<int:asset_id>/assign")
@roles_required(HR_OPERATIONS, OPERATIONS, SUPER_ADMIN)
def assign_asset(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    payload = request.get_json(silent=True) or {}
    asset.assigned_to = payload.get("user_id")
    asset.assigned_on = date.today()
    asset.returned_on = None
    asset.status = "assigned"
    db.session.commit()
    return jsonify(asset.to_dict())


@bp.post("/assets/<int:asset_id>/return")
@roles_required(HR_OPERATIONS, OPERATIONS, SUPER_ADMIN)
def return_asset(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    asset.returned_on = date.today()
    asset.status = "returned"
    db.session.commit()
    return jsonify(asset.to_dict())
