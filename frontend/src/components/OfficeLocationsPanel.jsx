import { useEffect, useState } from "react";
import client from "../api/client";
import Loader from "./Loader";
import { getBrowserLocation, mapsUrl } from "../utils/geo";

const inputStyle = { border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" };
const blank = { name: "", latitude: "", longitude: "", radius_meters: "200" };

/** Office geofences: the places people are expected to punch from. Only a Super Admin can change them. */
export default function OfficeLocationsPanel({ canManage }) {
  const [rows, setRows] = useState(null);
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
  const [locating, setLocating] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = () => client.get("/attendance/office-locations", { params: { active_only: "false" } }).then(({ data }) => setRows(data));
  useEffect(() => { load(); }, []);

  const useMyLocation = async () => {
    setLocating(true); setError("");
    const loc = await getBrowserLocation();
    setLocating(false);
    if (loc.error) { setError("Could not read your location — allow location access in the browser, or type the coordinates."); return; }
    setForm((f) => ({ ...f, latitude: loc.latitude.toFixed(6), longitude: loc.longitude.toFixed(6) }));
  };

  const add = async (e) => {
    e.preventDefault(); setError(""); setBusy(true);
    try {
      await client.post("/attendance/office-locations", {
        name: form.name, latitude: Number(form.latitude), longitude: Number(form.longitude), radius_meters: Number(form.radius_meters) || 200,
      });
      setForm(blank); load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not add this office.");
    } finally { setBusy(false); }
  };
  const patch = async (o, body) => { await client.put(`/attendance/office-locations/${o.id}`, body); load(); };
  const editRadius = async (o) => {
    const v = window.prompt(`New radius in metres for "${o.name}"`, String(o.radius_meters));
    if (v && Number(v) > 0) patch(o, { radius_meters: Number(v) });
  };
  const remove = async (o) => {
    if (!window.confirm(`Remove "${o.name}"? Past punches keep their in/out-of-office flag.`)) return;
    await client.delete(`/attendance/office-locations/${o.id}`); load();
  };

  return (
    <div className="card">
      <div className="card-title-row"><h3>Office Locations (geofences)</h3></div>
      <p className="muted" style={{ fontSize: 12.5, marginTop: -8, marginBottom: 14 }}>
        A punch inside any active circle counts as “in office”. By default a punch outside is still recorded but flagged;
        managers can switch on <strong>Office-only clock in/out</strong> for a person to refuse it instead.
        {!canManage && " Only a Super Admin can add or change offices."}
      </p>
      {canManage && (
        <form onSubmit={add} style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16, alignItems: "flex-end" }}>
          <div className="form-field" style={{ marginBottom: 0, flex: 1, minWidth: 170 }}>
            <label>Name</label>
            <input data-testid="office-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Bengaluru HQ" required />
          </div>
          <div className="form-field" style={{ marginBottom: 0, width: 130 }}>
            <label>Latitude</label>
            <input data-testid="office-lat" type="number" step="any" value={form.latitude} onChange={(e) => setForm({ ...form, latitude: e.target.value })} required />
          </div>
          <div className="form-field" style={{ marginBottom: 0, width: 130 }}>
            <label>Longitude</label>
            <input data-testid="office-lng" type="number" step="any" value={form.longitude} onChange={(e) => setForm({ ...form, longitude: e.target.value })} required />
          </div>
          <div className="form-field" style={{ marginBottom: 0, width: 110 }}>
            <label>Radius (m)</label>
            <input data-testid="office-radius" type="number" min="20" value={form.radius_meters} onChange={(e) => setForm({ ...form, radius_meters: e.target.value })} />
          </div>
          <button type="button" className="btn btn-sm btn-outline" onClick={useMyLocation} disabled={locating}>{locating ? "Locating…" : "Use my location"}</button>
          <button data-testid="office-add" className="btn btn-primary btn-sm" disabled={busy}>Add office</button>
        </form>
      )}
      {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
      {rows === null ? <Loader /> : (
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Office</th><th>Centre</th><th>Radius</th><th>Status</th>{canManage && <th></th>}</tr></thead>
            <tbody>
              {rows.length === 0 && <tr className="empty-row"><td colSpan={canManage ? 5 : 4}>No office locations yet{canManage ? " — add the first one above." : "."}</td></tr>}
              {rows.map((o) => (
                <tr key={o.id}>
                  <td><strong>{o.name}</strong></td>
                  <td>{o.latitude.toFixed(5)}, {o.longitude.toFixed(5)} <a href={mapsUrl(o.latitude, o.longitude)} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>Maps ›</a></td>
                  <td>{o.radius_meters} m</td>
                  <td>{o.is_active ? <span className="att-chip green">Active</span> : <span className="att-chip">Retired</span>}</td>
                  {canManage && (
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button className="btn btn-sm btn-outline" onClick={() => editRadius(o)}>Radius</button>{" "}
                      <button className={`btn btn-sm ${o.is_active ? "btn-outline" : "btn-success"}`} onClick={() => patch(o, { is_active: !o.is_active })}>{o.is_active ? "Retire" : "Reactivate"}</button>{" "}
                      <button className="btn btn-sm btn-outline" onClick={() => remove(o)}>Remove</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
