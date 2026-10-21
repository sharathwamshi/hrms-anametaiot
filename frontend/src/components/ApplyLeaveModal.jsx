import { useEffect, useState } from "react";
import client from "../api/client";
import { localDateStr } from "../utils/attendanceTime";

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
  const today = localDateStr();

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
    setSubmitting(true);
    try {
      await client.post("/leave/apply", form);
      onDone();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not submit leave request.");
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="card-title-row">
          <h3>Apply for Leave</h3>
          <button type="button" className="btn btn-sm btn-outline" onClick={onClose}>Close</button>
        </div>
        <p className="muted" style={{ fontSize: 12.5, marginTop: -8, marginBottom: 14 }}>
          Leave may be requested for today or a future date. Your manager must approve it.
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
                  type="date" required min={today} value={form.start_date}
                  onChange={(e) => setForm({ ...form, start_date: e.target.value, end_date: form.end_date < e.target.value ? e.target.value : form.end_date })}
                />
              </div>
              <div className="form-field">
                <label>End Date</label>
                <input type="date" required min={form.start_date || today} value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
              </div>
            </div>
            <div className="form-field">
              <label>Reason</label>
              <textarea rows={3} maxLength={500} required value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={submitting || types.length === 0}>
                {submitting ? "Submitting…" : "Submit Request"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
