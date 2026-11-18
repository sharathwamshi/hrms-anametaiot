from datetime import datetime

from app.extensions import db


class EmployeeFamilyMember(db.Model):
    __tablename__ = "employee_family_members"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    relationship = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    is_emergency_contact = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text("0"))
    notes = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("family_members", lazy="select"))

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "relationship": self.relationship,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "phone": self.phone,
            "is_emergency_contact": bool(self.is_emergency_contact),
            "notes": self.notes,
        }


class EmployeeEmergencyCommunication(db.Model):
    __tablename__ = "employee_emergency_communications"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    family_member_id = db.Column(
        db.Integer,
        db.ForeignKey("employee_family_members.id", ondelete="SET NULL"),
        nullable=True,
    )
    contact_name = db.Column(db.String(150), nullable=False)
    relationship = db.Column(db.String(100), nullable=True)
    contact_phone = db.Column(db.String(30), nullable=True)
    communication_method = db.Column(db.String(30), nullable=False)
    purpose = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.String(1000), nullable=True)
    outcome = db.Column(db.String(255), nullable=True)
    contacted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    employee = db.relationship("User", foreign_keys=[employee_id])
    family_member = db.relationship("EmployeeFamilyMember")
    recorder = db.relationship("User", foreign_keys=[recorded_by])

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "family_member_id": self.family_member_id,
            "contact_name": self.contact_name,
            "relationship": self.relationship,
            "contact_phone": self.contact_phone,
            "communication_method": self.communication_method,
            "purpose": self.purpose,
            "notes": self.notes,
            "outcome": self.outcome,
            "contacted_at": self.contacted_at.isoformat() if self.contacted_at else None,
            "recorded_by": self.recorded_by,
            "recorded_by_name": self.recorder.full_name if self.recorder else None,
        }
