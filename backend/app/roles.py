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

ALL_ROLES = [
    MANAGER,
    CONTRACT_EMPLOYEE,
    HR_OPERATIONS,
    FINANCE_ACCOUNTS,
    OPERATIONS,
    HR_RECRUITER,
    EMPLOYEE,
    SUPER_ADMIN,
]

ROLE_LABELS = {
    MANAGER: "Manager",
    CONTRACT_EMPLOYEE: "Contract Employee",
    HR_OPERATIONS: "HR Operations",
    FINANCE_ACCOUNTS: "Finance & Accounts",
    OPERATIONS: "Operations",
    HR_RECRUITER: "HR Recruiter",
    EMPLOYEE: "Employee",
    SUPER_ADMIN: "Super Admin",
}

# Contract employees are engaged on a fixed deliverable/timesheet basis and do
# not use the biometric-style clock in/out flow that regular staff use.
ROLES_WITH_CLOCK_IN_OUT = [r for r in ALL_ROLES if r != CONTRACT_EMPLOYEE]

# Roles that can approve leave / attendance regularization requests raised by
# an Employee or Contract Employee reporting to them.
APPROVER_ROLES = [MANAGER, HR_OPERATIONS, SUPER_ADMIN]

# Roles that can access org-wide admin surfaces (employee CRUD, role
# assignment, policy configuration).
ADMIN_ROLES = [HR_OPERATIONS, SUPER_ADMIN]

# Roles that can view/generate payroll data.
PAYROLL_ROLES = [FINANCE_ACCOUNTS, HR_OPERATIONS]

# Roles that manage recruitment pipeline.
RECRUITMENT_ROLES = [HR_RECRUITER, HR_OPERATIONS]

# Roles that manage vendor agreements, hires, and invoices day-to-day.
VENDOR_MANAGEMENT_ROLES = [FINANCE_ACCOUNTS, HR_OPERATIONS]
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
