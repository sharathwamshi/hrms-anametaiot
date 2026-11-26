import assert from "node:assert/strict";
import test from "node:test";

import {
  audienceCount,
  emptyAudiences,
  filterRecipients,
  millisecondsUntilNextIstMidnight,
  isoToIstInput,
  selectDashboardAnnouncements,
  sortAnnouncementsByPublication,
  istInputToIso,
  toggleAudience,
} from "./officialAnnouncements.js";

test("recipient filtering matches name, role, designation, and department", () => {
  const people = [{
    full_name: "Mira Rao",
    role_label: "Manager",
    designation: "Engineering Lead",
    department: "Platform",
  }];
  for (const search of ["mira", "manager", "engineering", "platform"]) {
    assert.equal(filterRecipients(people, search).length, 1);
  }
  assert.equal(filterRecipients(people, "finance").length, 0);
});

test("recipient selections persist independently of search and clear as a set", () => {
  let audiences = emptyAudiences();
  audiences = toggleAudience(audiences, "user", 12);
  audiences = toggleAudience(audiences, "role", "manager");
  audiences = toggleAudience(audiences, "department", 4);
  assert.deepEqual(audiences, {
    everyone: false,
    user_ids: [12],
    department_ids: [4],
    roles: ["manager"],
  });
  assert.equal(audienceCount(audiences), 3);
  assert.deepEqual(toggleAudience(audiences, "user", 12).user_ids, []);
});

test("Asia/Kolkata date-time conversion is independent of browser timezone", () => {
  assert.equal(istInputToIso("2026-11-25T09:30"), "2026-11-25T04:00:00.000Z");
  assert.equal(isoToIstInput("2026-11-25T04:00:00.000Z"), "2026-11-25T09:30");
});

test("birthday refresh delay targets midnight in Asia/Kolkata", () => {
  const beforeMidnight = new Date("2026-11-26T18:29:30.000Z");
  assert.equal(millisecondsUntilNextIstMidnight(beforeMidnight), 30_000);
});

test("dashboard selection prioritizes birthdays and newest official posts", () => {
  const now = new Date("2026-04-04T06:30:00.000Z");
  const birthday = {
    id: "birthday",
    kind: "birthday",
    status: "active",
    publish_at: "2026-04-03T18:30:00.000Z",
    expires_at: "2026-04-04T18:30:00.000Z",
  };
  const expiringNewest = {
    id: 1,
    kind: "official",
    status: "active",
    publish_at: "2026-04-04T05:30:00.000Z",
    expires_at: "2026-04-04T08:30:00.000Z",
  };
  const expiringOlder = {
    ...expiringNewest,
    id: 2,
    publish_at: "2026-04-04T04:30:00.000Z",
  };
  const noExpiryNewest = {
    id: 3,
    kind: "official",
    status: "active",
    publish_at: "2026-04-04T03:30:00.000Z",
    created_at: "2026-04-04T04:00:00.000Z",
    expires_at: null,
  };
  const noExpiryOlder = {
    ...noExpiryNewest,
    id: 4,
    publish_at: "2026-04-04T04:30:00.000Z",
    created_at: "2026-04-04T03:00:00.000Z",
  };
  const noExpiryJustPublished = {
    ...noExpiryNewest,
    id: 7,
    publish_at: "2026-04-04T05:45:00.000Z",
    created_at: "2026-04-04T06:00:00.000Z",
  };
  const future = { ...expiringNewest, id: 5, publish_at: "2026-04-04T07:00:00.000Z" };
  const expired = { ...expiringNewest, id: 6, expires_at: "2026-04-04T06:00:00.000Z" };

  assert.deepEqual(
    selectDashboardAnnouncements(
      [noExpiryOlder, future, expiringOlder, noExpiryNewest, birthday, expired, expiringNewest],
      now,
    ).map(({ id }) => id),
    ["birthday", 1],
  );
  assert.deepEqual(
    selectDashboardAnnouncements([expiringNewest, noExpiryOlder, noExpiryNewest], now)
      .map(({ id }) => id),
    [1, 3],
  );
  assert.deepEqual(
    selectDashboardAnnouncements([expiringNewest, noExpiryJustPublished], now)
      .map(({ id }) => id),
    [7, 1],
  );
  assert.deepEqual(
    selectDashboardAnnouncements([noExpiryOlder, noExpiryNewest], now)
      .map(({ id }) => id),
    [3, 4],
  );
});

test("announcements sort newest publication first regardless of priority", () => {
  const sorted = sortAnnouncementsByPublication([
    { id: 1, priority: "urgent", publish_at: "2026-11-25T04:00:00Z" },
    { id: 2, priority: "normal", publish_at: "2026-11-25T05:00:00Z" },
    { id: 3, priority: "important", publish_at: "2026-11-25T03:00:00Z" },
  ]);
  assert.deepEqual(sorted.map(({ id }) => id), [2, 1, 3]);
  assert.deepEqual(sortAnnouncementsByPublication(sorted.slice(0, 2)).map(({ id }) => id), [2, 1]);
});
