from datetime import datetime
from app.extensions import db
from sqlalchemy import JSON


class SalaryTemplate(db.Model):
    """A reusable salary structure template — Finance defines the % split
    once (e.g. 'Standard Employee', 'Senior Manager') and applies it to any
    employee's CTC instead of typing flat numbers every time."""
    __tablename__ = "salary_templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    company_name = db.Column(db.String(150), nullable=True)

    # Earnings — percentages of CTC, should sum to 100 (UI warns if not)
    basic_pct = db.Column(db.Float, default=50)
    hra_pct = db.Column(db.Float, default=20)
    special_allowance_pct = db.Column(db.Float, default=20)
    other_allowance_pct = db.Column(db.Float, default=10)
    transport_flat = db.Column(db.Float, nullable=False, default=0)

    # Deductions — percentages of CTC (kept simple/configurable, same
    # approach as the rest of Payroll — see README for the statutory-slab
    # caveat already documented there)
    pf_employee_pct = db.Column(db.Float, default=0)
    esi_employee_pct = db.Column(db.Float, default=0)
    insurance_pct = db.Column(db.Float, default=0)  # employee's share of group health/life insurance premium
    professional_tax_flat = db.Column(db.Float, default=0)
    tds_pct = db.Column(db.Float, default=0)
    employee_pf_rate_pct = db.Column(db.Float, nullable=False, default=0)
    employer_pf_rate_pct = db.Column(db.Float, nullable=False, default=0)
    employer_pf_flat = db.Column(db.Float, nullable=False, default=0)
    tds_flat = db.Column(db.Float, nullable=False, default=0)
    insurance_months = db.Column(JSON, nullable=False, default=list)
    insurance_amounts = db.Column(JSON, nullable=False, default=dict)
    arrears_by_employee = db.Column(JSON, nullable=True, default=dict)
    arrears_employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    arrears_description = db.Column(db.String(150), nullable=True)
    arrears_amount = db.Column(db.Float, nullable=True)
    arrears_month = db.Column(db.Integer, nullable=True)
    arrears_year = db.Column(db.Integer, nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_structures = db.relationship("SalaryStructure", back_populates="salary_template")

    def to_dict(self):
        arrears_by_employee = self.arrears_by_employee or {}
        if not arrears_by_employee and self.arrears_employee_id and self.arrears_amount:
            arrears_by_employee = {
                str(self.arrears_employee_id): {
                    "description": self.arrears_description or "",
                    "amount": self.arrears_amount,
                },
            }
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "company_name": self.company_name,
            "basic_pct": self.basic_pct,
            "hra_pct": self.hra_pct,
            "special_allowance_pct": self.special_allowance_pct,
            "other_allowance_pct": self.other_allowance_pct,
            "transport_flat": self.transport_flat,
            "pf_employee_pct": self.pf_employee_pct,
            "esi_employee_pct": self.esi_employee_pct,
            "insurance_pct": self.insurance_pct,
            "professional_tax_flat": self.professional_tax_flat,
            "tds_pct": self.tds_pct,
            "employee_pf_rate_pct": self.employee_pf_rate_pct,
            "employer_pf_rate_pct": self.employer_pf_rate_pct,
            "employer_pf_flat": self.employer_pf_flat,
            "tds_flat": self.tds_flat,
            "insurance_months": self.insurance_months or [],
            "insurance_amounts": self.insurance_amounts or {},
            "arrears_by_employee": arrears_by_employee,
            "arrears_employee_id": self.arrears_employee_id,
            "arrears_description": self.arrears_description,
            "arrears_amount": self.arrears_amount,
            "arrears_month": self.arrears_month,
            "arrears_year": self.arrears_year,
            "earnings_total_pct": round(
                self.basic_pct + self.hra_pct + self.special_allowance_pct + self.other_allowance_pct, 2
            ),
        }
