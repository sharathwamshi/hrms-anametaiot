import calendar
import os
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import SalaryStructure, Payslip, User, Attendance, LeaveRequest, SalaryTemplate, Holiday
from app.utils.security import roles_required
from app.utils.payslip_pdf import generate_payslip_pdf
from app.utils.companies import PAYROLL_COMPANIES
from app.roles import (
    PAYROLL_EDIT_ROLES, PAYROLL_VIEW_ROLES, FINANCE_ACCOUNTS, HR_OPERATIONS, EMPLOYEE,
)

bp = Blueprint("payroll", __name__, url_prefix="/api/payroll")

COMPANIES = PAYROLL_COMPANIES
PUBLISHED_STATUSES = {"published", "updated", "paid"}
EMPLOYEE_INFO_FIELDS = (
    "designation", "department", "date_of_joining", "pan", "pf_number",
    "uan_number", "bank_name", "bank_account_number", "pay_mode", "location",
)


def _visible_to_actor(payslip, actor_id, role):
    if role == FINANCE_ACCOUNTS:
        return True
    if (role not in PAYROLL_VIEW_ROLES and role != EMPLOYEE) or payslip.status not in PUBLISHED_STATUSES:
        return False
    return role != EMPLOYEE or payslip.user_id == actor_id


def _decimal_amount(value, label):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a valid non-negative amount.")
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label} must be a valid non-negative amount.")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _component_rows(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list.")
    rows = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"Each {label.lower()} component must be an object.")
        name = str(item.get("name") or "").strip()
        if not name or len(name) > 100:
            raise ValueError("Component names must be between 1 and 100 characters.")
        amount = _decimal_amount(item.get("amount"), name)
        rows.append({"name": name, "amount": float(amount)})
    return rows


def _make_employee_snapshot(user, overrides):
    if not isinstance(overrides, dict):
        raise ValueError("Employee information must be an object.")
    department = user.department.name if user.department else ""
    defaults = {
        "full_name": user.full_name,
        "employee_code": user.employee_code,
        "designation": user.designation or "",
        "department": department,
        "date_of_joining": user.date_of_joining.isoformat() if user.date_of_joining else "",
        "pan": "",
        "pf_number": "",
        "uan_number": user.uan or "",
        "bank_name": "",
        "bank_account_number": "",
        "pay_mode": "",
        "location": "",
    }
    for field in EMPLOYEE_INFO_FIELDS:
        if field in overrides:
            value = str(overrides[field] or "").strip()
            if len(value) > 150:
                raise ValueError(f"{field.replace('_', ' ').title()} must be 150 characters or fewer.")
            if field == "date_of_joining" and value:
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    raise ValueError("Date of joining must use YYYY-MM-DD format.")
            defaults[field] = value
    return defaults


def _validate_period(payload):
    try:
        month = int(payload.get("month"))
        year = int(payload.get("year"))
    except (TypeError, ValueError):
        raise ValueError("Payroll month and year are required.")
    if month < 1 or month > 12 or year < 2000 or year > 2200:
        raise ValueError("Payroll month or year is outside the supported range.")
    return month, year


def _private_pdf_path(key):
    if not key or os.path.isabs(key) or ".." in key.replace("\\", "/").split("/"):
        return None
    folder = os.path.realpath(current_app.config["PAYSLIP_FOLDER"])
    path = os.path.realpath(os.path.join(folder, key))
    return path if os.path.commonpath([folder, path]) == folder else None


def _stored_pdf_path(key):
    if key and key.startswith("/static/uploads/"):
        base = os.path.realpath(current_app.config["UPLOAD_FOLDER"])
        path = os.path.realpath(os.path.join(base, key[len("/static/uploads/"):]))
        return path if os.path.commonpath([base, path]) == base else None
    return _private_pdf_path(key)


def _generate_record_pdf(payslip):
    folder = current_app.config["PAYSLIP_FOLDER"]
    key = f"{payslip.year}/{payslip.month:02d}/{payslip.id}.pdf"
    path = os.path.join(folder, *key.split("/"))
    generate_payslip_pdf(
        path,
        {"company_name": payslip.company_name, "address": ""},
        payslip.employee_info,
        payslip.month,
        payslip.year,
        {},
        payslip.days_present,
        payslip.days_on_leave,
        payslip.lop_days,
        payslip.gross_earnings,
        payslip.total_deductions,
        payslip.net_pay,
        employee_info=payslip.employee_info,
        earnings=payslip.earnings or [],
        deductions=payslip.deductions or [],
        total_working_days=payslip.total_working_days,
        total_paid_days=payslip.total_paid_days,
    )
    payslip.pdf_path = key
    payslip.pdf_is_uploaded = False
    payslip.pdf_filename = f"Payslip_{payslip.year}_{payslip.month:02d}.pdf"


def _apply_payslip_payload(payslip, payload, user):
    month, year = _validate_period(payload)
    requested_company = payload.get("company_name")
    if requested_company not in COMPANIES:
        raise ValueError("Select one of the supported payroll companies.")
    if payslip.id:
        if requested_company != payslip.company_name:
            raise ValueError("A payslip must remain associated with its original company.")
        company_name = payslip.company_name
    else:
        if requested_company != user.company_name:
            raise ValueError("The selected employee is not assigned to this company.")
        company_name = user.company_name
    earnings = _component_rows(payload.get("earnings", []), "Earnings")
    deductions = _component_rows(payload.get("deductions", []), "Deductions")
    gross = sum((Decimal(str(item["amount"])) for item in earnings), Decimal("0"))
    deduction_total = sum((Decimal(str(item["amount"])) for item in deductions), Decimal("0"))
    gross = gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    deduction_total = deduction_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if deduction_total > gross:
        raise ValueError("Total deductions cannot exceed total earnings.")

    def day_value(field, default=0):
        value = _decimal_amount(payload.get(field, default), field.replace("_", " ").title())
        if value > Decimal("31"):
            raise ValueError(f"{field.replace('_', ' ').title()} cannot exceed 31.")
        return float(value)

    total_working = day_value("total_working_days", calendar.monthrange(year, month)[1])
    present = day_value("days_present", 0)
    paid = day_value("total_paid_days", present)
    lop = day_value("lop_days", 0)
    if present > total_working or paid > total_working or lop > total_working:
        raise ValueError("Present, paid, and loss-of-pay days cannot exceed working days.")

    net = (gross - deduction_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    payslip.month = month
    payslip.year = year
    payslip.company_name = company_name
    payslip.employee_info = _make_employee_snapshot(user, payload.get("employee_info", {}))
    payslip.earnings = earnings
    payslip.deductions = deductions
    payslip.total_working_days = total_working
    payslip.total_paid_days = paid
    payslip.days_present = present
    payslip.days_on_leave = max(0, paid - present)
    payslip.lop_days = lop
    payslip.gross_earnings = float(gross)
    payslip.total_deductions = float(deduction_total)
    payslip.net_pay = float(net)

@bp.get("/structure/<int:user_id>")
@roles_required(*PAYROLL_EDIT_ROLES)
def get_structure(user_id):
    structure = SalaryStructure.query.filter_by(user_id=user_id).first()
    if not structure:
        return jsonify({"message": "No salary structure defined for this employee."}), 404
    return jsonify(structure.to_dict())


@bp.get("/insurance/<int:user_id>")
@jwt_required()
def employee_insurance(user_id):
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if actor_id != user_id and role not in (FINANCE_ACCOUNTS, HR_OPERATIONS):
        return jsonify({"message": "You do not have permission to view this insurance information."}), 403
    user = User.query.get_or_404(user_id)
    structure = SalaryStructure.query.filter_by(user_id=user.id).first()
    return jsonify({
        "user_id": user.id,
        "insurance": structure.insurance if structure else 0,
        "effective_from": structure.effective_from.isoformat() if structure and structure.effective_from else None,
    })


@bp.post("/structure/<int:user_id>")
@roles_required(*PAYROLL_EDIT_ROLES)
def upsert_structure(user_id):
    User.query.get_or_404(user_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Salary structure data must be a JSON object."}), 400

    structure = SalaryStructure.query.filter_by(user_id=user_id).first()
    if not structure:
        structure = SalaryStructure(user_id=user_id)
        db.session.add(structure)

    for field in [
        "basic", "hra", "special_allowance", "other_allowance",
        "pf_employee", "esi_employee", "insurance", "professional_tax", "tds",
    ]:
        if field in payload:
            try:
                setattr(structure, field, float(_decimal_amount(payload[field], field.replace("_", " ").title())))
            except ValueError as exc:
                db.session.rollback()
                return jsonify({"message": str(exc)}), 400

    db.session.commit()
    return jsonify(structure.to_dict())


@bp.post("/generate")
@roles_required(*PAYROLL_EDIT_ROLES)
def generate_payslips():
    """Generate draft payslips for all active employees for a given month/year,
    using attendance + approved leave to compute loss-of-pay days."""
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"message": "Payroll parameters must be a JSON object."}), 400
    try:
        month, year = _validate_period({
            "month": payload.get("month") or date.today().month,
            "year": payload.get("year") or date.today().year,
        })
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    generated_by = int(get_jwt_identity())

    days_in_month = calendar.monthrange(year, month)[1]
    holiday_days = Holiday.query.filter(
        db.extract("month", Holiday.holiday_date) == month, db.extract("year", Holiday.holiday_date) == year
    ).count()
    results = []

    for user in User.query.filter_by(is_active=True).all():
        structure = SalaryStructure.query.filter_by(user_id=user.id).first()
        if not structure or structure.is_ctc_only:
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

        paid_days = min(days_in_month, present_days + approved_leave_days + holiday_days)
        lop_days = max(0, days_in_month - paid_days)
        per_day_gross = structure.gross / days_in_month if days_in_month else 0
        lop_deduction = round(per_day_gross * lop_days, 2)

        gross_earnings = round(structure.gross - lop_deduction, 2)
        deductions = [
            {"name": name, "amount": amount}
            for name, amount in (
                ("Provident Fund (PF)", structure.pf_employee),
                ("Employee State Insurance (ESI)", structure.esi_employee),
                ("Insurance", structure.insurance),
                ("Professional Tax", structure.professional_tax),
                ("Income Tax (TDS)", structure.tds),
            )
            if amount
        ]
        raw_deductions = sum(item["amount"] for item in deductions)
        if raw_deductions > gross_earnings and raw_deductions > 0:
            for item in deductions:
                item["amount"] = round(item["amount"] * gross_earnings / raw_deductions, 2)
            if deductions:
                deductions[-1]["amount"] = round(
                    deductions[-1]["amount"] + gross_earnings - sum(item["amount"] for item in deductions), 2
                )
        total_deductions = round(sum(item["amount"] for item in deductions), 2)
        net_pay = round(gross_earnings - total_deductions, 2)

        payslip = Payslip.query.filter_by(user_id=user.id, month=month, year=year).first()
        if payslip and payslip.status in PUBLISHED_STATUSES:
            continue
        if not payslip:
            payslip = Payslip(user_id=user.id, month=month, year=year)
            db.session.add(payslip)

        payslip.days_present = present_days
        payslip.days_on_leave = approved_leave_days
        payslip.lop_days = lop_days
        payslip.gross_earnings = gross_earnings
        payslip.total_deductions = total_deductions
        payslip.net_pay = net_pay
        payslip.status = "draft"
        payslip.generated_by = generated_by
        payslip.company_name = user.company_name
        payslip.total_working_days = days_in_month
        payslip.total_paid_days = paid_days
        payslip.employee_info = _make_employee_snapshot(user, {})
        base_earnings = [
            {"name": name, "amount": amount}
            for name, amount in (
                ("Basic Salary", structure.basic),
                ("House Rent Allowance", structure.hra),
                ("Special Allowance", structure.special_allowance),
                ("Other Earnings", structure.other_allowance),
            )
            if amount
        ]
        base_gross = sum(item["amount"] for item in base_earnings)
        scaled_earnings = []
        for item in base_earnings:
            scaled_earnings.append({
                "name": item["name"],
                "amount": round(item["amount"] * gross_earnings / base_gross, 2) if base_gross else 0,
            })
        if scaled_earnings:
            scaled_earnings[-1]["amount"] = round(
                scaled_earnings[-1]["amount"] + gross_earnings - sum(item["amount"] for item in scaled_earnings), 2
            )
        payslip.earnings = scaled_earnings
        payslip.deductions = deductions
        db.session.flush()

        _generate_record_pdf(payslip)

        results.append(payslip)

    db.session.commit()
    return jsonify([p.to_dict() for p in results])


@bp.get("/coverage")
@roles_required(*PAYROLL_EDIT_ROLES)
def payroll_coverage():
    """Every active in-house user (any role: recruiters, managers, contract logins,
    employees...) with their payroll status for a month. "Run Payroll" silently skips
    anyone without a salary structure, so this is how Finance sees who would be missed.
    Filters: q, role, department_id, payroll (missing | set | processed | paid)."""
    month = request.args.get("month", type=int) or date.today().month
    year = request.args.get("year", type=int) or date.today().year
    q = request.args.get("q", "").strip()
    role = request.args.get("role")
    department_id = request.args.get("department_id", type=int)
    payroll = request.args.get("payroll")
    company_name = request.args.get("company_name")

    query = User.query.filter_by(is_active=True)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(User.full_name.ilike(like), User.employee_code.ilike(like)))
    if role:
        query = query.filter_by(role=role)
    if department_id:
        query = query.filter_by(department_id=department_id)
    if company_name in COMPANIES:
        query = query.filter_by(company_name=company_name)
    elif company_name:
        return jsonify({"message": "Select one of the supported payroll companies."}), 400
    users = query.order_by(User.full_name.asc()).all()

    structures = {
        s.user_id: s
        for s in SalaryStructure.query.all()
        if not s.is_ctc_only
    }
    slips = {p.user_id: p for p in Payslip.query.filter_by(month=month, year=year).all()}
    managers = {u.id: u.full_name for u in User.query.filter(User.id.in_({u.manager_id for u in users if u.manager_id})).all()}

    people = []
    for u in users:
        st, slip = structures.get(u.id), slips.get(u.id)
        state = (
            "paid" if slip and slip.status == "paid"
            else "published" if slip and slip.status in {"published", "updated"}
            else "draft" if slip and slip.status == "draft"
            else "processed" if slip and slip.status == "processed"
            else "set" if st else "missing"
        )
        if payroll and payroll != state:
            continue
        people.append({
            "id": u.id, "full_name": u.full_name, "employee_code": u.employee_code, "email": u.email,
            "role": u.role, "designation": u.designation,
            "company_name": u.company_name,
            "department": u.department.name if u.department else None,
            "manager_name": managers.get(u.manager_id),
            "has_structure": st is not None,
            "monthly_gross": st.gross if st else None,
            "monthly_net": round(st.gross - st.total_deductions, 2) if st else None,
            "payslip_id": slip.id if slip else None,
            "payslip_status": slip.status if slip else None,
            "payroll_state": state,
        })

    # Summary is always over everyone active, regardless of the list filters
    all_active = User.query.filter_by(is_active=True).count()
    missing = User.query.filter_by(is_active=True).filter(~User.id.in_(list(structures) or [0])).count()
    return jsonify({
        "month": month, "year": year, "people": people,
        "summary": {
            "total_active": all_active,
            "with_structure": all_active - missing,
            "missing_structure": missing,
            "payslips_processed": sum(1 for p in slips.values() if p.status == "processed"),
            "payslips_draft": sum(1 for p in slips.values() if p.status == "draft"),
            "payslips_published": sum(1 for p in slips.values() if p.status in {"published", "updated"}),
            "payslips_paid": sum(1 for p in slips.values() if p.status == "paid"),
        },
    })


@bp.get("/companies")
@roles_required(*PAYROLL_VIEW_ROLES, EMPLOYEE)
def list_payroll_companies():
    return jsonify(list(COMPANIES))


@bp.get("/people")
@roles_required(*PAYROLL_EDIT_ROLES)
def payroll_people():
    query = User.query.filter_by(is_active=True)
    company = request.args.get("company_name")
    search = request.args.get("q", "").strip()
    if company in COMPANIES:
        query = query.filter_by(company_name=company)
    elif company:
        return jsonify({"message": "Select one of the supported payroll companies."}), 400
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(User.full_name.ilike(like), User.employee_code.ilike(like)))
    return jsonify([
        {
            "id": user.id,
            "full_name": user.full_name,
            "employee_code": user.employee_code,
            "designation": user.designation,
            "department": user.department.name if user.department else "",
            "date_of_joining": user.date_of_joining.isoformat() if user.date_of_joining else "",
            "uan_number": user.uan or "",
            "company_name": user.company_name,
        }
        for user in query.order_by(User.full_name.asc()).limit(100).all()
    ])


@bp.patch("/people/<int:user_id>/company")
@roles_required(*PAYROLL_EDIT_ROLES)
def assign_payroll_company(user_id):
    user = User.query.get_or_404(user_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("company_name") not in COMPANIES:
        return jsonify({"message": "Select one of the supported payroll companies."}), 400
    user.company_name = payload["company_name"]
    db.session.commit()
    return jsonify({
        "id": user.id,
        "full_name": user.full_name,
        "company_name": user.company_name,
    })


@bp.get("/payslips/<int:user_id>")
@jwt_required()
def employee_payslips(user_id):
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role not in PAYROLL_VIEW_ROLES and role != EMPLOYEE:
        return jsonify({"message": "You do not have permission to view payslips."}), 403
    if role == EMPLOYEE and actor_id != user_id:
        return jsonify({"message": "Employees can only view their own payslips."}), 403
    query = Payslip.query.filter_by(user_id=user_id)
    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    company_name = request.args.get("company_name")
    if month:
        query = query.filter(Payslip.month == month)
    if year:
        query = query.filter(Payslip.year == year)
    if company_name in COMPANIES:
        query = query.filter(Payslip.company_name == company_name)
    elif company_name:
        return jsonify({"message": "Select one of the supported payroll companies."}), 400
    rows = query.order_by(Payslip.year.desc(), Payslip.month.desc()).all()
    return jsonify([
        p.to_dict() for p in rows if _visible_to_actor(p, actor_id, role)
    ])


@bp.get("/payslips")
@jwt_required()
def all_payslips():
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role not in PAYROLL_VIEW_ROLES and role != EMPLOYEE:
        return jsonify({"message": "You do not have permission to view payslips."}), 403
    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    company_name = request.args.get("company_name")
    search = request.args.get("q", "").strip()
    query = Payslip.query.join(User, Payslip.user_id == User.id)
    if role == EMPLOYEE:
        query = query.filter(Payslip.user_id == actor_id)
    if month:
        query = query.filter(Payslip.month == month)
    if year:
        query = query.filter(Payslip.year == year)
    if company_name in COMPANIES:
        query = query.filter(Payslip.company_name == company_name)
    elif company_name:
        return jsonify({"message": "Select one of the supported payroll companies."}), 400
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(User.full_name.ilike(like), User.employee_code.ilike(like)))
    rows = query.order_by(Payslip.year.desc(), Payslip.month.desc(), User.full_name.asc()).all()
    return jsonify([
        p.to_dict() for p in rows if _visible_to_actor(p, actor_id, role)
    ])


@bp.get("/payslip/<int:payslip_id>")
@jwt_required()
def get_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if not _visible_to_actor(payslip, actor_id, role):
        return jsonify({"message": "You do not have permission to view this payslip."}), 403
    return jsonify(payslip.to_dict())


@bp.post("/payslips")
@roles_required(*PAYROLL_EDIT_ROLES)
def create_payslip():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Payslip data must be a JSON object."}), 400
    user = db.session.get(User, payload.get("user_id"))
    if user is None:
        return jsonify({"message": "Employee not found."}), 404
    try:
        month, year = _validate_period(payload)
        if Payslip.query.filter_by(user_id=user.id, month=month, year=year).first():
            return jsonify({"message": "A payslip already exists for this employee and month."}), 409
        payslip = Payslip(
            user_id=user.id,
            generated_by=int(get_jwt_identity()),
            generated_at=datetime.utcnow(),
            status="draft",
        )
        _apply_payslip_payload(payslip, payload, user)
        db.session.add(payslip)
        db.session.flush()
        _generate_record_pdf(payslip)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"message": str(exc)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "A payslip already exists for this employee and month."}), 409
    except OSError:
        db.session.rollback()
        current_app.logger.exception("Payslip PDF could not be stored.")
        return jsonify({"message": "Could not generate the payslip PDF."}), 500
    return jsonify(payslip.to_dict()), 201


@bp.put("/payslips/<int:payslip_id>")
@roles_required(*PAYROLL_EDIT_ROLES)
def update_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Payslip data must be a JSON object."}), 400
    user = db.session.get(User, payslip.user_id)
    old_key = payslip.pdf_path
    try:
        _apply_payslip_payload(payslip, payload, user)
        payslip.status = "updated" if payslip.status in PUBLISHED_STATUSES else "draft"
        payslip.updated_by = int(get_jwt_identity())
        payslip.updated_at = datetime.utcnow()
        _generate_record_pdf(payslip)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"message": str(exc)}), 400
    except OSError:
        db.session.rollback()
        current_app.logger.exception("Payslip PDF could not be stored.")
        return jsonify({"message": "Could not generate the payslip PDF."}), 500
    if old_key != payslip.pdf_path:
        _remove_private_pdf(old_key)
    return jsonify(payslip.to_dict())


def _remove_private_pdf(key):
    path = _private_pdf_path(key)
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            current_app.logger.exception("A replaced payslip PDF could not be removed.")


@bp.delete("/payslips/<int:payslip_id>")
@roles_required(*PAYROLL_EDIT_ROLES)
def delete_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    if payslip.status != "draft":
        return jsonify({"message": "Only draft payslips can be deleted."}), 409
    old_key = payslip.pdf_path
    db.session.delete(payslip)
    db.session.commit()
    _remove_private_pdf(old_key)
    return jsonify({"message": "Draft payslip deleted."})


@bp.post("/payslips/<int:payslip_id>/publish")
@roles_required(*PAYROLL_EDIT_ROLES)
def publish_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    if payslip.status not in {"draft", "published", "updated"}:
        return jsonify({"message": "This payslip cannot be published in its current state."}), 409
    pdf_path = _stored_pdf_path(payslip.pdf_path)
    if not pdf_path or not os.path.isfile(pdf_path):
        return jsonify({"message": "Generate or upload a PDF before publishing this payslip."}), 409
    payslip.status = "updated" if payslip.status in {"published", "updated"} else "published"
    payslip.published_by = int(get_jwt_identity())
    payslip.published_at = datetime.utcnow()
    db.session.commit()
    return jsonify(payslip.to_dict())


@bp.post("/payslips/<int:payslip_id>/upload")
@roles_required(*PAYROLL_EDIT_ROLES)
def upload_payslip_pdf(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"message": "A PDF file is required."}), 400
    filename = secure_filename(file.filename)
    if not filename or os.path.splitext(filename)[1].lower() != ".pdf":
        return jsonify({"message": "Only PDF files are accepted."}), 400
    content = file.stream.read(current_app.config["MAX_PAYSLIP_BYTES"] + 1)
    if not content:
        return jsonify({"message": "The selected PDF is empty."}), 400
    if len(content) > current_app.config["MAX_PAYSLIP_BYTES"]:
        return jsonify({"message": "The PDF exceeds the 10 MB limit."}), 400
    if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-1024:]:
        return jsonify({"message": "The file contents are not a valid PDF."}), 400

    key = f"uploads/{payslip.id}_{uuid.uuid4().hex}.pdf"
    path = _private_pdf_path(key)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as saved_file:
            saved_file.write(content)
    except OSError:
        current_app.logger.exception("Payslip PDF upload could not be stored.")
        return jsonify({"message": "Could not store the uploaded PDF."}), 500
    old_key = payslip.pdf_path
    payslip.pdf_path = key
    payslip.pdf_is_uploaded = True
    payslip.pdf_filename = filename
    if payslip.status in {"published", "updated"}:
        payslip.status = "updated"
    payslip.updated_by = int(get_jwt_identity())
    payslip.updated_at = datetime.utcnow()
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        _remove_private_pdf(key)
        current_app.logger.exception("Payslip PDF metadata could not be saved.")
        return jsonify({"message": "Could not save uploaded PDF metadata."}), 500
    if old_key != key:
        _remove_private_pdf(old_key)
    return jsonify(payslip.to_dict())


@bp.delete("/payslips/<int:payslip_id>/pdf")
@roles_required(*PAYROLL_EDIT_ROLES)
def remove_uploaded_payslip_pdf(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    if not payslip.pdf_is_uploaded:
        return jsonify({"message": "There is no uploaded PDF to remove."}), 409

    old_key = payslip.pdf_path
    try:
        _generate_record_pdf(payslip)
        if payslip.status in PUBLISHED_STATUSES:
            payslip.status = "updated"
        payslip.updated_by = int(get_jwt_identity())
        payslip.updated_at = datetime.utcnow()
        db.session.commit()
    except OSError:
        db.session.rollback()
        current_app.logger.exception("Generated payslip PDF could not replace uploaded PDF.")
        return jsonify({"message": "Could not restore the generated payslip PDF."}), 500
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Payslip PDF removal metadata could not be saved.")
        return jsonify({"message": "Could not remove the uploaded payslip PDF."}), 500

    if old_key != payslip.pdf_path:
        _remove_private_pdf(old_key)
    return jsonify(payslip.to_dict())


@bp.get("/payslips/<int:payslip_id>/pdf")
@jwt_required()
def download_payslip_pdf(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if not _visible_to_actor(payslip, actor_id, role):
        return jsonify({"message": "You do not have permission to download this payslip."}), 403
    path = _stored_pdf_path(payslip.pdf_path)
    if not path or not os.path.isfile(path):
        return jsonify({"message": "Payslip PDF is unavailable."}), 404
    download_name = secure_filename(
        f"{(payslip.employee_info or {}).get('employee_code', payslip.user_id)}_{payslip.year}_{payslip.month:02d}.pdf"
    )
    return send_from_directory(
        os.path.dirname(path),
        os.path.basename(path),
        mimetype="application/pdf",
        as_attachment=request.args.get("inline") != "1",
        download_name=download_name,
    )


@bp.post("/payslips/<int:payslip_id>/mark-paid")
@roles_required(*PAYROLL_EDIT_ROLES)
def mark_paid(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    payslip.status = "paid"
    payslip.published_by = int(get_jwt_identity())
    payslip.published_at = payslip.published_at or datetime.utcnow()
    db.session.commit()
    return jsonify(payslip.to_dict())


# ============================================================================
# Salary templates — Finance defines a reusable % split once, applies it
# to any employee's CTC instead of typing flat numbers each time.
# ============================================================================

@bp.get("/templates")
@roles_required(*PAYROLL_EDIT_ROLES)
def list_templates():
    rows = SalaryTemplate.query.order_by(SalaryTemplate.name).all()
    return jsonify([t.to_dict() for t in rows])


@bp.post("/templates")
@roles_required(*PAYROLL_EDIT_ROLES)
def create_template():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Salary template data must be a JSON object."}), 400
    numeric_fields = [
        "basic_pct", "hra_pct", "special_allowance_pct", "other_allowance_pct",
        "pf_employee_pct", "esi_employee_pct", "insurance_pct",
        "professional_tax_flat", "tds_pct",
    ]
    try:
        for field in numeric_fields:
            if field in payload:
                payload[field] = float(_decimal_amount(payload[field], field.replace("_", " ").title()))
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    if not payload.get("name"):
        return jsonify({"message": "Template name is required."}), 400

    template = SalaryTemplate(
        name=payload["name"], description=payload.get("description"),
        basic_pct=payload.get("basic_pct", 50), hra_pct=payload.get("hra_pct", 20),
        special_allowance_pct=payload.get("special_allowance_pct", 20),
        other_allowance_pct=payload.get("other_allowance_pct", 10),
        pf_employee_pct=payload.get("pf_employee_pct", 6),
        esi_employee_pct=payload.get("esi_employee_pct", 0),
        insurance_pct=payload.get("insurance_pct", 0),
        professional_tax_flat=payload.get("professional_tax_flat", 200),
        tds_pct=payload.get("tds_pct", 0),
        created_by=int(get_jwt_identity()),
    )
    db.session.add(template)
    db.session.commit()
    return jsonify(template.to_dict()), 201


@bp.put("/templates/<int:template_id>")
@roles_required(*PAYROLL_EDIT_ROLES)
def update_template(template_id):
    template = SalaryTemplate.query.get_or_404(template_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Salary template data must be a JSON object."}), 400
    numeric_fields = {
        "basic_pct", "hra_pct", "special_allowance_pct", "other_allowance_pct",
        "pf_employee_pct", "esi_employee_pct", "insurance_pct",
        "professional_tax_flat", "tds_pct",
    }
    try:
        for field in numeric_fields.intersection(payload):
            payload[field] = float(_decimal_amount(payload[field], field.replace("_", " ").title()))
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    for field in [
        "name", "description", "basic_pct", "hra_pct", "special_allowance_pct",
        "other_allowance_pct", "pf_employee_pct", "esi_employee_pct", "insurance_pct",
        "professional_tax_flat", "tds_pct",
    ]:
        if field in payload:
            setattr(template, field, payload[field])
    db.session.commit()
    return jsonify(template.to_dict())


@bp.delete("/templates/<int:template_id>")
@roles_required(*PAYROLL_EDIT_ROLES)
def delete_template(template_id):
    template = SalaryTemplate.query.get_or_404(template_id)
    db.session.delete(template)
    db.session.commit()
    return jsonify({"message": "Template removed."})


@bp.post("/templates/<int:template_id>/apply/<int:user_id>")
@roles_required(*PAYROLL_EDIT_ROLES)
def apply_template(template_id, user_id):
    """Body: { ctc }. Computes Basic/HRA/etc. from the template's percentages
    of the given CTC and upserts the employee's salary structure."""
    template = SalaryTemplate.query.get_or_404(template_id)
    User.query.get_or_404(user_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Template application data must be a JSON object."}), 400
    ctc = payload.get("ctc")
    try:
        ctc = _decimal_amount(ctc, "Annual CTC")
    except ValueError:
        return jsonify({"message": "A positive annual CTC is required."}), 400
    if ctc <= 0:
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
    structure.insurance = round(monthly * template.insurance_pct / 100, 2)
    structure.professional_tax = template.professional_tax_flat
    structure.tds = round(monthly * template.tds_pct / 100, 2)

    db.session.commit()
    return jsonify(structure.to_dict())
