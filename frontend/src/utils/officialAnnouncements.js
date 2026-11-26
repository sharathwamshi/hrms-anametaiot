export function emptyAudiences() {
  return { everyone: false, user_ids: [], department_ids: [], roles: [] };
}

export function audienceCount(audiences) {
  return Number(Boolean(audiences.everyone))
    + audiences.user_ids.length
    + audiences.department_ids.length
    + audiences.roles.length;
}

export function toggleAudience(audiences, type, value) {
  if (type === "everyone") {
    return { ...audiences, everyone: !audiences.everyone };
  }
  const field = { user: "user_ids", department: "department_ids", role: "roles" }[type];
  if (!field) return audiences;
  const values = audiences[field];
  const exists = values.some((item) => String(item) === String(value));
  return {
    ...audiences,
    [field]: exists
      ? values.filter((item) => String(item) !== String(value))
      : [...values, type === "role" ? value : Number(value)],
  };
}

export function filterRecipients(users, search) {
  const query = search.trim().toLocaleLowerCase();
  if (!query) return users;
  return users.filter((user) => (
    [user.full_name, user.role_label, user.designation, user.department]
      .some((value) => value?.toLocaleLowerCase().includes(query))
  ));
}

export function sortAnnouncementsByPublication(items) {
  const timestamp = (announcement) => {
    const value = Date.parse(announcement.publish_at || "");
    return Number.isNaN(value) ? Number.NEGATIVE_INFINITY : value;
  };
  return [...items].sort((left, right) => {
    const leftTime = timestamp(left);
    const rightTime = timestamp(right);
    return leftTime === rightTime ? 0 : leftTime > rightTime ? -1 : 1;
  });
}

export function selectDashboardAnnouncements(items, now = new Date()) {
  const nowMs = now.getTime();
  const eligible = items.filter((announcement) => {
    if (announcement.status !== "active") return false;
    const publishMs = Date.parse(announcement.publish_at || "");
    const expiryMs = announcement.expires_at ? Date.parse(announcement.expires_at) : null;
    return Number.isFinite(publishMs)
      && publishMs <= nowMs
      && (expiryMs === null || (Number.isFinite(expiryMs) && expiryMs > nowMs));
  });
  const birthdays = eligible.filter((announcement) => announcement.kind === "birthday");
  const official = [...eligible]
    .filter((announcement) => announcement.kind !== "birthday")
    .sort((left, right) => {
      const leftTime = Date.parse((left.expires_at ? left.publish_at : left.created_at) || "");
      const rightTime = Date.parse((right.expires_at ? right.publish_at : right.created_at) || "");
      const a = Number.isFinite(leftTime) ? leftTime : Number.NEGATIVE_INFINITY;
      const b = Number.isFinite(rightTime) ? rightTime : Number.NEGATIVE_INFINITY;
      if (a !== b) return a > b ? -1 : 1;
      return Number(right.id) - Number(left.id);
    });

  const selected = birthdays.slice(0, 2);
  let remaining = 2 - selected.length;
  selected.push(...official.slice(0, remaining));
  return selected;
}

export function millisecondsUntilNextIstMidnight(now = new Date()) {
  const dateParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const fields = Object.fromEntries(dateParts.map(({ type, value }) => [type, value]));
  const nextMidnightUtc = Date.UTC(
    Number(fields.year),
    Number(fields.month) - 1,
    Number(fields.day) + 1,
  ) - 5.5 * 60 * 60 * 1000;
  return Math.max(0, nextMidnightUtc - now.getTime());
}

export function istInputValue(value) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(value);
  const fields = Object.fromEntries(parts.map(({ type, value: part }) => [type, part]));
  return `${fields.year}-${fields.month}-${fields.day}T${fields.hour}:${fields.minute}`;
}

export function istInputToIso(value) {
  if (!value) return "";
  const parsed = new Date(`${value}:00+05:30`);
  if (Number.isNaN(parsed.getTime())) throw new Error("Enter a valid date and time.");
  return parsed.toISOString();
}

export function isoToIstInput(value) {
  return value ? istInputValue(new Date(value)) : "";
}
