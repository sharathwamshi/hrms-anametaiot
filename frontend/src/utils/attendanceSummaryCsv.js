import {
  attendanceMetrics,
  formatMinutes,
  formatPercent,
} from "./attendanceDashboard.js";

export const ATTENDANCE_SUMMARY_HEADERS = [
  "Employee ID",
  "Employee Name",
  "Department",
  "Total Working Days",
  "Days Present",
  "Average Check-In",
  "Average Check-Out",
  "On-Time Check-In %",
  "On-Time Check-Out %",
  "Attendance %",
];

function csvCell(value) {
  let text = value === null || value === undefined ? "" : String(value);
  if (/^[\s]*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

export function buildAttendanceSummaryCsv(employees, dates, holidays, policy, range) {
  const rows = employees.map((employee) => {
    const metrics = attendanceMetrics([employee], dates, holidays, policy);
    const present = (value) => value === "—" ? "" : value;
    return [
      employee.employee_code || employee.id,
      employee.full_name || "",
      employee.department || "Unassigned",
      metrics.eligibleDays,
      metrics.presentDays,
      present(formatMinutes(metrics.averageCheckIn)),
      present(formatMinutes(metrics.averageCheckOut)),
      present(formatPercent(metrics.onTimeCheckInPct)),
      present(formatPercent(metrics.onTimeCheckOutPct)),
      present(formatPercent(metrics.attendancePct)),
    ];
  });
  const data = [
    ["Report Period", `${range.from} to ${range.to}`],
    ATTENDANCE_SUMMARY_HEADERS,
    ...rows,
  ];
  return `\uFEFF${data.map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
}
