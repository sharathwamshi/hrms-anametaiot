import { useEffect, useState } from "react";
import ExportButton from "../components/ExportButton";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import { useAuth } from "../context/AuthContext";
import { ROLES, ROLE_LABELS } from "../config/roles";
import { DESIGNATION_OPTIONS } from "../config/employeeOptions";
import EmployeeDetailModal from "../components/EmployeeDetailModal";
import ManagerSelector from "../components/ManagerSelector";
import { PAYROLL_COMPANIES } from "../config/companies";

const emptyForm = {
  employee_code: "", full_name: "", email: "", password: "", role: ROLES.EMPLOYEE,
  company_name: PAYROLL_COMPANIES[1], designation: "", department_id: "", date_of_joining: "", annual_ctc: "", manager_id: "",
};

export default function Employees() {
  const { user } = useAuth();
  const isSuperAdmin = user.role === ROLES.SUPER_ADMIN;
  const isHrOps = user.role === ROLES.HR_OPERATIONS || isSuperAdmin; // Super Admin has HR-Operations-level people admin
  const canManageCtc = isHrOps;
  const isManager = user.role === ROLES.MANAGER;
  const canOnboard = isHrOps || isManager;
  const [employees, setEmployees] = useState([]);
  const [resignationRequests, setResignationRequests] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [managers, setManagers] = useState([]);
  const [managerLoadError, setManagerLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [companyFilter, setCompanyFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [selectedEmployeeId, setSelectedEmployeeId] = useState(null);
  const [showRemoved, setShowRemoved] = useState(false);

  const load = async (query = "", removed = showRemoved) => {
    setLoading(true);
    const params = {};
    if (query) params.q = query;
    if (removed) params.status = "removed";
    if (!removed && companyFilter) params.company_name = companyFilter;
    const requestsPromise = !removed && (isHrOps || isManager)
      ? client.get("/employees", { params: { status: "resignation_pending", ...(query ? { q: query } : {}) } })
      : Promise.resolve({ data: [] });
    const [empRes, deptRes, requestsRes] = await Promise.all([
      client.get("/employees", { params }),
      client.get("/employees/departments"),
      requestsPromise,
    ]);
    setEmployees(empRes.data);
    setDepartments(deptRes.data);
    setResignationRequests(requestsRes.data);
    setLoading(false);
  };

  useEffect(() => {
    load();
    client.get("/employees/managers")
      .then(({ data }) => {
        setManagers(data);
        setManagerLoadError("");
      })
      .catch((err) => {
        setManagerLoadError(err?.response?.data?.message || "Could not load available managers.");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleRemoved = () => {
    const next = !showRemoved;
    setShowRemoved(next);
    load(q, next);
  };

  // HR Operations can restore anyone; a Manager only someone they removed themselves.
  const canRestoreRow = (emp) => isHrOps || (isManager && emp.manager_id === user.id && emp.removed_by === user.id);
  const restoreRow = async (e, emp) => {
    e.stopPropagation();
    try {
      await client.post(`/employees/${emp.id}/restore`);
      load(q, true);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not restore this person.");
    }
  };
  const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—");

  const handleSearch = (e) => {
    e.preventDefault();
    load(q);
  };

  const openCreateForm = () => {
    setForm({ ...emptyForm, manager_id: isManager ? String(user.id) : "" });
    setError("");
    setShowForm(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    const payload = { ...form };
    if (!canManageCtc || String(form.annual_ctc).trim() === "") {
      delete payload.annual_ctc;
    } else {
      const annualCtc = Number(form.annual_ctc);
      if (!Number.isFinite(annualCtc) || annualCtc < 0) {
        setError("Annual CTC must be a non-negative finite amount.");
        return;
      }
      payload.annual_ctc = annualCtc;
    }
    try {
      await client.post("/employees", payload);
      setShowForm(false);
      setForm(emptyForm);
      load(q);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not create employee.");
    }
  };

  return (
    <AppLayout title="Employees" subtitle="Organization directory.">
      <div className="card">
        <p className="muted" style={{ fontSize: 11.5, marginTop: -4, marginBottom: 6 }}>Click an employee to view their performance, edit details, or manage permissions.</p>
        <div className="card-title-row">
          <form onSubmit={handleSearch} style={{ display: "flex", gap: 8 }}>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name or employee code..."
              style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 12px", width: 260 }}
            />
            <button type="submit" className="btn btn-outline btn-sm">Search</button>
          </form>
          {!showRemoved && (
            <select
              aria-label="Filter employees by company"
              value={companyFilter}
              onChange={(event) => {
                setCompanyFilter(event.target.value);
                const params = event.target.value ? { company_name: event.target.value, ...(q ? { q } : {}) } : (q ? { q } : {});
                setLoading(true);
                client.get("/employees", { params })
                  .then(({ data }) => setEmployees(data))
                  .catch((err) => setError(err?.response?.data?.message || "Could not filter employees."))
                  .finally(() => setLoading(false));
              }}
              style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}
            >
              <option value="">All companies</option>
              {PAYROLL_COMPANIES.map((company) => <option key={company}>{company}</option>)}
            </select>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <ExportButton filename={showRemoved ? "Removed_Employees" : "Employees"} title="Employees" />
            {canOnboard && (
              <button className={`btn btn-sm ${showRemoved ? "btn-primary" : "btn-outline"}`} onClick={toggleRemoved}>
                {showRemoved ? "← Back to active" : isManager ? "Removed from my team" : "Removed employees"}
              </button>
            )}
            {canOnboard && !showRemoved && (
              <button className="btn btn-primary btn-sm" onClick={openCreateForm}>
                + {isManager ? "Add to My Team" : "Add Employee"}
              </button>
            )}
          </div>
        </div>

        {error && !showForm && <div className="login-error" style={{ marginTop: 10 }}>{error}</div>}

        {loading ? (
          <Loader />
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                {showRemoved ? (
                  <tr><th>Code</th><th>Name</th><th>Role</th><th>Removed on</th><th>Removed by</th><th>Reason</th><th></th></tr>
                ) : (
                  <tr><th>Code</th><th>Name</th><th>Role</th><th>Department</th><th>Company</th><th>Designation</th><th>Manager</th><th>Status</th></tr>
                )}
              </thead>
              <tbody>
                {employees.length === 0 && (
                  <tr className="empty-row"><td colSpan={showRemoved ? 7 : 8}>{showRemoved ? "No removed employees." : "No employees found."}</td></tr>
                )}
                {employees.map((emp) => (
                  <tr key={emp.id} onClick={() => setSelectedEmployeeId(emp.id)} style={{ cursor: "pointer" }}>
                    <td>{emp.employee_code}</td>
                    <td>{emp.full_name}</td>
                    <td>{ROLE_LABELS[emp.role] || emp.role}</td>
                    {showRemoved ? (
                      <>
                        <td>{fmtDate(emp.removed_at)}</td>
                        <td>{emp.removed_by_name || "—"}</td>
                        <td className="muted" style={{ maxWidth: 260 }}>{emp.removal_reason || "—"}</td>
                        <td>{canRestoreRow(emp) && <button className="btn btn-sm btn-success" onClick={(e) => restoreRow(e, emp)}>Restore</button>}</td>
                      </>
                    ) : (
                      <>
                        <td>{emp.department || "—"}</td>
                        <td><span className="company-badge">{emp.company_name || "Acknowledger First Pvt Ltd"}</span></td>
                        <td>{emp.designation || "—"}</td>
                        <td>{emp.manager_name || "—"}</td>
                        <td><Badge status={emp.is_active ? "present" : "absent"} /></td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {!showRemoved && (isHrOps || isManager) && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title-row">
            <h3>Resignation requests</h3>
            <span className="chip orange">{resignationRequests.length} pending</span>
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: -4 }}>
            Review requests from your direct reports{isHrOps ? " and employees across the organization" : ""}.
          </p>
          {loading ? <Loader /> : resignationRequests.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>There are no pending resignation requests.</p>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Employee</th><th>Code</th><th>Department</th><th>Request date</th><th>Manager</th><th></th></tr></thead>
                <tbody>
                  {resignationRequests.map((employee) => (
                    <tr key={employee.id} onClick={() => setSelectedEmployeeId(employee.id)} style={{ cursor: "pointer" }}>
                      <td>{employee.full_name}</td>
                      <td>{employee.employee_code}</td>
                      <td>{employee.department || "—"}</td>
                      <td>{fmtDate(employee.resignation_requested_at)}</td>
                      <td>{employee.manager_name || "—"}</td>
                      <td><button className="btn btn-sm btn-primary" onClick={(event) => { event.stopPropagation(); setSelectedEmployeeId(employee.id); }}>Review</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 6 }}>{isManager ? "Add to My Team" : "Add Employee"}</h3>
            {isManager && (
              <p className="muted" style={{ fontSize: 12, marginBottom: 14 }}>
                This person will report directly to you.
              </p>
            )}
            {error && <div className="login-error">{error}</div>}
            <form onSubmit={submit}>
              <div className="form-grid">
                <div className="form-field">
                  <label>Employee Code</label>
                  <input required value={form.employee_code} onChange={(e) => setForm({ ...form, employee_code: e.target.value })} />
                </div>
                <div className="form-field">
                  <label>Full Name</label>
                  <input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
                </div>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Email</label>
                  <input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                </div>
                <div className="form-field">
                  <label>Temporary Password</label>
                  <input type="password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
                </div>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Role (system access)</label>
                  <select required value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                    {Object.entries(ROLE_LABELS).filter(([val]) => val !== ROLES.SUPER_ADMIN || isSuperAdmin).map(([val, label]) => <option key={val} value={val}>{label}</option>)}
                  </select>
                </div>
                <div className="form-field">
                  <label>Department</label>
                  <select value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
                    <option value="">Unassigned</option>
                    {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                </div>
              </div>
              <div className="form-field">
                <label>Company</label>
                <select value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })}>
                  {PAYROLL_COMPANIES.map((company) => <option key={company}>{company}</option>)}
                </select>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Designation (job title)</label>
                  <input
                    list="new-employee-designation-options"
                    value={form.designation}
                    onChange={(e) => setForm({ ...form, designation: e.target.value })}
                  />
                  <datalist id="new-employee-designation-options">
                    {DESIGNATION_OPTIONS.map((designation) => (
                      <option key={designation} value={designation} />
                    ))}
                  </datalist>
                </div>
                <div className="form-field">
                  <label>Date of Joining</label>
                  <input type="date" value={form.date_of_joining} onChange={(e) => setForm({ ...form, date_of_joining: e.target.value })} />
                </div>
              </div>
              {canManageCtc && (
                <div className="form-field">
                  <label htmlFor="new-employee-annual-ctc">Annual CTC (₹)</label>
                  <input
                    id="new-employee-annual-ctc"
                    type="number"
                    min="0"
                    step="0.01"
                    value={form.annual_ctc}
                    onChange={(e) => setForm({ ...form, annual_ctc: e.target.value })}
                  />
                </div>
              )}
              <div className="form-field">
                <label>Manager</label>
                {managerLoadError ? (
                  <div className="login-error">{managerLoadError}</div>
                ) : (
                  <ManagerSelector
                    managers={managers}
                    value={form.manager_id}
                    onChange={(managerId) => setForm({ ...form, manager_id: managerId })}
                    disabled={isManager}
                  />
                )}
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-success">Create Employee</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {selectedEmployeeId && (
        <EmployeeDetailModal
          employeeId={selectedEmployeeId}
          onClose={() => setSelectedEmployeeId(null)}
          onChanged={() => load(q, showRemoved)}
        />
      )}
    </AppLayout>
  );
}
