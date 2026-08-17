import { useEffect, useState } from "react";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";

export default function Assets() {
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ asset_tag: "", category: "laptop", description: "" });
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    const { data } = await client.get("/assets");
    setAssets(data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await client.post("/assets", form);
      setShowForm(false);
      setForm({ asset_tag: "", category: "laptop", description: "" });
      load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not add asset.");
    }
  };

  const assign = async (id) => {
    const userId = window.prompt("Employee ID to assign this asset to:");
    if (!userId) return;
    await client.post(`/assets/${id}/assign`, { user_id: Number(userId) });
    load();
  };

  const doReturn = async (id) => {
    await client.post(`/assets/${id}/return`);
    load();
  };

  return (
    <AppLayout title="Assets" subtitle="Track company assets — laptops, ID cards, SIMs and accessories.">
      <div className="card">
        <div className="card-title-row">
          <h3>Asset Register</h3>
          <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>+ Add Asset</button>
        </div>
        {loading ? <Loader /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr><th>Tag</th><th>Category</th><th>Description</th><th>Assigned To</th><th>Status</th><th>Action</th></tr>
              </thead>
              <tbody>
                {assets.length === 0 && <tr className="empty-row"><td colSpan={6}>No assets recorded yet.</td></tr>}
                {assets.map((a) => (
                  <tr key={a.id}>
                    <td>{a.asset_tag}</td>
                    <td>{a.category}</td>
                    <td>{a.description || "—"}</td>
                    <td>{a.holder_name || "—"}</td>
                    <td><Badge status={a.status} /></td>
                    <td>
                      {a.status !== "assigned" ? (
                        <button className="btn btn-sm btn-outline" onClick={() => assign(a.id)}>Assign</button>
                      ) : (
                        <button className="btn btn-sm btn-outline" onClick={() => doReturn(a.id)}>Mark Returned</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>Add Asset</h3>
            {error && <div className="login-error">{error}</div>}
            <form onSubmit={submit}>
              <div className="form-field">
                <label>Asset Tag</label>
                <input required value={form.asset_tag} onChange={(e) => setForm({ ...form, asset_tag: e.target.value })} />
              </div>
              <div className="form-field">
                <label>Category</label>
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                  <option value="laptop">Laptop</option>
                  <option value="id_card">ID Card</option>
                  <option value="sim">SIM</option>
                  <option value="accessory">Accessory</option>
                </select>
              </div>
              <div className="form-field">
                <label>Description</label>
                <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Add Asset</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
