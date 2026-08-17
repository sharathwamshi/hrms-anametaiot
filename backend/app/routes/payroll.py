import calendar
import os
import uuid
from datetime import date
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models import SalaryStructure, Payslip, User, Attendance, LeaveRequest, SalaryTemplate, CompanySettings
from app.utils.security import roles_required
from app.utils.payslip_pdf import generate_payslip_pdf
from app.roles import PAYROLL_ROLES

bp = Blueprint("payroll", __name__, url_prefix="/api/payroll")


@bp.get("/structure/<int:user_id>")
@roles_required(*PAYROLL_ROLES)
def get_structure(user_id):
    structure = SalaryStructure.query.filter_by(user_id=user_id).first()
    if not structure:
        return jsonify({"message": "No salary structure defined for this employee."}), 404
    return jsonify(structure.to_dict())


@bp.post("/structure/<int:user_id>")
@roles_required(*PAYROLL_ROLES)
def upsert_structure(user_id):
    User.query.get_or_404(user_id)
    payload = request.get_json(silent=True) or {}

    structure = SalaryStructure.query.filter_by(user_id=user_id).first()
    if not structure:
        structure = SalaryStructure(user_id=user_id)
        db.session.add(structure)

    for field in [
        "basic", "hra", "special_allowance", "other_allowance",
        "pf_employee", "esi_employee", "professional_tax", "tds",
    ]:
        if field in payload:
            setattr(structure, field, float(payload[field]))

    db.session.commit()
    return jsonify(structure.to_dict())


@bp.post("/generate")
@roles_required(*PAYROLL_ROLES)
def generate_payslips():
    """Generate draft payslips for all active employees for a given month/year,
    using attendance + approved leave to compute loss-of-pay days."""
    payload = request.get_json(silent=True) or {}
    month = int(payload.get("month") or date.today().month)
    year = int(payload.get("year") or date.today().year)
    generated_by = int(get_jwt_identity())

    days_in_month = calendar.monthrange(year, month)[1]
    results = []

    for user in User.query.filter_by(is_active=True).all():
        structure = SalaryStructure.query.filter_by(user_id=user.id).first()
        if not structure:
            continue

        present_days = Attendance.query.filter(
            Attendance.user_id == user.id,
            db.extract("month", Attendance.work_date) == month,
            db.extract("year", Attendance.work_date) == year,
            Attendance.status.in_(["present", "half_day", "regularized"]),
        ).count()

        approved_leave_days = (
            db.session.query(db.func.coalesce(db.func.sum(LeaveRequest.days), 0))
            .filter(
                LeaveRequest.user_id == user.id,
                LeaveRequest.status == "approved",
                db.extract("month", LeaveRequest.start_date) == month,
                db.extract("year", LeaveRequest.start_date) == year,
            )
            .scalar()
        )

        paid_days = min(days_in_month, present_days + approved_leave_days)
        lop_days = max(0, days_in_month - paid_days)
        per_day_gross = structure.gross / days_in_month if days_in_month else 0
        lop_deduction = round(per_day_gross * lop_days, 2)

        gross_earnings = round(structure.gross - lop_deduction, 2)
        total_deductions = structure.total_deductions
        net_pay = round(gross_earnings - total_deductions, 2)

        payslip = Payslip.query.filter_by(user_id=user.id, month=month, year=year).first()
        if not payslip:
            payslip = Payslip(user_id=user.id, month=month, year=year)
            db.session.add(payslip)

        payslip.days_present = present_days
        payslip.days_on_leave = approved_leave_days
        payslip.lop_days = lop_days
        payslip.gross_earnings = gross_earnings
        payslip.total_deductions = total_deductions
        payslip.net_pay = net_pay
        payslip.status = "processed"
        payslip.generated_by = generated_by
        db.session.flush()

        company = CompanySettings.query.first()
        filename = f"payslip_{user.id}_{year}_{month:02d}_{uuid.uuid4().hex[:6]}.pdf"
        rel_path = os.path.join("payslips", filename)
        abs_path = os.path.join(current_app.config["UPLOAD_FOLDER"], rel_path)
        generate_payslip_pdf(
            abs_path,
            {"company_name": company.company_name if company else "AnametaIOT", "address": company.address if company else ""},
            {"full_name": user.full_name, "employee_code": user.employee_code,
             "designation": user.designation, "department": user.department.name if user.department else None},
            month, year, structure.to_dict(),
            present_days, approved_leave_days, lop_days,
            gross_earnings, total_deductions, net_pay,
        )
        payslip.pdf_path = f"/static/uploads/{rel_path}"

        results.append(payslip)

    db.session.commit()
    return jsonify([p.to_dict() for p in results])


@bp.get("/payslips/<int:user_id>")
@jwt_required()
def employee_payslips(user_id):
    rows = (
        Payslip.query.filter_by(user_id=user_id)
        .order_by(Payslip.year.desc(), Payslip.month.desc())
        .all()
    )
    return jsonify([p.to_dict() for p in rows])


@bp.get("/payslips")
@roles_required(*PAYROLL_ROLES)
def all_payslips():
    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    query = Payslip.query
    if month:
        query = query.filter_by(month=month)
    if year:
        query = query.filter_by(year=year)
    rows = query.order_by(Payslip.year.desc(), Payslip.month.desc()).all()
    return jsonify([p.to_dict() for p in rows])


@bp.post("/payslips/<int:payslip_id>/mark-paid")
@roles_required(*PAYROLL_ROLES)
def mark_paid(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    payslip.status = "paid"
    db.session.commit()
    return jsonify(payslip.to_dict())


# ============================================================================
# Salary templates — Finance defines a reusable % split once, applies it
# to any employee's CTC instead of typing flat numbers each time.
# ============================================================================

@bp.get("/templates")
@jwt_required()
def list_templates():
    rows = SalaryTemplate.query.order_by(SalaryTemplate.name).all()
    return jsonify([t.to_dict() for t in rows])


@bp.post("/templates")
@roles_required(*PAYROLL_ROLES)
def create_template():
    payload = request.get_json(silent=True) or {}
    if not payload.get("name"):
        return jsonify({"message": "Template name is required."}), 400

    template = SalaryTemplate(
        name=payload["name"], description=payload.get("description"),
        basic_pct=payload.get("basic_pct", 50), hra_pct=payload.get("hra_pct", 20),
        special_allowance_pct=payload.get("special_allowance_pct", 20),
        other_allowance_pct=payload.get("other_allowance_pct", 10),
        pf_employee_pct=payload.get("pf_employee_pct", 6),
        esi_employee_pct=payload.get("esi_employee_pct", 0),
        professional_tax_flat=payload.get("professional_tax_flat", 200),
        tds_pct=payload.get("tds_pct", 0),
        created_by=int(get_jwt_identity()),
    )
    db.session.add(template)
    db.session.commit()
    return jsonify(template.to_dict()), 201


@bp.put("/templates/<int:template_id>")
@roles_required(*PAYROLL_ROLES)
def update_template(template_id):
    template = SalaryTemplate.query.get_or_404(template_id)
    payload = request.get_json(silent=True) or {}
    for field in [
        "name", "description", "basic_pct", "hra_pct", "special_allowance_pct",
        "other_allowance_pct", "pf_employee_pct", "esi_employee_pct",
        "professional_tax_flat", "tds_pct",
    ]:
        if field in payload:
            setattr(template, field, payload[field])
    db.session.commit()
    return jsonify(template.to_dict())


@bp.delete("/templates/<int:template_id>")
@roles_required(*PAYROLL_ROLES)
def delete_template(template_id):
    template = SalaryTemplate.query.get_or_404(template_id)
    db.session.delete(template)
    db.session.commit()
    return jsonify({"message": "Template removed."})


@bp.post("/templates/<int:template_id>/apply/<int:user_id>")
@roles_required(*PAYROLL_ROLES)
def apply_template(template_id, user_id):
    """Body: { ctc }. Computes Basic/HRA/etc. from the template's percentages
    of the given CTC and upserts the employee's salary structure."""
    template = SalaryTemplate.query.get_or_404(template_id)
    User.query.get_or_404(user_id)
    payload = request.get_json(silent=True) or {}
    ctc = payload.get("ctc")
    if not ctc or float(ctc) <= 0:
        return jsonify({"message": "A positive annual CTC is required."}), 400
    ctc = float(ctc)
    monthly = ctc / 12

    structure = SalaryStructure.query.filter_by(user_id=user_id).first()
    if not structure:
        structure = SalaryStructure(user_id=user_id)
        db.session.add(structure)

    structure.basic = round(monthly * template.basic_pct / 100, 2)
    structure.hra = round(monthly * template.hra_pct / 100, 2)
    structure.special_allowance = round(monthly * template.special_allowance_pct / 100, 2)
    structure.other_allowance = round(monthly * template.other_allowance_pct / 100, 2)
    structure.pf_employee = round(monthly * template.pf_employee_pct / 100, 2)
    structure.esi_employee = round(monthly * template.esi_employee_pct / 100, 2)
    structure.professional_tax = template.professional_tax_flat
    structure.tds = round(monthly * template.tds_pct / 100, 2)

    db.session.commit()
    return jsonify(structure.to_dict())
