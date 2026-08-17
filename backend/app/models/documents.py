from datetime import datetime
from app.extensions import db

DOC_TYPES = ["academic", "experience", "relieving_letter"]
DOC_TYPE_LABELS = {
    "academic": "Academic Document",
    "experience": "Experience Document",
    "relieving_letter": "Relieving Letter",
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

    user = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "doc_type": self.doc_type,
            "doc_type_label": DOC_TYPE_LABELS.get(self.doc_type, self.doc_type),
            "title": self.title,
            "file_path": self.file_path,
            "uploaded_at": self.uploaded_at.isoformat(),
        }
