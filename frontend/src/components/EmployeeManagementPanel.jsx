import { useEffect, useState } from "react";
import client from "../api/client";

const EMPTY_COMMUNICATION = {
  family_member_id: "",
  contact_name: "",
  relationship: "",
  contact_phone: "",
  communication_method: "phone",
  purpose: "",
  outcome: "",
  notes: "",
};

export default function EmployeeManagementPanel({ employeeId }) {
  const [uan, setUan] = useState("");
  const [family, setFamily] = useState([]);
  const [communications, setCommunications] = useState([]);
  const [communication, setCommunication] = useState(EMPTY_COMMUNICATION);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [statutory, familyResult, communicationResult] = await Promise.all([
        client.get(`/employees/${employeeId}/statutory`),
        client.get("/profile/family", { params: { user_id: employeeId } }),
        client.get(`/employees/${employeeId}/emergency-communications`),
      ]);
      setUan(statutory.data.uan || "");
      setFamily(familyResult.data);
      setCommunications(communicationResult.data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load employee HR information.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [employeeId]);

  const saveUan = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await client.put(`/employees/${employeeId}/statutory`, { uan: uan.trim() || null });
      setSuccess("UAN saved.");
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save UAN.");
    } finally {
      setBusy(false);
    }
  };

  const submitCommunication = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const payload = {
        ...communication,
        family_member_id: communication.family_member_id ? Number(communication.family_member_id) : null,
      };
      await client.post(`/employees/${employeeId}/emergency-communications`, payload);
      setCommunication(EMPTY_COMMUNICATION);
      await load();
      setSuccess("Emergency communication recorded.");
    } catch (err) {
      setError(err?.response?.data?.message || "Could not record this communication.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <div className="card-title-row"><h3>HR Information</h3></div>
      {error && <div className="login-error" role="alert">{error}</div>}
      {success && <p className="muted" role="status">{success}</p>}
      {loading ? <p className="muted">Loading HR information…</p> : (
        <div style={{ display: "grid", gap: 20 }}>
          <form onSubmit={saveUan}>
            <h4>PF information</h4>
            <div className="form-field">
              <label htmlFor={`employee-uan-${employeeId}`}>UAN</label>
              <input
                id={`employee-uan-${employeeId}`}
                inputMode="numeric"
                autoComplete="off"
                maxLength={12}
                pattern="[0-9]{12}"
                value={uan}
                onChange={(event) => setUan(event.target.value)}
                placeholder="12 digits"
              />
            </div>
            <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>Save UAN</button>
          </form>

          <form onSubmit={submitCommunication}>
            <h4>Emergency contact communication log</h4>
            <div className="form-grid">
              <div className="form-field">
                <label>Family member (optional)</label>
                <select
                  value={communication.family_member_id}
                  onChange={(event) => {
                    const member = family.find((entry) => entry.id === Number(event.target.value));
                    setCommunication({
                      ...communication,
                      family_member_id: event.target.value,
                      ...(member ? {
                        contact_name: member.name,
                        relationship: member.relationship,
                        contact_phone: member.phone || "",
                      } : {}),
                    });
                  }}
                >
                  <option value="">Enter contact details</option>
                  {family.map((member) => <option value={member.id} key={member.id}>{member.name} ({member.relationship})</option>)}
                </select>
              </div>
              <div className="form-field">
                <label>Contact name</label>
                <input required maxLength={150} value={communication.contact_name} onChange={(event) => setCommunication({ ...communication, contact_name: event.target.value })} />
              </div>
            </div>
            <div className="form-grid">
              <div className="form-field">
                <label>Relationship</label>
                <input maxLength={100} value={communication.relationship} onChange={(event) => setCommunication({ ...communication, relationship: event.target.value })} />
              </div>
              <div className="form-field">
                <label>Contact phone</label>
                <input maxLength={30} value={communication.contact_phone} onChange={(event) => setCommunication({ ...communication, contact_phone: event.target.value })} />
              </div>
            </div>
            <div className="form-grid">
              <div className="form-field">
                <label>Method</label>
                <select value={communication.communication_method} onChange={(event) => setCommunication({ ...communication, communication_method: event.target.value })}>
                  <option value="phone">Phone</option>
                  <option value="sms">SMS</option>
                  <option value="email">Email</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className="form-field">
                <label>Purpose</label>
                <input required maxLength={255} value={communication.purpose} onChange={(event) => setCommunication({ ...communication, purpose: event.target.value })} />
              </div>
            </div>
            <div className="form-grid">
              <div className="form-field">
                <label>Outcome</label>
                <input maxLength={255} value={communication.outcome} onChange={(event) => setCommunication({ ...communication, outcome: event.target.value })} />
              </div>
              <div className="form-field">
                <label>Notes</label>
                <input maxLength={1000} value={communication.notes} onChange={(event) => setCommunication({ ...communication, notes: event.target.value })} />
              </div>
            </div>
            <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>Record communication</button>
            <div style={{ display: "grid", gap: 7, marginTop: 12 }}>
              {communications.map((entry) => (
                <div key={entry.id} style={{ borderTop: "1px solid var(--color-border)", paddingTop: 8, fontSize: 12.5 }}>
                  <strong>{entry.contact_name}</strong> · {entry.communication_method} · {entry.contacted_at ? new Date(entry.contacted_at).toLocaleString() : "time unavailable"}
                  <div>{entry.purpose}{entry.outcome ? ` — ${entry.outcome}` : ""}</div>
                  <div className="muted">Recorded by {entry.recorded_by_name || "HR"}</div>
                </div>
              ))}
              {communications.length === 0 && <p className="muted">No communications recorded.</p>}
            </div>
          </form>

        </div>
      )}
    </section>
  );
}
