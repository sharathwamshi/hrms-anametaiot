import { parseUtc } from "./datetime";

export const fmtTime = (iso) =>
  iso ? parseUtc(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "—";

export const fmtHours = (h) => {
  if (h === null || h === undefined || h === 0) return "—";
  const mins = Math.round(h * 60);
  return `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, "0")}m`;
};

export const pad = (n) => String(n).padStart(2, "0");

/** YYYY-MM-DD for a local Date. */
export const localDateStr = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** "2026-10-08T09:30" (local wall-clock) for a <input type="datetime-local">, from a stored UTC ISO. */
export function toLocalInput(iso) {
  if (!iso) return "";
  const d = parseUtc(iso);
  return `${localDateStr(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** UTC ISO string ("…Z") from a datetime-local value, which is local wall-clock time. */
export function fromLocalInput(value) {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

/** In-office / out-of-office wording for a punch's soft-geofence flag. */
export function placeLabel(within) {
  if (within === true) return { text: "In office", cls: "green" };
  if (within === false) return { text: "Out of office", cls: "red" };
  return { text: "Location not captured", cls: "" };
}
