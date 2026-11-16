from datetime import datetime
from sqlalchemy import JSON

from app.extensions import db


class ResignationPolicy(db.Model):
    __tablename__ = "resignation_policies"

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=False, unique=True)
    notice_period_days = db.Column(db.Integer, nullable=False)
    buyback_daily_divisor = db.Column(db.Integer, nullable=True)
    buyback_multiplier = db.Column(db.Numeric(8, 4), nullable=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResignationRequest(db.Model):
    __tablename__ = "resignation_requests"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    company_name = db.Column(db.String(150), nullable=False, index=True)
    department_name = db.Column(db.String(100))
    resignation_date = db.Column(db.Date, nullable=False)
    exit_choice = db.Column(db.String(40))
    exit_policy_snapshot = db.Column(JSON, nullable=True)
    buyback_estimated_amount = db.Column(db.Numeric(12, 2))
    buyback_unserved_days = db.Column(db.Integer)
    buyback_calculation_verified_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    buyback_calculation_verified_at = db.Column(db.DateTime)
    buyback_payment_status = db.Column(db.String(30))
    buyback_payment_reference = db.Column(db.String(255))
    buyback_payment_verified_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    buyback_payment_verified_at = db.Column(db.DateTime)
    original_last_working_date = db.Column(db.Date, nullable=False)
    proposed_last_working_date = db.Column(db.Date, nullable=False)
    approved_last_working_date = db.Column(db.Date)
    reason = db.Column(db.Text, nullable=False)
    comments = db.Column(db.Text)
    status = db.Column(db.String(30), nullable=False, default="manager_pending", index=True)
    current_stage = db.Column(db.String(30), nullable=False, default="manager")
    current_approver_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    active_key = db.Column(db.String(20), unique=True)
    notice_period_days = db.Column(db.Integer)
    dates_approved_at = db.Column(db.DateTime)
    document_storage_key = db.Column(db.String(255))
    document_filename = db.Column(db.String(255))
    document_mime_type = db.Column(db.String(100))
    document_size = db.Column(db.Integer)
    pending_revision_id = db.Column(db.Integer)
    withdrawal_approver_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    withdrawal_approver_role = db.Column(db.String(30))
    withdrawal_previous_status = db.Column(db.String(30))
    withdrawal_previous_stage = db.Column(db.String(30))
    finance_pending_salary = db.Column(db.Numeric(12, 2))
    finance_advances = db.Column(db.Numeric(12, 2))
    finance_reimbursements = db.Column(db.Numeric(12, 2))
    finance_other_dues = db.Column(db.Numeric(12, 2))
    final_settlement_amount = db.Column(db.Numeric(12, 2))
    final_settlement_status = db.Column(db.String(30))
    finance_cleared_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResignationDateRevision(db.Model):
    __tablename__ = "resignation_date_revisions"

    id = db.Column(db.Integer, primary_key=True)
    resignation_id = db.Column(db.Integer, db.ForeignKey("resignation_requests.id"), nullable=False, index=True)
    requested_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    proposed_last_working_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="manager_pending")
    current_stage = db.Column(db.String(30), nullable=False, default="manager")
    prior_status = db.Column(db.String(30), nullable=False)
    prior_stage = db.Column(db.String(30), nullable=False)
    prior_approved_last_working_date = db.Column(db.Date)
    prior_notice_period_days = db.Column(db.Integer)
    prior_dates_approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    decided_at = db.Column(db.DateTime)


class ResignationRouting(db.Model):
    __tablename__ = "resignation_routing"

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=False, index=True)
    approver_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("company_name", "approver_user_id", name="uq_resignation_routing_company_approver"),
    )


class ResignationEvent(db.Model):
    __tablename__ = "resignation_events"

    id = db.Column(db.Integer, primary_key=True)
    resignation_id = db.Column(db.Integer, db.ForeignKey("resignation_requests.id"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    event_type = db.Column(db.String(40), nullable=False)
    stage = db.Column(db.String(30))
    status = db.Column(db.String(30))
    comments = db.Column(db.Text)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class ResignationChecklistItem(db.Model):
    __tablename__ = "resignation_checklist_items"

    id = db.Column(db.Integer, primary_key=True)
    resignation_id = db.Column(db.Integer, db.ForeignKey("resignation_requests.id"), nullable=False, index=True)
    item_key = db.Column(db.String(40), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    completed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    completed_at = db.Column(db.DateTime)
    __table_args__ = (
        db.UniqueConstraint("resignation_id", "item_key", name="uq_resignation_checklist_item"),
    )
