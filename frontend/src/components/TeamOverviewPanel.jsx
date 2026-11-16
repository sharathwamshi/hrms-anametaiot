import { useCallback, useEffect, useMemo, useState } from "react";
import client from "../api/client";
import Badge from "./Badge";
import Loader from "./Loader";
import { downloadFile } from "../utils/download";
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
  const [exportDialog, setExportDialog] = useState("");
  const [exportDate, setExportDate] = useState(localDateStr());
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [exportNotice, setExportNotice] = useState("");
  const [sort, setSort] = useState({ key: "name", direction: "asc" });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

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

  const searchTerm = q.trim().toLowerCase();
  const matchesSearch = useCallback((person) => !searchTerm
    || String(person.user.full_name || "").toLowerCase().includes(searchTerm)
    || String(person.user.employee_code || "").toLowerCase().includes(searchTerm), [searchTerm]);
  const people = useMemo(() => (data?.people || []).filter(matchesSearch), [data, matchesSearch]);
  const sortedPeople = useMemo(() => {
    const valueFor = (person) => ({
      name: person.user.full_name,
      employee_id: person.user.employee_code || person.user.id,
      status: person.status,
      first_in: person.record?.clock_in || "",
      last_out: person.record?.clock_out || "",
      hours: Number(person.record?.total_hours || 0),
    })[sort.key];
    return [...people].sort((a, b) => {
      const left = valueFor(a);
      const right = valueFor(b);
      const comparison = typeof left === "number" && typeof right === "number"
        ? left - right
        : String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
      return comparison * (sort.direction === "asc" ? 1 : -1);
    });
  }, [people, sort]);
  const pageCount = Math.max(1, Math.ceil(sortedPeople.length / pageSize));
  const pagePeople = sortedPeople.slice((page - 1) * pageSize, page * pageSize);
  const peopleById = useMemo(() => new Map(people.map((person) => [person.user.id, person])), [people]);
  const totalEmployees = (data?.organization_people || []).map((user) => ({ user })).filter(matchesSearch);
  const presentPeople = (data?.present_people || []).filter(matchesSearch);
  const notClockedInPeople = people.filter((person) => (
    !person.record?.clock_in && !(person.record?.sessions || []).some((session) => session.clock_in)
  ));
  const categoryPeople = {
    total_employees: totalEmployees,
    present_today: presentPeople,
    not_clocked_in: notClockedInPeople,
    absent: (data?.category_person_ids?.absent || []).map((id) => peopleById.get(id)).filter(Boolean),
    outside_office: (data?.category_person_ids?.outside_office || []).map((id) => peopleById.get(id)).filter(Boolean),
    reentries: people.flatMap((person) => (person.record?.sessions || [])
      .filter((session) => (session.session_no || 1) > 1)
      .map((session) => ({
        ...person,
        reentrySession: session,
        entryKey: `${person.user.id}-${session.session_no}`,
      }))),
  };
  const summaryCards = [
    { key: "total_employees", count: categoryPeople.total_employees.length, label: "Total Employees" },
    { key: "present_today", count: categoryPeople.present_today.length, label: "Present Today" },
    { key: "not_clocked_in", count: categoryPeople.not_clocked_in.length, label: "Not Clocked In Yet" },
    { key: "absent", count: categoryPeople.absent.length, label: "Absent" },
    { key: "outside_office", count: categoryPeople.outside_office.length, label: "Out of office" },
    { key: "reentries", count: categoryPeople.reentries.length, label: "Re-entries" },
  ];
  const selectedCard = summaryCards.find((card) => card.key === selectedCategory);
  const displayedPeople = selectedCategory ? categoryPeople[selectedCategory] : [];
  const attendanceColumns = [
    { label: "Employee", render: (person) => <strong>{person.user.full_name}</strong> },
    { label: "Employee ID", render: (person) => person.user.employee_code || person.user.id },
    { label: "Designation", render: (person) => person.user.designation || "—" },
    { label: "Attendance status", render: (person) => <Badge status={person.status} /> },
    { label: "First check-in", render: (person) => person.record?.clock_in ? fmtTime(person.record.clock_in) : "—" },
    { label: "Last check-out", render: (person) => person.record?.clock_out ? fmtTime(person.record.clock_out) : "—" },
  ];
  const detailColumns = {
    total_employees: [
      { label: "Employee", render: (person) => <strong>{person.user.full_name}</strong> },
      { label: "Employee ID", render: (person) => person.user.employee_code || person.user.id },
      { label: "Designation", render: (person) => person.user.designation || "—" },
    ],
    present_today: attendanceColumns,
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
  const rangeError = !range.from || !range.to
    ? "Select both a from date and a to date to export."
    : range.from > range.to
      ? "From date must be on or before To date."
      : "";

  useEffect(() => {
    setPage(1);
  }, [q, date, pageSize]);

  const sortButton = (key, label) => (
    <button
      type="button"
      className="table-sort-button"
      aria-label={`Sort by ${label}`}
      onClick={() => {
        setSort((current) => ({
          key,
          direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
        }));
        setPage(1);
      }}
    >
      {label}{sort.key === key ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
    </button>
  );

  const openExportDialog = (type) => {
    setExportError("");
    setExportNotice("");
    setExportDate(date);
    if (type === "range") {
      setRange((current) => ({ from: current.from || date, to: current.to || date }));
    }
    setExportDialog(type);
  };

  const runExport = async () => {
    if (exportDialog === "range" && rangeError) {
      setExportError(rangeError);
      return;
    }
    if (exportDialog === "day" && !exportDate) {
      setExportError("Select an attendance date to export.");
      return;
    }
    setExporting(true);
    setExportError("");
    try {
      const selectedRange = exportDialog === "range";
      const filename = selectedRange
        ? `Team_Attendance_${range.from}_to_${range.to}`
        : `Team_Attendance_${exportDate}`;
      await downloadFile(
        selectedRange ? "/attendance/export/team" : "/attendance/export/team-day",
        `${filename}_${new Date().toISOString().slice(0, 10)}.xlsx`,
        selectedRange ? range : { date: exportDate },
      );
      setExportNotice("Attendance export downloaded.");
      setExportDialog("");
    } catch (err) {
      setExportError(err?.message || "Could not export attendance.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="card">
      <div className="team-attendance-header">
        <h3>Team Attendance</h3>
        <div className="team-attendance-toolbar">
          <input aria-label="Search employee name or code" placeholder="Search employee name or code" value={q} onChange={(e) => setQ(e.target.value)} />
          <label><span>Attendance date</span><input type="date" value={date} max={localDateStr()} onChange={(e) => e.target.value && setDate(e.target.value)} /></label>
          <div className="team-attendance-export-actions">
            <button type="button" className="btn btn-sm btn-outline" onClick={() => openExportDialog("day")}>⬇ Export Selected Day</button>
            <button type="button" className="btn btn-sm btn-outline" onClick={() => openExportDialog("range")}>⬇ Export Range</button>
          </div>
        </div>
      </div>
      {exportNotice && <div className="notice-success" role="status" style={{ marginBottom: 10 }}>{exportNotice}</div>}
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
                <col className="team-attendance-col-employee-id" />
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
                <tr>
                  <th>{sortButton("name", "Employee")}</th>
                  <th>{sortButton("employee_id", "Employee ID")}</th>
                  <th>{sortButton("status", "Status")}</th>
                  <th>{sortButton("first_in", "First In")}</th>
                  <th>{sortButton("last_out", "Last Out")}</th>
                  <th>{sortButton("hours", "Hours")}</th>
                  <th>Check-ins</th><th>Work location</th><th>Where</th><th></th>
                </tr>
              </thead>
              <tbody>
                {people.length === 0 && <tr className="empty-row"><td colSpan={10}>No one to show.</td></tr>}
                {pagePeople.map((p) => {
                  const rec = p.record;
                  const loc = p.last_known_location;
                  const place = loc ? placeLabel(loc.within_geofence) : null;
                  return (
                    <tr key={p.user.id} className="att-person-row" onClick={() => onOpenPerson(p.user)}>
                      <td><strong>{p.user.full_name}</strong>{p.user.designation && <div className="muted" style={{ fontSize: 11.5 }}>{p.user.designation}</div>}{p.user.restrict_to_office && <span className="att-chip amber" style={{ marginTop: 4, display: "inline-block" }} title="Clock in/out is only allowed from the office">Office only</span>}</td>
                      <td>{p.user.employee_code || p.user.id}</td>
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
          <div className="table-pagination">
            <span>{sortedPeople.length ? `Showing ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, sortedPeople.length)} of ${sortedPeople.length}` : "0 employees"}</span>
            <label>Rows per page
              <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}>
                {[10, 25, 50].map((size) => <option key={size} value={size}>{size}</option>)}
              </select>
            </label>
            <button type="button" className="btn btn-sm btn-outline" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Previous</button>
            <span>Page {Math.min(page, pageCount)} of {pageCount}</span>
            <button type="button" className="btn btn-sm btn-outline" disabled={page >= pageCount} onClick={() => setPage((current) => current + 1)}>Next</button>
          </div>
        </>
      )}
      {exportDialog && (
        <div className="modal-overlay" onClick={() => !exporting && setExportDialog("")}>
          <div className="modal-box" role="dialog" aria-modal="true" aria-labelledby="team-attendance-export-title" onClick={(event) => event.stopPropagation()}>
            <h3 id="team-attendance-export-title">{exportDialog === "day" ? "Export Selected Day" : "Export Date Range"}</h3>
            {exportDialog === "day" ? (
              <div className="form-field">
                <label htmlFor="team-export-date">Attendance date</label>
                <input id="team-export-date" type="date" max={localDateStr()} value={exportDate} onChange={(event) => setExportDate(event.target.value)} required />
              </div>
            ) : (
              <div className="form-grid">
                <div className="form-field">
                  <label htmlFor="team-export-from">From date</label>
                  <input id="team-export-from" type="date" max={localDateStr()} value={range.from} onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))} required />
                </div>
                <div className="form-field">
                  <label htmlFor="team-export-to">To date</label>
                  <input id="team-export-to" type="date" min={range.from || undefined} max={localDateStr()} value={range.to} onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))} required />
                </div>
              </div>
            )}
            {exportDialog === "range" && rangeError && <div className="login-error" role="alert">{rangeError}</div>}
            {exportError && <div className="login-error" role="alert">{exportError}</div>}
            <div className="form-actions">
              <button type="button" className="btn btn-outline" disabled={exporting} onClick={() => setExportDialog("")}>Cancel</button>
              <button type="button" className="btn btn-primary" disabled={exporting || (exportDialog === "range" && !!rangeError)} onClick={runExport}>
                {exporting ? "Preparing…" : "Export"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
