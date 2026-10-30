import os
import uuid
from datetime import date, datetime, timedelta

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import InsuranceDocument, InsurancePolicy, InsuranceReminder, User
from app.roles import INSURANCE_MANAGEMENT_ROLES
from app.utils.push import send_push
from app.utils.security import roles_required

bp = Blueprint("insurance", __name__, url_prefix="/api/insurance")

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
DOCUMENT_TYPES = {"policy", "certificate", "insurance_card", "claim_form", "supporting", "other"}


def _actor_id():
    return int(get_jwt_identity())


def _parse_date(value, field):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD format.") from exc
    return parsed


def _authorized_policy(policy_id, management=False):
    policy = InsurancePolicy.query.get_or_404(policy_id)
    if management and get_jwt().get("role") not in INSURANCE_MANAGEMENT_ROLES:
        return None, (jsonify({"message": "You do not have insurance management permission."}), 403)
    if not management and _actor_id() != policy.employee_id and get_jwt().get("role") not in INSURANCE_MANAGEMENT_ROLES:
        return None, (jsonify({"message": "You do not have permission to access this insurance record."}), 403)
    return policy, None


def _validate_payload(payload, partial=False):
    required = {"employee_id", "insurance_type", "provider_name", "policy_number", "policy_start_date", "policy_expiry_date"}
    if not partial and not required.issubset(payload):
        raise ValueError("employee_id, insurance_type, provider_name, policy_number, policy_start_date, and policy_expiry_date are required.")
    if "insurance_type" in payload and payload["insurance_type"] not in {"health", "life", "accident", "dental", "vision", "travel", "other"}:
        raise ValueError("Unsupported insurance type.")
    values = {}
    for field in ("employee_id", "insurance_type", "provider_name", "policy_number", "member_id",
                  "certificate_number", "coverage_description", "notes", "contact_name",
                  "contact_email", "contact_phone"):
        if field in payload:
            value = payload[field]
            if value is not None and not isinstance(value, (str, int)):
                raise ValueError(f"{field} must be text.")
            if isinstance(value, str) and len(value) > 2000:
                raise ValueError(f"{field} is too long.")
            values[field] = value.strip() if isinstance(value, str) else value
    if "credentials" in payload:
        if not isinstance(payload["credentials"], dict):
            raise ValueError("credentials must be an object.")
        values["credentials"] = payload["credentials"]
    if "coverage_amount" in payload:
        try:
            amount = float(payload["coverage_amount"]) if payload["coverage_amount"] not in (None, "") else None
        except (TypeError, ValueError) as exc:
            raise ValueError("coverage_amount must be numeric.") from exc
        if amount is not None and amount < 0:
            raise ValueError("coverage_amount cannot be negative.")
        values["coverage_amount"] = amount
    for field in ("policy_start_date", "policy_expiry_date"):
        if field in payload:
            values[field] = _parse_date(payload[field], field)
    if "policy_start_date" in values and "policy_expiry_date" in values and values["policy_expiry_date"] < values["policy_start_date"]:
        raise ValueError("Policy expiry date cannot be before the start date.")
    return values


@bp.get("")
@jwt_required()
def list_policies():
    role = get_jwt().get("role")
    query = InsurancePolicy.query
    if role not in INSURANCE_MANAGEMENT_ROLES:
        query = query.filter_by(employee_id=_actor_id())
    employee_id = request.args.get("employee_id", type=int)
    insurance_type = request.args.get("insurance_type")
    provider = request.args.get("provider", "").strip()
    status = request.args.get("status")
    if employee_id:
        query = query.filter_by(employee_id=employee_id)
    if insurance_type:
        query = query.filter_by(insurance_type=insurance_type)
    if provider:
        query = query.filter(InsurancePolicy.provider_name.ilike(f"%{provider}%"))
    policies = query.order_by(InsurancePolicy.policy_expiry_date.asc(), InsurancePolicy.id.desc()).all()
    if status:
        policies = [p for p in policies if p.expiry_status == status]
    return jsonify([p.to_dict(include_internal=role in INSURANCE_MANAGEMENT_ROLES) for p in policies])


@bp.get("/summary")
@roles_required(*INSURANCE_MANAGEMENT_ROLES)
def insurance_summary():
    policies = InsurancePolicy.query.filter_by(status="active").all()
    return jsonify({
        "total": InsurancePolicy.query.count(),
        "active": sum(p.expiry_status == "active" for p in policies),
        "expiring_soon": sum(p.expiry_status == "expiring_soon" for p in policies),
        "expired": sum(p.expiry_status == "expired" for p in policies),
    })


@bp.post("")
@roles_required(*INSURANCE_MANAGEMENT_ROLES)
def create_policy():
    payload = request.get_json(silent=True) or {}
    try:
        values = _validate_payload(payload)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    employee = User.query.get(values["employee_id"])
    if employee is None:
        return jsonify({"message": "Employee not found."}), 404
    actor = _actor_id()
    policy = InsurancePolicy(**values, created_by=actor, updated_by=actor)
    db.session.add(policy)
    db.session.commit()
    return jsonify(policy.to_dict(include_internal=True)), 201


@bp.put("/<int:policy_id>")
@roles_required(*INSURANCE_MANAGEMENT_ROLES)
def update_policy(policy_id):
    policy = InsurancePolicy.query.get_or_404(policy_id)
    payload = request.get_json(silent=True) or {}
    try:
        values = _validate_payload(payload, partial=True)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    if "employee_id" in values and User.query.get(values["employee_id"]) is None:
        return jsonify({"message": "Employee not found."}), 404
    for field, value in values.items():
        setattr(policy, field, value)
    policy.updated_by = _actor_id()
    db.session.commit()
    return jsonify(policy.to_dict(include_internal=True))


@bp.post("/<int:policy_id>/renew")
@roles_required(*INSURANCE_MANAGEMENT_ROLES)
def renew_policy(policy_id):
    old = InsurancePolicy.query.get_or_404(policy_id)
    payload = request.get_json(silent=True) or {}
    payload.setdefault("employee_id", old.employee_id)
    payload.setdefault("insurance_type", old.insurance_type)
    payload.setdefault("provider_name", old.provider_name)
    payload.setdefault("policy_number", old.policy_number)
    payload.setdefault("member_id", old.member_id)
    payload.setdefault("certificate_number", old.certificate_number)
    payload.setdefault("credentials", old.credentials or {})
    payload.setdefault("coverage_amount", old.coverage_amount)
    payload.setdefault("coverage_description", old.coverage_description)
    payload.setdefault("policy_start_date", payload.get("policy_start_date", old.policy_expiry_date.isoformat()))
    payload.setdefault("notes", old.notes)
    payload.setdefault("contact_name", old.contact_name)
    payload.setdefault("contact_email", old.contact_email)
    payload.setdefault("contact_phone", old.contact_phone)
    try:
        values = _validate_payload(payload)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    actor = _actor_id()
    old.status = "archived"
    new_policy = InsurancePolicy(**values, renewed_from_id=old.id, created_by=actor, updated_by=actor)
    db.session.add(new_policy)
    db.session.commit()
    return jsonify(new_policy.to_dict(include_internal=True)), 201


@bp.get("/<int:policy_id>/documents")
@jwt_required()
def list_policy_documents(policy_id):
    policy, denied = _authorized_policy(policy_id)
    if denied:
        return denied
    return jsonify([d.to_dict() for d in policy.documents])


def _store_upload(file):
    filename = secure_filename(file.filename)
    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Allowed file types are PDF, JPG, PNG, DOC, and DOCX.")
    limit = current_app.config["MAX_INSURANCE_DOCUMENT_BYTES"]
    content = file.stream.read(limit + 1)
    file.stream.seek(0)
    if not content or len(content) > limit:
        raise ValueError(f"Files must be non-empty and {limit // (1024 * 1024)} MB or smaller.")
    signatures = {
        ".pdf": content.startswith(b"%PDF-"), ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"), ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".doc": content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")), ".docx": content.startswith(b"PK\x03\x04"),
    }
    if not signatures[extension]:
        raise ValueError("The file contents do not match the selected file type.")
    key = f"{uuid.uuid4().hex}{extension}"
    folder = current_app.config["INSURANCE_DOCUMENT_FOLDER"]
    path = os.path.join(folder, key)
    os.makedirs(folder, exist_ok=True)
    with open(path, "wb") as saved:
        saved.write(content)
    return key, filename, MIME_TYPES[extension], len(content)


@bp.post("/<int:policy_id>/documents")
@roles_required(*INSURANCE_MANAGEMENT_ROLES)
def upload_policy_document(policy_id):
    policy = InsurancePolicy.query.get_or_404(policy_id)
    file = request.files.get("file")
    document_type = request.form.get("document_type", "other")
    if document_type not in DOCUMENT_TYPES:
        return jsonify({"message": "Unsupported insurance document type."}), 400
    if not file or not file.filename:
        return jsonify({"message": "A file is required."}), 400
    try:
        key, filename, mime, size = _store_upload(file)
    except (OSError, ValueError) as exc:
        return jsonify({"message": str(exc)}), 400
    document = InsuranceDocument(
        policy_id=policy.id, document_type=document_type, original_filename=filename,
        storage_key=key, mime_type=mime, file_size=size, uploaded_by=_actor_id(),
    )
    db.session.add(document)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        try:
            os.remove(os.path.join(current_app.config["INSURANCE_DOCUMENT_FOLDER"], key))
        except OSError:
            current_app.logger.exception("Could not remove failed insurance upload.")
        return jsonify({"message": "Could not save this insurance document."}), 500
    return jsonify(document.to_dict()), 201


@bp.post("/<int:policy_id>/documents/<int:document_id>/replace")
@roles_required(*INSURANCE_MANAGEMENT_ROLES)
def replace_policy_document(policy_id, document_id):
    old = InsuranceDocument.query.filter_by(id=document_id, policy_id=policy_id).first_or_404()
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"message": "A replacement file is required."}), 400
    try:
        key, filename, mime, size = _store_upload(file)
    except (OSError, ValueError) as exc:
        return jsonify({"message": str(exc)}), 400
    replacement = InsuranceDocument(
        policy_id=policy_id, document_type=request.form.get("document_type", old.document_type),
        original_filename=filename, storage_key=key, mime_type=mime, file_size=size, uploaded_by=_actor_id(),
    )
    db.session.add(replacement)
    db.session.flush()
    old.status = "archived"
    old.archived_at = datetime.utcnow()
    old.replaced_by_id = replacement.id
    db.session.commit()
    return jsonify(replacement.to_dict()), 201


@bp.patch("/<int:policy_id>/documents/<int:document_id>/archive")
@roles_required(*INSURANCE_MANAGEMENT_ROLES)
def archive_policy_document(policy_id, document_id):
    document = InsuranceDocument.query.filter_by(id=document_id, policy_id=policy_id).first_or_404()
    document.status = "archived"
    document.archived_at = datetime.utcnow()
    db.session.commit()
    return jsonify(document.to_dict())


@bp.get("/documents/<int:document_id>/download")
@jwt_required()
def download_policy_document(document_id):
    document = InsuranceDocument.query.get_or_404(document_id)
    if get_jwt().get("role") not in INSURANCE_MANAGEMENT_ROLES and document.policy.employee_id != _actor_id():
        return jsonify({"message": "You do not have permission to access this document."}), 403
    if document.status == "archived":
        return jsonify({"message": "This document has been archived."}), 404
    return send_from_directory(
        current_app.config["INSURANCE_DOCUMENT_FOLDER"], document.storage_key,
        mimetype=document.mime_type, as_attachment=False, download_name=document.original_filename,
    )


@bp.post("/internal/expiry-reminders")
def run_expiry_reminders():
    secret = request.headers.get("X-Internal-Secret")
    if not secret or secret != current_app.config.get("INTERNAL_TASK_SECRET"):
        return jsonify({"message": "Not authorized."}), 403
    today = date.today()
    policies = InsurancePolicy.query.filter(
        InsurancePolicy.status == "active",
        InsurancePolicy.policy_expiry_date == today + timedelta(days=7),
    ).all()
    admin_ids = [u.id for u in User.query.filter(User.role.in_(INSURANCE_MANAGEMENT_ROLES), User.is_active.is_(True)).all()]
    created = sent = 0
    for policy in policies:
        recipients = list(dict.fromkeys([policy.employee_id] + admin_ids))
        for recipient_id in recipients:
            reminder = InsuranceReminder.query.filter_by(
                policy_id=policy.id, recipient_id=recipient_id, reminder_date=today,
            ).first()
            if reminder:
                continue
            reminder = InsuranceReminder(policy_id=policy.id, recipient_id=recipient_id, reminder_date=today)
            db.session.add(reminder)
            db.session.flush()
            created += 1
            delivered = send_push(
                recipient_id, "Insurance expiry reminder",
                f"{policy.provider_name} {policy.insurance_type} policy expires on {policy.policy_expiry_date.isoformat()}.",
                data={"type": "insurance_expiry", "policy_id": policy.id},
            )
            reminder.delivery_status = "sent" if delivered else "not_delivered"
            reminder.sent_at = datetime.utcnow() if delivered else None
            sent += int(delivered)
    db.session.commit()
    return jsonify({"policies": len(policies), "created": created, "sent": sent})

