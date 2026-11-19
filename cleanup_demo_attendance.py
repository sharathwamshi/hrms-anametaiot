"""Safely remove only marked demo attendance rows and deactivate demo accounts.

Requires HRMS_DEMO_ATTENDANCE_DEV=1 and an explicit --confirm-demo-attendance-delete.
"""
import os
import sys

from app import create_app
from app.extensions import db
from app.models import Attendance, User
from seed_demo_attendance import DEMO_MARKER, _require_local_development


def run():
    if sys.argv[1:] != ["--confirm-demo-attendance-delete"]:
        raise RuntimeError(
            "Pass --confirm-demo-attendance-delete to remove marked demo attendance."
        )
    app = create_app()
    _require_local_development(app)
    if os.environ.get("HRMS_DEMO_ATTENDANCE_DEV") != "1":
        raise RuntimeError("Set HRMS_DEMO_ATTENDANCE_DEV=1 before cleanup.")

    with app.app_context():
        demo_users = User.query.filter(
            User.employee_code.like("DEMO-%"),
            User.email.like("%@example.invalid"),
        ).all()
        demo_ids = {user.id for user in demo_users}
        rows = (
            Attendance.query.filter(Attendance.user_id.in_(demo_ids or {0}))
            .all()
        )
        marked_rows = [
            row for row in rows
            if row.clock_in_note == DEMO_MARKER and row.clock_out_note == DEMO_MARKER
        ]
        marked_user_ids = {row.user_id for row in marked_rows}
        for row in marked_rows:
            db.session.delete(row)
        for user in demo_users:
            if user.id in marked_user_ids:
                user.is_active = False
        db.session.commit()
        print(
            f"Deleted {len(marked_rows)} attendance rows carrying the exact demo marker; "
            f"deactivated {len(marked_user_ids)} dedicated demo accounts. No other records were changed."
        )


if __name__ == "__main__":
    run()
