import { useEffect, useMemo, useState } from "react";
import client from "../api/client";
import Badge from "./Badge";
import Loader from "./Loader";
import ExportButton from "./ExportButton";
import { fmtTime, fmtHours, arrivalLabel, localDateStr, placeLabel } from "../utils/attendanceTime";
import { mapsUrl } from "../utils/geo";

function workLocationNames(person) {
  const sessions = person.record?.sessions || [];
  return [...new Set(sessions.map((session) => session.work_location_name).filter(Boolean))].join(", ");
}

function activeSession(person) {
  return [...(person.record?.sessions || [])].reverse().find((session) => !session.clock_out);
}

/** Everyone in the viewer's scope for one day (including people who haven't clocked in). */
export default function TeamOverviewPanel({ onOpenPerson, refreshKey = 0, timezoneVersion = 0 }) {
  const [date, setDate] = useState(localDateStr());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [range, setRange] = useState({ from: localDateStr(new Date(Date.now() - 29 * 864e5)), to: localDateStr() });
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setDate(localDateStr());
    setRange({ from: localDateStr(new Date(Date.now() - 29 * 864e5)), to: localDateStr() });
  }, [timezoneVersion]);

  useEffect(() => {
    let off = false;
    setData(null);
    setError("");
    setLoading(true);
    client.get("/attendance/team/overview", { params: { date } })
      .then(({ data: d }) => { if (!off) setData(d); })
      .catch((e) => { if (!off) setError(e?.response?.data?.message || "Could not load the team."); })
      .finally(() => { if (!off) setLoading(false); });
    return () => { off = true; };
  }, [date, refreshKey]);

  const people = useMemo(() => (data?.people || []).filter((p) => !q || p.user.full_name.toLowerCase().includes(q.toLowerCase()) || (p.user.employee_code || "").toLowerCase().includes(q.toLowerCase())), [data, q]);
  const peopleById = useMemo(() => new Map((data?.people || []).map((person) => [person.user.id, person])), [data]);
  const presentPeople = data?.present_people || [];
  const s = data?.summary;
  const categoryPeople = {
    present: presentPeople,
    clocked_in_now: (data?.category_person_ids?.clocked_in_now || []).map((id) => peopleById.get(id)).filter(Boolean),
    not_clocked_in: (data?.category_person_ids?.not_clocked_in || []).map((id) => peopleById.get(id)).filter(Boolean),
    absent: (data?.category_person_ids?.absent || []).map((id) => peopleById.get(id)).filter(Boolean),
    outside_office: (data?.category_person_ids?.outside_office || []).map((id) => peopleById.get(id)).filter(Boolean),
    reentries: (data?.people || []).flatMap((person) => (person.record?.sessions || [])
      .filter((session) => (session.session_no || 1) > 1)
      .map((session) => ({
        ...person,
        reentrySession: session,
        entryKey: `${person.user.id}-${session.session_no}`,
      }))),
  };
  const summaryCards = [
    { key: "present", count: s?.present, label: "Total present" },
    { key: "clocked_in_now", count: s?.clocked_in_now, label: "Clocked in now" },
    { key: "not_clocked_in", count: s?.not_clocked_in, label: "Not in yet" },
    { key: "absent", count: s?.absent, label: "Absent" },
    { key: "outside_office", count: s?.outside_office, label: "Out of office" },
    { key: "reentries", count: s?.reentries, label: "Re-entries" },
  ];
  const selectedCard = summaryCards.find((card) => card.key === selectedCategory);
  const displayedPeople = selectedCategory ? categoryPeople[selectedCategory] : [];
  const detailColumns = {
    present: [
      { label: "Employee", render: (person) => <strong>{person.user.full_name}</strong> },
      { label: "Employee ID", render: (person) => person.user.employee_code || person.user.id },
      { label: "Designation", render: (person) => person.user.designation || "—" },
      { label: "Attendance status", render: (person) => <Badge status={person.status} /> },
      { label: "First check-in", render: (person) => person.record?.clock_in ? fmtTime(person.record.clock_in) : "—" },
      { label: "Last check-out", render: (person) => person.record?.clock_out ? fmtTime(person.record.clock_out) : "—" },
    ],
    clocked_in_now: [
      { label: "Employee", render: (person) => <strong>{person.user.full_name}</strong> },
      { label: "Employee ID", render: (person) => person.user.employee_code || person.user.id },
      { label: "Designation", render: (person) => person.user.designation || "—" },
      { label: "First check-in", render: (person) => person.record?.clock_in ? fmtTime(person.record.clock_in) : "—" },
      { label: "Current check-in status", render: (person) => person.record?.check_in_status ? arrivalLabel(person.record.check_in_status) : <Badge status={person.status} /> },
      { label: "Work location", render: (person) => activeSession(person)?.work_location_name || workLocationNames(person) || "—" },
      { label: "Last check-in", render: (person) => activeSession(person)?.clock_in ? fmtTime(activeSession(person).clock_in) : "—" },
    ],
    not_clocked_in: [
      { label: "Employee", render: (person) => <strong>{person.user.full_name}</strong> },
      { label: "Employee ID", render: (person) => person.user.employee_code || person.user.id },
      { label: "Designation", render: (person) => person.user.designation || "—" },
      { label: "Attendance date", render: () => date },
      { label: "Attendance status", render: (person) => <Badge status={person.status} /> },
    ],
    absent: [
      { label: "Employee", render: (person) => <strong>{person.user.full_name}</strong> },
      { label: "Employee ID", render: (person) => person.user.employee_code || person.user.id },
      { label: "Designation", render: (person) => person.user.designation || "—" },
      { label: "Attendance date", render: () => date },
      { label: "Attendance status", render: (person) => <Badge status={person.status} /> },
    ],
    outside_office: [
      { label: "Employee", render: (person) => <strong>{person.user.full_name}</strong> },
      { label: "Employee ID", render: (person) => person.user.employee_code || person.user.id },
      { label: "Designation", render: (person) => person.user.designation || "—" },
      { label: "Work location", render: (person) => workLocationNames(person) || (person.last_known_location ? placeLabel(person.last_known_location.within_geofence).text : "Out of office") },
      { label: "Check-in time", render: (person) => person.record?.clock_in ? fmtTime(person.record.clock_in) : "—" },
      { label: "Attendance status", render: (person) => <Badge status={person.status} /> },
    ],
    reentries: [
      { label: "Employee", render: (person) => <strong>{person.user.full_name}</strong> },
      { label: "Employee ID", render: (person) => person.user.employee_code || person.user.id },
      { label: "Designation", render: (person) => person.user.designation || "—" },
      { label: "Re-entry", render: (person) => `#${person.reentrySession.session_no}` },
      { label: "Check-in time", render: (person) => person.reentrySession.clock_in ? fmtTime(person.reentrySession.clock_in) : "—" },
      { label: "Reason", render: (person) => person.reentrySession.reentry_reason || "—" },
      { label: "Attendance status", render: (person) => <Badge status={person.status} /> },
    ],
  };
  const activeColumns = selectedCategory ? detailColumns[selectedCategory] : [];
  const rangeValid = !!range.from && !!range.to && range.from <= range.to;
  const rangeError = !range.from || !range.to
    ? "Select both a from date and a to date to export."
    : range.from > range.to
      ? "From date must be on or before To date."
      : "";

  return (
    <div className="card">
      <div className="team-attendance-header">
        <h3>Team Attendance</h3>
        <div className="team-attendance-toolbar">
          <input aria-label="Search employee name or code" placeholder="Search employee name or code" value={q} onChange={(e) => setQ(e.target.value)} />
          <label><span>Attendance date</span><input type="date" value={date} max={localDateStr()} onChange={(e) => e.target.value && setDate(e.target.value)} /></label>
          <label><span>From</span><input type="date" value={range.from} max={localDateStr()} onChange={(e) => setRange({ ...range, from: e.target.value })} required /></label>
          <label><span>To</span><input type="date" value={range.to} max={localDateStr()} onChange={(e) => setRange({ ...range, to: e.target.value })} required /></label>
          <div className="team-attendance-export-actions">
            <ExportButton url="/attendance/export/team-day" params={{ date }} filename={`Team_Attendance_${date}`} label="Export selected day" />
            <ExportButton url="/attendance/export/team" params={range} filename={`Team_Attendance_${range.from}_to_${range.to}`} label="Export range" disabled={!rangeValid} />
          </div>
        </div>
      </div>
      {rangeError && <div className="login-error" role="alert" style={{ marginBottom: 10 }}>{rangeError}</div>}
      {data?.is_holiday && <div className="att-chip amber" style={{ marginBottom: 10 }}>Holiday — {data.holiday_name}</div>}
      {error && !selectedCategory && <div className="login-error">{error}</div>}
      {!data && !error && !selectedCategory && <Loader />}
      {!data && selectedCategory && (
        <section className="team-present-list" aria-live="polite">
          <div className="card-title-row">
            <h4>{selectedCard?.label} — {date}</h4>
            <button type="button" className="btn btn-sm btn-outline" onClick={() => setSelectedCategory(null)}>Close</button>
          </div>
          {loading && <Loader />}
          {error && <div className="login-error">{error}</div>}
        </section>
      )}
      {data && (
        <>
          <div className="att-sum">
            {summaryCards.map((card) => (
              <button
                type="button"
                key={card.key}
                className={`att-sum-interactive${selectedCategory === card.key ? " selected" : ""}`}
                aria-expanded={selectedCategory === card.key}
                aria-controls="team-category-employees"
                onClick={() => setSelectedCategory((current) => current === card.key ? null : card.key)}
              >
                <b>{card.count}</b><span>{card.label}</span>
                {selectedCategory === card.key && <small>Selected</small>}
              </button>
            ))}
          </div>
          {selectedCategory && (
            <section id="team-category-employees" className="team-present-list" aria-label={`${selectedCard.label} ${selectedCategory === "reentries" ? "on" : "employees on"} ${date}`}>
              <div className="card-title-row">
                <h4>{selectedCard.label} — {date} ({displayedPeople.length} {selectedCategory === "reentries" ? `re-entry ${displayedPeople.length === 1 ? "event" : "events"}` : "employees"})</h4>
                <button type="button" className="btn btn-sm btn-outline" onClick={() => setSelectedCategory(null)}>Close</button>
              </div>
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr>{activeColumns.map((column) => <th key={column.label}>{column.label}</th>)}</tr></thead>
                  <tbody>
                    {displayedPeople.length === 0 && <tr className="empty-row"><td colSpan={activeColumns.length}>{selectedCategory === "reentries" ? "No re-entry events for the selected date." : "No employees match this category for the selected date."}</td></tr>}
                    {displayedPeople.map((person) => (
                      <tr key={person.entryKey || person.user.id}>
                        {activeColumns.map((column) => <td key={column.label}>{column.render(person)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          <div className="table-wrap">
            <table className="data-table team-attendance-table">
              <colgroup>
                <col className="team-attendance-col-employee" />
                <col className="team-attendance-col-status" />
                <col className="team-attendance-col-time" />
                <col className="team-attendance-col-time" />
                <col className="team-attendance-col-hours" />
                <col className="team-attendance-col-checkins" />
                <col className="team-attendance-col-location" />
                <col className="team-attendance-col-where" />
                <col className="team-attendance-col-view" />
              </colgroup>
              <thead>
                <tr><th>Employee</th><th>Status</th><th>First In</th><th>Last Out</th><th>Hours</th><th>Check-ins</th><th>Work location</th><th>Where</th><th></th></tr>
              </thead>
              <tbody>
                {people.length === 0 && <tr className="empty-row"><td colSpan={9}>No one to show.</td></tr>}
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
                      <td>{p.session_count || "—"}</td>
                      <td>
                        {(rec?.sessions || []).filter((session) => session.work_location_name).map((session) => (
                          <div key={session.session_no}><span className="att-chip">{(rec.sessions.length > 1 ? `#${session.session_no} ` : "") + session.work_location_name}</span></div>
                        ))}
                        {!(rec?.sessions || []).some((session) => session.work_location_name) && <span className="muted">—</span>}
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        {place ? <><span className={`att-chip ${place.cls}`}>{place.text}</span> <a href={mapsUrl(loc.latitude, loc.longitude)} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>Maps ›</a></> : <span className="muted">—</span>}
                      </td>
                      <td><button className="btn btn-sm btn-outline" onClick={(e) => { e.stopPropagation(); onOpenPerson(p.user); }}>View ›</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
