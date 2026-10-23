import { useEffect, useState } from "react";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import ClockWidget from "../components/ClockWidget";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import RegularizeRequestModal from "../components/RegularizeRequestModal";
import RegularizationReviewModal from "../components/RegularizationReviewModal";
import AttendanceCalendar from "../components/AttendanceCalendar";
import TeamOverviewPanel from "../components/TeamOverviewPanel";
import ReentriesPanel from "../components/ReentriesPanel";
import OfficeLocationsPanel from "../components/OfficeLocationsPanel";
import OfficeRestrictionToggle from "../components/OfficeRestrictionToggle";
import ExportButton from "../components/ExportButton";
import { fmtTime, fmtHours, arrivalLabel, localDateStr, placeLabel, companyYearMonth, setCompanyTimezone } from "../utils/attendanceTime";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";

const TEAM_VIEW_ROLES = [ROLES.MANAGER, ROLES.HR_OPERATIONS, ROLES.OPERATIONS, ROLES.SUPER_ADMIN];
const APPROVER_ROLES = [ROLES.MANAGER, ROLES.HR_OPERATIONS, ROLES.SUPER_ADMIN];
const CALENDAR_MANAGER_ROLES = [ROLES.MANAGER, ROLES.HR_OPERATIONS, ROLES.SUPER_ADMIN];
const OFFICE_ADMIN_ROLES = [ROLES.SUPER_ADMIN]; // only they define geofences
const inputStyle = { border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" };

function regStatusChip(status) {
  if (status === "pending") return <span className="chip orange">Pending Review</span>;
  if (status === "approved") return <span className="chip green">Approved</span>;
  if (status === "rejected") return <span className="chip">Rejected</span>;
  return null;
}

function formatDateDDMMYYYY(value) {
  if (!value) return "—";
  const [year, month, day] = value.slice(0, 10).split("-");
  return `${day}-${month}-${year}`;
}

function HolidaysPanel({ canManage }) {
  const [holidays, setHolidays] = useState(null);
  const [year, setYear] = useState(companyYearMonth().year);
  const [form, setForm] = useState({ name: "", holiday_date: "", description: "" });
  const [error, setError] = useState("");

  const load = () => client.get("/attendance/holidays", { params: { year } }).then(({ data }) => setHolidays(data));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [year]);

  const add = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await client.post("/attendance/holidays", form);
      setForm({ name: "", holiday_date: "", description: "" });
      load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not add the holiday.");
    }
  };
  const remove = async (id) => {
    if (!window.confirm("Remove this holiday?")) return;
    await client.delete(`/attendance/holidays/${id}`);
    load();
  };

  return (
    <div className="card">
      <div className="card-title-row">
        <h3>Holiday Calendar</h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} style={{ ...inputStyle, width: 100 }} />
          <ExportButton url="/attendance/export/holidays" params={{ year }} filename={`Holidays_${year}`} />
        </div>
      </div>

      {canManage && (
        <form onSubmit={add} style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16, alignItems: "flex-end" }}>
          <div className="form-field" style={{ marginBottom: 0, flex: 1, minWidth: 160 }}>
            <label>Name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Diwali" required />
          </div>
          <div className="form-field" style={{ marginBottom: 0 }}>
            <label>Date</label>
            <input type="date" value={form.holiday_date} onChange={(e) => setForm({ ...form, holiday_date: e.target.value })} required />
          </div>
          <div className="form-field" style={{ marginBottom: 0, flex: 1, minWidth: 160 }}>
            <label>Note (optional)</label>
            <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <button className="btn btn-primary btn-sm">Add Holiday</button>
        </form>
      )}
      {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}

      {holidays === null ? <Loader /> : (
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Date</th><th>Holiday</th><th>Note</th>{canManage && <th></th>}</tr></thead>
            <tbody>
              {holidays.length === 0 && <tr className="empty-row"><td colSpan={canManage ? 4 : 3}>No holidays set for {year} yet.</td></tr>}
              {holidays.map((h) => (
                <tr key={h.id}>
                  <td>{h.holiday_date}</td>
                  <td><strong>{h.name}</strong></td>
                  <td className="muted">{h.description || "—"}</td>
                  {canManage && <td><button className="btn btn-sm btn-outline" onClick={() => remove(h.id)}>Remove</button></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RulesPanel() {
  const [reasons, setReasons] = useState(null);
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const load = () => client.get("/attendance/regularization-reasons", { params: { active_only: "false" } }).then(({ data }) => setReasons(data));
  useEffect(() => { load(); }, []);

  const add = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await client.post("/attendance/regularization-reasons", { label, description });
      setLabel(""); setDescription("");
      load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not add this rule.");
    }
  };
  const toggle = async (r) => {
    await client.put(`/attendance/regularization-reasons/${r.id}`, { is_active: !r.is_active });
    load();
  };

  return (
    <div className="card">
      <div className="card-title-row"><h3>Regularization Reasons</h3><ExportButton url="/attendance/export/regularization-reasons" filename="Regularization_Reasons" /></div>
      <p className="muted" style={{ fontSize: 12.5, marginTop: -8, marginBottom: 14 }}>
        The reasons your team can pick from when they request a missed punch to be excused.
      </p>
      <form onSubmit={add} style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16, alignItems: "flex-end" }}>
        <div className="form-field" style={{ marginBottom: 0, flex: 1, minWidth: 160 }}>
          <label>Reason</label>
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Forgot to clock in" required />
        </div>
        <div className="form-field" style={{ marginBottom: 0, flex: 1, minWidth: 200 }}>
          <label>Description (optional)</label>
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <button className="btn btn-primary btn-sm">Add Rule</button>
      </form>
      {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}

      {reasons === null ? <Loader /> : (
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Reason</th><th>Description</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {reasons.length === 0 && <tr className="empty-row"><td colSpan={4}>No reasons defined yet — add one above.</td></tr>}
              {reasons.map((r) => (
                <tr key={r.id}>
                  <td><strong>{r.label}</strong></td>
                  <td className="muted">{r.description || "—"}</td>
                  <td><span className={`chip ${r.is_active ? "green" : ""}`}>{r.is_active ? "Active" : "Retired"}</span></td>
                  <td><button className={`btn btn-sm ${r.is_active ? "btn-outline" : "btn-success"}`} onClick={() => toggle(r)}>{r.is_active ? "Retire" : "Reactivate"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AttendancePolicyPanel() {
  const [policy, setPolicy] = useState(null);
  const [bufferMinutes, setBufferMinutes] = useState("10");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    client.get("/attendance/policy")
      .then(({ data }) => {
        setCompanyTimezone(data.company_timezone);
        setPolicy(data);
        setBufferMinutes(String(data.attendance_buffer_minutes));
      })
      .catch((err) => setError(err?.response?.data?.message || "Could not load attendance policy."));
  }, []);

  const save = async (e) => {
    e.preventDefault();
    setError("");
    setSaved(false);
    setSaving(true);
    try {
      const { data } = await client.put("/attendance/policy", {
        attendance_buffer_minutes: Number(bufferMinutes),
      });
      setPolicy(data);
      setCompanyTimezone(data.company_timezone);
      setSaved(true);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save attendance policy.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card">
      <h3>Attendance Policy</h3>
      <p className="muted" style={{ fontSize: 12.5 }}>
        Official check-in is 9:30 AM. A check-in at the selected buffer boundary is In Time; later check-ins are Late.
        Standard checkout is 6:30 PM; the actual checkout punch is recorded.
      </p>
      {!policy && !error && <Loader />}
      {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
      {policy && (
        <form onSubmit={save} style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div className="form-field" style={{ marginBottom: 0 }}>
            <label htmlFor="attendance-buffer">Check-in buffer</label>
            <select id="attendance-buffer" value={bufferMinutes} onChange={(e) => { setBufferMinutes(e.target.value); setSaved(false); }}>
              {[5, 10, 15].map((minutes) => <option key={minutes} value={minutes}>{minutes} minutes</option>)}
            </select>
          </div>
          <button className="btn btn-primary btn-sm" disabled={saving}>{saving ? "Saving…" : "Save policy"}</button>
          {saved && <span className="att-chip green">Saved</span>}
        </form>
      )}
    </div>
  );
}

export default function Attendance() {
  const { user } = useAuth();
  const [tab, setTab] = useState("calendar");
  const [history, setHistory] = useState([]);
  const [histMonth, setHistMonth] = useState(localDateStr().slice(0, 7));
  const [regularizationRequests, setRegularizationRequests] = useState([]);
  const [regularizationStatus, setRegularizationStatus] = useState("all");
  const [regularizationSearch, setRegularizationSearch] = useState("");
  const [requestDateFrom, setRequestDateFrom] = useState("");
  const [requestDateTo, setRequestDateTo] = useState("");
  const [attendanceDateFrom, setAttendanceDateFrom] = useState("");
  const [attendanceDateTo, setAttendanceDateTo] = useState("");
  const [loading, setLoading] = useState(false);
  const [requestFor, setRequestFor] = useState(null);
  const [reviewing, setReviewing] = useState(null);
  const [person, setPerson] = useState(null);       // team member whose calendar is open
  const [tick, setTick] = useState(0);              // bumps after a punch / correction so views refetch
  const [timezoneVersion, setTimezoneVersion] = useState(0);

  const canSeeTeam = TEAM_VIEW_ROLES.includes(user.role);
  const canApprove = APPROVER_ROLES.includes(user.role);
  const canManageCalendar = CALENDAR_MANAGER_ROLES.includes(user.role);
  const refresh = () => setTick((t) => t + 1);
  const filteredRequests = regularizationRequests.filter((record) => {
    if (regularizationStatus !== "all" && record.regularization_status !== regularizationStatus) {
      return false;
    }
    const search = regularizationSearch.trim().toLowerCase();
    const matchesSearch = !search || [
      record.employee_name,
      record.employee_code,
      record.user_id,
    ].some((value) => String(value || "").toLowerCase().includes(search));
    const requestDate = record.regularization_request_date || "";
    const attendanceDate = record.work_date || "";
    return matchesSearch &&
      (!requestDateFrom || requestDate >= requestDateFrom) &&
      (!requestDateTo || requestDate <= requestDateTo) &&
      (!attendanceDateFrom || attendanceDate >= attendanceDateFrom) &&
      (!attendanceDateTo || attendanceDate <= attendanceDateTo);
  });

  const loadHistory = async (ym = histMonth) => {
    setLoading(true);
    const [year, month] = ym.split("-").map(Number);
    const { data } = await client.get("/attendance/history", { params: { month, year } });
    setHistory(data);
    setLoading(false);
  };
  const loadRegularizationRequests = async () => {
    setLoading(true);
    try {
      const { data } = await client.get("/attendance/regularization-requests", { params: { status: "all" } });
      setRegularizationRequests(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tab === "mine") loadHistory();
    if (tab === "approvals") loadRegularizationRequests();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, tick]);
  useEffect(() => {
    setHistMonth(localDateStr().slice(0, 7));
  }, [timezoneVersion]);
  const tabBtn = (key, label) => (
    <button className={`btn btn-sm ${tab === key ? "btn-primary" : "btn-outline"}`} onClick={() => { setTab(key); if (key !== "team") setPerson(null); }}>{label}</button>
  );

  return (
    <AppLayout title="Attendance" subtitle="Clock in/out with your location, see your calendar, request regularization and export your history.">
      <div className="section-gap">
        <ClockWidget onPunch={refresh} onTimezoneChange={() => setTimezoneVersion((v) => v + 1)} />
      </div>

      <div className="tag-list section-gap">
        {tabBtn("calendar", "My Calendar")}
        {tabBtn("mine", "My History")}
        {canSeeTeam && tabBtn("team", "Team Attendance")}
        {canApprove && tabBtn("approvals", `Regularization Requests${regularizationRequests.filter((record) => record.regularization_status === "pending").length > 0 ? ` (${regularizationRequests.filter((record) => record.regularization_status === "pending").length})` : ""}`)}
        {canSeeTeam && tabBtn("reentries", "Re-entries")}
        {tabBtn("holidays", "Holidays")}
        {canManageCalendar && tabBtn("rules", "Regularization Rules")}
        {canApprove && tabBtn("policy", "Attendance Policy")}
        {tabBtn("offices", "Office Locations")}
      </div>

      {tab === "calendar" && (
        <div className="card">
          <div className="card-title-row"><h3>My Attendance Calendar</h3></div>
          <AttendanceCalendar endpoint="/attendance/my-calendar" refreshKey={tick} timezoneVersion={timezoneVersion} onChanged={refresh} />
        </div>
      )}

      {tab === "mine" && (
        <div className="card">
          <div className="card-title-row" style={{ flexWrap: "wrap", gap: 10 }}>
            <h3>My Attendance — List</h3>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="month" value={histMonth} max={localDateStr().slice(0, 7)} style={inputStyle}
                onChange={(e) => { if (e.target.value) { setHistMonth(e.target.value); loadHistory(e.target.value); } }} />
              <ExportButton
                url="/attendance/export/my"
                params={{ month: Number(histMonth.split("-")[1]), year: Number(histMonth.split("-")[0]) }}
                filename={`My_Attendance_${histMonth}`} label="Export to Excel"
              />
            </div>
          </div>
          {loading ? <Loader /> : (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Date</th><th>Clock In</th><th>Arrival</th><th>Clock Out</th><th>Hours</th><th>Check-ins</th><th>Where</th><th>Status</th><th>Regularization</th><th></th></tr></thead>
                <tbody>
                  {history.length === 0 && <tr className="empty-row"><td colSpan={10}>No attendance records for this month.</td></tr>}
                  {history.map((r) => {
                    const places = [...new Set((r.sessions || []).flatMap((x) => [x.clock_in_within_geofence, x.clock_out && x.clock_out_within_geofence]).filter((v) => v !== null && v !== undefined && v !== ""))];
                    return (
                      <tr key={r.id}>
                        <td>{r.work_date}</td>
                        <td>{fmtTime(r.clock_in)}</td>
                        <td><span className={`att-chip ${r.check_in_status === "late" ? "red" : r.check_in_status === "in_time" ? "green" : ""}`}>{arrivalLabel(r.check_in_status)}</span></td>
                        <td>{r.clock_out ? fmtTime(r.clock_out) : "—"}</td>
                        <td>{fmtHours(r.total_hours)}</td>
                        <td>{r.session_count || "—"}{r.reentry_count > 0 && <span className="att-chip amber" style={{ marginLeft: 6 }}>↻ {r.reentry_count}</span>}</td>
                        <td>
                          {places.length === 0 ? <span className="muted">—</span> : places.map((v) => { const p = placeLabel(v); return <span key={String(v)} className={`att-chip ${p.cls}`} style={{ marginRight: 4 }}>{p.text}</span>; })}
                        </td>
                        <td><Badge status={r.status} /></td>
                        <td>
                          {regStatusChip(r.regularization_status)}
                          {r.regularization_status === "rejected" && r.regularization_review_comment && (
                            <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>{r.regularization_review_comment}</div>
                          )}
                          {r.edited_by_name && <div className="muted" style={{ fontSize: 11 }}>✎ corrected by {r.edited_by_name}</div>}
                        </td>
                        <td>
                          {!r.is_regularized && r.regularization_status !== "pending" && r.status !== "regularized" && (
                            <button className="btn btn-sm btn-outline" onClick={() => setRequestFor(r)}>Regularize</button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "team" && canSeeTeam && !person && (
        <TeamOverviewPanel onOpenPerson={setPerson} refreshKey={tick} timezoneVersion={timezoneVersion} />
      )}
      {tab === "team" && canSeeTeam && person && (
        <div className="card">
          <div className="card-title-row">
            <h3>{person.full_name}'s Calendar <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>{person.employee_code}{person.designation ? ` · ${person.designation}` : ""}</span></h3>
            <button className="btn btn-sm btn-outline" onClick={() => setPerson(null)}>← Back to team</button>
          </div>
          {canApprove && <p className="muted" style={{ fontSize: 12.5, marginTop: -6, marginBottom: 12 }}>Click a day to see every check-in and where it happened — you can edit the times or regularize the day directly, no request needed.</p>}
          {canApprove && person.id !== user.id && <OfficeRestrictionToggle key={person.id} person={person} onChanged={refresh} />}
          <AttendanceCalendar
            endpoint={`/attendance/team/${person.id}/calendar`} manager={canApprove} exportUserId={person.id}
            refreshKey={tick} timezoneVersion={timezoneVersion} onChanged={refresh}
          />
        </div>
      )}

      {tab === "approvals" && canApprove && (
        <div className="card">
          <div className="card-title-row" style={{ flexWrap: "wrap", gap: 10 }}>
            <h3>Regularization Requests</h3>
            <div style={{ display: "flex", gap: 8 }}>
              <ExportButton url="/attendance/export/regularization-requests" params={{ status: "pending" }} filename="Regularization_Pending" label="Export pending" />
              <ExportButton url="/attendance/export/regularization-requests" params={{ status: "all" }} filename="Regularization_All" label="Export all history" />
            </div>
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginTop: -8, marginBottom: 12 }}>
            {user.role === ROLES.MANAGER ? "Requests from your direct reports." : "Requests from everyone."} You can also regularize or correct any day directly from <em>Team Attendance → a person's calendar</em>.
          </p>
          <div className="regularization-filter-row">
            <div className="form-field" style={{ margin: 0 }}>
              <label htmlFor="regularization-status">Status</label>
              <select id="regularization-status" value={regularizationStatus}
                onChange={(event) => setRegularizationStatus(event.target.value)}>
                <option value="all">All</option>
                <option value="pending">Pending</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>
            <div className="form-field" style={{ margin: 0 }}>
              <label htmlFor="regularization-search">Search employee name or ID</label>
              <input id="regularization-search" type="search" value={regularizationSearch}
                onChange={(event) => setRegularizationSearch(event.target.value)}
                placeholder="Name, employee code, or ID" />
            </div>
            <div className="form-field" style={{ margin: 0 }}>
              <label htmlFor="request-date-from">Request Date from</label>
              <input id="request-date-from" type="date" value={requestDateFrom}
                max={requestDateTo || undefined}
                onChange={(event) => setRequestDateFrom(event.target.value)} />
            </div>
            <div className="form-field" style={{ margin: 0 }}>
              <label htmlFor="request-date-to">Request Date to</label>
              <input id="request-date-to" type="date" value={requestDateTo}
                min={requestDateFrom || undefined}
                onChange={(event) => setRequestDateTo(event.target.value)} />
            </div>
            <div className="form-field" style={{ margin: 0 }}>
              <label htmlFor="attendance-date-from">Attendance Date from</label>
              <input id="attendance-date-from" type="date" value={attendanceDateFrom}
                max={attendanceDateTo || undefined}
                onChange={(event) => setAttendanceDateFrom(event.target.value)} />
            </div>
            <div className="form-field" style={{ margin: 0 }}>
              <label htmlFor="attendance-date-to">Attendance Date to</label>
              <input id="attendance-date-to" type="date" value={attendanceDateTo}
                min={attendanceDateFrom || undefined}
                onChange={(event) => setAttendanceDateTo(event.target.value)} />
            </div>
          </div>
          {loading ? <Loader /> : (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Employee</th><th>Employee ID</th><th>Request Date</th><th>Attendance Date</th><th>Reason</th><th>Note</th><th></th></tr></thead>
                <tbody>
                  {filteredRequests.length === 0 && <tr className="empty-row"><td colSpan={8}>{regularizationRequests.length ? "No requests match these filters." : "No regularization requests."}</td></tr>}
                  {filteredRequests.map((r) => (
                    <tr key={r.id}>
                      <td><strong>{r.employee_name}</strong></td>
                      <td>{r.employee_code || r.user_id}</td>
                      <td>{formatDateDDMMYYYY(r.regularization_request_date)}</td>
                      <td>{formatDateDDMMYYYY(r.work_date)}</td>
                      <td>{regStatusChip(r.regularization_status)}</td>
                      <td>{r.regularization_reason_label}</td>
                      <td className="muted" style={{ maxWidth: 260 }}>{r.regularization_note || "—"}</td>
                      <td>
                        {r.regularization_status === "pending" ? (
                          <button className="btn btn-sm btn-primary" onClick={() => setReviewing(r)}>Review</button>
                        ) : (
                          <span className="muted" title={r.regularization_review_comment || ""}>
                            {r.regularization_reviewed_by_name ? `Reviewed by ${r.regularization_reviewed_by_name}` : "Reviewed"}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "reentries" && canSeeTeam && <ReentriesPanel />}
      {tab === "holidays" && <HolidaysPanel canManage={canManageCalendar} />}
      {tab === "rules" && canManageCalendar && <RulesPanel />}
      {tab === "policy" && canApprove && <AttendancePolicyPanel />}
      {tab === "offices" && <OfficeLocationsPanel canManage={OFFICE_ADMIN_ROLES.includes(user.role)} />}

      {requestFor && (
        <RegularizeRequestModal
          record={requestFor}
          onClose={() => setRequestFor(null)}
          onDone={() => { setRequestFor(null); refresh(); }}
        />
      )}
      {reviewing && (
        <RegularizationReviewModal
          record={reviewing}
          onClose={() => setReviewing(null)}
          onDone={() => { setReviewing(null); refresh(); }}
        />
      )}
    </AppLayout>
  );
}
