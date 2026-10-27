import { useEffect, useState } from "react";
import client from "../api/client";
import Badge from "./Badge";
import { formatCompanyDateLabel, fmtHours, fmtTime, toLocalInput } from "../utils/attendanceTime";

function attendanceSessions(record) {
  if (record.sessions?.length) return record.sessions;
  return record.clock_in
    ? [{ id: null, clock_in: record.clock_in, clock_out: record.clock_out, reentry_reason: null }]
    : [];
}

function companyTimeInput(instant) {
  return instant ? toLocalInput(instant).slice(11, 16) : "";
}

function InlineTimeEditor({ record, field, initialValue, onCancel, onSave }) {
  const [value, setValue] = useState(companyTimeInput(initialValue));
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (saving) return;
    setError("");

    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(value)) {
      setError("Enter a valid time.");
      return;
    }
    if (reason.trim().length < 3) {
      setError("Enter a correction reason of at least 3 characters.");
      return;
    }

    setSaving(true);
    try {
      const { data } = await client.put(`/attendance/manager/records/${record.id}/time`, {
        field,
        time: value,
        reason: reason.trim(),
      });
      await onSave(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save this attendance correction.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="attendance-inline-editor" onSubmit={submit}>
      <input
        type="time"
        aria-label={field === "clock_in" ? "Edit check-in time" : "Edit check-out time"}
        value={value}
        step="60"
        onChange={(event) => setValue(event.target.value)}
        required
      />
      <input
        type="text"
        aria-label="Correction reason"
        placeholder="Correction reason"
        value={reason}
        maxLength={255}
        onChange={(event) => setReason(event.target.value)}
        required
      />
      {error && <span className="login-error attendance-inline-error" role="alert">{error}</span>}
      <span className="attendance-inline-actions">
        <button type="submit" className="btn btn-sm btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button type="button" className="btn btn-sm btn-outline" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </span>
    </form>
  );
}

export default function EmployeeAttendanceSection({ employee }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    client.get(`/attendance/team/${employee.id}/records`)
      .then(({ data }) => {
        if (active) setRecords(data);
      })
      .catch((err) => {
        if (active) setError(err?.response?.data?.message || "Could not load attendance records.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [employee.id, refreshKey]);

  const startEditing = (record, field) => {
    setNotice("");
    setEditing({ recordId: record.id, field });
  };

  const saveCorrection = async (updatedRecord) => {
    setRecords((current) => current.map((record) => (
      record.id === updatedRecord.id ? updatedRecord : record
    )));
    setEditing(null);
    setNotice("Attendance correction saved.");
    setRefreshKey((key) => key + 1);
  };

  const formatHours = (hours) => (hours === 0 ? "0h 00m" : fmtHours(hours));

  return (
    <div className="card" style={{ marginBottom: 14, padding: 14 }}>
      <div className="card-title-row">
        <h3 style={{ fontSize: 13 }}>Attendance Details &amp; Correction</h3>
      </div>
      {error && <div className="login-error" role="alert">{error}</div>}
      {notice && <div role="status" style={{ color: "#067647", fontSize: 12.5, marginBottom: 8 }}>{notice}</div>}
      {loading ? (
        <div className="muted" style={{ padding: 12 }}>Loading attendance…</div>
      ) : !error && (
        <div className="table-wrap" style={{ maxHeight: 320, overflowY: "auto" }}>
          <table className="data-table employee-attendance-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Check-in Time</th>
                <th>Check-out Time</th>
                <th>Attendance Status</th>
                <th>Total Working Hours</th>
              </tr>
            </thead>
            <tbody>
              {records.length === 0 ? (
                <tr className="empty-row"><td colSpan={5}>No attendance records found.</td></tr>
              ) : records.map((record) => {
                const sessions = attendanceSessions(record);
                const firstSession = sessions[0];
                const lastSession = sessions[sessions.length - 1];
                const isEditingCheckIn = editing?.recordId === record.id && editing.field === "clock_in";
                const isEditingCheckOut = editing?.recordId === record.id && editing.field === "clock_out";
                return (
                  <tr key={record.id}>
                    <td>{formatCompanyDateLabel(record.work_date, { day: "numeric", month: "short", year: "numeric" })}</td>
                    <td>
                      {isEditingCheckIn ? (
                        <InlineTimeEditor
                          key={`${record.id}-clock_in`}
                          record={record}
                          field="clock_in"
                          initialValue={firstSession?.clock_in}
                          onCancel={() => setEditing(null)}
                          onSave={saveCorrection}
                        />
                      ) : (
                        <div className="attendance-time-cell">
                          <span className="attendance-time-value">{firstSession?.clock_in ? fmtTime(firstSession.clock_in) : "—"}</span>
                          <button
                            type="button"
                            className="attendance-inline-edit-trigger"
                            title="Edit check-in time"
                            aria-label="Edit check-in time"
                            onClick={() => startEditing(record, "clock_in")}
                          >
                            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                              <path d="M11.7 1.3a1.5 1.5 0 0 1 2.1 2.1L6 11.2l-3.1.8.8-3.1 8-7.6ZM2.5 13h11v1h-11v-1Z" />
                            </svg>
                          </button>
                        </div>
                      )}
                    </td>
                    <td>
                      {isEditingCheckOut ? (
                        <InlineTimeEditor
                          key={`${record.id}-clock_out`}
                          record={record}
                          field="clock_out"
                          initialValue={lastSession?.clock_out}
                          onCancel={() => setEditing(null)}
                          onSave={saveCorrection}
                        />
                      ) : (
                        <div className="attendance-time-cell">
                          <span className="attendance-time-value">{lastSession?.clock_out ? fmtTime(lastSession.clock_out) : "—"}</span>
                          <button
                            type="button"
                            className="attendance-inline-edit-trigger"
                            title="Edit check-out time"
                            aria-label="Edit check-out time"
                            onClick={() => startEditing(record, "clock_out")}
                          >
                            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                              <path d="M11.7 1.3a1.5 1.5 0 0 1 2.1 2.1L6 11.2l-3.1.8.8-3.1 8-7.6ZM2.5 13h11v1h-11v-1Z" />
                            </svg>
                          </button>
                        </div>
                      )}
                    </td>
                    <td><Badge status={record.status} /></td>
                    <td>{formatHours(record.total_hours)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
