import { useState } from "react";
import client from "../api/client";

export default function EditVendorAgreementModal({ agreement, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: agreement.title || "",
    effective_from: agreement.effective_from || "",
    effective_to: agreement.effective_to || "",
    termination_notice_days: agreement.termination_notice_days ?? 90,
    confidentiality_days: agreement.confidentiality_days ?? 60,
    feedback_days: agreement.feedback_days ?? 2,
    status: agreement.status === "terminated" ? "terminated" : "active",
  });
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const update = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }));
  };

  const save = async (event) => {
    event.preventDefault();
    setError("");
    if (!form.title.trim() || !form.effective_from) {
      setError("Agreement title and effective start date are required.");
      return;
    }
    if (form.effective_to && form.effective_to < form.effective_from) {
      setError("Effective end date cannot precede the start date.");
      return;
    }
    const body = new FormData();
    Object.entries(form).forEach(([key, value]) => body.append(key, value));
    if (file) body.append("file", file);

    setSaving(true);
    try {
      const { data } = await client.put(`/vendors/agreements/${agreement.id}`, body);
      onSaved(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update this agreement.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <form className="modal-box" style={{ width: 560 }} onClick={(event) => event.stopPropagation()} onSubmit={save}>
        <h3 style={{ marginBottom: 14 }}>Edit Agreement</h3>
        {error && <div className="login-error" role="alert">{error}</div>}
        <div className="form-field">
          <label htmlFor="agreement-title">Agreement Title</label>
          <input id="agreement-title" value={form.title} onChange={update("title")} maxLength={150} required />
        </div>
        <div className="form-grid">
          <div className="form-field">
            <label htmlFor="agreement-from">Effective From</label>
            <input id="agreement-from" type="date" value={form.effective_from} onChange={update("effective_from")} required />
          </div>
          <div className="form-field">
            <label htmlFor="agreement-to">Effective To</label>
            <input id="agreement-to" type="date" value={form.effective_to} onChange={update("effective_to")} />
          </div>
        </div>
        <div className="form-grid">
          <div className="form-field">
            <label htmlFor="termination-days">Termination Notice (days)</label>
            <input id="termination-days" type="number" min="0" max="3650" value={form.termination_notice_days} onChange={update("termination_notice_days")} />
          </div>
          <div className="form-field">
            <label htmlFor="confidentiality-days">Confidentiality (days)</label>
            <input id="confidentiality-days" type="number" min="0" max="3650" value={form.confidentiality_days} onChange={update("confidentiality_days")} />
          </div>
        </div>
        <div className="form-grid">
          <div className="form-field">
            <label htmlFor="feedback-days">Feedback (days)</label>
            <input id="feedback-days" type="number" min="0" max="3650" value={form.feedback_days} onChange={update("feedback_days")} />
          </div>
          <div className="form-field">
            <label htmlFor="agreement-status">Agreement Status</label>
            <select id="agreement-status" value={form.status} onChange={update("status")}>
              <option value="active">Active</option>
              <option value="terminated">Terminated</option>
            </select>
          </div>
        </div>
        <div className="form-field">
          <label htmlFor="agreement-file">Replace agreement document (optional)</label>
          <input id="agreement-file" type="file" accept=".pdf,application/pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          <span className="muted" style={{ fontSize: 11 }}>Leave empty to keep the current document.</span>
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
          <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : "Save Changes"}</button>
        </div>
      </form>
    </div>
  );
}
