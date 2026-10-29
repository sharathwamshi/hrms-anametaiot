import { useState, useEffect } from "react";
import client from "../api/client";

export default function UploadAgreementModal({ onClose, onSaved, initialVendorId = null }) {
  const [file, setFile] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [parsed, setParsed] = useState(null);

  const [allVendors, setAllVendors] = useState([]);
  const [selectedVendorValue, setSelectedVendorValue] = useState(initialVendorId ? String(initialVendorId) : "");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [effectiveTo, setEffectiveTo] = useState("");
  const [terminationDays, setTerminationDays] = useState(90);
  const [confidentialityDays, setConfidentialityDays] = useState(60);
  const [feedbackDays, setFeedbackDays] = useState(2);
  const [roles, setRoles] = useState([]);

  useEffect(() => {
    client.get("/vendors")
      .then(({ data }) => setAllVendors(data))
      .catch((err) => setError(err?.response?.data?.message || "Could not load vendors."));
  }, []);

  const runParse = async () => {
    if (!file) return;
    setParsing(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await client.post("/vendors/agreements/parse", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setParsed(data);
      setEffectiveFrom(data.effective_from || "");
      setEffectiveTo(data.effective_to || "");
      setTerminationDays(data.termination_notice_days || 90);
      setConfidentialityDays(data.confidentiality_days || 60);
      setFeedbackDays(data.feedback_days || 2);
      setRoles(data.roles || []);

      if (initialVendorId) {
        setSelectedVendorValue(String(initialVendorId));
      } else if (data.matched_vendor) {
        setSelectedVendorValue(String(data.matched_vendor.id));
      } else {
        setSelectedVendorValue("");
      }
    } catch (err) {
      setError(err?.response?.data?.message || "Could not read this agreement. Try a text-based PDF (not a scanned image).");
    } finally {
      setParsing(false);
    }
  };

  const updateRole = (i, field, value) => {
    const next = [...roles];
    next[i] = { ...next[i], [field]: value };
    setRoles(next);
  };

  const removeRole = (i) => setRoles(roles.filter((_, idx) => idx !== i));
  const addRole = () => setRoles([...roles, { role_name: "", service_fee_pct: 0, replacement_days: 30, tenure_days: 60 }]);

  const confirm = async () => {
    setError("");
    if (!selectedVendorValue) {
      setError("Select the vendor for this agreement.");
      return;
    }
    if (!effectiveFrom) {
      setError("Effective start date is required.");
      return;
    }
    if (roles.length === 0) {
      setError("At least one role with a service fee is required.");
      return;
    }
    setSaving(true);
    try {
      const body = {
        token: parsed.token,
        effective_from: effectiveFrom,
        effective_to: effectiveTo || null,
        termination_notice_days: Number(terminationDays),
        confidentiality_days: Number(confidentialityDays),
        feedback_days: Number(feedbackDays),
        roles: roles.map((r) => ({
          role_name: r.role_name, service_fee_pct: Number(r.service_fee_pct),
          replacement_days: Number(r.replacement_days), tenure_days: Number(r.tenure_days),
        })),
      };
      body.vendor_id = Number(selectedVendorValue);
      const { data } = await client.post("/vendors/agreements/confirm", body);
      onSaved(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save this agreement.");
    } finally {
      setSaving(false);
    }
  };

  const matchedVendor = parsed?.matched_vendor;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ width: 640 }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 6 }}>Add Agreement</h3>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
          Upload the signed agreement for this vendor — extracted dates and role terms can be reviewed before saving.
        </p>
        {error && <div className="login-error">{error}</div>}

        {!parsed && (
          <>
            <input type="file" accept=".pdf" onChange={(e) => setFile(e.target.files[0])} />
            <div style={{ marginTop: 16, textAlign: "right" }}>
              <button className="btn btn-outline" onClick={onClose} style={{ marginRight: 8 }}>Cancel</button>
              <button className="btn btn-primary" disabled={!file || parsing} onClick={runParse}>
                {parsing ? "Reading agreement..." : "Read Agreement"}
              </button>
            </div>
          </>
        )}

        {parsed && (
          <>
            {parsed.used_ai_fallback && (
              <div className="callout" style={{ marginBottom: 12 }}>
                Some fields needed AI assistance to extract — please double-check the effective dates below.
              </div>
            )}

            <div className="card" style={{ marginBottom: 14, padding: 14 }}>
              <div className="card-title-row"><h3 style={{ fontSize: 14 }}>Vendor</h3></div>
              {!initialVendorId && matchedVendor && (
                <div className="callout note" style={{ marginBottom: 10, fontSize: 11.5 }}>
                  We matched this agreement to <strong>{matchedVendor.name}</strong> automatically.
                </div>
              )}
              <div className="form-field">
                <label htmlFor="agreement-vendor">Vendor</label>
                <select id="agreement-vendor" value={selectedVendorValue} disabled={Boolean(initialVendorId)} onChange={(e) => setSelectedVendorValue(e.target.value)}>
                  <option value="" disabled>Select a vendor...</option>
                  {allVendors.map((v) => (
                    <option key={v.id} value={v.id}>{v.name}{v.id === matchedVendor?.id ? " (matched)" : ""}</option>
                  ))}
                </select>
              </div>
            </div>

            {selectedVendorValue && (
              <>
                <div className="form-grid">
                  <div className="form-field">
                    <label>Effective From</label>
                    <input type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} />
                  </div>
                  <div className="form-field">
                    <label>Effective To</label>
                    <input type="date" value={effectiveTo} onChange={(e) => setEffectiveTo(e.target.value)} />
                  </div>
                </div>
                <div className="form-grid">
                  <div className="form-field">
                    <label>Termination Notice (days)</label>
                    <input type="number" value={terminationDays} onChange={(e) => setTerminationDays(e.target.value)} />
                  </div>
                  <div className="form-field">
                    <label>Confidentiality Period (days)</label>
                    <input type="number" value={confidentialityDays} onChange={(e) => setConfidentialityDays(e.target.value)} />
                  </div>
                </div>

                <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--color-text-muted)" }}>Rate Card (from the fee table)</label>
                {roles.map((r, i) => (
                  <div key={i} style={{ display: "flex", gap: 6, marginTop: 6, alignItems: "center" }}>
                    <input placeholder="Role name" value={r.role_name} onChange={(e) => updateRole(i, "role_name", e.target.value)} style={{ flex: 2 }} />
                    <input type="number" step="0.01" placeholder="Fee %" value={r.service_fee_pct} onChange={(e) => updateRole(i, "service_fee_pct", e.target.value)} style={{ width: 70 }} />
                    <span className="muted" style={{ fontSize: 11 }}>%</span>
                    <input type="number" placeholder="Replace days" value={r.replacement_days} onChange={(e) => updateRole(i, "replacement_days", e.target.value)} style={{ width: 60 }} />
                    <input type="number" placeholder="Tenure days" value={r.tenure_days} onChange={(e) => updateRole(i, "tenure_days", e.target.value)} style={{ width: 60 }} />
                    <button className="btn btn-sm btn-outline" onClick={() => removeRole(i)}>&times;</button>
                  </div>
                ))}
                <button className="btn btn-sm btn-outline" style={{ marginTop: 8 }} onClick={addRole}>+ Add Role</button>
              </>
            )}

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 20 }}>
              <button className="btn btn-outline" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" disabled={saving || !selectedVendorValue} onClick={confirm}>
                {saving ? "Saving..." : "Add Agreement"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
