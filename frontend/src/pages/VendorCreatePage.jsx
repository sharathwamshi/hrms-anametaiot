import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppLayout from "../components/AppLayout";
import Loader from "../components/Loader";
import client from "../api/client";

const OTHER_COMPANY = "__other_company__";
const MAX_PDF_BYTES = 10 * 1024 * 1024;
const INITIAL_COMPANIES = [
  "Acknowledger First Private Limited",
  "Ana Meta IOT",
  "VKALPA",
];
const INITIAL_ROLE = { role_name: "", service_fee_pct: "", replacement_days: 30, tenure_days: 60 };

export default function VendorCreatePage() {
  const navigate = useNavigate();
  const [companies, setCompanies] = useState([]);
  const [companyValue, setCompanyValue] = useState("");
  const [newCompanyName, setNewCompanyName] = useState("");
  const [vendor, setVendor] = useState({
    name: "",
    contact_person: "",
    contact_email: "",
    contact_phone: "",
    gstin: "",
    pan: "",
  });
  const [agreement, setAgreement] = useState({
    title: "",
    effective_from: "",
    effective_to: "",
    termination_notice_days: "",
    confidentiality_days: "",
    feedback_days: "",
  });
  const [roles, setRoles] = useState([{ ...INITIAL_ROLE }]);
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState("");
  const [extractionToken, setExtractionToken] = useState("");
  const [extractionMessage, setExtractionMessage] = useState("");
  const [extractionError, setExtractionError] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [loadingCompanies, setLoadingCompanies] = useState(true);
  const [companyError, setCompanyError] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);

  useEffect(() => {
    let active = true;
    client.get("/vendors/companies")
      .then(({ data }) => {
        if (active) setCompanies(data);
      })
      .catch((err) => {
        if (active) setCompanyError(err?.response?.data?.message || "Could not load companies.");
      })
      .finally(() => {
        if (active) setLoadingCompanies(false);
      });
    return () => { active = false; };
  }, []);

  const updateVendor = (field) => (event) => {
    setVendor((current) => ({ ...current, [field]: event.target.value }));
  };
  const updateAgreement = (field) => (event) => {
    setAgreement((current) => ({ ...current, [field]: event.target.value }));
  };

  const updateRole = (index, field, value) => {
    setRoles((current) => current.map((role, roleIndex) => (
      roleIndex === index ? { ...role, [field]: value } : role
    )));
  };

  const chooseFile = async (selectedFile) => {
    setFileError("");
    setExtractionToken("");
    setExtractionMessage("");
    setExtractionError(false);
    if (!selectedFile) {
      setFile(null);
      return;
    }
    if (!selectedFile.name.toLowerCase().endsWith(".pdf")
      || (selectedFile.type && selectedFile.type !== "application/pdf")) {
      setFile(null);
      setFileError("Choose a PDF document.");
      return;
    }
    if (selectedFile.size > MAX_PDF_BYTES) {
      setFile(null);
      setFileError("The PDF must be 10 MB or smaller.");
      return;
    }
    setFile(selectedFile);

    const form = new FormData();
    form.append("file", selectedFile);
    setParsing(true);
    setUploadProgress(0);
    try {
      const { data } = await client.post("/vendors/agreements/parse", form, {
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            setUploadProgress(Math.round((progressEvent.loaded / progressEvent.total) * 100));
          }
        },
      });
      setExtractionToken(data.token || "");
      const extractedFields = new Set(data.extracted_fields || []);
      setVendor((current) => ({ ...current, name: data.likely_vendor_name || "" }));
      setAgreement((current) => ({
        ...current,
        effective_from: extractedFields.has("effective_from") ? data.effective_from || "" : "",
        effective_to: extractedFields.has("effective_to") ? data.effective_to || "" : "",
        termination_notice_days: extractedFields.has("termination_notice_days")
          ? data.termination_notice_days : "",
        confidentiality_days: extractedFields.has("confidentiality_days")
          ? data.confidentiality_days : "",
        feedback_days: extractedFields.has("feedback_days") ? data.feedback_days : "",
      }));
      if (Array.isArray(data.roles) && data.roles.length) {
        setRoles(data.roles.map((role) => ({
          role_name: role.role_name || "",
          service_fee_pct: role.service_fee_pct ?? "",
          replacement_days: role.replacement_days ?? 30,
          tenure_days: role.tenure_days ?? 60,
        })));
      } else {
        setRoles([{ ...INITIAL_ROLE }]);
      }
      setExtractionError(false);
      setExtractionMessage(data.used_ai_fallback
        ? "Agreement fields extracted with AI assistance. Review and correct them before saving."
        : extractedFields.length
          ? "Available agreement fields were extracted. Review and correct them before saving."
          : "No agreement fields were identified. Enter the details manually.");
    } catch (err) {
      setExtractionToken("");
      setAgreement((current) => ({
        ...current,
        effective_from: "",
        effective_to: "",
        termination_notice_days: "",
        confidentiality_days: "",
        feedback_days: "",
      }));
      setRoles([{ ...INITIAL_ROLE }]);
      setExtractionError(true);
      setExtractionMessage(
        err?.response?.data?.message
          || "Could not read this agreement. You can still enter the details manually.",
      );
    } finally {
      setParsing(false);
      setUploadProgress(null);
    }
  };

  const validate = () => {
    if (!companyValue) return "Select a company.";
    if (companyValue === OTHER_COMPANY && !newCompanyName.trim()) return "Enter the company name.";
    if (!vendor.name.trim()) return "Vendor name is required.";
    if (!agreement.title.trim() || !agreement.effective_from || !agreement.effective_to) {
      return "Agreement title, start date, and end date are required.";
    }
    if (agreement.effective_to < agreement.effective_from) {
      return "Effective end date cannot precede the start date.";
    }
    const agreementDayValues = [
      agreement.termination_notice_days,
      agreement.confidentiality_days,
      agreement.feedback_days,
    ];
    if (agreementDayValues.some((value) => (
      value === "" || !Number.isInteger(Number(value)) || Number(value) < 0 || Number(value) > 3650
    ))) {
      return "Enter whole-number agreement periods from 0 to 3650 days.";
    }
    if (!roles.length || roles.some((role) => !role.role_name.trim())) {
      return "Enter a role name for each agreement role.";
    }
    if (roles.some((role) => {
      const fee = Number(role.service_fee_pct);
      const replacement = Number(role.replacement_days);
      const tenure = Number(role.tenure_days);
      return !Number.isFinite(fee) || fee < 0 || fee > 100
        || !Number.isInteger(replacement) || replacement < 0 || replacement > 3650
        || !Number.isInteger(tenure) || tenure < 0 || tenure > 3650;
    })) {
      return "Role fees must be 0–100%, and role day values must be whole numbers from 0 to 3650.";
    }
    if (!file) return "Upload the signed agreement PDF.";
    return "";
  };

  const save = async (event) => {
    event.preventDefault();
    setError("");
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    const body = new FormData();
    Object.entries(vendor).forEach(([key, value]) => body.append(key, value));
    Object.entries(agreement).forEach(([key, value]) => body.append(key, value));
    body.append("roles", JSON.stringify(roles.map((role) => ({
      role_name: role.role_name.trim(),
      service_fee_pct: Number(role.service_fee_pct),
      replacement_days: Number(role.replacement_days),
      tenure_days: Number(role.tenure_days),
    }))));
    if (companyValue === OTHER_COMPANY) body.append("new_company_name", newCompanyName.trim());
    else body.append("company_id", companyValue);
    if (extractionToken) body.append("extraction_token", extractionToken);
    else body.append("file", file);

    setSaving(true);
    setUploadProgress(extractionToken ? null : 0);
    try {
      const { data } = await client.post("/vendors/create-with-agreement", body, {
        onUploadProgress: (progressEvent) => {
          if (!extractionToken && progressEvent.total) {
            setUploadProgress(Math.round((progressEvent.loaded / progressEvent.total) * 100));
          }
        },
      });
      navigate("/vendors", { state: { vendorId: data.id } });
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save this vendor and agreement.");
    } finally {
      setSaving(false);
      setUploadProgress(null);
    }
  };

  return (
    <AppLayout title="Add Vendor & Agreement" subtitle="Create the vendor and signed agreement together.">
      <div className="vendor-create-page">
        <div className="vendor-create-header">
          <div className="vendor-create-heading">
            <button type="button" className="btn btn-sm btn-outline" onClick={() => navigate("/vendors", { state: { tab: "vendors" } })}>
              ← Back to All Vendors
            </button>
            <div>
              <h2>Add Vendor &amp; Agreement</h2>
              <p className="muted">Add company and contact details, agreement terms, roles, and the signed PDF.</p>
            </div>
          </div>
          <button className="btn btn-primary" type="submit" form="vendor-create-form" disabled={saving}>
            {saving ? "Saving..." : "Save Vendor & Agreement"}
          </button>
        </div>

        {error && <div className="login-error" role="alert">{error}</div>}
        {companyError && <div className="login-error" role="alert">{companyError}</div>}

        <form id="vendor-create-form" onSubmit={save}>
          <section className="card vendor-form-section">
            <div className="vendor-section-heading">
              <span className="vendor-section-number">01</span>
              <div><h3>Upload Agreement Document</h3><p>Upload the signed agreement PDF. Maximum file size: 10 MB.</p></div>
            </div>
            <label
              className="vendor-upload-area"
              htmlFor="vendor-agreement-file"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                chooseFile(event.dataTransfer.files?.[0]);
              }}
            >
              <span className="vendor-upload-icon" aria-hidden="true">↑</span>
              <strong>{file ? file.name : "Choose or drop a PDF agreement"}</strong>
              <span className="muted">PDF only · Up to 10 MB</span>
              <input id="vendor-agreement-file" type="file" accept=".pdf,application/pdf" onChange={(event) => chooseFile(event.target.files?.[0])} />
            </label>
            {fileError && <div className="login-error" role="alert">{fileError}</div>}
            {parsing && <div className="vendor-upload-progress" role="status">Reading agreement...</div>}
            {uploadProgress !== null && (
              <div className="vendor-upload-progress" role="status">Uploading document: {uploadProgress}%</div>
            )}
            {extractionMessage && (
              <div className={extractionError ? "login-error" : "callout"} role={extractionError ? "alert" : "status"}>
                {extractionMessage}
              </div>
            )}
          </section>

          <section className="card vendor-form-section">
            <div className="vendor-section-heading">
              <span className="vendor-section-number">02</span>
              <div><h3>Company &amp; Vendor Details</h3><p>Select the contracting company and enter vendor contact information.</p></div>
            </div>
            <div className="vendor-form-grid">
              <div className="form-field vendor-company-field">
                <label htmlFor="vendor-company">Company</label>
                {loadingCompanies ? <Loader label="Loading companies..." /> : (
                  <select id="vendor-company" value={companyValue} onChange={(event) => setCompanyValue(event.target.value)} required>
                    <option value="">Select a company</option>
                    {INITIAL_COMPANIES.map((name) => {
                      const company = companies.find((item) => item.name === name);
                      return company && <option key={company.id} value={company.id}>{name}</option>;
                    })}
                    {companies
                      .filter((company) => !INITIAL_COMPANIES.includes(company.name))
                      .map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}
                    <option value={OTHER_COMPANY}>Other (enter company name)</option>
                  </select>
                )}
                {companyValue === OTHER_COMPANY && (
                  <div className="form-field" style={{ marginTop: 10 }}>
                    <label htmlFor="new-company-name">Enter company name</label>
                    <input
                      id="new-company-name"
                      maxLength={150}
                      placeholder="Enter company name"
                      value={newCompanyName}
                      onChange={(event) => setNewCompanyName(event.target.value)}
                      required
                    />
                  </div>
                )}
              </div>
              <div className="form-field">
                <label htmlFor="vendor-name">Vendor name</label>
                <input id="vendor-name" maxLength={150} value={vendor.name} onChange={updateVendor("name")} required />
              </div>
              <div className="form-field">
                <label htmlFor="vendor-contact-person">Contact person</label>
                <input id="vendor-contact-person" maxLength={120} value={vendor.contact_person} onChange={updateVendor("contact_person")} />
              </div>
              <div className="form-field">
                <label htmlFor="vendor-contact-email">Contact email</label>
                <input id="vendor-contact-email" type="email" maxLength={150} value={vendor.contact_email} onChange={updateVendor("contact_email")} />
              </div>
              <div className="form-field">
                <label htmlFor="vendor-contact-phone">Contact phone</label>
                <input id="vendor-contact-phone" type="tel" maxLength={20} value={vendor.contact_phone} onChange={updateVendor("contact_phone")} />
              </div>
              <div className="form-field">
                <label htmlFor="vendor-gstin">GSTIN</label>
                <input id="vendor-gstin" maxLength={20} value={vendor.gstin} onChange={updateVendor("gstin")} />
              </div>
              <div className="form-field">
                <label htmlFor="vendor-pan">PAN</label>
                <input id="vendor-pan" maxLength={20} value={vendor.pan} onChange={updateVendor("pan")} />
              </div>
            </div>
          </section>

          <section className="card vendor-form-section">
            <div className="vendor-section-heading">
              <span className="vendor-section-number">03</span>
              <div><h3>Agreement Details</h3><p>Set the effective period and agreement terms.</p></div>
            </div>
            <div className="vendor-form-grid">
              <div className="form-field vendor-field-wide">
                <label htmlFor="agreement-title">Agreement title</label>
                <input id="agreement-title" maxLength={150} value={agreement.title} onChange={updateAgreement("title")} required />
              </div>
              <div className="form-field">
                <label htmlFor="agreement-start">Effective start date</label>
                <input id="agreement-start" type="date" value={agreement.effective_from} onChange={updateAgreement("effective_from")} required />
              </div>
              <div className="form-field">
                <label htmlFor="agreement-end">Effective end date</label>
                <input id="agreement-end" type="date" min={agreement.effective_from || undefined} value={agreement.effective_to} onChange={updateAgreement("effective_to")} required />
              </div>
              <div className="form-field">
                <label htmlFor="agreement-notice">Termination notice (days)</label>
                <input id="agreement-notice" type="number" min="0" max="3650" value={agreement.termination_notice_days} onChange={updateAgreement("termination_notice_days")} required />
              </div>
              <div className="form-field">
                <label htmlFor="agreement-confidentiality">Confidentiality period (days)</label>
                <input id="agreement-confidentiality" type="number" min="0" max="3650" value={agreement.confidentiality_days} onChange={updateAgreement("confidentiality_days")} required />
              </div>
              <div className="form-field">
                <label htmlFor="agreement-feedback">Feedback period (days)</label>
                <input id="agreement-feedback" type="number" min="0" max="3650" value={agreement.feedback_days} onChange={updateAgreement("feedback_days")} required />
              </div>
            </div>
          </section>

          <section className="card vendor-form-section">
            <div className="vendor-section-heading">
              <span className="vendor-section-number">04</span>
              <div><h3>Agreement Role Details</h3><p>Add the role fee and billing conditions from the agreement.</p></div>
            </div>
            <div className="table-wrap">
              <table className="data-table vendor-role-table">
                <thead><tr><th>Role</th><th>Fee percentage</th><th>Replacement period (days)</th><th>Billable after (days)</th><th>Actions</th></tr></thead>
                <tbody>
                  {roles.map((role, index) => (
                    <tr key={index}>
                      <td><input aria-label={`Role ${index + 1}`} maxLength={120} value={role.role_name} onChange={(event) => updateRole(index, "role_name", event.target.value)} required /></td>
                      <td><input aria-label={`Fee percentage for role ${index + 1}`} type="number" min="0" max="100" step="0.01" value={role.service_fee_pct} onChange={(event) => updateRole(index, "service_fee_pct", event.target.value)} required /></td>
                      <td><input aria-label={`Replacement days for role ${index + 1}`} type="number" min="0" max="3650" value={role.replacement_days} onChange={(event) => updateRole(index, "replacement_days", event.target.value)} required /></td>
                      <td><input aria-label={`Billable days for role ${index + 1}`} type="number" min="0" max="3650" value={role.tenure_days} onChange={(event) => updateRole(index, "tenure_days", event.target.value)} required /></td>
                      <td><button className="btn btn-sm btn-outline" type="button" disabled={roles.length === 1} onClick={() => setRoles((current) => current.filter((_, roleIndex) => roleIndex !== index))}>Remove</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button className="btn btn-sm btn-outline vendor-add-role" type="button" onClick={() => setRoles((current) => [...current, { ...INITIAL_ROLE }])}>+ Add role</button>
          </section>

          <section className="card vendor-form-section">
            <div className="vendor-section-heading">
              <span className="vendor-section-number">05</span>
              <div><h3>Hires</h3><p>Hires use the existing vendor assignment workflow.</p></div>
            </div>
            <div className="vendor-form-placeholder">
              <strong>No hires assigned yet.</strong>
              <span>Save the vendor and agreement first. You can assign hires from the vendor details view.</span>
            </div>
          </section>

          <section className="card vendor-form-section">
            <div className="vendor-section-heading">
              <span className="vendor-section-number">06</span>
              <div><h3>Invoices</h3><p>Invoices remain tied to an existing vendor record.</p></div>
            </div>
            <div className="vendor-form-placeholder">
              <strong>No invoices yet.</strong>
              <span>Saving this form will not generate an invoice. Existing monthly and one-time invoice actions are available from vendor details after saving.</span>
            </div>
          </section>
        </form>
      </div>
    </AppLayout>
  );
}
