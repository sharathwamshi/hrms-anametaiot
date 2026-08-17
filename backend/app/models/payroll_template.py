from datetime import datetime
from app.extensions import db


class SalaryTemplate(db.Model):
    """A reusable salary structure template — Finance defines the % split
    once (e.g. 'Standard Employee', 'Senior Manager') and applies it to any
    employee's CTC instead of typing flat numbers every time."""
    __tablename__ = "salary_templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)

    # Earnings — percentages of CTC, should sum to 100 (UI warns if not)
    basic_pct = db.Column(db.Float, default=50)
    hra_pct = db.Column(db.Float, default=20)
    special_allowance_pct = db.Column(db.Float, default=20)
    other_allowance_pct = db.Column(db.Float, default=10)

    # Deductions — percentages of CTC (kept simple/configurable, same
    # approach as the rest of Payroll — see README for the statutory-slab
    # caveat already documented there)
    pf_employee_pct = db.Column(db.Float, default=6)
    esi_employee_pct = db.Column(db.Float, default=0)
    professional_tax_flat = db.Column(db.Float, default=200)
    tds_pct = db.Column(db.Float, default=0)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "basic_pct": self.basic_pct,
            "hra_pct": self.hra_pct,
            "special_allowance_pct": self.special_allowance_pct,
            "other_allowance_pct": self.other_allowance_pct,
            "pf_employee_pct": self.pf_employee_pct,
            "esi_employee_pct": self.esi_employee_pct,
            "professional_tax_flat": self.professional_tax_flat,
            "tds_pct": self.tds_pct,
            "earnings_total_pct": round(
                self.basic_pct + self.hra_pct + self.special_allowance_pct + self.other_allowance_pct, 2
            ),
        }
