import { useEffect, useState } from "react";
import client from "../api/client";

export default function RegularizeRequestModal({ record, onClose, onDone }) {
  const [reasons, setReasons] = useState([]);
  const [reasonId, setReasonId] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    client.get("/attendance/regularization-reasons").then(({ data }) => setReasons(data));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!reasonId) { setError("Please pick a reason."); return; }
    setSaving(true);
    setError("");
    try {
      await client.post("/attendance/regularize-request", { work_date: record.work_date, reason_id: Number(reasonId), note });
      onDone();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not submit the request.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 4 }}>Request Regularization</h3>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 16 }}>
          For {record.work_date}. Your manager (or HR Operations) will review this.
        </p>
        <form onSubmit={submit}>
          <div className="form-field">
            <label>Reason</label>
            <select value={reasonId} onChange={(e) => setReasonId(e.target.value)} required>
              <option value="">Select a reason...</option>
              {reasons.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </div>
          <div className="form-field">
            <label>Note (optional)</label>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} placeholder="Any extra detail for your manager..." />
          </div>
          {reasons.length === 0 && (
            <p className="muted" style={{ fontSize: 12 }}>No reasons have been set up yet — ask your manager or HR Operations to add one.</p>
          )}
          {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
          <div className="form-actions">
            <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={saving || reasons.length === 0}>
              {saving ? "Submitting..." : "Submit Request"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
