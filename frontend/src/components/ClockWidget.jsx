import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
export default function ClockWidget({
  onPunch,
  onTimezoneChange,
  presentation = "card",
  minimized = false,
  onToggleMinimized,
  onMinimizedClick,
  dragHandlers,
}) {
  const { hasClockInOut } = useAuth();
  const [record, setRecord] = useState(null);
  const [attendanceLoading, setAttendanceLoading] = useState(true);
  const [attendanceLoadError, setAttendanceLoadError] = useState("");
  const [now, setNow] = useState(new Date());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null); // {kind: 'warn'|'info', text}
  const [selfieRequired, setSelfieRequired] = useState(false);
  const [selfie, setSelfie] = useState(null);
  const [reentering, setReentering] = useState(false);
  const [reason, setReason] = useState("");
  const [workLocations, setWorkLocations] = useState([]);
  const [workLocationsLoading, setWorkLocationsLoading] = useState(false);
  const [workLocationsError, setWorkLocationsError] = useState("");
  const [selectedWorkLocationId, setSelectedWorkLocationId] = useState("");
  const [clockInOpen, setClockInOpen] = useState(false);
  const [clockInLocationStatus, setClockInLocationStatus] = useState("idle");
  const [clockInLocation, setClockInLocation] = useState(null);
  const [clockInLocationError, setClockInLocationError] = useState("");
  const [clockOutOpen, setClockOutOpen] = useState(false);
  const [clockOutLocationStatus, setClockOutLocationStatus] = useState("idle");
  const [clockOutLocation, setClockOutLocation] = useState(null);
  const [clockOutLocationError, setClockOutLocationError] = useState("");
  const [showLocationInstructions, setShowLocationInstructions] = useState(false);
  const fileRef = useRef(null);
  const clockInDialogRef = useRef(null);
  const clockOutDialogRef = useRef(null);
  const punchInFlight = useRef(false);
  const isFloating = presentation === "floating";

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
    const dialogOpen = clockInOpen || clockOutOpen;
    const dialogRef = clockInOpen ? clockInDialogRef : clockOutDialogRef;
    if (!dialogOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement;
    document.body.style.overflow = "hidden";
    dialogRef.current?.focus();
    const keepFocusInDialog = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = dialogRef.current?.querySelectorAll(
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
  }, [clockInOpen, clockOutOpen]);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const fetchToday = async () => {
    setAttendanceLoading(true);
    setAttendanceLoadError("");
    try {
      const { data } = await client.get("/attendance/today");
      setRecord(data.record);
      return data.record;
    } catch (err) {
      setAttendanceLoadError(err?.response?.data?.message || "Could not load your attendance status.");
      throw err;
    } finally {
      setAttendanceLoading(false);
    }
  };

  useEffect(() => {
    if (hasClockInOut) fetchToday().catch(() => {});
  }, [hasClockInOut]);

  useEffect(() => {
    if (!hasClockInOut || !isFloating) return undefined;
    const refreshStatus = () => {
      if (document.visibilityState === "visible" && !punchInFlight.current) {
        fetchToday().catch(() => {});
      }
    };
    const interval = window.setInterval(refreshStatus, 60_000);
    window.addEventListener("focus", refreshStatus);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", refreshStatus);
    };
  }, [hasClockInOut, isFloating]);

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

  const checkClockOutLocation = async () => {
    setClockOutLocationStatus("loading");
    setClockOutLocation(null);
    setClockOutLocationError("");
    setShowLocationInstructions(false);
    const location = await getBrowserLocation();
    if (location.error) {
      setClockOutLocation(location);
      setClockOutLocationStatus("error");
      setClockOutLocationError(location.error);
      setShowLocationInstructions(true);
      return;
    }
    try {
      const { data } = await client.post("/attendance/location-check", {
        latitude: location.latitude,
        longitude: location.longitude,
      });
      setClockOutLocation({ ...location, ...data });
      setClockOutLocationStatus("ready");
    } catch (err) {
      setClockOutLocationStatus("error");
      const message = err?.response?.data?.message || "Could not verify your location. Please try again.";
      setClockOutLocation({ error: message });
      setClockOutLocationError(message);
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

  const openClockOut = () => {
    setError("");
    setNotice(null);
    setClockOutLocationStatus("loading");
    setClockOutLocation(null);
    setClockOutLocationError("");
    setShowLocationInstructions(false);
    setClockOutOpen(true);
    checkClockOutLocation();
  };

  const handleClock = async (action) => {
    if (punchInFlight.current) return;
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
    if (action === "clock-out" && !clockOutLocation) {
      setError("Fetch and verify your location before clocking out.");
      return;
    }
    punchInFlight.current = true;
    setBusy(true);
    setError("");
    setNotice(null);
    try {
      const loc = action === "clock-in"
        ? clockInLocation
        : clockOutLocation;
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
      if (action === "clock-out") setClockOutOpen(false);
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
      await fetchToday().catch(() => {});
      onPunch?.();
    } catch (err) {
      setError(err?.response?.data?.message || "Something went wrong.");
      if (err?.response?.data?.selfie_required) setSelfieRequired(true);
    } finally {
      setBusy(false);
      punchInFlight.current = false;
    }
  };

  const noticeStyle = {
    warn: { background: "var(--color-warning-100)", color: "#b54708" },
    info: { background: "var(--color-primary-50)", color: "var(--color-primary-700)" },
    ok: { background: "var(--color-success-100)", color: "#067647" },
  };

  return (
    <div className={isFloating ? "quick-attendance" : "card clock-widget"}>
      {isFloating && minimized ? (
        <button
          type="button"
          className="quick-attendance-minimized"
          aria-label="Expand Quick Attendance"
          title="Expand Quick Attendance"
          onClick={onMinimizedClick}
          {...dragHandlers}
        >
          <span aria-hidden="true">◷</span>
        </button>
      ) : (
        <>
          {isFloating && (
            <div className="quick-attendance-header" {...dragHandlers}>
              <span className="quick-attendance-grip" aria-hidden="true">⠿</span>
              <strong>Quick Attendance</strong>
              <button
                type="button"
                className="quick-attendance-toggle"
                data-no-drag
                aria-label="Minimize Quick Attendance"
                title="Minimize"
                onClick={onToggleMinimized}
              >
                −
              </button>
            </div>
          )}
          <div className={isFloating ? "quick-attendance-body" : ""}>
            <div style={{ minWidth: 0, flex: 1 }}>
              {!isFloating && <div className="label" style={{ marginBottom: 4 }}>Today's Attendance</div>}
              {isFloating && (
                <div className="quick-attendance-status" role="status">
                  {attendanceLoading
                    ? "Checking attendance status…"
                    : attendanceLoadError
                      ? "Attendance status unavailable"
                      : clockedIn
                        ? `Clocked in${lastSession?.clock_in ? ` since ${fmtTime(lastSession.clock_in)}` : ""}`
                        : canCheckInAgain && lastSession?.clock_out
                          ? `Clocked out at ${fmtTime(lastSession.clock_out)}`
                          : "Not clocked in"}
                </div>
              )}
              <div className={isFloating ? "time quick-attendance-time" : "time"}>
                {formatCompanyTime(now, true)}
              </div>
              {attendanceLoadError && isFloating && (
                <div className="quick-attendance-error" role="alert">
                  {attendanceLoadError}
                  <button type="button" className="btn btn-sm btn-outline" onClick={() => fetchToday().catch(() => {})}>
                    Retry
                  </button>
                </div>
              )}
              {error && <div style={{ color: "var(--color-danger)", fontSize: 12.5, marginTop: 6 }}>{error}</div>}
              {notice && (
                <div style={{ ...noticeStyle[notice.kind], fontSize: 12.5, borderRadius: 6, padding: "7px 10px", marginTop: 8, maxWidth: 520 }}>{notice.text}</div>
              )}
              {selfieRequired && clockedIn && !clockOutOpen && (
                <div style={{ marginTop: 8, fontSize: 12.5 }}>
                  <label className="muted">Photo required by your company: </label>
                  <input
                    ref={fileRef} type="file" accept="image/*" capture="user"
                    onChange={(e) => setSelfie(e.target.files?.[0] || null)}
                  />
                </div>
              )}
              {!isFloating && sessions.length > 0 && (
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
              {!isFloating && canCheckInAgain && !reentering && (
                <div className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>
                  Clocked out{lastSession?.clock_out ? ` at ${fmtTime(lastSession.clock_out)}` : ""}. Clocked out by mistake, or coming back? You can check in again — with a reason your manager can see.
                </div>
              )}
            </div>
            <div className={isFloating ? "quick-attendance-actions" : ""}>
              {(!isFloating || (!attendanceLoading && !attendanceLoadError)) && !record?.clock_in && (
          <button className="btn btn-success" disabled={busy} onClick={openClockIn}>
            {busy ? "Please wait…" : "Clock In"}
          </button>
        )}
              {(!isFloating || (!attendanceLoading && !attendanceLoadError)) && clockedIn && (
          <button className="btn btn-danger" disabled={busy || (isFloating && attendanceLoading)} onClick={openClockOut}>
            {busy ? "Please wait…" : "Clock Out"}
          </button>
        )}
              {(!isFloating || (!attendanceLoading && !attendanceLoadError)) && canCheckInAgain && !reentering && (
          <button className={isFloating ? "btn btn-success" : "btn btn-outline"} onClick={() => setReentering(true)}>Check in again</button>
        )}
              {(!isFloating || (!attendanceLoading && !attendanceLoadError)) && canCheckInAgain && reentering && (
          <>
            <button className="btn btn-success" disabled={busy} onClick={openClockIn}>{busy ? "Please wait…" : "Check In"}</button>
            <button className="btn btn-outline" style={{ marginLeft: 6 }} onClick={() => { setReentering(false); setReason(""); setError(""); }}>Cancel</button>
          </>
        )}
            </div>
          </div>
        </>
      )}
      {clockInOpen && createPortal(
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
        </div>,
        document.body,
      )}
      {clockOutOpen && createPortal(
        <div className="modal-overlay clock-in-location-overlay" role="presentation">
          <div ref={clockOutDialogRef} className="modal-box" role="dialog" aria-modal="true" aria-labelledby="clock-out-location-title" tabIndex={-1}>
            <h3 id="clock-out-location-title" style={{ marginBottom: 6 }}>Clock out</h3>
            <p className="muted" style={{ fontSize: 13, marginBottom: 14 }}>We’ll check your location before clocking you out.</p>
            {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
            {clockOutLocationStatus === "loading" && (
              <div className="muted" role="status" style={{ marginBottom: 14 }}>Getting and verifying your location…</div>
            )}
            {clockOutLocationStatus === "error" && (
              <div style={{ marginBottom: 14 }}>
                <div className="login-error" role="alert" style={{ marginBottom: 8 }}>{clockOutLocationError}</div>
                {showLocationInstructions && (
                  <p className="muted" style={{ fontSize: 12.5, marginBottom: 8 }}>
                    Allow Location in this site’s browser permissions, then retry.
                  </p>
                )}
                <button type="button" className="btn btn-sm btn-outline" onClick={checkClockOutLocation}>Retry location check</button>
              </div>
            )}
            {clockOutLocationStatus === "ready" && (
              <div
                role="status"
                style={{
                  background: clockOutLocation.office_configured && clockOutLocation.within_office
                    ? "var(--color-success-100)"
                    : "var(--color-warning-100)",
                  color: clockOutLocation.office_configured && clockOutLocation.within_office ? "#067647" : "#b54708",
                  fontSize: 13, borderRadius: 6, padding: "9px 12px", marginBottom: 14,
                }}
              >
                <div>
                  {clockOutLocation.office_configured
                    ? clockOutLocation.within_office ? "Your location was fetched. You are in the office." : "Your location was fetched. You are out of the office."
                    : "Your location was fetched, but no office geofence is configured."}
                </div>
                <div style={{ marginTop: 6 }}>
                  Your location is: {clockOutLocation.latitude.toFixed(5)}, {clockOutLocation.longitude.toFixed(5)}
                  {Number.isFinite(clockOutLocation.accuracy) && ` (accuracy ±${Math.round(clockOutLocation.accuracy)} m)`}
                  {" · "}
                  <a href={mapsUrl(clockOutLocation.latitude, clockOutLocation.longitude)} target="_blank" rel="noreferrer">View on map</a>
                </div>
              </div>
            )}
            {(clockOutLocationStatus === "ready" || clockOutLocationStatus === "error") && selfieRequired && (
              <div className="form-field">
                <label>Photo required by your company</label>
                <input ref={fileRef} type="file" accept="image/*" capture="user" onChange={(event) => setSelfie(event.target.files?.[0] || null)} />
              </div>
            )}
            <div className="form-actions">
              <button type="button" className="btn btn-outline" disabled={busy} onClick={() => setClockOutOpen(false)}>Cancel</button>
              {(clockOutLocationStatus === "ready" || clockOutLocationStatus === "error") && (
                <button type="button" className="btn btn-danger" disabled={busy || (selfieRequired && !selfie)} onClick={() => handleClock("clock-out")}>
                  {busy ? "Clocking out…" : clockOutLocationStatus === "error" ? "Clock Out without location" : "Clock Out"}
                </button>
              )}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
