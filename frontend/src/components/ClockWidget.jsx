import { useEffect, useRef, useState } from "react";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";
import { getBrowserLocation, mapsUrl } from "../utils/geo";
import { fmtTime, fmtHours, arrivalLabel, placeLabel } from "../utils/attendanceTime";

/**
 * Web clock-in/out — the same flow as the mobile app, minus the camera:
 *   • GPS: the browser's location is sent with every punch (soft geofence: it is recorded and
 *     flagged for the manager if outside the office, but never blocks the punch);
 *   • several check-ins a day: after clocking out you can check in again with a reason;
 *   • if the company has switched the selfie policy on, a photo file can still be attached.
 */
export default function ClockWidget({ onPunch }) {
  const { hasClockInOut } = useAuth();
  const [record, setRecord] = useState(null);
  const [now, setNow] = useState(new Date());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null); // {kind: 'warn'|'info', text}
  const [selfieRequired, setSelfieRequired] = useState(false);
  const [selfie, setSelfie] = useState(null);
  const [reentering, setReentering] = useState(false);
  const [reason, setReason] = useState("");
  const [locating, setLocating] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    client.get("/attendance/policy").then(({ data }) => setSelfieRequired(!!data.selfie_required)).catch(() => {});
  }, []);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const fetchToday = async () => {
    const { data } = await client.get("/attendance/today");
    setRecord(data.record);
  };

  useEffect(() => {
    if (hasClockInOut) fetchToday();
  }, [hasClockInOut]);

  if (!hasClockInOut) {
    return (
      <div className="card clock-widget">
        <div>
          <div className="label" style={{ marginBottom: 4 }}>Attendance</div>
          <div className="muted" style={{ fontSize: 13.5 }}>
            Contract employees track hours via timesheets — clock in/out isn't applicable to your role.
          </div>
        </div>
      </div>
    );
  }

  const sessions = record?.sessions || [];
  const clockedIn = !!record?.currently_clocked_in;
  // Clocked out earlier today (e.g. by mistake) -> they may check in again, with a reason.
  const canCheckInAgain = !!record?.clock_in && !clockedIn;
  const lastSession = sessions[sessions.length - 1];

  const handleClock = async (action) => {
    const isReentry = action === "clock-in" && canCheckInAgain;
    if (isReentry && reason.trim().length < 3) {
      setError("Please give a reason for checking in again — your manager will see it.");
      return;
    }
    if (selfieRequired && !selfie) {
      setError("A photo is required by your company — attach one first.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice(null);
    try {
      setLocating(true);
      const loc = await getBrowserLocation();
      setLocating(false);
      const coords = loc.error ? {} : { latitude: loc.latitude, longitude: loc.longitude };
      let data;
      if (selfie) {
        const form = new FormData();
        form.append("selfie", selfie);
        Object.entries(coords).forEach(([k, v]) => form.append(k, v));
        if (isReentry) form.append("reason", reason.trim());
        ({ data } = await client.post(`/attendance/${action}`, form));
      } else {
        ({ data } = await client.post(`/attendance/${action}`, { ...coords, ...(isReentry ? { reason: reason.trim() } : {}) }));
      }
      if (data.geofence_warning) {
        setNotice({ kind: "warn", text: "You weren't within the office radius. Your attendance is recorded as usual, and it has been flagged for your manager." });
      } else if (loc.error) {
        setNotice({ kind: "info", text: `${loc.error} Your attendance was still recorded.` });
      } else {
        setNotice({ kind: "ok", text: "Location captured — you're at the office." });
      }
      setSelfie(null);
      setReason("");
      setReentering(false);
      if (fileRef.current) fileRef.current.value = "";
      await fetchToday();
      onPunch?.();
    } catch (err) {
      setError(err?.response?.data?.message || "Something went wrong.");
      if (err?.response?.data?.selfie_required) setSelfieRequired(true);
    } finally {
      setLocating(false);
      setBusy(false);
    }
  };

  const noticeStyle = {
    warn: { background: "var(--color-warning-100)", color: "#b54708" },
    info: { background: "var(--color-primary-50)", color: "var(--color-primary-700)" },
    ok: { background: "var(--color-success-100)", color: "#067647" },
  };

  return (
    <div className="card clock-widget">
      <div style={{ minWidth: 0, flex: 1 }}>
        <div className="label" style={{ marginBottom: 4 }}>Today's Attendance</div>
        <div className="time">
          {now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </div>
        {error && <div style={{ color: "var(--color-danger)", fontSize: 12.5, marginTop: 6 }}>{error}</div>}
        {locating && <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>📍 Getting your location…</div>}
        {notice && (
          <div style={{ ...noticeStyle[notice.kind], fontSize: 12.5, borderRadius: 6, padding: "7px 10px", marginTop: 8, maxWidth: 520 }}>{notice.text}</div>
        )}
        {selfieRequired && (!record?.clock_in || clockedIn || reentering) && (
          <div style={{ marginTop: 8, fontSize: 12.5 }}>
            <label className="muted">Photo required by your company: </label>
            <input
              ref={fileRef} type="file" accept="image/*" capture="user"
              onChange={(e) => setSelfie(e.target.files?.[0] || null)}
            />
          </div>
        )}
        {sessions.length > 0 && (
          <div style={{ fontSize: 12.5, marginTop: 8 }}>
            {sessions.map((x) => {
              const place = placeLabel(x.clock_out ? x.clock_out_within_geofence : x.clock_in_within_geofence);
              return (
                <div key={x.session_no} className="muted" style={{ marginBottom: 2 }}>
                  <strong style={{ color: "var(--color-text)" }}>{sessions.length > 1 ? `Session ${x.session_no}: ` : "In: "}</strong>
                  {fmtTime(x.clock_in)}{x.clock_out ? <> &ndash; {fmtTime(x.clock_out)}</> : " (now)"}
                  {place.cls && <span className={`att-chip ${place.cls}`} style={{ marginLeft: 8 }}>{place.text}</span>}
                  {x.clock_in_lat != null && <a href={mapsUrl(x.clock_in_lat, x.clock_in_lng)} target="_blank" rel="noreferrer" style={{ marginLeft: 8 }}>map</a>}
                  {x.reentry_reason ? <> &middot; <em>{x.reentry_reason}</em></> : null}
                </div>
              );
            })}
            {record.check_in_status && <div className={`att-chip ${record.check_in_status === "late" ? "red" : "green"}`} style={{ marginTop: 5 }}>{arrivalLabel(record.check_in_status)}</div>}
            {record.total_hours > 0 && <div className="muted">Worked so far: <strong>{fmtHours(record.total_hours)}</strong>{record.away_minutes > 0 ? ` · away ${record.away_minutes} min` : ""}</div>}
          </div>
        )}
        {canCheckInAgain && !reentering && (
          <div className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>
            Clocked out{lastSession?.clock_out ? ` at ${fmtTime(lastSession.clock_out)}` : ""}. Clocked out by mistake, or coming back? You can check in again — with a reason your manager can see.
          </div>
        )}
        {reentering && canCheckInAgain && (
          <div style={{ marginTop: 8 }}>
            <input
              value={reason} onChange={(e) => setReason(e.target.value)} maxLength={255}
              placeholder="Reason for checking in again (your manager can see this)"
              style={{ width: "100%", maxWidth: 520, border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px", fontSize: 13 }}
            />
          </div>
        )}
      </div>
      <div>
        {!record?.clock_in && (
          <button className="btn btn-success" disabled={busy} onClick={() => handleClock("clock-in")}>
            {busy ? "Please wait…" : "Clock In"}
          </button>
        )}
        {clockedIn && (
          <button className="btn btn-danger" disabled={busy} onClick={() => handleClock("clock-out")}>
            {busy ? "Please wait…" : "Clock Out"}
          </button>
        )}
        {canCheckInAgain && !reentering && (
          <button className="btn btn-outline" onClick={() => setReentering(true)}>Check in again</button>
        )}
        {canCheckInAgain && reentering && (
          <>
            <button className="btn btn-success" disabled={busy} onClick={() => handleClock("clock-in")}>{busy ? "Please wait…" : "Check In"}</button>
            <button className="btn btn-outline" style={{ marginLeft: 6 }} onClick={() => { setReentering(false); setReason(""); setError(""); }}>Cancel</button>
          </>
        )}
      </div>
    </div>
  );
}
