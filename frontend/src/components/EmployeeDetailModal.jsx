import { useEffect, useState, useCallback } from "react";
import client from "../api/client";
import Badge from "./Badge";
import RemoveEmployeeModal from "./RemoveEmployeeModal";
import LeaveBalanceSummary from "./LeaveBalanceSummary";
import EmployeeAttendanceSection from "./EmployeeAttendanceSection";
import EmployeeFamilyPanel from "./EmployeeFamilyPanel";
import EmployeeDocumentsPanel from "./EmployeeDocumentsPanel";
import EmployeeManagementPanel from "./EmployeeManagementPanel";
import EmployeePersonalDetailsPanel from "./EmployeePersonalDetailsPanel";
import { useAuth } from "../context/AuthContext";
import { ROLES, ROLE_LABELS } from "../config/roles";
import ManagerSelector from "./ManagerSelector";

export default function EmployeeDetailModal({ employeeId, onClose, onChanged }) {
  const { user } = useAuth();
  const isSuperAdmin = user.role === ROLES.SUPER_ADMIN;
  const isAdmin = user.role === ROLES.HR_OPERATIONS || isSuperAdmin;
  const canManageCtc = isAdmin;

  const [snapshot, setSnapshot] = useState(null);
  const [managers, setManagers] = useState([]);
  const [managerLoadError, setManagerLoadError] = useState("");
  const [recruiterPerf, setRecruiterPerf] = useState(null);
  const [leaveBalances, setLeaveBalances] = useState([]);
  const [leaveBalanceLoading, setLeaveBalanceLoading] = useState(true);
  const [leaveBalanceError, setLeaveBalanceError] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const [ctcError, setCtcError] = useState("");
  const [ctcLoaded, setCtcLoaded] = useState(!canManageCtc);
  const [saveSuccess, setSaveSuccess] = useState("");
  const [removing, setRemoving] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewLastWorkingDay, setReviewLastWorkingDay] = useState("");
  const [activeTab, setActiveTab] = useState("overview");

  const load = useCallback(async () => {
    setLoading(true);
    setReviewLastWorkingDay("");
    const snapRes = await client.get(`/employees/${employeeId}/performance-snapshot`);
    setSnapshot(snapRes.data);
    if (canManageCtc) {
      try {
        const managersRes = await client.get("/employees/managers");
        setManagers(managersRes.data);
        setManagerLoadError("");
      } catch (err) {
        setManagers([]);
        setManagerLoadError(err?.response?.data?.message || "Could not load available managers.");
      }
    } else {
      setManagers([]);
      setManagerLoadError("");
    }
    let ctcFormValue = {};
    if (canManageCtc) {
      setCtcLoaded(false);
      setCtcError("");
      try {
        const { data } = await client.get(`/employees/${employeeId}/compensation`);
        ctcFormValue.annual_ctc = data.annual_ctc ?? "";
        setCtcLoaded(true);
      } catch (err) {
        setCtcError(err?.response?.data?.message || "Could not load Annual CTC.");
      }
    }
    setForm({
      full_name: snapRes.data.employee.full_name,
      phone: snapRes.data.employee.phone || "",
      designation: snapRes.data.employee.designation || "",
      role: snapRes.data.employee.role,
      manager_id: snapRes.data.employee.manager_id ? String(snapRes.data.employee.manager_id) : "",
      ...ctcFormValue,
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
  }, [employeeId, isAdmin, canManageCtc, user.id]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setActiveTab("overview"); }, [employeeId]);

  // A Manager can manage permissions/edit only for their own direct report;
  // the backend enforces this too — this just avoids showing controls that
  // would 403 anyway.
  const isOwnReport = snapshot?.employee.manager_id === user.id;
  const targetIsSuper = snapshot?.employee.role === ROLES.SUPER_ADMIN;
  const canManage = (isAdmin || isOwnReport) && (!targetIsSuper || isSuperAdmin); // only a Super Admin may touch a Super Admin

  const saveInfo = async () => {
    setError("");
    setSaveSuccess("");
    const payload = { ...form };
    if (canManageCtc && ctcLoaded) {
      if (String(form.annual_ctc).trim() === "") {
        payload.annual_ctc = null;
      } else {
        const annualCtc = Number(form.annual_ctc);
        if (!Number.isFinite(annualCtc) || annualCtc < 0) {
          setError("Annual CTC must be a non-negative finite amount.");
          return;
        }
        payload.annual_ctc = annualCtc;
      }
    } else {
      delete payload.annual_ctc;
    }
    try {
      await client.put(`/employees/${employeeId}`, payload);
      setEditing(false);
      setSaveSuccess("Employee details updated successfully.");
      load().catch(() => {
        setLoading(false);
        setError("Employee details were saved, but refreshed details could not be loaded.");
      });
      onChanged && onChanged();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save changes.");
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
  const canViewEmployeeRecords = isAdmin || isOwnReport;
  const canManageHrRecords = isAdmin || (isOwnReport && (!targetIsSuper || isSuperAdmin));
  const tabs = [
    { id: "overview", label: "Overview" },
    ...(canViewEmployeeRecords ? [
      { id: "personal", label: "Personal & Family" },
      { id: "documents", label: "Documents & HR" },
    ] : []),
    ...(canViewEmployeeRecords || emp.id === user.id
      ? [{ id: "leave-attendance", label: "Leave & Attendance" }]
      : []),
  ];
  // Admin can remove anyone; a Manager only their own direct reports; nobody removes themselves.
  const canRemove = (isAdmin || isOwnReport) && emp.id !== user.id && emp.is_active && (emp.role !== ROLES.SUPER_ADMIN || isSuperAdmin);
  // A Manager can only undo a removal they made themselves.
  const canRestore = !emp.is_active && (isAdmin || (isOwnReport && emp.removed_by === user.id));
  const canReviewResignation = (
    user.role === ROLES.HR_OPERATIONS
    || user.role === ROLES.SUPER_ADMIN
    || (user.role === ROLES.MANAGER && isOwnReport)
  ) && emp.id !== user.id;
  const canManageEmploymentStatus = (
    user.role === ROLES.HR_OPERATIONS
    || user.role === ROLES.SUPER_ADMIN
    || (user.role === ROLES.MANAGER && isOwnReport)
  ) && emp.id !== user.id;
  const today = new Date();
  const todayDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const validNoticePeriod = /^\d{4}-\d{2}-\d{2}$/.test(reviewLastWorkingDay)
    && reviewLastWorkingDay >= todayDate;
  const employmentStatusLabels = {
    active: "Active",
    resignation_pending: "Resignation pending manager review",
    notice_period: "Serving notice period",
    left: "Left the company",
  };

  const reviewResignation = async (decision) => {
    if (decision === "rejected" && !window.confirm(`Reject ${emp.full_name}'s resignation request? Their employment status will remain Active.`)) return;
    setReviewBusy(true);
    setError("");
    try {
      await client.post(`/employees/${emp.id}/resignation/review`, {
        decision,
        ...(decision === "accepted" ? { last_working_day: reviewLastWorkingDay } : {}),
      });
      await load();
      onChanged?.();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not review this resignation request.");
    } finally {
      setReviewBusy(false);
    }
  };

  const markAsLeft = async () => {
    if (!window.confirm(`Mark ${emp.full_name} as having left the company?`)) return;
    setReviewBusy(true);
    setError("");
    try {
      await client.post(`/employees/${emp.id}/employment-status`, { employment_status: "left" });
      await load();
      onChanged?.();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update employment status.");
    } finally {
      setReviewBusy(false);
    }
  };

  const reactivateEmployment = async () => {
    if (!window.confirm(`Reactivate ${emp.full_name}'s employment and change their status to Active?`)) return;
    setReviewBusy(true);
    setError("");
    try {
      await client.post(`/employees/${emp.id}/employment-status`, { employment_status: "active" });
      await load();
      onChanged?.();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not reactivate this employee.");
    } finally {
      setReviewBusy(false);
    }
  };

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
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ width: 800, maxWidth: "95vw" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex-between" style={{ marginBottom: 4 }}>
          <h3>{emp.full_name}</h3>
          <Badge status={emp.is_active ? "present" : "absent"} />
        </div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 14 }}>
          {emp.employee_code} · {ROLE_LABELS[emp.role] || emp.role} · {emp.department || "—"}
        </div>
        {error && <div className="login-error">{error}</div>}
        {saveSuccess && <p role="status" className="muted">{saveSuccess}</p>}
        {ctcError && canManageCtc && <div className="login-error">{ctcError}</div>}

        {!emp.is_active && (
          <div className="callout warn" style={{ marginBottom: 14, fontSize: 12.5 }}>
            <div className="flex-between">
              <div>
                <strong>Removed</strong>
                {emp.removed_at ? ` on ${new Date(emp.removed_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}` : ""}
                {emp.removed_by_name ? ` by ${emp.removed_by_name}` : ""}
                {emp.removal_reason ? <div style={{ marginTop: 4 }}>Reason: “{emp.removal_reason}”</div> : null}
              </div>
              {canRestore && <button className="btn btn-sm btn-success" onClick={restore}>Restore</button>}
            </div>
          </div>
        )}

        <div className="employee-detail-tabs" role="tablist" aria-label="Employee details">
          {tabs.map((tab, index) => (
            <button
              key={tab.id}
              id={`employee-detail-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              aria-controls="employee-detail-tabpanel"
              tabIndex={activeTab === tab.id ? 0 : -1}
              className={`employee-detail-tab${activeTab === tab.id ? " active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(event) => {
                let nextIndex = index;
                if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
                else if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
                else if (event.key === "Home") nextIndex = 0;
                else if (event.key === "End") nextIndex = tabs.length - 1;
                else return;
                event.preventDefault();
                const nextTab = tabs[nextIndex];
                setActiveTab(nextTab.id);
                document.getElementById(`employee-detail-tab-${nextTab.id}`)?.focus();
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div
          id="employee-detail-tabpanel"
          className="employee-detail-tabpanel"
          role="tabpanel"
          aria-labelledby={`employee-detail-tab-${activeTab}`}
          tabIndex={0}
        >
        {activeTab === "overview" && <>
        <div className="callout" style={{ marginBottom: 14, fontSize: 12.5 }}>
          <div className="flex-between" style={{ gap: 12, alignItems: "flex-start" }}>
            <div>
              <strong>Employment status: {employmentStatusLabels[emp.employment_status || "active"] || "Active"}</strong>
              {emp.employment_status === "resignation_pending" && (
                <div className="muted" style={{ marginTop: 4 }}>
                  Requested {emp.resignation_requested_at ? new Date(emp.resignation_requested_at).toLocaleDateString("en-IN") : "date unavailable"}.
                </div>
              )}
              {emp.employment_status === "notice_period" && (
                <div className="muted" style={{ marginTop: 4 }}>
                  Last working day: {emp.last_working_day || "Not set"}
                </div>
              )}
              {emp.employment_status === "left" && emp.left_company_at && (
                <div className="muted" style={{ marginTop: 4 }}>
                  Left on {emp.left_company_at}.
                </div>
              )}
            </div>
            {canManageEmploymentStatus && (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {emp.employment_status === "notice_period" && (
                  <button className="btn btn-sm btn-danger" disabled={reviewBusy} onClick={markAsLeft}>Mark as left</button>
                )}
                {emp.employment_status === "left" && (
                  <button className="btn btn-sm btn-success" disabled={reviewBusy} onClick={reactivateEmployment}>
                    {reviewBusy ? "Please wait…" : "Reactivate employment"}
                  </button>
                )}
              </div>
            )}
          </div>
          {canReviewResignation && emp.employment_status === "resignation_pending" && (
            <div style={{ marginTop: 12 }}>
              <div className="form-field" style={{ maxWidth: 240, marginBottom: 10 }}>
                <label htmlFor="resignation-notice-period">Notice period end date if accepted</label>
                <input
                  id="resignation-notice-period"
                  type="date"
                  min={todayDate}
                  required
                  value={reviewLastWorkingDay}
                  onChange={(event) => setReviewLastWorkingDay(event.target.value)}
                />
                <span className="muted" style={{ fontSize: 11.5 }}>Choose the agreed last working day from the calendar.</span>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-sm btn-success" disabled={reviewBusy || !validNoticePeriod} onClick={() => reviewResignation("accepted")}>Accept resignation</button>
                <button className="btn btn-sm btn-outline" disabled={reviewBusy} onClick={() => reviewResignation("rejected")}>Reject</button>
              </div>
            </div>
          )}
        </div>

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
              {canManageCtc && ctcLoaded && (
                <div><span className="muted">Annual CTC</span><div>{form.annual_ctc === "" ? "—" : `₹${Number(form.annual_ctc).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}</div></div>
              )}
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
              {canManageCtc && ctcLoaded && (
                <div className="form-field">
                  <label htmlFor="edit-employee-annual-ctc">Annual CTC (₹)</label>
                  <input
                    id="edit-employee-annual-ctc"
                    type="number"
                    min="0"
                    step="0.01"
                    value={form.annual_ctc}
                    onChange={(e) => setForm({ ...form, annual_ctc: e.target.value })}
                  />
                </div>
              )}
              {canManageCtc && (
                <div className="form-field">
                  <label>Manager</label>
                  {managerLoadError ? (
                    <div className="login-error">{managerLoadError}</div>
                  ) : (
                    <ManagerSelector
                      managers={managers}
                      value={form.manager_id}
                      onChange={(managerId) => setForm({ ...form, manager_id: managerId })}
                    />
                  )}
                </div>
              )}
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
        </>}

        {activeTab === "leave-attendance" && (isAdmin || isOwnReport || emp.id === user.id) && <>
          <LeaveBalanceSummary
            balances={leaveBalances}
            loading={leaveBalanceLoading}
            error={leaveBalanceError}
            showLink={false}
          />

        {emp.is_active && emp.role !== ROLES.CONTRACT_EMPLOYEE && (isAdmin || isOwnReport) && (
          <EmployeeAttendanceSection employee={emp} />
        )}
        </>}

        {activeTab === "personal" && canViewEmployeeRecords && (
          <div style={{ display: "grid", gap: 14, marginTop: 16 }}>
            <EmployeePersonalDetailsPanel employeeId={emp.id} canEdit onChanged={onChanged} />
            <EmployeeFamilyPanel employeeId={emp.id} canEdit />
          </div>
        )}

        {activeTab === "documents" && canViewEmployeeRecords && (
          <div style={{ display: "grid", gap: 14, marginTop: 16 }}>
            <EmployeeDocumentsPanel
              employeeId={emp.id}
              canUpload
              canReview={canManageHrRecords}
            />
            {canManageHrRecords && <EmployeeManagementPanel employeeId={emp.id} />}
          </div>
        )}
        </div>

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
