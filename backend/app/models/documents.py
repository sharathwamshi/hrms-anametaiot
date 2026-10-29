from datetime import datetime
from app.extensions import db

DOC_TYPES = [
    "academic", "education_10th", "education_12th", "diploma",
    "undergraduate_degree", "undergraduate_marks", "postgraduate_degree",
    "postgraduate_marks", "other_education", "pan", "aadhaar", "government_id",
    "experience", "relieving_letter", "previous_offer", "current_appointment",
    "resume", "professional_certification", "other",
]
DOC_TYPE_LABELS = {
    "academic": "Academic Document",
    "education_10th": "10th Certificate / Marks Card",
    "education_12th": "12th Certificate / Marks Card",
    "diploma": "Diploma Certificate / Marks Card",
    "undergraduate_degree": "Undergraduate Degree Certificate",
    "undergraduate_marks": "Undergraduate Marks Card",
    "postgraduate_degree": "Postgraduate Degree Certificate",
    "postgraduate_marks": "Postgraduate Marks Card",
    "other_education": "Other Education Document",
    "pan": "PAN Card",
    "aadhaar": "Aadhaar Card",
    "government_id": "Other Government ID",
    "experience": "Experience Document",
    "relieving_letter": "Relieving Letter",
    "previous_offer": "Previous Offer Letter",
    "current_appointment": "Current Appointment Letter",
    "resume": "Resume",
    "professional_certification": "Professional Certification",
    "other": "Other Document",
}


class EmployeeDocument(db.Model):
    """Every employee's own document locker — academic certificates, experience
    letters, and relieving letter(s) from previous employment."""
    __tablename__ = "employee_documents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    doc_type = db.Column(db.String(30), nullable=False)  # see DOC_TYPES
    title = db.Column(db.String(150), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    original_filename = db.Column(db.String(255), nullable=True)
    storage_key = db.Column(db.String(255), nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    file_size = db.Column(db.BigInteger, nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verification_status = db.Column(
        db.String(20), nullable=False, default="pending", server_default="pending"
    )
    verification_note = db.Column(db.String(500), nullable=True)
    verified_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])
    uploader = db.relationship("User", foreign_keys=[uploaded_by])
    verifier = db.relationship("User", foreign_keys=[verified_by])

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "doc_type": self.doc_type,
            "doc_type_label": DOC_TYPE_LABELS.get(self.doc_type, self.doc_type),
            "title": self.title,
            "file_path": f"/documents/{self.id}/download",
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "original_filename": self.original_filename or self.file_path.rsplit("/", 1)[-1],
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "uploaded_by": self.uploaded_by,
            "uploaded_by_name": self.uploader.full_name if self.uploader else None,
            "verification_status": self.verification_status or "pending",
            "verification_note": self.verification_note,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "verified_by": self.verified_by,
            "verified_by_name": self.verifier.full_name if self.verifier else None,
        }
