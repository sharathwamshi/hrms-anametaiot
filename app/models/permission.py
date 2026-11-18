from datetime import datetime
from app.extensions import db

# The full catalogue of grantable permissions. Each is an approval-style
# capability that normally belongs to a fixed role (Manager/HR Operations/
# Finance) but can be extended to a specific individual employee — e.g. a
# Manager delegating "approve candidates" (offer approval) to a senior
# team member without making them a Manager outright.
PERMISSION_CATALOGUE = {
    "approve_offers": "Approve recruitment offers (candidates)",
    "approve_job_postings": "Approve job requisitions",
    "approve_vendor_invoices": "Approve vendor invoices",
}


class EmployeePermission(db.Model):
    """One granted permission for one employee. Existence of a row = granted."""
    __tablename__ = "employee_permissions"
    __table_args__ = (
        db.UniqueConstraint("user_id", "permission_key", name="uq_employee_permission"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    permission_key = db.Column(db.String(50), nullable=False)
    granted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    granted_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "permission_key": self.permission_key,
            "label": PERMISSION_CATALOGUE.get(self.permission_key, self.permission_key),
            "granted_by": self.granted_by,
            "granted_at": self.granted_at.isoformat(),
        }
