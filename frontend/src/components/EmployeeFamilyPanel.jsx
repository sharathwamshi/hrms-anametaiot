import { useEffect, useState } from "react";
import client from "../api/client";

const EMPTY_MEMBER = {
  name: "",
  relationship: "",
  date_of_birth: "",
  phone: "",
  is_emergency_contact: false,
  notes: "",
};

export default function EmployeeFamilyPanel({ employeeId, canEdit = true }) {
  const [members, setMembers] = useState([]);
  const [form, setForm] = useState(EMPTY_MEMBER);
  const [editingId, setEditingId] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await client.get("/profile/family", {
        params: employeeId ? { user_id: employeeId } : undefined,
      });
      setMembers(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load family information.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [employeeId]);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const params = employeeId ? { user_id: employeeId } : undefined;
      if (editingId) {
        await client.put(`/profile/family/${editingId}`, form);
      } else {
        await client.post("/profile/family", form, { params });
      }
      setForm(EMPTY_MEMBER);
      setEditingId(null);
      setFormOpen(false);
      await load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save this family member.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (memberId) => {
    if (!window.confirm("Remove this family member?")) return;
    setError("");
    try {
      await client.delete(`/profile/family/${memberId}`);
      await load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not remove this family member.");
    }
  };

  const edit = (member) => {
    setEditingId(member.id);
    setFormOpen(true);
    setForm({
      name: member.name,
      relationship: member.relationship,
      date_of_birth: member.date_of_birth || "",
      phone: member.phone || "",
      is_emergency_contact: member.is_emergency_contact,
      notes: member.notes || "",
    });
  };

  const addFamilyMember = () => {
    setEditingId(null);
    setForm(EMPTY_MEMBER);
    setFormOpen(true);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm(EMPTY_MEMBER);
    setFormOpen(false);
  };

  return (
    <section className="card" aria-labelledby={`family-members-${employeeId || "me"}`}>
      <div className="card-title-row">
        <h3 id={`family-members-${employeeId || "me"}`}>Family Members</h3>
        {canEdit && !formOpen && (
          <button type="button" className="btn btn-sm btn-outline" onClick={addFamilyMember}>Add family member</button>
        )}
      </div>
      {error && <div className="login-error" role="alert">{error}</div>}
      {loading ? <p className="muted">Loading family information…</p> : members.length === 0 ? (
        <p className="muted">No family members added.</p>
      ) : (
        <div style={{ display: "grid", gap: 8, marginBottom: canEdit ? 16 : 0 }}>
          {members.map((member) => (
            <div className="flex-between" key={member.id} style={{ borderTop: "1px solid var(--color-border)", paddingTop: 8, gap: 10 }}>
              <div>
                <strong>{member.name}</strong> · {member.relationship}
                <div className="muted" style={{ fontSize: 11.5 }}>
                  {member.date_of_birth || "Date of birth not provided"}
                  {member.phone ? ` · ${member.phone}` : ""}
                  {member.is_emergency_contact ? " · Emergency contact" : ""}
                </div>
                {member.notes && <div className="muted" style={{ fontSize: 11.5 }}>{member.notes}</div>}
              </div>
              {canEdit && (
                <div style={{ display: "flex", gap: 6 }}>
                  <button type="button" className="btn btn-sm btn-outline" onClick={() => edit(member)}>Edit</button>
                  <button type="button" className="btn btn-sm btn-outline" onClick={() => remove(member.id)}>Remove</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {canEdit && formOpen && (
        <form onSubmit={submit}>
          <div className="form-grid">
            <div className="form-field">
              <label>Name</label>
              <input required maxLength={150} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
            </div>
            <div className="form-field">
              <label>Relationship</label>
              <input required maxLength={100} value={form.relationship} onChange={(event) => setForm({ ...form, relationship: event.target.value })} />
            </div>
          </div>
          <div className="form-grid">
            <div className="form-field">
              <label>Date of birth (optional)</label>
              <input type="date" value={form.date_of_birth} onChange={(event) => setForm({ ...form, date_of_birth: event.target.value })} />
            </div>
            <div className="form-field">
              <label>Phone (optional)</label>
              <input maxLength={30} value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} />
            </div>
          </div>
          <div className="form-field">
            <label>Other relevant information</label>
            <textarea maxLength={500} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
          </div>
          <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
            <input type="checkbox" checked={form.is_emergency_contact} onChange={(event) => setForm({ ...form, is_emergency_contact: event.target.checked })} />
            Designated emergency contact
          </label>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>{busy ? "Saving…" : editingId ? "Save changes" : "Add family member"}</button>
            <button type="button" className="btn btn-outline btn-sm" disabled={busy} onClick={cancelEdit}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}
