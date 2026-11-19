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
  const [directoryFilters, setDirectoryFilters] = useState({
    role: "",
    department_id: "",
    company_name: "",
    designation: "",
    employment_status: "",
  });
  const [resignationFilters, setResignationFilters] = useState({
    q: "",
    department_id: "",
    designation: "",
  });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [selectedEmployeeId, setSelectedEmployeeId] = useState(null);
  const [showRemoved, setShowRemoved] = useState(false);
  const [employeeSort, setEmployeeSort] = useState({ key: "full_name", direction: "asc" });
  const [employeePage, setEmployeePage] = useState(1);
  const [employeePageSize, setEmployeePageSize] = useState(10);

  const load = async (query = q, removed = showRemoved, requestFilters = resignationFilters, filters = directoryFilters) => {
    setLoading(true);
    setEmployeePage(1);
    const params = {};
    if (query) params.q = query;
    if (removed) params.status = "removed";
    if (!removed) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params[key] = value;
      });
    }
    const resignationParams = {
      status: "resignation_pending",
      ...(requestFilters.q ? { q: requestFilters.q } : {}),
      ...(requestFilters.department_id ? { department_id: requestFilters.department_id } : {}),
      ...(requestFilters.designation ? { designation: requestFilters.designation } : {}),
    };
    const requestsPromise = !removed && (isHrOps || isManager)
      ? client.get("/employees", { params: resignationParams })
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

  const updateResignationFilter = (name, value) => {
    const nextFilters = { ...resignationFilters, [name]: value };
    setResignationFilters(nextFilters);
    load(q, showRemoved, nextFilters);
  };
  const updateDirectoryFilter = (name, value) => {
    const nextFilters = { ...directoryFilters, [name]: value };
    setDirectoryFilters(nextFilters);
    setEmployeePage(1);
    load(q, showRemoved, resignationFilters, nextFilters);
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
  const sortedEmployees = [...employees].sort((a, b) => {
    const left = a[employeeSort.key] ?? "";
    const right = b[employeeSort.key] ?? "";
    const comparison = String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
    return comparison * (employeeSort.direction === "asc" ? 1 : -1);
  });
  const employeePageCount = employeePageSize === 0
    ? 1
    : Math.max(1, Math.ceil(sortedEmployees.length / employeePageSize));
  const pageEmployees = employeePageSize === 0
    ? sortedEmployees
    : sortedEmployees.slice((employeePage - 1) * employeePageSize, employeePage * employeePageSize);
  const sortEmployeeBy = (key) => {
    setEmployeeSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
    setEmployeePage(1);
  };
  const employeeSortLabel = (key, label) => (
    <button type="button" className="table-sort-button" onClick={() => sortEmployeeBy(key)}>
      {label}{employeeSort.key === key ? (employeeSort.direction === "asc" ? " ▲" : " ▼") : ""}
    </button>
  );

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
        <div className="employees-directory-toolbar">
          <form onSubmit={handleSearch} className="employees-directory-search">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name or employee code..."
              aria-label="Search by name or employee code"
              style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 12px", width: "100%" }}
            />
          </form>
          {!showRemoved && (
            <div className="employees-directory-filters">
              <select aria-label="Filter employees by role" value={directoryFilters.role} onChange={(event) => updateDirectoryFilter("role", event.target.value)}>
                <option value="">All roles</option>
                {Object.entries(ROLE_LABELS).map(([role, label]) => <option key={role} value={role}>{label}</option>)}
              </select>
              <select aria-label="Filter employees by department" value={directoryFilters.department_id} onChange={(event) => updateDirectoryFilter("department_id", event.target.value)}>
                <option value="">All departments</option>
                {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
              </select>
              <select aria-label="Filter employees by company" value={directoryFilters.company_name} onChange={(event) => updateDirectoryFilter("company_name", event.target.value)}>
                <option value="">All companies</option>
                {PAYROLL_COMPANIES.map((company) => <option key={company}>{company}</option>)}
              </select>
              <select aria-label="Filter employees by designation" value={directoryFilters.designation} onChange={(event) => updateDirectoryFilter("designation", event.target.value)}>
                <option value="">All designations</option>
                {[...new Set([...DESIGNATION_OPTIONS, ...employees.map((employee) => employee.designation).filter(Boolean), directoryFilters.designation])]
                  .filter(Boolean)
                  .sort((a, b) => a.localeCompare(b))
                  .map((designation) => <option key={designation} value={designation}>{designation}</option>)}
              </select>
              <select aria-label="Filter employees by employment status" value={directoryFilters.employment_status} onChange={(event) => updateDirectoryFilter("employment_status", event.target.value)}>
                <option value="">All employment statuses</option>
                <option value="active">Active</option>
                <option value="resignation_pending">Resignation pending</option>
                <option value="notice_period">Notice period</option>
                <option value="left">Left</option>
              </select>
            </div>
          )}
          <div className="employees-directory-actions">
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
          <div className={`table-wrap${showRemoved ? "" : " employees-directory-table-wrap"}`}>
            <table className={`data-table${showRemoved ? "" : " employees-directory-table"}`}>
              {!showRemoved && (
                <colgroup>
                  <col className="employees-col-code" />
                  <col className="employees-col-name" />
                  <col className="employees-col-role" />
                  <col className="employees-col-department" />
                  <col className="employees-col-company" />
                  <col className="employees-col-designation" />
                  <col className="employees-col-manager" />
                  <col className="employees-col-status" />
                </colgroup>
              )}
              <thead>
                {showRemoved ? (
                  <tr><th>Code</th><th>Name</th><th>Role</th><th>Removed on</th><th>Removed by</th><th>Reason</th><th></th></tr>
                ) : (
                  <tr><th>{employeeSortLabel("employee_code", "Code")}</th><th>{employeeSortLabel("full_name", "Name")}</th><th>{employeeSortLabel("role", "Role")}</th><th>{employeeSortLabel("department", "Department")}</th><th>{employeeSortLabel("company_name", "Company")}</th><th>{employeeSortLabel("designation", "Designation")}</th><th>Manager</th><th>{employeeSortLabel("employment_status", "Status")}</th></tr>
                )}
              </thead>
              <tbody>
                {employees.length === 0 && (
                  <tr className="empty-row"><td colSpan={showRemoved ? 7 : 8}>{showRemoved ? "No removed employees." : "No employees found."}</td></tr>
                )}
                {pageEmployees.map((emp) => (
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
                        <td><Badge status={emp.employment_status || (emp.is_active ? "active" : "inactive")} /></td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && (
          <div className="table-pagination">
            <span>{sortedEmployees.length ? `Showing ${employeePageSize === 0 ? 1 : (employeePage - 1) * employeePageSize + 1}–${employeePageSize === 0 ? sortedEmployees.length : Math.min(employeePage * employeePageSize, sortedEmployees.length)} of ${sortedEmployees.length}` : "0 employees"}</span>
            <label>Rows per page
              <select value={employeePageSize} onChange={(event) => { setEmployeePageSize(Number(event.target.value)); setEmployeePage(1); }}>
                {[10, 25, 50].map((size) => <option key={size} value={size}>{size}</option>)}
                <option value={0}>Show All</option>
              </select>
            </label>
            <button type="button" className="btn btn-sm btn-outline" disabled={employeePage <= 1 || employeePageSize === 0} onClick={() => setEmployeePage((page) => page - 1)}>Previous</button>
            <span>Page {employeePageSize === 0 ? 1 : Math.min(employeePage, employeePageCount)} of {employeePageCount}</span>
            <button type="button" className="btn btn-sm btn-outline" disabled={employeePage >= employeePageCount || employeePageSize === 0} onClick={() => setEmployeePage((page) => page + 1)}>Next</button>
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
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
            <input
              value={resignationFilters.q}
              onChange={(event) => updateResignationFilter("q", event.target.value)}
              placeholder="Search employee name or code..."
              aria-label="Search resignation requests by employee name or code"
              style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px", flex: "1 1 220px", minWidth: 180 }}
            />
            <select
              value={resignationFilters.department_id}
              onChange={(event) => updateResignationFilter("department_id", event.target.value)}
              aria-label="Filter resignation requests by department"
              style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px", flex: "1 1 150px", minWidth: 140 }}
            >
              <option value="">All departments</option>
              {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
            </select>
            <select
              value={resignationFilters.designation}
              onChange={(event) => updateResignationFilter("designation", event.target.value)}
              aria-label="Filter resignation requests by designation"
              style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px", flex: "1 1 170px", minWidth: 150 }}
            >
              <option value="">All designations</option>
              {[...new Set([...DESIGNATION_OPTIONS, ...resignationRequests.map((employee) => employee.designation).filter(Boolean)])]
                .sort((a, b) => a.localeCompare(b))
                .map((designation) => <option key={designation} value={designation}>{designation}</option>)}
            </select>
          </div>
          {loading ? <Loader /> : resignationRequests.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>
              {Object.values(resignationFilters).some(Boolean)
                ? "No pending resignation requests match these filters."
                : "There are no pending resignation requests."}
            </p>
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
