import { useEffect, useRef, useState } from "react";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";
import Loader from "./Loader";
import { getBrowserLocation, mapsUrl } from "../utils/geo";
import { fmtTime, fmtHours, arrivalLabel, placeLabel, formatCompanyTime, setCompanyTimezone } from "../utils/attendanceTime";

/**
 * Web clock-in/out — the same flow as the mobile app, minus the camera:
 *   • GPS: the browser's location is sent with every punch (soft geofence: it is recorded and
 *     flagged for the manager if outside the office, but never blocks the punch);
 *   • several check-ins a day: after clocking out you can check in again with a reason;
 *   • if the company has switched the selfie policy on, a photo file can still be attached.
 */
export default function ClockWidget({ onPunch, onTimezoneChange }) {
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
  const [workLocations, setWorkLocations] = useState([]);
  const [workLocationsLoading, setWorkLocationsLoading] = useState(false);
  const [workLocationsError, setWorkLocationsError] = useState("");
  const [selectedWorkLocationId, setSelectedWorkLocationId] = useState("");
  const [clockInOpen, setClockInOpen] = useState(false);
  const [clockInLocationStatus, setClockInLocationStatus] = useState("idle");
  const [clockInLocation, setClockInLocation] = useState(null);
  const [clockInLocationError, setClockInLocationError] = useState("");
  const [showLocationInstructions, setShowLocationInstructions] = useState(false);
  const fileRef = useRef(null);
  const clockInDialogRef = useRef(null);

  const loadWorkLocations = async () => {
    setWorkLocationsLoading(true);
    setWorkLocationsError("");
    try {
      const { data } = await client.get("/attendance/work-locations");
      setWorkLocations(data);
      setSelectedWorkLocationId((current) => (
        data.some((location) => String(location.id) === String(current))
          ? current
          : String(data.find((location) => location.is_default)?.id || data[0]?.id || "")
      ));
    } catch (err) {
      setWorkLocationsError(err?.response?.data?.message || "Could not load work locations.");
    } finally {
      setWorkLocationsLoading(false);
    }
  };

  useEffect(() => {
    client.get("/attendance/policy").then(({ data }) => {
      if (setCompanyTimezone(data.company_timezone)) onTimezoneChange?.();
      setSelfieRequired(!!data.selfie_required);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (hasClockInOut) loadWorkLocations();
  }, [hasClockInOut]);

  useEffect(() => {
    if (!clockInOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement;
    document.body.style.overflow = "hidden";
    clockInDialogRef.current?.focus();
    const keepFocusInDialog = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = clockInDialogRef.current?.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])'
      );
      if (!focusable?.length) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", keepFocusInDialog);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", keepFocusInDialog);
      previousFocus?.focus?.();
    };
  }, [clockInOpen]);

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

  const checkClockInLocation = async () => {
    setClockInLocationStatus("loading");
    setClockInLocation(null);
    setClockInLocationError("");
    setShowLocationInstructions(false);
    const location = await getBrowserLocation();
    if (location.error) {
      setClockInLocationStatus("error");
      setClockInLocationError(location.error);
      setShowLocationInstructions(true);
      return;
    }
    try {
      const { data } = await client.post("/attendance/location-check", {
        latitude: location.latitude,
        longitude: location.longitude,
      });
      setClockInLocation({ ...location, ...data });
      setClockInLocationStatus("ready");
    } catch (err) {
      setClockInLocationStatus("error");
      setClockInLocationError(err?.response?.data?.message || "Could not verify your location. Please try again.");
    }
  };

  const openClockIn = () => {
    setError("");
    setNotice(null);
    setClockInLocationStatus("loading");
    setClockInLocation(null);
    setClockInLocationError("");
    setShowLocationInstructions(false);
    setClockInOpen(true);
    setSelectedWorkLocationId((current) => (
      workLocations.some((location) => String(location.id) === String(current))
        ? current
        : String(workLocations.find((location) => location.is_default)?.id || workLocations[0]?.id || "")
    ));
    checkClockInLocation();
  };

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
    if (action === "clock-in" && (clockInLocationStatus !== "ready" || !clockInLocation)) {
      setError("Fetch and verify your location before clocking in.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice(null);
    try {
      if (action === "clock-out") setLocating(true);
      const loc = action === "clock-in"
        ? clockInLocation
        : await getBrowserLocation();
      setLocating(false);
      const coords = loc.error ? {} : { latitude: loc.latitude, longitude: loc.longitude };
      let data;
      if (selfie) {
        const form = new FormData();
        form.append("selfie", selfie);
        Object.entries(coords).forEach(([k, v]) => form.append(k, v));
        if (isReentry) form.append("reason", reason.trim());
        if (action === "clock-in") form.append("work_location_id", selectedWorkLocationId);
        ({ data } = await client.post(`/attendance/${action}`, form));
      } else {
        ({ data } = await client.post(`/attendance/${action}`, {
          ...coords,
          ...(isReentry ? { reason: reason.trim() } : {}),
          ...(action === "clock-in" ? { work_location_id: selectedWorkLocationId } : {}),
        }));
      }
      if (action === "clock-in") setClockInOpen(false);
      if (data.geofence_warning) {
        setNotice({ kind: "warn", text: "You weren't within the office radius. Your attendance is recorded as usual, and it has been flagged for your manager." });
      } else if (loc.error) {
        setNotice({ kind: "info", text: `${loc.error} Your attendance was still recorded.` });
      } else {
        setNotice({ kind: "ok", text: "GPS location captured." });
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
          {formatCompanyTime(now, true)}
        </div>
        {error && <div style={{ color: "var(--color-danger)", fontSize: 12.5, marginTop: 6 }}>{error}</div>}
        {locating && <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>📍 Getting your location…</div>}
        {notice && (
          <div style={{ ...noticeStyle[notice.kind], fontSize: 12.5, borderRadius: 6, padding: "7px 10px", marginTop: 8, maxWidth: 520 }}>{notice.text}</div>
        )}
        {selfieRequired && clockedIn && (
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
                  {x.work_location_name && <span className="att-chip" style={{ marginLeft: 8 }}>{x.work_location_name}</span>}
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
      </div>
      <div>
        {!record?.clock_in && (
          <button className="btn btn-success" disabled={busy} onClick={openClockIn}>
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
            <button className="btn btn-success" disabled={busy} onClick={openClockIn}>{busy ? "Please wait…" : "Check In"}</button>
            <button className="btn btn-outline" style={{ marginLeft: 6 }} onClick={() => { setReentering(false); setReason(""); setError(""); }}>Cancel</button>
          </>
        )}
      </div>
      {clockInOpen && (
        <div className="modal-overlay clock-in-location-overlay" role="presentation">
          <div ref={clockInDialogRef} className="modal-box" role="dialog" aria-modal="true" aria-labelledby="clock-in-location-title" tabIndex={-1}>
            <h3 id="clock-in-location-title" style={{ marginBottom: 6 }}>{canCheckInAgain ? "Check in again" : "Clock in"}</h3>
            <p className="muted" style={{ fontSize: 13, marginBottom: 14 }}>
              We’ll check your location before showing the clock-in options.
            </p>
            {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
            {clockInLocationStatus === "loading" && (
              <div className="muted" role="status" style={{ marginBottom: 14 }}>Getting and verifying your location…</div>
            )}
            {clockInLocationStatus === "error" && (
              <div style={{ marginBottom: 14 }}>
                <div className="login-error" role="alert" style={{ marginBottom: 8 }}>{clockInLocationError}</div>
                {showLocationInstructions && (
                  <p className="muted" style={{ fontSize: 12.5, marginBottom: 8 }}>
                    To allow location, click the site controls icon beside the address bar, open site permissions or settings, set Location to Allow, then retry. In other browsers, open this site’s permissions and allow Location.
                  </p>
                )}
                <button type="button" className="btn btn-sm btn-outline" onClick={checkClockInLocation}>Retry location check</button>
              </div>
            )}
            {clockInLocationStatus === "ready" && (
              <div
                role="status"
                style={{
                  background: clockInLocation.office_configured && clockInLocation.within_office
                    ? "var(--color-success-100)"
                    : "var(--color-warning-100)",
                  color: clockInLocation.office_configured && clockInLocation.within_office
                    ? "#067647"
                    : "#b54708",
                  fontSize: 13,
                  borderRadius: 6,
                  padding: "9px 12px",
                  marginBottom: 14,
                }}
              >
                <div>
                  {clockInLocation.office_configured
                    ? clockInLocation.within_office
                      ? "Your location was fetched. You are in the office."
                      : "Your location was fetched. You are out of the office."
                    : "Your location was fetched, but no office geofence is configured, so we could not determine whether you are in or out of the office."}
                </div>
                <div style={{ marginTop: 6 }}>
                  Your location is: {clockInLocation.latitude.toFixed(5)}, {clockInLocation.longitude.toFixed(5)}
                  {Number.isFinite(clockInLocation.accuracy) && ` (accuracy ±${Math.round(clockInLocation.accuracy)} m)`}
                  {" · "}
                  <a href={mapsUrl(clockInLocation.latitude, clockInLocation.longitude)} target="_blank" rel="noreferrer">View on map</a>
                </div>
              </div>
            )}
            {workLocationsError && (
              <div className="login-error" style={{ marginBottom: 10 }}>
                {workLocationsError}{" "}
                <button type="button" className="btn btn-sm btn-outline" onClick={loadWorkLocations}>Retry</button>
              </div>
            )}
            {clockInLocationStatus === "ready" && (workLocationsLoading ? <Loader /> : workLocations.length > 0 ? (
              <div className="form-field">
                <label>Work location</label>
                <div className="clock-in-location-options">
                  {workLocations.map((location) => (
                    <label key={location.id} className={`clock-in-location-option${String(location.id) === selectedWorkLocationId ? " selected" : ""}`}>
                      <input
                        type="radio"
                        name="work-location"
                        value={location.id}
                        checked={String(location.id) === selectedWorkLocationId}
                        onChange={() => setSelectedWorkLocationId(String(location.id))}
                      />
                      <span>{location.name}</span>
                      {location.is_default && <span className="muted">Default</span>}
                    </label>
                  ))}
                </div>
              </div>
            ) : !workLocationsError ? (
              <p className="login-error">No active work locations are available. Ask your manager to add one.</p>
            ) : null)}
            {clockInLocationStatus === "ready" && canCheckInAgain && (
              <div className="form-field">
                <label htmlFor="reentry-reason">Reason for checking in again</label>
                <input
                  id="reentry-reason"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  maxLength={255}
                  placeholder="Your manager will see this"
                />
              </div>
            )}
            {clockInLocationStatus === "ready" && selfieRequired && (
              <div className="form-field">
                <label>Photo required by your company</label>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  capture="user"
                  onChange={(event) => setSelfie(event.target.files?.[0] || null)}
                />
              </div>
            )}
            <div className="form-actions">
              <button type="button" className="btn btn-outline" disabled={busy} onClick={() => setClockInOpen(false)}>Cancel</button>
              {clockInLocationStatus === "ready" && (
                <button
                  type="button"
                  className="btn btn-success"
                  disabled={busy || workLocationsLoading || !selectedWorkLocationId || workLocations.length === 0 || !!workLocationsError || (selfieRequired && !selfie) || (canCheckInAgain && reason.trim().length < 3)}
                  onClick={() => handleClock("clock-in")}
                >
                  {busy ? "Clocking in…" : "Choose location and Clock In"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
