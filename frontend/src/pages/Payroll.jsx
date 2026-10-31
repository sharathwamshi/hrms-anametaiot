import { useEffect, useState } from "react";
import ExportButton from "../components/ExportButton";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import PayslipDetailModal from "../components/PayslipDetailModal";
import PayrollPeopleTab from "../components/PayrollPeopleTab";
import { useAuth } from "../context/AuthContext";
import { ROLES, ROLE_LABELS } from "../config/roles";
import { PAYROLL_COMPANIES } from "../config/companies";

const PAYROLL_ADMIN_ROLES = [ROLES.FINANCE_ACCOUNTS];
const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const EMPTY_TEMPLATE = {
  name: "", description: "",
  basic_pct: 50, hra_pct: 20, special_allowance_pct: 20, other_allowance_pct: 10,
  pf_employee_pct: 6, esi_employee_pct: 0, insurance_pct: 0, professional_tax_flat: 200, tds_pct: 0,
};

export default function Payroll() {
  const { user } = useAuth();
  const isAdmin = PAYROLL_ADMIN_ROLES.includes(user.role);
  const [tab, setTab] = useState("payslips");
  const [myPayslips, setMyPayslips] = useState([]);
  const [allPayslips, setAllPayslips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [month, setMonth] = useState(user.role === ROLES.FINANCE_ACCOUNTS ? new Date().getMonth() + 1 : "");
  const [year, setYear] = useState(user.role === ROLES.FINANCE_ACCOUNTS ? new Date().getFullYear() : "");
  const [structureModal, setStructureModal] = useState(false);
  const [empQuery, setEmpQuery] = useState("");
  const [empResults, setEmpResults] = useState([]);
  const [selectedEmp, setSelectedEmp] = useState(null);
  const [structure, setStructure] = useState({
    basic: 0, hra: 0, special_allowance: 0, other_allowance: 0,
    pf_employee: 0, esi_employee: 0, insurance: 0, professional_tax: 0, tds: 0,
  });
  const [structError, setStructError] = useState("");
  const [selectedPayslip, setSelectedPayslip] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [coverageVersion, setCoverageVersion] = useState(0);
  const [companyFilter, setCompanyFilter] = useState("");

  const load = async () => {
    setLoading(true);
    const params = {
      ...(month ? { month } : {}),
      ...(year ? { year } : {}),
      ...(companyFilter ? { company_name: companyFilter } : {}),
    };
    if (user.role !== ROLES.EMPLOYEE) {
      const { data } = await client.get("/payroll/payslips", { params });
      setAllPayslips(data);
    } else {
      const { data } = await client.get(`/payroll/payslips/${user.id}`, { params });
      setMyPayslips(data);
    }
    setLoading(false);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin, user.id, user.role, month, year, companyFilter]);

  useEffect(() => {
    if (!isAdmin) return;
    client.get("/payroll/coverage", { params: { month, year } }).then(({ data }) => setCoverage(data.summary)).catch(() => {});
  }, [isAdmin, month, year, coverageVersion]);

  const generate = async () => {
    setGenerating(true);
    try {
      await client.post("/payroll/generate", { month, year });
      load();
      setCoverageVersion((v) => v + 1);
    } finally {
      setGenerating(false);
    }
  };

  const searchEmployees = async (q) => {
    setEmpQuery(q);
    setSelectedEmp(null);
    if (q.length < 2) { setEmpResults([]); return; }
    const { data } = await client.get("/employees", { params: { q } });
    setEmpResults(data);
  };

  const pickEmployeeForStructure = async (emp) => {
    setSelectedEmp(emp);
    setEmpResults([]);
    try {
      const { data } = await client.get(`/payroll/structure/${emp.id}`);
      setStructure({
        basic: data.basic || 0, hra: data.hra || 0, special_allowance: data.special_allowance || 0,
        other_allowance: data.other_allowance || 0, pf_employee: data.pf_employee || 0,
        esi_employee: data.esi_employee || 0, insurance: data.insurance || 0,
        professional_tax: data.professional_tax || 0, tds: data.tds || 0,
      });
    } catch {
      // no existing structure yet — leave the form at its defaults for a fresh entry
      setStructure({ basic: 0, hra: 0, special_allowance: 0, other_allowance: 0, pf_employee: 0, esi_employee: 0, insurance: 0, professional_tax: 0, tds: 0 });
    }
  };

  const saveStructure = async (e) => {
    e.preventDefault();
    setStructError("");
    if (!selectedEmp) {
      setStructError("Search and select an employee first.");
      return;
    }
    try {
      await client.post(`/payroll/structure/${selectedEmp.id}`, structure);
      setCoverageVersion((v) => v + 1);
      setStructureModal(false);
      setSelectedEmp(null);
      setEmpQuery("");
    } catch (err) {
      setStructError(err?.response?.data?.message || "Could not save salary structure.");
    }
  };

  return (
    <AppLayout title="Payroll" subtitle={isAdmin ? "Company payslips, salary templates and payroll." : user.role === ROLES.EMPLOYEE ? "Your published payslip history." : "Published payslips · View only"}>
      {isAdmin && (
        <div className="tag-list section-gap">
          <button className={`btn btn-sm ${tab === "payslips" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("payslips")}>Payslips</button>
          <button className={`btn btn-sm ${tab === "templates" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("templates")}>Salary Templates</button>
          <button className={`btn btn-sm ${tab === "people" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("people")}>
            People{coverage && coverage.missing_structure > 0 ? ` (${coverage.missing_structure} to set up)` : ""}
          </button>
        </div>
      )}

      {(!isAdmin || tab === "payslips") && (
        <>
          {isAdmin && (
            <div className="card section-gap">
              <div className="card-title-row">
                <h3>Run Payroll</h3>
                <button className="btn btn-outline btn-sm" onClick={() => setStructureModal(true)}>
                  Set Salary Structure Manually
                </button>
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
                <div className="form-field" style={{ marginBottom: 0 }}>
                  <label>Month</label>
                  <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
                    {MONTH_NAMES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                  </select>
                </div>
                <div className="form-field" style={{ marginBottom: 0 }}>
                  <label>Year</label>
                  <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} style={{ width: 100 }} />
                </div>
                <button className="btn btn-primary" disabled={generating} onClick={generate}>
                  {generating ? "Generating..." : "Generate Payslips"}
                </button>
              </div>
              {coverage && coverage.missing_structure > 0 && (
                <div className="callout warn" style={{ marginTop: 12 }}>
                  {coverage.missing_structure} active {coverage.missing_structure === 1 ? "person has" : "people have"} no salary structure and will be
                  skipped. <a href="#people" onClick={(e) => { e.preventDefault(); setTab("people"); }}>Review in the People tab</a>.
                </div>
              )}
              <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
                Generates draft payslips (with a downloadable PDF for each) for every employee with a salary
                structure defined, using this month's attendance and approved leave to compute loss-of-pay.
              </p>
            </div>
          )}

          {isAdmin && (
            <div className="card section-gap">
              <div className="card-title-row">
                <h3>Published Payslips</h3>
                <span className="muted">View-only · manage drafts in Payslip Management</span>
              </div>
              {loading ? <Loader /> : (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead><tr><th>Employee</th><th>Month</th><th>Present</th><th>LOP Days</th><th>Gross</th><th>Deductions</th><th>Net Pay</th><th>Status</th></tr></thead>
                    <tbody>
                      {allPayslips.filter((payslip) => ["published", "updated", "paid"].includes(payslip.status)).length === 0 && (
                        <tr className="empty-row"><td colSpan={8}>No published payslips found.</td></tr>
                      )}
                      {allPayslips.filter((payslip) => ["published", "updated", "paid"].includes(payslip.status)).map((payslip) => (
                        <tr key={payslip.id} onClick={() => setSelectedPayslip(payslip)} style={{ cursor: "pointer" }}>
                          <td>{payslip.employee_name}</td>
                          <td>{MONTH_NAMES[payslip.month - 1]} {payslip.year}</td>
                          <td>{payslip.days_present}</td>
                          <td>{payslip.lop_days}</td>
                          <td>₹{Number(payslip.gross_earnings || 0).toLocaleString("en-IN")}</td>
                          <td>₹{Number(payslip.total_deductions || 0).toLocaleString("en-IN")}</td>
                          <td><strong>₹{Number(payslip.net_pay || 0).toLocaleString("en-IN")}</strong></td>
                          <td><Badge status={payslip.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {!isAdmin && <div className="card">
            <div className="card-title-row"><h3>{user.role === ROLES.EMPLOYEE ? "My Payslips" : "Published Payslips"}</h3><ExportButton filename={user.role === ROLES.EMPLOYEE ? "My_Payslips" : "Published_Payslips"} /></div>
            <p className="muted" style={{ fontSize: 11.5, marginTop: -8, marginBottom: 12 }}>Click a row to view, print, or download a full payslip.</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
              <select value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)} style={inputStyle}>
                <option value="">All companies</option>
                {PAYROLL_COMPANIES.map((name) => <option key={name}>{name}</option>)}
              </select>
              <select value={month} onChange={(e) => setMonth(e.target.value ? Number(e.target.value) : "")} style={inputStyle}>
                <option value="">All months</option>
                {MONTH_NAMES.map((name, i) => <option key={name} value={i + 1}>{name}</option>)}
              </select>
              <input type="number" value={year} onChange={(e) => setYear(e.target.value ? Number(e.target.value) : "")} placeholder="All years" style={{ ...inputStyle, width: 120 }} />
            </div>
            {loading ? (
              <Loader />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      {user.role !== ROLES.EMPLOYEE && <th>Employee</th>}
                      <th>Month</th><th>Present</th><th>LOP Days</th><th>Gross</th><th>Deductions</th><th>Net Pay</th><th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(user.role === ROLES.EMPLOYEE ? myPayslips : allPayslips).length === 0 && (
                      <tr className="empty-row"><td colSpan={user.role === ROLES.EMPLOYEE ? 7 : 8}>No published payslips found.</td></tr>
                    )}
                    {(user.role === ROLES.EMPLOYEE ? myPayslips : allPayslips).map((p) => (
                      <tr key={p.id} onClick={() => setSelectedPayslip(p)} style={{ cursor: "pointer" }}>
                        {user.role !== ROLES.EMPLOYEE && <td>{p.employee_name}</td>}
                        <td>{MONTH_NAMES[p.month - 1]} {p.year}</td>
                        <td>{p.days_present}</td>
                        <td>{p.lop_days}</td>
                        <td>₹{Number(p.gross_earnings || 0).toLocaleString("en-IN")}</td>
                        <td>₹{Number(p.total_deductions || 0).toLocaleString("en-IN")}</td>
                        <td><strong>₹{Number(p.net_pay || 0).toLocaleString("en-IN")}</strong></td>
                        <td><Badge status={p.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>}
        </>
      )}

      {isAdmin && tab === "templates" && <TemplatesTab />}
      {isAdmin && tab === "people" && (
        <PayrollPeopleTab
          month={month} year={year} version={coverageVersion}
          onSetStructure={(p) => { setStructureModal(true); pickEmployeeForStructure(p); }}
          onOpenPayslips={() => setTab("payslips")}
        />
      )}

      {structureModal && (
        <div className="modal-overlay" onClick={() => setStructureModal(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>Set Salary Structure</h3>
            {structError && <div className="login-error">{structError}</div>}
            <form onSubmit={saveStructure}>
              <div className="form-field">
                <label>Employee</label>
                <input
                  value={selectedEmp ? selectedEmp.full_name : empQuery}
                  onChange={(e) => searchEmployees(e.target.value)}
                  placeholder="Search by name — internal employees and contract logins both appear"
                />
                {empResults.length > 0 && !selectedEmp && (
                  <div style={{ border: "1px solid var(--color-border)", borderRadius: 6, marginTop: 4, maxHeight: 160, overflowY: "auto" }}>
                    {empResults.map((emp) => (
                      <div key={emp.id} onClick={() => pickEmployeeForStructure(emp)}
                        style={{ padding: "6px 10px", cursor: "pointer", fontSize: 12.5, display: "flex", justifyContent: "space-between" }}>
                        <span>{emp.full_name} — {emp.employee_code}</span>
                        <span className="muted">{ROLE_LABELS[emp.role] || emp.role}</span>
                      </div>
                    ))}
                  </div>
                )}
                {selectedEmp && (
                  <p className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>
                    {ROLE_LABELS[selectedEmp.role] || selectedEmp.role}
                    {selectedEmp.role === ROLES.CONTRACT_EMPLOYEE && " — placed with a vendor, tracked here for payroll only"}
                  </p>
                )}
              </div>
              <div className="form-grid">
                {Object.keys(structure).map((field) => (
                  <div className="form-field" key={field}>
                    <label>{field.replace(/_/g, " ")}</label>
                    <input
                      type="number"
                      value={structure[field]}
                      onChange={(e) => setStructure({ ...structure, [field]: Number(e.target.value) })}
                    />
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" onClick={() => { setStructureModal(false); setSelectedEmp(null); setEmpQuery(""); setEmpResults([]); }}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={!selectedEmp}>Save Structure</button>
              </div>
            </form>
          </div>
        </div>
      )}
      {selectedPayslip && (
        <PayslipDetailModal payslip={selectedPayslip} onClose={() => setSelectedPayslip(null)} />
      )}
    </AppLayout>
  );
}

// ============================================================================
// Salary Templates
// ============================================================================

function TemplatesTab() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_TEMPLATE);
  const [error, setError] = useState("");
  const [applyModal, setApplyModal] = useState(null);

  const load = async () => {
    setLoading(true);
    const { data } = await client.get("/payroll/templates");
    setTemplates(data);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const createTemplate = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await client.post("/payroll/templates", form);
      setShowForm(false);
      setForm(EMPTY_TEMPLATE);
      load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not create template.");
    }
  };

  const deleteTemplate = async (id) => {
    if (!window.confirm("Remove this template?")) return;
    await client.delete(`/payroll/templates/${id}`);
    load();
  };

  const earningsTotal = Number(form.basic_pct) + Number(form.hra_pct) + Number(form.special_allowance_pct) + Number(form.other_allowance_pct);

  return (
    <div className="card">
      <div className="card-title-row">
        <h3>Salary Templates</h3>
        <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>+ New Template</button>
      </div>
      <p className="muted" style={{ fontSize: 12, marginTop: -8, marginBottom: 14 }}>
        Define a reusable earnings/deductions split once, then apply it to any employee's CTC — no need to type flat numbers every time.
      </p>
      {loading ? <Loader /> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {templates.length === 0 && <div className="muted" style={{ fontSize: 13 }}>No templates yet.</div>}
          {templates.map((t) => (
            <div key={t.id} style={{ border: "1px solid var(--color-border)", borderRadius: 10, padding: 14 }}>
              <div className="flex-between">
                <div>
                  <strong>{t.name}</strong>
                  {t.description && <div className="muted" style={{ fontSize: 11.5 }}>{t.description}</div>}
                </div>
                {t.earnings_total_pct !== 100 && <span className="chip orange">Earnings total {t.earnings_total_pct}% (not 100)</span>}
              </div>
              <div className="chip-row" style={{ marginTop: 8 }}>
                <span className="chip blue">Basic {t.basic_pct}%</span>
                <span className="chip blue">HRA {t.hra_pct}%</span>
                <span className="chip blue">Special {t.special_allowance_pct}%</span>
                <span className="chip blue">Other {t.other_allowance_pct}%</span>
                <span className="chip">PF {t.pf_employee_pct}%</span>
                <span className="chip">ESI {t.esi_employee_pct}%</span>
                {t.insurance_pct > 0 && <span className="chip">Insurance {t.insurance_pct}%</span>}
                <span className="chip">PT ₹{t.professional_tax_flat}</span>
                {t.tds_pct > 0 && <span className="chip">TDS {t.tds_pct}%</span>}
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                <button className="btn btn-sm btn-primary" onClick={() => setApplyModal(t)}>Apply to Employee</button>
                <button className="btn btn-sm btn-outline" onClick={() => deleteTemplate(t.id)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>New Salary Template</h3>
            {error && <div className="login-error">{error}</div>}
            <form onSubmit={createTemplate}>
              <div className="form-field">
                <label>Template Name</label>
                <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Standard Employee" />
              </div>
              <div className="form-field">
                <label>Description</label>
                <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>

              <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--color-text-muted)" }}>
                Earnings (% of CTC) — currently totals {earningsTotal}%
              </label>
              <div className="form-grid">
                <div className="form-field">
                  <label>Basic %</label>
                  <input type="number" value={form.basic_pct} onChange={(e) => setForm({ ...form, basic_pct: Number(e.target.value) })} />
                </div>
                <div className="form-field">
                  <label>HRA %</label>
                  <input type="number" value={form.hra_pct} onChange={(e) => setForm({ ...form, hra_pct: Number(e.target.value) })} />
                </div>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Special Allowance %</label>
                  <input type="number" value={form.special_allowance_pct} onChange={(e) => setForm({ ...form, special_allowance_pct: Number(e.target.value) })} />
                </div>
                <div className="form-field">
                  <label>Other Allowance %</label>
                  <input type="number" value={form.other_allowance_pct} onChange={(e) => setForm({ ...form, other_allowance_pct: Number(e.target.value) })} />
                </div>
              </div>

              <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--color-text-muted)" }}>Deductions</label>
              <div className="form-grid">
                <div className="form-field">
                  <label>PF (% of CTC)</label>
                  <input type="number" value={form.pf_employee_pct} onChange={(e) => setForm({ ...form, pf_employee_pct: Number(e.target.value) })} />
                </div>
                <div className="form-field">
                  <label>ESI (% of CTC)</label>
                  <input type="number" value={form.esi_employee_pct} onChange={(e) => setForm({ ...form, esi_employee_pct: Number(e.target.value) })} />
                </div>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Insurance (% of CTC)</label>
                  <input type="number" value={form.insurance_pct} onChange={(e) => setForm({ ...form, insurance_pct: Number(e.target.value) })} />
                </div>
                <div className="form-field">
                  <label>Professional Tax (flat, monthly)</label>
                  <input type="number" value={form.professional_tax_flat} onChange={(e) => setForm({ ...form, professional_tax_flat: Number(e.target.value) })} />
                </div>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>TDS (% of CTC)</label>
                  <input type="number" value={form.tds_pct} onChange={(e) => setForm({ ...form, tds_pct: Number(e.target.value) })} />
                </div>
              </div>

              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Create Template</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {applyModal && (
        <ApplyTemplateModal template={applyModal} onClose={() => setApplyModal(null)} />
      )}
    </div>
  );
}

function ApplyTemplateModal({ template, onClose }) {
  const [query, setQuery] = useState("");
  const [employees, setEmployees] = useState([]);
  const [selected, setSelected] = useState(null);
  const [ctc, setCtc] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [saving, setSaving] = useState(false);

  const search = async (q) => {
    setQuery(q);
    setSelected(null);
    if (q.length < 2) { setEmployees([]); return; }
    const { data } = await client.get("/employees", { params: { q } });
    setEmployees(data);
  };

  const apply = async () => {
    setError("");
    if (!selected) {
      setError("Select an employee.");
      return;
    }
    if (!ctc || Number(ctc) <= 0) {
      setError("A valid annual CTC is required.");
      return;
    }
    setSaving(true);
    try {
      const { data } = await client.post(`/payroll/templates/${template.id}/apply/${selected.id}`, { ctc: Number(ctc) });
      setResult(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not apply this template.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 6 }}>Apply "{template.name}"</h3>
        {error && <div className="login-error">{error}</div>}

        {!result ? (
          <>
            <div className="form-field">
              <label>Employee</label>
              <input value={selected ? selected.full_name : query} onChange={(e) => search(e.target.value)} placeholder="Search by name — internal employees and contract logins both appear" />
              {employees.length > 0 && !selected && (
                <div style={{ border: "1px solid var(--color-border)", borderRadius: 6, marginTop: 4, maxHeight: 140, overflowY: "auto" }}>
                  {employees.map((emp) => (
                    <div key={emp.id} onClick={() => { setSelected(emp); setEmployees([]); }}
                      style={{ padding: "6px 10px", cursor: "pointer", fontSize: 12.5, display: "flex", justifyContent: "space-between" }}>
                      <span>{emp.full_name} — {emp.employee_code}</span>
                      <span className="muted">{ROLE_LABELS[emp.role] || emp.role}</span>
                    </div>
                  ))}
                </div>
              )}
              {selected && selected.role === ROLES.CONTRACT_EMPLOYEE && (
                <p className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>
                  Placed with a vendor — tracked here for payroll only.
                </p>
              )}
            </div>
            <div className="form-field">
              <label>Annual CTC</label>
              <input type="number" value={ctc} onChange={(e) => setCtc(e.target.value)} />
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
              <button className="btn btn-outline" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" disabled={saving} onClick={apply}>{saving ? "Applying..." : "Apply"}</button>
            </div>
          </>
        ) : (
          <>
            <div className="callout note">
              Salary structure set for <strong>{selected.full_name}</strong> — monthly Basic ₹{result.basic.toLocaleString("en-IN")},
              HRA ₹{result.hra.toLocaleString("en-IN")}, Net ₹{result.net.toLocaleString("en-IN")}.
              Adjust further anytime via "Set Salary Structure Manually" on the Payslips tab.
            </div>
            <div style={{ textAlign: "right", marginTop: 16 }}>
              <button className="btn btn-primary" onClick={onClose}>Done</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
