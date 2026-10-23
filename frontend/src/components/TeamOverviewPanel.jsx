import { useEffect, useMemo, useState } from "react";
import client from "../api/client";
import Badge from "./Badge";
import Loader from "./Loader";
import ExportButton from "./ExportButton";
import { fmtTime, fmtHours, arrivalLabel, localDateStr, placeLabel } from "../utils/attendanceTime";
import { mapsUrl } from "../utils/geo";

const inputStyle = { border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" };

/** Everyone in the viewer's scope for one day (including people who haven't clocked in). */
export default function TeamOverviewPanel({ onOpenPerson, refreshKey = 0, timezoneVersion = 0 }) {
  const [date, setDate] = useState(localDateStr());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [range, setRange] = useState({ from: localDateStr(new Date(Date.now() - 29 * 864e5)), to: localDateStr() });

  useEffect(() => {
    setDate(localDateStr());
    setRange({ from: localDateStr(new Date(Date.now() - 29 * 864e5)), to: localDateStr() });
  }, [timezoneVersion]);

  useEffect(() => {
    let off = false;
    setData(null);
    client.get("/attendance/team/overview", { params: { date } })
      .then(({ data: d }) => { if (!off) setData(d); })
      .catch((e) => { if (!off) setError(e?.response?.data?.message || "Could not load the team."); });
    return () => { off = true; };
  }, [date, refreshKey]);

  const people = useMemo(() => (data?.people || []).filter((p) => !q || p.user.full_name.toLowerCase().includes(q.toLowerCase()) || (p.user.employee_code || "").toLowerCase().includes(q.toLowerCase())), [data, q]);
  const s = data?.summary;

  return (
    <div className="card">
      <div className="card-title-row" style={{ flexWrap: "wrap", gap: 10 }}>
        <h3>Team Attendance</h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input placeholder="Search name or code" value={q} onChange={(e) => setQ(e.target.value)} style={{ ...inputStyle, width: 170 }} />
          <input type="date" value={date} max={localDateStr()} onChange={(e) => e.target.value && setDate(e.target.value)} style={inputStyle} />
          <ExportButton url="/attendance/export/team-day" params={{ date }} filename={`Team_Attendance_${date}`} label="Export this day" />
        </div>
      </div>
      {data?.is_holiday && <div className="att-chip amber" style={{ marginBottom: 10 }}>Holiday — {data.holiday_name}</div>}
      {error && <div className="login-error">{error}</div>}
      {!data && !error && <Loader />}
      {data && (
        <>
          <div className="att-sum">
            <div><b>{s.present}</b><span>Present</span></div>
            <div><b>{s.clocked_in_now}</b><span>Clocked in now</span></div>
            <div><b>{s.not_clocked_in}</b><span>Not in yet</span></div>
            <div><b>{s.on_leave}</b><span>On leave</span></div>
            <div><b>{s.absent}</b><span>Absent</span></div>
            <div><b>{s.outside_office}</b><span>Out of office</span></div>
            <div><b>{s.reentries}</b><span>Re-entries</span></div>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr><th>Employee</th><th>Status</th><th>First In</th><th>Last Out</th><th>Hours</th><th>Check-ins</th><th>Work location</th><th>Where</th><th>Re-entry reason</th><th></th></tr>
              </thead>
              <tbody>
                {people.length === 0 && <tr className="empty-row"><td colSpan={10}>No one to show.</td></tr>}
                {people.map((p) => {
                  const rec = p.record;
                  const loc = p.last_known_location;
                  const place = loc ? placeLabel(loc.within_geofence) : null;
                  return (
                    <tr key={p.user.id} className="att-person-row" onClick={() => onOpenPerson(p.user)}>
                      <td><strong>{p.user.full_name}</strong><div className="muted" style={{ fontSize: 11.5 }}>{p.user.employee_code}{p.user.designation ? ` · ${p.user.designation}` : ""}</div>{p.user.restrict_to_office && <span className="att-chip amber" style={{ marginTop: 4, display: "inline-block" }} title="Clock in/out is only allowed from the office">Office only</span>}</td>
                      <td><Badge status={p.status} />{p.clocked_in_now && <div className="att-chip green" style={{ marginTop: 4 }}>In now</div>}{rec?.check_in_status && <div className={`att-chip ${rec.check_in_status === "late" ? "red" : "green"}`} style={{ marginTop: 4 }}>{arrivalLabel(rec.check_in_status)}</div>}</td>
                      <td>{rec?.clock_in ? fmtTime(rec.clock_in) : "—"}</td>
                      <td>{rec?.clock_in ? (rec.clock_out ? fmtTime(rec.clock_out) : "—") : "—"}</td>
                      <td>{fmtHours(rec?.total_hours)}</td>
                      <td>{p.session_count || "—"}{p.reentry_count > 0 && <span className="att-chip amber" style={{ marginLeft: 6 }}>↻ {p.reentry_count}</span>}</td>
                      <td>
                        {(rec?.sessions || []).filter((session) => session.work_location_name).map((session) => (
                          <div key={session.session_no}><span className="att-chip">{(rec.sessions.length > 1 ? `#${session.session_no} ` : "") + session.work_location_name}</span></div>
                        ))}
                        {!(rec?.sessions || []).some((session) => session.work_location_name) && <span className="muted">—</span>}
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        {place ? <><span className={`att-chip ${place.cls}`}>{place.text}</span> <a href={mapsUrl(loc.latitude, loc.longitude)} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>Maps ›</a></> : <span className="muted">—</span>}
                      </td>
                      <td className="muted" style={{ maxWidth: 220, fontSize: 12.5 }}>{p.latest_reentry?.reason || "—"}</td>
                      <td><button className="btn btn-sm btn-outline" onClick={(e) => { e.stopPropagation(); onOpenPerson(p.user); }}>View ›</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--color-border)", display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <strong style={{ fontSize: 13 }}>Export a date range (daily rows + every check-in):</strong>
            <input type="date" value={range.from} max={range.to} onChange={(e) => setRange({ ...range, from: e.target.value })} style={inputStyle} />
            <span className="muted">to</span>
            <input type="date" value={range.to} min={range.from} max={localDateStr()} onChange={(e) => setRange({ ...range, to: e.target.value })} style={inputStyle} />
            <ExportButton url="/attendance/export/team" params={range} filename={`Team_Attendance_${range.from}_to_${range.to}`} label="Export range" />
          </div>
        </>
      )}
    </div>
  );
}
