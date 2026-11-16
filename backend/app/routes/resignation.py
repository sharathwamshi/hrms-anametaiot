import json
import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import SalaryStructure, User
from app.models.resignation import (
    ResignationChecklistItem, ResignationDateRevision, ResignationEvent,
    ResignationPolicy, ResignationRequest, ResignationRouting,
)
from app.roles import (
    CONTRACT_EMPLOYEE, FINANCE_ACCOUNTS, HR, HR_EXECUTIVE, HR_OPERATIONS,
    MANAGER, SUPER_ADMIN,
)
from app.utils.company_time import company_today, utc_now_naive
from app.utils.push import send_push

bp = Blueprint("resignation", __name__, url_prefix="/api/resignations")

HR_ROLES = {HR, HR_EXECUTIVE, HR_OPERATIONS, SUPER_ADMIN}
FINANCE_ROLES = {FINANCE_ACCOUNTS, SUPER_ADMIN}
ROUTING_ADMIN_ROLES = {HR_OPERATIONS, SUPER_ADMIN}
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
CHECKLIST = (
    ("knowledge_transfer", "Knowledge transfer"),
    ("project_handover", "Project handover"),
    ("assets_returned", "Company assets returned"),
    ("system_access_revocation", "System access revocation"),
    ("finance_clearance", "Finance clearance"),
    ("hr_clearance", "HR clearance"),
    ("relieving_letter", "Relieving letter"),
)
TERMINAL_RESIGNATION_STATUSES = ("rejected", "withdrawn", "revoked", "completed")


def _actor():
    return db.session.get(User, int(get_jwt_identity()))


def _active_resignation(employee_id):
    return ResignationRequest.query.filter_by(employee_id=employee_id).filter(
        ResignationRequest.active_key.isnot(None),
        ResignationRequest.status.notin_(TERMINAL_RESIGNATION_STATUSES),
    ).first()


def _active_key(employee_id):
    return f"employee:{employee_id}"


def _locked_resignation(resignation_id):
    return ResignationRequest.query.filter_by(id=resignation_id).with_for_update().first_or_404()


def _role():
    actor = _actor()
    return actor.role if actor else None


def _parse_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} is required.")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid YYYY-MM-DD date.") from exc


def _event(resignation, actor_id, event_type, comments=None, stage=None, details=None):
    db.session.add(ResignationEvent(
        resignation_id=resignation.id,
        actor_id=actor_id,
        event_type=event_type,
        stage=stage or resignation.current_stage,
        status=resignation.status,
        comments=comments,
        details=json.dumps(details, default=str) if details is not None else None,
    ))


def _user_summary(user_id):
    user = db.session.get(User, user_id) if user_id else None
    if user is None:
        return None
    return {
        "id": user.id,
        "full_name": user.full_name,
        "employee_code": user.employee_code,
        "role": user.role,
    }


def _remove_uncommitted_file(path):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            current_app.logger.exception("Uncommitted resignation document could not be removed.")


def _serialize_event(event):
    return {
        "id": event.id,
        "event_type": event.event_type,
        "stage": event.stage,
        "status": event.status,
        "comments": event.comments,
        "details": json.loads(event.details) if event.details else None,
        "actor": _user_summary(event.actor_id),
        "created_at": event.created_at.isoformat() + "Z",
    }


def _serialize_revision(revision):
    return {
        "id": revision.id,
        "proposed_last_working_date": revision.proposed_last_working_date.isoformat(),
        "reason": revision.reason,
        "status": revision.status,
        "current_stage": revision.current_stage,
        "created_at": revision.created_at.isoformat() + "Z",
    }


def _serialize(resignation, include_history=False):
    actor = _actor()
    employee = db.session.get(User, resignation.employee_id)
    revision = db.session.get(ResignationDateRevision, resignation.pending_revision_id) if resignation.pending_revision_id else None
    checklist = ResignationChecklistItem.query.filter_by(
        resignation_id=resignation.id
    ).order_by(ResignationChecklistItem.id).all()
    today = company_today()
    approved_last_day = resignation.approved_last_working_date
    remaining_days = max(0, (approved_last_day - today).days) if (
        approved_last_day and resignation.dates_approved_at
    ) else None
    data = {
        "id": resignation.id,
        "employee": {
            "id": employee.id,
            "full_name": employee.full_name,
            "employee_code": employee.employee_code,
            "department": employee.department.name if employee.department else None,
            "company_name": resignation.company_name,
        } if employee else None,
        "employee_id": resignation.employee_id,
        "company_name": resignation.company_name,
        "department_name": resignation.department_name,
        "resignation_date": resignation.resignation_date.isoformat(),
        "original_last_working_date": resignation.original_last_working_date.isoformat(),
        "proposed_last_working_date": resignation.proposed_last_working_date.isoformat(),
        "approved_last_working_date": approved_last_day.isoformat() if approved_last_day else None,
        "notice_period_days": resignation.notice_period_days,
        "remaining_notice_period_days": remaining_days,
        "dates_approved_at": resignation.dates_approved_at.isoformat() + "Z" if resignation.dates_approved_at else None,
        "reason": resignation.reason,
        "comments": resignation.comments,
        "status": resignation.status,
        "current_stage": resignation.current_stage,
        "withdrawal_previous_stage": resignation.withdrawal_previous_stage,
        "active_key": resignation.active_key,
        "current_approver": _user_summary(resignation.current_approver_id),
        "pending_revision": _serialize_revision(revision) if revision else None,
        "document_available": bool(resignation.document_storage_key),
        "document_filename": resignation.document_filename,
        "finance": {
            "pending_salary": str(resignation.finance_pending_salary) if resignation.finance_pending_salary is not None else None,
            "advances": str(resignation.finance_advances) if resignation.finance_advances is not None else None,
            "reimbursements": str(resignation.finance_reimbursements) if resignation.finance_reimbursements is not None else None,
            "other_dues": str(resignation.finance_other_dues) if resignation.finance_other_dues is not None else None,
            "final_settlement_amount": str(resignation.final_settlement_amount) if resignation.final_settlement_amount is not None else None,
            "final_settlement_status": resignation.final_settlement_status,
            "cleared_at": resignation.finance_cleared_at.isoformat() + "Z" if resignation.finance_cleared_at else None,
        },
        "checklist": [{
            "key": item.item_key,
            "label": item.label,
            "status": item.status,
            "completed_by": _user_summary(item.completed_by),
            "completed_at": item.completed_at.isoformat() + "Z" if item.completed_at else None,
        } for item in checklist],
        "created_at": resignation.created_at.isoformat() + "Z",
    }
    data["exit_choice"] = resignation.exit_choice
    data["exit_policy_snapshot"] = None
    data["buyback_estimated_amount"] = None
    data["buyback_unserved_days"] = resignation.buyback_unserved_days
    data["buyback_calculation_verified_at"] = (
        resignation.buyback_calculation_verified_at.isoformat() + "Z"
        if resignation.buyback_calculation_verified_at else None
    )
    data["buyback_payment_status"] = None
    data["buyback_payment_reference"] = None
    data["buyback_payment_verified_at"] = (
        resignation.buyback_payment_verified_at.isoformat() + "Z"
        if resignation.buyback_payment_verified_at else None
    )
    can_view_compensation_details = (
        actor.id == resignation.employee_id or actor.role in HR_ROLES | FINANCE_ROLES
    )
    if can_view_compensation_details:
        data["finance"]["buyback_payment_reference"] = resignation.buyback_payment_reference
    snapshot = resignation.exit_policy_snapshot or {}
    if can_view_compensation_details:
        data["exit_policy_snapshot"] = snapshot
        data["buyback_estimated_amount"] = (
            str(resignation.buyback_estimated_amount)
            if resignation.buyback_estimated_amount is not None else None
        )
        data["buyback_payment_status"] = resignation.buyback_payment_status
        data["buyback_payment_reference"] = resignation.buyback_payment_reference
    elif snapshot:
        data["exit_policy_snapshot"] = {
            "notice_period_days": snapshot.get("notice_period_days"),
            "expected_last_working_date": snapshot.get("expected_last_working_date"),
        }
    if include_history:
        data["history"] = [
            _serialize_event(event)
            for event in ResignationEvent.query.filter_by(resignation_id=resignation.id)
            .order_by(ResignationEvent.created_at, ResignationEvent.id).all()
        ]
    return data


def _l2_approvers(company_name, exclude_user_id=None):
    query = (
        ResignationRouting.query.filter_by(company_name=company_name)
        .join(User, User.id == ResignationRouting.approver_user_id)
        .filter(User.is_active.is_(True))
    )
    if exclude_user_id:
        query = query.filter(ResignationRouting.approver_user_id != exclude_user_id)
    return [row.approver_user_id for row in query.order_by(ResignationRouting.id).all()]


def _stage_status(stage):
    return {
        "manager": "manager_pending",
        "l2": "l2_pending",
        "hr": "hr_pending",
        "finance": "finance_pending",
        "exit": "exit_pending",
    }.get(stage, "manager_pending")


def _stage_recipients(resignation, stage):
    if stage == "manager":
        return [resignation.current_approver_id] if resignation.current_approver_id else []
    if stage == "l2":
        return _l2_approvers(resignation.company_name)
    roles = HR_ROLES if stage in {"hr", "exit"} else FINANCE_ROLES if stage == "finance" else set()
    if not roles:
        return []
    return [user.id for user in User.query.filter(
        User.is_active.is_(True), User.role.in_(roles)
    ).all()]


def _notify(resignation, user_ids, title, body):
    send_push(
        user_ids, title, body,
        {"type": "resignation", "resignation_id": resignation.id},
    )


def _notify_stage(resignation):
    stage_label = {
        "manager": "Manager",
        "l2": "L2 / Director",
        "hr": "HR",
        "finance": "Finance",
        "exit": "Exit & Relieving",
    }.get(resignation.current_stage, "Approver")
    _notify(
        resignation,
        _stage_recipients(resignation, resignation.current_stage),
        "Resignation requires review",
        f"A resignation request is waiting for {stage_label}.",
    )


def _may_view(resignation, actor):
    if actor.id == resignation.employee_id:
        return True
    if actor.role == MANAGER:
        employee = db.session.get(User, resignation.employee_id)
        if employee and employee.manager_id == actor.id:
            return True
    if actor.role in HR_ROLES:
        return True
    if actor.role in FINANCE_ROLES:
        if resignation.current_stage in {"finance", "exit"}:
            return True
        if resignation.status == "withdrawal_pending" and resignation.withdrawal_approver_role == "finance":
            return True
        return ResignationEvent.query.filter_by(
            resignation_id=resignation.id, stage="finance"
        ).first() is not None
    return (
        resignation.current_stage == "l2"
        and actor.id in _l2_approvers(resignation.company_name)
    ) or (
        resignation.status == "withdrawal_pending"
        and resignation.withdrawal_approver_id == actor.id
    )


def _can_approve_stage(resignation, actor, stage):
    if actor.id == resignation.employee_id:
        return False
    if stage == "manager":
        return (
            actor.role in {MANAGER, HR_OPERATIONS, SUPER_ADMIN}
            and resignation.current_approver_id == actor.id
        )
    if stage == "l2":
        return actor.id in _l2_approvers(resignation.company_name)
    if stage == "hr":
        return actor.role in HR_ROLES
    if stage == "finance":
        return actor.role in FINANCE_ROLES
    return False


def _set_stage(resignation, stage):
    resignation.current_stage = stage
    resignation.status = _stage_status(stage)
    resignation.current_approver_id = resignation.employee_id and (
        db.session.get(User, resignation.employee_id).manager_id if stage == "manager" else None
    )


def _parse_amount(payload, key):
    value = payload.get(key)
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{key.replace('_', ' ').capitalize()} must be a valid amount.") from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal("9999999999.99"):
        raise ValueError(f"{key.replace('_', ' ').capitalize()} must be a non-negative amount.")
    return amount.quantize(Decimal("0.01"))


def _parse_integer(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a whole number.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a whole number.") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError(f"{label} must be a whole number.")
    return int(number)


def _policy_snapshot(policy, annual_ctc, expected_last_working_date):
    estimated_amount = None
    if annual_ctc is not None:
        estimated_amount = (
            (annual_ctc / Decimal(policy.buyback_daily_divisor))
            * Decimal(policy.buyback_multiplier)
            * Decimal(policy.notice_period_days)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if estimated_amount > Decimal("9999999999.99"):
            raise ValueError("The estimated buyback amount exceeds the supported settlement range.")
    return {
        "policy_id": policy.id,
        "policy_version": policy.version,
        "company_name": policy.company_name,
        "notice_period_days": policy.notice_period_days,
        "buyback_daily_divisor": policy.buyback_daily_divisor,
        "buyback_multiplier": str(policy.buyback_multiplier),
        "annual_ctc": str(annual_ctc) if annual_ctc is not None else None,
        "expected_last_working_date": expected_last_working_date.isoformat(),
        "buyback_unserved_days": policy.notice_period_days,
        "buyback_estimated_amount": str(estimated_amount) if estimated_amount is not None else None,
        "buyback_formula": "annual CTC / configured divisor * configured multiplier * full notice days",
    }


def _snapshot_buyback_amount(snapshot):
    try:
        annual_ctc = Decimal(snapshot["annual_ctc"])
        divisor = int(snapshot["buyback_daily_divisor"])
        multiplier = Decimal(snapshot["buyback_multiplier"])
        notice_days = int(snapshot["buyback_unserved_days"])
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("The saved buyback calculation snapshot is incomplete.") from exc
    if (
        not annual_ctc.is_finite() or annual_ctc <= 0
        or divisor <= 0 or not multiplier.is_finite() or multiplier <= 0
        or notice_days <= 0
    ):
        raise ValueError("The saved buyback calculation snapshot is invalid.")
    return (
        (annual_ctc / Decimal(divisor)) * multiplier * Decimal(notice_days)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _serialize_policy(policy):
    return {
        "id": policy.id,
        "company_name": policy.company_name,
        "notice_period_days": policy.notice_period_days,
        "buyback_daily_divisor": policy.buyback_daily_divisor,
        "buyback_multiplier": (
            str(policy.buyback_multiplier) if policy.buyback_multiplier is not None else None
        ),
        "version": policy.version,
        "updated_at": policy.updated_at.isoformat() + "Z" if policy.updated_at else None,
    }


def _policy_incomplete(policy):
    return (
        policy.notice_period_days is None
        or policy.notice_period_days < 1
        or policy.buyback_daily_divisor is None
        or policy.buyback_daily_divisor < 1
        or policy.buyback_multiplier is None
        or policy.buyback_multiplier <= 0
    )


def _file_bytes(file):
    size_limit = current_app.config["MAX_RESIGNATION_DOCUMENT_BYTES"]
    content = file.stream.read(size_limit + 1)
    file.stream.seek(0)
    if not content:
        raise ValueError("The selected document is empty.")
    if len(content) > size_limit:
        raise ValueError(f"Documents must be {size_limit // (1024 * 1024)} MB or smaller.")
    extension = os.path.splitext(secure_filename(file.filename))[1].lower()
    signature_ok = {
        ".pdf": content.startswith(b"%PDF-"),
        ".doc": content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")),
        ".docx": content.startswith(b"PK\x03\x04"),
    }[extension]
    if not signature_ok:
        raise ValueError("The document contents do not match the selected file type.")
    return content, extension


@bp.get("/my")
@jwt_required()
def my_resignations():
    actor = _actor()
    rows = ResignationRequest.query.filter_by(employee_id=actor.id).order_by(
        ResignationRequest.created_at.desc(), ResignationRequest.id.desc()
    ).all()
    return jsonify([_serialize(row, include_history=True) for row in rows])


@bp.get("/context")
@jwt_required()
def resignation_context():
    return jsonify({"company_today": company_today().isoformat()})


@bp.get("/policy/quote")
@jwt_required()
def resignation_policy_quote():
    actor = _actor()
    if actor is None:
        return jsonify({"message": "The employee record for the authenticated account could not be found."}), 404
    policy = ResignationPolicy.query.filter_by(company_name=actor.company_name).first()
    if policy is None:
        return jsonify({
            "message": "Resignation policy has not been configured for your company. Contact HR."
        }), 409
    if _policy_incomplete(policy):
        return jsonify({
            "message": "Your company's resignation policy is incomplete. Contact HR to finish configuring it."
        }), 409
    expected_last_working_date = company_today() + timedelta(days=policy.notice_period_days)
    salary = SalaryStructure.query.filter_by(user_id=actor.id).first()
    annual_ctc = Decimal(salary.annual_ctc) if salary and salary.annual_ctc is not None else None
    can_buyback = annual_ctc is not None and annual_ctc > 0
    message = None
    try:
        snapshot = _policy_snapshot(policy, annual_ctc if can_buyback else None, expected_last_working_date)
    except ValueError as exc:
        snapshot = _policy_snapshot(policy, None, expected_last_working_date)
        can_buyback = False
        message = str(exc)
    return jsonify({
        "policy_version": policy.version,
        "notice_period_days": policy.notice_period_days,
        "expected_last_working_date": expected_last_working_date.isoformat(),
        "buyback_available": can_buyback,
        "buyback_estimated_amount": snapshot["buyback_estimated_amount"],
        "buyback_unserved_days": policy.notice_period_days,
        "buyback_formula": snapshot["buyback_formula"],
        "message": message or (
            None if can_buyback else "Buyback is unavailable because your annual CTC is not configured."
        ),
    })


@bp.get("/policy")
@jwt_required()
def list_resignation_policies():
    actor = _actor()
    if actor is None or actor.role not in HR_ROLES:
        return jsonify({"message": "Only authorized HR or Super Admin users may manage resignation policy."}), 403
    companies = [
        row[0] for row in db.session.query(User.company_name)
        .filter(User.is_active.is_(True), User.company_name.isnot(None))
        .distinct().order_by(User.company_name).all()
    ]
    policies = ResignationPolicy.query.order_by(ResignationPolicy.company_name).all()
    return jsonify({
        "companies": companies,
        "policies": [_serialize_policy(policy) for policy in policies],
    })


@bp.put("/policy")
@jwt_required()
def save_resignation_policy():
    actor = _actor()
    if actor is None or actor.role not in HR_ROLES:
        return jsonify({"message": "Only authorized HR or Super Admin users may manage resignation policy."}), 403
    payload = request.get_json(silent=True) or {}
    company_name = payload.get("company_name")
    if not isinstance(company_name, str) or not company_name.strip() or len(company_name.strip()) > 150:
        return jsonify({"message": "Select a valid company for this resignation policy."}), 400
    company_name = company_name.strip()
    if not User.query.filter_by(company_name=company_name, is_active=True).first():
        return jsonify({"message": "The selected company has no active employee records."}), 400
    try:
        notice_period_days = _parse_integer(payload.get("notice_period_days"), "Notice period")
        buyback_daily_divisor = _parse_integer(payload.get("buyback_daily_divisor"), "Buyback divisor")
        buyback_multiplier = Decimal(str(payload.get("buyback_multiplier")))
        if not 1 <= notice_period_days <= 3650:
            raise ValueError
        if not 1 <= buyback_daily_divisor <= 366:
            raise ValueError
        if not buyback_multiplier.is_finite() or not Decimal("0.0001") <= buyback_multiplier <= Decimal("100"):
            raise ValueError
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({
            "message": "Enter a notice period from 1 to 3,650 days, a divisor from 1 to 366, and a positive multiplier up to 100."
        }), 400

    policy = ResignationPolicy.query.filter_by(company_name=company_name).with_for_update().first()
    if policy is None:
        policy = ResignationPolicy(
            company_name=company_name,
            notice_period_days=notice_period_days,
            buyback_daily_divisor=buyback_daily_divisor,
            buyback_multiplier=buyback_multiplier,
            version=1,
            updated_by=actor.id,
        )
        db.session.add(policy)
    else:
        policy.notice_period_days = notice_period_days
        policy.buyback_daily_divisor = buyback_daily_divisor
        policy.buyback_multiplier = buyback_multiplier
        policy.version += 1
        policy.updated_by = actor.id
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "A policy for this company was saved by another user. Reload and try again."}), 409
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Resignation policy could not be saved.")
        return jsonify({"message": "Could not save resignation policy. Please try again."}), 500
    return jsonify(_serialize_policy(policy))


@bp.post("")
@jwt_required()
def submit_resignation():
    actor = _actor()
    if actor is None:
        return jsonify({"message": "The employee record for the authenticated account could not be found."}), 404
    if actor.role == CONTRACT_EMPLOYEE:
        return jsonify({"message": "Contract employees cannot submit a resignation request through this workflow."}), 403
    if not actor.is_active:
        return jsonify({"message": "Your account is inactive and cannot submit a resignation request."}), 403
    current_status = (actor.employment_status or "").strip().lower()
    if current_status != "active":
        if _active_resignation(actor.id):
            return jsonify({"message": "You already have an active resignation request."}), 409
        status_label = current_status.replace("_", " ") if current_status else "not set"
        return jsonify({
            "message": (
                "A resignation request can only be submitted while your employment status is Active. "
                f"Your current employment status is {status_label}."
            )
        }), 409
    if _active_resignation(actor.id):
        return jsonify({"message": "You already have an active resignation request."}), 409
    manager = db.session.get(User, actor.manager_id) if actor.manager_id else None
    if (
        manager is None
        or not manager.is_active
        or manager.id == actor.id
        or manager.role not in {MANAGER, HR_OPERATIONS, SUPER_ADMIN}
    ):
        return jsonify({"message": "A valid direct manager must be assigned before submitting a resignation."}), 400
    if not _l2_approvers(actor.company_name, actor.id):
        return jsonify({"message": "No L2 / Director approver is configured for your company. Contact HR Operations."}), 409

    payload = request.form if request.form else (request.get_json(silent=True) or {})
    try:
        exit_choice = payload.get("exit_choice")
        if exit_choice not in {"serve_full_notice", "full_notice_buyback"}:
            raise ValueError("Choose either Serve Full Notice Period or Full Notice Period Buyback.")
        policy = ResignationPolicy.query.filter_by(company_name=actor.company_name).first()
        if policy is None:
            return jsonify({
                "message": "Resignation policy has not been configured for your company. Contact HR."
            }), 409
        if _policy_incomplete(policy):
            return jsonify({
                "message": "Your company's resignation policy is incomplete. Contact HR to finish configuring it."
            }), 409
        try:
            policy_version = _parse_integer(payload.get("policy_version"), "Policy version")
        except ValueError:
            raise ValueError("Refresh the resignation policy quote before submitting.")
        if policy_version != policy.version:
            return jsonify({
                "message": "Resignation policy changed. Refresh the quote and review the updated terms before submitting."
            }), 409
        resignation_date = company_today()
        expected_last_working_date = resignation_date + timedelta(days=policy.notice_period_days)
        supplied_last_day = payload.get("proposed_last_working_date")
        if supplied_last_day and supplied_last_day != expected_last_working_date.isoformat():
            return jsonify({
                "message": "The resignation policy quote is out of date. Refresh it before submitting."
            }), 409
        last_day = expected_last_working_date
        salary = SalaryStructure.query.filter_by(user_id=actor.id).first()
        annual_ctc = Decimal(salary.annual_ctc) if salary and salary.annual_ctc is not None else None
        if exit_choice == "full_notice_buyback" and (annual_ctc is None or annual_ctc <= 0):
            return jsonify({
                "message": "Full notice buyback is unavailable because your annual CTC is not configured. Contact HR."
            }), 409
        try:
            snapshot = _policy_snapshot(
                policy,
                annual_ctc if exit_choice == "full_notice_buyback" else None,
                expected_last_working_date,
            )
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 409
        reason = (payload.get("reason") or "").strip()
        if not reason:
            raise ValueError("Reason for resignation is required.")
        if len(reason) > 5000:
            raise ValueError("Reason for resignation must be 5,000 characters or fewer.")
        comments = (payload.get("comments") or "").strip() or None
        if comments and len(comments) > 5000:
            raise ValueError("Additional comments must be 5,000 characters or fewer.")
        file = request.files.get("document")
        if file and file.filename:
            filename = secure_filename(file.filename)
            extension = os.path.splitext(filename)[1].lower()
            if extension not in ALLOWED_EXTENSIONS:
                raise ValueError("Allowed supporting document types are PDF, DOC, and DOCX.")
            content, extension = _file_bytes(file)
        else:
            filename = None
            content = None
            extension = None
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    resignation = ResignationRequest(
        employee_id=actor.id,
        company_name=actor.company_name,
        department_name=actor.department.name if actor.department else None,
        resignation_date=company_today(),
        exit_choice=exit_choice,
        exit_policy_snapshot=snapshot,
        buyback_estimated_amount=(
            Decimal(snapshot["buyback_estimated_amount"])
            if exit_choice == "full_notice_buyback" else None
        ),
        buyback_unserved_days=(
            policy.notice_period_days if exit_choice == "full_notice_buyback" else None
        ),
        buyback_payment_status="pending" if exit_choice == "full_notice_buyback" else None,
        original_last_working_date=last_day,
        proposed_last_working_date=last_day,
        reason=reason,
        comments=comments,
        status="manager_pending",
        current_stage="manager",
        current_approver_id=manager.id,
        active_key=_active_key(actor.id),
        final_settlement_status="pending",
    )
    saved_path = None
    try:
        db.session.add(resignation)
        db.session.flush()
        if content is not None:
            storage_key = f"{actor.id}/{uuid.uuid4().hex}{extension}"
            saved_path = os.path.join(
                current_app.config["RESIGNATION_DOCUMENT_FOLDER"], *storage_key.split("/")
            )
            os.makedirs(os.path.dirname(saved_path), exist_ok=True)
            with open(saved_path, "wb") as saved_file:
                saved_file.write(content)
            resignation.document_storage_key = storage_key
            resignation.document_filename = filename
            resignation.document_mime_type = MIME_TYPES[extension]
            resignation.document_size = len(content)
        for item_key, label in CHECKLIST:
            db.session.add(ResignationChecklistItem(
                resignation_id=resignation.id,
                item_key=item_key,
                label=label,
            ))
        actor.employment_status = "resignation_pending"
        actor.resignation_requested_at = utc_now_naive()
        actor.resignation_reviewed_at = None
        actor.resignation_reviewed_by = None
        actor.resignation_decision = None
        actor.notice_period_days = None
        actor.last_working_day = None
        actor.resignation_withdrawn_at = None
        actor.left_company_at = None
        _event(resignation, actor.id, "submitted", comments, stage="employee")
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        _remove_uncommitted_file(saved_path)
        return jsonify({"message": "You already have an active resignation request."}), 409
    except (OSError, SQLAlchemyError):
        db.session.rollback()
        _remove_uncommitted_file(saved_path)
        current_app.logger.exception("Resignation request could not be saved.")
        return jsonify({"message": "Could not submit the resignation request. Please try again."}), 500
    _notify_stage(resignation)
    return jsonify(_serialize(resignation, include_history=True)), 201


@bp.get("/queue")
@jwt_required()
def resignation_queue():
    actor = _actor()
    rows = ResignationRequest.query.filter(
        ResignationRequest.active_key.isnot(None),
        ResignationRequest.status.notin_(TERMINAL_RESIGNATION_STATUSES),
    ).order_by(ResignationRequest.created_at.asc()).all()
    visible = [
        row for row in rows
        if (
            (row.status == "withdrawal_pending" and (
                row.withdrawal_approver_id == actor.id
                or (
                    row.withdrawal_approver_role == "hr" and actor.role in HR_ROLES
                )
                or (
                    row.withdrawal_approver_role == "finance" and actor.role in FINANCE_ROLES
                )
            ))
            or (row.current_stage == "manager" and row.current_approver_id == actor.id)
            or (row.current_stage == "l2" and actor.id in _l2_approvers(row.company_name))
            or (row.current_stage == "hr" and actor.role in HR_ROLES)
            or (row.current_stage == "finance" and actor.role in FINANCE_ROLES)
            or (row.current_stage == "exit" and actor.role in HR_ROLES)
        )
    ]
    return jsonify([_serialize(row) for row in visible])


@bp.get("/history")
@jwt_required()
def resignation_history():
    actor = _actor()
    if actor.role not in HR_ROLES | FINANCE_ROLES:
        return jsonify({"message": "Only HR and Finance may view the organization resignation history."}), 403
    rows = ResignationRequest.query.order_by(
        ResignationRequest.created_at.desc(), ResignationRequest.id.desc()
    ).all()
    return jsonify([_serialize(row) for row in rows])


@bp.get("/<int:resignation_id>")
@jwt_required()
def resignation_details(resignation_id):
    resignation = ResignationRequest.query.get_or_404(resignation_id)
    actor = _actor()
    if not _may_view(resignation, actor):
        return jsonify({"message": "You do not have permission to view this resignation."}), 403
    return jsonify(_serialize(resignation, include_history=True))


@bp.patch("/<int:resignation_id>/details")
@jwt_required()
def update_resignation_details(resignation_id):
    resignation = _locked_resignation(resignation_id)
    actor = _actor()
    if actor.id != resignation.employee_id:
        return jsonify({"message": "Only the employee may edit their resignation details."}), 403
    if not resignation.active_key or resignation.status != "manager_pending" or resignation.pending_revision_id:
        return jsonify({"message": "Resignation details can only be edited while awaiting the initial manager review."}), 409
    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason")
    comments = payload.get("comments")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 5000:
        return jsonify({"message": "Reason for resignation is required and must be 5,000 characters or fewer."}), 400
    if comments is not None and (not isinstance(comments, str) or len(comments.strip()) > 5000):
        return jsonify({"message": "Additional comments must be 5,000 characters or fewer."}), 400
    previous_reason = resignation.reason
    resignation.reason = reason.strip()
    resignation.comments = (comments or "").strip() or None
    _event(resignation, actor.id, "details_updated", details={
        "previous_reason": previous_reason,
        "updated_reason": resignation.reason,
    })
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Resignation details could not be updated.")
        return jsonify({"message": "Could not update resignation details. Please try again."}), 500
    _notify_stage(resignation)
    return jsonify(_serialize(resignation, include_history=True))


@bp.post("/<int:resignation_id>/decision")
@jwt_required()
def resignation_decision(resignation_id):
    resignation = _locked_resignation(resignation_id)
    actor = _actor()
    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision")
    if decision not in {"approve", "reject"}:
        return jsonify({"message": "Decision must be approve or reject."}), 400
    comment = (payload.get("comment") or "").strip() or None
    if decision == "reject" and not comment:
        return jsonify({"message": "A comment is required when rejecting a resignation."}), 400
    if resignation.status == "withdrawal_pending":
        return jsonify({"message": "Use the withdrawal decision action for this request."}), 409

    stage = resignation.current_stage
    if resignation.status != _stage_status(stage) or not _can_approve_stage(resignation, actor, stage):
        return jsonify({"message": "You are not the assigned approver for the current stage."}), 403
    if resignation.pending_revision_id and not (stage == "finance" and decision == "approve"):
        revision = db.session.get(ResignationDateRevision, resignation.pending_revision_id)
        if revision is None:
            return jsonify({"message": "The pending date change could not be found."}), 409
        if decision == "reject":
            revision.status = "rejected"
            revision.decided_at = utc_now_naive()
            resignation.approved_last_working_date = revision.prior_approved_last_working_date
            resignation.notice_period_days = revision.prior_notice_period_days
            resignation.dates_approved_at = revision.prior_dates_approved_at
            resignation.status = revision.prior_status
            resignation.current_stage = revision.prior_stage
            resignation.current_approver_id = (
                db.session.get(User, resignation.employee_id).manager_id
                if revision.prior_stage == "manager" else None
            )
            employee = db.session.get(User, resignation.employee_id)
            employee.employment_status = (
                "notice_period" if revision.prior_approved_last_working_date else "resignation_pending"
            )
            employee.notice_period_days = revision.prior_notice_period_days
            employee.last_working_day = revision.prior_approved_last_working_date
            employee.resignation_decision = (
                "accepted" if revision.prior_approved_last_working_date else None
            )
            resignation.pending_revision_id = None
            _event(resignation, actor.id, "date_change_rejected", comment, stage=stage,
                   details={"revision_id": revision.id})
        else:
            next_stage = {"manager": "l2", "l2": "hr", "hr": "finance"}.get(stage)
            if not next_stage:
                return jsonify({"message": "This date change cannot be approved at the current stage."}), 409
            if stage == "hr":
                if revision.proposed_last_working_date < company_today():
                    return jsonify({"message": "The proposed last working date cannot be in the past."}), 400
                expected_date = (resignation.exit_policy_snapshot or {}).get("expected_last_working_date")
                if expected_date and revision.proposed_last_working_date < _parse_date(
                    expected_date, "Policy last working date"
                ):
                    return jsonify({
                        "message": "The revised date cannot be earlier than the configured full notice period."
                    }), 400
                resignation.approved_last_working_date = revision.proposed_last_working_date
                resignation.notice_period_days = (
                    revision.proposed_last_working_date - resignation.resignation_date
                ).days
                resignation.dates_approved_at = utc_now_naive()
                employee = db.session.get(User, resignation.employee_id)
                employee.employment_status = "notice_period"
                employee.last_working_day = revision.proposed_last_working_date
                employee.notice_period_days = resignation.notice_period_days
                employee.resignation_decision = "accepted"
                resignation.status = "finance_pending"
                resignation.current_stage = "finance"
                resignation.current_approver_id = None
            else:
                _set_stage(resignation, next_stage)
            revision.current_stage = next_stage
            revision.status = _stage_status(next_stage)
            _event(resignation, actor.id, "date_change_approved", comment, stage=stage,
                   details={"revision_id": revision.id, "next_stage": next_stage})
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Resignation date revision decision could not be saved.")
            return jsonify({"message": "Could not save this decision. Please try again."}), 500
        _notify_stage(resignation)
        _notify(resignation, [resignation.employee_id], "Resignation update",
                "Your proposed last working date has been reviewed.")
        return jsonify(_serialize(resignation, include_history=True))

    if decision == "reject":
        resignation.status = "rejected"
        resignation.current_stage = stage
        resignation.current_approver_id = None
        resignation.active_key = None
        employee = db.session.get(User, resignation.employee_id)
        employee.employment_status = "active"
        employee.resignation_decision = "rejected"
        employee.resignation_reviewed_at = utc_now_naive()
        employee.resignation_reviewed_by = actor.id
        employee.notice_period_days = None
        employee.last_working_day = None
        _event(resignation, actor.id, "rejected", comment, stage=stage)
    elif stage == "manager":
        _set_stage(resignation, "l2")
        _event(resignation, actor.id, "approved", comment, stage=stage)
    elif stage == "l2":
        _set_stage(resignation, "hr")
        _event(resignation, actor.id, "approved", comment, stage=stage)
    elif stage == "hr":
        employee = db.session.get(User, resignation.employee_id)
        if resignation.exit_choice == "full_notice_buyback":
            snapshot = resignation.exit_policy_snapshot or {}
            try:
                calculated_amount = _snapshot_buyback_amount(snapshot)
            except ValueError as exc:
                return jsonify({"message": str(exc)}), 409
            if (
                resignation.buyback_estimated_amount is None
                or calculated_amount != Decimal(resignation.buyback_estimated_amount)
                or str(calculated_amount) != snapshot.get("buyback_estimated_amount")
            ):
                return jsonify({"message": "The saved buyback calculation does not match its policy snapshot."}), 409
            if payload.get("buyback_calculation_verified") is not True:
                return jsonify({"message": "HR must verify the full buyback calculation before approval."}), 400
            resignation.buyback_calculation_verified_by = actor.id
            resignation.buyback_calculation_verified_at = utc_now_naive()
            resignation.notice_period_days = int(snapshot["notice_period_days"])
            employee.employment_status = "resignation_pending"
            employee.last_working_day = None
            employee.notice_period_days = None
            employee.resignation_decision = "accepted"
        else:
            approved_date = payload.get("approved_last_working_date")
            try:
                approved_date = _parse_date(
                    approved_date or resignation.proposed_last_working_date.isoformat(),
                    "Approved last working date",
                )
                if approved_date < company_today():
                    raise ValueError("Approved last working date cannot be in the past.")
                snapshot = resignation.exit_policy_snapshot or {}
                expected_date = snapshot.get("expected_last_working_date")
                if expected_date and approved_date < _parse_date(expected_date, "Policy last working date"):
                    raise ValueError("Approved last working date cannot be earlier than the configured full notice period.")
            except ValueError as exc:
                return jsonify({"message": str(exc)}), 400
            resignation.approved_last_working_date = approved_date
            resignation.notice_period_days = (approved_date - resignation.resignation_date).days
            resignation.dates_approved_at = utc_now_naive()
            employee.employment_status = "notice_period"
            employee.last_working_day = approved_date
            employee.notice_period_days = resignation.notice_period_days
            employee.resignation_decision = "accepted"
        _set_stage(resignation, "finance")
        _event(
            resignation, actor.id, "approved", comment, stage=stage,
            details=(
                {"buyback_calculation_verified": True}
                if resignation.exit_choice == "full_notice_buyback"
                else {"approved_last_working_date": approved_date.isoformat()}
            ),
        )
    elif stage == "finance":
        try:
            amounts = {
                "finance_pending_salary": _parse_amount(payload, "pending_salary"),
                "finance_advances": _parse_amount(payload, "advances"),
                "finance_reimbursements": _parse_amount(payload, "reimbursements"),
                "finance_other_dues": _parse_amount(payload, "other_dues"),
                "final_settlement_amount": _parse_amount(payload, "final_settlement_amount"),
            }
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
        settlement_status = payload.get("final_settlement_status")
        if settlement_status != "cleared":
            return jsonify({"message": "Finance clearance must be marked cleared before approval."}), 400
        finance_fields = {
            "finance_pending_salary": "Pending salary",
            "finance_advances": "Advances",
            "finance_reimbursements": "Reimbursements",
            "finance_other_dues": "Other dues",
            "final_settlement_amount": "Final settlement amount",
        }
        for field, title in finance_fields.items():
            if amounts[field] is None:
                amounts[field] = getattr(resignation, field)
            if amounts[field] is None:
                return jsonify({"message": f"{title} is required before finance clearance."}), 400
        for field, value in amounts.items():
            setattr(resignation, field, value)
        if resignation.exit_choice == "full_notice_buyback":
            payment_reference = payload.get("buyback_payment_reference")
            if payment_reference is not None:
                if not isinstance(payment_reference, str) or len(payment_reference.strip()) > 255:
                    return jsonify({"message": "Buyback payment reference must be 255 characters or fewer."}), 400
                if payment_reference.strip():
                    resignation.buyback_payment_reference = payment_reference.strip()
            if payload.get("buyback_payment_verified") is not True:
                return jsonify({"message": "Finance must verify the full buyback payment before clearance."}), 400
            if not resignation.buyback_payment_reference:
                return jsonify({"message": "A payment reference is required before buyback clearance."}), 400
            if not resignation.buyback_calculation_verified_at:
                return jsonify({"message": "HR must verify the buyback calculation before Finance clearance."}), 409
            resignation.buyback_payment_status = "verified"
            resignation.buyback_payment_verified_by = actor.id
            resignation.buyback_payment_verified_at = utc_now_naive()
            resignation.approved_last_working_date = company_today()
            employee = db.session.get(User, resignation.employee_id)
            employee.employment_status = "notice_period"
            employee.last_working_day = resignation.approved_last_working_date
            employee.notice_period_days = resignation.notice_period_days
            employee.resignation_decision = "accepted"
        resignation.final_settlement_status = "cleared"
        resignation.finance_cleared_at = utc_now_naive()
        if resignation.pending_revision_id:
            revision = db.session.get(ResignationDateRevision, resignation.pending_revision_id)
            if revision is None:
                return jsonify({"message": "The pending date change could not be found."}), 409
            revision.status = "approved"
            revision.decided_at = utc_now_naive()
            resignation.proposed_last_working_date = revision.proposed_last_working_date
            resignation.pending_revision_id = None
        _set_stage(resignation, "exit")
        finance_item = ResignationChecklistItem.query.filter_by(
            resignation_id=resignation.id, item_key="finance_clearance"
        ).first()
        if finance_item:
            finance_item.status = "completed"
            finance_item.completed_by = actor.id
            finance_item.completed_at = utc_now_naive()
        _event(resignation, actor.id, "approved", comment, stage=stage, details={
            "pending_salary": amounts["finance_pending_salary"],
            "advances": amounts["finance_advances"],
            "reimbursements": amounts["finance_reimbursements"],
            "other_dues": amounts["finance_other_dues"],
            "final_settlement_amount": amounts["final_settlement_amount"],
            "buyback_payment_verified": (
                True if resignation.exit_choice == "full_notice_buyback" else None
            ),
        })
    else:
        return jsonify({"message": "This resignation is not awaiting an approval decision."}), 409

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Resignation decision could not be saved.")
        return jsonify({"message": "Could not save this decision. Please try again."}), 500
    _notify(resignation, [resignation.employee_id], "Resignation update",
            f"Your resignation request is now {resignation.status.replace('_', ' ')}.")
    if decision == "approve":
        _notify_stage(resignation)
    return jsonify(_serialize(resignation, include_history=True))


@bp.patch("/<int:resignation_id>/finance")
@jwt_required()
def save_finance_details(resignation_id):
    resignation = _locked_resignation(resignation_id)
    actor = _actor()
    if (
        resignation.current_stage != "finance"
        or resignation.status != "finance_pending"
        or not _can_approve_stage(resignation, actor, "finance")
    ):
        return jsonify({"message": "Only the assigned Finance approver may update this pending clearance."}), 403
    payload = request.get_json(silent=True) or {}
    if payload.get("final_settlement_status") != "pending":
        return jsonify({"message": "Save interim Finance details with a pending clearance status."}), 400
    try:
        amounts = {
            "finance_pending_salary": _parse_amount(payload, "pending_salary"),
            "finance_advances": _parse_amount(payload, "advances"),
            "finance_reimbursements": _parse_amount(payload, "reimbursements"),
            "finance_other_dues": _parse_amount(payload, "other_dues"),
            "final_settlement_amount": _parse_amount(payload, "final_settlement_amount"),
        }
        labels = {
            "finance_pending_salary": "Pending salary",
            "finance_advances": "Advances",
            "finance_reimbursements": "Reimbursements",
            "finance_other_dues": "Other dues",
            "final_settlement_amount": "Final settlement amount",
        }
        for field, title in labels.items():
            if amounts[field] is None:
                raise ValueError(f"{title} is required.")
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    for field, value in amounts.items():
        setattr(resignation, field, value)
    if resignation.exit_choice == "full_notice_buyback":
        payment_reference = payload.get("buyback_payment_reference")
        if payment_reference is not None:
            if not isinstance(payment_reference, str) or len(payment_reference.strip()) > 255:
                return jsonify({"message": "Buyback payment reference must be 255 characters or fewer."}), 400
            resignation.buyback_payment_reference = payment_reference.strip() or None
    resignation.final_settlement_status = "pending"
    _event(resignation, actor.id, "finance_details_saved", stage="finance", details={
        "pending_salary": amounts["finance_pending_salary"],
        "advances": amounts["finance_advances"],
        "reimbursements": amounts["finance_reimbursements"],
        "other_dues": amounts["finance_other_dues"],
        "final_settlement_amount": amounts["final_settlement_amount"],
    })
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Finance clearance details could not be saved.")
        return jsonify({"message": "Could not save Finance details. Please try again."}), 500
    _notify(resignation, [resignation.employee_id], "Finance update",
            "Finance saved interim details for your resignation settlement.")
    return jsonify(_serialize(resignation, include_history=True))


@bp.post("/<int:resignation_id>/date-change")
@jwt_required()
def request_date_change(resignation_id):
    resignation = _locked_resignation(resignation_id)
    actor = _actor()
    if actor.id != resignation.employee_id:
        return jsonify({"message": "Only the employee may request a last working date change."}), 403
    if not resignation.active_key or resignation.status in (*TERMINAL_RESIGNATION_STATUSES, "withdrawal_pending"):
        return jsonify({"message": "This resignation is not eligible for a date change."}), 409
    if resignation.exit_choice == "full_notice_buyback":
        return jsonify({"message": "The last working day for a full buyback is set when Finance verifies payment."}), 409
    if resignation.pending_revision_id:
        return jsonify({"message": "A last working date change is already awaiting review."}), 409
    if not db.session.get(User, actor.manager_id):
        return jsonify({"message": "A direct manager must be assigned before requesting a date change."}), 409
    payload = request.get_json(silent=True) or {}
    try:
        proposed_date = _parse_date(payload.get("proposed_last_working_date"), "Proposed last working date")
        if proposed_date < company_today():
            raise ValueError("Proposed last working date cannot be in the past.")
        expected_date = (resignation.exit_policy_snapshot or {}).get("expected_last_working_date")
        if expected_date and proposed_date < _parse_date(expected_date, "Policy last working date"):
            raise ValueError("The proposed date cannot be earlier than the configured full notice period.")
        reason = (payload.get("reason") or "").strip()
        if not reason:
            raise ValueError("A reason is required for a last working date change.")
        if len(reason) > 2000:
            raise ValueError("Date change reason must be 2,000 characters or fewer.")
        current_date = resignation.proposed_last_working_date
        if current_date == proposed_date:
            raise ValueError("The proposed date must differ from the current date.")
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    revision = ResignationDateRevision(
        resignation_id=resignation.id,
        requested_by=actor.id,
        proposed_last_working_date=proposed_date,
        reason=reason,
        status="manager_pending",
        current_stage="manager",
        prior_status=resignation.status,
        prior_stage=resignation.current_stage,
        prior_approved_last_working_date=resignation.approved_last_working_date,
        prior_notice_period_days=resignation.notice_period_days,
        prior_dates_approved_at=resignation.dates_approved_at,
    )
    db.session.add(revision)
    db.session.flush()
    resignation.pending_revision_id = revision.id
    resignation.approved_last_working_date = None
    resignation.notice_period_days = None
    resignation.dates_approved_at = None
    _set_stage(resignation, "manager")
    actor = db.session.get(User, resignation.employee_id)
    actor.employment_status = "resignation_pending"
    actor.notice_period_days = None
    actor.last_working_day = None
    actor.resignation_decision = "pending"
    _event(resignation, actor.id, "date_change_requested", reason, stage="employee",
           details={"revision_id": revision.id, "proposed_last_working_date": proposed_date.isoformat()})
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Resignation date change could not be saved.")
        return jsonify({"message": "Could not submit the date change. Please try again."}), 500
    _notify_stage(resignation)
    return jsonify(_serialize(resignation, include_history=True)), 201


@bp.post("/<int:resignation_id>/withdrawal")
@jwt_required()
def request_withdrawal(resignation_id):
    resignation = _locked_resignation(resignation_id)
    actor = _actor()
    if actor.id != resignation.employee_id:
        return jsonify({"message": "Only the employee may request withdrawal."}), 403
    if not resignation.active_key or resignation.status in (*TERMINAL_RESIGNATION_STATUSES, "withdrawal_pending"):
        return jsonify({"message": "This resignation cannot be withdrawn."}), 409
    if (
        resignation.exit_choice == "full_notice_buyback"
        and resignation.buyback_payment_status == "verified"
    ):
        return jsonify({"message": "A resignation cannot be withdrawn after Finance has verified the full buyback payment."}), 409
    if resignation.pending_revision_id:
        return jsonify({"message": "Resolve the pending date change before requesting withdrawal."}), 409
    stage = resignation.current_stage
    if stage == "manager":
        approver_id, approver_role = resignation.current_approver_id, None
    elif stage == "l2":
        approvers = _l2_approvers(resignation.company_name, actor.id)
        if not approvers:
            return jsonify({"message": "No L2 approver is configured for this resignation."}), 409
        approver_id, approver_role = approvers[0], None
    elif stage == "finance":
        approver_id, approver_role = None, "finance"
    else:
        approver_id, approver_role = None, "hr"
    if approver_id == actor.id:
        return jsonify({"message": "You cannot approve your own withdrawal request."}), 409
    resignation.withdrawal_previous_status = resignation.status
    resignation.withdrawal_previous_stage = stage
    resignation.withdrawal_approver_id = approver_id
    resignation.withdrawal_approver_role = approver_role
    resignation.status = "withdrawal_pending"
    resignation.current_stage = "withdrawal"
    _event(resignation, actor.id, "withdrawal_requested", stage="employee",
           details={"previous_stage": stage})
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Resignation withdrawal request could not be saved.")
        return jsonify({"message": "Could not submit the withdrawal request. Please try again."}), 500
    recipients = [approver_id] if approver_id else _stage_recipients(
        resignation, "finance" if approver_role == "finance" else "hr"
    )
    _notify(
        resignation,
        recipients,
        "Withdrawal approval required",
        "An employee requested withdrawal of a resignation.",
    )
    return jsonify(_serialize(resignation, include_history=True)), 201


@bp.post("/<int:resignation_id>/withdrawal-decision")
@jwt_required()
def decide_withdrawal(resignation_id):
    resignation = _locked_resignation(resignation_id)
    actor = _actor()
    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision")
    comment = (payload.get("comment") or "").strip() or None
    if decision not in {"approve", "reject"}:
        return jsonify({"message": "Decision must be approve or reject."}), 400
    if decision == "reject" and not comment:
        return jsonify({"message": "A comment is required when rejecting a withdrawal."}), 400
    if resignation.status != "withdrawal_pending" or actor.id == resignation.employee_id:
        return jsonify({"message": "You are not the assigned approver for this withdrawal."}), 403
    assigned = resignation.withdrawal_approver_id == actor.id
    if resignation.withdrawal_approver_role == "hr":
        assigned = actor.role in HR_ROLES
    elif resignation.withdrawal_approver_role == "finance":
        assigned = actor.role in FINANCE_ROLES
    if not assigned:
        return jsonify({"message": "You are not the assigned approver for this withdrawal."}), 403
    if decision == "approve":
        resignation.status = "withdrawn"
        resignation.current_stage = "completed"
        resignation.active_key = None
        employee = db.session.get(User, resignation.employee_id)
        employee.employment_status = "active"
        employee.resignation_withdrawn_at = utc_now_naive()
        employee.resignation_decision = "withdrawn"
        employee.notice_period_days = None
        employee.last_working_day = None
        resignation.current_approver_id = None
        _event(resignation, actor.id, "withdrawal_approved", comment, stage="withdrawal")
    else:
        resignation.status = resignation.withdrawal_previous_status
        resignation.current_stage = resignation.withdrawal_previous_stage
        resignation.current_approver_id = (
            db.session.get(User, resignation.employee_id).manager_id
            if resignation.current_stage == "manager" else None
        )
        employee = db.session.get(User, resignation.employee_id)
        has_approved_dates = bool(resignation.approved_last_working_date and resignation.dates_approved_at)
        employee.employment_status = "notice_period" if has_approved_dates else "resignation_pending"
        employee.last_working_day = resignation.approved_last_working_date if has_approved_dates else None
        employee.notice_period_days = resignation.notice_period_days if has_approved_dates else None
        employee.resignation_decision = "accepted" if has_approved_dates else None
        _event(resignation, actor.id, "withdrawal_rejected", comment, stage="withdrawal")
    resignation.withdrawal_approver_id = None
    resignation.withdrawal_approver_role = None
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Resignation withdrawal decision could not be saved.")
        return jsonify({"message": "Could not save the withdrawal decision. Please try again."}), 500
    _notify(resignation, [resignation.employee_id], "Withdrawal decision",
            f"Your withdrawal request was {decision}d.")
    if decision == "reject":
        _notify_stage(resignation)
    return jsonify(_serialize(resignation, include_history=True))


@bp.post("/<int:resignation_id>/revoke")
@jwt_required()
def revoke_resignation(resignation_id):
    resignation = _locked_resignation(resignation_id)
    actor = _actor()
    if actor.role not in HR_ROLES:
        return jsonify({"message": "Only HR or Super Admin may revoke a resignation."}), 403
    if actor.id == resignation.employee_id:
        return jsonify({"message": "You cannot revoke your own resignation request."}), 403
    if (
        not resignation.active_key
        or resignation.status in TERMINAL_RESIGNATION_STATUSES
        or resignation.status == "withdrawal_pending"
    ):
        return jsonify({"message": "This resignation is not eligible for revocation."}), 409
    if resignation.pending_revision_id:
        return jsonify({"message": "Resolve the pending date change before revoking this resignation."}), 409
    if resignation.finance_cleared_at or (
        resignation.exit_choice == "full_notice_buyback"
        and resignation.buyback_payment_status == "verified"
    ):
        return jsonify({"message": "A resignation cannot be revoked after Finance clearance or verified full buyback payment."}), 409

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"message": "A revocation reason is required."}), 400
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500:
        return jsonify({"message": "A revocation reason of 1 to 500 characters is required."}), 400

    employee = db.session.get(User, resignation.employee_id)
    prior_stage = resignation.current_stage
    resignation.status = "revoked"
    resignation.current_stage = "completed"
    resignation.current_approver_id = None
    resignation.active_key = None
    resignation.withdrawal_approver_id = None
    resignation.withdrawal_approver_role = None
    employee.employment_status = "active"
    employee.resignation_decision = "revoked"
    employee.resignation_reviewed_at = utc_now_naive()
    employee.resignation_reviewed_by = actor.id
    employee.notice_period_days = None
    employee.last_working_day = None
    employee.left_company_at = None
    _event(resignation, actor.id, "revoked", reason.strip(), stage=prior_stage)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Resignation revocation could not be saved.")
        return jsonify({"message": "Could not revoke this resignation. Please try again."}), 500
    _notify(resignation, [employee.id], "Resignation revoked", reason.strip())
    return jsonify(_serialize(resignation, include_history=True))


@bp.patch("/<int:resignation_id>/checklist/<item_key>")
@jwt_required()
def update_checklist(resignation_id, item_key):
    resignation = _locked_resignation(resignation_id)
    actor = _actor()
    if not _may_view(resignation, actor) or resignation.status not in {"exit_pending", "completed"}:
        return jsonify({"message": "Exit checklist access is not available for this request."}), 403
    item = ResignationChecklistItem.query.filter_by(
        resignation_id=resignation.id, item_key=item_key
    ).first_or_404()
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if status not in {"pending", "completed"}:
        return jsonify({"message": "Checklist status must be pending or completed."}), 400
    employee_items = {"knowledge_transfer", "project_handover"}
    finance_items = {"finance_clearance"}
    hr_items = {"assets_returned", "system_access_revocation", "hr_clearance", "relieving_letter"}
    allowed = (
        (actor.id == resignation.employee_id and item_key in employee_items)
        or (actor.role in FINANCE_ROLES and item_key in finance_items)
        or (actor.role in HR_ROLES and item_key in hr_items)
    )
    if not allowed:
        return jsonify({"message": "You are not allowed to update this exit checklist item."}), 403
    if status == "completed" and item_key == "finance_clearance" and resignation.final_settlement_status != "cleared":
        return jsonify({"message": "Finance clearance must be recorded before completing this item."}), 409
    item.status = status
    item.completed_by = actor.id if status == "completed" else None
    item.completed_at = utc_now_naive() if status == "completed" else None
    _event(resignation, actor.id, "checklist_updated", stage="exit",
           details={"item": item_key, "status": status})
    all_complete = all(
        checklist_item.status == "completed"
        for checklist_item in ResignationChecklistItem.query.filter_by(resignation_id=resignation.id).all()
    )
    if all_complete and resignation.finance_cleared_at:
        resignation.status = "completed"
        resignation.current_stage = "completed"
        resignation.active_key = None
        resignation.current_approver_id = None
        employee = db.session.get(User, resignation.employee_id)
        employee.employment_status = "left"
        employee.left_company_at = resignation.approved_last_working_date
        employee.last_working_day = resignation.approved_last_working_date
        employee.notice_period_days = resignation.notice_period_days
        employee.resignation_decision = "approved"
        _event(resignation, actor.id, "completed", stage="exit")
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Resignation checklist update could not be saved.")
        return jsonify({"message": "Could not update the exit checklist. Please try again."}), 500
    if resignation.status == "completed":
        _notify(resignation, [resignation.employee_id], "Resignation completed",
                "Your exit formalities are complete.")
    return jsonify(_serialize(resignation, include_history=True))


@bp.get("/<int:resignation_id>/document")
@jwt_required()
def download_resignation_document(resignation_id):
    resignation = ResignationRequest.query.get_or_404(resignation_id)
    if not _may_view(resignation, _actor()):
        return jsonify({"message": "You do not have permission to access this document."}), 403
    storage_key = resignation.document_storage_key
    if not storage_key or ".." in storage_key.split("/") or os.path.isabs(storage_key):
        return jsonify({"message": "The resignation document is unavailable."}), 404
    return send_from_directory(
        current_app.config["RESIGNATION_DOCUMENT_FOLDER"],
        storage_key,
        mimetype=resignation.document_mime_type,
        as_attachment=False,
        download_name=resignation.document_filename or "resignation-document",
    )


@bp.get("/routing")
@jwt_required()
def list_routing():
    if _role() not in ROUTING_ADMIN_ROLES:
        return jsonify({"message": "Only HR Operations or Super Admin may manage approver routing."}), 403
    rows = ResignationRouting.query.join(
        User, User.id == ResignationRouting.approver_user_id
    ).order_by(ResignationRouting.company_name, User.full_name).all()
    return jsonify([{
        "id": row.id,
        "company_name": row.company_name,
        "approver": _user_summary(row.approver_user_id),
    } for row in rows])


@bp.get("/routing/users")
@jwt_required()
def routing_users():
    if _role() not in ROUTING_ADMIN_ROLES:
        return jsonify({"message": "Only HR Operations or Super Admin may manage approver routing."}), 403
    users = User.query.filter(
        User.is_active.is_(True),
        User.role != CONTRACT_EMPLOYEE,
    ).order_by(User.company_name, User.full_name).all()
    return jsonify([{
        "id": user.id,
        "full_name": user.full_name,
        "employee_code": user.employee_code,
        "company_name": user.company_name,
        "role": user.role,
    } for user in users])


@bp.post("/routing")
@jwt_required()
def add_routing():
    actor = _actor()
    if actor.role not in ROUTING_ADMIN_ROLES:
        return jsonify({"message": "Only HR Operations or Super Admin may manage approver routing."}), 403
    payload = request.get_json(silent=True) or {}
    company_name = (payload.get("company_name") or "").strip()
    approver_id = payload.get("approver_user_id")
    if not company_name or len(company_name) > 150:
        return jsonify({"message": "A valid company name is required."}), 400
    approver = db.session.get(User, approver_id) if isinstance(approver_id, int) else None
    if approver is None or not approver.is_active or approver.role == CONTRACT_EMPLOYEE:
        return jsonify({"message": "Select an active, eligible L2 / Director approver."}), 400
    routing = ResignationRouting(
        company_name=company_name,
        approver_user_id=approver.id,
        created_by=actor.id,
    )
    db.session.add(routing)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "This approver is already configured for the selected company."}), 409
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Resignation approver mapping could not be saved.")
        return jsonify({"message": "Could not save this approver mapping. Please try again."}), 500
    return jsonify({
        "id": routing.id,
        "company_name": routing.company_name,
        "approver": _user_summary(routing.approver_user_id),
    }), 201


@bp.delete("/routing/<int:routing_id>")
@jwt_required()
def delete_routing(routing_id):
    if _role() not in ROUTING_ADMIN_ROLES:
        return jsonify({"message": "Only HR Operations or Super Admin may manage approver routing."}), 403
    routing = ResignationRouting.query.get_or_404(routing_id)
    db.session.delete(routing)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Resignation approver mapping could not be removed.")
        return jsonify({"message": "Could not remove this approver mapping. Please try again."}), 500
    return jsonify({"message": "Approver mapping removed."})
