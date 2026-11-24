import calendar
import copy
import io
import os
import re
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import SimpleNamespace
from flask import Blueprint, request, jsonify, current_app, send_file, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError

from app.extensions import db
from app.models import (
    SalaryStructure, Payslip, User, Attendance, LeaveRequest, SalaryTemplate, Holiday,
    CompanyPayslipTemplate, PayslipRevision, PayrollAuditLog, Department,
)
from app.utils.security import roles_required
from app.utils.compensation import normalize_annual_ctc
from app.utils.reference_payslip_pdf import generate_reference_payslip_pdf
from app.utils.companies import PAYROLL_COMPANIES
from app.utils.payslip_templates import default_company_template, EMPLOYEE_CATEGORIES
from app.utils.push import send_push
from app.roles import (
    PAYROLL_EDIT_ROLES, PAYROLL_VIEW_ROLES, FINANCE_ACCOUNTS, OPERATIONS, MANAGER,
    EMPLOYEE, CONTRACT_EMPLOYEE,
)

bp = Blueprint("payroll", __name__, url_prefix="/api/payroll")

COMPANIES = PAYROLL_COMPANIES
SALARY_STRUCTURE_EDIT_ROLES = (FINANCE_ACCOUNTS, OPERATIONS)
SALARY_STRUCTURE_ACTIVITY_ACTIONS = {
    "annual_ctc_updated",
    "employee_salary_override_updated",
    "salary_structure_assigned",
    "salary_structure_published",
    "salary_structure_unassigned",
    "salary_structure_updated",
    "salary_template_applied",
    "salary_template_updated",
}
PUBLISHED_STATUSES = {"published", "updated", "paid"}
EMPLOYEE_INFO_FIELDS = (
    "designation", "department", "date_of_joining", "pan", "pf_number",
    "uan_number", "bank_name", "bank_account_name", "bank_account_number",
    "pay_mode", "location",
)


def _visible_to_actor(payslip, actor_id, role):
    if role in PAYROLL_EDIT_ROLES:
        return True
    if (role not in PAYROLL_VIEW_ROLES and role != EMPLOYEE) or payslip.status not in PUBLISHED_STATUSES:
        return False
    if role in (EMPLOYEE, CONTRACT_EMPLOYEE):
        return payslip.user_id == actor_id
    if role == MANAGER:
        employee = db.session.get(User, payslip.user_id)
        return bool(employee and (employee.id == actor_id or employee.manager_id == actor_id))
    return True


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
        "annual_ctc": float(user.salary_structure.annual_ctc) if user.salary_structure and user.salary_structure.annual_ctc is not None else None,
        "designation": user.designation or "",
        "department": department,
        "date_of_joining": user.date_of_joining.isoformat() if user.date_of_joining else "",
        "pan": getattr(user, "pan", None) or "",
        "pf_number": getattr(user, "pf_number", None) or "",
        "uan_number": user.uan or "",
        "bank_name": getattr(user, "bank_name", None) or "",
        "bank_account_name": user.bank_account_name or "",
        "bank_account_number": getattr(user, "bank_account_number", None) or "",
        "employment_type": EMPLOYEE_CATEGORIES.get(user.employee_category, ""),
        "employee_category": user.employee_category or "",
        "pay_mode": getattr(user, "pay_mode", None) or "",
        "location": getattr(user, "location", None) or "",
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


def _company_template(company_name):
    template = CompanyPayslipTemplate.query.filter_by(company_name=company_name).first()
    return template.to_dict() if template else default_company_template(company_name)


def _payslip_snapshot(payslip):
    return {
        "user_id": payslip.user_id,
        "month": payslip.month,
        "year": payslip.year,
        "company_name": payslip.company_name,
        "employee_info": copy.deepcopy(payslip.employee_info or {}),
        "earnings": copy.deepcopy(payslip.earnings or []),
        "deductions": copy.deepcopy(payslip.deductions or []),
        "days_present": payslip.days_present,
        "days_on_leave": payslip.days_on_leave,
        "lop_days": payslip.lop_days,
        "total_working_days": payslip.total_working_days,
        "total_paid_days": payslip.total_paid_days,
        "gross_earnings": payslip.gross_earnings,
        "total_deductions": payslip.total_deductions,
        "net_pay": payslip.net_pay,
        "status": payslip.status,
        "pdf_path": payslip.pdf_path,
        "template_snapshot": copy.deepcopy(payslip.template_snapshot or {}),
    }


def _payslip_revision_counts(payslips):
    payslip_ids = [payslip.id for payslip in payslips if payslip.id is not None]
    if not payslip_ids:
        return {}
    rows = db.session.query(
        PayslipRevision.payslip_id,
        db.func.count(PayslipRevision.id),
    ).filter(PayslipRevision.payslip_id.in_(payslip_ids)).group_by(
        PayslipRevision.payslip_id,
    ).all()
    return dict(rows)


def _serialize_payslips(payslips):
    rows = list(payslips)
    revision_counts = _payslip_revision_counts(rows)
    return [
        payslip.to_dict(revision_count=revision_counts.get(payslip.id, 0))
        for payslip in rows
    ]


def _record_revision(payslip, actor_id, action, snapshot=None):
    revision = db.session.query(db.func.max(PayslipRevision.revision)).filter_by(
        payslip_id=payslip.id,
    ).scalar() or 0
    db.session.add(PayslipRevision(
        payslip_id=payslip.id,
        revision=revision + 1,
        action=action,
        actor_id=actor_id,
        snapshot=copy.deepcopy(snapshot if snapshot is not None else _payslip_snapshot(payslip)),
    ))


def _record_payroll_audit(employee_id, actor_id, action, previous=None, new=None, payslip_id=None):
    event = PayrollAuditLog(
        employee_id=employee_id,
        payslip_id=payslip_id,
        actor_id=actor_id,
        action=action,
        previous_values=copy.deepcopy(previous) if previous is not None else None,
        new_values=copy.deepcopy(new) if new is not None else None,
    )
    db.session.add(event)
    return event


def _salary_structure_activity_by_employee(employee_ids):
    employee_ids = list(employee_ids)
    if not employee_ids:
        return {}
    events = PayrollAuditLog.query.filter(
        PayrollAuditLog.employee_id.in_(employee_ids),
        PayrollAuditLog.action.in_(SALARY_STRUCTURE_ACTIVITY_ACTIONS),
        PayrollAuditLog.payslip_id.is_(None),
    ).order_by(PayrollAuditLog.created_at.asc(), PayrollAuditLog.id.asc()).all()
    return {event.employee_id: event for event in events}


def _published_salary_structure_state(activity, template_id):
    if (
        activity is None
        or activity.action != "salary_structure_published"
        or not isinstance(activity.new_values, dict)
        or activity.new_values.get("salary_template_id") != template_id
    ):
        return None
    return {
        "published_at": activity.created_at.isoformat() if activity.created_at else None,
        "published_by": activity.actor_id,
    }


def _salary_component_rows(structure, template, category):
    names = list(template[f"{category}_components"])
    required = (
        ("Basic Salary", "HRA", "Special Allowance", "Other Allowance")
        if category == "earnings"
        else ("Employee PF", "Insurance", "Professional Tax", "TDS", "Employee ESI")
    )
    existing_names = {_canonical_component(name) for name in names}
    for name in required:
        if _canonical_component(name) not in existing_names:
            names.append(name)
            existing_names.add(_canonical_component(name))
    if structure is None:
        return [{"name": name, "amount": 0} for name in names]
    if category == "earnings":
        fixed = {
            "basic pay": structure.basic,
            "basic salary": structure.basic,
            "hra": structure.hra,
            "house rent allowance": structure.hra,
            "special allowance": structure.special_allowance,
            "other earnings": structure.other_allowance,
            "other allowance": structure.other_allowance,
        }
        custom = structure.custom_earnings or []
    else:
        fixed = {
            "pf": structure.pf_employee,
            "employee pf": structure.pf_employee,
            "provident fund": structure.pf_employee,
            "provident fund (pf)": structure.pf_employee,
            "esi": structure.esi_employee,
            "employee esi": structure.esi_employee,
            "employee state insurance (esi)": structure.esi_employee,
            "professional tax": structure.professional_tax,
            "tds": structure.tds,
            "income tax (tds)": structure.tds,
            "insurance": structure.insurance,
        }
        custom = structure.custom_deductions or []
    custom_amounts = {
        re.sub(r"\s+", " ", str(item.get("name", "")).strip().lower()): float(item.get("amount") or 0)
        for item in custom
    }
    return [
        {
            "name": name,
            "amount": round(float(fixed.get(name.strip().lower(), custom_amounts.get(name.strip().lower(), 0)) or 0), 2),
        }
        for name in names
    ]


def _canonical_component(name):
    normalized = re.sub(r"\s+", " ", str(name or "").strip().lower())
    return {
        "basic pay": "basic salary",
        "hra": "hra",
        "house rent allowance": "hra",
        "other earnings": "other allowance",
        "pf": "employee pf",
        "provident fund": "employee pf",
        "provident fund (pf)": "employee pf",
        "employee provident fund": "employee pf",
        "esi": "employee esi",
        "employee state insurance": "employee esi",
        "employee state insurance (esi)": "employee esi",
        "income tax (tds)": "tds",
    }.get(normalized, normalized)


def _financial_year_start(year, month):
    return year if month >= 4 else year - 1


def _period_payslips(user_id, start_year, start_month, month, year):
    return Payslip.query.filter(
        Payslip.user_id == user_id,
        db.or_(
            Payslip.year > start_year,
            db.and_(Payslip.year == start_year, Payslip.month >= start_month),
        ),
        db.or_(
            Payslip.year < year,
            db.and_(Payslip.year == year, Payslip.month <= month),
        ),
    ).all()


def _component_totals(payslips):
    totals = {"earnings": {}, "deductions": {}}
    for payslip in payslips:
        for category in totals:
            for item in getattr(payslip, category) or []:
                key = _canonical_component(item.get("name"))
                totals[category][key] = totals[category].get(key, 0) + float(item.get("amount") or 0)
    return totals


def _template_arrears_by_employee(salary_template):
    arrears_by_employee = getattr(salary_template, "arrears_by_employee", None) or {}
    if arrears_by_employee:
        return {str(employee_id): values for employee_id, values in arrears_by_employee.items()}
    employee_id = getattr(salary_template, "arrears_employee_id", None)
    amount = getattr(salary_template, "arrears_amount", None)
    if employee_id and amount:
        return {
            str(employee_id): {
                "description": salary_template.arrears_description or "",
                "amount": amount,
            },
        }
    return {}


def _salary_structure_rows(structure, user_id, month, year):
    start_year = _financial_year_start(year, month)
    records = _period_payslips(user_id, start_year, 4, month, year)
    ytd_totals = _component_totals(records)
    mtd_totals = _component_totals([
        payslip for payslip in records if payslip.year == year and payslip.month == month
    ])
    configured = {
        "basic salary": ("earnings", structure.basic),
        "hra": ("earnings", structure.hra),
        "special allowance": ("earnings", structure.special_allowance),
        "other allowance": ("earnings", structure.other_allowance),
        "employee pf": ("deductions", structure.pf_employee),
        "insurance": ("deductions", structure.insurance),
        "professional tax": ("deductions", structure.professional_tax),
        "tds": ("deductions", structure.tds),
        "employee esi": ("deductions", structure.esi_employee),
    }
    labels = {
        "basic salary": "Basic Salary",
        "hra": "HRA",
        "special allowance": "Special Allowance",
        "other allowance": "Other Allowance",
        "employee pf": "Employee PF",
        "insurance": "Insurance",
        "professional tax": "Professional Tax",
        "tds": "TDS",
        "employee esi": "Employee ESI",
    }
    rows = []
    for key, (category, amount) in configured.items():
        rows.append({
            "name": labels[key],
            "amount": round(float(amount or 0), 2),
            "ytd": round(ytd_totals[category].get(key, 0), 2),
            "mtd": round(mtd_totals[category].get(key, 0), 2),
        })
    return rows


def _payslip_rows_with_ytd_mtd(payslip):
    start_year = _financial_year_start(payslip.year, payslip.month)
    records = _period_payslips(payslip.user_id, start_year, 4, payslip.month, payslip.year)
    records = [row for row in records if row.id != payslip.id]
    ytd_totals = _component_totals(records)
    mtd_totals = _component_totals([
        row for row in records if row.year == payslip.year and row.month == payslip.month
    ])
    result = {}
    for category in ("earnings", "deductions"):
        result[category] = []
        for item in getattr(payslip, category) or []:
            key = _canonical_component(item.get("name"))
            amount = float(item.get("amount") or 0)
            result[category].append({
                **item,
                "ytd": round(ytd_totals[category].get(key, 0) + amount, 2),
                "mtd": round(mtd_totals[category].get(key, 0) + amount, 2),
            })
    return result


def _attendance_for_period(user_id, month, year):
    days_in_month = calendar.monthrange(year, month)[1]
    holiday_days = Holiday.query.filter(
        db.extract("month", Holiday.holiday_date) == month,
        db.extract("year", Holiday.holiday_date) == year,
    ).count()
    present_days = Attendance.query.filter(
        Attendance.user_id == user_id,
        db.extract("month", Attendance.work_date) == month,
        db.extract("year", Attendance.work_date) == year,
        Attendance.status.in_(["present", "half_day", "regularized"]),
    ).count()
    approved_leave_days = (
        db.session.query(db.func.coalesce(db.func.sum(LeaveRequest.days), 0))
        .filter(
            LeaveRequest.user_id == user_id,
            LeaveRequest.status == "approved",
            db.extract("month", LeaveRequest.start_date) == month,
            db.extract("year", LeaveRequest.start_date) == year,
        )
        .scalar()
    )
    paid_days = min(days_in_month, present_days + approved_leave_days + holiday_days)
    return {
        "days_in_month": days_in_month,
        "present_days": present_days,
        "leave_days": float(approved_leave_days or 0),
        "paid_days": paid_days,
        "lop_days": max(0, days_in_month - paid_days),
    }


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
    key = f"{payslip.year}/{payslip.month:02d}/{payslip.id}_{uuid.uuid4().hex}.pdf"
    path = os.path.join(folder, *key.split("/"))
    template = payslip.template_snapshot or _company_template(payslip.company_name)
    salary_rows = _payslip_rows_with_ytd_mtd(payslip)
    try:
        generate_reference_payslip_pdf(
            path,
            template=template,
            employee_info=payslip.employee_info or {},
            month=payslip.month,
            year=payslip.year,
            earnings=salary_rows["earnings"],
            deductions=salary_rows["deductions"],
            days_present=payslip.days_present or 0,
            days_on_leave=payslip.days_on_leave or 0,
            lop_days=payslip.lop_days or 0,
            total_working_days=payslip.total_working_days or calendar.monthrange(payslip.year, payslip.month)[1],
            total_paid_days=payslip.total_paid_days or 0,
            gross_earnings=payslip.gross_earnings or 0,
            total_deductions=payslip.total_deductions or 0,
            net_pay=payslip.net_pay or 0,
        )
    except (OSError, ValueError):
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                current_app.logger.exception("A partial payslip PDF could not be removed.")
        raise
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
        requested_category = payload.get("employee_category")
        if requested_category is not None and (
            requested_category not in EMPLOYEE_CATEGORIES
            or requested_category != user.employee_category
        ):
            raise ValueError("The selected employee does not match the selected category.")
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
    employee_info = _make_employee_snapshot(user, payload.get("employee_info", {}))
    source_employee_info = payload.get("employee_info", {})
    structure = SalaryStructure.query.filter_by(user_id=user.id).first()
    salary_structure_name = (
        source_employee_info.get("salary_structure_name")
        if isinstance(source_employee_info, dict) else None
    ) or (structure.salary_template.name if structure and structure.salary_template else None)
    if salary_structure_name:
        employee_info["salary_structure_name"] = str(salary_structure_name)[:100]
    payslip.employee_info = employee_info
    if not payslip.template_snapshot:
        payslip.template_snapshot = _company_template(company_name)
    payslip.earnings = earnings
    payslip.deductions = deductions
    payslip.total_working_days = total_working
    payslip.total_paid_days = paid
    payslip.days_present = present
    payslip.days_on_leave = _attendance_for_period(user.id, month, year)["leave_days"]
    payslip.lop_days = lop
    payslip.gross_earnings = float(gross)
    payslip.total_deductions = float(deduction_total)
    payslip.net_pay = float(net)


def _preview_payload_for_user(
    user, month, year, salary_template_override=None, allow_deductions_over_gross=False,
):
    template = _company_template(user.company_name)
    structure = SalaryStructure.query.filter_by(user_id=user.id).first()
    if not template or not structure or (
        salary_template_override is None
        and not structure.salary_template
        and structure.is_ctc_only
    ):
        raise ValueError(f"{user.full_name} needs a complete salary structure before payslips can be generated.")
    attendance = _attendance_for_period(user.id, month, year)
    salary_template = salary_template_override or structure.salary_template
    if salary_template:
        if salary_template.company_name != user.company_name:
            raise ValueError(f"{user.full_name}'s salary structure belongs to another company.")
        ctc = Decimal(str(structure.annual_ctc or 0))
        if ctc <= 0:
            raise ValueError(f"{user.full_name} needs a positive Annual CTC before payslips can be generated.")
        overrides = structure.employee_overrides or {}
        percentages = overrides.get("component_percentages") or {}
        monthly_ctc = ctc / Decimal(12)

        def money(value):
            return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        def percentage(field):
            value = percentages.get(field, getattr(salary_template, field))
            parsed = _decimal_amount(value, field.replace("_", " ").title())
            if parsed > 100:
                raise ValueError(f"{field.replace('_', ' ').title()} must not exceed 100%.")
            return parsed

        def amount_override(field, fallback):
            return money(overrides.get(field, fallback))

        basic = money(monthly_ctc * percentage("basic_pct") / 100)
        era = money(monthly_ctc * percentage("hra_pct") / 100)
        special = money(monthly_ctc * percentage("special_allowance_pct") / 100)
        other = money(monthly_ctc * percentage("other_allowance_pct") / 100)
        transport = amount_override("transport_flat", salary_template.transport_flat)
        earnings = [
            {"name": name, "amount": float(value)}
            for name, value in (
                ("Basic Salary", basic), ("ERA", era), ("Special Allowance", special),
                ("Other Allowance", other), ("Transport", transport),
            )
        ]
        custom_earnings = _component_rows(structure.custom_earnings or [], "Earnings")
        earnings.extend(custom_earnings)
        arrears = _template_arrears_by_employee(salary_template).get(str(user.id))
        if arrears and salary_template.arrears_month == month and salary_template.arrears_year == year:
            arrears_period = f"{calendar.month_name[month]} {year}"
            earnings.append({
                "name": f"Arrears - {arrears['description']} ({arrears_period})",
                "amount": float(money(arrears["amount"])),
            })
        gross = sum((money(item["amount"]) for item in earnings), Decimal("0"))

        insurance_months = salary_template.insurance_months or []
        insurance_amounts = salary_template.insurance_amounts or {}
        employee_insurance = overrides.get("insurance_amounts") or {}
        insurance = 0
        if month in insurance_months or str(month) in insurance_months:
            insurance = employee_insurance.get(str(month), employee_insurance.get(month, insurance_amounts.get(str(month), 0)))

        employee_pf_rate = amount_override(
            "employee_pf_rate_pct", salary_template.employee_pf_rate_pct,
        )
        employer_pf = amount_override("employer_pf_flat", salary_template.employer_pf_flat)
        deductions = [
            {"name": name, "amount": float(value)}
            for name, value in (
                ("Employee PF", money(basic * employee_pf_rate / 100)),
                ("Insurance", money(insurance)),
                ("Professional Tax", amount_override("professional_tax_flat", salary_template.professional_tax_flat)),
                ("TDS", amount_override("tds_flat", salary_template.tds_flat)),
                ("Employer PF", employer_pf),
            )
        ]
        deductions.extend(_component_rows(structure.custom_deductions or [], "Deductions"))
        lop_amount = money(
            gross * Decimal(str(attendance["lop_days"])) / Decimal(str(attendance["days_in_month"]))
        ) if attendance["days_in_month"] else Decimal("0")
        deductions.append({"name": "Absent", "amount": float(lop_amount)})
        deduction_total = sum((money(item["amount"]) for item in deductions), Decimal("0"))
        if deduction_total > gross and not allow_deductions_over_gross:
            raise ValueError(f"{user.full_name}'s total deductions exceed gross earnings.")
        employee_info = _make_employee_snapshot(user, {})
        employee_info["salary_structure_name"] = salary_template.name
        return {
            "user_id": user.id,
            "month": month,
            "year": year,
            "company_name": user.company_name,
            "employee_info": employee_info,
            "template_snapshot": template,
            "earnings": earnings,
            "deductions": deductions,
            "gross_earnings": float(gross),
            "total_deductions": float(deduction_total),
            "net_pay": float(gross - deduction_total),
            "days_present": attendance["present_days"],
            "days_on_leave": attendance["leave_days"],
            "lop_days": attendance["lop_days"],
            "total_working_days": attendance["days_in_month"],
            "total_paid_days": attendance["paid_days"],
        }

    earnings = _salary_component_rows(structure, template, "earnings")
    deductions = _salary_component_rows(structure, template, "deductions")
    total_days = attendance["days_in_month"]
    factor = Decimal(attendance["paid_days"]) / Decimal(total_days) if total_days else Decimal("0")
    prorated = [
        {"name": item["name"], "amount": float(
            (Decimal(str(item["amount"])) * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )}
        for item in earnings
    ]
    gross = sum(Decimal(str(item["amount"])) for item in prorated)
    if prorated:
        prorated[-1]["amount"] = float(
            Decimal(str(prorated[-1]["amount"])) + gross - sum(Decimal(str(item["amount"])) for item in prorated)
        )
    deduction_total = sum(Decimal(str(item["amount"])) for item in deductions)
    if deduction_total > gross:
        raise ValueError(f"{user.full_name}'s total deductions exceed gross earnings.")
    return {
        "user_id": user.id,
        "month": month,
        "year": year,
        "company_name": user.company_name,
        "employee_info": _make_employee_snapshot(user, {}),
        "template_snapshot": template,
        "earnings": prorated,
        "deductions": deductions,
        "gross_earnings": float(gross),
        "total_deductions": float(deduction_total),
        "net_pay": float(gross - deduction_total),
        "days_present": attendance["present_days"],
        "days_on_leave": attendance["leave_days"],
        "lop_days": attendance["lop_days"],
        "total_working_days": total_days,
        "total_paid_days": attendance["paid_days"],
    }


def _template_preview_response(user, month, year, preview):
    start_year = _financial_year_start(year, month)
    records = _period_payslips(user.id, start_year, 4, month, year)
    ytd_totals = _component_totals(records)
    mtd_totals = _component_totals([
        record for record in records if record.year == year and record.month == month
    ])
    components = []
    for category in ("earnings", "deductions"):
        for item in preview[category]:
            key = _canonical_component(item["name"])
            components.append({
                "category": category,
                "name": item["name"],
                "projected": item["amount"],
                "ytd": round(ytd_totals[category].get(key, 0), 2),
                "mtd": round(mtd_totals[category].get(key, 0), 2),
            })
    return {
        "month": month,
        "year": year,
        "has_current_month_payslip": Payslip.query.filter_by(
            user_id=user.id, month=month, year=year,
        ).first() is not None,
        "salary_structure_name": preview["employee_info"].get("salary_structure_name"),
        "employee_info": preview["employee_info"],
        "components": components,
    }


def _batch_users(payload):
    try:
        month, year = _validate_period(payload)
    except ValueError:
        raise
    company = payload.get("company_name")
    category = payload.get("employee_category")
    salary_template_id = payload.get("salary_template_id")
    if company not in COMPANIES:
        raise ValueError("Select one of the supported payroll companies.")
    if category and category not in EMPLOYEE_CATEGORIES:
        raise ValueError("Select Full Time, Part Time, or Internship.")
    if not category and not salary_template_id:
        raise ValueError("Select an employee category.")
    salary_template = None
    if salary_template_id is not None:
        if isinstance(salary_template_id, bool):
            raise ValueError("Salary structure ID must be an integer.")
        try:
            salary_template_id = int(salary_template_id)
        except (TypeError, ValueError):
            raise ValueError("Salary structure ID must be an integer.")
        salary_template = db.session.get(SalaryTemplate, salary_template_id)
        if salary_template is None or salary_template.company_name != company:
            raise ValueError("Select a salary structure for the selected company.")
    raw_ids = payload.get("user_ids")
    if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 200:
        raise ValueError("Select between 1 and 200 employees.")
    try:
        user_ids = [int(value) for value in raw_ids]
    except (TypeError, ValueError):
        raise ValueError("Employee IDs must be integers.")
    if any(isinstance(value, bool) for value in raw_ids) or len(set(user_ids)) != len(user_ids):
        raise ValueError("Employee selection must contain unique employee IDs.")
    users = User.query.filter(User.id.in_(user_ids), User.is_active.is_(True)).all()
    if len(users) != len(user_ids):
        raise ValueError("One or more selected employees are missing or inactive.")
    users_by_id = {user.id: user for user in users}
    users = [users_by_id[user_id] for user_id in user_ids]
    if any(
        user.company_name != company
        or (category and user.employee_category != category)
        or (
            salary_template
            and not SalaryStructure.query.filter_by(
                user_id=user.id, salary_template_id=salary_template.id,
            ).first()
        )
        for user in users
    ):
        raise ValueError("Every selected employee must match the selected company, category, and salary structure.")
    if salary_template:
        arrears_employee_ids = set(_template_arrears_by_employee(salary_template))
        if arrears_employee_ids and any(str(user_id) not in arrears_employee_ids for user_id in user_ids):
            raise ValueError("This arrears template can only be used for employees selected for arrears.")
    duplicates = Payslip.query.filter(
        Payslip.user_id.in_(user_ids), Payslip.month == month, Payslip.year == year,
    ).with_entities(Payslip.user_id).all()
    if duplicates:
        raise ValueError("A payslip already exists for one or more selected employees in this month.")
    missing_structure = [
        user.id for user in users
        if (structure := SalaryStructure.query.filter_by(user_id=user.id).first()) is None
        or (structure.is_ctc_only and not structure.salary_template)
    ]
    if missing_structure:
        raise ValueError(
            "Set up complete salary structures for all selected employees before generating payslips: "
            + ", ".join(str(user_id) for user_id in missing_structure)
        )
    return users, month, year


@bp.post("/preview")
@roles_required(*PAYROLL_EDIT_ROLES)
def preview_payslip():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Payslip preview data must be a JSON object."}), 400
    user = User.query.get_or_404(payload.get("user_id"))
    existing_id = payload.get("payslip_id")
    if existing_id:
        existing = Payslip.query.get_or_404(existing_id)
        if existing.user_id != user.id:
            return jsonify({"message": "The payslip and employee do not match."}), 400
        preview = Payslip(
            id=existing.id,
            user_id=existing.user_id,
            company_name=existing.company_name,
            template_snapshot=copy.deepcopy(existing.template_snapshot),
        )
    else:
        preview = Payslip(user_id=user.id)
    try:
        _apply_payslip_payload(preview, payload, user)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    output = io.BytesIO()
    salary_rows = _payslip_rows_with_ytd_mtd(preview)
    generate_reference_payslip_pdf(
        output,
        template=preview.template_snapshot,
        employee_info=preview.employee_info,
        month=preview.month,
        year=preview.year,
        earnings=salary_rows["earnings"],
        deductions=salary_rows["deductions"],
        days_present=preview.days_present or 0,
        days_on_leave=preview.days_on_leave or 0,
        lop_days=preview.lop_days or 0,
        total_working_days=preview.total_working_days or 0,
        total_paid_days=preview.total_paid_days or 0,
        gross_earnings=preview.gross_earnings or 0,
        total_deductions=preview.total_deductions or 0,
        net_pay=preview.net_pay or 0,
    )
    return send_file(output, mimetype="application/pdf", download_name="payslip-preview.pdf")


@bp.post("/preview-bulk")
@roles_required(*PAYROLL_EDIT_ROLES)
def preview_bulk_payslips():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Payroll parameters must be a JSON object."}), 400
    try:
        users, month, year = _batch_users(payload)
        previews = [_preview_payload_for_user(user, month, year) for user in users]
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    return jsonify({"previews": previews})


@bp.post("/generate-selected")
@roles_required(*PAYROLL_EDIT_ROLES)
def generate_selected_payslips():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Payroll parameters must be a JSON object."}), 400
    try:
        users, month, year = _batch_users(payload)
        previews = [_preview_payload_for_user(user, month, year) for user in users]
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    adjustments = payload.get("adjustments", [])
    if not isinstance(adjustments, list):
        return jsonify({"message": "Payroll adjustments must be a list."}), 400
    by_user = {preview["user_id"]: preview for preview in previews}
    adjusted_users = set()
    try:
        for adjustment in adjustments:
            if not isinstance(adjustment, dict):
                raise ValueError("Each payroll adjustment must be an object.")
            raw_user_id = adjustment.get("user_id")
            if isinstance(raw_user_id, bool):
                raise ValueError("Payroll adjustment employee IDs must be integers.")
            user_id = int(raw_user_id)
            if user_id not in by_user:
                raise ValueError("Payroll adjustments may only contain selected employees.")
            if user_id in adjusted_users:
                raise ValueError("Each selected employee may have only one payroll adjustment.")
            adjusted_users.add(user_id)
            for component_field in ("earnings", "deductions"):
                if component_field in adjustment:
                    by_user[user_id][component_field] = _component_rows(
                        adjustment[component_field], component_field.title(),
                    )
    except (TypeError, ValueError) as exc:
        return jsonify({"message": str(exc)}), 400

    actor_id = int(get_jwt_identity())
    generated_keys = []
    records = []
    try:
        for preview in previews:
            payslip = Payslip(
                user_id=preview["user_id"],
                generated_by=actor_id,
                generated_at=datetime.utcnow(),
                status="draft",
                template_snapshot=preview["template_snapshot"],
            )
            user = db.session.get(User, preview["user_id"])
            _apply_payslip_payload(payslip, preview, user)
            db.session.add(payslip)
            db.session.flush()
            _generate_record_pdf(payslip)
            generated_keys.append(payslip.pdf_path)
            _record_revision(payslip, actor_id, "created")
            _record_payroll_audit(
                user.id, actor_id, "payslip_created",
                new=_payslip_snapshot(payslip), payslip_id=payslip.id,
            )
            records.append(payslip)
        db.session.commit()
    except (ValueError, IntegrityError, SQLAlchemyError, OSError) as exc:
        db.session.rollback()
        for key in generated_keys:
            _remove_private_pdf(key)
        if isinstance(exc, ValueError):
            return jsonify({"message": str(exc)}), 400
        if isinstance(exc, IntegrityError):
            return jsonify({"message": "A payslip already exists for one or more selected employees in this month."}), 409
        current_app.logger.exception("Bulk payslip generation failed.")
        return jsonify({"message": "Could not generate selected payslips."}), 500
    return jsonify(_serialize_payslips(records)), 201


@bp.get("/structure/<int:user_id>")
@roles_required(*PAYROLL_EDIT_ROLES)
def get_structure(user_id):
    structure = SalaryStructure.query.filter_by(user_id=user_id).first()
    if not structure:
        return jsonify({"message": "No salary structure defined for this employee."}), 404
    try:
        month, year = _validate_period({
            "month": request.args.get("month", date.today().month),
            "year": request.args.get("year", date.today().year),
        })
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    result = structure.to_dict()
    result["salary_components"] = _salary_structure_rows(structure, user_id, month, year)
    result["has_current_month_payslip"] = Payslip.query.filter_by(
        user_id=user_id, month=month, year=year,
    ).first() is not None
    salary_template = structure.salary_template
    result["salary_template"] = salary_template.to_dict() if salary_template else None
    if salary_template:
        overrides = structure.employee_overrides or {}
        percentages = overrides.get("component_percentages") or {}
        for field in ("basic_pct", "hra_pct", "special_allowance_pct", "other_allowance_pct"):
            result["salary_template"][field] = percentages.get(field, result["salary_template"][field])
        for field in (
            "transport_flat", "employee_pf_rate_pct", "employer_pf_rate_pct",
            "employer_pf_flat", "professional_tax_flat", "tds_flat",
        ):
            result["salary_template"][field] = overrides.get(field, result["salary_template"][field])
        result["salary_template"]["insurance_amounts"] = {
            **(result["salary_template"].get("insurance_amounts") or {}),
            **(overrides.get("insurance_amounts") or {}),
        }
    return jsonify(result)


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
    user = User.query.get_or_404(user_id)
    existing_structure = SalaryStructure.query.filter_by(user_id=user_id).first()
    if not existing_structure or existing_structure.annual_ctc is None or existing_structure.annual_ctc <= 0:
        return jsonify({"message": "A positive Annual CTC must be maintained in the employee profile before configuring salary."}), 400
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Salary structure data must be a JSON object."}), 400

    structure = SalaryStructure.query.filter_by(user_id=user_id).first()
    previous = structure.to_dict() if structure else None
    if not structure:
        structure = SalaryStructure(user_id=user_id)
        db.session.add(structure)

    for field in (
        "basic", "hra", "special_allowance", "other_allowance",
        "pf_employee", "esi_employee", "insurance", "professional_tax", "tds",
    ):
        if field in payload:
            try:
                setattr(structure, field, float(_decimal_amount(payload[field], field.replace("_", " ").title())))
            except ValueError as exc:
                db.session.rollback()
                return jsonify({"message": str(exc)}), 400
    try:
        for field in ("custom_earnings", "custom_deductions"):
            if field in payload:
                setattr(structure, field, _component_rows(payload[field], field.replace("_", " ").title()))
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"message": str(exc)}), 400

    db.session.flush()
    _record_payroll_audit(
        user.id, int(get_jwt_identity()), "salary_structure_updated",
        previous=previous, new=structure.to_dict(),
    )
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

    results = []
    skipped = []

    for user in User.query.filter_by(is_active=True).all():
        structure = SalaryStructure.query.filter_by(user_id=user.id).first()
        if not structure or (structure.is_ctc_only and not structure.salary_template):
            skipped.append({
                "user_id": user.id,
                "employee_code": user.employee_code,
                "full_name": user.full_name,
                "reason": "No complete salary structure is assigned.",
            })
            continue
        payslip = Payslip.query.filter_by(user_id=user.id, month=month, year=year).first()
        if payslip and payslip.status in PUBLISHED_STATUSES:
            skipped.append({
                "user_id": user.id,
                "employee_code": user.employee_code,
                "full_name": user.full_name,
                "reason": f"Payslip is already {payslip.status}.",
            })
            continue
        if structure.salary_template:
            prior_snapshot = _payslip_snapshot(payslip) if payslip and payslip.id else None
            try:
                preview = _preview_payload_for_user(user, month, year)
            except ValueError as exc:
                skipped.append({
                    "user_id": user.id,
                    "employee_code": user.employee_code,
                    "full_name": user.full_name,
                    "reason": str(exc),
                })
                continue
            if not payslip:
                payslip = Payslip(user_id=user.id, month=month, year=year)
                db.session.add(payslip)
            _apply_payslip_payload(payslip, preview, user)
            payslip.status = "draft"
            payslip.generated_by = generated_by
            payslip.generated_at = datetime.utcnow()
            db.session.flush()
            _generate_record_pdf(payslip)
            _record_revision(payslip, generated_by, "generated", prior_snapshot)
            _record_payroll_audit(
                user.id, generated_by, "payslip_generated",
                previous=prior_snapshot, new=_payslip_snapshot(payslip), payslip_id=payslip.id,
            )
            results.append(payslip)
            continue

        attendance = _attendance_for_period(user.id, month, year)
        days_in_month = attendance["days_in_month"]
        present_days = attendance["present_days"]
        approved_leave_days = attendance["leave_days"]
        paid_days = attendance["paid_days"]
        lop_days = attendance["lop_days"]
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
        if raw_deductions > gross_earnings:
            skipped.append({
                "user_id": user.id,
                "employee_code": user.employee_code,
                "full_name": user.full_name,
                "reason": "Total deductions exceed gross earnings.",
            })
            continue
        total_deductions = round(sum(item["amount"] for item in deductions), 2)
        net_pay = round(gross_earnings - total_deductions, 2)

        prior_snapshot = _payslip_snapshot(payslip) if payslip and payslip.id else None
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
        payslip.template_snapshot = _company_template(user.company_name)
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
        if payslip.id:
            _record_revision(payslip, generated_by, "generated", prior_snapshot)
            _record_payroll_audit(
                user.id, generated_by, "payslip_generated",
                previous=prior_snapshot, new=_payslip_snapshot(payslip), payslip_id=payslip.id,
            )

        results.append(payslip)

    db.session.commit()
    return jsonify({
        "month": month,
        "year": year,
        "generated": _serialize_payslips(results),
        "skipped": skipped,
    })


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
    employee_category = request.args.get("employee_category")
    employee_id = request.args.get("employee_id", type=int)

    query = User.query.filter_by(is_active=True)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(User.full_name.ilike(like), User.employee_code.ilike(like)))
    if role:
        query = query.filter_by(role=role)
    if department_id:
        query = query.filter_by(department_id=department_id)
    if employee_id:
        query = query.filter_by(id=employee_id)
    if employee_category:
        if employee_category not in EMPLOYEE_CATEGORIES:
            return jsonify({"message": "Select Full Time, Part Time, or Intern."}), 400
        query = query.filter_by(employee_category=employee_category)
    if company_name in COMPANIES:
        query = query.filter_by(company_name=company_name)
    elif company_name:
        return jsonify({"message": "Select one of the supported payroll companies."}), 400
    users = query.order_by(User.full_name.asc()).all()

    structures = {
        s.user_id: s
        for s in SalaryStructure.query.all()
        if s.salary_template_id or not s.is_ctc_only
    }
    slips = {p.user_id: p for p in Payslip.query.filter_by(month=month, year=year).all()}
    revision_counts = _payslip_revision_counts(slips.values())
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
            "employee_category": getattr(u, "employee_category", None),
            "employment_type": EMPLOYEE_CATEGORIES.get(getattr(u, "employee_category", None), ""),
            "annual_ctc": float(st.annual_ctc) if st and st.annual_ctc is not None else None,
            "department": u.department.name if u.department else None,
            "manager_name": managers.get(u.manager_id),
            "has_structure": st is not None,
            "monthly_gross": (
                round(
                    float(st.annual_ctc or 0) / 12 * (
                        (st.employee_overrides or {}).get("component_percentages", {}).get("basic_pct", st.salary_template.basic_pct)
                        + (st.employee_overrides or {}).get("component_percentages", {}).get("hra_pct", st.salary_template.hra_pct)
                        + (st.employee_overrides or {}).get("component_percentages", {}).get("special_allowance_pct", st.salary_template.special_allowance_pct)
                        + (st.employee_overrides or {}).get("component_percentages", {}).get("other_allowance_pct", st.salary_template.other_allowance_pct)
                    ) / 100 + float((st.employee_overrides or {}).get("transport_flat", st.salary_template.transport_flat) or 0),
                    2,
                )
                if st and st.salary_template else st.gross if st else None
            ),
            "monthly_net": (
                round(st.gross - st.total_deductions, 2)
                if st and not st.salary_template else None
            ),
            "payslip_id": slip.id if slip else None,
            "payslip_status": slip.status if slip else None,
            "payroll_state": state,
            "payslip": slip.to_dict(revision_count=revision_counts.get(slip.id, 0)) if slip else None,
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
@roles_required(*PAYROLL_EDIT_ROLES)
def list_payroll_companies():
    return jsonify(list(COMPANIES))


def _template_dict(company_name):
    template = _company_template(company_name)
    if template is None:
        return None
    return template


@bp.get("/payslip-templates")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def list_company_payslip_templates():
    return jsonify([_template_dict(name) for name in COMPANIES])


@bp.put("/payslip-templates/<path:company_name>")
@roles_required(*PAYROLL_EDIT_ROLES)
def update_company_payslip_template(company_name):
    if company_name not in COMPANIES:
        return jsonify({"message": "Select one of the supported payroll companies."}), 400
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Payslip template data must be a JSON object."}), 400
    current = _company_template(company_name)
    address = payload.get("address", current["address"])
    if not isinstance(address, str) or len(address) > 1000:
        return jsonify({"message": "Company address must be 1,000 characters or fewer."}), 400
    component_updates = {}
    for field in ("earnings_components", "deductions_components"):
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, list) or len(value) > 15:
            return jsonify({"message": f"{field.replace('_', ' ').title()} must contain at most 15 components."}), 400
        names = []
        for item in value:
            name = str(item or "").strip()
            if not name or len(name) > 100 or name.lower() in {entry.lower() for entry in names}:
                return jsonify({"message": "Component names must be unique and between 1 and 100 characters."}), 400
            names.append(name)
        component_updates[field] = names
    colors_to_update = {}
    for field in ("primary_color", "accent_color"):
        value = payload.get(field, current[field])
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            return jsonify({"message": f"{field.replace('_', ' ').title()} must be a six-digit hex color."}), 400
        colors_to_update[field] = value.upper()

    template = CompanyPayslipTemplate.query.filter_by(company_name=company_name).first()
    if template is None:
        template = CompanyPayslipTemplate(
            company_name=company_name,
            layout_key=current["layout_key"],
            logo_path=current["logo_path"],
            earnings_components=current["earnings_components"],
            deductions_components=current["deductions_components"],
        )
        db.session.add(template)
    template.address = address
    template.primary_color = colors_to_update["primary_color"]
    template.accent_color = colors_to_update["accent_color"]
    for field, value in component_updates.items():
        setattr(template, field, value)
    template.updated_by = int(get_jwt_identity())
    db.session.commit()
    return jsonify(template.to_dict())


@bp.post("/payslip-templates/<path:company_name>/logo")
@roles_required(*PAYROLL_EDIT_ROLES)
def upload_company_payslip_logo(company_name):
    if company_name not in COMPANIES:
        return jsonify({"message": "Select one of the supported payroll companies."}), 400
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"message": "A company logo image is required."}), 400
    content = uploaded.stream.read(5 * 1024 * 1024 + 1)
    if not content or len(content) > 5 * 1024 * 1024:
        return jsonify({"message": "Company logo must be between 1 byte and 5 MB."}), 400
    try:
        image = Image.open(io.BytesIO(content))
        if image.format not in {"PNG", "JPEG", "WEBP"} or image.width > 6000 or image.height > 6000:
            return jsonify({"message": "Upload a PNG, JPEG, or WEBP logo no larger than 6,000 by 6,000 pixels."}), 400
        image.load()
        image.thumbnail((1600, 1000))
        output = io.BytesIO()
        image.convert("RGBA").save(output, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, ValueError):
        return jsonify({"message": "The uploaded company logo is not a valid image."}), 400

    current = _company_template(company_name)
    template = CompanyPayslipTemplate.query.filter_by(company_name=company_name).first()
    if template is None:
        template = CompanyPayslipTemplate(
            company_name=company_name,
            layout_key=current["layout_key"],
            address=current["address"],
            primary_color=current["primary_color"],
            accent_color=current["accent_color"],
            logo_path=current["logo_path"],
            earnings_components=current["earnings_components"],
            deductions_components=current["deductions_components"],
        )
        db.session.add(template)
    filename = f"{uuid.uuid4().hex}.png"
    key = f"uploads/{filename}"
    folder = current_app.config["PAYSLIP_TEMPLATE_FOLDER"]
    path = os.path.join(folder, filename)
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "wb") as saved_logo:
            saved_logo.write(output.getvalue())
        template.logo_path = key
        template.updated_by = int(get_jwt_identity())
        db.session.commit()
    except (OSError, SQLAlchemyError):
        db.session.rollback()
        if os.path.isfile(path):
            os.remove(path)
        current_app.logger.exception("Company payslip logo could not be saved.")
        return jsonify({"message": "Could not save the company logo."}), 500
    return jsonify(template.to_dict())


@bp.get("/people")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def payroll_people():
    query = User.query.filter_by(is_active=True)
    company = request.args.get("company_name")
    search = request.args.get("q", "").strip()
    category = request.args.get("employee_category")
    include_uncategorized = request.args.get("include_uncategorized") == "true"
    if company in COMPANIES:
        query = query.filter_by(company_name=company)
    elif company:
        return jsonify({"message": "Select one of the supported payroll companies."}), 400
    if category:
        if category not in EMPLOYEE_CATEGORIES:
            return jsonify({"message": "Select Full Time, Part Time, or Internship."}), 400
        if include_uncategorized:
            query = query.filter(db.or_(
                User.employee_category == category,
                User.employee_category.is_(None),
            ))
        else:
            query = query.filter_by(employee_category=category)
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(User.full_name.ilike(like), User.employee_code.ilike(like)))
    users = query.order_by(User.full_name.asc()).all()
    activity_by_employee = _salary_structure_activity_by_employee(user.id for user in users)
    people = []
    for user in users:
        structure = SalaryStructure.query.filter_by(user_id=user.id).first()
        template = _company_template(user.company_name)
        publication = _published_salary_structure_state(
            activity_by_employee.get(user.id),
            structure.salary_template_id if structure else None,
        )
        people.append({
            "id": user.id,
            "full_name": user.full_name,
            "employee_code": user.employee_code,
            "designation": user.designation,
            "department": user.department.name if user.department else "",
            "date_of_joining": user.date_of_joining.isoformat() if user.date_of_joining else "",
            "uan_number": user.uan or "",
            "company_name": user.company_name,
            "employee_category": getattr(user, "employee_category", None),
            "annual_ctc": float(structure.annual_ctc) if structure and structure.annual_ctc is not None else None,
            "employee_info": _make_employee_snapshot(user, {}),
            "salary_structure": structure.to_dict() if structure else None,
            "salary_structure_name": (
                structure.salary_template.name
                if structure and structure.salary_template else None
            ),
            "salary_structure_published_at": publication["published_at"] if publication else None,
            "salary_structure_published_by": publication["published_by"] if publication else None,
            "earnings": _salary_component_rows(structure, template, "earnings") if structure and template else [],
            "deductions": _salary_component_rows(structure, template, "deductions") if structure and template else [],
        })
    return jsonify(people)


@bp.get("/manager/people")
@jwt_required()
def manager_payroll_people():
    if get_jwt().get("role") != MANAGER:
        return jsonify({"message": "Only managers can access this employee list."}), 403
    actor_id = int(get_jwt_identity())
    return jsonify([
        {
            "id": user.id,
            "full_name": user.full_name,
            "employee_code": user.employee_code,
            "company_name": user.company_name,
            "designation": user.designation,
            "department": user.department.name if user.department else None,
            "employee_category": getattr(user, "employee_category", None),
        }
        for user in User.query.filter_by(manager_id=actor_id, is_active=True)
        .order_by(User.full_name.asc()).all()
    ])


@bp.patch("/people/<int:user_id>/company")
@roles_required(*PAYROLL_EDIT_ROLES)
def assign_payroll_company(user_id):
    user = User.query.get_or_404(user_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("company_name") not in COMPANIES:
        return jsonify({"message": "Select one of the supported payroll companies."}), 400
    previous_company = user.company_name
    user.company_name = payload["company_name"]
    if previous_company != user.company_name:
        structure = SalaryStructure.query.filter_by(user_id=user.id).first()
        if structure:
            _record_payroll_audit(
                user.id, int(get_jwt_identity()), "salary_structure_updated",
                previous={"company_name": previous_company},
                new={"company_name": user.company_name},
            )
    db.session.commit()
    return jsonify({
        "id": user.id,
        "full_name": user.full_name,
        "company_name": user.company_name,
    })


@bp.patch("/people/<int:user_id>/ctc")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def update_employee_ctc(user_id):
    user = User.query.get_or_404(user_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or "annual_ctc" not in payload:
        return jsonify({"message": "Annual CTC is required."}), 400
    try:
        annual_ctc = normalize_annual_ctc(payload["annual_ctc"])
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    structure = SalaryStructure.query.filter_by(user_id=user.id).first()
    if structure is None:
        structure = SalaryStructure(user_id=user.id)
        db.session.add(structure)
    previous_ctc = structure.annual_ctc
    structure.annual_ctc = annual_ctc
    _record_payroll_audit(
        user.id, int(get_jwt_identity()), "annual_ctc_updated",
        previous={"annual_ctc": float(previous_ctc) if previous_ctc is not None else None},
        new={"annual_ctc": float(annual_ctc)},
    )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Employee Annual CTC could not be updated.")
        return jsonify({"message": "Could not update Annual CTC."}), 500
    return jsonify({"id": user.id, "annual_ctc": float(structure.annual_ctc)})


@bp.post("/people/<int:user_id>/salary-structure/publish")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def publish_employee_salary_structure(user_id):
    employee = User.query.get_or_404(user_id)
    structure = SalaryStructure.query.filter_by(user_id=employee.id).with_for_update().first()
    if structure is None or structure.salary_template is None:
        return jsonify({"message": "Save a salary structure before publishing it."}), 400
    if structure.annual_ctc is None or structure.annual_ctc <= 0:
        return jsonify({"message": "A positive Annual CTC is required before publishing."}), 400
    template = structure.salary_template
    if template.company_name != employee.company_name:
        return jsonify({"message": "The salary structure must match the employee's company before publishing."}), 409

    activity = _salary_structure_activity_by_employee([employee.id]).get(employee.id)
    current_publication = _published_salary_structure_state(activity, template.id)
    if current_publication:
        return jsonify({
            **current_publication,
            "already_published": True,
            "notification_sent": False,
        })

    actor_id = int(get_jwt_identity())
    event = _record_payroll_audit(
        employee.id,
        actor_id,
        "salary_structure_published",
        new={
            "salary_template_id": template.id,
            "salary_template_name": template.name,
        },
    )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Salary structure could not be published.")
        return jsonify({"message": "Could not publish the salary structure."}), 500

    notification_sent = send_push(
        employee.id,
        "Salary structure published",
        "Your salary structure has been published. Contact Finance & Operations if you have questions.",
        data={"type": "salary_structure_published", "employee_id": employee.id},
    )
    return jsonify({
        "published_at": event.created_at.isoformat() if event.created_at else None,
        "published_by": actor_id,
        "already_published": False,
        "notification_sent": notification_sent,
    })


def _can_manage_employee_profile(user, actor_id, role):
    return role in PAYROLL_EDIT_ROLES or (
        role == MANAGER and user.manager_id == actor_id
    )


@bp.get("/people/<int:user_id>/payroll-profile")
@jwt_required()
def get_payroll_profile(user_id):
    user = User.query.get_or_404(user_id)
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if not _can_manage_employee_profile(user, actor_id, role):
        return jsonify({"message": "You can only view payroll profile details for your assigned employees."}), 403
    structure = SalaryStructure.query.filter_by(user_id=user.id).first()
    result = {
        "id": user.id,
        "employee_category": user.employee_category,
        "annual_ctc": float(structure.annual_ctc) if structure and structure.annual_ctc is not None else None,
        "employee_info": _make_employee_snapshot(user, {}),
        "department_id": user.department_id,
    }
    if role in PAYROLL_EDIT_ROLES:
        result["salary_structure"] = structure.to_dict() if structure else None
    return jsonify(result)


@bp.put("/people/<int:user_id>/payroll-profile")
@jwt_required()
def update_payroll_profile(user_id):
    user = User.query.get_or_404(user_id)
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if not _can_manage_employee_profile(user, actor_id, role):
        return jsonify({"message": "You can only edit payroll profile details for your assigned employees."}), 403
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Payroll profile data must be a JSON object."}), 400
    if role not in PAYROLL_EDIT_ROLES and "salary_structure" in payload:
        return jsonify({"message": "Managers cannot edit salary amounts."}), 403

    fields = {
        "employee_category": 20,
        "designation": 120,
        "pan": 20,
        "pf_number": 50,
        "uan_number": 12,
        "bank_name": 120,
        "bank_account_name": 150,
        "bank_account_number": 40,
        "pay_mode": 30,
        "location": 120,
    }
    for field, max_length in fields.items():
        if field not in payload:
            continue
        value = str(payload[field] or "").strip()
        if field == "employee_category" and value and value not in EMPLOYEE_CATEGORIES:
            db.session.rollback()
            return jsonify({"message": "Select Full Time, Part Time, or Internship."}), 400
        if len(value) > max_length:
            db.session.rollback()
            return jsonify({"message": f"{field.replace('_', ' ').title()} must be {max_length} characters or fewer."}), 400
        setattr(user, "uan" if field == "uan_number" else field, value or None)

    if "date_of_joining" in payload:
        value = str(payload["date_of_joining"] or "").strip()
        if value:
            try:
                user.date_of_joining = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                db.session.rollback()
                return jsonify({"message": "Date of joining must use YYYY-MM-DD format."}), 400
        else:
            user.date_of_joining = None
    if "department_id" in payload:
        value = payload["department_id"]
        if value in ("", None):
            user.department_id = None
        else:
            try:
                department_id = int(value)
            except (TypeError, ValueError):
                db.session.rollback()
                return jsonify({"message": "Select a valid department."}), 400
            if Department.query.get(department_id) is None:
                db.session.rollback()
                return jsonify({"message": "Select a valid department."}), 400
            user.department_id = department_id

    structure = None
    previous_salary = None
    if "salary_structure" in payload:
        value = payload["salary_structure"]
        if not isinstance(value, dict):
            db.session.rollback()
            return jsonify({"message": "Salary structure must be an object."}), 400
        structure = SalaryStructure.query.filter_by(user_id=user.id).first()
        previous_salary = structure.to_dict() if structure else None
        if structure is None:
            structure = SalaryStructure(user_id=user.id)
            db.session.add(structure)
        try:
            for field in (
                "basic", "hra", "special_allowance", "other_allowance",
                "pf_employee", "esi_employee", "insurance", "professional_tax", "tds",
            ):
                if field in value:
                    setattr(structure, field, float(_decimal_amount(value[field], field.replace("_", " ").title())))
            for field in ("custom_earnings", "custom_deductions"):
                if field in value:
                    setattr(structure, field, _component_rows(value[field], field.replace("_", " ").title()))
        except ValueError as exc:
            db.session.rollback()
            return jsonify({"message": str(exc)}), 400

    db.session.flush()
    if structure is not None:
        _record_payroll_audit(
            user.id, actor_id, "salary_structure_updated",
            previous=previous_salary, new=structure.to_dict(),
        )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Payroll profile update could not be saved.")
        return jsonify({"message": "Could not save payroll profile details."}), 500
    profile_structure = SalaryStructure.query.filter_by(user_id=user.id).first()
    result = {
        "id": user.id,
        "employee_category": user.employee_category,
        "annual_ctc": float(profile_structure.annual_ctc) if profile_structure and profile_structure.annual_ctc is not None else None,
        "employee_info": _make_employee_snapshot(user, {}),
        "department_id": user.department_id,
    }
    if role in PAYROLL_EDIT_ROLES:
        result["salary_structure"] = structure.to_dict() if structure else None
    return jsonify(result)


@bp.get("/audit")
@roles_required(*PAYROLL_EDIT_ROLES)
def payroll_audit_history():
    raw_employee_id = request.args.get("employee_id")
    employee_id = None
    if raw_employee_id:
        try:
            employee_id = int(raw_employee_id)
        except ValueError:
            return jsonify({"message": "Employee ID must be an integer."}), 400
        if employee_id <= 0:
            return jsonify({"message": "Employee ID must be positive."}), 400
    query = PayrollAuditLog.query
    if employee_id is not None:
        query = query.filter_by(employee_id=employee_id)
    rows = query.order_by(PayrollAuditLog.created_at.desc(), PayrollAuditLog.id.desc()).limit(200).all()
    user_ids = {row.employee_id for row in rows} | {row.actor_id for row in rows}
    users = {user.id: user for user in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return jsonify([
        {
            "id": row.id,
            "employee_id": row.employee_id,
            "employee_name": users[row.employee_id].full_name if row.employee_id in users else None,
            "actor_id": row.actor_id,
            "actor_name": users[row.actor_id].full_name if row.actor_id in users else None,
            "payslip_id": row.payslip_id,
            "action": row.action,
            "previous_values": row.previous_values,
            "new_values": row.new_values,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ])


@bp.get("/payslips/<int:user_id>")
@jwt_required()
def employee_payslips(user_id):
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role not in PAYROLL_VIEW_ROLES and role != EMPLOYEE:
        return jsonify({"message": "You do not have permission to view payslips."}), 403
    employee = User.query.get_or_404(user_id)
    if role in (EMPLOYEE, CONTRACT_EMPLOYEE) and actor_id != user_id:
        return jsonify({"message": "Employees can only view their own payslips."}), 403
    if role == MANAGER and employee.id != actor_id and employee.manager_id != actor_id:
        return jsonify({"message": "Managers can only view payslips for their assigned employees."}), 403
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
    visible_rows = [p for p in rows if _visible_to_actor(p, actor_id, role)]
    return jsonify(_serialize_payslips(visible_rows))


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
    if role in (EMPLOYEE, CONTRACT_EMPLOYEE):
        query = query.filter(Payslip.user_id == actor_id)
    elif role == MANAGER:
        query = query.filter(db.or_(
            Payslip.user_id == actor_id,
            Payslip.user_id.in_(db.session.query(User.id).filter_by(manager_id=actor_id)),
        ))
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
    visible_rows = [p for p in rows if _visible_to_actor(p, actor_id, role)]
    return jsonify(_serialize_payslips(visible_rows))


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
    generated_pdf_key = None
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
        generated_pdf_key = payslip.pdf_path
        actor_id = int(get_jwt_identity())
        _record_revision(payslip, actor_id, "created")
        _record_payroll_audit(
            user.id, actor_id, "payslip_created",
            new=_payslip_snapshot(payslip), payslip_id=payslip.id,
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"message": str(exc)}), 400
    except IntegrityError:
        db.session.rollback()
        if generated_pdf_key:
            _remove_private_pdf(generated_pdf_key)
        return jsonify({"message": "A payslip already exists for this employee and month."}), 409
    except SQLAlchemyError:
        db.session.rollback()
        if generated_pdf_key:
            _remove_private_pdf(generated_pdf_key)
        current_app.logger.exception("Payslip record could not be saved.")
        return jsonify({"message": "Could not save this payslip."}), 500
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
    previous = _payslip_snapshot(payslip)
    generated_pdf_key = None
    try:
        actor_id = int(get_jwt_identity())
        _apply_payslip_payload(payslip, payload, user)
        payslip.status = "updated" if payslip.status in PUBLISHED_STATUSES else "draft"
        payslip.updated_by = actor_id
        payslip.updated_at = datetime.utcnow()
        _generate_record_pdf(payslip)
        generated_pdf_key = payslip.pdf_path
        _record_revision(payslip, actor_id, "updated")
        _record_payroll_audit(
            user.id, actor_id, "payslip_updated",
            previous=previous, new=_payslip_snapshot(payslip), payslip_id=payslip.id,
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"message": str(exc)}), 400
    except OSError:
        db.session.rollback()
        if generated_pdf_key:
            _remove_private_pdf(generated_pdf_key)
        current_app.logger.exception("Payslip PDF could not be stored.")
        return jsonify({"message": "Could not generate the payslip PDF."}), 500
    except SQLAlchemyError:
        db.session.rollback()
        if generated_pdf_key:
            _remove_private_pdf(generated_pdf_key)
        current_app.logger.exception("Payslip update could not be saved.")
        return jsonify({"message": "Could not save this payslip."}), 500
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
    if payslip.status not in {"draft", "processed"}:
        return jsonify({"message": "Only unpublished draft or processed payslips can be deleted."}), 409
    pdf_keys = {payslip.pdf_path} if payslip.pdf_path else set()
    pdf_keys.update(
        revision.snapshot.get("pdf_path")
        for revision in payslip.revisions
        if revision.snapshot and revision.snapshot.get("pdf_path")
    )
    db.session.delete(payslip)
    db.session.commit()
    for key in pdf_keys:
        _remove_private_pdf(key)
    return jsonify({"message": "Unpublished payslip deleted."})


@bp.post("/payslips/<int:payslip_id>/publish")
@roles_required(*PAYROLL_EDIT_ROLES)
def publish_payslip(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    if payslip.status not in {"draft", "published", "updated"}:
        return jsonify({"message": "This payslip cannot be published in its current state."}), 409
    pdf_path = _stored_pdf_path(payslip.pdf_path)
    if not pdf_path or not os.path.isfile(pdf_path):
        return jsonify({"message": "Generate or upload a PDF before publishing this payslip."}), 409
    old_status = payslip.status
    payslip.status = "updated" if payslip.status in {"published", "updated"} else "published"
    actor_id = int(get_jwt_identity())
    payslip.published_by = actor_id
    payslip.published_at = datetime.utcnow()
    _record_payroll_audit(
        payslip.user_id, actor_id, "payslip_published",
        previous={"status": old_status}, new={"status": payslip.status}, payslip_id=payslip.id,
    )
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
    previous = _payslip_snapshot(payslip)
    previous_uploaded_pdf = payslip.pdf_path if payslip.pdf_is_uploaded else None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as saved_file:
            saved_file.write(content)
    except OSError:
        current_app.logger.exception("Payslip PDF upload could not be stored.")
        return jsonify({"message": "Could not store the uploaded PDF."}), 500
    payslip.pdf_path = key
    payslip.pdf_is_uploaded = True
    payslip.pdf_filename = filename
    if payslip.status in {"published", "updated"}:
        payslip.status = "updated"
    payslip.updated_by = int(get_jwt_identity())
    payslip.updated_at = datetime.utcnow()
    actor_id = int(get_jwt_identity())
    _record_revision(payslip, actor_id, "pdf_uploaded")
    _record_payroll_audit(
        payslip.user_id, actor_id, "payslip_pdf_uploaded",
        previous=previous, new=_payslip_snapshot(payslip), payslip_id=payslip.id,
    )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        _remove_private_pdf(key)
        current_app.logger.exception("Payslip PDF metadata could not be saved.")
        return jsonify({"message": "Could not save uploaded PDF metadata."}), 500
    if previous_uploaded_pdf:
        _remove_private_pdf(previous_uploaded_pdf)
    return jsonify(payslip.to_dict())


@bp.delete("/payslips/<int:payslip_id>/pdf")
@roles_required(*PAYROLL_EDIT_ROLES)
def remove_uploaded_payslip_pdf(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    if not payslip.pdf_is_uploaded:
        return jsonify({"message": "There is no uploaded PDF to remove."}), 409

    previous = _payslip_snapshot(payslip)
    previous_uploaded_pdf = payslip.pdf_path
    generated_pdf_key = None
    try:
        _generate_record_pdf(payslip)
        generated_pdf_key = payslip.pdf_path
        if payslip.status in PUBLISHED_STATUSES:
            payslip.status = "updated"
        payslip.updated_by = int(get_jwt_identity())
        payslip.updated_at = datetime.utcnow()
        actor_id = int(get_jwt_identity())
        _record_revision(payslip, actor_id, "uploaded_pdf_removed")
        _record_payroll_audit(
            payslip.user_id, actor_id, "uploaded_payslip_pdf_removed",
            previous=previous, new=_payslip_snapshot(payslip), payslip_id=payslip.id,
        )
        db.session.commit()
    except OSError:
        db.session.rollback()
        if generated_pdf_key:
            _remove_private_pdf(generated_pdf_key)
        current_app.logger.exception("Generated payslip PDF could not replace uploaded PDF.")
        return jsonify({"message": "Could not restore the generated payslip PDF."}), 500
    except SQLAlchemyError:
        db.session.rollback()
        if generated_pdf_key:
            _remove_private_pdf(generated_pdf_key)
        current_app.logger.exception("Payslip PDF removal metadata could not be saved.")
        return jsonify({"message": "Could not remove the uploaded payslip PDF."}), 500

    _remove_private_pdf(previous_uploaded_pdf)
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


@bp.post("/payslips/bulk-download")
@jwt_required()
def download_payslips_archive():
    actor_id = int(get_jwt_identity())
    role = get_jwt().get("role")
    if role not in PAYROLL_VIEW_ROLES and role != EMPLOYEE:
        return jsonify({"message": "You do not have permission to download payslips."}), 403
    payload = request.get_json(silent=True)
    ids = payload.get("payslip_ids") if isinstance(payload, dict) else None
    if not isinstance(ids, list) or not ids or len(ids) > 100:
        return jsonify({"message": "Select between 1 and 100 payslips."}), 400
    try:
        payslip_ids = [int(value) for value in ids]
    except (TypeError, ValueError):
        return jsonify({"message": "Payslip IDs must be integers."}), 400
    if any(isinstance(value, bool) for value in ids) or len(set(payslip_ids)) != len(payslip_ids):
        return jsonify({"message": "Payslip selection must contain unique IDs."}), 400
    payslips = Payslip.query.filter(Payslip.id.in_(payslip_ids)).all()
    if len(payslips) != len(payslip_ids):
        return jsonify({"message": "One or more selected payslips are unavailable."}), 404
    by_id = {payslip.id: payslip for payslip in payslips}
    payslips = [by_id[payslip_id] for payslip_id in payslip_ids]
    if any(not _visible_to_actor(payslip, actor_id, role) for payslip in payslips):
        return jsonify({"message": "You do not have permission to download one or more selected payslips."}), 403
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for payslip in payslips:
            path = _stored_pdf_path(payslip.pdf_path)
            if not path or not os.path.isfile(path):
                return jsonify({"message": "One or more selected payslip PDFs are unavailable."}), 404
            employee_code = (payslip.employee_info or {}).get("employee_code") or str(payslip.user_id)
            filename = secure_filename(
                f"{employee_code}_{payslip.year}_{payslip.month:02d}_{payslip.id}.pdf"
            )
            with open(path, "rb") as pdf_file:
                zipped.writestr(filename, pdf_file.read())
    archive.seek(0)
    return send_file(archive, mimetype="application/zip", as_attachment=True, download_name="payslips.zip")


@bp.get("/payslips/<int:payslip_id>/revisions")
@roles_required(*PAYROLL_EDIT_ROLES)
def list_payslip_revisions(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    rows = PayslipRevision.query.filter_by(payslip_id=payslip.id).order_by(
        PayslipRevision.revision.asc(),
    ).all()
    return jsonify([row.to_dict() for row in rows])


@bp.get("/payslips/<int:payslip_id>/revisions/<int:revision_number>/pdf")
@roles_required(*PAYROLL_EDIT_ROLES)
def download_payslip_revision_pdf(payslip_id, revision_number):
    revision = PayslipRevision.query.filter_by(
        payslip_id=payslip_id,
        revision=revision_number,
    ).first_or_404()
    pdf_key = (revision.snapshot or {}).get("pdf_path")
    path = _stored_pdf_path(pdf_key)
    if not path or not os.path.isfile(path):
        return jsonify({"message": "Historical payslip PDF is unavailable."}), 404
    payslip_snapshot = revision.snapshot
    employee_code = (payslip_snapshot.get("employee_info") or {}).get("employee_code")
    download_name = secure_filename(
        f"{employee_code or payslip_snapshot.get('user_id')}_{payslip_snapshot.get('year')}_"
        f"{int(payslip_snapshot.get('month') or 0):02d}_revision_{revision_number}.pdf"
    )
    return send_from_directory(
        os.path.dirname(path),
        os.path.basename(path),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name,
    )


@bp.post("/payslips/<int:payslip_id>/mark-paid")
@roles_required(*PAYROLL_EDIT_ROLES)
def mark_paid(payslip_id):
    payslip = Payslip.query.get_or_404(payslip_id)
    old_status = payslip.status
    payslip.status = "paid"
    actor_id = int(get_jwt_identity())
    payslip.published_by = actor_id
    payslip.published_at = payslip.published_at or datetime.utcnow()
    _record_payroll_audit(
        payslip.user_id, actor_id, "payslip_marked_paid",
        previous={"status": old_status}, new={"status": "paid"}, payslip_id=payslip.id,
    )
    db.session.commit()
    return jsonify(payslip.to_dict())


# ============================================================================
# Salary templates — Finance defines a reusable % split once, applies it
# to any employee's CTC instead of typing flat numbers each time.
# ============================================================================

@bp.get("/templates")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def list_templates():
    company_name = request.args.get("company_name")
    query = SalaryTemplate.query
    if company_name:
        if company_name not in COMPANIES:
            return jsonify({"message": "Select one of the supported payroll companies."}), 400
        query = query.filter_by(company_name=company_name)
    rows = query.order_by(SalaryTemplate.company_name, SalaryTemplate.name).all()
    return jsonify([t.to_dict() for t in rows])


def _validated_salary_template_values(payload, existing=None):
    values = {}
    if not isinstance(payload, dict):
        raise ValueError("Salary structure data must be a JSON object.")
    if "name" in payload or existing is None:
        name = str(payload.get("name") or "").strip()
        if not name or len(name) > 100:
            raise ValueError("Salary structure name must be between 1 and 100 characters.")
        values["name"] = name
    if "description" in payload:
        description = str(payload.get("description") or "").strip()
        if len(description) > 255:
            raise ValueError("Description must be 255 characters or fewer.")
        values["description"] = description or None
    if "company_name" in payload or existing is None:
        company_name = payload.get("company_name")
        if company_name and company_name not in COMPANIES:
            raise ValueError("Select one of the supported payroll companies.")
        values["company_name"] = company_name or None

    numeric_fields = (
        "basic_pct", "hra_pct", "special_allowance_pct", "other_allowance_pct",
        "transport_flat", "employee_pf_rate_pct", "employer_pf_rate_pct",
        "employer_pf_flat", "professional_tax_flat", "tds_flat", "pf_employee_pct", "esi_employee_pct",
        "insurance_pct", "tds_pct",
    )
    percentage_fields = {
        "basic_pct", "hra_pct", "special_allowance_pct", "other_allowance_pct",
        "employee_pf_rate_pct", "employer_pf_rate_pct", "pf_employee_pct",
        "esi_employee_pct", "insurance_pct", "tds_pct",
    }
    for field in numeric_fields:
        if field not in payload and existing is None:
            continue
        if field not in payload:
            continue
        amount = _decimal_amount(payload[field], field.replace("_", " ").title())
        if field in percentage_fields and amount > 100:
            raise ValueError(f"{field.replace('_', ' ').title()} must not exceed 100%.")
        values[field] = float(amount)

    insurance_months = payload.get(
        "insurance_months",
        existing.insurance_months if existing is not None else [],
    )
    if not isinstance(insurance_months, list) or any(
        isinstance(month, bool) or not isinstance(month, int) or month not in (1, 2)
        for month in insurance_months
    ):
        raise ValueError("Insurance can only be scheduled for January or February.")
    if len(set(insurance_months)) != len(insurance_months) or len(insurance_months) > 1:
        raise ValueError("Select either January, February, or no insurance month.")
    values["insurance_months"] = insurance_months

    raw_amounts = payload.get(
        "insurance_amounts",
        existing.insurance_amounts if existing is not None else {},
    )
    if not isinstance(raw_amounts, dict):
        raise ValueError("Insurance amounts must be an object keyed by month number.")
    insurance_amounts = {}
    for month_key, raw_amount in raw_amounts.items():
        try:
            month_number = int(month_key)
        except (TypeError, ValueError):
            raise ValueError("Insurance amount keys must be month numbers.")
        if month_number not in insurance_months:
            raise ValueError("Insurance amounts may only be set for selected insurance months.")
        insurance_amounts[str(month_number)] = float(_decimal_amount(raw_amount, "Insurance amount"))
    values["insurance_amounts"] = insurance_amounts

    if "arrears_by_employee" in payload:
        raw_arrears = payload["arrears_by_employee"]
        if not isinstance(raw_arrears, dict):
            raise ValueError("Arrears must be an object keyed by employee ID.")
        arrears_by_employee = {}
        employee_ids = set()
        for raw_employee_id, raw_values in raw_arrears.items():
            try:
                employee_id = int(raw_employee_id)
            except (TypeError, ValueError):
                raise ValueError("Arrears employee IDs must be integers.")
            if employee_id <= 0 or employee_id in employee_ids:
                raise ValueError("Arrears employees must have unique positive IDs.")
            if not isinstance(raw_values, dict):
                raise ValueError("Each employee arrears entry must include a description and amount.")
            description = str(raw_values.get("description") or "").strip()
            if not description or len(description) > 150:
                raise ValueError("Each arrears description must be between 1 and 150 characters.")
            arrears_amount = _decimal_amount(raw_values.get("amount"), "Arrears amount")
            if arrears_amount <= 0:
                raise ValueError("Each arrears amount must be greater than zero.")
            employee_ids.add(employee_id)
            arrears_by_employee[str(employee_id)] = {
                "description": description,
                "amount": float(arrears_amount),
            }

        employees = User.query.filter(
            User.id.in_(employee_ids),
            User.is_active.is_(True),
        ).all() if employee_ids else []
        employees_by_id = {employee.id: employee for employee in employees}
        if len(employees_by_id) != len(employee_ids):
            raise ValueError("One or more arrears employees are missing or inactive.")
        if employee_ids and (
            not values.get("company_name")
            or any(employee.company_name != values["company_name"] for employee in employees)
        ):
            raise ValueError("All arrears employees must belong to the selected company.")
        if employee_ids:
            arrears_month, arrears_year = _validate_period({
                "month": payload.get(
                    "arrears_month",
                    existing.arrears_month if existing is not None else None,
                ),
                "year": payload.get(
                    "arrears_year",
                    existing.arrears_year if existing is not None else None,
                ),
            })
        else:
            arrears_month = None
            arrears_year = None
        values.update({
            "arrears_by_employee": arrears_by_employee,
            "arrears_employee_id": None,
            "arrears_description": None,
            "arrears_amount": None,
            "arrears_month": arrears_month,
            "arrears_year": arrears_year,
        })
    elif "arrears_employee_id" in payload or existing is None:
        arrears_employee_id = payload.get(
            "arrears_employee_id",
            existing.arrears_employee_id if existing is not None else None,
        )
        arrears_fields = (
            "arrears_description", "arrears_amount", "arrears_month", "arrears_year",
        )
        if arrears_employee_id in (None, ""):
            if any(payload.get(field) not in (None, "") for field in arrears_fields):
                raise ValueError("Select an employee before configuring template arrears.")
            values.update({
                "arrears_by_employee": {},
                "arrears_employee_id": None,
                "arrears_description": None,
                "arrears_amount": None,
                "arrears_month": None,
                "arrears_year": None,
            })
        else:
            if isinstance(arrears_employee_id, bool):
                raise ValueError("Select a valid employee for template arrears.")
            try:
                arrears_employee_id = int(arrears_employee_id)
            except (TypeError, ValueError):
                raise ValueError("Select a valid employee for template arrears.")
            arrears_employee = User.query.filter_by(
                id=arrears_employee_id, is_active=True,
            ).first()
            if (
                not arrears_employee
                or not values.get("company_name")
                or arrears_employee.company_name != values["company_name"]
            ):
                raise ValueError("The arrears employee must be active and belong to the selected company.")
            description = str(payload.get(
                "arrears_description",
                existing.arrears_description if existing is not None else "",
            ) or "").strip()
            if not description or len(description) > 150:
                raise ValueError("Arrears description must be between 1 and 150 characters.")
            arrears_amount = _decimal_amount(
                payload.get(
                    "arrears_amount",
                    existing.arrears_amount if existing is not None else None,
                ),
                "Arrears amount",
            )
            if arrears_amount <= 0:
                raise ValueError("Arrears amount must be greater than zero.")
            arrears_month, arrears_year = _validate_period({
                "month": payload.get(
                    "arrears_month",
                    existing.arrears_month if existing is not None else None,
                ),
                "year": payload.get(
                    "arrears_year",
                    existing.arrears_year if existing is not None else None,
                ),
            })
            values.update({
                "arrears_by_employee": {},
                "arrears_employee_id": arrears_employee_id,
                "arrears_description": description,
                "arrears_amount": float(arrears_amount),
                "arrears_month": arrears_month,
                "arrears_year": arrears_year,
            })

    for confirmation in ("earnings_confirmed", "deductions_confirmed"):
        if values.get("company_name") or (existing and existing.company_name):
            if payload.get(confirmation) is not True:
                raise ValueError("Confirm both earnings and deductions before saving the salary structure.")
    return values


@bp.post("/templates/preview")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def preview_salary_template():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Salary structure preview data must be a JSON object."}), 400
    user = User.query.get_or_404(payload.get("user_id"))
    if payload.get("company_name") != user.company_name:
        return jsonify({"message": "Select the employee's company before previewing salary."}), 400
    try:
        month, year = _validate_period(payload)
        values = _validated_salary_template_values({
            "name": "Preview",
            "company_name": user.company_name,
            "basic_pct": 50,
            "hra_pct": 20,
            "special_allowance_pct": 20,
            "other_allowance_pct": 10,
            "transport_flat": 0,
            "employee_pf_rate_pct": 0,
            "employer_pf_rate_pct": 0,
            "employer_pf_flat": 0,
            "professional_tax_flat": 0,
            "tds_flat": 0,
            "insurance_months": [],
            "insurance_amounts": {},
            **payload,
            "earnings_confirmed": True,
            "deductions_confirmed": True,
        })
        preview = _preview_payload_for_user(
            user,
            month,
            year,
            salary_template_override=SimpleNamespace(**values),
            allow_deductions_over_gross=True,
        )
        arrears_employee_ids = set(_template_arrears_by_employee(SimpleNamespace(**values)))
        if arrears_employee_ids and str(user.id) not in arrears_employee_ids:
            raise ValueError("Arrears can only be previewed for selected employees.")
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    return jsonify(_template_preview_response(user, month, year, preview))


@bp.post("/templates")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def create_template():
    payload = request.get_json(silent=True)
    try:
        values = _validated_salary_template_values(payload)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    if values["company_name"] and SalaryTemplate.query.filter(
        db.func.lower(SalaryTemplate.name) == values["name"].lower(),
        SalaryTemplate.company_name == values["company_name"],
    ).first():
        return jsonify({"message": "A salary structure with this name already exists for the selected company."}), 409
    template = SalaryTemplate(**values, created_by=int(get_jwt_identity()))
    db.session.add(template)
    db.session.commit()
    return jsonify(template.to_dict()), 201


@bp.put("/templates/<int:template_id>")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def update_template(template_id):
    template = SalaryTemplate.query.get_or_404(template_id)
    payload = request.get_json(silent=True)
    try:
        values = _validated_salary_template_values(payload, template)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    if values["company_name"] and SalaryTemplate.query.filter(
        db.func.lower(SalaryTemplate.name) == values["name"].lower(),
        SalaryTemplate.company_name == values["company_name"],
        SalaryTemplate.id != template.id,
    ).first():
        return jsonify({"message": "A salary structure with this name already exists for the selected company."}), 409
    if values["company_name"] != template.company_name and template.assigned_structures:
        return jsonify({"message": "Unassign employees before changing this structure's company."}), 409
    updated_template_values = {**template.to_dict(), **values}
    arrears_employee_ids = set(
        _template_arrears_by_employee(SimpleNamespace(**updated_template_values))
    )
    if arrears_employee_ids and any(
        str(structure.user_id) not in arrears_employee_ids for structure in template.assigned_structures
    ):
        return jsonify({
            "message": "Unassign employees not selected for arrears before updating this template."
        }), 409
    previous_values = template.to_dict()
    for field, value in values.items():
        setattr(template, field, value)
    for structure in template.assigned_structures:
        _record_payroll_audit(
            structure.user_id,
            int(get_jwt_identity()),
            "salary_template_updated",
            previous=previous_values,
            new=template.to_dict(),
        )
    db.session.commit()
    return jsonify(template.to_dict())


@bp.put("/people/<int:user_id>/salary-structure")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def save_employee_salary_structure(user_id):
    employee = User.query.get_or_404(user_id)
    structure = SalaryStructure.query.filter_by(user_id=employee.id).first()
    if structure is None or structure.annual_ctc is None or structure.annual_ctc <= 0:
        return jsonify({"message": "A positive Annual CTC must be maintained in the employee profile before saving a salary structure."}), 400

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Salary structure data must be a JSON object."}), 400
    if payload.get("company_name", employee.company_name) != employee.company_name:
        return jsonify({"message": "A salary structure must use the employee's existing company."}), 400
    if employee.company_name not in COMPANIES:
        return jsonify({"message": "The employee must belong to a supported payroll company."}), 400

    existing = structure.salary_template
    if existing and existing.company_name != employee.company_name:
        return jsonify({"message": "The employee's existing salary structure belongs to another company."}), 409
    assigned_count = (
        db.session.query(db.func.count(SalaryStructure.id))
        .filter_by(salary_template_id=existing.id)
        .scalar()
        if existing else 0
    )
    clone_shared_template = bool(existing and assigned_count > 1)
    template_to_update = existing if existing and not clone_shared_template else None
    requested_name = str(payload.get("name") or "").strip()
    if requested_name:
        name = requested_name
    elif template_to_update:
        name = template_to_update.name
    else:
        source_name = existing.name if existing else f"{employee.full_name} Salary Structure"
        suffix = employee.employee_code or str(employee.id)
        name = f"{source_name[:max(1, 100 - len(suffix) - 4)]} - {suffix}"

    values_payload = {
        **payload,
        "name": name,
        "company_name": employee.company_name,
        "description": payload.get(
            "description",
            existing.description if existing else None,
        ),
        "earnings_confirmed": True,
        "deductions_confirmed": True,
    }
    try:
        values = _validated_salary_template_values(
            values_payload,
            template_to_update,
        )
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    duplicate_query = SalaryTemplate.query.filter(
        db.func.lower(SalaryTemplate.name) == values["name"].lower(),
        SalaryTemplate.company_name == employee.company_name,
    )
    if template_to_update:
        duplicate_query = duplicate_query.filter(SalaryTemplate.id != template_to_update.id)
    if duplicate_query.first():
        return jsonify({"message": "A salary structure with this name already exists for the selected company."}), 409

    actor_id = int(get_jwt_identity())
    previous_structure = structure.to_dict()
    previous_template = existing.to_dict() if existing else None
    if template_to_update:
        template = template_to_update
        for field, value in values.items():
            setattr(template, field, value)
    else:
        template = SalaryTemplate(**values, created_by=actor_id)
        db.session.add(template)
        db.session.flush()
        structure.salary_template_id = template.id
    structure.employee_overrides = {}

    try:
        db.session.flush()
        _record_payroll_audit(
            employee.id,
            actor_id,
            "salary_structure_updated",
            previous={"structure": previous_structure, "template": previous_template},
            new={"structure": structure.to_dict(), "template": template.to_dict()},
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Employee salary structure could not be saved.")
        return jsonify({"message": "Could not save this employee's salary structure."}), 500
    return jsonify({
        "salary_template": template.to_dict(),
        "salary_structure": structure.to_dict(),
    })


@bp.delete("/templates/<int:template_id>")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def delete_template(template_id):
    template = SalaryTemplate.query.get_or_404(template_id)
    if template.assigned_structures:
        return jsonify({"message": "Unassign employees before deleting this salary structure."}), 409
    db.session.delete(template)
    db.session.commit()
    return jsonify({"message": "Template removed."})


@bp.get("/templates/<int:template_id>/employees")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def list_template_employees(template_id):
    template = SalaryTemplate.query.get_or_404(template_id)
    rows = SalaryStructure.query.filter_by(salary_template_id=template.id).all()
    return jsonify([
        {
            "id": structure.user.id,
            "full_name": structure.user.full_name,
            "employee_code": structure.user.employee_code,
            "company_name": structure.user.company_name,
            "designation": structure.user.designation,
            "department": structure.user.department.name if structure.user.department else "",
            "employee_category": getattr(structure.user, "employee_category", None),
            "employment_type": EMPLOYEE_CATEGORIES.get(getattr(structure.user, "employee_category", None), ""),
            "annual_ctc": float(structure.annual_ctc) if structure.annual_ctc is not None else None,
            "overrides": structure.employee_overrides or {},
        }
        for structure in rows if structure.user
    ])


@bp.delete("/templates/<int:template_id>/employees/<int:user_id>")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def unassign_template_employee(template_id, user_id):
    template = SalaryTemplate.query.get_or_404(template_id)
    employee = User.query.get_or_404(user_id)
    arrears_employee_ids = set(_template_arrears_by_employee(template))
    if arrears_employee_ids and str(employee.id) not in arrears_employee_ids:
        return jsonify({"message": "This arrears template can only be applied to employees selected for arrears."}), 400
    structure = SalaryStructure.query.filter_by(
        user_id=user_id,
        salary_template_id=template.id,
    ).first()
    if structure is None or employee.company_name != template.company_name:
        return jsonify({"message": "This employee is not assigned to the selected salary structure."}), 404

    previous = structure.to_dict()
    structure.salary_template_id = None
    structure.employee_overrides = {}
    actor_id = int(get_jwt_identity())
    _record_payroll_audit(
        employee.id, actor_id, "salary_structure_unassigned",
        previous=previous, new=structure.to_dict(),
    )
    db.session.commit()
    return jsonify({"message": "Employee removed from this salary structure."})


@bp.get("/templates/<int:template_id>/employees/<int:user_id>/preview")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def preview_template_employee(template_id, user_id):
    template = SalaryTemplate.query.get_or_404(template_id)
    employee = User.query.get_or_404(user_id)
    structure = SalaryStructure.query.filter_by(user_id=user_id, salary_template_id=template.id).first()
    if structure is None or employee.company_name != template.company_name:
        return jsonify({"message": "This employee is not assigned to the selected salary structure."}), 404
    try:
        month, year = _validate_period({
            "month": request.args.get("month", date.today().month),
            "year": request.args.get("year", date.today().year),
        })
        preview = _preview_payload_for_user(employee, month, year)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    return jsonify(_template_preview_response(employee, month, year, preview))


@bp.post("/templates/<int:template_id>/assign")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def assign_template_employees(template_id):
    template = SalaryTemplate.query.get_or_404(template_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("employee_ids"), list):
        return jsonify({"message": "Select one or more employees to assign."}), 400
    raw_ids = payload["employee_ids"]
    if not raw_ids or len(raw_ids) > 200:
        return jsonify({"message": "Select between 1 and 200 employees."}), 400
    try:
        employee_ids = [int(value) for value in raw_ids]
    except (TypeError, ValueError):
        return jsonify({"message": "Employee IDs must be integers."}), 400
    if any(isinstance(value, bool) for value in raw_ids) or len(set(employee_ids)) != len(employee_ids):
        return jsonify({"message": "Employee selection must contain unique employee IDs."}), 400
    employees = User.query.filter(User.id.in_(employee_ids), User.is_active.is_(True)).all()
    by_id = {employee.id: employee for employee in employees}
    if len(by_id) != len(employee_ids):
        return jsonify({"message": "One or more selected employees are missing or inactive."}), 400
    if not template.company_name:
        return jsonify({"message": "Choose a company for this salary structure before assigning employees."}), 400
    if any(employee.company_name != template.company_name for employee in employees):
        return jsonify({"message": "Employees must belong to the salary structure's company."}), 400
    arrears_employee_ids = set(_template_arrears_by_employee(template))
    if arrears_employee_ids and any(
        str(employee_id) not in arrears_employee_ids for employee_id in employee_ids
    ):
        return jsonify({"message": "This arrears template can only be assigned to employees selected for arrears."}), 400
    for employee_id in employee_ids:
        employee = by_id[employee_id]
        structure = SalaryStructure.query.filter_by(user_id=employee_id).first()
        if structure is None or structure.annual_ctc is None or structure.annual_ctc <= 0:
            return jsonify({"message": f"{employee.full_name} needs a positive Annual CTC in their profile before assignment."}), 400

    actor_id = int(get_jwt_identity())
    for employee_id in employee_ids:
        structure = SalaryStructure.query.filter_by(user_id=employee_id).first()
        if structure.salary_template_id != template.id:
            previous = structure.to_dict()
            structure.employee_overrides = {}
            structure.salary_template_id = template.id
            _record_payroll_audit(
                employee_id, actor_id, "salary_structure_assigned",
                previous=previous, new=structure.to_dict(),
            )
    db.session.commit()
    return jsonify({"message": "Salary structure assigned.", "employee_ids": employee_ids})


@bp.put("/templates/<int:template_id>/employees/<int:user_id>")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def update_template_employee_override(template_id, user_id):
    template = SalaryTemplate.query.get_or_404(template_id)
    employee = User.query.get_or_404(user_id)
    structure = SalaryStructure.query.filter_by(user_id=user_id, salary_template_id=template.id).first()
    if structure is None or employee.company_name != template.company_name:
        return jsonify({"message": "This employee is not assigned to the selected salary structure."}), 404
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Employee salary overrides must be a JSON object."}), 400
    allowed_amounts = (
        "transport_flat", "employee_pf_rate_pct", "employer_pf_rate_pct", "employer_pf_flat",
        "professional_tax_flat", "tds_flat",
    )
    overrides = dict(structure.employee_overrides or {})
    try:
        for field in allowed_amounts:
            if field in payload:
                value = _decimal_amount(payload[field], field.replace("_", " ").title())
                if field.endswith("_rate_pct") and value > 100:
                    raise ValueError(f"{field.replace('_', ' ').title()} must not exceed 100%.")
                overrides[field] = float(value)
        if "component_percentages" in payload:
            percentages = payload["component_percentages"]
            allowed = {"basic_pct", "hra_pct", "special_allowance_pct", "other_allowance_pct"}
            if not isinstance(percentages, dict) or set(percentages) - allowed:
                raise ValueError("Employee salary percentage overrides contain unsupported fields.")
            current = dict(overrides.get("component_percentages") or {})
            for field, raw_value in percentages.items():
                value = _decimal_amount(raw_value, field.replace("_", " ").title())
                if value > 100:
                    raise ValueError(f"{field.replace('_', ' ').title()} must not exceed 100%.")
                current[field] = float(value)
            overrides["component_percentages"] = current
        if "insurance_amounts" in payload:
            amounts = payload["insurance_amounts"]
            if not isinstance(amounts, dict):
                raise ValueError("Insurance overrides must be keyed by month number.")
            normalized = {}
            for month_key, raw_value in amounts.items():
                month_number = int(month_key)
                if month_number not in (1, 2) or month_number not in (template.insurance_months or []):
                    raise ValueError("Employee insurance can only be set for the selected January or February month.")
                normalized[str(month_number)] = float(_decimal_amount(raw_value, "Insurance amount"))
            overrides["insurance_amounts"] = normalized
    except (TypeError, ValueError) as exc:
        return jsonify({"message": str(exc)}), 400

    previous = copy.deepcopy(structure.employee_overrides or {})
    structure.employee_overrides = overrides
    actor_id = int(get_jwt_identity())
    _record_payroll_audit(
        employee.id, actor_id, "employee_salary_override_updated",
        previous=previous, new=overrides,
    )
    db.session.commit()
    return jsonify({"overrides": overrides})


@bp.post("/templates/<int:template_id>/apply/<int:user_id>")
@roles_required(*SALARY_STRUCTURE_EDIT_ROLES)
def apply_template(template_id, user_id):
    """Apply a percentage template to the CTC maintained in the employee profile."""
    template = SalaryTemplate.query.get_or_404(template_id)
    employee = User.query.get_or_404(user_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "Template application data must be a JSON object."}), 400
    structure = SalaryStructure.query.filter_by(user_id=user_id).first()
    if structure is None or structure.annual_ctc is None:
        return jsonify({"message": "Set the employee's Annual CTC in their profile before applying a salary template."}), 400
    ctc = _decimal_amount(structure.annual_ctc, "Annual CTC")
    if "ctc" in payload:
        try:
            requested_ctc = _decimal_amount(payload["ctc"], "Annual CTC")
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        if requested_ctc != ctc:
            return jsonify({"message": "Salary templates must use the Annual CTC maintained in the employee profile."}), 400
    if ctc <= 0:
        return jsonify({"message": "The employee's Annual CTC must be greater than zero."}), 400
    monthly = float(ctc / Decimal(12))

    previous = structure.to_dict()
    if template.company_name:
        if employee.company_name != template.company_name:
            return jsonify({"message": "This salary structure belongs to another company."}), 400
        structure.salary_template_id = template.id
        structure.employee_overrides = {}
        actor_id = int(get_jwt_identity())
        db.session.flush()
        _record_payroll_audit(
            employee.id, actor_id, "salary_structure_assigned",
            previous=previous, new=structure.to_dict(),
        )
        db.session.commit()
        return jsonify(structure.to_dict())

    structure.basic = round(monthly * template.basic_pct / 100, 2)
    structure.hra = round(monthly * template.hra_pct / 100, 2)
    structure.special_allowance = round(monthly * template.special_allowance_pct / 100, 2)
    structure.other_allowance = round(monthly * template.other_allowance_pct / 100, 2)
    structure.pf_employee = round(monthly * template.pf_employee_pct / 100, 2)
    structure.esi_employee = round(monthly * template.esi_employee_pct / 100, 2)
    structure.insurance = round(monthly * template.insurance_pct / 100, 2)
    structure.professional_tax = template.professional_tax_flat
    structure.tds = round(monthly * template.tds_pct / 100, 2)

    actor_id = int(get_jwt_identity())
    db.session.flush()
    _record_payroll_audit(
        employee.id, actor_id, "salary_template_applied",
        previous=previous, new=structure.to_dict(),
    )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Salary template application could not be saved.")
        return jsonify({"message": "Could not apply salary template."}), 500
    return jsonify(structure.to_dict())
