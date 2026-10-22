import assert from "node:assert/strict";
import test from "node:test";
import {
  fmtTime,
  formatCompanyDateLabel,
  formatCompanyDateTime,
  fromLocalInput,
  localDateStr,
  setCompanyTimezone,
  toLocalInput,
} from "../src/utils/attendanceTime.js";

test("attendance timestamps and datetime inputs use the company timezone, not browser TZ", () => {
  setCompanyTimezone("Asia/Kolkata");
  const previousTimezone = process.env.TZ;
  const observed = [];

  try {
    for (const timezone of ["UTC", "America/Los_Angeles", "Pacific/Auckland"]) {
      process.env.TZ = timezone;
      const instant = "2026-10-22T04:00:00Z";
      observed.push({
        time: fmtTime(instant),
        input: toLocalInput(instant),
        utc: fromLocalInput("2026-10-22T09:30"),
        today: localDateStr(new Date("2026-10-21T20:00:00Z")),
        dateLabel: formatCompanyDateLabel("2026-10-22", { weekday: "long", day: "numeric" }),
        editedAt: formatCompanyDateTime(instant, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }),
      });
    }
  } finally {
    if (previousTimezone === undefined) delete process.env.TZ;
    else process.env.TZ = previousTimezone;
  }

  assert.deepEqual(observed[0], observed[1]);
  assert.deepEqual(observed[0], observed[2]);
  assert.match(observed[0].time, /09:30.*IST/);
  assert.equal(observed[0].input, "2026-10-22T09:30");
  assert.equal(observed[0].utc, "2026-10-22T04:00:00.000Z");
  assert.equal(observed[0].today, "2026-10-22");
  assert.match(observed[0].dateLabel, /Thursday/);
  assert.match(observed[0].editedAt, /IST/);
});
