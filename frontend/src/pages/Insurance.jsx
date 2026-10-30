import { useEffect, useMemo, useState } from "react";
import AppLayout from "../components/AppLayout";
import Loader from "../components/Loader";
import client from "../api/client";
import { ROLES } from "../config/roles";
import { useAuth } from "../context/AuthContext";

const MANAGEMENT_ROLES = [ROLES.MANAGER, ROLES.HR_OPERATIONS, ROLES.FINANCE_ACCOUNTS, ROLES.SUPER_ADMIN];
const TYPES = ["health", "life", "accident", "dental", "vision", "travel", "other"];
const EMPTY = {
  employee_id: "", insurance_type: "health", provider_name: "", policy_number: "",
  member_id: "", certificate_number: "", coverage_amount: "", coverage_description: "",
  policy_start_date: "", policy_expiry_date: "", notes: "", contact_name: "",
  contact_email: "", contact_phone: "", credentials: {},
};
const inr = (value) => `₹${Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function statusLabel(status) {
  return { active: "Active", expiring_soon: "Expiring soon", expired: "Expired", archived: "Archived" }[status] || status;
}

export default function Insurance() {
  const { user } = useAuth();
  const isManager = MANAGEMENT_ROLES.includes(user.role);
  const [policies, setPolicies] = useState([]);
  const [summary, setSummary] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [filters, setFilters] = useState({ q: "", type: "", status: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [file, setFile] = useState(null);
  const [fileType, setFileType] = useState("policy");
  const [additionalFile, setAdditionalFile] = useState(null);
  const [additionalFileType, setAdditionalFileType] = useState("policy");
  const [preview, setPreview] = useState(null);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const requests = [client.get("/insurance")];
      if (isManager) requests.push(client.get("/insurance/summary"), client.get("/employees"));
      const results = await Promise.all(requests);
      setPolicies(results[0].data);
      if (isManager) {
        setSummary(results[1].data);
        setEmployees(results[2].data);
      }
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load insurance records.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [isManager]);

  const openPolicy = async (policy) => {
    setSelected(policy);
    setForm({ ...EMPTY, ...policy, employee_id: policy.employee_id, coverage_amount: policy.coverage_amount ?? "" });
    setNotice("");
    setAdditionalFile(null);
    setAdditionalFileType("policy");
    try {
      const { data } = await client.get(`/insurance/${policy.id}/documents`);
      setDocuments(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load insurance documents.");
    }
  };

  const filtered = useMemo(() => policies.filter((policy) => {
    const text = `${policy.employee_name || ""} ${policy.employee_code || ""} ${policy.provider_name} ${policy.policy_number} ${policy.member_id || ""} ${policy.certificate_number || ""}`.toLowerCase();
    return (!filters.q || text.includes(filters.q.toLowerCase()))
      && (!filters.type || policy.insurance_type === filters.type)
      && (!filters.status || policy.expiry_status === filters.status);
  }), [policies, filters]);

  const uploadPolicyDocument = async (policyId, selectedFile, documentType) => {
    const payload = new FormData();
    payload.append("file", selectedFile);
    payload.append("document_type", documentType);
    await client.post(`/insurance/${policyId}/documents`, payload, { headers: { "Content-Type": "multipart/form-data" } });
  };

  const uploadAdditionalDocument = async (event) => {
    event.preventDefault();
    if (!selected || !additionalFile) {
      setError("Choose a document to upload.");
      return;
    }
    setError("");
    try {
      await uploadPolicyDocument(selected.id, additionalFile, additionalFileType);
      setAdditionalFile(null);
      setAdditionalFileType("policy");
      event.currentTarget.reset();
      await openPolicy(selected);
      setNotice("Insurance document uploaded.");
    } catch (err) {
      setError(err?.response?.data?.message || "Could not upload this document.");
    }
  };

  const save = async (event) => {
    event.preventDefault();
    setError("");
    setNotice("");
    const payload = { ...form, employee_id: Number(form.employee_id), coverage_amount: form.coverage_amount === "" ? null : Number(form.coverage_amount) };
    try {
      let policy;
      if (selected) {
        const { data } = await client.put(`/insurance/${selected.id}`, payload);
        policy = data;
      } else {
        const { data } = await client.post("/insurance", payload);
        policy = data;
        if (file) {
          await uploadPolicyDocument(policy.id, file, fileType);
        }
      }
      setNotice("Insurance policy saved.");
      setSelected(null);
      setForm(EMPTY);
      setFile(null);
      setFileType("policy");
      await load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save this insurance policy.");
    }
  };

  const archiveDocument = async (documentId) => {
    try {
      await client.patch(`/insurance/${selected.id}/documents/${documentId}/archive`);
      await openPolicy(selected);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not archive this document.");
    }
  };

  const replaceDocument = async (documentId, replacement) => {
    if (!replacement || !selected) return;
    const payload = new FormData();
    payload.append("file", replacement);
    try {
      await client.post(`/insurance/${selected.id}/documents/${documentId}/replace`, payload, { headers: { "Content-Type": "multipart/form-data" } });
      await openPolicy(selected);
      setNotice("Insurance document replaced.");
    } catch (err) {
      setError(err?.response?.data?.message || "Could not replace this document.");
    }
  };

  const downloadDocument = async (document) => {
    try {
      const { data } = await client.get(document.download_url, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = document.original_filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not download this document.");
    }
  };

  const viewDocument = async (document) => {
    setError("");
    try {
      const { data } = await client.get(document.download_url, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      setPreview((current) => {
        if (current?.url) URL.revokeObjectURL(current.url);
        return {
          document,
          url,
          mimeType: data.type || "",
        };
      });
    } catch (err) {
      setError(err?.response?.data?.message || "Could not open this document.");
    }
  };

  const closePreview = () => {
    setPreview((current) => {
      if (current?.url) URL.revokeObjectURL(current.url);
      return null;
    });
  };

  return (
    <AppLayout title="Insurance" subtitle={isManager ? "Manage employee insurance policies and documents." : "Your assigned insurance policies."}>
      {error && <div className="login-error" role="alert">{error}</div>}
      {notice && <p className="muted" role="status">{notice}</p>}
      {isManager && summary && (
        <div className="stat-grid section-gap">
          <div className="stat-card"><div className="label">Total policies</div><div className="value">{summary.total}</div></div>
          <div className="stat-card"><div className="label">Active policies</div><div className="value">{summary.active}</div></div>
          <div className="stat-card"><div className="label">Expiring within 7 days</div><div className="value">{summary.expiring_soon}</div></div>
          <div className="stat-card"><div className="label">Expired policies</div><div className="value">{summary.expired}</div></div>
        </div>
      )}
      {loading ? <Loader label="Loading insurance records..." /> : (
        <section className="card">
          <div className="card-title-row">
            <h3>{isManager ? "Employee insurance records" : "My insurance policies"}</h3>
          </div>
          <div className="form-grid" style={{ marginBottom: 14 }}>
            <div className="form-field"><label>{isManager ? "Search employee, provider, or policy" : "Search your insurance details"}</label><input placeholder={isManager ? "Search employee, provider, or policy" : "Search provider, policy number, or member ID"} value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} /></div>
            <div className="form-field"><label>Insurance type</label><select value={filters.type} onChange={(e) => setFilters({ ...filters, type: e.target.value })}><option value="">All types</option>{TYPES.map((type) => <option key={type} value={type}>{type}</option>)}</select></div>
            <div className="form-field"><label>Expiry status</label><select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All statuses</option><option value="active">Active</option><option value="expiring_soon">Expiring soon</option><option value="expired">Expired</option><option value="archived">Archived</option></select></div>
          </div>
          <div className="table-wrap"><table className="data-table"><thead><tr><th>Employee</th><th>Type</th><th>Provider</th><th>Policy number</th><th>Expiry</th><th>Status</th><th /></tr></thead><tbody>
            {filtered.map((policy) => <tr key={policy.id}><td>{policy.employee_name || "You"}<div className="muted">{policy.employee_code}</div></td><td>{policy.insurance_type}</td><td>{policy.provider_name}</td><td>{policy.policy_number}</td><td>{policy.policy_expiry_date}</td><td><span className={`chip ${policy.expiry_status === "expired" ? "red" : policy.expiry_status === "expiring_soon" ? "orange" : "green"}`}>{statusLabel(policy.expiry_status)}</span></td><td><button className="btn btn-sm btn-outline" onClick={() => openPolicy(policy)}>View</button></td></tr>)}
            {filtered.length === 0 && <tr className="empty-row"><td colSpan="7">No insurance policies found.</td></tr>}
          </tbody></table></div>
        </section>
      )}
      {(isManager || selected) && (
        <section className="card section-gap">
          <div className="card-title-row"><h3>{selected ? (isManager ? "Edit insurance policy" : "Insurance policy details") : "Assign insurance"}</h3>{selected && <button className="btn btn-outline btn-sm" onClick={() => setSelected(null)}>Close</button>}</div>
          <form id="insurance-policy-form" onSubmit={save}>
            <fieldset disabled={!isManager} style={{ border: 0, padding: 0, margin: 0 }}>
            <div className="form-grid">
              <div className="form-field">
                <label>Employee</label>
                {isManager ? (
                  <select required disabled={Boolean(selected)} value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })}>
                    <option value="">Select employee</option>
                    {employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name} ({employee.employee_code})</option>)}
                  </select>
                ) : (
                  <div className="profile-value">
                    {selected?.employee_name || user.full_name} ({selected?.employee_code || user.employee_code})
                  </div>
                )}
              </div>
              <div className="form-field"><label>Insurance type</label><select value={form.insurance_type} onChange={(e) => setForm({ ...form, insurance_type: e.target.value })}>{TYPES.map((type) => <option key={type} value={type}>{type}</option>)}</select></div>
              <div className="form-field"><label>Provider/company</label><input required value={form.provider_name} onChange={(e) => setForm({ ...form, provider_name: e.target.value })} /></div>
              <div className="form-field"><label>Policy number</label><input required value={form.policy_number} onChange={(e) => setForm({ ...form, policy_number: e.target.value })} /></div>
              <div className="form-field"><label>Member / Insurance ID</label><input value={form.member_id || ""} onChange={(e) => setForm({ ...form, member_id: e.target.value })} /></div>
              <div className="form-field"><label>Certificate number</label><input value={form.certificate_number || ""} onChange={(e) => setForm({ ...form, certificate_number: e.target.value })} /></div>
              <div className="form-field"><label>Coverage amount</label><input type="number" min="0" step="0.01" value={form.coverage_amount} onChange={(e) => setForm({ ...form, coverage_amount: e.target.value })} /></div>
              <div className="form-field"><label>Policy start date</label><input required type="date" value={form.policy_start_date} onChange={(e) => setForm({ ...form, policy_start_date: e.target.value })} /></div>
              <div className="form-field"><label>Policy expiry date</label><input required type="date" value={form.policy_expiry_date} onChange={(e) => setForm({ ...form, policy_expiry_date: e.target.value })} /></div>
              <div className="form-field"><label>Contact name</label><input value={form.contact_name || ""} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} /></div>
              <div className="form-field"><label>Contact email</label><input type="email" value={form.contact_email || ""} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} /></div>
              <div className="form-field"><label>Contact phone</label><input value={form.contact_phone || ""} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} /></div>
            </div>
            {!selected && (
              <div className="form-grid">
                <div className="form-field"><label>Insurance document (optional)</label><input type="file" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" onChange={(e) => setFile(e.target.files[0])} /></div>
                <div className="form-field"><label>Document type</label><select value={fileType} onChange={(e) => setFileType(e.target.value)}><option value="policy">Policy</option><option value="certificate">Certificate</option><option value="insurance_card">Insurance card</option><option value="claim_form">Claim form</option><option value="supporting">Supporting</option><option value="other">Other</option></select></div>
              </div>
            )}
            <div className="form-field"><label>Coverage description</label><textarea rows="2" value={form.coverage_description || ""} onChange={(e) => setForm({ ...form, coverage_description: e.target.value })} /></div>
            <div className="form-field"><label>Additional notes</label><textarea rows="2" value={form.notes || ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
            {!selected && isManager && <button type="submit" className="btn btn-primary">Assign insurance</button>}
            </fieldset>
          </form>
          {selected && <div style={{ marginTop: 20 }}>
            {isManager && <form onSubmit={uploadAdditionalDocument} className="form-grid" style={{ marginBottom: 18 }}>
              <div className="form-field"><label>Upload additional document</label><input required type="file" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" onChange={(e) => setAdditionalFile(e.target.files[0])} /></div>
              <div className="form-field"><label>Document type</label><select value={additionalFileType} onChange={(e) => setAdditionalFileType(e.target.value)}><option value="policy">Policy</option><option value="certificate">Certificate</option><option value="insurance_card">Insurance card</option><option value="claim_form">Claim form</option><option value="supporting">Supporting</option><option value="other">Other</option></select></div>
              <div className="form-field" style={{ alignSelf: "end" }}><button type="submit" className="btn btn-outline">Upload document</button></div>
            </form>}
            <h4>Policy documents</h4>
            {documents.filter((document) => document.status === "active").map((document) => <div key={document.id} className="flex-between" style={{ borderTop: "1px solid var(--color-border)", padding: "8px 0" }}><span>{document.original_filename} <span className="muted">({document.document_type})</span></span><span><button className="btn btn-sm btn-outline" onClick={() => viewDocument(document)}>View</button> <button className="btn btn-sm btn-outline" onClick={() => downloadDocument(document)}>Download</button>{isManager && <><label className="btn btn-sm btn-outline" style={{ marginLeft: 6 }}>Replace<input type="file" hidden accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" onChange={(e) => replaceDocument(document.id, e.target.files[0])} /></label><button className="btn btn-sm btn-outline" onClick={() => archiveDocument(document.id)}>Archive</button></>}</span></div>)}
            {isManager && <button type="submit" form="insurance-policy-form" className="btn btn-primary" style={{ marginTop: 14 }}>Save changes</button>}
          </div>}
        </section>
      )}
      {!isManager && policies.map((policy) => null)}
      {preview && (
        <div className="modal-overlay" onClick={closePreview}>
          <div className="modal-box" style={{ width: 900, maxWidth: "95vw" }} onClick={(event) => event.stopPropagation()}>
            <div className="card-title-row">
              <h3>{preview.document.original_filename}</h3>
              <button type="button" className="btn btn-outline btn-sm" onClick={closePreview}>Close</button>
            </div>
            {preview.mimeType === "application/pdf" ? (
              <iframe title={preview.document.original_filename} src={preview.url} style={{ width: "100%", height: "70vh", border: 0 }} />
            ) : preview.mimeType.startsWith("image/") ? (
              <img src={preview.url} alt={preview.document.original_filename} style={{ display: "block", maxWidth: "100%", maxHeight: "70vh", margin: "0 auto" }} />
            ) : (
              <div className="callout">
                This file type cannot be previewed in the browser. Use Download to open it.
                <div style={{ marginTop: 10 }}>
                  <button type="button" className="btn btn-primary btn-sm" onClick={() => downloadDocument(preview.document)}>Download</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </AppLayout>
  );
}
