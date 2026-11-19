import test from "node:test";
import assert from "node:assert/strict";
import {
  currentMonthLeaveStart,
  isDisallowedBackdatedLeaveDate,
  isSundayDate,
  leaveDaysByYear,
} from "./attendanceTime.js";

test("Sunday dates are recognized", () => {
  assert.equal(isSundayDate("2026-11-22"), true);
  assert.equal(isSundayDate("2026-11-23"), false);
});

test("current-month leave cutoff handles month, leap-year, and year boundaries", () => {
  assert.equal(currentMonthLeaveStart("2026-11-19"), "2026-11-01");
  assert.equal(currentMonthLeaveStart("2026-03-01"), "2026-03-01");
  assert.equal(currentMonthLeaveStart("2024-02-29"), "2024-02-01");
  assert.equal(currentMonthLeaveStart("2025-01-03"), "2025-01-01");

  assert.equal(isDisallowedBackdatedLeaveDate("2026-10-31", "2026-11-19"), true);
  assert.equal(isDisallowedBackdatedLeaveDate("2026-09-30", "2026-11-19"), true);
  assert.equal(isDisallowedBackdatedLeaveDate("2026-11-01", "2026-11-19"), false);
  assert.equal(isDisallowedBackdatedLeaveDate("2026-11-02", "2026-11-19"), false);
  assert.equal(isDisallowedBackdatedLeaveDate("2026-11-18", "2026-11-19"), false);
  assert.equal(isDisallowedBackdatedLeaveDate("2026-11-19", "2026-11-19"), false);
  assert.equal(isDisallowedBackdatedLeaveDate("2026-11-30", "2026-11-19"), false);
  assert.equal(isDisallowedBackdatedLeaveDate("2025-12-31", "2026-01-03"), true);
  assert.equal(isSundayDate("2026-11-15"), true);
});

test("leave day counts exclude Sundays and split totals by year", () => {
  assert.deepEqual(leaveDaysByYear("2026-11-20", "2026-11-23"), { 2026: 3 });
  assert.deepEqual(leaveDaysByYear("2026-11-22", "2026-11-22"), {});
  assert.deepEqual(leaveDaysByYear("2026-12-31", "2027-01-02"), { 2026: 1, 2027: 2 });
});
