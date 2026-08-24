import os
import re
import uuid
from datetime import datetime, date

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    Vendor, VendorAgreement, VendorAgreementRole, VendorHire,
    VendorInvoice, VendorInvoiceItem, CompanySettings, User, Candidate, SalaryStructure,
)
from app.utils.security import roles_required
from app.utils.agreement_parser import parse_agreement
from app.utils.vendor_invoice_pdf import generate_vendor_invoice_pdf
from app.utils.permissions import role_or_permission_required
from app.roles import VENDOR_MANAGEMENT_ROLES, VENDOR_APPROVER_ROLES, HR_OPERATIONS, CONTRACT_EMPLOYEE

bp = Blueprint("vendors", __name__, url_prefix="/api/vendors")

# In-memory staging area for parsed-but-not-yet-confirmed agreements.
# Keyed by a one-time token so the confirm step doesn't need to re-upload
# or re-parse the PDF; entries are cleared once confirmed or on restart.
_PENDING_AGREEMENTS = {}


def _normalize_name(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


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


# ============================================================================
# Vendors
# ============================================================================

@bp.post("")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def create_vendor():
    """Add a vendor directly, with no agreement attached yet — for when the
    relationship starts before a contract is signed, or the agreement will
    be uploaded separately afterward."""
    payload = request.get_json(silent=True) or {}
    if not payload.get("name", "").strip():
        return jsonify({"message": "Vendor name is required."}), 400

    existing = Vendor.query.filter_by(normalized_name=_normalize_name(payload["name"])).first()
    if existing:
        return jsonify({"message": f"A vendor named '{existing.name}' already exists.", "existing_vendor": existing.to_dict()}), 409

    vendor = Vendor(
        name=payload["name"].strip(),
        normalized_name=_normalize_name(payload["name"]),
        address=payload.get("address"),
        state=payload.get("state"),
        gstin=payload.get("gstin"),
        pan=payload.get("pan"),
        contact_person=payload.get("contact_person"),
        contact_email=payload.get("contact_email"),
        contact_phone=payload.get("contact_phone"),
        bank_name=payload.get("bank_name"),
        bank_account_no=payload.get("bank_account_no"),
        bank_ifsc=payload.get("bank_ifsc"),
        bank_branch=payload.get("bank_branch"),
        created_by=int(get_jwt_identity()),
    )
    db.session.add(vendor)
    db.session.commit()
    return jsonify(vendor.to_dict()), 201


@bp.get("")
@jwt_required()
def list_vendors():
    status = request.args.get("status")
    query = Vendor.query
    if status:
        query = query.filter_by(status=status)
    rows = query.order_by(Vendor.name).all()
    return jsonify([v.to_dict() for v in rows])


@bp.get("/<int:vendor_id>")
@jwt_required()
def get_vendor(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)
    return jsonify(vendor.to_dict(include_agreements=True))


@bp.put("/<int:vendor_id>")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def update_vendor(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)
    payload = request.get_json(silent=True) or {}
    for field in [
        "name", "address", "state", "gstin", "pan", "contact_person",
        "contact_email", "contact_phone", "bank_name", "bank_account_no",
        "bank_ifsc", "bank_branch", "status",
    ]:
        if field in payload:
            setattr(vendor, field, payload[field])
    if "name" in payload:
        vendor.normalized_name = _normalize_name(payload["name"])
    db.session.commit()
    return jsonify(vendor.to_dict())


# ============================================================================
# Agreement upload — parse, detect existing vendor, stage for confirmation
# ============================================================================

@bp.post("/agreements/parse")
@roles_required(*VENDOR_MANAGEMENT_ROLES)
def parse_agreement_upload():
    if "file" not in request.files:
        return jsonify({"message": "No file uploaded."}), 400

    file = request.files["file"]
    original_filename = file.filename

    # Save the file now (into a staging path) so the confirm step doesn't
    # need the browser to re-upload it.
    safe_name = secure_filename(f"{uuid.uuid4().hex[:10]}_{original_filename}")
    rel_path = os.path.join("vendor_agreements", safe_name)
    abs_path = os.path.join(current_app.config["UPLOAD_FOLDER"], rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    file.save(abs_path)

    with open(abs_path, "rb") as fh:
        parsed = parse_agreement(fh)

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
        "file_path": f"/static/uploads/{rel_path}",
        "abs_path": abs_path,
        "parsed": parsed,
    }

    return jsonify({
        "token": token,
        "file_path": f"/static/uploads/{rel_path}",
        "likely_vendor_name": likely_vendor_name,
        "party_a": parsed.get("party_a"),
        "party_b": parsed.get("party_b"),
        "effective_from": parsed.get("effective_from"),
        "effective_to": parsed.get("effective_to"),
        "termination_notice_days": parsed.get("termination_notice_days"),
        "confidentiality_days": parsed.get("confidentiality_days"),
        "feedback_days": parsed.get("feedback_days"),
        "roles": parsed.get("roles"),
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
    payload = request.get_json(silent=True) or {}
    token = payload.get("token")
    staged = _PENDING_AGREEMENTS.get(token)
    if not staged:
        return jsonify({"message": "This upload has expired — please upload the agreement again."}), 400

    actor_id = int(get_jwt_identity())

    vendor_id = payload.get("vendor_id")
    if vendor_id:
        vendor = Vendor.query.get_or_404(vendor_id)
    else:
        new_vendor = payload.get("new_vendor") or {}
        if not new_vendor.get("name"):
            return jsonify({"message": "New vendor requires at least a name."}), 400
        vendor = Vendor(
            name=new_vendor["name"],
            normalized_name=_normalize_name(new_vendor["name"]),
            address=new_vendor.get("address"),
            state=new_vendor.get("state"),
            gstin=new_vendor.get("gstin"),
            pan=new_vendor.get("pan"),
            contact_person=new_vendor.get("contact_person"),
            contact_email=new_vendor.get("contact_email"),
            contact_phone=new_vendor.get("contact_phone"),
            bank_name=new_vendor.get("bank_name"),
            bank_account_no=new_vendor.get("bank_account_no"),
            bank_ifsc=new_vendor.get("bank_ifsc"),
            bank_branch=new_vendor.get("bank_branch"),
            created_by=actor_id,
        )
        db.session.add(vendor)
        db.session.flush()

    agreement = VendorAgreement(
        vendor_id=vendor.id,
        title=payload.get("title") or f"Agreement {payload.get('effective_from', '')}",
        file_path=staged["file_path"],
        effective_from=datetime.strptime(payload["effective_from"], "%Y-%m-%d").date()
        if payload.get("effective_from") else None,
        effective_to=datetime.strptime(payload["effective_to"], "%Y-%m-%d").date()
        if payload.get("effective_to") else None,
        termination_notice_days=payload.get("termination_notice_days", 90),
        confidentiality_days=payload.get("confidentiality_days", 60),
        feedback_days=payload.get("feedback_days", 2),
        parsed_with_ai=staged["parsed"].get("used_ai_fallback", False),
        raw_extracted_text=staged["parsed"].get("raw_text"),
        uploaded_by=actor_id,
    )
    db.session.add(agreement)
    db.session.flush()

    for role in payload.get("roles", []):
        db.session.add(VendorAgreementRole(
            agreement_id=agreement.id,
            role_name=role["role_name"],
            service_fee_pct=role["service_fee_pct"],
            replacement_days=role.get("replacement_days", 30),
            tenure_days=role.get("tenure_days", 60),
        ))

    db.session.commit()
    _PENDING_AGREEMENTS.pop(token, None)

    return jsonify(vendor.to_dict(include_agreements=True)), 201


# ============================================================================
# Vendor hires — assigning a hired person to a vendor rate-card role
# ============================================================================

@bp.get("/hires")
@jwt_required()
def list_hires():
    """With no vendor_id, this is the cross-vendor 'All Placements' list —
    every candidate ever placed with any vendor, direct or contract, kept
    entirely separate from AnametaIOT's own Employees directory."""
    vendor_id = request.args.get("vendor_id", type=int)
    status = request.args.get("status")
    billable_only = request.args.get("billable_only") == "true"
    q = request.args.get("q", "").strip()
    placement_type = request.args.get("placement_type")
    billing_type = request.args.get("billing_type")
    sort = request.args.get("sort", "assigned_desc")

    query = VendorHire.query
    if vendor_id:
        query = query.filter_by(vendor_id=vendor_id)
    if status:
        query = query.filter_by(status=status)
    if placement_type:
        query = query.filter_by(placement_type=placement_type)
    if billing_type:
        query = query.filter_by(billing_type=billing_type)
    if q:
        query = query.filter(VendorHire.candidate_name.ilike(f"%{q}%"))

    sort_map = {
        "assigned_desc": VendorHire.assigned_at.desc(),
        "assigned_asc": VendorHire.assigned_at.asc(),
        "name_asc": VendorHire.candidate_name.asc(),
        "name_desc": VendorHire.candidate_name.desc(),
    }
    rows = query.order_by(sort_map.get(sort, VendorHire.assigned_at.desc())).all()
    data = [h.to_dict() for h in rows]
    if billable_only:
        data = [h for h in data if h["is_billable"]]
    return jsonify(data)


@bp.get("/hires/export")
@jwt_required()
def export_hires():
    """CSV export of the All Placements list, same filters as /hires."""
    import csv
    import io
    from flask import Response

    vendor_id = request.args.get("vendor_id", type=int)
    status = request.args.get("status")
    placement_type = request.args.get("placement_type")
    billing_type = request.args.get("billing_type")
    q = request.args.get("q", "").strip()

    query = VendorHire.query
    if vendor_id:
        query = query.filter_by(vendor_id=vendor_id)
    if status:
        query = query.filter_by(status=status)
    if placement_type:
        query = query.filter_by(placement_type=placement_type)
    if billing_type:
        query = query.filter_by(billing_type=billing_type)
    if q:
        query = query.filter(VendorHire.candidate_name.ilike(f"%{q}%"))
    rows = query.order_by(VendorHire.assigned_at.desc()).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Candidate", "Vendor", "Role", "Placement Type", "Billing Type", "CTC",
        "Tenure Start", "Status", "Has Internal Login", "Assigned On",
    ])
    for h in rows:
        writer.writerow([
            h.candidate_name, h.vendor.name if h.vendor else "", h.role.role_name if h.role else "",
            h.placement_type, h.billing_type, h.ctc, h.tenure_start_date.isoformat(),
            h.status, "Yes" if h.employee_id else "No", h.assigned_at.isoformat(),
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

    if placement_type == "contract" and not employee_id:
        # Create the internal "contract login" — tracked in our tool, but
        # they work for the vendor, not for us.
        email = (payload.get("contract_login_email") or "").strip().lower()
        password = payload.get("contract_login_password")
        if not email or not password:
            return jsonify({"message": "A contract placement needs a login email and password (contract_login_email / contract_login_password)."}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({"message": f"Email '{email}' is already in use by another account."}), 409

        employee_code = None
        for _ in range(5):
            candidate_code = f"CT{uuid.uuid4().hex[:6].upper()}"
            if not User.query.filter_by(employee_code=candidate_code).first():
                employee_code = candidate_code
                break
        if not employee_code:
            return jsonify({"message": "Could not generate a unique contract login code — please try again."}), 500

        contract_user = User(
            employee_code=employee_code, full_name=payload["candidate_name"], email=email,
            role=CONTRACT_EMPLOYEE, date_of_joining=datetime.strptime(payload["tenure_start_date"], "%Y-%m-%d").date(),
        )
        contract_user.set_password(password)
        db.session.add(contract_user)
        db.session.flush()
        employee_id = contract_user.id

    hire = VendorHire(
        vendor_id=payload["vendor_id"],
        agreement_id=payload["agreement_id"],
        agreement_role_id=payload["agreement_role_id"],
        candidate_id=payload.get("candidate_id"),
        employee_id=employee_id,
        candidate_name=payload["candidate_name"],
        ctc=float(payload["ctc"]),
        placement_type=placement_type,
        billing_type=billing_type,
        tenure_start_date=datetime.strptime(payload["tenure_start_date"], "%Y-%m-%d").date(),
        assigned_by=int(get_jwt_identity()),
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

    original.status = "replaced"
    replacement = VendorHire(
        vendor_id=original.vendor_id,
        agreement_id=original.agreement_id,
        agreement_role_id=original.agreement_role_id,
        candidate_id=payload.get("candidate_id"),
        employee_id=payload.get("employee_id"),
        candidate_name=payload["candidate_name"],
        ctc=float(payload.get("ctc", original.ctc)),
        tenure_start_date=datetime.strptime(
            payload.get("tenure_start_date", date.today().isoformat()), "%Y-%m-%d"
        ).date(),
        replacement_of_hire_id=original.id,
        assigned_by=int(get_jwt_identity()),
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
@jwt_required()
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
@jwt_required()
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
