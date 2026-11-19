import json
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import (
    TopicLibrary, MockTestTemplate, MockTestQuestion, MockTestAssignment,
    MockTestAnswer, MockTestResult, Candidate, User,
)
from app.utils.security import roles_required
from app.utils.audit import log_action
from app.utils.ai_grading import grade_subjective_answer, grade_mcq_answer
from app.roles import RECRUITMENT_ROLES, HR_OPERATIONS, MANAGER

bp = Blueprint("mocktest", __name__, url_prefix="/api/mocktest")


# ============================================================================
# Topic library (maintained by HR Operations)
# ============================================================================

@bp.get("/topics")
@jwt_required()
def list_topics():
    return jsonify([t.to_dict() for t in TopicLibrary.query.order_by(TopicLibrary.name).all()])


@bp.post("/topics")
@roles_required(HR_OPERATIONS)
def create_topic():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"message": "Topic name is required."}), 400
    if TopicLibrary.query.filter_by(name=name).first():
        return jsonify({"message": "Topic already exists."}), 409
    topic = TopicLibrary(name=name)
    db.session.add(topic)
    db.session.commit()
    return jsonify(topic.to_dict()), 201


# ============================================================================
# Mock test templates — setup (Section 11)
# ============================================================================

@bp.get("/templates")
@jwt_required()
def list_templates():
    job_id = request.args.get("job_id", type=int)
    query = MockTestTemplate.query
    if job_id:
        query = query.filter_by(job_id=job_id)
    rows = query.order_by(MockTestTemplate.created_at.desc()).all()
    return jsonify([t.to_dict() for t in rows])


@bp.get("/templates/<int:template_id>")
@jwt_required()
def get_template(template_id):
    template = MockTestTemplate.query.get_or_404(template_id)
    data = template.to_dict()
    data["questions"] = [q.to_dict(include_answer=True) for q in template.questions]
    return jsonify(data)


@bp.post("/templates")
@roles_required(*RECRUITMENT_ROLES)
def create_template():
    """Body: { title, job_id, topics, complexity, duration_minutes,
    passing_threshold_pct, questions: [ {question_text, question_type,
    options_json, correct_answer, marks, topic} ] }"""
    payload = request.get_json(silent=True) or {}
    if not payload.get("title") or not payload.get("topics"):
        return jsonify({"message": "title and topics are required."}), 400

    template = MockTestTemplate(
        title=payload["title"],
        job_id=payload.get("job_id"),
        topics=payload["topics"],
        complexity=payload.get("complexity", "medium"),
        duration_minutes=payload.get("duration_minutes", 30),
        passing_threshold_pct=payload.get("passing_threshold_pct", 60),
        created_by=int(get_jwt_identity()),
    )
    db.session.add(template)
    db.session.flush()

    for q in payload.get("questions", []):
        db.session.add(MockTestQuestion(
            template_id=template.id,
            topic=q.get("topic"),
            question_text=q["question_text"],
            question_type=q.get("question_type", "mcq"),
            options_json=json.dumps(q.get("options")) if q.get("options") else None,
            correct_answer=q.get("correct_answer"),
            marks=q.get("marks", 1),
        ))

    db.session.commit()
    return jsonify(template.to_dict()), 201


@bp.post("/templates/<int:template_id>/questions")
@roles_required(*RECRUITMENT_ROLES)
def add_question(template_id):
    MockTestTemplate.query.get_or_404(template_id)
    payload = request.get_json(silent=True) or {}
    if not payload.get("question_text"):
        return jsonify({"message": "question_text is required."}), 400

    question = MockTestQuestion(
        template_id=template_id,
        topic=payload.get("topic"),
        question_text=payload["question_text"],
        question_type=payload.get("question_type", "mcq"),
        options_json=json.dumps(payload.get("options")) if payload.get("options") else None,
        correct_answer=payload.get("correct_answer"),
        marks=payload.get("marks", 1),
    )
    db.session.add(question)
    db.session.commit()
    return jsonify(question.to_dict(include_answer=True)), 201


# ============================================================================
# Assignment (Section 11) + retesting (Section 12)
# ============================================================================

@bp.post("/assign")
@roles_required(*RECRUITMENT_ROLES)
def assign_test():
    payload = request.get_json(silent=True) or {}
    template_id = payload.get("template_id")
    candidate_ids = payload.get("candidate_ids", [])
    if not template_id or not candidate_ids:
        return jsonify({"message": "template_id and candidate_ids are required."}), 400

    template = MockTestTemplate.query.get_or_404(template_id)
    try:
        window_start = datetime.strptime(payload["window_start"], "%Y-%m-%dT%H:%M")
        window_end = datetime.strptime(payload["window_end"], "%Y-%m-%dT%H:%M")
    except (KeyError, ValueError):
        return jsonify({"message": "window_start and window_end are required (format YYYY-MM-DDTHH:MM)."}), 400

    actor_id = int(get_jwt_identity())
    created = []
    for cid in candidate_ids:
        candidate = Candidate.query.get(cid)
        if not candidate:
            continue
        attempt_number = MockTestAssignment.query.filter_by(
            template_id=template_id, candidate_id=cid
        ).count() + 1

        assignment = MockTestAssignment(
            template_id=template_id, candidate_id=cid, attempt_number=attempt_number,
            assigned_by=actor_id, window_start=window_start, window_end=window_end,
        )
        db.session.add(assignment)
        candidate.stage = "mock_test"
        db.session.flush()
        log_action(cid, "mock_test_assigned", actor_id=actor_id,
                   detail=f"Template '{template.title}', attempt #{attempt_number}")
        created.append(assignment)

    db.session.commit()
    return jsonify([a.to_dict() for a in created]), 201


@bp.post("/assignments/<int:assignment_id>/retest")
@roles_required(*RECRUITMENT_ROLES)
def assign_retest(assignment_id):
    """Retesting is recruiter-assigned only — never candidate self-service."""
    original = MockTestAssignment.query.get_or_404(assignment_id)
    payload = request.get_json(silent=True) or {}
    try:
        window_start = datetime.strptime(payload["window_start"], "%Y-%m-%dT%H:%M")
        window_end = datetime.strptime(payload["window_end"], "%Y-%m-%dT%H:%M")
    except (KeyError, ValueError):
        return jsonify({"message": "window_start and window_end are required (format YYYY-MM-DDTHH:MM)."}), 400

    actor_id = int(get_jwt_identity())
    attempt_number = MockTestAssignment.query.filter_by(
        template_id=original.template_id, candidate_id=original.candidate_id
    ).count() + 1

    retest = MockTestAssignment(
        template_id=original.template_id, candidate_id=original.candidate_id,
        attempt_number=attempt_number, assigned_by=actor_id,
        window_start=window_start, window_end=window_end,
    )
    db.session.add(retest)
    db.session.flush()
    log_action(original.candidate_id, "mock_test_retest_assigned", actor_id=actor_id,
               detail=f"Attempt #{attempt_number} of template #{original.template_id}")
    db.session.commit()
    return jsonify(retest.to_dict()), 201


@bp.get("/assignments")
@jwt_required()
def list_assignments():
    claims = get_jwt()
    role = claims.get("role")
    actor_id = int(get_jwt_identity())

    query = MockTestAssignment.query
    if role not in (HR_OPERATIONS, MANAGER):
        query = query.join(Candidate).filter(Candidate.assigned_to == actor_id)

    template_id = request.args.get("template_id", type=int)
    candidate_id = request.args.get("candidate_id", type=int)
    if template_id:
        query = query.filter(MockTestAssignment.template_id == template_id)
    if candidate_id:
        query = query.filter(MockTestAssignment.candidate_id == candidate_id)

    rows = query.order_by(MockTestAssignment.created_at.desc()).all()
    return jsonify([a.to_dict() for a in rows])


@bp.get("/templates/<int:template_id>/rankings")
@jwt_required()
def rankings(template_id):
    """Rankings scoped to this specific mock test template — latest attempt per
    candidate, ranked by score (Section 12 of the spec)."""
    MockTestTemplate.query.get_or_404(template_id)
    assignments = (
        MockTestAssignment.query.filter_by(template_id=template_id)
        .filter(MockTestAssignment.status == "completed")
        .order_by(MockTestAssignment.candidate_id, MockTestAssignment.attempt_number.desc())
        .all()
    )

    latest_by_candidate = {}
    for a in assignments:
        if a.candidate_id not in latest_by_candidate:
            latest_by_candidate[a.candidate_id] = a

    ranked = sorted(
        latest_by_candidate.values(),
        key=lambda a: (a.result.percentage if a.result else 0),
        reverse=True,
    )
    return jsonify([
        {
            "rank": i + 1,
            "candidate_id": a.candidate_id,
            "candidate_name": a.candidate.full_name if a.candidate else None,
            "attempt_number": a.attempt_number,
            "score": a.result.score if a.result else None,
            "percentage": a.result.percentage if a.result else None,
            "passed": a.result.passed if a.result else None,
        }
        for i, a in enumerate(ranked)
    ])


# ============================================================================
# Candidate-facing test-taking — public via access token, no HRMS account
# ============================================================================

@bp.get("/take/<token>")
def take_test_info(token):
    assignment = MockTestAssignment.query.filter_by(access_token=token).first_or_404()
    now = datetime.utcnow()
    if now < assignment.window_start:
        return jsonify({"message": "This test is not open yet.", "opens_at": assignment.window_start.isoformat()}), 403
    if now > assignment.window_end or assignment.status == "expired":
        return jsonify({"message": "This test window has closed."}), 403
    if assignment.status == "completed":
        return jsonify({"message": "This test has already been submitted."}), 403

    template = assignment.template
    return jsonify({
        "template_title": template.title,
        "duration_minutes": template.duration_minutes,
        "window_end": assignment.window_end.isoformat(),
        "status": assignment.status,
        "questions": [q.to_dict(include_answer=False) for q in template.questions],
    })


@bp.post("/take/<token>/start")
def start_test(token):
    assignment = MockTestAssignment.query.filter_by(access_token=token).first_or_404()
    if assignment.status == "assigned":
        assignment.status = "in_progress"
        assignment.started_at = datetime.utcnow()
        db.session.commit()
    return jsonify(assignment.to_dict())


@bp.post("/take/<token>/submit")
def submit_test(token):
    assignment = MockTestAssignment.query.filter_by(access_token=token).first_or_404()
    if assignment.status == "completed":
        return jsonify({"message": "This test has already been submitted."}), 400
    if datetime.utcnow() > assignment.window_end:
        assignment.status = "expired"
        db.session.commit()
        return jsonify({"message": "The test window has closed; this submission was not accepted."}), 403

    payload = request.get_json(silent=True) or {}
    submitted_answers = {a["question_id"]: a.get("answer_text", "") for a in payload.get("answers", [])}

    total_score, max_score = 0.0, 0.0
    topic_scores = {}  # topic -> [earned, possible]

    for question in assignment.template.questions:
        max_score += question.marks
        answer_text = submitted_answers.get(question.id, "")

        if question.question_type == "mcq":
            score, is_correct = grade_mcq_answer(question, answer_text)
            feedback = "Correct" if is_correct else "Incorrect"
        else:
            score, feedback = grade_subjective_answer(question.question_text, answer_text, question.marks)

        total_score += score
        topic = question.topic or "General"
        earned, possible = topic_scores.get(topic, (0, 0))
        topic_scores[topic] = (earned + score, possible + question.marks)

        db.session.add(MockTestAnswer(
            assignment_id=assignment.id, question_id=question.id,
            answer_text=answer_text, score_awarded=score, ai_feedback=feedback,
        ))

    percentage = round((total_score / max_score) * 100, 2) if max_score else 0
    topic_breakdown = {
        t: round((earned / possible) * 100, 2) if possible else 0
        for t, (earned, possible) in topic_scores.items()
    }

    result = MockTestResult(
        assignment_id=assignment.id, score=total_score, max_score=max_score,
        percentage=percentage, topic_breakdown_json=json.dumps(topic_breakdown),
        passed=percentage >= assignment.template.passing_threshold_pct,
    )
    db.session.add(result)

    assignment.status = "completed"
    assignment.submitted_at = datetime.utcnow()
    db.session.flush()

    log_action(assignment.candidate_id, "mock_test_graded", actor_id=None,
               detail=f"'{assignment.template.title}' attempt #{assignment.attempt_number}: {percentage}%")
    db.session.commit()
    return jsonify(result.to_dict())
