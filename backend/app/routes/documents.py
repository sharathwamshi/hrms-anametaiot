import os
import uuid
from datetime import datetime

from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import EmployeeDocument, User
from app.models.documents import DOC_TYPES
from app.roles import HR_OPERATIONS, MANAGER, SUPER_ADMIN

bp = Blueprint("documents", __name__, url_prefix="/api/documents")

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
HR_ROLES = (HR_OPERATIONS, SUPER_ADMIN)


def _can_access_document(user_id):
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if user_id == actor_id or role in HR_ROLES:
        return True
    target = db.session.get(User, user_id)
    return role == MANAGER and target is not None and target.manager_id == actor_id


def _is_manager_upload_allowed(target_user_id, role, actor_id):
    if role in HR_ROLES:
        return True
    target = db.session.get(User, target_user_id)
    return role == MANAGER and target is not None and target.manager_id == actor_id


def _can_review_document(document):
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role in HR_ROLES:
        return True
    employee = db.session.get(User, document.user_id)
    return (
        role == MANAGER
        and employee is not None
        and employee.manager_id == actor_id
        and employee.role != SUPER_ADMIN
    )


def _safe_file_bytes(file, extension):
    limit = current_app.config["MAX_EMPLOYEE_DOCUMENT_BYTES"]
    content = file.stream.read(limit + 1)
    file.stream.seek(0)
    if not content:
        raise ValueError("The selected file is empty.")
    if len(content) > limit:
        raise ValueError(f"Files must be {limit // (1024 * 1024)} MB or smaller.")
    signatures = {
        ".pdf": content.startswith(b"%PDF-"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".doc": content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")),
        ".docx": content.startswith(b"PK\x03\x04"),
    }
    if not signatures[extension]:
        raise ValueError("The file contents do not match the selected file type.")
    return content


@bp.get("")
@jwt_required()
def list_documents():
    """Employees see their own documents; managers see direct reports; HR sees all."""
    actor_id = int(get_jwt_identity())
    target_user_id = request.args.get("user_id", type=int) or actor_id
    if not _can_access_document(target_user_id):
        return jsonify({"message": "You do not have permission to view these documents."}), 403
    rows = EmployeeDocument.query.filter_by(user_id=target_user_id).order_by(
        EmployeeDocument.uploaded_at.desc(), EmployeeDocument.id.desc()
    ).all()
    return jsonify([document.to_dict() for document in rows])


@bp.post("")
@jwt_required()
def upload_document():
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    target_user_id = request.form.get("user_id", type=int) or actor_id
    if target_user_id != actor_id and not _is_manager_upload_allowed(target_user_id, role, actor_id):
        return jsonify({"message": "You do not have permission to upload documents for this employee."}), 403
    if not db.session.get(User, target_user_id):
        return jsonify({"message": "Employee not found."}), 404

    doc_type = request.form.get("doc_type")
    if doc_type not in DOC_TYPES:
        return jsonify({"message": f"doc_type must be one of {DOC_TYPES}"}), 400
    if "file" not in request.files or not request.files["file"].filename:
        return jsonify({"message": "A file is required."}), 400

    file = request.files["file"]
    original_filename = secure_filename(file.filename)
    extension = os.path.splitext(original_filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({"message": "Allowed file types are PDF, JPG, PNG, DOC, and DOCX."}), 400
    try:
        content = _safe_file_bytes(file, extension)
        title = (request.form.get("title") or original_filename).strip()
        if not title or len(title) > 150:
            raise ValueError("Document title is required and must be 150 characters or fewer.")
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    storage_key = f"{target_user_id}/{uuid.uuid4().hex}{extension}"
    document_folder = current_app.config["EMPLOYEE_DOCUMENT_FOLDER"]
    absolute_path = os.path.join(document_folder, *storage_key.split("/"))
    try:
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        with open(absolute_path, "wb") as saved_file:
            saved_file.write(content)
    except OSError:
        current_app.logger.exception("Employee document file could not be stored.")
        return jsonify({"message": "Could not store this document. Please try again."}), 500

    document = EmployeeDocument(
        user_id=target_user_id,
        doc_type=doc_type,
        title=title,
        file_path="private",
        original_filename=original_filename,
        storage_key=storage_key,
        mime_type=MIME_TYPES[extension],
        file_size=len(content),
        uploaded_by=actor_id,
        verification_status="pending",
    )
    db.session.add(document)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        try:
            os.remove(absolute_path)
        except OSError:
            current_app.logger.exception("Could not remove an unrecorded employee document upload.")
        current_app.logger.exception("Employee document metadata could not be saved.")
        return jsonify({"message": "Could not save this document. Please try again."}), 500
    return jsonify(document.to_dict()), 201


@bp.get("/<int:doc_id>/download")
@jwt_required()
def download_document(doc_id):
    document = EmployeeDocument.query.get_or_404(doc_id)
    if not _can_access_document(document.user_id):
        return jsonify({"message": "You do not have permission to access this document."}), 403

    if document.storage_key:
        folder = current_app.config["EMPLOYEE_DOCUMENT_FOLDER"]
        if ".." in document.storage_key.split("/") or os.path.isabs(document.storage_key):
            return jsonify({"message": "This document file is unavailable."}), 404
        return send_from_directory(
            folder,
            document.storage_key,
            mimetype=document.mime_type,
            as_attachment=False,
            download_name=document.original_filename or document.title,
        )

    legacy_prefix = "/static/uploads/"
    if not document.file_path.startswith(legacy_prefix):
        return jsonify({"message": "This document file is unavailable."}), 404
    relative_path = document.file_path[len(legacy_prefix):].replace("\\", "/")
    if not relative_path.startswith("documents/") or ".." in relative_path.split("/"):
        return jsonify({"message": "This document file is unavailable."}), 404
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        relative_path,
        as_attachment=False,
        download_name=document.original_filename or document.title,
    )


@bp.patch("/<int:doc_id>/verification")
@jwt_required()
def verify_document(doc_id):
    document = EmployeeDocument.query.get_or_404(doc_id)
    if not _can_review_document(document):
        return jsonify({"message": "Only HR Operations, Super Admin, or the employee's direct manager can verify documents."}), 403
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - {"status", "note"} or payload.get("status") not in {"pending", "verified", "rejected"}:
        return jsonify({"message": "Provide a verification status of pending, verified, or rejected."}), 400
    note = payload.get("note")
    if note is not None and (not isinstance(note, str) or len(note.strip()) > 500):
        return jsonify({"message": "Verification note must be 500 characters or fewer."}), 400
    document.verification_status = payload["status"]
    if note is not None:
        document.verification_note = note.strip() or None
    document.verified_by = int(get_jwt_identity()) if payload["status"] != "pending" else None
    document.verified_at = datetime.utcnow() if payload["status"] != "pending" else None
    db.session.commit()
    return jsonify(document.to_dict())


@bp.delete("/<int:doc_id>")
@jwt_required()
def delete_document(doc_id):
    document = EmployeeDocument.query.get_or_404(doc_id)
    if not _can_access_document(document.user_id):
        return jsonify({"message": "You do not have permission to remove this document."}), 403
    storage_key = document.storage_key
    legacy_path = None
    if not storage_key and document.file_path.startswith("/static/uploads/documents/"):
        legacy_path = document.file_path[len("/static/uploads/"):].replace("\\", "/")
        if ".." in legacy_path.split("/"):
            return jsonify({"message": "Document storage path is invalid."}), 500
    db.session.delete(document)
    db.session.commit()
    file_path = None
    if storage_key:
        if ".." in storage_key.split("/") or os.path.isabs(storage_key):
            return jsonify({"message": "Document storage path is invalid."}), 500
        file_path = os.path.join(current_app.config["EMPLOYEE_DOCUMENT_FOLDER"], *storage_key.split("/"))
    elif legacy_path:
        file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], legacy_path)
    if file_path and os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError:
            current_app.logger.exception("Employee document record was removed, but its file could not be deleted.")
            return jsonify({"message": "Document record was removed, but its stored file could not be deleted."}), 500
    return jsonify({"message": "Document removed."})
