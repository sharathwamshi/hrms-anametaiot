import assert from "node:assert/strict";
import test from "node:test";
import { NAV_BY_ROLE, NAV_ITEMS, ROLES } from "../src/config/roles.js";

const payslipRoles = [
  ROLES.MANAGER,
  ROLES.CONTRACT_EMPLOYEE,
  ROLES.HR_OPERATIONS,
  ROLES.FINANCE_ACCOUNTS,
  ROLES.OPERATIONS,
  ROLES.HR_RECRUITER,
  ROLES.EMPLOYEE,
];

test("all authorized roles see one Payslips navigation item", () => {
  for (const role of payslipRoles) {
    const navItems = NAV_BY_ROLE[role];
    assert.ok(navItems.includes("payslips"), `${role} should see Payslips`);
    assert.equal(navItems.filter((item) => item === "payslips").length, 1);
    assert.ok(!navItems.includes("payroll"), `${role} should not see a duplicate Payroll item`);
    assert.equal(NAV_ITEMS.payslips.path, "/payroll");
  }
});

test("only Finance & Accounts sees Payslip Management navigation", () => {
  for (const role of payslipRoles) {
    assert.equal(
      NAV_BY_ROLE[role].includes("payslipManagement"),
      role === ROLES.FINANCE_ACCOUNTS,
      `${role} Payslip Management visibility`,
    );
  }
});
