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
  const [departments, setDepartments] = useState([]);
  const [availableTypes, setAvailableTypes] = useState(["health"]);
  const [typeSettings, setTypeSettings] = useState(["health"]);
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [employeeRole, setEmployeeRole] = useState("");
  const [employeeDepartment, setEmployeeDepartment] = useState("");
  const [selectedEmployee, setSelectedEmployee] = useState(null);
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
  const [assignmentSuccess, setAssignmentSuccess] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const requests = [client.get("/insurance"), client.get("/insurance/types")];
      if (isManager) requests.push(client.get("/insurance/summary"), client.get("/employees/departments"));
      const results = await Promise.all(requests);
      setPolicies(results[0].data);
      setAvailableTypes(results[1].data.available_types);
      setTypeSettings(results[1].data.available_types);
      if (isManager) {
        setSummary(results[2].data);
        setDepartments(results[3].data);
      }
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load insurance records.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [isManager]);

  const updateTypeSettings = async (event) => {
    event.preventDefault();
    try {
      const { data } = await client.put("/insurance/types", { available_types: typeSettings });
      setAvailableTypes(data.available_types);
      setForm((current) => data.available_types.includes(current.insurance_type) ? current : { ...current, insurance_type: data.available_types[0] });
      setNotice("Insurance types updated.");
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update insurance types.");
    }
  };

  useEffect(() => {
    if (!isManager || selected) return undefined;
    const query = employeeSearch.trim();
    if (query.length < 2 && !employeeRole && !employeeDepartment) {
      setEmployees([]);
      return undefined;
    }
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const { data } = await client.get("/employees", {
          params: {
            q: query || undefined,
            role: employeeRole || undefined,
            department_id: employeeDepartment || undefined,
            status: "active",
          },
        });
        if (active) setEmployees(data);
      } catch (err) {
        if (active) setError(err?.response?.data?.message || "Could not search employees.");
      }
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [employeeDepartment, employeeRole, employeeSearch, isManager, selected]);

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

  const closePolicy = () => {
    setSelected(null);
    setForm(EMPTY);
    setDocuments([]);
    setEmployees([]);
    setEmployeeSearch("");
    setEmployeeRole("");
    setEmployeeDepartment("");
    setSelectedEmployee(null);
    setFile(null);
    setFileType("policy");
    setAdditionalFile(null);
    setAdditionalFileType("policy");
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
      if (!selected) {
        setAssignmentSuccess(true);
        window.setTimeout(() => setAssignmentSuccess(false), 4000);
      }
      closePolicy();
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

  const deletePolicy = async () => {
    if (!selected || !window.confirm("Delete this insurance policy and its documents? This action cannot be undone.")) return;
    try {
      await client.delete(`/insurance/${selected.id}`);
      closePolicy();
      setDocuments([]);
      setNotice("Insurance policy deleted.");
      await load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not delete this insurance policy.");
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
      {assignmentSuccess && (
        <div className="insurance-assignment-success" role="status">
          <span>Insurance assigned successfully.</span>
          <button type="button" onClick={() => setAssignmentSuccess(false)} aria-label="Close success message">×</button>
        </div>
      )}
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
      {user.role === ROLES.SUPER_ADMIN && (
        <form className="card section-gap" onSubmit={updateTypeSettings}>
          <div className="card-title-row"><h3>Insurance type configuration</h3></div>
          <p className="muted">Super Admin controls which insurance types are available to insurance administrators.</p>
          <div className="form-grid">
            {TYPES.map((type) => <label key={type} className="form-field"><span><input type="checkbox" checked={typeSettings.includes(type)} onChange={(event) => setTypeSettings((current) => event.target.checked ? [...current, type] : current.filter((value) => value !== type))} /> {type}</span></label>)}
          </div>
          <button type="submit" className="btn btn-primary">Save insurance types</button>
        </form>
      )}
      {loading ? <Loader label="Loading insurance records..." /> : (
        <section className="card">
          <div className="card-title-row">
            <h3>{isManager ? "Employee insurance records" : "My insurance policies"}</h3>
          </div>
          <div className="form-grid" style={{ marginBottom: 14 }}>
            <div className="form-field"><label>{isManager ? "Search employee, provider, or policy" : "Search your insurance details"}</label><input placeholder={isManager ? "Search employee, provider, or policy" : "Search provider, policy number, or member ID"} value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} /></div>
            <div className="form-field"><label>Insurance type</label><select value={filters.type} onChange={(e) => setFilters({ ...filters, type: e.target.value })}><option value="">All types</option>{availableTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></div>
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
          <div className="card-title-row"><h3>{selected ? (isManager ? "Edit insurance policy" : "Insurance policy details") : "Assign insurance"}</h3>{selected && <button type="button" className="btn btn-outline btn-sm" onClick={closePolicy}>Close</button>}</div>
          <form id="insurance-policy-form" onSubmit={save}>
            <fieldset disabled={!isManager} style={{ border: 0, padding: 0, margin: 0 }}>
            <div className="form-grid">
              <div className="form-field">
                <label>Employee</label>
                {isManager ? (
                  selected ? (
                    <div className="profile-value">{selected.employee_name} ({selected.employee_code})</div>
                  ) : (
                    <>
                      <input
                        required
                        value={selectedEmployee ? `${selectedEmployee.full_name} (${selectedEmployee.employee_code})` : employeeSearch}
                        placeholder="Search by employee name or number"
                        onChange={(e) => {
                          setEmployeeSearch(e.target.value);
                          setSelectedEmployee(null);
                          setForm({ ...form, employee_id: "" });
                        }}
                      />
                      <div className="form-grid" style={{ marginTop: 8 }}>
                        <div className="form-field">
                          <label>Filter by role</label>
                          <select value={employeeRole} onChange={(e) => { setEmployeeRole(e.target.value); setSelectedEmployee(null); setForm({ ...form, employee_id: "" }); }}>
                            <option value="">All roles</option>
                            <option value={ROLES.EMPLOYEE}>Employee</option>
                            <option value={ROLES.CONTRACT_EMPLOYEE}>Contract employee</option>
                            <option value={ROLES.MANAGER}>Manager</option>
                            <option value={ROLES.HR_OPERATIONS}>HR Operations</option>
                            <option value={ROLES.FINANCE_ACCOUNTS}>Finance & Accounts</option>
                          </select>
                        </div>
                        <div className="form-field">
                          <label>Filter by department</label>
                          <select value={employeeDepartment} onChange={(e) => { setEmployeeDepartment(e.target.value); setSelectedEmployee(null); setForm({ ...form, employee_id: "" }); }}>
                            <option value="">All departments</option>
                            {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                          </select>
                        </div>
                      </div>
                      {employees.length > 0 && !selectedEmployee && (
                        <div style={{ border: "1px solid var(--color-border)", borderRadius: 6, marginTop: 4, maxHeight: 180, overflowY: "auto" }}>
                          {employees.map((employee) => (
                            <button
                              type="button"
                              key={employee.id}
                              onClick={() => {
                                setSelectedEmployee(employee);
                                setEmployeeSearch(employee.full_name);
                                setEmployees([]);
                                setForm({ ...form, employee_id: employee.id });
                              }}
                              style={{ width: "100%", border: 0, background: "transparent", padding: "8px 10px", cursor: "pointer", textAlign: "left", display: "flex", justifyContent: "space-between" }}
                            >
                              <span>{employee.full_name} — {employee.employee_code}</span>
                              <span className="muted">{employee.department_name || employee.role}</span>
                            </button>
                          ))}
                        </div>
                      )}
                      {!selectedEmployee && (employeeSearch.trim().length >= 2 || employeeRole || employeeDepartment) && employees.length === 0 && (
                        <p className="muted" style={{ marginTop: 6 }}>No matching active employees found.</p>
                      )}
                    </>
                  )
                ) : (
                  <div className="profile-value">
                    {selected?.employee_name || user.full_name} ({selected?.employee_code || user.employee_code})
                  </div>
                )}
              </div>
              <div className="form-field"><label>Insurance type</label><select value={form.insurance_type} onChange={(e) => setForm({ ...form, insurance_type: e.target.value })}>{availableTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></div>
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
                <div className="form-field"><label>Insurance document (optional)</label><input type="file" accept="*/*" onChange={(e) => setFile(e.target.files[0])} /></div>
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
              <div className="form-field"><label>Upload additional document</label><input required type="file" accept="*/*" onChange={(e) => setAdditionalFile(e.target.files[0])} /></div>
              <div className="form-field"><label>Document type</label><select value={additionalFileType} onChange={(e) => setAdditionalFileType(e.target.value)}><option value="policy">Policy</option><option value="certificate">Certificate</option><option value="insurance_card">Insurance card</option><option value="claim_form">Claim form</option><option value="supporting">Supporting</option><option value="other">Other</option></select></div>
              <div className="form-field" style={{ alignSelf: "end" }}><button type="submit" className="btn btn-outline">Upload document</button></div>
            </form>}
            <h4>Policy documents</h4>
            {documents.filter((document) => document.status === "active").map((document) => <div key={document.id} className="flex-between" style={{ borderTop: "1px solid var(--color-border)", padding: "8px 0" }}><span>{document.original_filename} <span className="muted">({document.document_type})</span></span><span><button type="button" className="btn btn-sm btn-outline" onClick={() => viewDocument(document)}>View</button> <button type="button" className="btn btn-sm btn-outline" onClick={() => downloadDocument(document)}>Download</button>{isManager && <><label className="btn btn-sm btn-outline" style={{ marginLeft: 6 }}>Replace<input type="file" hidden accept="*/*" onChange={(e) => replaceDocument(document.id, e.target.files[0])} /></label><button type="button" className="btn btn-sm btn-outline" onClick={() => archiveDocument(document.id)}>Archive</button></>}</span></div>)}
            {isManager && <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
              <button type="submit" form="insurance-policy-form" className="btn btn-primary">Save changes</button>
              <button type="button" className="btn btn-outline" onClick={deletePolicy}>Delete policy</button>
            </div>}
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
