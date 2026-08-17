import { useState } from "react";
import client from "../api/client";

export default function AddVendorModal({ onClose, onSaved }) {
  const [form, setForm] = useState({
    name: "", address: "", state: "Karnataka", gstin: "", pan: "",
    contact_person: "", contact_email: "", contact_phone: "",
    bank_name: "", bank_account_no: "", bank_ifsc: "", bank_branch: "",
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  const save = async () => {
    setError("");
    if (!form.name.trim()) {
      setError("Vendor name is required.");
      return;
    }
    setSaving(true);
    try {
      const { data } = await client.post("/vendors", form);
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
        <h3 style={{ marginBottom: 6 }}>Add Vendor</h3>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
          Add a vendor directly — useful if the relationship starts before the agreement is signed. You can upload the agreement for this vendor anytime afterward.
        </p>
        {error && <div className="login-error">{error}</div>}

        <h4 style={{ fontSize: 12.5, color: "var(--color-text-muted)", marginBottom: 6 }}>Basic Information</h4>
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

        <h4 style={{ fontSize: 12.5, color: "var(--color-text-muted)", margin: "14px 0 6px" }}>Billing Information</h4>
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
        <div className="form-grid">
          <div className="form-field">
            <label>Bank Name</label>
            <input value={form.bank_name} onChange={set("bank_name")} />
          </div>
          <div className="form-field">
            <label>Account No.</label>
            <input value={form.bank_account_no} onChange={set("bank_account_no")} />
          </div>
        </div>
        <div className="form-grid">
          <div className="form-field">
            <label>IFSC</label>
            <input value={form.bank_ifsc} onChange={set("bank_ifsc")} />
          </div>
          <div className="form-field">
            <label>Branch</label>
            <input value={form.bank_branch} onChange={set("bank_branch")} />
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
          <button className="btn btn-outline" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={saving} onClick={save}>
            {saving ? "Adding..." : "Add Vendor"}
          </button>
        </div>
      </div>
    </div>
  );
}
