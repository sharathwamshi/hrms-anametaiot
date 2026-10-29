import { useEffect, useState } from "react";
import client from "../api/client";

const EMPTY_PROFILE = {
  full_name: "",
  email: "",
  phone: "",
  date_of_birth: "",
  gender: "",
  residential_address: "",
  permanent_address: "",
  emergency_contact_name: "",
  emergency_contact_relationship: "",
  emergency_contact_phone: "",
};

export default function EmployeePersonalDetailsPanel({ employeeId, canEdit = false, onChanged }) {
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await client.get(`/employees/${employeeId}/profile`);
      setProfile({ ...EMPTY_PROFILE, ...data });
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load employee personal information.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [employeeId]);

  const update = (field, value) => setProfile((current) => ({ ...current, [field]: value }));

  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const editableFields = [
        "full_name", "email", "phone", "date_of_birth", "gender",
        "residential_address", "permanent_address", "emergency_contact_name",
        "emergency_contact_relationship", "emergency_contact_phone",
      ];
      const payload = Object.fromEntries(editableFields.map((field) => [field, profile[field]]));
      const { data } = await client.patch(`/employees/${employeeId}/profile`, payload);
      setProfile({ ...EMPTY_PROFILE, ...data.profile });
      setEditing(false);
      setSuccess("Personal information updated.");
      onChanged?.();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update personal information.");
    } finally {
      setBusy(false);
    }
  };

  const field = (label, value) => (
    <div key={label}>
      <div className="muted" style={{ fontSize: 11.5 }}>{label}</div>
      <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{value || "—"}</div>
    </div>
  );

  return (
    <section className="card">
      <div className="card-title-row">
        <h3>Personal &amp; Contact Information</h3>
        {canEdit && !editing && <button className="btn btn-sm btn-outline" onClick={() => setEditing(true)}>Edit</button>}
      </div>
      {error && <div className="login-error" role="alert">{error}</div>}
      {success && <p className="muted" role="status">{success}</p>}
      {loading ? <p className="muted">Loading personal information…</p> : editing ? (
        <form onSubmit={save}>
          <div className="form-grid">
            <div className="form-field">
              <label>Full name</label>
              <input required maxLength={150} value={profile.full_name} onChange={(event) => update("full_name", event.target.value)} />
            </div>
            <div className="form-field">
              <label>Email</label>
              <input type="email" required maxLength={150} value={profile.email} onChange={(event) => update("email", event.target.value)} />
            </div>
          </div>
          <div className="form-grid">
            <div className="form-field">
              <label>Phone</label>
              <input type="tel" maxLength={20} value={profile.phone || ""} onChange={(event) => update("phone", event.target.value)} />
            </div>
            <div className="form-field">
              <label>Date of birth</label>
              <input type="date" max={new Date().toISOString().slice(0, 10)} value={profile.date_of_birth || ""} onChange={(event) => update("date_of_birth", event.target.value)} />
            </div>
          </div>
          <div className="form-field">
            <label>Gender (if applicable)</label>
            <input maxLength={30} value={profile.gender || ""} onChange={(event) => update("gender", event.target.value)} />
          </div>
          <div className="form-grid">
            <div className="form-field">
              <label>Residential address</label>
              <textarea rows={3} maxLength={2000} value={profile.residential_address || ""} onChange={(event) => update("residential_address", event.target.value)} />
            </div>
            <div className="form-field">
              <label>Permanent address</label>
              <textarea rows={3} maxLength={2000} value={profile.permanent_address || ""} onChange={(event) => update("permanent_address", event.target.value)} />
            </div>
          </div>
          <h4>Emergency contact</h4>
          <div className="form-grid">
            <div className="form-field">
              <label>Name</label>
              <input maxLength={150} value={profile.emergency_contact_name || ""} onChange={(event) => update("emergency_contact_name", event.target.value)} />
            </div>
            <div className="form-field">
              <label>Relationship</label>
              <input maxLength={100} value={profile.emergency_contact_relationship || ""} onChange={(event) => update("emergency_contact_relationship", event.target.value)} />
            </div>
          </div>
          <div className="form-field">
            <label>Emergency contact phone</label>
            <input type="tel" maxLength={30} value={profile.emergency_contact_phone || ""} onChange={(event) => update("emergency_contact_phone", event.target.value)} />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>{busy ? "Saving…" : "Save personal information"}</button>
            <button type="button" className="btn btn-outline btn-sm" disabled={busy} onClick={() => { setEditing(false); load(); }}>Cancel</button>
          </div>
        </form>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 18px", fontSize: 12.5 }}>
          {field("Full name", profile.full_name)}
          {field("Email", profile.email)}
          {field("Phone", profile.phone)}
          {field("Date of birth", profile.date_of_birth)}
          {field("Gender", profile.gender)}
          {field("Residential address", profile.residential_address)}
          {field("Permanent address", profile.permanent_address)}
          {field("Emergency contact", profile.emergency_contact_name)}
          {field("Emergency contact relationship", profile.emergency_contact_relationship)}
          {field("Emergency contact phone", profile.emergency_contact_phone)}
        </div>
      )}
    </section>
  );
}
