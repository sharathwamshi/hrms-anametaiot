from datetime import datetime
from app.extensions import db


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    posted_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    audience_role = db.Column(db.String(30), nullable=True)  # null = everyone
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "author_name": self.author.full_name if self.author else "HR Operations",
            "audience_role": self.audience_role,
            "created_at": self.created_at.isoformat(),
        }


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
