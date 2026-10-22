
import { useEffect, useState } from "react";
import client from "../api/client";
import Badge from "./Badge";
import RegularizeRequestModal from "./RegularizeRequestModal";
import ManagerEditDayModal from "./ManagerEditDayModal";
import ManagerRegularizeModal from "./ManagerRegularizeModal";
import ApplyLeaveModal from "./ApplyLeaveModal";
import { fmtTime, fmtHours, arrivalLabel, placeLabel, localDateStr, formatCompanyDateLabel, formatCompanyDateTime } from "../utils/attendanceTime";
import { mapsUrl } from "../utils/geo";

function Place({ within, lat, lng, label }) {
  const p = placeLabel(within);
  return (
    <span>
      <span className="muted">{label}: </span>
      <span className={`att-chip ${p.cls}`}>{p.text}</span>
      {lat != null && lng != null && (
        <> <a href={mapsUrl(lat, lng)} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>Open in Maps ›</a></>
      )}
    </span>
  );
}

function changedTimes(details) {
  const before = details?.before || [];
  const after = details?.after || [];
  const count = Math.max(before.length, after.length);
  if (!count) return "No session times recorded.";
  return Array.from({ length: count }, (_, i) => {
    const oldSession = before[i];
    const newSession = after[i];
    if (!oldSession) {
      return `Session ${newSession.session_no} added: ${fmtTime(newSession.clock_in)} → ${fmtTime(newSession.clock_out)}`;
    }
    if (!newSession) {
      return `Session ${oldSession.session_no} removed: ${fmtTime(oldSession.clock_in)} → ${fmtTime(oldSession.clock_out)}`;
    }
    return `Session ${newSession.session_no}: ${fmtTime(oldSession.clock_in)} → ${fmtTime(oldSession.clock_out)} changed to ${fmtTime(newSession.clock_in)} → ${fmtTime(newSession.clock_out)}`;
  }).join("; ");
}

/** Everything about one day: each check-in/out, where it happened, why, who corrected it — plus the actions. */
export default function DayDetailModal({ day, person, manager, onClose, onChanged }) {
  const [sub, setSub] = useState(null);
  const [regularizationQuota, setRegularizationQuota] = useState(null);
  const [quotaError, setQuotaError] = useState("");
  const rec = day.rec;
  const sessions = rec?.sessions || [];
  const pastOrToday = day.ds <= localDateStr();
  const pretty = formatCompanyDateLabel(day.ds, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const regularized = rec?.is_regularized || rec?.status === "regularized";
  const pending = rec?.regularization_status === "pending";

  useEffect(() => {
    if (manager) return undefined;
    let cancelled = false;
    client.get("/attendance/regularization-limit")
      .then(({ data }) => {
        if (!cancelled) setRegularizationQuota(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setQuotaError(
            err?.response?.data?.message ||
            "Could not load your regularization limit."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [manager]);

  if (sub === "request") {
    return (
      <RegularizeRequestModal
        record={{ work_date: day.ds }}
        onClose={() => setSub(null)}
        onDone={onChanged}
      />
    );
  }

  if (sub === "edit") {
    return (
      <ManagerEditDayModal
        person={person}
        day={day}
        onClose={() => setSub(null)}
        onDone={onChanged}
      />
    );
  }

  if (sub === "regularize") {
    return (
      <ManagerRegularizeModal
        person={person}
        day={day}
        onClose={() => setSub(null)}
        onDone={onChanged}
      />
    );
  }

  if (sub === "leave") {
    return (
      <ApplyLeaveModal
        startDate={day.ds}
        onClose={() => setSub(null)}
        onDone={onChanged}
      />
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-box att-modal-wide"
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
        }}>
          <div>
            <h3 style={{ marginBottom: 2 }}>{pretty}</h3>
            <div className="muted" style={{ fontSize: 12.5 }}>
              {person?.full_name}
              {person?.employee_code ? ` · ${person.employee_code}` : ""}
            </div>
          </div>
          {rec?.status && <Badge status={rec.status} />}
        </div>

        {day.holiday && (
          <div className="att-chip amber" style={{ marginTop: 10 }}>
            Holiday — {day.holiday.name}
          </div>
        )}

        {day.leave && (
          <div className="att-chip" style={{ marginTop: 10 }}>
            {day.leave.status === "pending"
              ? "Leave request pending"
              : "On approved leave"}
            {day.leave.leave_type ? ` — ${day.leave.leave_type}` : ""}
            {day.leave.reason ? ` · ${day.leave.reason}` : ""}
          </div>
        )}

        {day.leaveRequest && (
          <div className="att-chip" style={{ marginTop: 10 }}>
            Leave request
            {day.leaveRequest.leave_type
              ? ` — ${day.leaveRequest.leave_type}`
              : ""}
            : <Badge status={day.leaveRequest.status} />
          </div>
        )}

        {sessions.length === 0 ? (
          <p className="muted" style={{ margin: "16px 0", fontSize: 13.5 }}>
            No check-ins recorded for this day.
          </p>
        ) : (
          <>
            <div style={{
              display: "flex",
              gap: 18,
              margin: "14px 0 4px",
              fontSize: 13,
            }}>
              <span>
                <strong>{fmtHours(rec.total_hours)}</strong>{" "}
                <span className="muted">worked</span>
              </span>
              {rec.check_in_status && (
                <span className={`att-chip ${rec.check_in_status === "late" ? "red" : "green"}`}>
                  {arrivalLabel(rec.check_in_status)}
                </span>
              )}
              <span>
                <strong>{sessions.length}</strong>{" "}
                <span className="muted">
                  check-in{sessions.length > 1 ? "s" : ""}
                </span>
              </span>
              {rec.away_minutes > 0 && (
                <span>
                  <strong>{rec.away_minutes} min</strong>{" "}
                  <span className="muted">away</span>
                </span>
              )}
            </div>
            {sessions.map((x) => (
              <div className="att-session" key={x.session_no}>
                <div className="when">
                  Session {x.session_no}: {fmtTime(x.clock_in)} →{" "}
                  {x.clock_out ? fmtTime(x.clock_out) : "still clocked in"}
                  {x.duration_hours ? (
                    <span className="muted" style={{ fontWeight: 400 }}>
                      {" "}({fmtHours(x.duration_hours)})
                    </span>
                  ) : null}
                </div>

                <div className="meta">
                  <Place
                    label="Check-in"
                    within={x.clock_in_within_geofence}
                    lat={x.clock_in_lat}
                    lng={x.clock_in_lng}
                  />
                  {x.has_clock_in_selfie && (
                    <span className="att-chip">Photo sent</span>
                  )}
                </div>

                {x.clock_out && (
                  <div className="meta">
                    <Place
                      label="Check-out"
                      within={x.clock_out_within_geofence}
                      lat={x.clock_out_lat}
                      lng={x.clock_out_lng}
                    />
                    {x.has_clock_out_selfie && (
                      <span className="att-chip">Photo sent</span>
                    )}
                  </div>
                )}

                {x.reentry_reason && (
                  <div className="why">
                    ↻ Checked in again — “{x.reentry_reason}”
                  </div>
                )}
              </div>
            ))}
          </>
        )}

        {(rec?.regularization_status || regularized) && (
          <div
            className="note-box"
            style={{
              background: "var(--color-brand-orange-50)",
              borderRadius: 8,
              padding: "10px 12px",
              fontSize: 12.5,
              marginTop: 10,
            }}
          >
            <strong>Regularization:</strong>{" "}
            {(rec.regularization_status || "approved")
              .replace(/^./, (c) => c.toUpperCase())}
            {rec.regularization_reason_label
              ? ` — ${rec.regularization_reason_label}`
              : ""}
            {rec.regularization_note && (
              <div className="muted">Note: {rec.regularization_note}</div>
            )}
            {rec.regularization_reviewed_by_name && (
              <div className="muted">
                Reviewed by {rec.regularization_reviewed_by_name}
                {rec.regularization_review_comment
                  ? ` — “${rec.regularization_review_comment}”`
                  : ""}
              </div>
            )}
          </div>
        )}

        {rec?.edited_by_name && (
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            ✎ Corrected by {rec.edited_by_name}
            {rec.edited_at
              ? ` on ${formatCompanyDateTime(rec.edited_at, {
                  day: "numeric",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
                })}`
              : ""}
            {rec.edit_note ? ` — ${rec.edit_note}` : ""}
            {rec.edit_details && <div style={{ marginTop: 4 }}>Changed times: {changedTimes(rec.edit_details)}</div>}
          </div>
        )}

        <div className="form-actions" style={{ marginTop: 18, flexWrap: "wrap" }}>
          <button className="btn btn-outline" onClick={onClose}>
            Close
          </button>

          {!manager && pastOrToday && !regularized && !pending && !day.holiday && (
            <button
              className="btn btn-primary"
              onClick={() => setSub("request")}
            >
              Request regularization
              {regularizationQuota
                ? ` (${regularizationQuota.remaining}/${regularizationQuota.limit} left)`
                : ""}
            </button>
          )}

          {!manager && day.ds >= localDateStr() && !day.leave && !day.holiday && (
            <button
              className="btn btn-primary"
              onClick={() => setSub("leave")}
            >
              Apply for leave
            </button>
          )}

          {manager && pastOrToday && !regularized && (
            <button
              className="btn btn-outline"
              onClick={() => setSub("regularize")}
            >
              Regularize…
            </button>
          )}

          {manager && pastOrToday && (
            <button
              className="btn btn-primary"
              onClick={() => setSub("edit")}
            >
              Edit Attendance
            </button>
          )}
        </div>

        {quotaError && !manager && (
          <p className="login-error" style={{ marginTop: 8, marginBottom: 0 }}>
            {quotaError}
          </p>
        )}
      </div>
    </div>
  );
}
