import { useEffect, useMemo, useState } from "react";
import client from "../api/client";
import Loader from "./Loader";
import ExportButton from "./ExportButton";
import DayDetailModal from "./DayDetailModal";
import { fmtTime, fmtHours, localDateStr } from "../utils/attendanceTime";

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/**
 * Month calendar of one person's attendance — the web twin of the mobile app's History tab.
 *   endpoint: "/attendance/my-calendar" (yourself) or `/attendance/team/${id}/calendar` (a manager looking
 *   at a report). `manager` turns on the correction actions in the day detail.
 */
export default function AttendanceCalendar({ endpoint, manager = false, exportUserId = null, refreshKey = 0, onChanged }) {
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [openDay, setOpenDay] = useState(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError("");
    client.get(endpoint, { params: { month, year } })
      .then(({ data: d }) => { if (!cancelled) setData(d); })
      .catch((err) => { if (!cancelled) setError(err?.response?.data?.message || "Could not load the calendar."); });
    return () => { cancelled = true; };
  }, [endpoint, month, year, refreshKey, version]);

  const shift = (delta) => {
    let m = month + delta, y = year;
    if (m < 1) { m = 12; y -= 1; }
    if (m > 12) { m = 1; y += 1; }
    setMonth(m); setYear(y);
  };

  const cells = useMemo(() => {
    if (!data) return [];
    const byDate = Object.fromEntries(data.records.map((r) => [r.work_date, r]));
    const holidays = Object.fromEntries(data.holidays.map((h) => [h.holiday_date, h]));
    const leaveFor = (ds) => data.leaves.find((l) => l.start_date <= ds && l.end_date >= ds);
    const first = new Date(year, month - 1, 1);
    const lead = (first.getDay() + 6) % 7; // Monday-first
    const days = new Date(year, month, 0).getDate();
    const today = localDateStr();
    const out = Array.from({ length: lead }, () => ({ blank: true }));
    for (let d = 1; d <= days; d++) {
      const ds = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const rec = byDate[ds];
      const dow = (new Date(year, month - 1, d).getDay() + 6) % 7;
      const holiday = holidays[ds];
      const leave = leaveFor(ds);
      let cls = "";
      if (rec && (rec.clock_in || rec.status === "absent" || rec.status === "regularized")) cls = rec.status === "half_day" ? "half_day" : rec.status;
      else if (leave) cls = "leave";
      else if (holiday) cls = "holiday";
      else if (dow >= 5) cls = "weekend";
      out.push({ d, ds, rec, holiday, leave, cls, isToday: ds === today, future: ds > today });
    }
    return out;
  }, [data, month, year]);

  const s = data?.summary;
  const changed = () => { setVersion((v) => v + 1); onChanged?.(); };

  return (
    <div>
      <div className="att-cal-head">
        <div className="att-cal-nav">
          <button className="btn btn-sm btn-outline" onClick={() => shift(-1)} aria-label="Previous month">‹</button>
          <strong>{MONTHS[month - 1]} {year}</strong>
          <button className="btn btn-sm btn-outline" onClick={() => shift(1)} aria-label="Next month">›</button>
          <button className="btn btn-sm btn-outline" onClick={() => { setMonth(now.getMonth() + 1); setYear(now.getFullYear()); }}>Today</button>
        </div>
        <ExportButton
          url={exportUserId ? "/attendance/export/team" : "/attendance/export/my"}
          params={{ month, year, ...(exportUserId ? { user_id: exportUserId } : {}) }}
          filename={`Attendance_${data?.user?.employee_code || "me"}_${year}-${String(month).padStart(2, "0")}`}
          label="Export month to Excel"
        />
      </div>

      {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
      {!data && !error && <Loader />}
      {data && (
        <>
          <div className="att-sum">
            <div><b>{s.present}</b><span>Present</span></div>
            <div><b>{s.half_day}</b><span>Half days</span></div>
            <div><b>{s.absent}</b><span>Absent</span></div>
            <div><b>{s.on_leave}</b><span>On leave</span></div>
            <div><b>{s.holidays}</b><span>Holidays</span></div>
            <div><b>{fmtHours(s.total_hours)}</b><span>Worked</span></div>
            <div><b>{s.reentries}</b><span>Re-entries</span></div>
            <div><b>{s.outside_office}</b><span>Out-of-office days</span></div>
          </div>

          <div className="att-grid">
            {DOW.map((d) => <div key={d} className="att-dow">{d}</div>)}
            {cells.map((c, i) => c.blank ? <div key={`b${i}`} className="att-day blank" /> : (
              <button
                key={c.ds} type="button"
                className={`att-day ${c.cls} ${c.isToday ? "today" : ""} ${c.future ? "future" : ""}`}
                onClick={() => setOpenDay(c)}
                title={c.holiday?.name || c.leave?.leave_type || ""}
              >
                <span className="n">{c.d}</span>
                {c.rec?.outside_office_any && <i className="att-dot" title="A punch was outside the office" />}
                {!c.rec?.outside_office_any && c.rec?.regularization_status === "pending" && <i className="att-dot pending" title="Regularization pending" />}
                <span className="t">
                  {c.rec?.clock_in ? <>{fmtTime(c.rec.clock_in)}{c.rec.clock_out ? ` – ${fmtTime(c.rec.clock_out)}` : " – now"}<br />{fmtHours(c.rec.total_hours)}{c.rec.session_count > 1 ? ` · ${c.rec.session_count}×` : ""}</>
                    : c.holiday ? c.holiday.name
                    : c.leave ? (c.leave.leave_type || "Leave")
                    : c.rec?.status === "absent" ? "Absent"
                    : c.rec?.status === "regularized" ? "Regularized" : ""}
                </span>
              </button>
            ))}
          </div>

          <div className="att-legend">
            <span><i style={{ background: "var(--color-success-100)" }} />Present</span>
            <span><i style={{ background: "var(--color-warning-100)" }} />Half day</span>
            <span><i style={{ background: "var(--color-brand-orange-100)" }} />Regularized</span>
            <span><i style={{ background: "var(--color-brand-blue-50)" }} />Leave</span>
            <span><i style={{ background: "#fff7e0" }} />Holiday</span>
            <span><i style={{ background: "var(--color-danger-100)" }} />Absent</span>
            <span><i style={{ background: "var(--color-danger)", borderRadius: "50%" }} />Punched outside the office</span>
            <span><i style={{ background: "var(--color-warning)", borderRadius: "50%" }} />Regularization pending</span>
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>Click any day for every check-in and check-out, the location of each punch and the reason for each re-entry.</p>
        </>
      )}

      {openDay && data && (
        <DayDetailModal
          day={openDay}
          person={data.user}
          manager={manager}
          onClose={() => setOpenDay(null)}
          onChanged={() => { setOpenDay(null); changed(); }}
        />
      )}
    </div>
  );
}
