import { useEffect, useState } from "react";
import client from "../api/client";
import { fromLocalInput } from "../utils/attendanceTime";

/** Regularize a day directly by choosing one of the defined reasons — no employee request needed. */
export default function ManagerRegularizeModal({ person, day, onClose, onDone }) {
  const hasSessions = !!day.rec?.sessions?.length;
  const [reasons, setReasons] = useState([]);
  const [reasonId, setReasonId] = useState("");
  const [note, setNote] = useState("");
  const [setTimes, setSetTimes] = useState(false);
  const [cin, setCin] = useState(`${day.ds}T09:30`);
  const [cout, setCout] = useState(`${day.ds}T18:30`);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => { client.get("/attendance/regularization-reasons").then(({ data }) => setReasons(data)); }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!reasonId) { setError("Please pick a reason."); return; }
    setSaving(true);
    setError("");
    try {
      await client.post("/attendance/manager/regularize", {
        user_id: person.id, work_date: day.ds, reason_id: Number(reasonId), note,
        ...(setTimes && !hasSessions ? { clock_in: fromLocalInput(cin), clock_out: fromLocalInput(cout) } : {}),
      });
      onDone();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not regularize this day.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 4 }}>Regularize — {person.full_name}</h3>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 16 }}>
          For {day.ds}. Pick the reason that applies; the day will count as regularized and {person.full_name.split(" ")[0]} is notified.
        </p>
        <form onSubmit={submit}>
          <div className="form-field">
            <label>Reason</label>
            <select value={reasonId} onChange={(e) => setReasonId(e.target.value)} required>
              <option value="">Select a reason…</option>
              {reasons.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </div>
          <div className="form-field">
            <label>Note (optional)</label>
            <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={255} />
          </div>
          {!hasSessions && (
            <>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: 10 }}>
                <input type="checkbox" checked={setTimes} onChange={(e) => setSetTimes(e.target.checked)} /> Also record the working times being excused
              </label>
              {setTimes && (
                <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
                  <div className="form-field" style={{ flex: 1, marginBottom: 0 }}><label>Check-in</label><input type="datetime-local" value={cin} onChange={(e) => setCin(e.target.value)} /></div>
                  <div className="form-field" style={{ flex: 1, marginBottom: 0 }}><label>Check-out</label><input type="datetime-local" value={cout} onChange={(e) => setCout(e.target.value)} /></div>
                </div>
              )}
            </>
          )}
          {reasons.length === 0 && <p className="muted" style={{ fontSize: 12 }}>No reasons are set up yet — add some under “Regularization Rules”.</p>}
          {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
          <div className="form-actions">
            <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={saving || reasons.length === 0}>{saving ? "Saving…" : "Regularize"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
