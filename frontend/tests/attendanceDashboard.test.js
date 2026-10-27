import assert from "node:assert/strict";
import test from "node:test";
import {
  attendanceMetrics,
  createDemoEmployees,
  dateKeys,
  dateRange,
  dateRangeError,
} from "../src/utils/attendanceDashboard.js";
import { ATTENDANCE_SUMMARY_HEADERS, buildAttendanceSummaryCsv } from "../src/utils/attendanceSummaryCsv.js";
import { setCompanyTimezone } from "../src/utils/attendanceTime.js";

setCompanyTimezone("Asia/Kolkata");

test("date filters align daily, weekly, and monthly views to selected date", () => {
  const today = "2026-10-24";
  assert.deepEqual(dateRange("daily", today, today), { from: today, to: today });
  assert.deepEqual(dateRange("weekly", today, today), { from: "2026-10-19", to: today });
  assert.deepEqual(dateRange("monthly", today, today), { from: "2026-10-01", to: today });
  assert.equal(dateKeys("2026-10-23", "2026-10-24").length, 2);
});

test("date-range validation rejects incomplete, reversed, invalid, and oversized ranges", () => {
  assert.match(dateRangeError("", "2026-10-24"), /both/);
  assert.match(dateRangeError("2026-10-25", "2026-10-24"), /must not be later/);
  assert.match(dateRangeError("2026-02-30", "2026-03-01"), /valid/);
  assert.match(dateRangeError("2026-01-01", "2026-04-04"), /93 days or less/);
  assert.equal(dateRangeError("2026-10-23", "2026-10-24"), "");
});

test("percentages exclude holidays and approved leave, and missing attendance is not on time", () => {
  const employee = {
    id: 1,
    records: [
      { work_date: "2026-10-19", status: "present", clock_in: "2026-10-19T04:00:00Z", clock_out: "2026-10-19T13:00:00Z", check_in_status: "in_time" },
      { work_date: "2026-10-20", status: "absent", clock_in: null, clock_out: null },
      { work_date: "2026-10-21", status: "holiday", clock_in: null, clock_out: null },
      { work_date: "2026-10-23", status: "present", clock_in: "2026-10-23T04:15:00Z", clock_out: "2026-10-23T12:50:00Z", check_in_status: "late" },
    ],
    approved_leave_dates: ["2026-10-22"],
  };
  const metrics = attendanceMetrics(
    [employee],
    dateKeys("2026-10-19", "2026-10-23"),
    [],
    { official_check_in: "09:30", official_check_out: "18:30", attendance_buffer_minutes: 10 },
    "2026-10-23",
  );

  assert.equal(metrics.eligibleDays, 3);
  assert.equal(metrics.presentDays, 2);
  assert.equal(metrics.absentDays, 1);
  assert.equal(metrics.attendancePct, 67);
  assert.equal(metrics.onTimeCheckInPct, 33);
  assert.equal(metrics.onTimeCheckOutPct, 33);
  assert.equal(metrics.averageCheckIn, 9 * 60 + 37.5);
  assert.equal(metrics.averageCheckOut, 18 * 60 + 25);
});

test("summary CSV uses attendance metrics and safely quotes employee details", () => {
  const employee = {
    id: 1,
    employee_code: "EMP-1",
    full_name: 'Doe, "Jane"',
    department: "Engineering",
    records: [
      { work_date: "2026-10-19", status: "present", clock_in: "2026-10-19T04:00:00Z", clock_out: "2026-10-19T13:00:00Z" },
      { work_date: "2026-10-20", status: "absent" },
    ],
  };
  const csv = buildAttendanceSummaryCsv(
    [employee],
    dateKeys("2026-10-19", "2026-10-20"),
    [],
    { official_check_in: "09:30", official_check_out: "18:30", attendance_buffer_minutes: 10 },
    { from: "2026-10-19", to: "2026-10-20" },
  );

  assert.ok(csv.startsWith("\uFEFF"));
  assert.ok(csv.includes('"Report Period","2026-10-19 to 2026-10-20"'));
  assert.ok(csv.includes(ATTENDANCE_SUMMARY_HEADERS.map((header) => `"${header}"`).join(",")));
  assert.ok(csv.includes('"EMP-1","Doe, ""Jane""","Engineering","2","1","09:30 AM","06:30 PM"'));
});

test("demo data has ten distinct employees and metrics derive from their records", () => {
  const demo = createDemoEmployees("2026-10-19", "2026-10-25");
  assert.equal(demo.employees.length, 10);
  assert.equal(new Set(demo.employees.map((employee) => employee.employee_code)).size, 10);
  assert.ok(demo.employees.every((employee) => employee.is_demo));
  assert.ok(demo.employees.some((employee) => employee.records.some((record) => record.status === "absent")));
  assert.ok(demo.employees.some((employee) => employee.records.some((record) => record.status === "holiday")));
  const metrics = attendanceMetrics(
    demo.employees,
    dateKeys("2026-10-19", "2026-10-23"),
    demo.holidays,
    { official_check_in: "09:30", official_check_out: "18:30", attendance_buffer_minutes: 10 },
    "2026-10-24",
  );
  assert.ok(metrics.attendancePct > 0 && metrics.attendancePct < 100);
});
