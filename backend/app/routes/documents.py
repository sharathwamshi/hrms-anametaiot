import os
import uuid

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import EmployeeDocument
from app.models.documents import DOC_TYPES
from app.roles import HR_OPERATIONS, MANAGER
from app.models import User

bp = Blueprint("documents", __name__, url_prefix="/api/documents")


@bp.get("")
@jwt_required()
def list_documents():
    """Everyone sees their own documents. HR Operations can look up anyone's;
    a Manager can look up their own direct reports' (e.g. while onboarding)."""
    actor_id = int(get_jwt_identity())
    claims = get_jwt()
    target_user_id = request.args.get("user_id", type=int) or actor_id

    if target_user_id != actor_id:
        if claims.get("role") in (HR_OPERATIONS, "super_admin"):
            pass
        elif claims.get("role") == MANAGER:
            target = User.query.get_or_404(target_user_id)
            if target.manager_id != actor_id:
                return jsonify({"message": "You can only view documents for your own direct reports."}), 403
        else:
            return jsonify({"message": "You do not have permission to view these documents."}), 403

    rows = EmployeeDocument.query.filter_by(user_id=target_user_id).order_by(EmployeeDocument.uploaded_at.desc()).all()
    return jsonify([d.to_dict() for d in rows])


@bp.post("")
@jwt_required()
def upload_document():
    actor_id = int(get_jwt_identity())
    doc_type = request.form.get("doc_type")
    if doc_type not in DOC_TYPES:
        return jsonify({"message": f"doc_type must be one of {DOC_TYPES}"}), 400
    if "file" not in request.files or not request.files["file"].filename:
        return jsonify({"message": "A file is required."}), 400

    file = request.files["file"]
    safe_name = secure_filename(f"{uuid.uuid4().hex[:10]}_{file.filename}")
    rel_path = os.path.join("documents", str(actor_id), safe_name)
    abs_path = os.path.join(current_app.config["UPLOAD_FOLDER"], rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    file.save(abs_path)

    doc = EmployeeDocument(
        user_id=actor_id,
        doc_type=doc_type,
        title=request.form.get("title") or file.filename,
        file_path=f"/static/uploads/{rel_path}",
    )
    db.session.add(doc)
    db.session.commit()
    return jsonify(doc.to_dict()), 201


@bp.delete("/<int:doc_id>")
@jwt_required()
def delete_document(doc_id):
    doc = EmployeeDocument.query.get_or_404(doc_id)
    actor_id = int(get_jwt_identity())
    claims = get_jwt()
    if doc.user_id != actor_id and claims.get("role") != HR_OPERATIONS:
        return jsonify({"message": "You can only remove your own documents."}), 403

    db.session.delete(doc)
    db.session.commit()
    return jsonify({"message": "Document removed."})
