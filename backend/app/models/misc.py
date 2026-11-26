from datetime import datetime

from app.extensions import db


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    posted_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    audience_role = db.Column(db.String(30), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(40), nullable=False, default="general")
    priority = db.Column(db.String(20), nullable=False, default="normal")
    audiences = db.Column(db.JSON, nullable=True)
    publish_at = db.Column(db.DateTime, nullable=True, index=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)

    author = db.relationship("User", foreign_keys=[posted_by])


class Asset(db.Model):
    __tablename__ = "assets"

    id = db.Column(db.Integer, primary_key=True)
    asset_tag = db.Column(db.String(50), unique=True, nullable=False)
    category = db.Column(db.String(50))  # laptop, id_card, sim, accessory
    description = db.Column(db.String(200))
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    assigned_on = db.Column(db.Date, nullable=True)
    returned_on = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="available")  # available, assigned, returned, retired

    holder = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "asset_tag": self.asset_tag,
            "category": self.category,
            "description": self.description,
            "assigned_to": self.assigned_to,
            "holder_name": self.holder.full_name if self.holder else None,
            "assigned_on": self.assigned_on.isoformat() if self.assigned_on else None,
            "returned_on": self.returned_on.isoformat() if self.returned_on else None,
            "status": self.status,
        }
