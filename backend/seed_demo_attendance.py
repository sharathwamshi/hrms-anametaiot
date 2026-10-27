"""Explicit, local-development-only seed for clearly marked demo attendance.

Set HRMS_DEMO_ATTENDANCE_DEV=1 before running. The script never updates existing
users or attendance rows; it creates dedicated DEMO-* accounts and only fills
dates that do not already have an attendance record.
"""
from datetime import date, datetime, time, timedelta, timezone
import os
import secrets
from zoneinfo import ZoneInfo

from app import create_app
from app.extensions import db
from app.models import Attendance, Department, Holiday, User
from app.roles import EMPLOYEE, MANAGER
from app.utils.company_time import company_today

DEMO_MARKER = "[HRMS_DEMO_ATTENDANCE:v1]"
DEMO_EMPLOYEES = (
    ("DEMO-2001", "Maya Chen", "Development"),
    ("DEMO-2002", "Noah Williams", "Development"),
    ("DEMO-2003", "Aisha Patel", "Design"),
    ("DEMO-2004", "Lucas Martin", "QA"),
    ("DEMO-2005", "Sofia Garcia", "Backend"),
    ("DEMO-2006", "Ethan Brooks", "Backend"),
    ("DEMO-2007", "Isabella Kim", "Frontend"),
    ("DEMO-2008", "Oliver Singh", "Frontend"),
    ("DEMO-2009", "Amara Okafor", "HR"),
    ("DEMO-2010", "Daniel Costa", "QA"),
)
FIXED_DEMO_HOLIDAYS = {(1, 26), (8, 15), (10, 2), (12, 25)}


def _require_local_development(app):
    if os.environ.get("HRMS_DEMO_ATTENDANCE_DEV") != "1":
        raise RuntimeError("Set HRMS_DEMO_ATTENDANCE_DEV=1 to enable this development-only script.")
    if app.config.get("DB_HOST", "").lower() not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("Demo attendance scripts are restricted to a local database host.")
    if app.config.get("DB_NAME") != "anametaiot_hrms":
        raise RuntimeError("Demo attendance scripts only run against anametaiot_hrms.")


def _utc_naive(work_date, hour, minute, timezone_name):
    local = datetime.combine(work_date, time(hour, minute), tzinfo=ZoneInfo(timezone_name))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def run():
    app = create_app()
    _require_local_development(app)

    with app.app_context():
        db.create_all()
        manager = User.query.filter_by(role=MANAGER, is_active=True).order_by(User.id.asc()).first()
        if not manager:
            raise RuntimeError("Create or seed a Manager account before adding demo attendance.")

        departments = {}
        for _code, _name, department_name in DEMO_EMPLOYEES:
            department = Department.query.filter_by(name=department_name).first()
            if not department:
                department = Department(name=department_name)
                db.session.add(department)
                db.session.flush()
            departments[department_name] = department

        employees = []
        for code, name, department_name in DEMO_EMPLOYEES:
            email = f"{code.lower()}@example.invalid"
            by_code = User.query.filter_by(employee_code=code).first()
            by_email = User.query.filter_by(email=email).first()
            if by_code and by_code.email != email:
                raise RuntimeError(f"{code} already belongs to a different account; no records were changed.")
            if by_email and by_email.employee_code != code:
                raise RuntimeError(f"{email} already belongs to a different account; no records were changed.")

            employee = by_code or by_email
            if employee is None:
                employee = User(
                    employee_code=code,
                    full_name=name,
                    email=email,
                    role=EMPLOYEE,
                    designation=f"{department_name} Demo Employee",
                    department_id=departments[department_name].id,
                    manager_id=manager.id,
                    date_of_joining=date(2024, 1, 15),
                )
                employee.set_password(secrets.token_urlsafe(32))
                db.session.add(employee)
                db.session.flush()
            employees.append(employee)
        db.session.commit()

        today = company_today()
        start = today - timedelta(days=89)
        timezone_name = app.config.get("COMPANY_TIMEZONE", "Asia/Kolkata")
        existing_holidays = {
            holiday.holiday_date
            for holiday in Holiday.query.filter(
                Holiday.holiday_date >= start, Holiday.holiday_date <= today
            ).all()
        }
        existing = {
            (record.user_id, record.work_date)
            for record in Attendance.query.filter(
                Attendance.user_id.in_([employee.id for employee in employees]),
                Attendance.work_date >= start,
                Attendance.work_date <= today,
            ).all()
        }
        created = 0

        for offset in range(90):
            work_date = start + timedelta(days=offset)
            is_holiday = (
                work_date.weekday() >= 5
                or work_date in existing_holidays
                or (work_date.month, work_date.day) in FIXED_DEMO_HOLIDAYS
            )
            ordinal = work_date.toordinal()

            for index, employee in enumerate(employees):
                if (employee.id, work_date) in existing:
                    continue
                if is_holiday:
                    record = Attendance(
                        user_id=employee.id,
                        work_date=work_date,
                        status="holiday",
                        clock_in_note=DEMO_MARKER,
                        clock_out_note=DEMO_MARKER,
                    )
                elif (ordinal + index * 5) % 19 == 0:
                    record = Attendance(
                        user_id=employee.id,
                        work_date=work_date,
                        status="absent",
                        clock_in_note=DEMO_MARKER,
                        clock_out_note=DEMO_MARKER,
                    )
                else:
                    check_in_minutes = 9 * 60 + 10 + ((ordinal * 3 + index * 7) % 41)
                    check_out_minutes = 18 * 60 + 15 + ((ordinal * 5 + index * 11) % 46)
                    record = Attendance(
                        user_id=employee.id,
                        work_date=work_date,
                        clock_in=_utc_naive(
                            work_date, check_in_minutes // 60, check_in_minutes % 60, timezone_name
                        ),
                        clock_out=_utc_naive(
                            work_date, check_out_minutes // 60, check_out_minutes % 60, timezone_name
                        ),
                        status="present",
                        total_hours=round((check_out_minutes - check_in_minutes) / 60, 2),
                        clock_in_note=DEMO_MARKER,
                        clock_out_note=DEMO_MARKER,
                    )
                db.session.add(record)
                existing.add((employee.id, work_date))
                created += 1

        db.session.commit()
        print(f"Demo accounts available: {len(employees)} (codes DEMO-2001 through DEMO-2010).")
        print(f"Created {created} marked attendance rows; existing records were left unchanged.")


if __name__ == "__main__":
    run()
