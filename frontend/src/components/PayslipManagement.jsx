import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import client from "../api/client";
import AppLayout from "./AppLayout";
import Badge from "./Badge";
import Loader from "./Loader";
import PayslipDetailModal from "./PayslipDetailModal";
import { numberToWordsInr } from "../utils/numberToWords";
import { PAYROLL_COMPANIES } from "../config/companies";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const EARNING_DEFAULTS = [
  "Basic Salary", "House Rent Allowance", "Conveyance Allowance", "Medical Allowance",
  "Special Allowance", "Personal Pay", "Bonus", "Performance Incentive", "Other Earnings",
];
const DEDUCTION_DEFAULTS = [
  "Provident Fund (PF)", "Employee State Insurance (ESI)", "Professional Tax",
  "Income Tax (TDS)", "Advance Salary", "GPA", "Other Deductions",
];
const EMPLOYEE_FIELDS = [
  ["designation", "Designation"], ["department", "Department"], ["date_of_joining", "Date of Joining"],
  ["pan", "PAN number"], ["pf_number", "PF number"], ["uan_number", "UAN number"],
  ["bank_name", "Bank name"], ["bank_account_number", "Bank account number"],
  ["pay_mode", "Pay mode"], ["location", "Location"],
];
const inputStyle = { border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px", width: "100%" };
const amount = (value) => Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const emptyComponents = (labels) => labels.map((name) => ({ name, amount: 0 }));

function emptyDraft(month, year) {
  return {
    id: null, user_id: "", month, year, company_name: PAYROLL_COMPANIES[1],
    employee_info: {}, total_working_days: new Date(year, month, 0).getDate(), total_paid_days: 0,
    days_present: 0, lop_days: 0,
    earnings: emptyComponents(EARNING_DEFAULTS),
    deductions: emptyComponents(DEDUCTION_DEFAULTS),
  };
}

export default function PayslipManagement({ defaultMonth, defaultYear }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { payslipId } = useParams();
  const isEditor = location.pathname.endsWith("/create") || Boolean(payslipId);
  const [payslips, setPayslips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState(defaultMonth);
  const [year, setYear] = useState(defaultYear);
  const [company, setCompany] = useState("");
  const [search, setSearch] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [employees, setEmployees] = useState([]);
  const [employeeSearching, setEmployeeSearching] = useState(false);
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    if (isEditor) return undefined;
    const timer = setTimeout(() => {
      setLoading(true);
      client.get("/payroll/payslips", {
        params: {
          ...(month ? { month } : {}),
          ...(year ? { year } : {}),
          ...(company ? { company_name: company } : {}),
          ...(search ? { q: search } : {}),
        },
      }).then(({ data }) => setPayslips(data))
        .catch((err) => setError(err?.response?.data?.message || "Could not load payslips."))
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(timer);
  }, [isEditor, month, year, company, search, refresh]);

  useEffect(() => {
    if (!isEditor) return;
    setError("");
    if (!payslipId) {
      setDraft(emptyDraft(
        defaultMonth || new Date().getMonth() + 1,
        defaultYear || new Date().getFullYear(),
      ));
      setCompany(location.state?.company || "");
      return;
    }

    setLoading(true);
    client.get(`/payroll/payslip/${payslipId}`)
      .then(({ data }) => {
        setDraft({
          ...data,
          id: data.id,
          user_id: data.user_id,
          company_name: data.company_name || PAYROLL_COMPANIES[1],
          employee_info: {
            ...data.employee_info,
            full_name: data.employee_info?.full_name || data.employee_name || "",
            employee_code: data.employee_info?.employee_code || "",
          },
        });
      })
      .catch((err) => setError(err?.response?.data?.message || "Could not load this payslip."))
      .finally(() => setLoading(false));
  }, [isEditor, payslipId, location.state, defaultMonth, defaultYear]);

  useEffect(() => {
    let active = true;
    if (!isEditor || !company || employeeSearch.trim().length < 2) {
      setEmployees([]);
      setEmployeeSearching(false);
      return undefined;
    }
    setEmployees([]);
    setEmployeeSearching(true);
    const timer = setTimeout(() => {
      client.get("/payroll/people", { params: { q: employeeSearch.trim(), company_name: company } })
        .then(({ data }) => { if (active) setEmployees(data); })
        .catch((err) => { if (active) setError(err?.response?.data?.message || "Could not search employees."); })
        .finally(() => { if (active) setEmployeeSearching(false); });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [isEditor, company, employeeSearch]);

  const earnings = useMemo(
    () => (draft?.earnings || []).reduce((total, item) => total + Number(item.amount || 0), 0),
    [draft],
  );
  const deductions = useMemo(
    () => (draft?.deductions || []).reduce((total, item) => total + Number(item.amount || 0), 0),
    [draft],
  );

  const startNew = () => {
    setError("");
    setEmployeeSearch("");
    navigate("/payroll/manage/create", { state: { company } });
  };

  const startEdit = (payslip) => {
    setError("");
    navigate(`/payroll/manage/${payslip.id}/edit`);
  };

  const chooseEmployee = (person) => {
    setDraft({
      ...draft,
      user_id: person.id,
      company_name: person.company_name || PAYROLL_COMPANIES[1],
      employee_info: {
        full_name: person.full_name,
        employee_code: person.employee_code,
        designation: person.designation || "",
        department: person.department || "",
        date_of_joining: person.date_of_joining || "",
        uan_number: person.uan_number || "",
        pan: "", pf_number: "", bank_name: "", bank_account_number: "", pay_mode: "", location: "",
      },
    });
    setEmployeeSearch("");
    setEmployees([]);
  };

  const setField = (field, value) => setDraft((current) => ({ ...current, [field]: value }));
  const setEmployeeField = (field, value) => setDraft((current) => ({
    ...current,
    employee_info: { ...current.employee_info, [field]: value },
  }));
  const setComponent = (field, index, key, value) => setDraft((current) => ({
    ...current,
    [field]: current[field].map((item, itemIndex) => (
      itemIndex === index ? { ...item, [key]: value } : item
    )),
  }));
  const addComponent = (field) => setDraft((current) => ({
    ...current,
    [field]: [...current[field], { name: "", amount: 0 }],
  }));
  const removeComponent = (field, index) => setDraft((current) => ({
    ...current,
    [field]: current[field].filter((_item, itemIndex) => itemIndex !== index),
  }));

  const saveDraft = async (event, {
    previewAfterSave = false,
    downloadAfterSave = false,
    publishAfterSave = false,
  } = {}) => {
    event?.preventDefault();
    setError("");
    if (!draft.user_id) {
      setError("Search for and select an employee.");
      return;
    }
    if (deductions > earnings) {
      setError("Total deductions cannot exceed total earnings.");
      return;
    }
    const payload = {
      ...draft,
      user_id: Number(draft.user_id),
      month: Number(draft.month),
      year: Number(draft.year),
      total_working_days: Number(draft.total_working_days),
      total_paid_days: Number(draft.total_paid_days),
      days_present: Number(draft.days_present),
      lop_days: Number(draft.lop_days),
      earnings: draft.earnings.map((row) => ({ ...row, amount: Number(row.amount) })),
      deductions: draft.deductions.map((row) => ({ ...row, amount: Number(row.amount) })),
    };
    setSaving(true);
    const pdfWindow = previewAfterSave ? window.open("about:blank", "_blank") : null;
    try {
      let savedId = draft.id;
      let savedPayslip;
      if (draft.id) {
        const { data } = await client.put(`/payroll/payslips/${draft.id}`, payload);
        savedPayslip = data;
      } else {
        const { data } = await client.post("/payroll/payslips", payload);
        savedId = data.id;
        savedPayslip = data;
      }
      if (savedPayslip) setDraft(savedPayslip);
      if (publishAfterSave && savedId) {
        await client.post(`/payroll/payslips/${savedId}/publish`);
        navigate("/payroll/manage");
        return;
      }
      if ((previewAfterSave || downloadAfterSave) && savedId) {
        const { data: pdf } = await client.get(
          `/payroll/payslips/${savedId}/pdf${previewAfterSave ? "?inline=1" : ""}`,
          { responseType: "blob" },
        );
        const objectUrl = URL.createObjectURL(pdf);
        if (previewAfterSave) {
          if (pdfWindow) pdfWindow.location = objectUrl;
          else window.open(objectUrl, "_blank", "noopener,noreferrer");
        } else {
          const link = document.createElement("a");
          link.href = objectUrl;
          link.download = payslipDownloadName(savedPayslip || payload);
          link.click();
        }
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
      } else if (!downloadAfterSave) {
        navigate("/payroll/manage");
      }
    } catch (err) {
      pdfWindow?.close();
      setError(err?.response?.data?.message || "Could not save this payslip.");
    } finally {
      setSaving(false);
    }
  };

  const publish = async () => {
    await saveDraft(null, { publishAfterSave: true });
  };

  const deleteDraft = async (payslip) => {
    if (!window.confirm("Delete this draft payslip? This cannot be undone.")) return;
    setError("");
    try {
      await client.delete(`/payroll/payslips/${payslip.id}`);
      setRefresh((value) => value + 1);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not delete the draft payslip.");
    }
  };

  const publishFromList = async (payslip) => {
    setError("");
    try {
      await client.post(`/payroll/payslips/${payslip.id}/publish`);
      setRefresh((value) => value + 1);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not publish this payslip.");
    }
  };

  const markPaid = async (payslip) => {
    setError("");
    try {
      await client.post(`/payroll/payslips/${payslip.id}/mark-paid`);
      setRefresh((value) => value + 1);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not mark this payslip as paid.");
    }
  };

  const getPdf = async (payslip, inline = false) => {
    setError("");
    const previewWindow = inline ? window.open("about:blank", "_blank") : null;
    try {
      const { data } = await client.get(
        `/payroll/payslips/${payslip.id}/pdf${inline ? "?inline=1" : ""}`,
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(data);
      if (inline) {
        if (previewWindow) previewWindow.location = url;
        else window.open(url, "_blank", "noopener,noreferrer");
      } else {
        const link = document.createElement("a");
        link.href = url;
        link.download = payslipDownloadName(payslip);
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      previewWindow?.close();
      setError(err?.response?.data?.message || "Could not open the payslip PDF.");
    }
  };

  const payslipDownloadName = (payslip) => {
    const employeeId = payslip.employee_info?.employee_code || payslip.user_id;
    const companyName = (payslip.company_name || "Company").replace(/[^a-z0-9]+/gi, "_");
    const monthName = MONTHS[Number(payslip.month) - 1] || "Month";
    return `${employeeId}_${companyName}_${monthName}_${payslip.year}_Payslip.pdf`;
  };

  if (isEditor) {
    if (loading && payslipId) return <AppLayout title="Payslip Editor"><Loader /></AppLayout>;
    if (!draft) return <AppLayout title="Payslip Editor"><div className="card">{error || "Preparing payslip editor..."}</div></AppLayout>;

    return (
      <AppLayout title={draft.id ? "Edit Payslip" : "Create Payslip"} subtitle="Company-specific payslip editor">
        <section className="card section-gap payslip-editor">
          <div className="card-title-row">
            <div>
              <h2>{draft.id ? "Edit Payslip" : "Create New Payslip"}</h2>
              <p className="muted">{draft.company_name} · {draft.id ? draft.status : "Draft"}</p>
            </div>
            <button type="button" className="btn btn-outline" onClick={() => navigate("/payroll/manage")}>Back to Management</button>
          </div>
          {error && <div className="login-error" role="alert">{error}</div>}
          <form onSubmit={saveDraft}>
            {!draft.id && (
              <>
                <h3>Company and Employee</h3>
                <div className="form-grid">
                  <div className="form-field">
                    <label>Company</label>
                    <select
                      value={company}
                      required
                      onChange={(event) => {
                        setCompany(event.target.value);
                        setEmployeeSearch("");
                        setEmployees([]);
                        setDraft((current) => ({ ...current, user_id: "", company_name: event.target.value, employee_info: {} }));
                      }}
                    >
                      <option value="">Select a company</option>
                      {PAYROLL_COMPANIES.map((name) => <option key={name}>{name}</option>)}
                    </select>
                  </div>
                  <div className="form-field">
                    <label>Search employees in {company || "selected company"}</label>
                    <input
                      value={employeeSearch}
                      onChange={(event) => setEmployeeSearch(event.target.value)}
                      placeholder={company ? "Search by name or employee ID" : "Select a company first"}
                      disabled={!company}
                    />
                    {employees.length > 0 && (
                      <div className="payslip-employee-results">
                        {employees.map((person) => (
                          <button key={person.id} type="button" onClick={() => chooseEmployee(person)}>
                            <span>{person.full_name} · {person.employee_code}</span>
                            <span>{person.company_name}</span>
                          </button>
                        ))}
                      </div>
                    )}
                    {company && employeeSearch.trim().length >= 2 && !employeeSearching && employees.length === 0 && (
                      <p className="muted">No employees found for this company and search.</p>
                    )}
                  </div>
                </div>
              </>
            )}
            {draft.user_id && (
              <>
                <section className="payslip-editor-section">
                  <h3>Employee Details</h3>
                  <div className="payslip-employee-summary">
                    <strong>{draft.employee_info.full_name}</strong>
                    <span>{draft.employee_info.employee_code}</span>
                    <span>{draft.company_name}</span>
                  </div>
                  <div className="form-grid">
                    {EMPLOYEE_FIELDS.map(([key, label]) => (
                      <div className="form-field" key={key}>
                        <label>{label}</label>
                        <input type={key === "date_of_joining" ? "date" : "text"} value={draft.employee_info[key] || ""} onChange={(event) => setEmployeeField(key, event.target.value)} />
                      </div>
                    ))}
                  </div>
                </section>
                <section className="payslip-editor-section">
                  <h3>Payroll Details</h3>
                  <div className="form-grid">
                    <div className="form-field"><label>Payroll Month</label><select value={draft.month} onChange={(event) => setField("month", Number(event.target.value))}>{MONTHS.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}</select></div>
                    <div className="form-field"><label>Payroll Year</label><input type="number" min="2000" max="2200" value={draft.year} onChange={(event) => setField("year", event.target.value)} /></div>
                    <div className="form-field"><label>Total Working Days</label><input type="number" min="0" max="31" step="0.5" value={draft.total_working_days} onChange={(event) => setField("total_working_days", event.target.value)} /></div>
                    <div className="form-field"><label>Present Days</label><input type="number" min="0" max="31" step="0.5" value={draft.days_present} onChange={(event) => setField("days_present", event.target.value)} /></div>
                    <div className="form-field"><label>Total Paid Days</label><input type="number" min="0" max="31" step="0.5" value={draft.total_paid_days} onChange={(event) => setField("total_paid_days", event.target.value)} /></div>
                    <div className="form-field"><label>LOP Days</label><input type="number" min="0" max="31" step="0.5" value={draft.lop_days} onChange={(event) => setField("lop_days", event.target.value)} /></div>
                  </div>
                </section>
                <div className="payslip-components-grid">
                  {[
                    ["earnings", "Earnings", earnings],
                    ["deductions", "Deductions", deductions],
                  ].map(([field, label, total]) => (
                    <section className="payslip-editor-section" key={field}>
                      <div className="card-title-row"><h3>{label}</h3><button type="button" className="btn btn-sm btn-outline" onClick={() => addComponent(field)}>+ Add component</button></div>
                      {draft[field].map((item, index) => (
                        <div className="payslip-component-row" key={`${field}-${index}`}>
                          <input aria-label={`${label} component name`} value={item.name} onChange={(event) => setComponent(field, index, "name", event.target.value)} placeholder="Component name" />
                          <input aria-label={`${label} amount`} type="number" min="0" step="0.01" value={item.amount} onChange={(event) => setComponent(field, index, "amount", event.target.value)} />
                          <button type="button" className="btn btn-sm btn-outline" aria-label={`Remove ${label} component`} onClick={() => removeComponent(field, index)}>Remove</button>
                        </div>
                      ))}
                      <strong>Total {label}: ₹{amount(total)}</strong>
                    </section>
                  ))}
                </div>
                <section className="payslip-net-summary">
                  <strong>Net Pay: ₹{amount(earnings - deductions)}</strong>
                  <span>{numberToWordsInr(earnings - deductions)}</span>
                </section>
                <section className="payslip-editor-section">
                  <h3>Payslip PDF</h3>
                  <div className="payslip-pdf-download-card">
                    <div className="payslip-pdf-details">
                      <strong>{draft.employee_info.full_name || "Employee not selected"}</strong>
                      <span>{draft.company_name}</span>
                      <span>{MONTHS[Number(draft.month) - 1]} {draft.year}</span>
                      <span>Template: {draft.company_name}</span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={saving || !draft.user_id}
                      onClick={() => saveDraft(null, { downloadAfterSave: true })}
                    >
                      {saving ? "Preparing PDF..." : "Download Payslip PDF"}
                    </button>
                  </div>
                </section>
              </>
            )}
            <div className="payslip-editor-actions">
              <button type="button" className="btn btn-outline" onClick={() => navigate("/payroll/manage")}>Cancel</button>
              <button type="button" className="btn btn-outline" disabled={!draft.user_id || saving} onClick={() => saveDraft(null, { previewAfterSave: true })}>Preview Payslip</button>
              <button type="submit" className="btn btn-primary" disabled={saving || !draft.user_id}>{saving ? "Saving..." : draft.id ? "Update Payslip" : "Save as Draft"}</button>
              <button type="button" className="btn btn-success" disabled={saving || !draft.user_id || draft.status === "paid"} onClick={publish}>{draft.status === "published" || draft.status === "updated" ? "Publish Update" : "Publish Payslip"}</button>
            </div>
          </form>
        </section>
      </AppLayout>
    );
  }

  return (
    <AppLayout title="Payslip Management" subtitle="Create, edit, preview and publish company-specific payslips.">
    <section className="card section-gap">
      <div className="card-title-row">
        <div>
          <h2>Payslip Management</h2>
          <p className="muted" style={{ fontSize: 12, margin: "4px 0 0" }}>Create, edit, upload, preview, and publish company-specific payslips.</p>
        </div>
        <button className="btn btn-primary" onClick={startNew}>+ Create New Payslip</button>
      </div>
      {error && <div className="login-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
        <select value={company} onChange={(event) => setCompany(event.target.value)} style={inputStyle}>
          <option value="">All companies</option>
          {PAYROLL_COMPANIES.map((name) => <option key={name}>{name}</option>)}
        </select>
        <select value={month} onChange={(event) => setMonth(event.target.value ? Number(event.target.value) : "")} style={inputStyle}>
          <option value="">All months</option>
          {MONTHS.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}
        </select>
        <input type="number" value={year} onChange={(event) => setYear(event.target.value ? Number(event.target.value) : "")} placeholder="All years" style={{ ...inputStyle, width: 120 }} />
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search employee name or ID" style={{ ...inputStyle, flex: 1, minWidth: 190 }} />
      </div>
      {loading ? <Loader /> : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr><th>Employee ID</th><th>Employee Name</th><th>Company</th><th>Designation</th><th>Payroll Month</th><th>Gross Earnings</th><th>Total Deductions</th><th>Net Pay</th><th>Status</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {payslips.length === 0 && <tr className="empty-row"><td colSpan={10}>No payslips match these filters.</td></tr>}
              {payslips.map((payslip) => (
                <tr key={payslip.id}>
                  <td>{payslip.employee_info?.employee_code}</td>
                  <td><strong>{payslip.employee_name || payslip.employee_info?.full_name}</strong></td>
                  <td>{payslip.company_name}</td>
                  <td>{payslip.employee_info?.designation || "—"}</td>
                  <td>{MONTHS[payslip.month - 1]} {payslip.year}</td>
                  <td>₹{amount(payslip.gross_earnings)}</td>
                  <td>₹{amount(payslip.total_deductions)}</td>
                  <td><strong>₹{amount(payslip.net_pay)}</strong></td>
                  <td><Badge status={payslip.status} /></td>
                  <td>
                    <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                      <button className="btn btn-sm btn-outline" onClick={() => setPreview(payslip)}>View</button>
                      <button className="btn btn-sm btn-outline" onClick={() => startEdit(payslip)}>Edit</button>
                      <button className="btn btn-sm btn-outline" onClick={() => getPdf(payslip, true)}>Preview PDF</button>
                      <button className="btn btn-sm btn-outline" onClick={() => getPdf(payslip)}>PDF</button>
                      {payslip.status === "draft" && <button className="btn btn-sm btn-success" onClick={() => publishFromList(payslip)}>Publish</button>}
                      {payslip.status === "processed" && <button className="btn btn-sm btn-success" onClick={() => markPaid(payslip)}>Mark Paid</button>}
                      {payslip.status === "draft" && <button className="btn btn-sm btn-outline" onClick={() => deleteDraft(payslip)}>Delete</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {preview && <PayslipDetailModal payslip={preview} onClose={() => setPreview(null)} onDownload={() => getPdf(preview)} />}
    </section>
    </AppLayout>
  );
}
