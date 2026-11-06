import assert from "node:assert/strict";
import test from "node:test";
import {
  AUTO_CLOCK_OUT_MESSAGE,
  hasAutomaticClockoutBell,
  toggleAutomaticClockoutNotification,
} from "../src/utils/attendanceCalendar.js";

test("automatic clock-out bell dates come only from calendar API metadata", () => {
  const calendar = {
    automatic_clockout_bell_dates: ["2026-10-31", "2026-12-31"],
  };

  assert.equal(hasAutomaticClockoutBell(calendar, "2026-10-31"), true);
  assert.equal(hasAutomaticClockoutBell(calendar, "2026-12-31"), true);
  assert.equal(hasAutomaticClockoutBell(calendar, "2026-11-01"), false);
  assert.equal(hasAutomaticClockoutBell({ records: [{ clock_out_note: "manual" }] }, "2026-10-31"), false);
});

test("automatic clock-out notification uses the required message", () => {
  assert.equal(AUTO_CLOCK_OUT_MESSAGE, "You forgot to clock out yesterday.");
});

test("notification activation opens and toggles closed for the selected date", () => {
  assert.equal(toggleAutomaticClockoutNotification(null, "2026-10-31"), "2026-10-31");
  assert.equal(toggleAutomaticClockoutNotification("2026-10-31", "2026-10-31"), null);
  assert.equal(toggleAutomaticClockoutNotification("2026-10-30", "2026-10-31"), "2026-10-31");
});
