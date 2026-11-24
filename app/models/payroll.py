from datetime import datetime
from app.extensions import db
from sqlalchemy import JSON


class SalaryStructure(db.Model):
    __tablename__ = "salary_structures"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    salary_template_id = db.Column(db.Integer, db.ForeignKey("salary_templates.id"), nullable=True)

    annual_ctc = db.Column(db.Numeric(12, 2), nullable=True)
    employee_overrides = db.Column(JSON, nullable=False, default=dict)
    basic = db.Column(db.Float, default=0)
    hra = db.Column(db.Float, default=0)
    special_allowance = db.Column(db.Float, default=0)
    other_allowance = db.Column(db.Float, default=0)

    pf_employee = db.Column(db.Float, default=0)   # employee PF contribution
    esi_employee = db.Column(db.Float, default=0)
    insurance = db.Column(db.Float, default=0)      # employee's share of group health/life insurance premium
    professional_tax = db.Column(db.Float, default=0)
    tds = db.Column(db.Float, default=0)
    custom_earnings = db.Column(JSON, nullable=False, default=list)
    custom_deductions = db.Column(JSON, nullable=False, default=list)

    effective_from = db.Column(db.Date, default=datetime.utcnow)
    user = db.relationship("User", backref=db.backref("salary_structure", uselist=False))
    salary_template = db.relationship("SalaryTemplate", back_populates="assigned_structures")

    @property
    def gross(self):
        return round(self.basic + self.hra + self.special_allowance + self.other_allowance, 2)

    @property
    def total_deductions(self):
        return round(self.pf_employee + self.esi_employee + self.insurance + self.professional_tax + self.tds, 2)

    @property
    def net(self):
        return round(self.gross - self.total_deductions, 2)

    @property
    def is_ctc_only(self):
        amounts = (
            self.basic, self.hra, self.special_allowance, self.other_allowance,
            self.pf_employee, self.esi_employee, self.insurance,
            self.professional_tax, self.tds,
        )
        return self.annual_ctc is not None and all(value in (None, 0) for value in amounts)

    def to_dict(self):
        return {
            "basic": self.basic,
            "annual_ctc": float(self.annual_ctc) if self.annual_ctc is not None else None,
            "salary_template_id": self.salary_template_id,
            "employee_overrides": self.employee_overrides or {},
            "hra": self.hra,
            "special_allowance": self.special_allowance,
            "other_allowance": self.other_allowance,
            "pf_employee": self.pf_employee,
            "esi_employee": self.esi_employee,
            "insurance": self.insurance,
            "professional_tax": self.professional_tax,
            "tds": self.tds,
            "custom_earnings": self.custom_earnings or [],
            "custom_deductions": self.custom_deductions or [],
            "gross": self.gross,
            "total_deductions": self.total_deductions,
            "net": self.net,
        }


class Payslip(db.Model):
    __tablename__ = "payslips"
    __table_args__ = (
        db.UniqueConstraint("user_id", "month", "year", name="uq_payslip_user_month_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)

    days_present = db.Column(db.Float, default=0)
    days_on_leave = db.Column(db.Float, default=0)
    lop_days = db.Column(db.Float, default=0)  # loss of pay

    gross_earnings = db.Column(db.Float, default=0)
    total_deductions = db.Column(db.Float, default=0)
    net_pay = db.Column(db.Float, default=0)

    status = db.Column(db.String(20), default="draft")  # draft, processed, paid
    pdf_path = db.Column(db.String(255), nullable=True)
    generated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    company_name = db.Column(db.String(150), nullable=True)
    employee_info = db.Column(JSON, nullable=True)
    earnings = db.Column(JSON, nullable=True)
    deductions = db.Column(JSON, nullable=True)
    total_working_days = db.Column(db.Float, nullable=True)
    total_paid_days = db.Column(db.Float, nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)
    published_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    pdf_is_uploaded = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    pdf_filename = db.Column(db.String(255), nullable=True)
    template_snapshot = db.Column(JSON, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id], backref="payslips")
    revisions = db.relationship(
        "PayslipRevision",
        back_populates="payslip",
        cascade="all, delete-orphan",
        order_by="PayslipRevision.revision",
    )

    def to_dict(self, revision_count=None):
        from app.utils.number_to_words import number_to_words_inr

        if revision_count is None:
            revision_count = (
                db.session.query(db.func.count(PayslipRevision.id))
                .filter_by(payslip_id=self.id)
                .scalar()
                if self.id else 0
            )
        return {
            "id": self.id,
            "user_id": self.user_id,
            "employee_name": self.user.full_name if self.user else None,
            "month": self.month,
            "year": self.year,
            "days_present": self.days_present,
            "days_on_leave": self.days_on_leave,
            "lop_days": self.lop_days,
            "gross_earnings": self.gross_earnings,
            "total_deductions": self.total_deductions,
            "net_pay": self.net_pay,
            "amount_in_words": number_to_words_inr(self.net_pay or 0),
            "status": self.status,
            "pdf_path": self.pdf_path,
            "company_name": self.company_name or (self.user.company_name if self.user else None),
            "employee_info": self.employee_info or {},
            "earnings": self.earnings or [],
            "deductions": self.deductions or [],
            "total_working_days": self.total_working_days or 0,
            "total_paid_days": self.total_paid_days or 0,
            "created_by": self.generated_by,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "published_by": self.published_by,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "pdf_is_uploaded": bool(self.pdf_is_uploaded),
            "pdf_filename": self.pdf_filename,
            "template_snapshot": self.template_snapshot or {},
            "revision_count": revision_count,
            "pdf_url": f"/api/payroll/payslips/{self.id}/pdf" if self.pdf_path else None,
        }


class CompanyPayslipTemplate(db.Model):
    __tablename__ = "company_payslip_templates"

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=False, unique=True)
    layout_key = db.Column(db.String(40), nullable=False)
    address = db.Column(db.Text, nullable=False)
    primary_color = db.Column(db.String(7), nullable=False)
    accent_color = db.Column(db.String(7), nullable=False)
    logo_path = db.Column(db.String(255), nullable=False)
    earnings_components = db.Column(JSON, nullable=False)
    deductions_components = db.Column(JSON, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "company_name": self.company_name,
            "layout_key": self.layout_key,
            "address": self.address,
            "primary_color": self.primary_color,
            "accent_color": self.accent_color,
            "logo_path": self.logo_path,
            "earnings_components": self.earnings_components or [],
            "deductions_components": self.deductions_components or [],
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PayslipRevision(db.Model):
    __tablename__ = "payslip_revisions"

    id = db.Column(db.Integer, primary_key=True)
    payslip_id = db.Column(db.Integer, db.ForeignKey("payslips.id", ondelete="CASCADE"), nullable=False)
    revision = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(30), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    snapshot = db.Column(JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    payslip = db.relationship("Payslip", back_populates="revisions")


class PayrollAuditLog(db.Model):
    __tablename__ = "payroll_audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    payslip_id = db.Column(db.Integer, db.ForeignKey("payslips.id"), nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(40), nullable=False)
    previous_values = db.Column(JSON, nullable=True)
    new_values = db.Column(JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
