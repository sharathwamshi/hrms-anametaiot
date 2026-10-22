import { useState } from "react";
import client from "../api/client";
import { fromLocalInput, localDateStr, toLocalInput } from "../utils/attendanceTime";

const STATUS_OPTIONS = [
  { value: "", label: "Automatic (Present if ≥ 4 hours, else Half day)" },
  { value: "present", label: "Present" },
  { value: "half_day", label: "Half day" },
  { value: "regularized", label: "Regularized" },
  { value: "absent", label: "Absent (clears all check-ins)" },
];

/**
 * A manager / HR Ops corrects a person's check-in and check-out times for a day directly —
 * no request from the employee needed. Every correction needs a reason and is stamped on the record.
 */
export default function ManagerEditDayModal({ person, day, onClose, onDone }) {
  const rec = day.rec;
  const [rows, setRows] = useState(() => (rec?.sessions?.length
    ? rec.sessions.map((s) => ({ id: s.id, in: toLocalInput(s.clock_in), out: toLocalInput(s.clock_out), why: s.reentry_reason || "" }))
    : [{ id: null, in: "", out: "", why: "" }]));
  const [status, setStatus] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const setRow = (i, patch) => setRows((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const addRow = () => setRows((rs) => {
    const last = rs[rs.length - 1];
    const start = last?.out || `${day.ds}T09:30`;
    return [...rs, { id: null, in: start, out: "", why: "" }];
  });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    const clearing = status === "absent";
    if (!clearing) {
      if (rows.length === 0) { setError("Add a check-in or mark the day as absent."); return; }
      const parsed = [];
      for (let i = 0; i < rows.length; i++) {
        if (!rows[i].in) { setError(`Check-in ${i + 1}: please pick a check-in time.`); return; }
        const checkIn = fromLocalInput(rows[i].in);
        const checkOut = rows[i].out ? fromLocalInput(rows[i].out) : null;
        if (!checkIn || rows[i].in.slice(0, 10) !== day.ds) { setError(`Check-in ${i + 1} must be a valid time on ${day.ds}.`); return; }
        if (rows[i].out && (!checkOut || rows[i].out.slice(0, 10) < day.ds)) { setError(`Check-out ${i + 1} must be a valid time after the check-in date.`); return; }
        const inDate = new Date(checkIn);
        const outDate = checkOut ? new Date(checkOut) : null;
        if (outDate && outDate <= inDate) { setError(`Check-out ${i + 1} must be after its check-in.`); return; }
        if (outDate && outDate - inDate > 24 * 60 * 60 * 1000) { setError(`Session ${i + 1} cannot be longer than 24 hours.`); return; }
        if (!outDate && (i !== rows.length - 1 || day.ds !== localDateStr())) { setError("Only the final session for today can be left without a check-out."); return; }
        parsed.push({ start: inDate, end: outDate, index: i });
      }
      parsed.sort((a, b) => a.start - b.start);
      for (let i = 1; i < parsed.length; i++) {
        if (!parsed[i - 1].end || parsed[i].start < parsed[i - 1].end) {
          setError(`Check-in ${parsed[i].index + 1} overlaps the previous session.`);
          return;
        }
      }
    }
    if (reason.trim().length < 3) { setError("Enter a reason for the correction (at least 3 characters)."); return; }
    setSaving(true);
    try {
      await client.put("/attendance/manager/day", {
        user_id: person.id, work_date: day.ds,
        sessions: clearing ? [] : rows.map((r) => ({ id: r.id, clock_in: fromLocalInput(r.in), clock_out: fromLocalInput(r.out), reentry_reason: r.why })),
        status: status || undefined, reason, note,
      });
      onDone();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save the correction.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box att-modal-wide" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 4 }}>Edit times — {person.full_name}</h3>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
          {new Date(`${day.ds}T00:00:00`).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}. No request is needed — your correction is recorded with your name, the time and your reason.
          {rec?.regularization_status === "pending" && " This also settles their pending regularization request."}
          {" "}Standard checkout is 6:30 PM; enter the actual check-out time.
        </p>
        <form onSubmit={submit}>
          {status !== "absent" && (
            <>
              {rows.map((r, i) => (
                <div key={i}>
                  <div className="att-edit-row">
                    <div className="no">{i + 1}</div>
                    <div><label className="muted" style={{ fontSize: 11.5 }}>Check-in</label><input type="datetime-local" value={r.in} onChange={(e) => setRow(i, { in: e.target.value })} required /></div>
                    <div><label className="muted" style={{ fontSize: 11.5 }}>Check-out {i === rows.length - 1 ? "(empty = still in, today only)" : ""}</label><input type="datetime-local" value={r.out} onChange={(e) => setRow(i, { out: e.target.value })} /></div>
                    <button type="button" className="btn btn-sm btn-outline" title="Remove this check-in" onClick={() => setRows((rs) => rs.filter((_, k) => k !== i))} disabled={rows.length === 1 && !rec?.sessions?.length}>✕</button>
                  </div>
                  {i > 0 && (
                    <div style={{ margin: "-4px 0 10px 36px" }}>
                      <input value={r.why} onChange={(e) => setRow(i, { why: e.target.value })} maxLength={255} placeholder="Reason for this re-entry (optional)" />
                    </div>
                  )}
                </div>
              ))}
              {rows.length < 10 && <button type="button" className="btn btn-sm btn-outline" onClick={addRow} style={{ marginBottom: 14 }}>+ Add another check-in</button>}
            </>
          )}

          <div className="form-field">
            <label>Day status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="form-field">
            <label>Reason for the correction</label>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Enter reason for correction"
              maxLength={255}
              required
            />
          </div>
          <div className="form-field">
            <label>Note (optional)</label>
            <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Confirmed with the client site lead" maxLength={255} />
          </div>
          {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
          <div className="form-actions">
            <button type="button" className="btn btn-outline" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving…" : "Save correction"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
