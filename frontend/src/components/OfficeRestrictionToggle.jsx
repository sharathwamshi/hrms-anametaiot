import { useState } from "react";
import client from "../api/client";

/**
 * Lets a manager (their direct reports), HR Operations or a Super Admin (anyone) require a
 * person to clock in/out from the office. When ON, the server refuses a punch whose position
 * is not inside an active office geofence. OFF (the default) keeps the soft, flag-only rule.
 */
export default function OfficeRestrictionToggle({ person, onChanged }) {
  const [on, setOn] = useState(!!person.restrict_to_office);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const flip = async () => {
    const next = !on;
    if (next && !window.confirm(`Require ${person.full_name} to clock in and out from an office location?\n\nTheir punch will be refused anywhere else (and from the web without location).`)) return;
    setBusy(true); setMsg(null);
    try {
      const { data } = await client.put(`/attendance/team/${person.id}/office-restriction`, { restricted: next });
      setOn(!!data.user.restrict_to_office);
      setMsg(data.no_active_office && next
        ? { cls: "amber", text: "Saved — but no office location has been set up yet, so nothing is enforced until a Super Admin adds one." }
        : { cls: "green", text: next ? "Saved. They can only clock in/out from the office now." : "Saved. Clock in/out is open again (outside punches are only flagged)." });
      onChanged && onChanged(data.user);
    } catch (err) {
      setMsg({ cls: "red", text: err?.response?.data?.message || "Could not save the change." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="office-restriction" style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", padding: "12px 14px", margin: "0 0 14px", borderRadius: 10, border: "1px solid var(--color-border)", background: on ? "#fff3ea" : "var(--color-bg, #f7f8fc)" }}>
      <div style={{ flex: 1, minWidth: 220 }}>
        <strong style={{ fontSize: 13.5 }}>Office-only clock in/out</strong>
        <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>
          {on ? "ON — punches from outside an office are refused." : "OFF — punches from outside an office are allowed but flagged."}
        </div>
        {msg && <div className={`att-chip ${msg.cls}`} style={{ marginTop: 6, display: "inline-block" }}>{msg.text}</div>}
      </div>
      <button data-testid="office-restriction-btn" className={`btn btn-sm ${on ? "btn-outline" : "btn-primary"}`} onClick={flip} disabled={busy}>
        {busy ? "Saving…" : on ? "Turn off" : "Require office"}
      </button>
    </div>
  );
}
