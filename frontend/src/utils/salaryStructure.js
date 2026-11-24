export function monthlyAmountFromAnnualPercentage(annualCtc, percentage) {
  const ctc = Number(annualCtc);
  const rate = Number(percentage);
  if (!Number.isFinite(ctc) || !Number.isFinite(rate) || ctc < 0 || rate < 0) return 0;
  return Math.round((ctc * rate / 1200 + Number.EPSILON) * 100) / 100;
}

export function annualPercentageFromMonthlyAmount(monthlyAmount, annualCtc) {
  const amount = Number(monthlyAmount);
  const ctc = Number(annualCtc);
  if (!Number.isFinite(amount) || !Number.isFinite(ctc) || amount < 0 || ctc <= 0) return 0;
  return Math.round((amount * 1200 / ctc + Number.EPSILON) * 100) / 100;
}

export function isValidSalaryPercentage(value) {
  const percentage = Number(value);
  return Number.isFinite(percentage) && percentage >= 0 && percentage <= 100;
}

export function partitionEmployeesByExistingPayslip(employeeIds, coveragePeople) {
  const peopleById = new Map(coveragePeople.map((person) => [person.id, person]));
  const employeesWithPayslips = employeeIds
    .map((id) => peopleById.get(id))
    .filter((employee) => employee?.payslip_id);
  const employeeIdsToGenerate = employeeIds.filter(
    (id) => !peopleById.get(id)?.payslip_id,
  );
  return { employeesWithPayslips, employeeIdsToGenerate };
}
