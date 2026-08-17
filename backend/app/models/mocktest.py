import secrets
from datetime import datetime
from app.extensions import db


class TopicLibrary(db.Model):
    """Topic list maintained by HR Operations, used when building mock test templates."""
    __tablename__ = "topic_library"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class MockTestTemplate(db.Model):
    __tablename__ = "mock_test_templates"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("job_postings.id"), nullable=True)
    topics = db.Column(db.String(255), nullable=False)  # comma-separated topic names
    complexity = db.Column(db.String(20), default="medium")  # easy, medium, hard
    duration_minutes = db.Column(db.Integer, default=30)
    passing_threshold_pct = db.Column(db.Float, default=60)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    questions = db.relationship(
        "MockTestQuestion", backref="template", cascade="all, delete-orphan"
    )
    assignments = db.relationship("MockTestAssignment", backref="template")
    job = db.relationship("JobPosting")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "job_id": self.job_id,
            "job_title": self.job.title if self.job_id and self.job else None,
            "topics": self.topics,
            "complexity": self.complexity,
            "duration_minutes": self.duration_minutes,
            "passing_threshold_pct": self.passing_threshold_pct,
            "question_count": len(self.questions),
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
        }


class MockTestQuestion(db.Model):
    __tablename__ = "mock_test_questions"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("mock_test_templates.id"), nullable=False)
    topic = db.Column(db.String(80), nullable=True)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), default="mcq")  # mcq, subjective
    options_json = db.Column(db.Text, nullable=True)  # JSON list, for mcq
    correct_answer = db.Column(db.String(500), nullable=True)  # for mcq
    marks = db.Column(db.Float, default=1)

    def to_dict(self, include_answer=False):
        data = {
            "id": self.id,
            "template_id": self.template_id,
            "topic": self.topic,
            "question_text": self.question_text,
            "question_type": self.question_type,
            "options_json": self.options_json,
            "marks": self.marks,
        }
        if include_answer:
            data["correct_answer"] = self.correct_answer
        return data


class MockTestAssignment(db.Model):
    __tablename__ = "mock_test_assignments"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("mock_test_templates.id"), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=False)
    attempt_number = db.Column(db.Integer, default=1)

    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    access_token = db.Column(db.String(64), unique=True, default=lambda: secrets.token_urlsafe(24))

    window_start = db.Column(db.DateTime, nullable=False)
    window_end = db.Column(db.DateTime, nullable=False)

    status = db.Column(db.String(20), default="assigned")
    # assigned, in_progress, completed, expired
    started_at = db.Column(db.DateTime, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    result = db.relationship(
        "MockTestResult", backref="assignment", uselist=False, cascade="all, delete-orphan"
    )
    answers = db.relationship(
        "MockTestAnswer", backref="assignment", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "template_id": self.template_id,
            "template_title": self.template.title if self.template else None,
            "candidate_id": self.candidate_id,
            "candidate_name": self.candidate.full_name if self.candidate else None,
            "attempt_number": self.attempt_number,
            "assigned_by": self.assigned_by,
            "access_token": self.access_token,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "result": self.result.to_dict() if self.result else None,
        }


class MockTestAnswer(db.Model):
    __tablename__ = "mock_test_answers"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("mock_test_assignments.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("mock_test_questions.id"), nullable=False)
    answer_text = db.Column(db.Text, nullable=True)
    score_awarded = db.Column(db.Float, default=0)
    ai_feedback = db.Column(db.Text, nullable=True)

    question = db.relationship("MockTestQuestion")

    def to_dict(self):
        return {
            "id": self.id,
            "question_id": self.question_id,
            "question_text": self.question.question_text if self.question else None,
            "answer_text": self.answer_text,
            "score_awarded": self.score_awarded,
            "ai_feedback": self.ai_feedback,
        }


class MockTestResult(db.Model):
    __tablename__ = "mock_test_results"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("mock_test_assignments.id"), unique=True, nullable=False)

    score = db.Column(db.Float, default=0)
    max_score = db.Column(db.Float, default=0)
    percentage = db.Column(db.Float, default=0)
    topic_breakdown_json = db.Column(db.Text, nullable=True)  # {"Java": 80, "SQL": 60, ...}
    ai_feedback = db.Column(db.Text, nullable=True)
    passed = db.Column(db.Boolean, default=False)
    graded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "score": self.score,
            "max_score": self.max_score,
            "percentage": self.percentage,
            "topic_breakdown_json": self.topic_breakdown_json,
            "ai_feedback": self.ai_feedback,
            "passed": self.passed,
            "graded_at": self.graded_at.isoformat() if self.graded_at else None,
        }
