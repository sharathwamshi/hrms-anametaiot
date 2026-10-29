import os
import re
import uuid
import logging
import math
import hmac
import json
from datetime import datetime, date
from pathlib import PurePosixPath
from sqlalchemy import delete, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    Vendor, VendorAgreement, VendorAgreementRole, VendorHire,
    VendorInvoice, VendorInvoiceItem,
    CompanySettings, VendorCompany, User, Candidate, SalaryStructure, JobPosting,
)
from app.utils.security import roles_required
from app.utils.agreement_parser import parse_agreement
from app.utils.vendor_invoice_pdf import generate_vendor_invoice_pdf
from app.utils.permissions import role_or_permission_required
from app.roles import (
    VENDOR_MANAGEMENT_ROLES, VENDOR_VIEW_ROLES, VENDOR_CREATE_ROLES, VENDOR_EDIT_ROLES,
    VENDOR_APPROVER_ROLES, HR_OPERATIONS, CONTRACT_EMPLOYEE,
)
from app.services.vendor_agreements import agreement_status, send_expiry_reminders

bp = Blueprint("vendors", __name__, url_prefix="/api/vendors")
logger = logging.getLogger(__name__)

# In-memory staging area for parsed-but-not-yet-confirmed agreements.
# Keyed by a one-time token so the confirm step doesn't need to re-upload
# or re-parse the PDF; entries are cleared once confirmed or on restart.
_PENDING_AGREEMENTS = {}


def _normalize_name(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _validate_vendor_payload(payload, vendor=None):
    fields = (
        "name", "address", "state", "gstin", "pan", "contact_person",
        "contact_email", "contact_phone", "bank_name", "bank_account_no",
        "bank_ifsc", "bank_branch", "status",
    )
    values = {}
    for field in fields:
        if field not in payload:
            continue
        value = payload[field]
        if value is not None and not isinstance(value, str):
            return None, f"{field.replace('_', ' ').capitalize()} must be text."
        value = value.strip() if value else None
        values[field] = value or None

    name = values.get("name", vendor.name if vendor else "")
    if not name or not name.strip():
        return None, "Vendor name is required."
    if len(name) > 150:
        return None, "Vendor name cannot exceed 150 characters."
    values["name"] = name.strip()

    limits = {
        "state": 50, "gstin": 20, "pan": 20, "contact_person": 120,
        "contact_email": 150, "contact_phone": 20, "bank_name": 120,
        "bank_account_no": 40, "bank_ifsc": 20, "bank_branch": 120,
    }
    for field, limit in limits.items():
        if values.get(field) and len(values[field]) > limit:
            return None, f"{field.replace('_', ' ').capitalize()} cannot exceed {limit} characters."
    if values.get("address") and len(values["address"]) > 65535:
        return None, "Address is too long."
    if values.get("contact_email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", values["contact_email"]):
        return None, "Enter a valid contact email."
    if values.get("contact_phone") and not re.fullmatch(r"[+()\d\s.-]{7,20}", values["contact_phone"]):
        return None, "Enter a valid contact phone number."
    if values.get("gstin"):
        values["gstin"] = values["gstin"].upper()
        if not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]", values["gstin"]):
            return None, "Enter a valid GSTIN."
    if values.get("pan"):
        values["pan"] = values["pan"].upper()
        if not re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", values["pan"]):
            return None, "Enter a valid PAN."
    if values.get("bank_ifsc"):
        values["bank_ifsc"] = values["bank_ifsc"].upper()
        if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", values["bank_ifsc"]):
            return None, "Enter a valid IFSC."
    status = values.get("status", vendor.status if vendor else "active")
    if status not in ("active", "inactive"):
        return None, "Vendor status must be active or inactive."
    values["status"] = status
    if "company_id" in payload:
        raw_company_id = payload["company_id"]
        if raw_company_id in (None, ""):
            values["company_id"] = None
        else:
            try:
                company_id = int(raw_company_id)
            except (TypeError, ValueError):
                return None, "Company selection must be valid."
            if company_id <= 0 or not db.session.get(VendorCompany, company_id):
                return None, "Selected company was not found."
            values["company_id"] = company_id

    normalized_name = _normalize_name(values["name"])
    duplicate_query = Vendor.query.filter_by(normalized_name=normalized_name)
    if vendor:
        duplicate_query = duplicate_query.filter(Vendor.id != vendor.id)
    duplicate = duplicate_query.first()
    if duplicate:
        return None, f"A vendor named '{duplicate.name}' already exists."
    values["normalized_name"] = normalized_name
    return values, None


def _parse_agreement_date(value, label, required=False):
    if not value:
        return (None, None) if not required else (None, f"{label} is required.")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None, f"{label} must be a valid YYYY-MM-DD date."
    return parsed, None


def _validate_agreement_terms(values):
    effective_from, error = _parse_agreement_date(
        values.get("effective_from"), "Effective start date", required=True
    )
    if error:
        return None, error
    effective_to, error = _parse_agreement_date(values.get("effective_to"), "Effective end date")
    if error:
        return None, error
    if effective_to and effective_to < effective_from:
        return None, "Effective end date cannot precede the start date."

    terms = {"effective_from": effective_from, "effective_to": effective_to}
    for key, default in (
        ("termination_notice_days", 90),
        ("confidentiality_days", 60),
        ("feedback_days", 2),
    ):
        raw = values.get(key, default)
        if isinstance(raw, bool):
            return None, f"{key.replace('_', ' ').capitalize()} must be a non-negative integer."
        try:
            number = int(raw)
        except (TypeError, ValueError):
            return None, f"{key.replace('_', ' ').capitalize()} must be a non-negative integer."
        if str(number) != str(raw).strip() and not isinstance(raw, int):
            return None, f"{key.replace('_', ' ').capitalize()} must be a non-negative integer."
        if number < 0 or number > 3650:
            return None, f"{key.replace('_', ' ').capitalize()} must be between 0 and 3650."
        terms[key] = number
    title = values.get("title")
    if title is not None and (not isinstance(title, str) or len(title.strip()) > 150):
        return None, "Agreement title must be text no longer than 150 characters."
    terms["title"] = title.strip() if isinstance(title, str) and title.strip() else None
    status = values.get("status")
    if status is not None and status not in ("active", "expired", "terminated"):
        return None, "Agreement status must be active or terminated."
    if status in ("active", "terminated"):
        terms["status"] = status
    return terms, None


def _validate_agreement_roles(raw_roles, required=False):
    if not isinstance(raw_roles, list):
        return None, "Agreement roles must be a list."
    if required and not raw_roles:
        return None, "At least one agreement role is required."

    validated_roles = []
    for item in raw_roles:
        if not isinstance(item, dict):
            return None, "Each agreement role must be an object."
        role_name = item.get("role_name")
        if not isinstance(role_name, str) or not role_name.strip() or len(role_name.strip()) > 120:
            return None, "Each agreement role requires a name no longer than 120 characters."
        fee_raw = item.get("service_fee_pct")
        if isinstance(fee_raw, bool):
            return None, "Role fee and day fields must be valid numbers."
        try:
            fee = float(fee_raw)
            replacement_raw = item.get("replacement_days", 30)
            tenure_raw = item.get("tenure_days", 60)
            if isinstance(replacement_raw, bool) or isinstance(tenure_raw, bool):
                raise ValueError
            replacement_days = int(replacement_raw)
            tenure_days = int(tenure_raw)
        except (TypeError, ValueError):
            return None, "Role fee and day fields must be valid numbers."
        if (
            not math.isfinite(fee)
            or not 0 <= fee <= 100
            or str(replacement_days) != str(replacement_raw).strip()
            or str(tenure_days) != str(tenure_raw).strip()
            or not 0 <= replacement_days <= 3650
            or not 0 <= tenure_days <= 3650
        ):
            return None, "Role fee must be 0–100%, and role day fields must be 0–3650."
        validated_roles.append({
            "role_name": role_name.strip(),
            "service_fee_pct": fee,
            "replacement_days": replacement_days,
            "tenure_days": tenure_days,
        })
    return validated_roles, None


def _save_agreement_file(upload):
    if not upload or not upload.filename:
        return None, "A PDF agreement document is required."
    if PurePosixPath(upload.filename.replace("\\", "/")).suffix.lower() != ".pdf":
        return None, "Only PDF agreement documents are supported."
    header = upload.stream.read(5)
    upload.stream.seek(0)
    if header != b"%PDF-":
        return None, "The uploaded file is not a valid PDF."
    upload.stream.seek(0, os.SEEK_END)
    size = upload.stream.tell()
    upload.stream.seek(0)
    if size > 10 * 1024 * 1024:
        return None, "The agreement PDF must be 10 MB or smaller."
    safe_name = secure_filename(upload.filename)
    if not safe_name:
        return None, "The uploaded filename is invalid."
    filename = f"{uuid.uuid4().hex}_{safe_name[-180:]}"
    folder = current_app.config["VENDOR_AGREEMENT_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    upload.save(os.path.join(folder, filename))
    return filename, None


# ============================================================================
# Company settings (the "Buyer" block on every generated invoice)
# ============================================================================

@bp.get("/company-settings")
@jwt_required()
def get_company_settings():
    settings = CompanySettings.query.first()
    if not settings:
        settings = CompanySettings()
        db.session.add(settings)
        db.session.commit()
    return jsonify(settings.to_dict())


@bp.put("/company-settings")
@roles_required(HR_OPERATIONS)
def update_company_settings():
    settings = CompanySettings.query.first() or CompanySettings()
    payload = request.get_json(silent=True) or {}
    for field in ["company_name", "address", "gstin", "pan", "state"]:
        if field in payload:
            setattr(settings, field, payload[field])
    settings.updated_by = int(get_jwt_identity())
    db.session.add(settings)
    db.session.commit()
    return jsonify(settings.to_dict())


@bp.get("/companies")
@roles_required(*VENDOR_VIEW_ROLES)
def list_vendor_companies():
    return jsonify([
        company.to_dict()
        for company in VendorCompany.query.order_by(VendorCompany.name).all()
    ])


# ============================================================================
# Vendors
# ============================================================================

@bp.post("")
@roles_required(*VENDOR_CREATE_ROLES)
def create_vendor():
    """Add a vendor directly, with no agreement attached yet — for when the
    relationship starts before a contract is signed, or the agreement will
    be uploaded separately afterward."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "A vendor object is required."}), 400
    values, error = _validate_vendor_payload(payload)
    if error:
        return jsonify({"message": error}), 409 if error.startswith("A vendor named") else 400
    vendor = Vendor(**values, created_by=int(get_jwt_identity()))
    db.session.add(vendor)
    db.session.commit()
    return jsonify(vendor.to_sensitive_dict()), 201


@bp.post("/create-with-agreement")
@roles_required(*VENDOR_CREATE_ROLES)
def create_vendor_with_agreement():
    form = request.form.to_dict()
    company_id = form.get("company_id")
    new_company_name = (form.get("new_company_name") or "").strip()
    if bool(company_id) == bool(new_company_name):
        return jsonify({"message": "Select a company or enter a new company name."}), 400
    if new_company_name and len(new_company_name) > 150:
        return jsonify({"message": "Company name cannot exceed 150 characters."}), 400

    vendor_fields = (
        "name", "contact_person", "contact_email", "contact_phone", "gstin", "pan",
    )
    vendor_payload = {field: form.get(field) for field in vendor_fields}
    vendor_values, error = _validate_vendor_payload(vendor_payload)
    if error:
        return jsonify({"message": error}), 409 if error.startswith("A vendor named") else 400

    terms, error = _validate_agreement_terms({
        "title": form.get("title"),
        "effective_from": form.get("effective_from"),
        "effective_to": form.get("effective_to"),
        "termination_notice_days": form.get("termination_notice_days"),
        "confidentiality_days": form.get("confidentiality_days"),
        "feedback_days": form.get("feedback_days"),
    })
    if error:
        return jsonify({"message": error}), 400
    if not terms["title"]:
        return jsonify({"message": "Agreement title is required."}), 400
    if not terms["effective_to"]:
        return jsonify({"message": "Effective end date is required."}), 400

    try:
        roles_payload = json.loads(form.get("roles", ""))
    except (TypeError, json.JSONDecodeError):
        return jsonify({"message": "Agreement roles must be valid JSON."}), 400
    validated_roles, error = _validate_agreement_roles(roles_payload, required=True)
    if error:
        return jsonify({"message": error}), 400

    company = None
    if company_id:
        try:
            company_id = int(company_id)
        except (TypeError, ValueError):
            return jsonify({"message": "Company selection must be valid."}), 400
        company = db.session.get(VendorCompany, company_id)
        if not company:
            return jsonify({"message": "Selected company was not found."}), 400
        vendor_values["company_id"] = company.id
    else:
        if not new_company_name:
            return jsonify({"message": "Company name is required."}), 400
        company = VendorCompany.query.filter(
            func.lower(VendorCompany.name) == new_company_name.lower()
        ).first()
        if company:
            return jsonify({"message": "That company already exists. Select it from the company list."}), 409

    extraction_token = (form.get("extraction_token") or "").strip()
    staged_upload = _PENDING_AGREEMENTS.get(extraction_token) if extraction_token else None
    if extraction_token and not staged_upload:
        return jsonify({"message": "This upload has expired — please upload the agreement again."}), 400
    if staged_upload:
        file_path = staged_upload.get("file_path")
        if not file_path or not os.path.isfile(staged_upload.get("abs_path", "")):
            return jsonify({"message": "The staged agreement document is missing. Please upload it again."}), 400
    else:
        upload = request.files.get("file")
        file_path, error = _save_agreement_file(upload)
        if error:
            return jsonify({"message": error}), 400
    absolute_file_path = os.path.join(current_app.config["VENDOR_AGREEMENT_FOLDER"], file_path)
    actor_id = int(get_jwt_identity())

    try:
        if new_company_name:
            company = VendorCompany(name=new_company_name, created_by=actor_id)
            db.session.add(company)
            db.session.flush()
            vendor_values["company_id"] = company.id

        vendor = Vendor(**vendor_values, created_by=actor_id)
        db.session.add(vendor)
        db.session.flush()

        agreement = VendorAgreement(
            vendor_id=vendor.id,
            title=terms["title"],
            file_path=file_path,
            effective_from=terms["effective_from"],
            effective_to=terms["effective_to"],
            termination_notice_days=terms["termination_notice_days"],
            confidentiality_days=terms["confidentiality_days"],
            feedback_days=terms["feedback_days"],
            parsed_with_ai=staged_upload["parsed"].get("used_ai_fallback", False) if staged_upload else False,
            raw_extracted_text=staged_upload["parsed"].get("raw_text") if staged_upload else None,
            uploaded_by=actor_id,
        )
        db.session.add(agreement)
        db.session.flush()
        for role in validated_roles:
            db.session.add(VendorAgreementRole(agreement_id=agreement.id, **role))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if not staged_upload:
            try:
                os.remove(absolute_file_path)
            except OSError:
                logger.exception("Could not remove an agreement file after a failed vendor creation.")
        return jsonify({"message": "Vendor or company details conflict with an existing record."}), 409
    except Exception:
        db.session.rollback()
        if not staged_upload:
            try:
                os.remove(absolute_file_path)
            except OSError:
                logger.exception("Could not remove an agreement file after a failed vendor creation.")
        logger.exception("Combined vendor and agreement creation failed.")
        return jsonify({"message": "Vendor and agreement could not be created."}), 500

    if extraction_token:
        _PENDING_AGREEMENTS.pop(extraction_token, None)
    return jsonify(vendor.to_sensitive_dict(include_agreements=True)), 201


@bp.get("")
@roles_required(*VENDOR_VIEW_ROLES)
def list_vendors():
    status = request.args.get("status")
    agreement_filter = request.args.get("agreement_status")
    search = request.args.get("q", "").strip()
    if status and status not in ("active", "inactive"):
        return jsonify({"message": "Status must be active or inactive."}), 400
    if agreement_filter and agreement_filter not in {"upcoming", "active", "expiring_soon", "expired", "terminated"}:
        return jsonify({"message": "Invalid agreement status filter."}), 400
    query = Vendor.query.options(selectinload(Vendor.agreements), selectinload(Vendor.company))
    if status:
        query = query.filter_by(status=status)
    if search:
        term = f"%{search}%"
        query = query.filter(or_(
            Vendor.name.ilike(term),
            Vendor.gstin.ilike(term),
            Vendor.pan.ilike(term),
            Vendor.contact_person.ilike(term),
            Vendor.contact_email.ilike(term),
        ))
    rows = query.order_by(Vendor.name).all()
    if agreement_filter:
        rows = [
            vendor for vendor in rows
            if any(agreement_status(agreement) == agreement_filter for agreement in vendor.agreements)
        ]
    return jsonify([vendor.to_dict() for vendor in rows])


@bp.get("/<int:vendor_id>")
@roles_required(*VENDOR_VIEW_ROLES)
def get_vendor(vendor_id):
    vendor = Vendor.query.options(
        selectinload(Vendor.agreements).selectinload(VendorAgreement.roles)
    ).filter_by(id=vendor_id).first_or_404()
    if get_jwt().get("role") in VENDOR_MANAGEMENT_ROLES:
        return jsonify(vendor.to_sensitive_dict(include_agreements=True))
    return jsonify(vendor.to_dict(include_agreements=True))


@bp.put("/<int:vendor_id>")
@roles_required(*VENDOR_EDIT_ROLES)
def update_vendor(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "A vendor object is required."}), 400
    values, error = _validate_vendor_payload(payload, vendor)
    if error:
        return jsonify({"message": error}), 409 if error.startswith("A vendor named") else 400
    for field, value in values.items():
        setattr(vendor, field, value)
    db.session.commit()
    return jsonify(vendor.to_sensitive_dict())


@bp.delete("/<int:vendor_id>")
@roles_required(HR_OPERATIONS)
def delete_vendor(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)
    dependencies = {
        "agreements": VendorAgreement.query.filter_by(vendor_id=vendor.id).count(),
        "hires": VendorHire.query.filter_by(vendor_id=vendor.id).count(),
        "invoices": VendorInvoice.query.filter_by(vendor_id=vendor.id).count(),
        "requisitions": JobPosting.query.filter_by(vendor_id=vendor.id).count(),
    }
    linked_records = {name: count for name, count in dependencies.items() if count}
    if linked_records:
        return jsonify({
            "message": "This vendor has associated records and cannot be permanently deleted. Deactivate it instead.",
            "dependencies": linked_records,
        }), 409

    vendor_name = vendor.name
    try:
        db.session.execute(delete(Vendor).where(Vendor.id == vendor.id))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        logger.exception("Could not delete vendor %s because a related record exists.", vendor.id)
        return jsonify({
            "message": "This vendor has related records and cannot be permanently deleted. Deactivate it instead."
        }), 409
    logger.info("Vendor %s (%s) permanently deleted by user %s.", vendor.id, vendor_name, get_jwt_identity())
    return jsonify({"message": f"Vendor '{vendor_name}' was deleted."})
# ============================================================================
# Agreement upload — parse, detect existing vendor, stage for confirmation
# ============================================================================

@bp.post("/agreements/parse")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def parse_agreement_upload():
    if "file" not in request.files:
        return jsonify({"message": "No file uploaded."}), 400

    filename, error = _save_agreement_file(request.files["file"])
    if error:
        return jsonify({"message": error}), 400
    abs_path = os.path.join(current_app.config["VENDOR_AGREEMENT_FOLDER"], filename)

    try:
        with open(abs_path, "rb") as fh:
            parsed = parse_agreement(fh)
    except Exception:
        try:
            os.remove(abs_path)
        except OSError:
            logger.exception("Could not remove an agreement file after extraction failed.")
        logger.exception("Could not extract fields from an uploaded vendor agreement.")
        return jsonify({"message": "Could not read this agreement. Try a text-based PDF or enter its details manually."}), 422

    # Try to identify which of the two parties is the vendor: whichever
    # name does NOT resemble our own company. Default to party_b (the
    # second-mentioned party in this template), but let the UI confirm.
    company = CompanySettings.query.first()
    our_name_norm = _normalize_name(company.company_name) if company else ""
    candidates_for_vendor = [parsed.get("party_a"), parsed.get("party_b")]
    likely_vendor_name = None
    for name in candidates_for_vendor:
        if name and _normalize_name(name) != our_name_norm:
            likely_vendor_name = name
            break
    likely_vendor_name = likely_vendor_name or parsed.get("party_b")

    matched_vendor = None
    if likely_vendor_name:
        norm = _normalize_name(likely_vendor_name)
        matched_vendor = Vendor.query.filter_by(normalized_name=norm).first()
        if not matched_vendor:
            # Fuzzy fallback: substring match either direction
            for v in Vendor.query.all():
                if norm and (norm in v.normalized_name or v.normalized_name in norm):
                    matched_vendor = v
                    break

    token = uuid.uuid4().hex
    _PENDING_AGREEMENTS[token] = {
        "file_path": filename,
        "abs_path": abs_path,
        "parsed": parsed,
    }

    return jsonify({
        "token": token,
        "likely_vendor_name": likely_vendor_name,
        "party_a": parsed.get("party_a"),
        "party_b": parsed.get("party_b"),
        "effective_from": parsed.get("effective_from"),
        "effective_to": parsed.get("effective_to"),
        "termination_notice_days": parsed.get("termination_notice_days"),
        "confidentiality_days": parsed.get("confidentiality_days"),
        "feedback_days": parsed.get("feedback_days"),
        "roles": parsed.get("roles"),
        "extracted_fields": parsed.get("extracted_fields", []),
        "used_ai_fallback": parsed.get("used_ai_fallback"),
        "matched_vendor": matched_vendor.to_dict() if matched_vendor else None,
    })


@bp.post("/agreements/confirm")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def confirm_agreement():
    """Body: { token, vendor_id (existing) OR new_vendor: {...},
    effective_from, effective_to, termination_notice_days,
    confidentiality_days, feedback_days, roles: [...] }
    Everything here is exactly what the user reviewed/edited in the
    preview step — nothing is inferred fresh at this point."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "An agreement object is required."}), 400
    token = payload.get("token")
    staged = _PENDING_AGREEMENTS.get(token)
    if not staged:
        return jsonify({"message": "This upload has expired — please upload the agreement again."}), 400

    actor_id = int(get_jwt_identity())
    terms, error = _validate_agreement_terms(payload)
    if error:
        return jsonify({"message": error}), 400
    if not staged.get("file_path") or not os.path.isfile(staged.get("abs_path", "")):
        return jsonify({"message": "The staged agreement document is missing. Please upload it again."}), 400

    validated_roles, error = _validate_agreement_roles(payload.get("roles", []))
    if error:
        return jsonify({"message": error}), 400

    vendor_id = payload.get("vendor_id")
    if vendor_id:
        try:
            vendor_id = int(vendor_id)
        except (TypeError, ValueError):
            return jsonify({"message": "Vendor ID must be an integer."}), 400
        vendor = db.session.get(Vendor, vendor_id)
        if not vendor:
            return jsonify({"message": "Vendor not found."}), 404
    else:
        new_vendor = payload.get("new_vendor")
        if not isinstance(new_vendor, dict):
            return jsonify({"message": "New vendor details must be an object."}), 400
        vendor_values, error = _validate_vendor_payload(new_vendor)
        if error:
            return jsonify({"message": error}), 400
        vendor = Vendor(**vendor_values, created_by=actor_id)
        db.session.add(vendor)
        db.session.flush()

    agreement = VendorAgreement(
        vendor_id=vendor.id,
        title=terms["title"] or f"Agreement {terms['effective_from'].isoformat()}",
        file_path=staged["file_path"],
        effective_from=terms["effective_from"],
        effective_to=terms["effective_to"],
        termination_notice_days=terms["termination_notice_days"],
        confidentiality_days=terms["confidentiality_days"],
        feedback_days=terms["feedback_days"],
        parsed_with_ai=staged["parsed"].get("used_ai_fallback", False),
        raw_extracted_text=staged["parsed"].get("raw_text"),
        uploaded_by=actor_id,
    )
    db.session.add(agreement)
    db.session.flush()

    for role in validated_roles:
        db.session.add(VendorAgreementRole(
            agreement_id=agreement.id,
            role_name=role["role_name"],
            service_fee_pct=role["service_fee_pct"],
            replacement_days=role["replacement_days"],
            tenure_days=role["tenure_days"],
        ))

    db.session.commit()
    _PENDING_AGREEMENTS.pop(token, None)

    return jsonify(vendor.to_dict(include_agreements=True)), 201


@bp.get("/agreements/<int:agreement_id>")
@roles_required(*VENDOR_VIEW_ROLES)
def get_agreement(agreement_id):
    agreement = VendorAgreement.query.get_or_404(agreement_id)
    return jsonify(agreement.to_dict(include_roles=True))


@bp.put("/agreements/<int:agreement_id>")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def update_agreement(agreement_id):
    agreement = VendorAgreement.query.get_or_404(agreement_id)
    payload = request.form.to_dict() if request.mimetype == "multipart/form-data" else request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Agreement details are required."}), 400
    if "title" in payload and (not isinstance(payload["title"], str) or not payload["title"].strip()):
        return jsonify({"message": "Agreement title is required."}), 400
    terms, error = _validate_agreement_terms({
        **{
            "effective_from": agreement.effective_from.isoformat() if agreement.effective_from else None,
            "effective_to": agreement.effective_to.isoformat() if agreement.effective_to else None,
            "termination_notice_days": agreement.termination_notice_days,
            "confidentiality_days": agreement.confidentiality_days,
            "feedback_days": agreement.feedback_days,
            "title": agreement.title,
            "status": agreement.status,
        },
        **payload,
    })
    if error:
        return jsonify({"message": error}), 400

    replacement_path = None
    upload = request.files.get("file")
    if upload and upload.filename:
        replacement_path, error = _save_agreement_file(upload)
        if error:
            return jsonify({"message": error}), 400

    previous_path = agreement.file_path
    agreement.title = terms["title"]
    agreement.effective_from = terms["effective_from"]
    agreement.effective_to = terms["effective_to"]
    agreement.termination_notice_days = terms["termination_notice_days"]
    agreement.confidentiality_days = terms["confidentiality_days"]
    agreement.feedback_days = terms["feedback_days"]
    if terms.get("status"):
        agreement.status = terms["status"]
    if replacement_path:
        agreement.file_path = replacement_path
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        if replacement_path:
            try:
                os.remove(os.path.join(current_app.config["VENDOR_AGREEMENT_FOLDER"], replacement_path))
            except OSError:
                logger.exception("Could not remove an uncommitted agreement replacement.")
        raise

    if replacement_path:
        _remove_agreement_file(previous_path)
    return jsonify(agreement.to_dict(include_roles=True))


def _remove_agreement_file(file_path):
    if not file_path:
        return
    if file_path.startswith("/static/uploads/"):
        root = current_app.config["UPLOAD_FOLDER"]
        relative = file_path[len("/static/uploads/"):]
    else:
        root = current_app.config["VENDOR_AGREEMENT_FOLDER"]
        relative = file_path
    normalized = os.path.normpath(relative)
    if os.path.isabs(normalized) or normalized == ".." or normalized.startswith(f"..{os.sep}"):
        logger.warning("Skipped removal of an invalid agreement path.")
        return
    try:
        os.remove(os.path.join(root, normalized))
    except FileNotFoundError:
        return
    except OSError:
        logger.exception("Could not remove a replaced agreement file.")


@bp.get("/agreements/<int:agreement_id>/download")
@roles_required(*VENDOR_VIEW_ROLES)
def download_agreement(agreement_id):
    agreement = VendorAgreement.query.get_or_404(agreement_id)
    file_path = agreement.file_path or ""
    if file_path.startswith("/static/uploads/"):
        root = current_app.config["UPLOAD_FOLDER"]
        relative = file_path[len("/static/uploads/"):]
    else:
        root = current_app.config["VENDOR_AGREEMENT_FOLDER"]
        relative = file_path
    normalized = os.path.normpath(relative)
    if os.path.isabs(normalized) or normalized == ".." or normalized.startswith(f"..{os.sep}"):
        return jsonify({"message": "Agreement document not found."}), 404
    try:
        return send_from_directory(
            root,
            normalized,
            as_attachment=True,
            download_name=secure_filename(os.path.basename(normalized)) or "agreement.pdf",
        )
    except (FileNotFoundError, OSError):
        return jsonify({"message": "Agreement document not found."}), 404


@bp.post("/internal/agreement-expiry-reminders")
def run_agreement_expiry_reminders():
    secret = request.headers.get("X-Internal-Secret")
    expected = current_app.config.get("INTERNAL_TASK_SECRET")
    if not secret or not expected or not hmac.compare_digest(secret, expected):
        return jsonify({"message": "Not authorized."}), 403
    return jsonify(send_expiry_reminders())


# ============================================================================
# Vendor hires — assigning a hired person to a vendor rate-card role
# ============================================================================

def _build_hire_query(args):
    """Shared filters for the All Placements list and its CSV export."""
    q = args.get("q", "").strip()
    query = VendorHire.query
    for field in ("vendor_id", "recruiter_id"):
        val = args.get(field, type=int)
        if val:
            query = query.filter(getattr(VendorHire, field) == val)
    for field in ("status", "placement_type", "billing_type"):
        val = args.get(field)
        if val:
            query = query.filter(getattr(VendorHire, field) == val)
    if q:
        query = query.filter(VendorHire.candidate_name.ilike(f"%{q}%"))
    return query


@bp.get("/hires")
@roles_required(*VENDOR_VIEW_ROLES)
def list_hires():
    """With no vendor_id, this is the cross-vendor 'All Placements' list —
    every candidate ever placed with any vendor, direct or contract, kept
    entirely separate from AnametaIOT's own Employees directory. Filters:
    q, vendor_id, recruiter_id, status, placement_type, billing_type."""
    sort = request.args.get("sort", "assigned_desc")
    sort_map = {
        "assigned_desc": VendorHire.assigned_at.desc(),
        "assigned_asc": VendorHire.assigned_at.asc(),
        "name_asc": VendorHire.candidate_name.asc(),
        "name_desc": VendorHire.candidate_name.desc(),
    }
    rows = _build_hire_query(request.args).order_by(sort_map.get(sort, VendorHire.assigned_at.desc())).all()
    data = [h.to_dict() for h in rows]
    if request.args.get("billable_only") == "true":
        data = [h for h in data if h["is_billable"]]
    return jsonify(data)


@bp.get("/hires/export")
@roles_required(*VENDOR_VIEW_ROLES)
def export_hires():
    """CSV export of the All Placements list, same filters as /hires."""
    import csv
    import io
    from flask import Response

    rows = _build_hire_query(request.args).order_by(VendorHire.assigned_at.desc()).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Candidate", "Vendor", "Role", "Recruiter", "Placement Type", "Billing Type", "CTC",
        "Tenure Start", "Status", "Has Internal Login", "Assigned On",
    ])
    for h in rows:
        writer.writerow([
            h.candidate_name, h.vendor.name if h.vendor else "", h.role.role_name if h.role else "",
            h.recruiter.full_name if h.recruiter else "", h.placement_type, h.billing_type, h.ctc,
            h.tenure_start_date.isoformat(), h.status, "Yes" if h.employee_id else "No",
            h.assigned_at.isoformat(),
        ])
    return Response(
        buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=vendor_placements_export.csv"},
    )


@bp.post("/hires/<int:hire_id>/bill-recurring")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def bill_hire_recurring(hire_id):
    """Marks a continuous-billing placement as billed for a given month —
    called once per month per active contract placement when its monthly
    invoice is generated. Body: { period: 'YYYY-MM' } (defaults to current month)."""
    hire = VendorHire.query.get_or_404(hire_id)
    payload = request.get_json(silent=True) or {}
    period = payload.get("period") or date.today().strftime("%Y-%m")

    if not hire.is_due_for_recurring_billing(period):
        return jsonify({"message": "This placement is not due for recurring billing this period."}), 400

    hire.last_billed_month = period
    db.session.commit()
    return jsonify(hire.to_dict())


def _create_contract_login(full_name, email, password, start_date):
    """Creates the narrow internal login (role: Contract Employee) used to
    track a contract placement's documents and payroll. Returns (user, None)
    on success or (None, (json_response, status)) on a validation problem."""
    email = (email or "").strip().lower()
    if not email or not password:
        return None, (jsonify({"message": "A contract placement needs a login email and password (contract_login_email / contract_login_password)."}), 400)
    if User.query.filter_by(email=email).first():
        return None, (jsonify({"message": f"Email '{email}' is already in use by another account."}), 409)
    employee_code = None
    for _ in range(5):
        code = f"CT{uuid.uuid4().hex[:6].upper()}"
        if not User.query.filter_by(employee_code=code).first():
            employee_code = code
            break
    if not employee_code:
        return None, (jsonify({"message": "Could not generate a unique contract login code — please try again."}), 500)
    user = User(employee_code=employee_code, full_name=full_name, email=email,
                role=CONTRACT_EMPLOYEE, date_of_joining=start_date)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user, None


@bp.post("/hires")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def assign_hire():
    """Assigns a candidate to a vendor's rate-card role, starting the
    tenure/billing clock. Two distinct placement types:

    - "direct": the person joins the vendor's own payroll entirely. No
      internal AnametaIOT account is created — they are not our employee.
    - "contract": still placed with (and worked for) the vendor, but we
      keep a limited internal login (role: Contract Employee) purely to
      track their documents and payroll inside this tool — the exact
      narrow scope that role already exists for. This does NOT make them
      an AnametaIOT employee in any other sense (no department requisites,
      no internal team membership) — it's a tracking record, not a hire.
    """
    payload = request.get_json(silent=True) or {}
    required = ["vendor_id", "agreement_id", "agreement_role_id", "candidate_name", "ctc", "tenure_start_date"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return jsonify({"message": f"Missing fields: {', '.join(missing)}"}), 400

    placement_type = payload.get("placement_type", "direct")
    if placement_type not in ("direct", "contract"):
        return jsonify({"message": "placement_type must be 'direct' or 'contract'."}), 400
    billing_type = payload.get("billing_type", "one_time" if placement_type == "direct" else "continuous")
    if billing_type not in ("one_time", "continuous"):
        return jsonify({"message": "billing_type must be 'one_time' or 'continuous'."}), 400

    Vendor.query.get_or_404(payload["vendor_id"])
    VendorAgreement.query.get_or_404(payload["agreement_id"])
    VendorAgreementRole.query.get_or_404(payload["agreement_role_id"])

    employee_id = payload.get("employee_id")

    # --- Candidate link: keeps the pipeline and the placement list consistent ---
    recruiter_id = payload.get("recruiter_id")
    candidate_id = payload.get("candidate_id")
    if candidate_id:
        cand = Candidate.query.get(candidate_id)
        if not cand:
            return jsonify({"message": "That candidate no longer exists."}), 404
        job = cand.job
        if not job or job.requisition_type != "client" or job.vendor_id != int(payload["vendor_id"]):
            return jsonify({"message": "This candidate was not sourced for this vendor's client requisition, so they cannot be placed with it."}), 400
        if cand.stage != "hired":
            return jsonify({"message": f"Only hired candidates can be placed with a vendor (this one is at '{cand.stage}')."}), 400
        already = VendorHire.query.filter(
            VendorHire.candidate_id == cand.id, VendorHire.status.in_(["active", "invoiced"])
        ).first()
        if already:
            return jsonify({"message": "This candidate is already placed with a vendor."}), 409
        recruiter_id = recruiter_id or cand.added_by
    if recruiter_id and not User.query.get(recruiter_id):
        return jsonify({"message": "The selected recruiter does not exist."}), 400

    tenure_start = datetime.strptime(payload["tenure_start_date"], "%Y-%m-%d").date()
    if placement_type == "contract" and not employee_id:
        # Create the internal "contract login" — tracked in our tool, but
        # they work for the vendor, not for us.
        contract_user, err = _create_contract_login(
            payload["candidate_name"], payload.get("contract_login_email"),
            payload.get("contract_login_password"), tenure_start,
        )
        if err:
            return err
        employee_id = contract_user.id

    hire = VendorHire(
        vendor_id=payload["vendor_id"],
        agreement_id=payload["agreement_id"],
        agreement_role_id=payload["agreement_role_id"],
        candidate_id=candidate_id,
        employee_id=employee_id,
        candidate_name=payload["candidate_name"],
        ctc=float(payload["ctc"]),
        placement_type=placement_type,
        billing_type=billing_type,
        tenure_start_date=tenure_start,
        assigned_by=int(get_jwt_identity()),
        recruiter_id=recruiter_id,
    )
    db.session.add(hire)

    # "Once assigned, payroll starts" — auto-create a starter salary
    # structure for the linked employee if one doesn't exist yet, using
    # the CTC as Basic. Finance can refine the actual breakdown afterward
    # from the Payroll page — this just makes sure payroll isn't blocked
    # on a manual first step. Only applies when there IS an internal login
    # (contract placements) — a direct hire has no internal payroll at all.
    if employee_id:
        existing = SalaryStructure.query.filter_by(user_id=employee_id).first()
        if not existing:
            db.session.add(SalaryStructure(user_id=employee_id, basic=float(payload["ctc"])))

    db.session.commit()
    return jsonify(hire.to_dict()), 201


@bp.post("/hires/<int:hire_id>/replace")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def replace_hire(hire_id):
    """Marks a hire as replaced (within the agreement's replacement window)
    and creates the replacement hire under the same role/vendor."""
    original = VendorHire.query.get_or_404(hire_id)
    payload = request.get_json(silent=True) or {}
    if not payload.get("candidate_name"):
        return jsonify({"message": "candidate_name for the replacement is required."}), 400
    if original.status not in ("active", "invoiced"):
        # An invoiced/paid placement is still replaceable — the replacement
        # guarantee exists precisely for someone who leaves after billing.
        return jsonify({"message": f"This placement is already '{original.status}' and cannot be replaced again."}), 400

    tenure_start = datetime.strptime(
        payload.get("tenure_start_date", date.today().isoformat()), "%Y-%m-%d"
    ).date()
    employee_id = payload.get("employee_id")
    # A replacement keeps the original's deal (direct/contract, one-time/monthly).
    # A contract replacement is a different person, so they need their own login.
    if original.placement_type == "contract" and not employee_id:
        login_user, err = _create_contract_login(
            payload["candidate_name"], payload.get("contract_login_email"),
            payload.get("contract_login_password"), tenure_start,
        )
        if err:
            return err
        employee_id = login_user.id
        if not SalaryStructure.query.filter_by(user_id=employee_id).first():
            db.session.add(SalaryStructure(user_id=employee_id, basic=float(payload.get("ctc", original.ctc))))

    original.status = "replaced"
    replacement = VendorHire(
        vendor_id=original.vendor_id,
        agreement_id=original.agreement_id,
        agreement_role_id=original.agreement_role_id,
        candidate_id=payload.get("candidate_id"),
        employee_id=employee_id,
        candidate_name=payload["candidate_name"],
        ctc=float(payload.get("ctc", original.ctc)),
        placement_type=original.placement_type,
        billing_type=original.billing_type,
        tenure_start_date=tenure_start,
        replacement_of_hire_id=original.id,
        assigned_by=int(get_jwt_identity()),
        recruiter_id=payload.get("recruiter_id") or original.recruiter_id,
    )
    db.session.add(replacement)
    db.session.commit()
    return jsonify(replacement.to_dict()), 201


# ============================================================================
# Vendor invoices
# ============================================================================

def _next_invoice_number(vendor):
    prefix = re.sub(r"[^A-Z]", "", (vendor.name or "VEN").upper())[:4] or "VEN"
    count = VendorInvoice.query.filter(VendorInvoice.invoice_number.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:04d}/{date.today().strftime('%m/%y')}"


@bp.get("/invoices")
@roles_required(*VENDOR_VIEW_ROLES)
def list_invoices():
    vendor_id = request.args.get("vendor_id", type=int)
    status = request.args.get("status")
    query = VendorInvoice.query
    if vendor_id:
        query = query.filter_by(vendor_id=vendor_id)
    if status:
        query = query.filter_by(status=status)
    rows = query.order_by(VendorInvoice.generated_at.desc()).all()
    return jsonify([i.to_dict() for i in rows])


@bp.get("/invoices/<int:invoice_id>")
@roles_required(*VENDOR_VIEW_ROLES)
def get_invoice(invoice_id):
    invoice = VendorInvoice.query.get_or_404(invoice_id)
    return jsonify(invoice.to_dict(include_items=True))


@bp.post("/<int:vendor_id>/invoices/generate")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def generate_invoice(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)
    payload = request.get_json(silent=True) or {}
    hire_ids = payload.get("hire_ids")

    query = VendorHire.query.filter_by(vendor_id=vendor_id, status="active")
    if hire_ids:
        query = query.filter(VendorHire.id.in_(hire_ids))
    hires = [h for h in query.all() if h.is_billable]

    if not hires:
        return jsonify({"message": "No billable hires found — either none are assigned, or their tenure period hasn't completed yet."}), 400

    agreement = hires[0].agreement
    subtotal = 0.0
    line_items_data = []
    for hire in hires:
        fee_amount = round(hire.ctc * (hire.role.service_fee_pct / 100), 2)
        subtotal += fee_amount
        line_items_data.append({
            "hire": hire, "candidate_name": hire.candidate_name,
            "role_name": hire.role.role_name, "ctc": hire.ctc,
            "fee_pct": hire.role.service_fee_pct, "fee_amount": fee_amount,
        })

    company = CompanySettings.query.first() or CompanySettings()
    same_state = (vendor.state or "").strip().lower() == (company.state or "").strip().lower()

    if same_state:
        cgst = round(subtotal * 0.09, 2)
        sgst = round(subtotal * 0.09, 2)
        igst = 0.0
    else:
        cgst = sgst = 0.0
        igst = round(subtotal * 0.18, 2)
    total = round(subtotal + cgst + sgst + igst, 2)

    invoice = VendorInvoice(
        vendor_id=vendor.id,
        agreement_id=agreement.id,
        invoice_number=_next_invoice_number(vendor),
        invoice_date=date.today(),
        subtotal=subtotal, cgst_amount=cgst, sgst_amount=sgst, igst_amount=igst,
        total_amount=total,
        status="draft",
        generated_by=int(get_jwt_identity()),
    )
    db.session.add(invoice)
    db.session.flush()

    for item in line_items_data:
        db.session.add(VendorInvoiceItem(
            invoice_id=invoice.id, hire_id=item["hire"].id,
            candidate_name=item["candidate_name"], role_name=item["role_name"],
            ctc=item["ctc"], fee_pct=item["fee_pct"], fee_amount=item["fee_amount"],
        ))
        item["hire"].status = "invoiced"

    filename = f"invoice_{invoice.id}_{uuid.uuid4().hex[:8]}.pdf"
    rel_path = os.path.join("vendor_invoices", filename)
    abs_path = os.path.join(current_app.config["UPLOAD_FOLDER"], rel_path)
    generate_vendor_invoice_pdf(
        abs_path, invoice.invoice_number, invoice.invoice_date.strftime("%d-%m-%Y"),
        vendor.to_dict(), company.to_dict(),
        [{"candidate_name": i["candidate_name"], "role_name": i["role_name"],
          "ctc": i["ctc"], "fee_pct": i["fee_pct"], "fee_amount": i["fee_amount"]} for i in line_items_data],
        subtotal, cgst, sgst, igst, total,
    )
    invoice.pdf_path = f"/static/uploads/{rel_path}"

    db.session.commit()
    return jsonify(invoice.to_dict(include_items=True)), 201


@bp.post("/<int:vendor_id>/invoices/generate-recurring")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def generate_recurring_invoice(vendor_id):
    """Monthly billing for continuous-billing (typically contract)
    placements — completely separate from the one-time tenure-gated flow
    above. Each eligible hire is billed a monthly fee (CTC/12 × the
    role's service fee %) and marked with last_billed_month so the same
    period is never double-charged; unlike a one-time hire, its status
    stays 'active' so it continues billing every subsequent month."""
    vendor = Vendor.query.get_or_404(vendor_id)
    payload = request.get_json(silent=True) or {}
    period = payload.get("period") or date.today().strftime("%Y-%m")
    hire_ids = payload.get("hire_ids")

    query = VendorHire.query.filter_by(vendor_id=vendor_id, status="active", billing_type="continuous")
    if hire_ids:
        query = query.filter(VendorHire.id.in_(hire_ids))
    hires = [h for h in query.all() if h.is_due_for_recurring_billing(period)]

    if not hires:
        return jsonify({"message": f"No continuous placements are due for billing in {period}."}), 400

    agreement = hires[0].agreement
    subtotal = 0.0
    line_items_data = []
    for hire in hires:
        fee_amount = round((hire.ctc / 12) * (hire.role.service_fee_pct / 100), 2)
        subtotal += fee_amount
        line_items_data.append({
            "hire": hire, "candidate_name": hire.candidate_name,
            "role_name": f"{hire.role.role_name} (monthly — {period})", "ctc": hire.ctc,
            "fee_pct": hire.role.service_fee_pct, "fee_amount": fee_amount,
        })

    company = CompanySettings.query.first() or CompanySettings()
    same_state = (vendor.state or "").strip().lower() == (company.state or "").strip().lower()
    if same_state:
        cgst = round(subtotal * 0.09, 2)
        sgst = round(subtotal * 0.09, 2)
        igst = 0.0
    else:
        cgst = sgst = 0.0
        igst = round(subtotal * 0.18, 2)
    total = round(subtotal + cgst + sgst + igst, 2)

    invoice = VendorInvoice(
        vendor_id=vendor.id, agreement_id=agreement.id,
        invoice_number=_next_invoice_number(vendor), invoice_date=date.today(),
        subtotal=subtotal, cgst_amount=cgst, sgst_amount=sgst, igst_amount=igst,
        total_amount=total, status="draft", generated_by=int(get_jwt_identity()),
    )
    db.session.add(invoice)
    db.session.flush()

    for item in line_items_data:
        db.session.add(VendorInvoiceItem(
            invoice_id=invoice.id, hire_id=item["hire"].id,
            candidate_name=item["candidate_name"], role_name=item["role_name"],
            ctc=item["ctc"], fee_pct=item["fee_pct"], fee_amount=item["fee_amount"],
        ))
        item["hire"].last_billed_month = period  # stays "active" — bills again next period

    filename = f"invoice_{invoice.id}_{uuid.uuid4().hex[:8]}.pdf"
    rel_path = os.path.join("vendor_invoices", filename)
    abs_path = os.path.join(current_app.config["UPLOAD_FOLDER"], rel_path)
    generate_vendor_invoice_pdf(
        abs_path, invoice.invoice_number, invoice.invoice_date.strftime("%d-%m-%Y"),
        vendor.to_dict(), company.to_dict(),
        [{"candidate_name": i["candidate_name"], "role_name": i["role_name"],
          "ctc": i["ctc"], "fee_pct": i["fee_pct"], "fee_amount": i["fee_amount"]} for i in line_items_data],
        subtotal, cgst, sgst, igst, total,
    )
    invoice.pdf_path = f"/static/uploads/{rel_path}"

    db.session.commit()
    return jsonify(invoice.to_dict(include_items=True)), 201


@bp.post("/invoices/<int:invoice_id>/submit-for-approval")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def submit_invoice_for_approval(invoice_id):
    invoice = VendorInvoice.query.get_or_404(invoice_id)
    invoice.status = "pending_approval"
    db.session.commit()
    return jsonify(invoice.to_dict())


@bp.post("/invoices/<int:invoice_id>/approve")
@role_or_permission_required(*VENDOR_APPROVER_ROLES, permission_key="approve_vendor_invoices")
def approve_invoice(invoice_id):
    invoice = VendorInvoice.query.get_or_404(invoice_id)
    payload = request.get_json(silent=True) or {}
    invoice.status = "approved"
    invoice.approved_by = int(get_jwt_identity())
    invoice.approved_at = datetime.utcnow()
    invoice.approval_comment = payload.get("comment", "")
    db.session.commit()
    return jsonify(invoice.to_dict())


@bp.post("/invoices/<int:invoice_id>/reject")
@role_or_permission_required(*VENDOR_APPROVER_ROLES, permission_key="approve_vendor_invoices")
def reject_invoice(invoice_id):
    invoice = VendorInvoice.query.get_or_404(invoice_id)
    payload = request.get_json(silent=True) or {}
    invoice.status = "rejected"
    invoice.approved_by = int(get_jwt_identity())
    invoice.approved_at = datetime.utcnow()
    invoice.approval_comment = payload.get("comment", "")
    # Free the hires back up so they can be re-billed on a corrected invoice
    for item in invoice.items:
        if item.hire.status == "invoiced":
            item.hire.status = "active"
    db.session.commit()
    return jsonify(invoice.to_dict())


@bp.post("/invoices/<int:invoice_id>/mark-paid")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def mark_invoice_paid(invoice_id):
    invoice = VendorInvoice.query.get_or_404(invoice_id)
    if invoice.status != "approved":
        return jsonify({"message": "Only an approved invoice can be marked paid."}), 400
    invoice.status = "paid"
    invoice.paid_at = datetime.utcnow()
    db.session.commit()
    return jsonify(invoice.to_dict())
