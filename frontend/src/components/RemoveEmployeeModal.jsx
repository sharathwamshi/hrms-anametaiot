import { useState } from "react";
import client from "../api/client";

// Confirmation for removing a person. Not a hard delete — spells out exactly what
// happens, and requires a reason that is recorded with who removed them and when.
export default function RemoveEmployeeModal({ employee, onClose, onRemoved }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const firstName = employee.full_name.split(" ")[0];

  const submit = async (e) => {
    e.preventDefault();
    if (reason.trim().length < 3) {
      setError("Please give a reason (at least 3 characters).");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await client.delete(`/employees/${employee.id}`, { data: { reason: reason.trim() } });
      onRemoved();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not remove this person.");
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" style={{ zIndex: 1100 }} onClick={onClose}>
      <div className="modal-box" style={{ width: 520 }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 4 }}>Remove {employee.full_name}?</h3>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
          {employee.employee_code} · {employee.designation || "No designation"}
        </p>

        <div className="callout warn" style={{ marginBottom: 14, fontSize: 12.5, lineHeight: 1.6 }}>
          <strong>What happens</strong>
          <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
            <li>{firstName} is <strong>signed out immediately</strong> and can no longer log in.</li>
            <li>They disappear from the directory, approval queues and <strong>future payroll runs</strong> — generate their final payslip first if they're owed one.</li>
            <li>Their pending leave requests are cancelled and their phone stops receiving notifications.</li>
          </ul>
          <strong style={{ display: "block", marginTop: 8 }}>What is kept</strong>
          <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
            <li>Attendance, payslips, leave history, documents and everything else — nothing is deleted.</li>
            <li>You can restore {firstName} later from the "Removed" list.</li>
          </ul>
        </div>

        {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="form-field">
            <label>Reason for removal (recorded with your name and the date)</label>
            <textarea
              rows={3} value={reason} maxLength={255} autoFocus
              onChange={(e) => { setReason(e.target.value); setError(""); }}
              placeholder="e.g. Resigned — last working day 30 Sep"
            />
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-outline" onClick={onClose} disabled={busy}>Cancel</button>
            <button type="submit" className="btn btn-danger" disabled={busy || reason.trim().length < 3}>
              {busy ? "Removing..." : `Remove ${firstName}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
