import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { DESIGNATION_OPTIONS } from "../src/config/employeeOptions.js";
import { ROLE_LABELS, ROLES } from "../src/config/roles.js";

const employeeForm = readFileSync(new URL("../src/pages/Employees.jsx", import.meta.url), "utf8");
const employeeDetail = readFileSync(new URL("../src/components/EmployeeDetailModal.jsx", import.meta.url), "utf8");

test("role labels include requested roles and retain current HRMS roles", () => {
  const expectedRoles = {
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
  };

  for (const [key, label] of Object.entries(expectedRoles)) {
    assert.equal(ROLE_LABELS[ROLES[key]], label);
  }
});

test("designation suggestions include all requested titles", () => {
  assert.deepEqual(DESIGNATION_OPTIONS, [
    "HR Executive",
    "HR Manager",
    "HR Recruiter",
    "Senior HR Recruiter",
    "Talent Acquisition Specialist",
    "HR Generalist",
    "HR Operations Executive",
    "Payroll Executive",
    "HR Team Lead",
    "Assistant HR Manager",
    "Head of HR",
    "HR Intern",
  ]);
});

test("creation and editing keep system role separate from free-text designation", () => {
  for (const source of [employeeForm, employeeDetail]) {
    assert.match(source, /Role \(system access\)/);
    assert.match(source, /Designation \(job title\)/);
    assert.match(source, /DESIGNATION_OPTIONS\.map/);
    assert.match(source, /list="(?:new|edit)-employee-designation-options"/);
  }
});
