import { useState } from "react";
import client from "../api/client";

export default function RegularizationReviewModal({ record, onClose, onDone }) {
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const act = async (action) => {
    if (action === "reject" && !comment.trim()) {
      setError("A comment explaining the rejection is required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await client.post(`/attendance/regularization-requests/${record.id}/${action}`, { comment });
      onDone();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not process this request.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 4 }}>Regularization Request</h3>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>{record.employee_name} — {record.work_date}</p>

        <div style={{ background: "var(--color-bg-alt, #f6f7fb)", borderRadius: 8, padding: 12, marginBottom: 14, fontSize: 13 }}>
          <div><strong>Reason:</strong> {record.regularization_reason_label}</div>
          {record.regularization_note && <div style={{ marginTop: 6 }}><strong>Note:</strong> {record.regularization_note}</div>}
        </div>

        <div className="form-field">
          <label>Your Comment {"(required to reject)"}</label>
          <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={3} placeholder="Optional when approving; required when rejecting" />
        </div>
        {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
        <div className="form-actions">
          <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-danger" disabled={saving} onClick={() => act("reject")}>Reject</button>
          <button type="button" className="btn btn-primary" disabled={saving} onClick={() => act("approve")}>Approve</button>
        </div>
      </div>
    </div>
  );
}
