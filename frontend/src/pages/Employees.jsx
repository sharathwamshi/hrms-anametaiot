import { useEffect, useState } from "react";
import ExportButton from "../components/ExportButton";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import { useAuth } from "../context/AuthContext";
import { ROLES, ROLE_LABELS } from "../config/roles";
import EmployeeDetailModal from "../components/EmployeeDetailModal";

const emptyForm = {
  employee_code: "", full_name: "", email: "", password: "", role: ROLES.EMPLOYEE,
  designation: "", department_id: "", date_of_joining: "",
};

export default function Employees() {
  const { user } = useAuth();
  const isHrOps = user.role === ROLES.HR_OPERATIONS;
  const isManager = user.role === ROLES.MANAGER;
  const canOnboard = isHrOps || isManager;
  const [employees, setEmployees] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
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
    const [empRes, deptRes] = await Promise.all([
      client.get("/employees", { params }),
      client.get("/employees/departments"),
    ]);
    setEmployees(empRes.data);
    setDepartments(deptRes.data);
    setLoading(false);
  };

  useEffect(() => {
    load();
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

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await client.post("/employees", form);
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
          <div style={{ display: "flex", gap: 8 }}>
            <ExportButton filename={showRemoved ? "Removed_Employees" : "Employees"} title="Employees" />
            {canOnboard && (
              <button className={`btn btn-sm ${showRemoved ? "btn-primary" : "btn-outline"}`} onClick={toggleRemoved}>
                {showRemoved ? "← Back to active" : isManager ? "Removed from my team" : "Removed employees"}
              </button>
            )}
            {canOnboard && !showRemoved && (
              <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>
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
                  <tr><th>Code</th><th>Name</th><th>Role</th><th>Department</th><th>Designation</th><th>Manager</th><th>Status</th></tr>
                )}
              </thead>
              <tbody>
                {employees.length === 0 && (
                  <tr className="empty-row"><td colSpan={7}>{showRemoved ? "No removed employees." : "No employees found."}</td></tr>
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
                        <td>{canRestoreRow(emp) && <button className="btn btn-sm btn-outline" onClick={(e) => restoreRow(e, emp)}>Restore</button>}</td>
                      </>
                    ) : (
                      <>
                        <td>{emp.department || "—"}</td>
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
                  <label>Role</label>
                  <select required value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                    {Object.entries(ROLE_LABELS).map(([val, label]) => <option key={val} value={val}>{label}</option>)}
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
              <div className="form-grid">
                <div className="form-field">
                  <label>Designation</label>
                  <input value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })} />
                </div>
                <div className="form-field">
                  <label>Date of Joining</label>
                  <input type="date" value={form.date_of_joining} onChange={(e) => setForm({ ...form, date_of_joining: e.target.value })} />
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Create Employee</button>
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
