from datetime import datetime
from app.extensions import db


class JobPosting(db.Model):
    __tablename__ = "job_postings"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"))
    employment_type = db.Column(db.String(30), default="full_time")
    openings = db.Column(db.Integer, default=1)
    description = db.Column(db.Text)

    salary_min = db.Column(db.Float, nullable=True)
    salary_max = db.Column(db.Float, nullable=True)
    priority = db.Column(db.String(20), default="standard")
    auto_close_date = db.Column(db.Date, nullable=True)
    requisition_status = db.Column(db.String(20), default="pending_approval")
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    screening_questions = db.Column(db.Text, nullable=True)
    post_image_url = db.Column(db.String(255), nullable=True)
    linkedin_post_url = db.Column(db.String(255), nullable=True)
    naukri_post_url = db.Column(db.String(255), nullable=True)
    interview_levels = db.Column(db.Text, nullable=True)  # comma-separated, e.g. "Screening, Tech L1, Tech L2, HR, Offer"
    requisition_type = db.Column(db.String(20), default="internal")  # internal | client
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=True)  # set only when requisition_type="client"

    status = db.Column(db.String(20), default="open")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    department = db.relationship("Department")
    vendor = db.relationship("Vendor")
    candidates = db.relationship("Candidate", backref="job", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id, "title": self.title,
            "department": self.department.name if self.department else None,
            "department_id": self.department_id, "employment_type": self.employment_type,
            "openings": self.openings, "description": self.description,
            "salary_min": self.salary_min, "salary_max": self.salary_max,
            "priority": self.priority,
            "auto_close_date": self.auto_close_date.isoformat() if self.auto_close_date else None,
            "requisition_status": self.requisition_status, "approved_by": self.approved_by,
            "screening_questions": self.screening_questions, "post_image_url": self.post_image_url,
            "linkedin_post_url": self.linkedin_post_url, "naukri_post_url": self.naukri_post_url,
            "interview_levels": [l.strip() for l in (self.interview_levels or "").split(",") if l.strip()],
            "requisition_type": self.requisition_type or "internal",
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor.name if self.vendor else None,
            "status": self.status, "candidate_count": len(self.candidates),
            "created_at": self.created_at.isoformat(),
        }


class Candidate(db.Model):
    __tablename__ = "candidates"
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job_postings.id"), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150))
    email_normalized = db.Column(db.String(150), index=True)
    phone = db.Column(db.String(20))
    phone_normalized = db.Column(db.String(20), index=True)
    resume_url = db.Column(db.String(255))
    resume_file_path = db.Column(db.String(255), nullable=True)
    source = db.Column(db.String(50))
    skills = db.Column(db.String(500), nullable=True)
    location = db.Column(db.String(120), nullable=True)
    open_to_relocation = db.Column(db.Boolean, default=False)
    current_level = db.Column(db.String(100), nullable=True)  # e.g. "Tech L1" — should match one of job.interview_levels

    stage = db.Column(db.String(30), default="applied")
    notes = db.Column(db.Text)

    validation_status = db.Column(db.String(20), default="pending")
    validation_notes = db.Column(db.Text, nullable=True)
    duplicate_of_candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=True)

    verification_status = db.Column(db.String(20), default="unverified")
    verified_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    next_revalidation_due = db.Column(db.DateTime, nullable=True)

    referring_employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    referral_bonus_status = db.Column(db.String(20), nullable=True)

    bgv_status = db.Column(db.String(20), default="not_started")
    linked_employee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    added_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    interviews = db.relationship("Interview", backref="candidate", cascade="all, delete-orphan")
    screening_calls = db.relationship("ScreeningCall", backref="candidate", cascade="all, delete-orphan",
                                       order_by="ScreeningCall.attempt_number")
    mock_assignments = db.relationship("MockTestAssignment", backref="candidate", cascade="all, delete-orphan")
    notes_thread = db.relationship("CandidateNote", backref="candidate", cascade="all, delete-orphan",
                                    order_by="CandidateNote.created_at")
    audit_log = db.relationship("CandidateAuditLog", backref="candidate", cascade="all, delete-orphan",
                                 order_by="CandidateAuditLog.created_at")
    offers = db.relationship("Offer", backref="candidate", cascade="all, delete-orphan")

    def to_dict(self, include_detail=False):
        data = {
            "id": self.id, "job_id": self.job_id,
            "job_title": self.job.title if self.job else None,
            "requisition_type": self.job.requisition_type if self.job else None,
            "vendor_name": self.job.vendor.name if (self.job and self.job.vendor) else None,
            "full_name": self.full_name, "email": self.email, "phone": self.phone,
            "resume_url": self.resume_url, "resume_file_path": self.resume_file_path,
            "source": self.source,
            "skills": [s.strip() for s in (self.skills or "").split(",") if s.strip()],
            "location": self.location,
            "open_to_relocation": self.open_to_relocation,
            "current_level": self.current_level,
            "stage": self.stage, "notes": self.notes,
            "validation_status": self.validation_status, "validation_notes": self.validation_notes,
            "duplicate_of_candidate_id": self.duplicate_of_candidate_id,
            "verification_status": self.verification_status, "verified_by": self.verified_by,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "next_revalidation_due": self.next_revalidation_due.isoformat() if self.next_revalidation_due else None,
            "can_reverify_now": (self.next_revalidation_due is None or self.next_revalidation_due <= datetime.utcnow()),
            "referring_employee_id": self.referring_employee_id,
            "referral_bonus_status": self.referral_bonus_status,
            "bgv_status": self.bgv_status, "linked_employee_id": self.linked_employee_id,
            "added_by": self.added_by, "assigned_to": self.assigned_to,
            "created_at": self.created_at.isoformat(),
        }
        if include_detail:
            data["screening_calls"] = [c.to_dict() for c in self.screening_calls]
            data["notes_thread"] = [n.to_dict() for n in self.notes_thread]
            data["audit_log"] = [a.to_dict() for a in self.audit_log]
        return data


class Interview(db.Model):
    __tablename__ = "interviews"
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    round_name = db.Column(db.String(50))
    mode = db.Column(db.String(20), default="online")
    status = db.Column(db.String(20), default="scheduled")
    reschedule_reason = db.Column(db.String(255), nullable=True)
    feedback = db.Column(db.Text)
    scorecard = db.Column(db.Text, nullable=True)
    result = db.Column(db.String(20))
    scheduled_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    panelists = db.relationship("InterviewPanelist", backref="interview", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id, "candidate_id": self.candidate_id,
            "scheduled_at": self.scheduled_at.isoformat(), "round_name": self.round_name,
            "mode": self.mode, "status": self.status, "reschedule_reason": self.reschedule_reason,
            "feedback": self.feedback, "scorecard": self.scorecard, "result": self.result,
            "scheduled_by": self.scheduled_by,
            "panelists": [p.to_dict() for p in self.panelists],
        }


class InterviewPanelist(db.Model):
    __tablename__ = "interview_panelists"
    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey("interviews.id"), nullable=False)
    interviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    interviewer = db.relationship("User")

    def to_dict(self):
        return {"id": self.id, "interviewer_id": self.interviewer_id,
                "interviewer_name": self.interviewer.full_name if self.interviewer else None}
