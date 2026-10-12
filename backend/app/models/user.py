from datetime import datetime
from app.extensions import db, bcrypt


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employees = db.relationship("User", back_populates="department")

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(20), unique=True, nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(30), nullable=False)  # see app/roles.py
    designation = db.Column(db.String(120))
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"))
    department = db.relationship("Department", back_populates="employees")

    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    manager = db.relationship("User", remote_side=[id], foreign_keys=[manager_id], backref="direct_reports")

    date_of_joining = db.Column(db.Date)
    avatar_url = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

    # Removal audit trail. People are never hard-deleted (payslips, attendance, leave,
    # placements and 40+ other records point at them and must be kept), so "removing" a
    # person deactivates them and records who did it, when, and why.
    removed_at = db.Column(db.DateTime, nullable=True)
    removed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    removal_reason = db.Column(db.String(255), nullable=True)
    remover = db.relationship("User", remote_side=[id], foreign_keys=[removed_by])

    # --- Recruiter-specific policy fields (meaningful only when role == hr_recruiter) ---
    self_verify_rights = db.Column(db.Boolean, default=False)
    self_verify_granted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    revalidation_interval_days = db.Column(db.Integer, default=60)  # set by the recruiter's Manager

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, raw_password):
        self.password_hash = bcrypt.generate_password_hash(raw_password).decode("utf-8")

    def check_password(self, raw_password):
        return bcrypt.check_password_hash(self.password_hash, raw_password)

    def to_dict(self, include_sensitive=False):
        data = {
            "id": self.id,
            "employee_code": self.employee_code,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "designation": self.designation,
            "department": self.department.name if self.department else None,
            "department_id": self.department_id,
            "manager_id": self.manager_id,
            "manager_name": self.manager.full_name if self.manager else None,
            "date_of_joining": self.date_of_joining.isoformat() if self.date_of_joining else None,
            "avatar_url": self.avatar_url,
            "is_active": self.is_active,
            "removed_at": self.removed_at.isoformat() + "Z" if self.removed_at else None,
            "removed_by": self.removed_by,
            "removed_by_name": self.remover.full_name if self.remover else None,
            "removal_reason": self.removal_reason,
            "self_verify_rights": self.self_verify_rights,
            "revalidation_interval_days": self.revalidation_interval_days,
        }
        return data
