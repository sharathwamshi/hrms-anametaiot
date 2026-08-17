/**
 * Backend timestamps (created_at, clock_in, scheduled_at, window_end, etc.)
 * are stored and serialized as naive UTC — Python's datetime.isoformat()
 * omits the "Z" suffix (e.g. "2026-08-07T15:00:00", not "...Z"). The
 * browser's Date constructor treats a date-*time* string with no timezone
 * marker as LOCAL time, not UTC — so every one of these fields was silently
 * shifting by the viewer's UTC offset (5:30 hours for IST) once displayed.
 *
 * Plain DATE-only fields (work_date, date_of_joining — "YYYY-MM-DD", no
 * "T") are unaffected: the JS spec already treats those as UTC.
 *
 * Use this instead of `new Date(x)` for any field that has a time
 * component and came from the API.
 */
export function parseUtc(isoString) {
  if (!isoString) return null;
  const alreadyHasZone = /[Zz]|[+-]\d{2}:\d{2}$/.test(isoString);
  if (!isoString.includes("T") || alreadyHasZone) {
    return new Date(isoString);
  }
  return new Date(isoString + "Z");
}
