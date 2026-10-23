"""
Run once after configuring .env and creating the MySQL database:

    python seed.py

Creates all tables (if schema.sql wasn't imported separately), a set of
departments, standard leave types, and one demo login per role so every
role's dashboard can be tested immediately.
"""
from datetime import date
import json
from app import create_app
from app.extensions import db
from app.models import User, Department, LeaveType, LeaveBalance, TopicLibrary, MockTestTemplate, MockTestQuestion, CompanySettings, SalaryTemplate, JobPosting, Candidate, OfficeLocation, WorkLocation
from app.roles import (
    MANAGER, CONTRACT_EMPLOYEE, HR_OPERATIONS, FINANCE_ACCOUNTS,
    OPERATIONS, HR_RECRUITER, EMPLOYEE,
)
from seed_data.java_questions import JAVA_QUESTIONS

app = create_app()

DEMO_PASSWORD = "Welcome@123"

DEPARTMENTS = ["Engineering", "Human Resources", "Finance", "Operations", "Sales & Marketing"]

LEAVE_TYPES = [
    ("Casual Leave", 12),
    ("Sick Leave", 8),
    ("Earned Leave", 15),
]

MOCK_TEST_TOPICS = [
    "Java", "Python", "SQL", "Data Structures & Algorithms",
    "Communication", "Aptitude", "System Design",
]

DEMO_USERS = [
    ("EMP-1001", "Ananya Rao", "manager@anametaiot.com", MANAGER, "Engineering Manager"),
    ("EMP-1002", "Vikram Shetty", "contract@anametaiot.com", CONTRACT_EMPLOYEE, "Contract Developer"),
    ("EMP-1003", "Priya Nair", "hrops@anametaiot.com", HR_OPERATIONS, "HR Operations Lead"),
    ("EMP-1004", "Rahul Menon", "finance@anametaiot.com", FINANCE_ACCOUNTS, "Finance & Accounts Executive"),
    ("EMP-1005", "Karthik Iyer", "operations@anametaiot.com", OPERATIONS, "Operations Executive"),
    ("EMP-1006", "Sneha Kulkarni", "recruiter@anametaiot.com", HR_RECRUITER, "HR Recruiter"),
    ("EMP-1007", "Arjun Das", "employee@anametaiot.com", EMPLOYEE, "Software Engineer"),
]


def run():
    with app.app_context():
        db.create_all()

        default_work_location = WorkLocation.query.filter_by(is_default=True, is_active=True).first()
        if not default_work_location:
            office = OfficeLocation.query.filter_by(is_active=True).order_by(OfficeLocation.id.asc()).first()
            office_name = office.name.strip() if office and office.name.strip() else "Main Office"
            default_work_location = WorkLocation.query.filter_by(name=office_name).first()
            if default_work_location:
                default_work_location.is_active = True
                default_work_location.is_default = True
            else:
                db.session.add(WorkLocation(name=office_name, is_active=True, is_default=True))
        home_location = WorkLocation.query.filter_by(name="Work From Home").first()
        if not home_location:
            db.session.add(WorkLocation(name="Work From Home", is_active=True, is_default=False))
        db.session.commit()

        dept_map = {}
        for name in DEPARTMENTS:
            dept = Department.query.filter_by(name=name).first()
            if not dept:
                dept = Department(name=name)
                db.session.add(dept)
                db.session.flush()
            dept_map[name] = dept

        for name, quota in LEAVE_TYPES:
            if not LeaveType.query.filter_by(name=name).first():
                db.session.add(LeaveType(name=name, annual_quota=quota))

        for name in MOCK_TEST_TOPICS:
            if not TopicLibrary.query.filter_by(name=name).first():
                db.session.add(TopicLibrary(name=name))
        db.session.commit()

        if not CompanySettings.query.first():
            db.session.add(CompanySettings(
                company_name="AnametaIOT Pvt Ltd",
                address="Bengaluru, Karnataka, India",
                state="Karnataka",
            ))
            db.session.commit()

        if not SalaryTemplate.query.filter_by(name="Standard Employee").first():
            db.session.add(SalaryTemplate(
                name="Standard Employee",
                description="Default 50/20/20/10 earnings split for regular staff",
                basic_pct=50, hra_pct=20, special_allowance_pct=20, other_allowance_pct=10,
                pf_employee_pct=6, esi_employee_pct=0, professional_tax_flat=200, tds_pct=0,
            ))
            db.session.commit()

        eng = dept_map["Engineering"]
        hr = dept_map["Human Resources"]
        fin = dept_map["Finance"]
        ops = dept_map["Operations"]

        dept_for_role = {
            MANAGER: eng, CONTRACT_EMPLOYEE: eng, HR_OPERATIONS: hr,
            FINANCE_ACCOUNTS: fin, OPERATIONS: ops, HR_RECRUITER: hr, EMPLOYEE: eng,
        }

        created_users = {}
        for code, name, email, role, designation in DEMO_USERS:
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    employee_code=code,
                    full_name=name,
                    email=email,
                    role=role,
                    designation=designation,
                    department_id=dept_for_role[role].id,
                    date_of_joining=date(2024, 1, 15),
                )
                user.set_password(DEMO_PASSWORD)
                db.session.add(user)
                db.session.flush()
            created_users[role] = user
        db.session.commit()

        # Every other demo user reports to the single demo Manager, so the whole
        # org chart is visible under one person for the demo walkthrough.
        for role, user in created_users.items():
            if role != MANAGER:
                user.manager_id = created_users[MANAGER].id
        db.session.commit()

        # Allocate leave balances for the current year for clock-in eligible staff
        year = date.today().year
        leave_types = LeaveType.query.all()
        for user in created_users.values():
            for lt in leave_types:
                if not LeaveBalance.query.filter_by(
                    user_id=user.id, leave_type_id=lt.id, year=year
                ).first():
                    db.session.add(
                        LeaveBalance(user_id=user.id, leave_type_id=lt.id, year=year, allocated=lt.annual_quota)
                    )
        db.session.commit()

        # Ready-to-use Java mock test template so Recruitment has real content
        # on day one (Section 11 of the Recruiter Specification).
        template_title = "Java Fundamentals — 100 Questions"
        if not MockTestTemplate.query.filter_by(title=template_title).first():
            template = MockTestTemplate(
                title=template_title,
                topics="Java, OOP, Collections, Exceptions, Concurrency, Strings, Generics, JVM",
                complexity="medium",
                duration_minutes=60,
                passing_threshold_pct=60,
                created_by=created_users[HR_RECRUITER].id,
            )
            db.session.add(template)
            db.session.flush()
            for question_text, options, correct_answer, topic in JAVA_QUESTIONS:
                db.session.add(MockTestQuestion(
                    template_id=template.id,
                    topic=topic,
                    question_text=question_text,
                    question_type="mcq",
                    options_json=json.dumps(options),
                    correct_answer=correct_answer,
                    marks=1,
                ))
            db.session.commit()
            print(f"Seeded '{template_title}' with {len(JAVA_QUESTIONS)} questions.")

        # A job posting with a defined interview pipeline (levels), approved
        # and open, plus 10 candidates spread across stages and levels so the
        # Candidates tab, the level tracking, and the dashboard widgets all
        # have real data to show immediately.
        job_title = "Backend Engineer"
        job = JobPosting.query.filter_by(title=job_title).first()
        if not job:
            job = JobPosting(
                title=job_title, department_id=eng.id, employment_type="full_time", openings=2,
                description="Build and maintain our core platform services.",
                salary_min=800000, salary_max=1400000, priority="urgent",
                interview_levels="Screening, Tech L1, Tech L2, HR Round, Offer",
                requisition_status="open", status="open",
                created_by=created_users[HR_RECRUITER].id,
                approved_by=created_users[MANAGER].id,
            )
            db.session.add(job)
            db.session.flush()
            print(f"Seeded job posting '{job_title}' with interview levels.")

        CANDIDATE_SEED = [
            # name, email, phone, source, skills, location, relocation, stage, level
            ("Ritika Sharma", "ritika.sharma@example.com", "9845010001", "linkedin",
             "Java, Spring Boot, SQL, Docker", "Bengaluru", False, "interview", "Tech L1"),
            ("Aman Gupta", "aman.gupta@example.com", "9845010002", "referral",
             "Python, Django, AWS", "Hyderabad", True, "screening", "Screening"),
            ("Priyanka Reddy", "priyanka.reddy@example.com", "9845010003", "naukri",
             "Java, Microservices, Kafka", "Bengaluru", False, "interview", "Tech L2"),
            ("Rohan Verma", "rohan.verma@example.com", "9845010004", "walk-in",
             "Node.js, MongoDB", "Pune", True, "applied", None),
            ("Sneha Joshi", "sneha.joshi@example.com", "9845010005", "linkedin",
             "Java, Spring Boot, Kubernetes", "Bengaluru", False, "offer", "HR Round"),
            ("Vivek Nair", "vivek.nair@example.com", "9845010006", "referral",
             "PHP, Laravel", "Chennai", True, "rejected", None),
            ("Kavya Menon", "kavya.menon@example.com", "9845010007", "naukri",
             "Java, SQL, REST APIs", "Bengaluru", False, "mock_test", None),
            ("Arjun Pillai", "arjun.pillai@example.com", "9845010008", "linkedin",
             "Python, FastAPI, PostgreSQL", "Mumbai", True, "interview", "Screening"),
            ("Divya Krishnan", "divya.krishnan@example.com", "9845010009", "referral",
             "Java, Spring Boot, SQL", "Bengaluru", False, "hired", "Offer"),
            ("Sanjay Kumar", "sanjay.kumar@example.com", "9845010010", "naukri",
             "Go, gRPC, Docker", "Bengaluru", True, "screening", None),
        ]
        if Candidate.query.filter_by(job_id=job.id).count() < len(CANDIDATE_SEED):
            for name, email, phone, source, skills, location, relocation, stage, level in CANDIDATE_SEED:
                if Candidate.query.filter_by(email_normalized=email).first():
                    continue
                db.session.add(Candidate(
                    job_id=job.id, full_name=name, email=email, email_normalized=email,
                    phone=phone, phone_normalized=phone, source=source, skills=skills,
                    location=location, open_to_relocation=relocation,
                    stage=stage, current_level=level,
                    validation_status="auto_validated",
                    added_by=created_users[HR_RECRUITER].id, assigned_to=created_users[HR_RECRUITER].id,
                ))
            db.session.commit()
            print(f"Seeded {len(CANDIDATE_SEED)} candidates for '{job_title}'.")

        print("Seed complete. Demo login password for all users:", DEMO_PASSWORD)
        for code, name, email, role, designation in DEMO_USERS:
            print(f"  {role:18s} -> {email}")


if __name__ == "__main__":
    run()
