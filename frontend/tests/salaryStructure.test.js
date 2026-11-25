import assert from "node:assert/strict";
import test from "node:test";
import {
  annualPercentageFromMonthlyAmount,
  isValidSalaryPercentage,
  monthlyAmountFromAnnualPercentage,
  partitionEmployeesByExistingPayslip,
} from "../src/utils/salaryStructure.js";

test("annual CTC percentages convert to rounded monthly rupee amounts", () => {
  assert.equal(monthlyAmountFromAnnualPercentage(720000, 50), 30000);
  assert.equal(monthlyAmountFromAnnualPercentage(720000, 10), 6000);
  assert.equal(monthlyAmountFromAnnualPercentage(725000, 7.25), 4380.21);
});

test("saved monthly amounts can be reopened as their original annual CTC percentages", () => {
  assert.equal(annualPercentageFromMonthlyAmount(30000, 720000), 50);
  assert.equal(annualPercentageFromMonthlyAmount(6000, 720000), 10);
  assert.equal(annualPercentageFromMonthlyAmount(500, 0), 0);
});

test("salary percentage validation rejects values outside the supported range", () => {
  assert.equal(isValidSalaryPercentage(0), true);
  assert.equal(isValidSalaryPercentage(100), true);
  assert.equal(isValidSalaryPercentage(-0.1), false);
  assert.equal(isValidSalaryPercentage(100.01), false);
  assert.equal(isValidSalaryPercentage("not a number"), false);
});

test("existing payslips are skipped without blocking other selected employees", () => {
  const result = partitionEmployeesByExistingPayslip(
    [1, 2, 3],
    [
      { id: 1, full_name: "Existing Slip", payslip_id: 10 },
      { id: 2, full_name: "No Slip", payslip_id: null },
    ],
  );
  assert.deepEqual(result.employeesWithPayslips.map((person) => person.id), [1]);
  assert.deepEqual(result.employeeIdsToGenerate, [2, 3]);
});
