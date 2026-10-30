from datetime import date, datetime

from app.extensions import db


INSURANCE_TYPES = {"health", "life", "accident", "dental", "vision", "travel", "other"}


class InsurancePolicy(db.Model):
    __tablename__ = "insurance_policies"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    insurance_type = db.Column(db.String(30), nullable=False)
    provider_name = db.Column(db.String(150), nullable=False)
    policy_number = db.Column(db.String(150), nullable=False)
    member_id = db.Column(db.String(150), nullable=True)
    certificate_number = db.Column(db.String(150), nullable=True)
    credentials = db.Column(db.JSON, nullable=True)
    coverage_amount = db.Column(db.Numeric(14, 2), nullable=True)
    coverage_description = db.Column(db.Text, nullable=True)
    policy_start_date = db.Column(db.Date, nullable=False)
    policy_expiry_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    contact_name = db.Column(db.String(150), nullable=True)
    contact_email = db.Column(db.String(150), nullable=True)
    contact_phone = db.Column(db.String(40), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active", server_default="active")
    renewed_from_id = db.Column(db.Integer, db.ForeignKey("insurance_policies.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    employee = db.relationship("User", foreign_keys=[employee_id], backref=db.backref("insurance_policies", lazy="select"))
    renewed_from = db.relationship("InsurancePolicy", remote_side=[id], backref="renewals")

    @property
    def expiry_status(self):
        if self.status == "archived":
            return "archived"
        if self.policy_expiry_date < date.today():
            return "expired"
        if (self.policy_expiry_date - date.today()).days <= 7:
            return "expiring_soon"
        return "active"

    def to_dict(self, include_internal=False):
        data = {
            "id": self.id,
            "employee_id": self.employee_id,
            "employee_name": self.employee.full_name if self.employee else None,
            "employee_code": self.employee.employee_code if self.employee else None,
            "insurance_type": self.insurance_type,
            "provider_name": self.provider_name,
            "policy_number": self.policy_number,
            "member_id": self.member_id,
            "certificate_number": self.certificate_number,
            "credentials": self.credentials or {},
            "coverage_amount": float(self.coverage_amount) if self.coverage_amount is not None else None,
            "coverage_description": self.coverage_description,
            "policy_start_date": self.policy_start_date.isoformat(),
            "policy_expiry_date": self.policy_expiry_date.isoformat(),
            "notes": self.notes,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "status": self.status,
            "expiry_status": self.expiry_status,
            "renewed_from_id": self.renewed_from_id,
            "document_count": len([d for d in self.documents if d.status == "active"]),
        }
        if include_internal:
            data.update({
                "created_by": self.created_by,
                "updated_by": self.updated_by,
                "created_at": self.created_at.isoformat(),
                "updated_at": self.updated_at.isoformat(),
            })
        return data


class InsuranceDocument(db.Model):
    __tablename__ = "insurance_documents"

    id = db.Column(db.Integer, primary_key=True)
    policy_id = db.Column(db.Integer, db.ForeignKey("insurance_policies.id"), nullable=False, index=True)
    document_type = db.Column(db.String(40), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(255), nullable=False, unique=True)
    mime_type = db.Column(db.String(120), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active", server_default="active")
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    archived_at = db.Column(db.DateTime, nullable=True)
    replaced_by_id = db.Column(db.Integer, db.ForeignKey("insurance_documents.id"), nullable=True)

    policy = db.relationship("InsurancePolicy", backref=db.backref("documents", lazy="select"))
    uploader = db.relationship("User", foreign_keys=[uploaded_by])
    replaced_by = db.relationship("InsuranceDocument", remote_side=[id])

    def to_dict(self):
        return {
            "id": self.id,
            "policy_id": self.policy_id,
            "document_type": self.document_type,
            "original_filename": self.original_filename,
            "file_size": self.file_size,
            "status": self.status,
            "uploaded_by": self.uploaded_by,
            "uploaded_by_name": self.uploader.full_name if self.uploader else None,
            "uploaded_at": self.uploaded_at.isoformat(),
            "download_url": f"/insurance/documents/{self.id}/download",
        }


class InsuranceReminder(db.Model):
    __tablename__ = "insurance_reminders"
    __table_args__ = (db.UniqueConstraint("policy_id", "recipient_id", "reminder_date", name="uq_insurance_reminder_recipient_date"),)

    id = db.Column(db.Integer, primary_key=True)
    policy_id = db.Column(db.Integer, db.ForeignKey("insurance_policies.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reminder_date = db.Column(db.Date, nullable=False)
    sent_at = db.Column(db.DateTime, nullable=True)
    delivery_status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    error_message = db.Column(db.String(500), nullable=True)

    policy = db.relationship("InsurancePolicy", backref="reminders")
    recipient = db.relationship("User")

