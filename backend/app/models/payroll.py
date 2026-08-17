from datetime import datetime
from app.extensions import db


class SalaryStructure(db.Model):
    __tablename__ = "salary_structures"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    basic = db.Column(db.Float, default=0)
    hra = db.Column(db.Float, default=0)
    special_allowance = db.Column(db.Float, default=0)
    other_allowance = db.Column(db.Float, default=0)

    pf_employee = db.Column(db.Float, default=0)   # employee PF contribution
    esi_employee = db.Column(db.Float, default=0)
    professional_tax = db.Column(db.Float, default=0)
    tds = db.Column(db.Float, default=0)

    effective_from = db.Column(db.Date, default=datetime.utcnow)
    user = db.relationship("User", backref=db.backref("salary_structure", uselist=False))

    @property
    def gross(self):
        return round(self.basic + self.hra + self.special_allowance + self.other_allowance, 2)

    @property
    def total_deductions(self):
        return round(self.pf_employee + self.esi_employee + self.professional_tax + self.tds, 2)

    @property
    def net(self):
        return round(self.gross - self.total_deductions, 2)

    def to_dict(self):
        return {
            "basic": self.basic,
            "hra": self.hra,
            "special_allowance": self.special_allowance,
            "other_allowance": self.other_allowance,
            "pf_employee": self.pf_employee,
            "esi_employee": self.esi_employee,
            "professional_tax": self.professional_tax,
            "tds": self.tds,
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

    user = db.relationship("User", foreign_keys=[user_id], backref="payslips")

    def to_dict(self):
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
            "status": self.status,
            "pdf_path": self.pdf_path,
        }
