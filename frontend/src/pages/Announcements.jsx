import { useEffect, useState } from "react";
import client from "../api/client";
import { parseUtc } from "../utils/datetime";
import AppLayout from "../components/AppLayout";
import Loader from "../components/Loader";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";

export default function Announcements() {
  const { user } = useAuth();
  const isHrOps = user.role === ROLES.HR_OPERATIONS;
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", body: "" });
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    const { data } = await client.get("/announcements");
    setItems(data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await client.post("/announcements", form);
      setShowForm(false);
      setForm({ title: "", body: "" });
      load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not post announcement.");
    }
  };

  return (
    <AppLayout title="Announcements" subtitle="Company-wide updates from HR Operations.">
      <div className="card">
        <div className="card-title-row">
          <h3>All Announcements</h3>
          {isHrOps && <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>+ Post Announcement</button>}
        </div>
        {loading ? <Loader /> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {items.length === 0 && <div className="muted" style={{ fontSize: 13 }}>No announcements yet.</div>}
            {items.map((a) => (
              <div key={a.id} style={{ borderBottom: "1px solid var(--color-border)", paddingBottom: 14 }}>
                <div style={{ fontWeight: 700, fontSize: 14.5 }}>{a.title}</div>
                <div style={{ fontSize: 13, marginTop: 4, color: "var(--color-text)" }}>{a.body}</div>
                <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
                  {a.author_name} &middot; {parseUtc(a.created_at).toLocaleString("en-IN")}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>Post Announcement</h3>
            {error && <div className="login-error">{error}</div>}
            <form onSubmit={submit}>
              <div className="form-field">
                <label>Title</label>
                <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </div>
              <div className="form-field">
                <label>Message</label>
                <textarea required rows={4} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Post</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
