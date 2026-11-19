import { parseUtc } from "./datetime.js";

let companyTimezone = "Asia/Kolkata";

export function setCompanyTimezone(timezone) {
  if (!timezone || timezone === companyTimezone) return false;
  new Intl.DateTimeFormat("en-IN", { timeZone: timezone });
  companyTimezone = timezone;
  return true;
}

function companyParts(date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: companyTimezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  return Object.fromEntries(parts.filter((part) => part.type !== "literal").map(({ type, value }) => [type, Number(value)]));
}

export function formatCompanyTime(instant, seconds = false) {
  if (!instant) return "—";
  const date = typeof instant === "string" ? parseUtc(instant) : instant;
  const parts = new Intl.DateTimeFormat("en-IN", {
    timeZone: companyTimezone,
    hour: "2-digit",
    minute: "2-digit",
    ...(seconds ? { second: "2-digit" } : {}),
    hour12: true,
    timeZoneName: "short",
  }).formatToParts(date);
  const value = (type) => parts.find((part) => part.type === type)?.value;
  return `${value("hour")}:${value("minute")}${seconds ? `:${value("second")}` : ""} ${value("dayPeriod").toUpperCase()} ${value("timeZoneName")}`;
}

export const fmtTime = (iso) => formatCompanyTime(iso);

export const fmtHours = (h) => {
  if (h === null || h === undefined || h === 0) return "—";
  const mins = Math.round(h * 60);
  return `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, "0")}m`;
};

export const arrivalLabel = (status) => (
  status === "late" ? "Late" : status === "in_time" ? "In Time" : "—"
);

export const pad = (n) => String(n).padStart(2, "0");

/** YYYY-MM-DD in the company timezone. */
export const localDateStr = (d = new Date()) => {
  const parts = companyParts(d);
  return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}`;
};

export const isSundayDate = (dateString) => (
  Boolean(dateString) && new Date(`${dateString}T00:00:00`).getDay() === 0
);

export const BACKDATED_LEAVE_ERROR = "You can apply for leave only from the first day of the current month onward. Applications for previous months are not allowed.";

export function currentMonthLeaveStart(today = localDateStr()) {
  return `${today.slice(0, 7)}-01`;
}

export const isDisallowedBackdatedLeaveDate = (dateString, today = localDateStr()) => {
  return Boolean(dateString) && dateString < currentMonthLeaveStart(today);
};

export const leaveDaysByYear = (startDate, endDate) => {
  const days = {};
  if (!startDate || !endDate || startDate > endDate) return days;
  const current = new Date(`${startDate}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);
  while (current <= end) {
    if (current.getDay() !== 0) {
      const year = current.getFullYear();
      days[year] = (days[year] || 0) + 1;
    }
    current.setDate(current.getDate() + 1);
  }
  return days;
};

export function formatCompanyDateLabel(dateString, options) {
  const date = new Date(`${dateString}T00:00:00Z`);
  return new Intl.DateTimeFormat("en-IN", { ...options, timeZone: "UTC" }).format(date);
}

export function formatCompanyDateTime(instant, options) {
  if (!instant) return "";
  return new Intl.DateTimeFormat("en-IN", {
    ...options,
    timeZone: companyTimezone,
    timeZoneName: "short",
  }).format(parseUtc(instant));
}

export function companyYearMonth(date = new Date()) {
  const { year, month } = companyParts(date);
  return { year, month };
}

/** Company-local wall-clock value for a datetime-local input, from a stored UTC ISO. */
export function toLocalInput(iso) {
  if (!iso) return "";
  const d = parseUtc(iso);
  const parts = companyParts(d);
  return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}T${pad(parts.hour)}:${pad(parts.minute)}`;
}

/** Converts a company-local wall-clock input to a UTC ISO string independent of the browser TZ. */
export function fromLocalInput(value) {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const [, year, month, day, hour, minute] = match.map(Number);
  const wallTime = Date.UTC(year, month - 1, day, hour, minute);
  const requested = new Date(wallTime);
  if (requested.getUTCFullYear() !== year || requested.getUTCMonth() !== month - 1 || requested.getUTCDate() !== day ||
      requested.getUTCHours() !== hour || requested.getUTCMinutes() !== minute) return null;
  let utcTime = wallTime;
  for (let i = 0; i < 3; i++) {
    const shown = companyParts(new Date(utcTime));
    const shownAsUtc = Date.UTC(shown.year, shown.month - 1, shown.day, shown.hour, shown.minute);
    utcTime += wallTime - shownAsUtc;
  }
  return new Date(utcTime).toISOString();
}

/** In-office / out-of-office wording for a punch's soft-geofence flag. */
export function placeLabel(within) {
  if (within === true) return { text: "In office", cls: "green" };
  if (within === false) return { text: "Out of office", cls: "red" };
  return { text: "Location not captured", cls: "" };
}
