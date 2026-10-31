
export const ROLES = {
  SUPER_ADMIN: "super_admin",
  ADMIN: "admin",
  MANAGER: "manager",
  TEAM_LEAD: "team_lead",
  DEVELOPER: "developer",
  TESTER_QA: "tester_qa",
  SCRUM_MASTER: "scrum_master",
  BUSINESS_ANALYST: "business_analyst",
  HR: "hr",
  HR_EXECUTIVE: "hr_executive",
  HR_RECRUITER: "hr_recruiter",
  EMPLOYEE: "employee",
  CONTRACT_EMPLOYEE: "contract_employee",
  HR_OPERATIONS: "hr_operations",
  FINANCE_ACCOUNTS: "finance_accounts",
  OPERATIONS: "operations",
};

export const ROLE_LABELS = {
  [ROLES.SUPER_ADMIN]: "Super Admin",
  [ROLES.ADMIN]: "Admin",
  [ROLES.MANAGER]: "Manager",
  [ROLES.TEAM_LEAD]: "Team Lead",
  [ROLES.DEVELOPER]: "Developer",
  [ROLES.TESTER_QA]: "Tester / QA",
  [ROLES.SCRUM_MASTER]: "Scrum Master",
  [ROLES.BUSINESS_ANALYST]: "Business Analyst",
  [ROLES.HR]: "HR",
  [ROLES.HR_RECRUITER]: "HR Recruiter",
  [ROLES.HR_EXECUTIVE]: "HR Executive",
  [ROLES.EMPLOYEE]: "Employee",
  [ROLES.CONTRACT_EMPLOYEE]: "Contract Employee",
  [ROLES.HR_OPERATIONS]: "HR Operations",
  [ROLES.FINANCE_ACCOUNTS]: "Finance & Accounts",
  [ROLES.OPERATIONS]: "Operations",
};

// Which nav items each role sees. Every role gets Dashboard + Profile.
export const NAV_BY_ROLE = {
  [ROLES.SUPER_ADMIN]: [
    "dashboard", "employees", "attendance", "leave", "assets", "insurance", "profile",
  ],
  [ROLES.HR_OPERATIONS]: [
    "dashboard", "employees", "attendance", "leave", "payroll", "recruitment",
    "allCandidates", "recruiters", "vendors", "allPlacements", "announcements",
    "assets", "insurance", "profile",
  ],
  [ROLES.MANAGER]: [
    "dashboard", "employees", "attendance", "leave", "reports", "payroll", "recruitment",
    "allCandidates", "recruiters", "vendors", "allPlacements", "insurance", "profile",
  ],
  [ROLES.FINANCE_ACCOUNTS]: [
    "dashboard", "attendance", "leave", "payroll", "payslipManagement", "allCandidates", "recruiters",
    "vendors", "allPlacements", "insurance", "profile",
  ],
  [ROLES.OPERATIONS]: [
    "dashboard", "attendance", "assets", "employees", "vendors", "payroll", "profile",
  ],
  [ROLES.HR_RECRUITER]: [
    "dashboard", "attendance", "leave", "payroll", "recruitment", "allCandidates", "profile",
  ],
  [ROLES.EMPLOYEE]: [
    "home", "myAttendance", "leave", "payslips", "insurance", "profile",
  ],
  [ROLES.CONTRACT_EMPLOYEE]: [
    "dashboard", "payroll", "insurance", "profile",
  ],
};

export const NAV_ITEMS = {
  dashboard: { path: "/", label: "Dashboard", icon: "\u25A6" },
  home: { path: "/", label: "Home", icon: "\u25A6" },
  employees: { path: "/employees", label: "Employees", icon: "\u25A5" },
  attendance: { path: "/attendance", label: "Attendance", icon: "\u23F1" },
  myAttendance: { path: "/attendance", label: "My Attendance", icon: "\u23F1" },
  team: { path: "/attendance?tab=team", label: "Team", icon: "\u25A5" },
  reports: { path: "/attendance?tab=reports", label: "Reports", icon: "\u25A4" },
  leave: { path: "/leave", label: "Leave", icon: "\u2708" },
  payroll: { path: "/payroll", label: "Payroll", icon: "\u20B9" },
  payslipManagement: { path: "/payroll/manage", label: "Payslip Management", icon: "\u20B9" },
  payslips: { path: "/payroll", label: "Payslips", icon: "\u20B9" },
  insurance: { path: "/insurance", label: "Insurance", icon: "\u2665" },
  recruitment: { path: "/recruitment", label: "Recruitment", icon: "\u2605" },
  allCandidates: { path: "/all-candidates", label: "All Candidates", icon: "\u25A4" },
  recruiters: { path: "/recruiters", label: "Recruiters", icon: "\u2691" },
  allPlacements: { path: "/all-placements", label: "All Placements", icon: "\u{1F517}" },
  vendors: { path: "/vendors", label: "Vendors", icon: "\u{1F3E2}" },
  announcements: { path: "/announcements", label: "Announcements", icon: "\u266A" },
  assets: { path: "/assets", label: "Assets", icon: "\u2726" },
  profile: { path: "/profile", label: "My Profile", icon: "\u25CF" },
};
