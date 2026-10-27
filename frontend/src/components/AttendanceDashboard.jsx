import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import client from "../api/client";
import Loader from "./Loader";
import DashboardTopWidgets from "./DashboardTopWidgets";
import DashboardPendingRequests from "./DashboardPendingRequests";
import { buildAttendanceSummaryCsv } from "../utils/attendanceSummaryCsv";
import {
  addDays,
  attendanceMetrics,
  buildAttendanceTrend,
  dateKeys,
  dateRange,
  dateRangeError,
  dayRecordFor,
  formatMinutes,
  formatPercent,
  parseDateKey,
} from "../utils/attendanceDashboard";
import { fmtTime, localDateStr, setCompanyTimezone } from "../utils/attendanceTime";

const inputStyle = { border: "1px solid var(--color-border)", borderRadius: 8, padding: "8px 10px", background: "#fff" };
const todayKey = () => localDateStr();
function monthParts(date) {
  const parsed = parseDateKey(date);
  return { year: parsed.getUTCFullYear(), month: parsed.getUTCMonth() + 1 };
}

function formatDate(date, options = { day: "numeric", month: "short" }) {
  return parseDateKey(date).toLocaleDateString("en-IN", { ...options, timeZone: "UTC" });
}

function statusFor(employee, date, holidays, today = todayKey()) {
  const record = dayRecordFor(employee, date);
  if (employee?.approved_leave_dates?.includes(date)) return "On leave";
  if ((holidays || []).some((holiday) => holiday.holiday_date === date) || record?.status === "holiday") return "Holiday";
  if (record && (["present", "regularized", "half_day"].includes(record.status) || record.clock_in)) {
    return record.status === "half_day" ? "Half day" : "Present";
  }
  const weekday = parseDateKey(date).getUTCDay();
  const scheduled = (weekday >= 1 && weekday <= 5) || ["absent", "on_leave"].includes(record?.status);
  if (!scheduled) return "Non-working day";
  if (date === today && !record) return "Not clocked in";
  return date <= today ? "Absent" : "Scheduled";
}

function downloadAttendanceSummary(employees, dates, holidays, policy, range) {
  if (!employees.length) {
    window.alert("No attendance records are available for export.");
    return;
  }
  const csv = buildAttendanceSummaryCsv(employees, dates, holidays, policy, range);
  const url = window.URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `Attendance_Summary_${range.from}_to_${range.to}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
}

function employeeLeaves(data) {
  const dates = new Set();
  for (const leave of data.leaves || []) {
    if (leave.status !== "approved") continue;
    let current = leave.start_date;
    while (current <= leave.end_date) {
      dates.add(current);
      current = addDays(current, 1);
    }
  }
  return [...dates];
}

function mergeCalendars(payloads, user) {
  const first = payloads[0] || {};
  const records = new Map();
  const holidays = new Map();
  const leaves = new Map();
  for (const payload of payloads) {
    for (const record of payload.records || []) records.set(record.work_date, record);
    for (const holiday of payload.holidays || []) holidays.set(holiday.holiday_date, holiday);
    for (const leave of payload.leaves || []) {
      const key = `${leave.start_date}-${leave.end_date}-${leave.status}`;
      leaves.set(key, leave);
    }
  }
  return {
    user: first.user || user,
    records: [...records.values()].sort((a, b) => a.work_date.localeCompare(b.work_date)),
    holidays: [...holidays.values()],
    leaves: [...leaves.values()],
  };
}

async function fetchMyCalendarRange(user, range) {
  const months = new Map();
  for (const date of dateKeys(range.from, range.to)) {
    const { year, month } = monthParts(date);
    months.set(`${year}-${month}`, { year, month });
  }
  const responses = await Promise.all(
    [...months.values()].map(({ year, month }) => (
      client.get("/attendance/my-calendar", { params: { year, month } })
    )),
  );
  return mergeCalendars(responses.map((response) => response.data), user);
}

async function fetchTeamCalendarRange(employee, range) {
  const months = new Map();
  for (const date of dateKeys(range.from, range.to)) {
    const { year, month } = monthParts(date);
    months.set(`${year}-${month}`, { year, month });
  }
  const responses = await Promise.all(
    [...months.values()].map(({ year, month }) => (
      client.get(`/attendance/team/${employee.id}/calendar`, { params: { year, month } })
    )),
  );
  return mergeCalendars(responses.map((response) => response.data), employee);
}

function normalizeEmployee(employee) {
  return {
    ...employee,
    records: employee.records || [],
    approved_leave_dates: employee.approved_leave_dates || [],
    is_demo_account: Boolean(employee.is_demo_account || employee.employee_code?.startsWith("DEMO-")),
  };
}

function statusClass(status) {
  if (status === "Present") return "dashboard-status present";
  if (status === "Holiday" || status === "Non-working day" || status === "On leave") return "dashboard-status neutral";
  if (status === "Scheduled" || status === "Not clocked in") return "dashboard-status scheduled";
  return "dashboard-status absent";
}

function MetricCard({ label, value, note, color = "blue" }) {
  return (
    <div className={`dashboard-metric dashboard-metric-${color}`}>
      <div className="dashboard-metric-icon" aria-hidden="true">
        {color === "green" ? "✓" : color === "orange" ? "◷" : color === "purple" ? "◉" : "▦"}
      </div>
      <div className="dashboard-metric-label">{label}</div>
      <div className="dashboard-metric-value">{value}</div>
      {note && <div className="dashboard-metric-note">{note}</div>}
    </div>
  );
}

function AttendanceChart({ trend, emptyMessage = "No attendance data is available for this period." }) {
  const chartData = trend.map((item) => ({
    ...item,
    label: formatDate(item.date, { day: "numeric", month: "short" }),
  }));

  if (!chartData.length || chartData.every((item) => item.checkIn === null && item.checkOut === null && item.attendancePct === null)) {
    return <div className="dashboard-chart-empty">{emptyMessage}</div>;
  }

  return (
    <div className="dashboard-chart" role="img" aria-label="Check-in, check-out and attendance trend">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 12, right: 10, bottom: 4, left: 2 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e7edf5" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "#667085" }}
            interval="preserveStartEnd"
            angle={-30}
            textAnchor="end"
            height={52}
            minTickGap={8}
            tickMargin={12}
          />
          <YAxis yAxisId="time" domain={[480, 1200]} tickFormatter={formatMinutes} tick={{ fontSize: 10, fill: "#667085" }} width={65} />
          <YAxis yAxisId="percent" orientation="right" domain={[0, 100]} tickFormatter={(value) => `${value}%`} tick={{ fontSize: 10, fill: "#667085" }} width={42} />
          <Tooltip
            labelFormatter={(label, payload) => payload?.[0]?.payload?.date ? formatDate(payload[0].payload.date, { weekday: "long", day: "numeric", month: "long" }) : label}
            formatter={(value, name) => [
              name === "Attendance" ? formatPercent(value) : formatMinutes(value),
              name,
            ]}
            contentStyle={{ borderRadius: 9, borderColor: "#e4e7ec", fontSize: 12 }}
          />
          <Line yAxisId="time" type="monotone" dataKey="checkIn" name="Check-in" stroke="#2f7cf6" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} connectNulls />
          <Line yAxisId="time" type="monotone" dataKey="checkOut" name="Check-out" stroke="#12a361" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} connectNulls />
          <Line yAxisId="percent" type="monotone" dataKey="attendancePct" name="Attendance" stroke="#f2650a" strokeWidth={1.75} strokeDasharray="5 4" dot={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
      <div className="dashboard-chart-legend">
        <span><i style={{ background: "#2f7cf6" }} />Check-in</span>
        <span><i style={{ background: "#12a361" }} />Check-out</span>
        <span><i style={{ background: "#f2650a" }} />Attendance %</span>
      </div>
    </div>
  );
}

function AttendanceRecordsTable({ employee, dates, holidays, title = "My Attendance Details" }) {
  const rows = dates.slice().reverse().map((date) => ({
    date,
    record: dayRecordFor(employee, date),
    status: statusFor(employee, date, holidays, todayKey()),
  }));
  return (
    <div className="card">
      <div className="card-title-row"><h3>{title}</h3><span className="muted" style={{ fontSize: 12 }}>{rows.length} date(s)</span></div>
      <div className="table-wrap">
        <table className="data-table">
          <thead><tr><th>Date</th><th>Day</th><th>Check-in</th><th>Check-out</th><th>Status</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr className="empty-row"><td colSpan={5}>No attendance records are available for this period.</td></tr>}
            {rows.map(({ date, record, status }) => (
              <tr key={date}>
                <td>{formatDate(date, { day: "numeric", month: "short", year: "numeric" })}</td>
                <td>{formatDate(date, { weekday: "long" })}</td>
                <td>{record?.clock_in ? fmtTime(record.clock_in) : "—"}</td>
                <td>{record?.clock_out ? fmtTime(record.clock_out) : "—"}</td>
                <td><span className={statusClass(status)}>{status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DateRangeFilter({ draft, onChange, onApply, onReset, error }) {
  return (
    <form
      className="dashboard-date-range"
      onSubmit={(event) => {
        event.preventDefault();
        onApply();
      }}
    >
      <label className="dashboard-field">
        <span>From Date</span>
        <input type="date" value={draft.from} max={draft.to || undefined} onChange={(event) => onChange({ ...draft, from: event.target.value })} style={inputStyle} />
      </label>
      <label className="dashboard-field">
        <span>To Date</span>
        <input type="date" value={draft.to} min={draft.from || undefined} onChange={(event) => onChange({ ...draft, to: event.target.value })} style={inputStyle} />
      </label>
      <button type="submit" className="btn btn-sm btn-primary">Apply Filter</button>
      <button type="button" className="btn btn-sm btn-outline" onClick={onReset}>Reset</button>
      {error && <div className="dashboard-date-range-error" role="alert">{error}</div>}
    </form>
  );
}

function ProgressMetric({ label, value }) {
  const progress = value === null || value === undefined ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div className="dashboard-progress-item">
      <div className="flex-between"><span>{label}</span><strong>{formatPercent(value)}</strong></div>
      <div className="dashboard-progress-track"><span style={{ width: `${progress}%` }} /></div>
    </div>
  );
}

function SummaryCards({ metrics, manager = false, absentToday = 0, totalEmployees = 0, assignedIn, assignedOut }) {
  if (manager) {
    return (
      <div className="dashboard-metric-grid">
        <MetricCard label="Total Employees" value={totalEmployees} note="In your attendance scope" />
        <MetricCard label="On-Time Check-In" value={formatPercent(metrics.onTimeCheckInPct)} note="Selected period" color="blue" />
        <MetricCard label="On-Time Check-Out" value={formatPercent(metrics.onTimeCheckOutPct)} note="Selected period" color="green" />
        <MetricCard label="Employees Absent" value={absentToday} note="Selected date" color="orange" />
      </div>
    );
  }
  return (
    <div className="dashboard-metric-grid employee">
      <MetricCard label="Average Check-In" value={formatMinutes(metrics.averageCheckIn)} note={`${formatPercent(metrics.onTimeCheckInPct)} on time · assigned ${assignedIn}`} />
      <MetricCard label="Average Check-Out" value={formatMinutes(metrics.averageCheckOut)} note={`${formatPercent(metrics.onTimeCheckOutPct)} on time · assigned ${assignedOut}`} color="green" />
      <MetricCard label="Overall Attendance" value={formatPercent(metrics.attendancePct)} note={`${metrics.presentDays} present · ${metrics.absentDays} absent · ${metrics.holidays} holidays`} color="purple" />
    </div>
  );
}

function EmployeeDetail({ employee, from, to, policy, onClose }) {
  const range = { from, to };
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setPayload(null);
    setError("");
    setLoading(true);

    fetchTeamCalendarRange(employee, range)
      .then((data) => { if (active) setPayload(data); })
      .catch((err) => { if (active) setError(err?.response?.data?.message || "Could not load this employee's attendance."); })
      .finally(() => { if (active) setLoading(false); });

    return () => { active = false; };
  }, [employee, range.from, range.to]);

  if (loading) return <div className="card"><Loader /></div>;
  if (error) return <div className="login-error" role="alert">{error}</div>;
  if (!payload) return null;

  const detailEmployee = normalizeEmployee({
    ...employee,
    records: payload.records || [],
    approved_leave_dates: employeeLeaves(payload),
  });
  const holidays = payload.holidays || [];
  const dates = dateKeys(range.from, range.to);
  const metrics = attendanceMetrics([detailEmployee], dates, holidays, policy);
  const trend = buildAttendanceTrend([detailEmployee], dates, holidays, policy);

  return (
    <section className="dashboard-detail section-gap">
      <div className="dashboard-section-heading">
        <div><h2>{employee.full_name}</h2><p>{employee.employee_code} · {employee.department || "Unassigned"} · Individual attendance</p></div>
        <button className="btn btn-sm btn-outline" onClick={onClose}>Close details</button>
      </div>
      <div className="dashboard-detail-metrics">
        <MetricCard label="Attendance" value={formatPercent(metrics.attendancePct)} note={`${metrics.presentDays}/${metrics.eligibleDays} eligible days`} />
        <MetricCard label="On-Time Check-In" value={formatPercent(metrics.onTimeCheckInPct)} note="Assigned check-in schedule" />
        <MetricCard label="On-Time Check-Out" value={formatPercent(metrics.onTimeCheckOutPct)} note="Assigned check-out schedule" color="green" />
        <MetricCard label="Average Check-In" value={formatMinutes(metrics.averageCheckIn)} />
        <MetricCard label="Average Check-Out" value={formatMinutes(metrics.averageCheckOut)} color="green" />
      </div>
      <div className="card">
        <div className="card-title-row"><div><h3>Attendance Trend</h3><span className="muted" style={{ fontSize: 12 }}>{formatDate(range.from)} – {formatDate(range.to)} · {formatPercent(metrics.attendancePct)} attendance</span></div></div>
        <AttendanceChart trend={trend} />
      </div>
      <AttendanceRecordsTable employee={detailEmployee} dates={dates} holidays={holidays} title={`${employee.full_name} Attendance Records`} />
    </section>
  );
}

function TeamAttendanceTable({ employees, dates, holidays, policy, selectedDate, search, teamFilter, statusFilter, onSelectEmployee }) {
  const rows = filterTeamEmployees(employees, selectedDate, holidays, search, teamFilter, statusFilter).map((employee) => {
    const metrics = attendanceMetrics([employee], dates, holidays, policy);
    const status = statusFor(employee, selectedDate, holidays, todayKey());
    return { employee, metrics, status };
  });

  return (
    <div className="card">
      <div className="card-title-row"><div><h3>Employee Attendance Details</h3><div className="muted" style={{ fontSize: 12, marginTop: 3 }}>Select an employee for attendance records within the selected date range</div></div></div>
      <div className="table-wrap">
        <table className="data-table">
          <thead><tr><th>Employee</th><th>Team</th><th>Avg. Check-In</th><th>Avg. Check-Out</th><th>On-Time In</th><th>On-Time Out</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr className="empty-row"><td colSpan={8}>No employees match these filters.</td></tr>}
            {rows.map(({ employee, metrics, status }) => (
              <tr key={employee.id}>
                <td><strong>{employee.full_name}</strong><div className="muted" style={{ fontSize: 11 }}>{employee.employee_code}{employee.is_demo || employee.is_demo_account ? " · Demo" : ""}</div></td>
                <td>{employee.department || "Unassigned"}</td>
                <td>{formatMinutes(metrics.averageCheckIn)}</td>
                <td>{formatMinutes(metrics.averageCheckOut)}</td>
                <td>{formatPercent(metrics.onTimeCheckInPct)}</td>
                <td>{formatPercent(metrics.onTimeCheckOutPct)}</td>
                <td><span className={statusClass(status)}>{status}</span></td>
                <td><button type="button" className="btn btn-sm btn-outline" onClick={() => onSelectEmployee(employee)}>Details</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function filterTeamEmployees(employees, selectedDate, holidays, search, teamFilter, statusFilter) {
  return employees.filter((employee) => {
    const status = statusFor(employee, selectedDate, holidays, todayKey());
    return (
      (!teamFilter || (employee.department || "Unassigned") === teamFilter)
      && (!statusFilter || status.toLowerCase() === statusFilter.toLowerCase())
      && (!search || `${employee.full_name} ${employee.employee_code} ${employee.department}`.toLowerCase().includes(search.toLowerCase()))
    );
  });
}

function TeamSummaryTable({ employees, dates, holidays, policy }) {
  const teams = [...new Set(employees.map((employee) => employee.department || "Unassigned"))].sort();
  return (
    <div className="card">
      <div className="card-title-row"><h3>Team-Wise Attendance</h3></div>
      <div className="table-wrap">
        <table className="data-table">
          <thead><tr><th>Team</th><th>Employees</th><th>Avg. Check-In</th><th>Avg. Check-Out</th><th>On-Time Attendance</th></tr></thead>
          <tbody>
            {teams.length === 0 && <tr className="empty-row"><td colSpan={5}>No team attendance is available.</td></tr>}
            {teams.map((team) => {
              const members = employees.filter((employee) => (employee.department || "Unassigned") === team);
              const metrics = attendanceMetrics(members, dates, holidays, policy);
              return (
                <tr key={team}>
                  <td><strong>{team}</strong></td><td>{members.length}</td>
                  <td>{formatMinutes(metrics.averageCheckIn)}</td><td>{formatMinutes(metrics.averageCheckOut)}</td>
                  <td>{formatPercent(metrics.onTimeCheckInPct)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ManagerDashboard({ user, summary, summaryLoading, summaryError, pendingRequests }) {
  const defaultRange = useMemo(() => dateRange("monthly", todayKey()), []);
  const [draftRange, setDraftRange] = useState(defaultRange);
  const [range, setRange] = useState(defaultRange);
  const [rangeError, setRangeError] = useState("");
  const [selectedDate, setSelectedDate] = useState(todayKey());
  const [teamFilter, setTeamFilter] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [response, setResponse] = useState(null);
  const [policy, setPolicy] = useState({ official_check_in: "09:30", official_check_out: "18:30", attendance_buffer_minutes: 10 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    client.get("/attendance/team/analytics", { params: range })
      .then(({ data }) => {
        if (!active) return;
        if (data.company_timezone) setCompanyTimezone(data.company_timezone);
        if (data.policy) setPolicy(data.policy);
        const employees = (data.employees || []).map(normalizeEmployee);
        setResponse({ ...data, employees });
      })
      .catch((err) => {
        if (active) setError(err?.response?.data?.message || "Could not load team attendance analytics.");
      })
      .finally(() => { if (active) setLoading(false); });

    return () => { active = false; };
  }, [range.from, range.to]);

  const applyRange = () => {
    const validationError = dateRangeError(draftRange.from, draftRange.to);
    setRangeError(validationError);
    if (!validationError) setRange({ ...draftRange });
  };

  const resetRange = () => {
    const nextRange = dateRange("monthly", todayKey());
    setDraftRange(nextRange);
    setRange(nextRange);
    setRangeError("");
  };

  const allEmployees = response?.employees || [];
  const teams = [...new Set(allEmployees.map((employee) => employee.department || "Unassigned"))].sort();
  const employees = allEmployees.filter((employee) => !teamFilter || (employee.department || "Unassigned") === teamFilter);
  const dates = dateKeys(range.from, range.to);
  const holidays = response?.holidays || [];
  const metrics = attendanceMetrics(employees, dates, holidays, policy);
  const trend = buildAttendanceTrend(employees, dates, holidays, policy);
  const exportEmployees = filterTeamEmployees(allEmployees, selectedDate, holidays, search, teamFilter, statusFilter);
  const absentSelectedDate = selectedDate > todayKey()
    ? 0
    : employees.filter((employee) => statusFor(employee, selectedDate, holidays, todayKey()) === "Absent").length;

  return (
    <div className="attendance-dashboard">
      <section className="dashboard-welcome">
        <div>
          <div className="dashboard-eyebrow">MANAGER OVERVIEW</div>
          <h2>Good {new Date().getHours() < 12 ? "morning" : new Date().getHours() < 17 ? "afternoon" : "evening"}, {user.full_name.split(" ")[0]}</h2>
          <p>Track your team's attendance, review requests and explore individual trends.</p>
          {allEmployees.some((employee) => employee.is_demo_account) && <span className="dashboard-demo-label">Includes marked demo employee accounts</span>}
        </div>
        <div className="dashboard-date-card">
          <span>Today</span><strong>{formatDate(todayKey(), { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</strong>
          <small>Attendance policy · {policy.official_check_in}–{policy.official_check_out}</small>
        </div>
      </section>

      <DashboardTopWidgets summary={summary} loading={summaryLoading} error={summaryError} />
      {pendingRequests}

      <DateRangeFilter
        draft={draftRange}
        onChange={setDraftRange}
        onApply={applyRange}
        onReset={resetRange}
        error={rangeError}
      />

      <div className="dashboard-toolbar">
        <label className="dashboard-field"><span>Search team</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Employee name, ID or team" style={inputStyle} /></label>
        <label className="dashboard-field"><span>Selected date</span><input type="date" value={selectedDate} max={todayKey()} onChange={(event) => event.target.value && setSelectedDate(event.target.value)} style={inputStyle} /></label>
      </div>

      {error && <div className="login-error" role="alert">{error}</div>}
      {loading ? <Loader /> : response && (
        <>
          <SummaryCards manager totalEmployees={employees.length} metrics={metrics} absentToday={absentSelectedDate} />
          <div className="card dashboard-analytics-card">
            <div className="card-title-row dashboard-analytics-header">
              <div><h3>Team Attendance Overview</h3><div className="muted" style={{ fontSize: 12, marginTop: 3 }}>{formatDate(range.from, { day: "numeric", month: "short" })} – {formatDate(range.to, { day: "numeric", month: "short", year: "numeric" })} · Attendance {formatPercent(metrics.attendancePct)}</div></div>
              <div className="dashboard-controls">
                <select value={teamFilter} onChange={(event) => setTeamFilter(event.target.value)} aria-label="Filter team" style={inputStyle}>
                  <option value="">All teams</option>
                  {teams.map((team) => <option key={team} value={team}>{team}</option>)}
                </select>
              </div>
            </div>
            <AttendanceChart trend={trend} />
          </div>
          <div className="dashboard-quick-actions">
            <Link to="/employees" className="btn btn-sm btn-outline">Manage Teams</Link>
            <Link to="/attendance?tab=team" className="btn btn-sm btn-outline">View Reports</Link>
            <button type="button" className="btn btn-sm btn-outline" onClick={() => downloadAttendanceSummary(exportEmployees, dates, holidays, policy, range)}>Export CSV</button>
            <Link to="/attendance?tab=policy" className="btn btn-sm btn-outline">Manage Timings</Link>
          </div>
          <div className="two-col dashboard-table-row">
            <TeamSummaryTable employees={allEmployees} dates={dates} holidays={holidays} policy={policy} />
            <div className="card dashboard-period-summary">
              <div className="card-title-row"><h3>Period Summary</h3></div>
              <ProgressMetric label="Overall attendance" value={metrics.attendancePct} />
              <ProgressMetric label="On-time check-in" value={metrics.onTimeCheckInPct} />
              <ProgressMetric label="On-time check-out" value={metrics.onTimeCheckOutPct} />
              <div className="muted" style={{ fontSize: 11, marginTop: 14 }}>
                {metrics.eligibleDays} eligible employee-days · {metrics.totalDays} calendar days. Holidays and approved leave are excluded.
              </div>
            </div>
          </div>
          <div className="dashboard-filter-row">
            <label className="dashboard-field"><span>Team</span><select value={teamFilter} onChange={(event) => setTeamFilter(event.target.value)} style={inputStyle}><option value="">All teams</option>{teams.map((team) => <option key={team} value={team}>{team}</option>)}</select></label>
            <label className="dashboard-field"><span>Status on selected date</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} style={inputStyle}><option value="">All statuses</option>{["Present", "Absent", "On leave", "Holiday", "Non-working day", "Scheduled", "Not clocked in"].map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
          </div>
          <TeamAttendanceTable
            employees={allEmployees}
            dates={dates}
            holidays={holidays}
            policy={policy}
            selectedDate={selectedDate}
            search={search}
            teamFilter={teamFilter}
            statusFilter={statusFilter}
            onSelectEmployee={setSelectedEmployee}
          />
          {selectedEmployee && (
            <EmployeeDetail
              key={`${selectedEmployee.id}-${range.from}-${range.to}`}
              employee={selectedEmployee}
              from={range.from}
              to={range.to}
              policy={policy}
              onClose={() => setSelectedEmployee(null)}
            />
          )}
        </>
      )}
    </div>
  );
}

function EmployeeDashboard({ user, summary, summaryLoading, summaryError }) {
  const defaultRange = useMemo(() => dateRange("monthly", todayKey()), []);
  const [draftRange, setDraftRange] = useState(defaultRange);
  const [range, setRange] = useState(defaultRange);
  const [rangeError, setRangeError] = useState("");
  const [selectedDate, setSelectedDate] = useState(todayKey());
  const [calendar, setCalendar] = useState(null);
  const [policy, setPolicy] = useState({ official_check_in: "09:30", official_check_out: "18:30", attendance_buffer_minutes: 10 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      fetchMyCalendarRange(user, range),
      client.get("/attendance/policy"),
    ])
      .then(([data, policyResponse]) => {
        if (!active) return;
        const currentPolicy = policyResponse.data;
        setPolicy(currentPolicy);
        if (currentPolicy.company_timezone) setCompanyTimezone(currentPolicy.company_timezone);
        const employee = normalizeEmployee({
          id: user.id,
          employee_code: user.employee_code,
          full_name: user.full_name,
          designation: user.designation,
          department: user.department,
          records: (data.records || []).filter((record) => record.work_date >= range.from && record.work_date <= range.to),
          approved_leave_dates: employeeLeaves(data),
        });
        setCalendar({ ...data, employee });
      })
      .catch((err) => { if (active) setError(err?.response?.data?.message || "Could not load your attendance."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [user, range.from, range.to]);

  const applyRange = () => {
    const validationError = dateRangeError(draftRange.from, draftRange.to);
    setRangeError(validationError);
    if (!validationError) setRange({ ...draftRange });
  };

  const resetRange = () => {
    const nextRange = dateRange("monthly", todayKey());
    setDraftRange(nextRange);
    setRange(nextRange);
    setRangeError("");
  };

  const employee = calendar?.employee;
  const dates = dateKeys(range.from, range.to);
  const holidays = calendar?.holidays || [];
  const metrics = attendanceMetrics(employee ? [employee] : [], dates, holidays, policy);
  const trend = buildAttendanceTrend(employee ? [employee] : [], dates, holidays, policy);
  const selectedRecord = dayRecordFor(employee, selectedDate);
  const selectedStatus = employee ? statusFor(employee, selectedDate, holidays, todayKey()) : "No data";

  return (
    <div className="attendance-dashboard employee-dashboard">
      <section className="dashboard-welcome employee">
        <div>
          <div className="dashboard-eyebrow">MY ATTENDANCE</div>
          <h2>Hello, {employee?.full_name || user.full_name}</h2>
          <p>{employee?.designation || user.designation || "Employee"} · {employee?.employee_code || user.employee_code}</p>
        </div>
        <div className="dashboard-date-card">
          <span>Today</span><strong>{formatDate(todayKey(), { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</strong>
          <small>{calendar?.user?.department || user.department || "Employee"} · {policy.official_check_in}–{policy.official_check_out}</small>
        </div>
      </section>

      <DashboardTopWidgets summary={summary} loading={summaryLoading} error={summaryError} />

      <DateRangeFilter
        draft={draftRange}
        onChange={setDraftRange}
        onApply={applyRange}
        onReset={resetRange}
        error={rangeError}
      />

      {error && <div className="login-error" role="alert">{error}</div>}
      {loading ? <Loader /> : employee && (
        <>
          <div className="dashboard-controls dashboard-employee-controls">
            <div className="dashboard-selected-day">
              <label className="dashboard-field"><span>Selected date</span><input type="date" value={selectedDate} onChange={(event) => event.target.value && setSelectedDate(event.target.value)} style={inputStyle} /></label>
              <span className={statusClass(selectedStatus)}>{selectedStatus}</span>
              {selectedRecord?.clock_in && <span className="muted" style={{ fontSize: 12 }}>In {fmtTime(selectedRecord.clock_in)} · Out {selectedRecord.clock_out ? fmtTime(selectedRecord.clock_out) : "—"}</span>}
            </div>
          </div>

          <SummaryCards
            metrics={metrics}
            assignedIn={formatMinutes(Number(policy.official_check_in.split(":")[0]) * 60 + Number(policy.official_check_in.split(":")[1]))}
            assignedOut={formatMinutes(Number(policy.official_check_out.split(":")[0]) * 60 + Number(policy.official_check_out.split(":")[1]))}
          />
          <div className="dashboard-quick-actions">
            <button type="button" className="btn btn-sm btn-outline" onClick={() => downloadAttendanceSummary([employee], dates, holidays, policy, range)}>Export CSV</button>
          </div>

          <div className="dashboard-working-summary">
            <span><strong>{metrics.eligibleDays}</strong> eligible working days</span>
            <span><strong>{metrics.totalDays}</strong> days in selected period</span>
            <span><strong>{metrics.holidays}</strong> holidays / non-working dates</span>
            <span><strong>{metrics.presentDays}</strong> present</span>
            <span><strong>{metrics.absentDays}</strong> absent</span>
          </div>

          <div className="dashboard-employee-analytics">
            <div className="card">
              <div className="card-title-row">
                <div><h3>Attendance Trend</h3><div className="muted" style={{ fontSize: 12, marginTop: 3 }}>{formatDate(range.from)} – {formatDate(range.to)}</div></div>
              </div>
              <AttendanceChart trend={trend} />
              <div className="dashboard-progress-list">
                <ProgressMetric label="Overall attendance" value={metrics.attendancePct} />
                <ProgressMetric label="On-time check-in" value={metrics.onTimeCheckInPct} />
                <ProgressMetric label="On-time check-out" value={metrics.onTimeCheckOutPct} />
              </div>
              <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>Rates use eligible scheduled workdays. Holidays and approved leave are excluded; missing punches are not on time.</div>
            </div>
          </div>

          <AttendanceRecordsTable employee={employee} dates={dates} holidays={holidays} />
        </>
      )}
    </div>
  );
}

export default function AttendanceDashboard({
  user,
  manager,
  summary,
  summaryLoading,
  summaryError,
  pendingRequests,
}) {
  return manager
    ? <ManagerDashboard user={user} summary={summary} summaryLoading={summaryLoading} summaryError={summaryError} pendingRequests={pendingRequests} />
    : <EmployeeDashboard user={user} summary={summary} summaryLoading={summaryLoading} summaryError={summaryError} />;
}
