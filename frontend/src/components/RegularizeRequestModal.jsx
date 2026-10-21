import { useEffect, useRef, useState } from "react";
import client from "../api/client";

export default function RegularizeRequestModal({ record, onClose, onDone }) {
  const [reasons, setReasons] = useState([]);
  const [quota, setQuota] = useState(null);
  const [reasonId, setReasonId] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const alerted = useRef(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      client.get("/attendance/regularization-reasons"),
      client.get("/attendance/regularization-limit"),
    ])
      .then(([reasonResponse, quotaResponse]) => {
        if (cancelled) return;
        setReasons(reasonResponse.data);
        setQuota(quotaResponse.data);
        if (quotaResponse.data.remaining === 0 && !alerted.current) {
          alerted.current = true;
          window.alert("your limit is exceeded please contact your manager");
          onCloseRef.current();
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err?.response?.data?.message || "Could not load regularization details.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
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
      if (err?.response?.status === 429) {
        window.alert("your limit is exceeded please contact your manager");
        onCloseRef.current();
      } else {
        setError(err?.response?.data?.message || "Could not submit the request.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="card-title-row">
          <h3 style={{ marginBottom: 4 }}>Request Regularization</h3>
          <button type="button" className="btn btn-sm btn-outline" onClick={onClose}>Close</button>
        </div>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 16 }}>
          For {record.work_date}. Your manager (or HR Operations) will review this.
        </p>
        {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
        {loading ? <p className="muted">Loading regularization details…</p> : quota && quota.remaining > 0 ? (
          <form onSubmit={submit}>
            <div className="form-field">
              <span className="muted" style={{ fontSize: 12.5 }}>
                {quota.remaining}/{quota.limit} regularization requests remaining this month.
              </span>
            </div>
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
            <div className="form-actions">
              <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={saving || reasons.length === 0}>
                {saving ? "Submitting..." : "Submit Request"}
              </button>
            </div>
          </form>
        ) : null}
      </div>
    </div>
  );
}
