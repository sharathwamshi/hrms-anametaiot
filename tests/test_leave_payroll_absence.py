import sys
sys.path.insert(0, ".")

from datetime import date

from config import Config


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


from app import create_app
from app.extensions import db
from app.models import Attendance, LeaveRequest, LeaveType, User
from app.routes.payroll import _attendance_for_period
from app.roles import EMPLOYEE


app = create_app(TestConfig)

with app.app_context():
    db.create_all()
    casual = LeaveType(name="Casual Leave", annual_quota=0)
    sick = LeaveType(name="Sick Leave", annual_quota=0)
    paid = LeaveType(name="Paid Leave", annual_quota=6)
    db.session.add_all((casual, sick, paid))
    db.session.flush()

    def make_employee(code):
        user = User(
            employee_code=code,
            full_name=code,
            email=f"{code.lower()}@example.com",
            role=EMPLOYEE,
        )
        user.set_password("test-password")
        db.session.add(user)
        db.session.flush()
        return user

    def create_case(code, leave_type, day, duration="full_day", classification=None, present_on_leave=False):
        user = make_employee(code)
        for day_of_month in range(1, 31):
            db.session.add(Attendance(
                user_id=user.id,
                work_date=date(2026, 6, day_of_month),
                status=(
                    "present"
                    if day_of_month != day or present_on_leave
                    else "absent"
                ),
            ))
        db.session.add(LeaveRequest(
            user_id=user.id,
            leave_type_id=leave_type.id,
            start_date=date(2026, 6, day),
            end_date=date(2026, 6, day),
            days=0.5 if duration != "full_day" else 1,
            duration=duration,
            final_classification=classification,
            status="approved",
            reason="Payroll leave test",
        ))
        db.session.flush()
        return _attendance_for_period(user.id, 6, 2026)

    full_casual = create_case("FULL-CL", casual, 1)
    half_casual = create_case("HALF-CL", casual, 2, duration="first_half")
    casual_on_present_day = create_case("PRESENT-CL", casual, 3, present_on_leave=True)
    sick_as_casual = create_case("SICK-CL", sick, 4, classification="casual")
    sick_as_paid = create_case("SICK-PL", sick, 5, classification="paid")

    assert full_casual["lop_days"] == 1, full_casual
    assert half_casual["lop_days"] == 0.5, half_casual
    assert casual_on_present_day["lop_days"] == 1, casual_on_present_day
    assert sick_as_casual["lop_days"] == 1, sick_as_casual
    assert sick_as_paid["lop_days"] == 0, sick_as_paid

print("ALL LEAVE PAYROLL ABSENCE TESTS PASSED")
