export const ROLES = {
  MANAGER: "manager",
  CONTRACT_EMPLOYEE: "contract_employee",
  HR_OPERATIONS: "hr_operations",
  FINANCE_ACCOUNTS: "finance_accounts",
  OPERATIONS: "operations",
  HR_RECRUITER: "hr_recruiter",
  EMPLOYEE: "employee",
};

export const ROLE_LABELS = {
  [ROLES.MANAGER]: "Manager",
  [ROLES.CONTRACT_EMPLOYEE]: "Contract Employee",
  [ROLES.HR_OPERATIONS]: "HR Operations",
  [ROLES.FINANCE_ACCOUNTS]: "Finance & Accounts",
  [ROLES.OPERATIONS]: "Operations",
  [ROLES.HR_RECRUITER]: "HR Recruiter",
  [ROLES.EMPLOYEE]: "Employee",
};

// Which nav items each role sees. Every role gets Dashboard + Profile.
export const NAV_BY_ROLE = {
  [ROLES.HR_OPERATIONS]: ["dashboard", "employees", "attendance", "leave", "payroll", "recruitment", "allCandidates", "vendors", "allPlacements", "announcements", "assets", "documents", "profile"],
  [ROLES.MANAGER]: ["dashboard", "attendance", "leave", "employees", "recruitment", "allCandidates", "vendors", "allPlacements", "documents", "profile"],
  [ROLES.FINANCE_ACCOUNTS]: ["dashboard", "payroll", "vendors", "allPlacements", "documents", "profile"],
  [ROLES.OPERATIONS]: ["dashboard", "attendance", "assets", "employees", "documents", "profile"],
  [ROLES.HR_RECRUITER]: ["dashboard", "recruitment", "allCandidates", "documents", "profile"],
  [ROLES.EMPLOYEE]: ["dashboard", "attendance", "leave", "payroll", "documents", "profile"],
  [ROLES.CONTRACT_EMPLOYEE]: ["dashboard", "documents", "payroll", "profile"],
};

export const NAV_ITEMS = {
  dashboard: { path: "/", label: "Dashboard", icon: "\u25A6" },
  employees: { path: "/employees", label: "Employees", icon: "\u25A5" },
  attendance: { path: "/attendance", label: "Attendance", icon: "\u23F1" },
  leave: { path: "/leave", label: "Leave", icon: "\u2708" },
  payroll: { path: "/payroll", label: "Payroll", icon: "\u20B9" },
  recruitment: { path: "/recruitment", label: "Recruitment", icon: "\u2605" },
  allCandidates: { path: "/all-candidates", label: "All Candidates", icon: "\u25A4" },
  allPlacements: { path: "/all-placements", label: "All Placements", icon: "\u{1F517}" },
  vendors: { path: "/vendors", label: "Vendors", icon: "\u{1F3E2}" },
  announcements: { path: "/announcements", label: "Announcements", icon: "\u266A" },
  assets: { path: "/assets", label: "Assets", icon: "\u2726" },
  documents: { path: "/documents", label: "Documents", icon: "\u{1F4C4}" },
  profile: { path: "/profile", label: "My Profile", icon: "\u25CF" },
};
