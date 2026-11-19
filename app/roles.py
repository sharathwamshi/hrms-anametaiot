"""
Canonical role list for the platform. Kept as plain string constants (rather
than an editable DB table) so RBAC checks in code stay simple and predictable.
"""

MANAGER = "manager"
CONTRACT_EMPLOYEE = "contract_employee"
HR_OPERATIONS = "hr_operations"
FINANCE_ACCOUNTS = "finance_accounts"
OPERATIONS = "operations"
HR_RECRUITER = "hr_recruiter"
EMPLOYEE = "employee"
# Owns the organisation-wide setup (office geofences) and sees/acts on everything the
# Manager, HR Operations and Operations roles can, for attendance.
SUPER_ADMIN = "super_admin"
ADMIN = "admin"
TEAM_LEAD = "team_lead"
DEVELOPER = "developer"
TESTER_QA = "tester_qa"
SCRUM_MASTER = "scrum_master"
BUSINESS_ANALYST = "business_analyst"
HR = "hr"
HR_EXECUTIVE = "hr_executive"

ALL_ROLES = [
    MANAGER,
    CONTRACT_EMPLOYEE,
    HR_OPERATIONS,
    FINANCE_ACCOUNTS,
    OPERATIONS,
    HR_RECRUITER,
    EMPLOYEE,
    SUPER_ADMIN,
    ADMIN,
    TEAM_LEAD,
    DEVELOPER,
    TESTER_QA,
    SCRUM_MASTER,
    BUSINESS_ANALYST,
    HR,
    HR_EXECUTIVE,
]

ROLE_LABELS = {
    SUPER_ADMIN: "Super Admin",
    ADMIN: "Admin",
    MANAGER: "Manager",
    TEAM_LEAD: "Team Lead",
    DEVELOPER: "Developer",
    TESTER_QA: "Tester / QA",
    SCRUM_MASTER: "Scrum Master",
    BUSINESS_ANALYST: "Business Analyst",
    HR: "HR",
    HR_RECRUITER: "HR Recruiter",
    HR_EXECUTIVE: "HR Executive",
    EMPLOYEE: "Employee",
    CONTRACT_EMPLOYEE: "Contract Employee",
    HR_OPERATIONS: "HR Operations",
    FINANCE_ACCOUNTS: "Finance & Accounts",
    OPERATIONS: "Operations",
}

# Contract employees are engaged on a fixed deliverable/timesheet basis and do
# not use the biometric-style clock in/out flow that regular staff use.
# Keep clock eligibility explicit so adding a recognized role does not grant attendance access.
ROLES_WITH_CLOCK_IN_OUT = [
    MANAGER,
    HR_OPERATIONS,
    FINANCE_ACCOUNTS,
    OPERATIONS,
    HR_RECRUITER,
    EMPLOYEE,
    SUPER_ADMIN,
]

# Roles that can approve leave / attendance regularization requests raised by
# an Employee or Contract Employee reporting to them.
APPROVER_ROLES = [MANAGER, HR_OPERATIONS, SUPER_ADMIN]

# Roles that can access org-wide admin surfaces (employee CRUD, role
# assignment, policy configuration).
ADMIN_ROLES = [HR_OPERATIONS, SUPER_ADMIN]

# Payroll reads and payroll changes are intentionally separate capabilities.
PAYROLL_VIEW_ROLES = [
    FINANCE_ACCOUNTS, MANAGER, CONTRACT_EMPLOYEE, HR_OPERATIONS,
    OPERATIONS, HR_RECRUITER,
]
PAYROLL_EDIT_ROLES = [FINANCE_ACCOUNTS]
PAYROLL_ROLES = PAYROLL_VIEW_ROLES
INSURANCE_MANAGEMENT_ROLES = [MANAGER, HR_OPERATIONS, FINANCE_ACCOUNTS, SUPER_ADMIN]

# Roles that manage recruitment pipeline.
RECRUITMENT_ROLES = [HR_RECRUITER, HR_OPERATIONS]

# Roles that manage vendor agreements, hires, and invoices day-to-day.
VENDOR_CREATE_ROLES = [FINANCE_ACCOUNTS, HR_OPERATIONS, OPERATIONS]
VENDOR_MANAGEMENT_ROLES = [FINANCE_ACCOUNTS, HR_OPERATIONS, OPERATIONS]
VENDOR_VIEW_ROLES = [FINANCE_ACCOUNTS, HR_OPERATIONS, MANAGER, OPERATIONS]
VENDOR_EDIT_ROLES = [HR_OPERATIONS]
# Who may see the in-house recruiter overview (Finance needs it for payroll/incentive
# attribution; a Manager only ever sees their own direct reports).
RECRUITER_OVERVIEW_ROLES = [FINANCE_ACCOUNTS, HR_OPERATIONS, MANAGER]

# Roles that approve a vendor invoice before it's considered official.
VENDOR_APPROVER_ROLES = [MANAGER, HR_OPERATIONS]

# Who sees and may correct EVERY active person's attendance (not just direct reports),
# including exact locations and selfies.
ATTENDANCE_FULL_ACCESS_ROLES = [HR_OPERATIONS, SUPER_ADMIN]
# Who defines office geofences (the places people are expected to punch from).
OFFICE_ADMIN_ROLES = [SUPER_ADMIN]
