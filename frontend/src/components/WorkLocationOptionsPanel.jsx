import { useEffect, useState } from "react";
import client from "../api/client";
import Loader from "./Loader";

const inputStyle = { border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" };

export default function WorkLocationOptionsPanel() {
  const [locations, setLocations] = useState(null);
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await client.get("/attendance/work-locations", { params: { active_only: "false" } });
      setLocations(data);
      setError("");
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load work locations.");
    }
  };

  useEffect(() => { load(); }, []);

  const add = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await client.post("/attendance/work-locations", { name });
      setName("");
      await load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not add this work location.");
    } finally {
      setBusy(false);
    }
  };

  const update = async (location, changes) => {
    setBusy(true);
    setError("");
    try {
      await client.put(`/attendance/work-locations/${location.id}`, changes);
      setEditing(null);
      await load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update this work location.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <div className="card-title-row"><h3>Work Location Options</h3></div>
      <p className="muted" style={{ fontSize: 12.5, marginTop: -8, marginBottom: 14 }}>
        Employees choose one of these when clocking in. This selection is separate from GPS office geofences.
        Existing office location is the default; Work From Home is also available.
      </p>
      <form onSubmit={add} style={{ display: "flex", gap: 8, alignItems: "flex-end", marginBottom: 16 }}>
        <div className="form-field" style={{ margin: 0, flex: 1, minWidth: 180 }}>
          <label htmlFor="new-work-location">Add a location</label>
          <input id="new-work-location" value={name} onChange={(event) => setName(event.target.value)} maxLength={100} placeholder="e.g. Secondary Office" required />
        </div>
        <button className="btn btn-success btn-sm" disabled={busy || !name.trim()}>{busy ? "Saving…" : "Add location"}</button>
      </form>
      {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
      {locations === null ? <Loader /> : (
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Location</th><th>Status</th><th>Default</th><th>Actions</th></tr></thead>
            <tbody>
              {locations.map((location) => (
                <tr key={location.id}>
                  <td>
                    {editing?.id === location.id ? (
                      <form
                        onSubmit={(event) => {
                          event.preventDefault();
                          update(location, { name: editing.name });
                        }}
                        style={{ display: "flex", gap: 6 }}
                      >
                        <input aria-label="Work location name" value={editing.name} maxLength={100} onChange={(event) => setEditing({ ...editing, name: event.target.value })} required style={inputStyle} />
                        <button className="btn btn-sm btn-success" disabled={busy}>Save</button>
                        <button type="button" className="btn btn-sm btn-outline" onClick={() => setEditing(null)}>Cancel</button>
                      </form>
                    ) : <strong>{location.name}</strong>}
                  </td>
                  <td>{location.is_active ? <span className="att-chip green">Active</span> : <span className="att-chip">Inactive</span>}</td>
                  <td>{location.is_default ? <span className="att-chip green">Default</span> : "—"}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {editing?.id !== location.id && (
                      <>
                        <button className="btn btn-sm btn-outline" disabled={busy} onClick={() => setEditing({ id: location.id, name: location.name })}>Edit</button>{" "}
                        {location.is_active && !location.is_default && (
                          <button className="btn btn-sm btn-outline" disabled={busy} onClick={() => update(location, { is_default: true })}>Make default</button>
                        )}{" "}
                        <button
                          className={`btn btn-sm ${location.is_active ? "btn-outline" : "btn-success"}`}
                          disabled={busy || (location.is_active && location.is_default)}
                          onClick={() => update(location, { is_active: !location.is_active })}
                        >
                          {location.is_active ? "Deactivate" : "Reactivate"}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {locations.length === 0 && <tr className="empty-row"><td colSpan={4}>No work locations are set up.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
