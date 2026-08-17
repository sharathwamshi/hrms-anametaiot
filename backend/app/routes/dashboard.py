from datetime import date
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.models import (
    User, Attendance, LeaveRequest, JobPosting, Candidate, Payslip, Announcement,
)
from app.roles import MANAGER, HR_OPERATIONS, FINANCE_ACCOUNTS, OPERATIONS, HR_RECRUITER, EMPLOYEE, CONTRACT_EMPLOYEE

bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@bp.get("/summary")
@jwt_required()
def summary():
    claims = get_jwt()
    role = claims.get("role")
    user_id = int(get_jwt_identity())
    today = date.today()

    data = {"role": role, "today": today.isoformat()}

    if role == HR_OPERATIONS:
        data["headcount"] = User.query.filter_by(is_active=True).count()
        data["present_today"] = Attendance.query.filter_by(work_date=today, status="present").count()
        data["pending_leave_requests"] = LeaveRequest.query.filter_by(status="pending").count()
        data["open_positions"] = JobPosting.query.filter_by(status="open").count()

    elif role == MANAGER:
        report_ids = [u.id for u in User.query.filter_by(manager_id=user_id).all()]
        data["team_size"] = len(report_ids)
        data["team_present_today"] = Attendance.query.filter(
            Attendance.user_id.in_(report_ids), Attendance.work_date == today, Attendance.status == "present"
        ).count()
        data["pending_approvals"] = LeaveRequest.query.filter(
            LeaveRequest.user_id.in_(report_ids), LeaveRequest.status == "pending"
        ).count()

    elif role == FINANCE_ACCOUNTS:
        data["payslips_this_month"] = Payslip.query.filter_by(
            month=today.month, year=today.year
        ).count()
        data["pending_payout"] = Payslip.query.filter_by(status="processed").count()

    elif role == HR_RECRUITER:
        data["open_positions"] = JobPosting.query.filter_by(status="open").count()
        data["active_candidates"] = Candidate.query.filter(
            Candidate.stage.notin_(["hired", "rejected"])
        ).count()
        data["hired_this_month"] = Candidate.query.filter(
            Candidate.stage == "hired",
            db.extract("month", Candidate.created_at) == today.month,
        ).count()

    elif role == OPERATIONS:
        data["headcount"] = User.query.filter_by(is_active=True).count()
        data["present_today"] = Attendance.query.filter_by(work_date=today, status="present").count()

    else:  # EMPLOYEE, CONTRACT_EMPLOYEE
        my_record = Attendance.query.filter_by(user_id=user_id, work_date=today).first()
        data["clocked_in"] = bool(my_record and my_record.clock_in and not my_record.clock_out)
        pending = LeaveRequest.query.filter_by(user_id=user_id, status="pending").count()
        data["pending_leave_requests"] = pending

    data["recent_announcements"] = [
        a.to_dict() for a in Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    ]
    return jsonify(data)


@bp.get("/recruiter-performance/<int:recruiter_id>")
@jwt_required()
def recruiter_performance(recruiter_id):
    """Combines recruitment activity (from the candidate audit trail) with the
    recruiter's existing attendance record — Section 19 of the Recruiter
    Specification. Visible to Manager and Admin only."""
    from app.models import CandidateAuditLog, Candidate, User as UserModel
    claims = get_jwt()
    role = claims.get("role")
    if role not in (MANAGER, HR_OPERATIONS):
        return jsonify({"message": "You do not have permission to view this."}), 403

    recruiter = UserModel.query.get_or_404(recruiter_id)
    today = date.today()
    month_start = today.replace(day=1)

    candidates_added = Candidate.query.filter_by(added_by=recruiter_id).count()
    interviews_scheduled = CandidateAuditLog.query.filter_by(
        actor_id=recruiter_id, action="interview_scheduled"
    ).count()
    verifications_done = CandidateAuditLog.query.filter_by(
        actor_id=recruiter_id, action="verified"
    ).count()
    hired_count = Candidate.query.filter_by(added_by=recruiter_id, stage="hired").count()
    conversion_rate = round((hired_count / candidates_added) * 100, 1) if candidates_added else 0

    attendance_this_month = Attendance.query.filter(
        Attendance.user_id == recruiter_id,
        Attendance.work_date >= month_start,
        Attendance.status.in_(["present", "half_day", "regularized"]),
    ).count()

    return jsonify({
        "recruiter": recruiter.to_dict(),
        "candidates_added": candidates_added,
        "interviews_scheduled": interviews_scheduled,
        "verifications_done": verifications_done,
        "hired_count": hired_count,
        "conversion_rate_pct": conversion_rate,
        "attendance_present_days_this_month": attendance_this_month,
    })
