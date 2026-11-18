from datetime import datetime, timedelta
from app.extensions import db


class CompanySettings(db.Model):
    """Singleton row — AnametaIOT's own details, used as the 'Buyer' block
    on every generated vendor invoice. Editable by Admin/Finance."""
    __tablename__ = "company_settings"

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), default="AnametaIOT")
    address = db.Column(db.Text, default="")
    gstin = db.Column(db.String(20), nullable=True)
    pan = db.Column(db.String(20), nullable=True)
    state = db.Column(db.String(50), default="Karnataka")
    # Attendance policy: when on, every clock-in/out must include a selfie.
    # Off by default.
    selfie_required = db.Column(db.Boolean, default=False, nullable=False, server_default="0")
    attendance_buffer_minutes = db.Column(db.Integer, default=10, nullable=False, server_default="10")
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "company_name": self.company_name,
            "address": self.address,
            "gstin": self.gstin,
            "pan": self.pan,
            "state": self.state,
        }


class VendorCompany(db.Model):
    __tablename__ = "vendor_companies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class Vendor(db.Model):
    """A staffing/recruitment vendor who supplies manpower to AnametaIOT
    under one or more signed agreements."""
    __tablename__ = "vendors"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("vendor_companies.id"), nullable=True)
    name = db.Column(db.String(150), nullable=False)
    normalized_name = db.Column(db.String(150), index=True)  # for dedup matching
    address = db.Column(db.Text, nullable=True)
    state = db.Column(db.String(50), nullable=True)
    gstin = db.Column(db.String(20), nullable=True)
    pan = db.Column(db.String(20), nullable=True)

    contact_person = db.Column(db.String(120), nullable=True)
    contact_email = db.Column(db.String(150), nullable=True)
    contact_phone = db.Column(db.String(20), nullable=True)

    bank_name = db.Column(db.String(120), nullable=True)
    bank_account_no = db.Column(db.String(40), nullable=True)
    bank_ifsc = db.Column(db.String(20), nullable=True)
    bank_branch = db.Column(db.String(120), nullable=True)

    status = db.Column(db.String(20), default="active")  # active, inactive
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    agreements = db.relationship(
        "VendorAgreement", backref="vendor", cascade="all, delete-orphan",
        order_by="VendorAgreement.effective_from.desc()",
    )
    company = db.relationship("VendorCompany")

    def to_dict(self, include_agreements=False):
        from app.services.vendor_agreements import agreement_status

        agreements = self.agreements
        current_agreements = [
            agreement for agreement in agreements
            if agreement_status(agreement) in ("active", "expiring_soon")
        ]
        active_agreement = min(
            current_agreements,
            key=lambda agreement: agreement.effective_to or datetime.max.date(),
            default=None,
        )
        visible_agreements = [
            agreement for agreement in agreements
            if agreement_status(agreement) != "terminated"
        ]
        upcoming_agreements = [
            agreement for agreement in visible_agreements
            if agreement_status(agreement) == "upcoming"
        ]
        summary_agreement = (
            active_agreement
            or min(upcoming_agreements, key=lambda a: a.effective_from or datetime.max.date(), default=None)
            or max(visible_agreements, key=lambda a: a.effective_to or datetime.min.date(), default=None)
        )
        from app.services.vendor_agreements import agreement_days_remaining
        data = {
            "id": self.id,
            "company_id": self.company_id,
            "company_name": self.company.name if self.company else None,
            "name": self.name,
            "address": self.address,
            "state": self.state,
            "gstin": self.gstin,
            "pan": self.pan,
            "contact_person": self.contact_person,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "status": self.status,
            "agreement_count": len(agreements),
            "active_agreement": active_agreement.to_dict() if active_agreement else None,
            "agreement_status": agreement_status(summary_agreement) if summary_agreement else None,
            "agreement_expiry": (
                summary_agreement.effective_to.isoformat()
                if summary_agreement and summary_agreement.effective_to else None
            ),
            "agreement_days_to_expiry": agreement_days_remaining(summary_agreement) if summary_agreement else None,
            "agreement_title": summary_agreement.title if summary_agreement else None,
            "expiring_agreement_count": sum(
                agreement_status(agreement) == "expiring_soon" for agreement in agreements
            ),
            "expired_agreement_count": sum(
                agreement_status(agreement) == "expired" for agreement in agreements
            ),
            "expiring_agreements": [
                {
                    "id": agreement.id,
                    "title": agreement.title,
                    "expiry_date": agreement.effective_to.isoformat(),
                    "days_remaining": agreement_days_remaining(agreement),
                }
                for agreement in agreements
                if agreement_status(agreement) == "expiring_soon"
            ],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_agreements:
            data["agreements"] = [a.to_dict(include_roles=True) for a in agreements]
        return data

    def to_sensitive_dict(self, include_agreements=False):
        data = self.to_dict(include_agreements=include_agreements)
        data.update({
            "bank_name": self.bank_name,
            "bank_account_no": self.bank_account_no,
            "bank_ifsc": self.bank_ifsc,
            "bank_branch": self.bank_branch,
        })
        return data


class VendorAgreement(db.Model):
    """One signed contract with a vendor. A vendor can have several over
    time (renewals) — the most recent by effective_from is the active one."""
    __tablename__ = "vendor_agreements"

    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)

    title = db.Column(db.String(150), nullable=True)
    file_path = db.Column(db.String(255), nullable=False)

    effective_from = db.Column(db.Date, nullable=True)
    effective_to = db.Column(db.Date, nullable=True)
    termination_notice_days = db.Column(db.Integer, default=90)
    confidentiality_days = db.Column(db.Integer, default=60)
    feedback_days = db.Column(db.Integer, default=2)

    status = db.Column(db.String(20), default="active")  # active, expired, terminated
    parsed_with_ai = db.Column(db.Boolean, default=False)
    raw_extracted_text = db.Column(db.Text, nullable=True)

    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    roles = db.relationship(
        "VendorAgreementRole", backref="agreement", cascade="all, delete-orphan"
    )

    def to_dict(self, include_roles=False):
        from app.services.vendor_agreements import agreement_status

        data = {
            "id": self.id,
            "vendor_id": self.vendor_id,
            "title": self.title,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "termination_notice_days": self.termination_notice_days,
            "confidentiality_days": self.confidentiality_days,
            "feedback_days": self.feedback_days,
            "status": agreement_status(self),
            "download_url": f"/vendors/agreements/{self.id}/download",
            "parsed_with_ai": self.parsed_with_ai,
            "uploaded_at": self.uploaded_at.isoformat(),
        }
        if include_roles:
            data["roles"] = [r.to_dict() for r in self.roles]
        return data


class VendorAgreementReminder(db.Model):
    __tablename__ = "vendor_agreement_reminders"
    __table_args__ = (
        db.UniqueConstraint(
            "agreement_id", "reminder_type", "expiry_date",
            name="uq_vendor_agreement_reminder",
        ),
        db.Index("ix_vendor_agreement_reminder_status", "status", "expiry_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    agreement_id = db.Column(
        db.Integer,
        db.ForeignKey("vendor_agreements.id", ondelete="CASCADE"),
        nullable=False,
    )
    reminder_type = db.Column(db.String(40), nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    attempted_at = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    agreement = db.relationship("VendorAgreement")


class VendorAgreementRole(db.Model):
    """One rate-card line from an agreement's fee table — e.g.
    'Telesales Executive: 7.55% of CTC, 30-day replacement, billable after
    60-day tenure'."""
    __tablename__ = "vendor_agreement_roles"

    id = db.Column(db.Integer, primary_key=True)
    agreement_id = db.Column(db.Integer, db.ForeignKey("vendor_agreements.id"), nullable=False)

    role_name = db.Column(db.String(120), nullable=False)
    service_fee_pct = db.Column(db.Float, nullable=False)
    replacement_days = db.Column(db.Integer, default=30)
    tenure_days = db.Column(db.Integer, default=60)  # billable once candidate completes this many days

    def to_dict(self):
        return {
            "id": self.id,
            "agreement_id": self.agreement_id,
            "role_name": self.role_name,
            "service_fee_pct": self.service_fee_pct,
            "replacement_days": self.replacement_days,
            "tenure_days": self.tenure_days,
        }


class VendorHire(db.Model):
    """A person supplied by a vendor and hired into a specific rate-card
    role — the unit that payroll and vendor billing both hang off of."""
    __tablename__ = "vendor_hires"

    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    agreement_id = db.Column(db.Integer, db.ForeignKey("vendor_agreements.id"), nullable=False)
    agreement_role_id = db.Column(db.Integer, db.ForeignKey("vendor_agreement_roles.id"), nullable=False)

    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    candidate_name = db.Column(db.String(150), nullable=False)

    ctc = db.Column(db.Float, nullable=False)
    tenure_start_date = db.Column(db.Date, nullable=False)

    placement_type = db.Column(db.String(20), default="direct")  # direct | contract
    billing_type = db.Column(db.String(20), default="one_time")  # one_time | continuous
    last_billed_month = db.Column(db.String(7), nullable=True)  # "YYYY-MM" — guards continuous billing against double-charging the same month

    status = db.Column(db.String(20), default="active")
    # active, replaced, invoiced (billed at least once), terminated
    replacement_of_hire_id = db.Column(db.Integer, db.ForeignKey("vendor_hires.id"), nullable=True)

    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    # The in-house recruiter who sourced this person (auto-filled from the
    # candidate's owner when placed from the pipeline) — separate from
    # assigned_by, which is whoever in Finance/HR Ops recorded the placement.
    recruiter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    invoice_items = db.relationship("VendorInvoiceItem", backref="hire")
    recruiter = db.relationship("User", foreign_keys=[recruiter_id])

    role = db.relationship("VendorAgreementRole")
    agreement = db.relationship("VendorAgreement")
    vendor = db.relationship("Vendor")

    @property
    def tenure_days_required(self):
        return self.role.tenure_days if self.role else 60

    @property
    def tenure_end_date(self):
        return self.tenure_start_date + timedelta(days=self.tenure_days_required)

    @property
    def is_billable(self):
        """One-time-billing hires only — a continuous-billing placement is
        never eligible for this tenure-gated single fee; it's billed
        recurring instead (see is_due_for_recurring_billing)."""
        from datetime import date
        if self.billing_type != "one_time":
            return False
        already_invoiced = any(i.invoice.status != "rejected" for i in self.invoice_items)
        return (
            self.status == "active"
            and not already_invoiced
            and date.today() >= self.tenure_end_date
        )

    def is_due_for_recurring_billing(self, period):
        """period: 'YYYY-MM'. Continuous-billing hires only — true once
        their tenure has started for that period and they haven't already
        been billed for it."""
        if self.billing_type != "continuous" or self.status != "active":
            return False
        if self.last_billed_month == period:
            return False
        return self.tenure_start_date.strftime("%Y-%m") <= period

    def to_dict(self):
        from datetime import date
        days_elapsed = (date.today() - self.tenure_start_date).days
        return {
            "id": self.id,
            "vendor_id": self.vendor_id,
            "agreement_id": self.agreement_id,
            "agreement_role_id": self.agreement_role_id,
            "role_name": self.role.role_name if self.role else None,
            "service_fee_pct": self.role.service_fee_pct if self.role else None,
            "candidate_id": self.candidate_id,
            "employee_id": self.employee_id,
            "vendor_name": self.vendor.name if self.vendor else None,
            "recruiter_id": self.recruiter_id,
            "recruiter_name": self.recruiter.full_name if self.recruiter else None,
            "candidate_name": self.candidate_name,
            "ctc": self.ctc,
            "placement_type": self.placement_type,
            "billing_type": self.billing_type,
            "last_billed_month": self.last_billed_month,
            "tenure_start_date": self.tenure_start_date.isoformat(),
            "tenure_end_date": self.tenure_end_date.isoformat(),
            "tenure_days_required": self.tenure_days_required,
            "tenure_days_elapsed": max(0, days_elapsed),
            "tenure_progress_pct": round(min(100, max(0, days_elapsed) / self.tenure_days_required * 100), 1),
            "is_billable": self.is_billable,
            "status": self.status,
            "assigned_at": self.assigned_at.isoformat(),
        }


class VendorInvoice(db.Model):
    __tablename__ = "vendor_invoices"

    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    agreement_id = db.Column(db.Integer, db.ForeignKey("vendor_agreements.id"), nullable=True)

    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    invoice_date = db.Column(db.Date, nullable=False)

    subtotal = db.Column(db.Float, default=0)
    cgst_amount = db.Column(db.Float, default=0)
    sgst_amount = db.Column(db.Float, default=0)
    igst_amount = db.Column(db.Float, default=0)
    total_amount = db.Column(db.Float, default=0)

    status = db.Column(db.String(20), default="draft")
    # draft, pending_approval, approved, rejected, paid
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approval_comment = db.Column(db.String(255), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)

    pdf_path = db.Column(db.String(255), nullable=True)
    generated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("VendorInvoiceItem", backref="invoice", cascade="all, delete-orphan")
    vendor = db.relationship("Vendor")

    def to_dict(self, include_items=False):
        data = {
            "id": self.id,
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor.name if self.vendor else None,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date.isoformat(),
            "subtotal": self.subtotal,
            "cgst_amount": self.cgst_amount,
            "sgst_amount": self.sgst_amount,
            "igst_amount": self.igst_amount,
            "total_amount": self.total_amount,
            "status": self.status,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "pdf_path": self.pdf_path,
            "generated_at": self.generated_at.isoformat(),
        }
        if include_items:
            data["items"] = [i.to_dict() for i in self.items]
        return data


class VendorInvoiceItem(db.Model):
    __tablename__ = "vendor_invoice_items"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("vendor_invoices.id"), nullable=False)
    hire_id = db.Column(db.Integer, db.ForeignKey("vendor_hires.id"), nullable=False)

    candidate_name = db.Column(db.String(150), nullable=False)
    role_name = db.Column(db.String(120), nullable=True)
    ctc = db.Column(db.Float, nullable=False)
    fee_pct = db.Column(db.Float, nullable=False)
    fee_amount = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "hire_id": self.hire_id,
            "candidate_name": self.candidate_name,
            "role_name": self.role_name,
            "ctc": self.ctc,
            "fee_pct": self.fee_pct,
            "fee_amount": self.fee_amount,
        }
