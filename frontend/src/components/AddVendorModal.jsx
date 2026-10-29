import { useEffect, useState } from "react";
import client from "../api/client";

const EMPTY_VENDOR = {
  name: "", address: "", state: "Karnataka", gstin: "", pan: "",
  contact_person: "", contact_email: "", contact_phone: "",
  company_id: "", status: "active",
};

export default function AddVendorModal({ onClose, onSaved, vendor = null }) {
  const [companies, setCompanies] = useState([]);
  const [form, setForm] = useState({
    ...EMPTY_VENDOR,
    ...(vendor || {}),
    company_id: vendor?.company_id || "",
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    client.get("/vendors/companies")
      .then(({ data }) => setCompanies(data))
      .catch((err) => setError(err?.response?.data?.message || "Could not load companies."));
  }, []);

  const set = (field) => (e) => setForm((current) => ({ ...current, [field]: e.target.value }));

  const save = async () => {
    setError("");
    if (!form.name.trim()) {
      setError("Vendor name is required.");
      return;
    }
    setSaving(true);
    try {
      const { data } = await client.put(`/vendors/${vendor.id}`, {
        ...form,
        company_id: form.company_id || null,
      });
      onSaved(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not add this vendor.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ width: 560 }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 6 }}>{vendor ? "Edit Vendor" : "Add Vendor"}</h3>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
          Update the vendor's details. Existing agreements, hires, invoices, and bank information are preserved.
        </p>
        {error && <div className="login-error">{error}</div>}

        <h4 style={{ fontSize: 12.5, color: "var(--color-text-muted)", marginBottom: 6 }}>Company &amp; Vendor Information</h4>
        <div className="form-field">
          <label>Company</label>
          <select value={form.company_id} onChange={set("company_id")}>
            <option value="">No company selected</option>
            {companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}
          </select>
        </div>
        <div className="form-grid">
          <div className="form-field">
            <label>Vendor Name</label>
            <input value={form.name} onChange={set("name")} />
          </div>
          <div className="form-field">
            <label>State</label>
            <input value={form.state} onChange={set("state")} />
          </div>
        </div>
        <div className="form-field">
          <label>Address</label>
          <input value={form.address} onChange={set("address")} />
        </div>
        <div className="form-grid">
          <div className="form-field">
            <label>Contact Person</label>
            <input value={form.contact_person} onChange={set("contact_person")} />
          </div>
          <div className="form-field">
            <label>Contact Email</label>
            <input value={form.contact_email} onChange={set("contact_email")} />
          </div>
        </div>
        <div className="form-field">
          <label>Contact Phone</label>
          <input value={form.contact_phone} onChange={set("contact_phone")} />
        </div>
        <div className="form-field">
          <label>Vendor Status</label>
          <select value={form.status} onChange={set("status")}>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>

        <h4 style={{ fontSize: 12.5, color: "var(--color-text-muted)", margin: "14px 0 6px" }}>Tax Information</h4>
        <div className="form-grid">
          <div className="form-field">
            <label>GSTIN</label>
            <input value={form.gstin} onChange={set("gstin")} />
          </div>
          <div className="form-field">
            <label>PAN</label>
            <input value={form.pan} onChange={set("pan")} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
          <button className="btn btn-outline" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={saving} onClick={save}>
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
