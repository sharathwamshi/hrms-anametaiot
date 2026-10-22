import { useEffect, useState, useCallback } from "react";
import client from "../api/client";
import Badge from "./Badge";
import RemoveEmployeeModal from "./RemoveEmployeeModal";
import LeaveBalanceSummary from "./LeaveBalanceSummary";
import { useAuth } from "../context/AuthContext";
import { ROLES, ROLE_LABELS } from "../config/roles";

export default function EmployeeDetailModal({ employeeId, onClose, onChanged }) {
  const { user } = useAuth();
  const isSuperAdmin = user.role === ROLES.SUPER_ADMIN;
  const isAdmin = user.role === ROLES.HR_OPERATIONS || isSuperAdmin;

  const [snapshot, setSnapshot] = useState(null);
  const [recruiterPerf, setRecruiterPerf] = useState(null);
  const [permissions, setPermissions] = useState([]);
  const [catalogue, setCatalogue] = useState([]);
  const [leaveBalances, setLeaveBalances] = useState([]);
  const [leaveBalanceLoading, setLeaveBalanceLoading] = useState(true);
  const [leaveBalanceError, setLeaveBalanceError] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const [removing, setRemoving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [snapRes, catRes, permRes] = await Promise.all([
      client.get(`/employees/${employeeId}/performance-snapshot`),
      client.get("/employees/permissions/catalogue"),
      client.get(`/employees/${employeeId}/permissions`).catch(() => ({ data: [] })),
    ]);
    setSnapshot(snapRes.data);
    setCatalogue(catRes.data);
    setPermissions(permRes.data);
    setForm({
      full_name: snapRes.data.employee.full_name,
      phone: snapRes.data.employee.phone || "",
      designation: snapRes.data.employee.designation || "",
      role: snapRes.data.employee.role,
    });

    const targetEmployee = snapRes.data.employee;
    const canViewLeaveBalance = isAdmin || targetEmployee.id === user.id || targetEmployee.manager_id === user.id;
    setLeaveBalances([]);
    setLeaveBalanceError("");
    setLeaveBalanceLoading(canViewLeaveBalance);
    if (canViewLeaveBalance) {
      client.get(`/leave/balances/${employeeId}`)
        .then(({ data }) => setLeaveBalances(data))
        .catch((err) => {
          setLeaveBalanceError(err?.response?.data?.message || "Could not load this employee's leave balance.");
        })
        .finally(() => setLeaveBalanceLoading(false));
    }

    if (snapRes.data.is_recruiter) {
      try {
        const { data } = await client.get(`/dashboard/recruiter-performance/${employeeId}`);
        setRecruiterPerf(data);
      } catch {
        setRecruiterPerf(null);
      }
    }
    setLoading(false);
  }, [employeeId, isAdmin, user.id]);

  useEffect(() => { load(); }, [load]);

  // A Manager can manage permissions/edit only for their own direct report;
  // the backend enforces this too — this just avoids showing controls that
  // would 403 anyway.
  const isOwnReport = snapshot?.employee.manager_id === user.id;
  const targetIsSuper = snapshot?.employee.role === ROLES.SUPER_ADMIN;
  const canManage = (isAdmin || isOwnReport) && (!targetIsSuper || isSuperAdmin); // only a Super Admin may touch a Super Admin

  const saveInfo = async () => {
    setError("");
    try {
      await client.put(`/employees/${employeeId}`, form);
      setEditing(false);
      load();
      onChanged && onChanged();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save changes.");
    }
  };

  const togglePermission = async (key, currentlyGranted) => {
    setError("");
    try {
      if (currentlyGranted) {
        await client.delete(`/employees/${employeeId}/permissions/${key}`);
      } else {
        await client.post(`/employees/${employeeId}/permissions`, { permission_key: key });
      }
      load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update permission.");
    }
  };

  if (loading || !snapshot) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-box" onClick={(e) => e.stopPropagation()}>Loading…</div>
      </div>
    );
  }

  const emp = snapshot.employee;
  // Admin can remove anyone; a Manager only their own direct reports; nobody removes themselves.
  const canRemove = (isAdmin || isOwnReport) && emp.id !== user.id && emp.is_active && (emp.role !== ROLES.SUPER_ADMIN || isSuperAdmin);
  // A Manager can only undo a removal they made themselves.
  const canRestore = !emp.is_active && (isAdmin || (isOwnReport && emp.removed_by === user.id));

  const restore = async () => {
    setError("");
    try {
      await client.post(`/employees/${emp.id}/restore`);
      await load();
      onChanged?.();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not restore this person.");
    }
  };
  const grantedKeys = permissions.map((p) => p.permission_key);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ width: 600 }} onClick={(e) => e.stopPropagation()}>
        <div className="flex-between" style={{ marginBottom: 4 }}>
          <h3>{emp.full_name}</h3>
          <Badge status={emp.is_active ? "present" : "absent"} />
        </div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 14 }}>
          {emp.employee_code} · {ROLE_LABELS[emp.role] || emp.role} · {emp.department || "—"}
        </div>
        {error && <div className="login-error">{error}</div>}

        {!emp.is_active && (
          <div className="callout warn" style={{ marginBottom: 14, fontSize: 12.5 }}>
            <div className="flex-between">
              <div>
                <strong>Removed</strong>
                {emp.removed_at ? ` on ${new Date(emp.removed_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}` : ""}
                {emp.removed_by_name ? ` by ${emp.removed_by_name}` : ""}
                {emp.removal_reason ? <div style={{ marginTop: 4 }}>Reason: “{emp.removal_reason}”</div> : null}
              </div>
              {canRestore && <button className="btn btn-sm btn-outline" onClick={restore}>Restore</button>}
            </div>
          </div>
        )}

        {/* Info */}
        <div className="card" style={{ marginBottom: 14, padding: 14 }}>
          <div className="card-title-row">
            <h3 style={{ fontSize: 13 }}>Details</h3>
            {canManage && !editing && <button className="btn btn-sm btn-outline" onClick={() => setEditing(true)}>Edit</button>}
          </div>
          {!editing ? (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 16px", fontSize: 12.5 }}>
              <div><span className="muted">Email</span><div>{emp.email}</div></div>
              <div><span className="muted">Phone</span><div>{emp.phone || "—"}</div></div>
              <div><span className="muted">Designation</span><div>{emp.designation || "—"}</div></div>
              <div><span className="muted">Manager</span><div>{emp.manager_name || "—"}</div></div>
            </div>
          ) : (
            <>
              <div className="form-grid">
                <div className="form-field">
                  <label>Full Name</label>
                  <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
                </div>
                <div className="form-field">
                  <label>Phone</label>
                  <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
                </div>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Designation</label>
                  <input value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })} />
                </div>
                <div className="form-field">
                  <label>Role</label>
                  <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                    {Object.entries(ROLE_LABELS).filter(([val]) => val !== ROLES.SUPER_ADMIN || isSuperAdmin).map(([val, label]) => <option key={val} value={val}>{label}</option>)}
                  </select>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button className="btn btn-sm btn-outline" onClick={() => setEditing(false)}>Cancel</button>
                <button className="btn btn-sm btn-primary" onClick={saveInfo}>Save</button>
              </div>
            </>
          )}
        </div>

        {/* Performance */}
        <div className="card" style={{ marginBottom: 14, padding: 14 }}>
          <div className="card-title-row"><h3 style={{ fontSize: 13 }}>Performance</h3></div>
          <div className="stat-grid" style={{ marginBottom: 0 }}>
            <div className="stat-card" style={{ padding: 12 }}>
              <div><div className="label">Present Days (month)</div><div className="value" style={{ fontSize: 20 }}>{snapshot.present_days_this_month}</div></div>
            </div>
            <div className="stat-card" style={{ padding: 12 }}>
              <div><div className="label">Leave Taken (year)</div><div className="value" style={{ fontSize: 20 }}>{snapshot.leave_days_taken_this_year}</div></div>
            </div>
            <div className="stat-card" style={{ padding: 12 }}>
              <div><div className="label">Pending Leave Requests</div><div className="value" style={{ fontSize: 20 }}>{snapshot.pending_leave_requests}</div></div>
            </div>
            {recruiterPerf && (
              <div className="stat-card" style={{ padding: 12 }}>
                <div><div className="label">Candidates Added</div><div className="value" style={{ fontSize: 20 }}>{recruiterPerf.candidates_added}</div></div>
              </div>
            )}
          </div>
          {recruiterPerf && (
            <div className="chip-row" style={{ marginTop: 10 }}>
              <span className="chip blue">Interviews scheduled: {recruiterPerf.interviews_scheduled}</span>
              <span className="chip green">Hired: {recruiterPerf.hired_count}</span>
              <span className="chip orange">Conversion: {recruiterPerf.conversion_rate_pct}%</span>
            </div>
          )}
        </div>

        {(isAdmin || isOwnReport || emp.id === user.id) && (
          <LeaveBalanceSummary
            balances={leaveBalances}
            loading={leaveBalanceLoading}
            error={leaveBalanceError}
            showLink={false}
          />
        )}

        {/* Roles & Permissions */}
        {canManage && (
          <div className="card" style={{ padding: 14 }}>
            <div className="card-title-row"><h3 style={{ fontSize: 13 }}>Roles &amp; Permissions</h3></div>
            <p className="muted" style={{ fontSize: 11.5, marginBottom: 10 }}>
              Extend specific approval capabilities to this employee without changing their base role.
            </p>
            {catalogue.map((perm) => {
              const granted = grantedKeys.includes(perm.key);
              return (
                <div key={perm.key} className="flex-between" style={{ padding: "7px 0", borderBottom: "1px solid var(--color-border)" }}>
                  <span style={{ fontSize: 12.5 }}>{perm.label}</span>
                  <button
                    className={`btn btn-sm ${granted ? "btn-danger" : "btn-outline"}`}
                    onClick={() => togglePermission(perm.key, granted)}
                  >
                    {granted ? "Revoke" : "Grant"}
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <div className="flex-between" style={{ marginTop: 16 }}>
          <div>
            {canRemove && (
              <button className="btn btn-danger btn-sm" onClick={() => setRemoving(true)}>Remove from system</button>
            )}
          </div>
          <button className="btn btn-outline" onClick={onClose}>Close</button>
        </div>
      </div>

      {removing && (
        <RemoveEmployeeModal
          employee={emp}
          onClose={() => setRemoving(false)}
          onRemoved={() => { setRemoving(false); onChanged?.(); onClose(); }}
        />
      )}
    </div>
  );
}
