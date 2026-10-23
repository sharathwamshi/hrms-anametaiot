import assert from "node:assert/strict";
import test from "node:test";
import { hasAutomaticClockoutBell } from "../src/utils/attendanceCalendar.js";

test("automatic clock-out bell dates come only from calendar API metadata", () => {
  const calendar = {
    automatic_clockout_bell_dates: ["2026-11-01", "2027-01-01"],
  };

  assert.equal(hasAutomaticClockoutBell(calendar, "2026-11-01"), true);
  assert.equal(hasAutomaticClockoutBell(calendar, "2027-01-01"), true);
  assert.equal(hasAutomaticClockoutBell(calendar, "2026-10-31"), false);
  assert.equal(hasAutomaticClockoutBell({ records: [{ clock_out_note: "manual" }] }, "2026-11-01"), false);
});
