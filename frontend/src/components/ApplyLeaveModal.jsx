import { useEffect, useState } from "react";
import client from "../api/client";
import LeaveBalancePreview from "./LeaveBalancePreview";
import {
  isDisallowedBackdatedLeaveDate,
  isSundayDate,
  BACKDATED_LEAVE_ERROR,
  currentMonthLeaveStart,
} from "../utils/attendanceTime";

const emptyForm = (startDate) => ({
  leave_type_id: "",
  start_date: startDate,
  end_date: startDate,
  reason: "",
});

export default function ApplyLeaveModal({ startDate, onClose, onDone }) {
  const [types, setTypes] = useState([]);
  const [form, setForm] = useState(() => emptyForm(startDate));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const minimumDate = currentMonthLeaveStart();
  const minimumEndDate = form.start_date && (!minimumDate || form.start_date > minimumDate)
    ? form.start_date
    : minimumDate;
  useEffect(() => {
    let cancelled = false;
    client.get("/leave/types")
      .then(({ data }) => { if (!cancelled) setTypes(data); })
      .catch((err) => {
        if (!cancelled) setError(err?.response?.data?.message || "Could not load leave types.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (isSundayDate(form.start_date) || isSundayDate(form.end_date)) {
      setError("Leave start and end dates cannot be Sundays.");
      return;
    }
    if (
      isDisallowedBackdatedLeaveDate(form.start_date) ||
      isDisallowedBackdatedLeaveDate(form.end_date)
    ) {
      setError(BACKDATED_LEAVE_ERROR);
      return;
    }
    setSubmitting(true);
    try {
      await client.post("/leave/apply", form);
      onDone();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not submit leave request.");
      setSubmitting(false);
    }
  };
  const updateDate = (field, value) => {
    if (isSundayDate(value)) {
      setError("Sundays cannot be selected for leave.");
      return;
    }
    if (isDisallowedBackdatedLeaveDate(value)) {
      setError(BACKDATED_LEAVE_ERROR);
      return;
    }
    setError("");
    setForm((current) => ({
      ...current,
      [field]: value,
      ...(field === "start_date" && current.end_date < value ? { end_date: value } : {}),
    }));
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="card-title-row">
          <h3>Apply for Leave</h3>
          <button type="button" className="btn btn-sm btn-outline" onClick={onClose}>Close</button>
        </div>
        <p className="muted" style={{ fontSize: 12.5, marginTop: -8, marginBottom: 14 }}>
          Employees may apply for leave on eligible dates in the current month or future dates. Sundays are not selectable.
        </p>
        {error && <div className="login-error">{error}</div>}
        {loading ? <p className="muted">Loading leave types…</p> : (
          <form onSubmit={submit}>
            <div className="form-field">
              <label>Leave Type</label>
              <select required value={form.leave_type_id} onChange={(e) => setForm({ ...form, leave_type_id: e.target.value })}>
                <option value="">Select type</option>
                {types.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
              </select>
            </div>
            <div className="form-grid">
              <div className="form-field">
                <label>Start Date</label>
                <input
                  type="date" required min={minimumDate} value={form.start_date}
                  onChange={(e) => updateDate("start_date", e.target.value)}
                />
              </div>
              <div className="form-field">
                <label>End Date</label>
                <input type="date" required min={minimumEndDate} value={form.end_date} onChange={(e) => updateDate("end_date", e.target.value)} />
              </div>
            </div>
            <LeaveBalancePreview
              leaveTypeId={form.leave_type_id}
              startDate={form.start_date}
              endDate={form.end_date}
            />
            <div className="form-field">
              <label>Reason</label>
              <textarea rows={3} maxLength={500} required value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn-success" disabled={submitting || types.length === 0}>
                {submitting ? "Submitting…" : "Submit Request"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
