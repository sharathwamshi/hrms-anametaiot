import { useEffect, useState } from "react";
import ExportButton from "../components/ExportButton";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import LeaveBalanceSummary from "../components/LeaveBalanceSummary";
import LeaveBalancePreview from "../components/LeaveBalancePreview";
import LeaveReasonPreview from "../components/LeaveReasonPreview";
import ManagerLeaveDashboard from "../components/ManagerLeaveDashboard";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import {
  isDisallowedBackdatedLeaveDate,
  isSundayDate,
  BACKDATED_LEAVE_ERROR,
  currentMonthLeaveStart,
} from "../utils/attendanceTime";

const APPROVER_ROLES = [ROLES.MANAGER, ROLES.HR_OPERATIONS, ROLES.SUPER_ADMIN];

export default function Leave() {
  const { user } = useAuth();
  const [types, setTypes] = useState([]);
  const [balances, setBalances] = useState([]);
  const [myRequests, setMyRequests] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingRequestId, setEditingRequestId] = useState(null);
  const [form, setForm] = useState({ leave_type_id: "", start_date: "", end_date: "", reason: "" });
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");
  const [busyRequestId, setBusyRequestId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [leaveTab, setLeaveTab] = useState("my");
  const [myPage, setMyPage] = useState(1);
  const [myPageSize, setMyPageSize] = useState(10);
  const [mySort, setMySort] = useState({ key: "start_date", direction: "desc" });
  const [approvalPage, setApprovalPage] = useState(1);
  const [approvalPageSize, setApprovalPageSize] = useState(10);
  const [approvalSort, setApprovalSort] = useState({ key: "start_date", direction: "desc" });
  const isManager = user.role === ROLES.MANAGER;
  const isApprover = APPROVER_ROLES.includes(user.role) && !isManager;
  const minimumDate = currentMonthLeaveStart();
  const minimumEndDate = form.start_date && (!minimumDate || form.start_date > minimumDate)
    ? form.start_date
    : minimumDate;
  const sortedMyRequests = [...myRequests].sort((a, b) => {
    const left = a[mySort.key] ?? "";
    const right = b[mySort.key] ?? "";
    const comparison = typeof left === "number" && typeof right === "number"
      ? left - right
      : String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
    return comparison * (mySort.direction === "asc" ? 1 : -1);
  });
  const myPageCount = myPageSize === 0 ? 1 : Math.max(1, Math.ceil(sortedMyRequests.length / myPageSize));
  const pageMyRequests = myPageSize === 0
    ? sortedMyRequests
    : sortedMyRequests.slice((myPage - 1) * myPageSize, myPage * myPageSize);
  const sortedApprovals = [...approvals].sort((a, b) => {
    const left = a[approvalSort.key] ?? "";
    const right = b[approvalSort.key] ?? "";
    const comparison = typeof left === "number" && typeof right === "number"
      ? left - right
      : String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
    return comparison * (approvalSort.direction === "asc" ? 1 : -1);
  });
  const approvalPageCount = approvalPageSize === 0 ? 1 : Math.max(1, Math.ceil(sortedApprovals.length / approvalPageSize));
  const pageApprovals = approvalPageSize === 0
    ? sortedApprovals
    : sortedApprovals.slice((approvalPage - 1) * approvalPageSize, approvalPage * approvalPageSize);

  useEffect(() => { setMyPage(1); }, [myRequests, myPageSize]);
  useEffect(() => { setApprovalPage(1); }, [approvals, approvalPageSize]);

  const loadAll = async () => {
    setLoading(true);
    setError("");
    const calls = [
      client.get("/leave/types"),
      client.get("/leave/balances"),
      client.get("/leave/my-requests"),
    ];
    if (isApprover) calls.push(client.get("/leave/pending-approvals"));

    try {
      const results = await Promise.all(calls);
      setTypes(results[0].data);
      setBalances(results[1].data);
      setMyRequests(results[2].data);
      if (isApprover) setApprovals(results[3].data);
      return true;
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load leave information.");
      return false;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const closeForm = () => {
    setShowForm(false);
    setFormError("");
  };

  const submitLeave = async (e) => {
    e.preventDefault();
    setFormError("");
    setSuccess("");
    if (isSundayDate(form.start_date) || isSundayDate(form.end_date)) {
      setFormError("Leave start and end dates cannot be Sundays.");
      return;
    }
    if (
      isDisallowedBackdatedLeaveDate(form.start_date) ||
      isDisallowedBackdatedLeaveDate(form.end_date)
    ) {
      setFormError(BACKDATED_LEAVE_ERROR);
      return;
    }
    setSubmitting(true);
    try {
      if (editingRequestId) {
        await client.put(`/leave/${editingRequestId}`, form);
      } else {
        await client.post("/leave/apply", form);
      }
      setShowForm(false);
      setEditingRequestId(null);
      setForm({ leave_type_id: "", start_date: "", end_date: "", reason: "" });
      if (await loadAll()) setSuccess("Your leave request was submitted.");
    } catch (err) {
      setFormError(err?.response?.data?.message || "Could not submit leave request.");
    } finally {
      setSubmitting(false);
    }
  };

  const decide = async (id, decision) => {
    const comment = window.prompt(`Comment for this ${decision} decision (optional):`) || "";
    setError("");
    setSuccess("");
    setBusyRequestId(id);
    try {
      await client.post(`/leave/${id}/decision`, { decision, comment });
      if (await loadAll()) setSuccess(`Leave request ${decision}.`);
    } catch (err) {
      setError(err?.response?.data?.message || `Could not ${decision} this leave request.`);
    } finally {
      setBusyRequestId(null);
    }
  };

  const sortMyRequests = (key) => {
    setMySort((current) => ({ key, direction: current.key === key && current.direction === "asc" ? "desc" : "asc" }));
    setMyPage(1);
  };
  const sortLabel = (key, label) => (
    <button type="button" className="table-sort-button" onClick={() => sortMyRequests(key)}>
      {label}{mySort.key === key ? (mySort.direction === "asc" ? " ▲" : " ▼") : ""}
    </button>
  );
  const sortApprovalLabel = (key, label) => (
    <button
      type="button"
      className="table-sort-button"
      onClick={() => {
        setApprovalSort((current) => ({ key, direction: current.key === key && current.direction === "asc" ? "desc" : "asc" }));
        setApprovalPage(1);
      }}
    >
      {label}{approvalSort.key === key ? (approvalSort.direction === "asc" ? " ▲" : " ▼") : ""}
    </button>
  );
  const updateLeaveDate = (field, value) => {
    if (isSundayDate(value)) {
      setFormError("Sundays cannot be selected for leave.");
      return;
    }
    if (isDisallowedBackdatedLeaveDate(value)) {
      setFormError(BACKDATED_LEAVE_ERROR);
      return;
    }
    setFormError("");
    setForm((current) => ({
      ...current,
      [field]: value,
      ...(field === "start_date" && current.end_date < value ? { end_date: value } : {}),
    }));
  };

  if (loading) return <AppLayout title="Leave"><Loader /></AppLayout>;

  return (
    <AppLayout title="Leave" subtitle="Apply for leave and track approvals.">
      {error && <div className="login-error" role="alert">{error}</div>}
      {success && <div className="notice-success" role="status">{success}</div>}
      {(isManager || isApprover) && (
        <div className="tag-list section-gap" role="tablist" aria-label="Leave views">
          <button type="button" role="tab" aria-selected={leaveTab === "my"} className={`btn btn-sm ${leaveTab === "my" ? "btn-primary" : "btn-outline"}`} onClick={() => setLeaveTab("my")}>My Leave</button>
          <button type="button" role="tab" aria-selected={leaveTab === "team"} className={`btn btn-sm ${leaveTab === "team" ? "btn-primary" : "btn-outline"}`} onClick={() => setLeaveTab("team")}>Team Leave</button>
        </div>
      )}

      {leaveTab === "my" && (
        <>
          <LeaveBalanceSummary balances={balances} showLink={false} />
          <div className="card section-gap">
            <div className="card-title-row">
              <h3>My Leave Requests</h3>
              <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>+ Apply for Leave</button>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr><th>{sortLabel("leave_type", "Type")}</th><th>{sortLabel("start_date", "From")}</th><th>{sortLabel("end_date", "To")}</th><th>{sortLabel("days", "Days")}</th><th>{sortLabel("status", "Status")}</th><th>Reviewer</th></tr>
                </thead>
                <tbody>
                  {myRequests.length === 0 && <tr className="empty-row"><td colSpan={6}>No leave requests yet.</td></tr>}
                  {pageMyRequests.map((r) => (
                    <tr key={r.id}>
                      <td>{r.leave_type}</td><td>{r.start_date}</td><td>{r.end_date}</td><td>{r.days}</td>
                      <td><Badge status={r.status} /></td><td>{r.reviewer_name || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-pagination">
              <span>{sortedMyRequests.length ? `Showing ${myPageSize === 0 ? 1 : (myPage - 1) * myPageSize + 1}–${myPageSize === 0 ? sortedMyRequests.length : Math.min(myPage * myPageSize, sortedMyRequests.length)} of ${sortedMyRequests.length}` : "0 requests"}</span>
              <label>Rows per page
                <select value={myPageSize} onChange={(event) => { setMyPageSize(Number(event.target.value)); setMyPage(1); }}>
                  {[10, 25, 50].map((size) => <option key={size} value={size}>{size}</option>)}
                  <option value={0}>Show All</option>
                </select>
              </label>
              <button type="button" className="btn btn-sm btn-outline" disabled={myPage <= 1} onClick={() => setMyPage((current) => current - 1)}>Previous</button>
              <span>Page {myPageSize === 0 ? 1 : Math.min(myPage, myPageCount)} of {myPageCount}</span>
              <button type="button" className="btn btn-sm btn-outline" disabled={myPage >= myPageCount} onClick={() => setMyPage((current) => current + 1)}>Next</button>
            </div>
          </div>
        </>
      )}

      {leaveTab === "team" && isManager && <ManagerLeaveDashboard />}
      {leaveTab === "team" && isApprover && (
        <div className="card">
          <div className="card-title-row"><h3>Pending Approvals</h3><ExportButton filename="Leave_Pending_Approvals" /></div>
          <div className="table-wrap">
            <table className="data-table leave-approvals-table">
              <thead><tr><th>{sortApprovalLabel("employee_name", "Employee")}</th><th>{sortApprovalLabel("employee_code", "Employee ID")}</th><th>{sortApprovalLabel("leave_type", "Type")}</th><th>{sortApprovalLabel("start_date", "From")}</th><th>{sortApprovalLabel("end_date", "To")}</th><th>{sortApprovalLabel("days", "Days")}</th><th>Reason</th><th>Action</th></tr></thead>
              <tbody>
                {approvals.length === 0 && <tr className="empty-row"><td colSpan={8}>No pending requests.</td></tr>}
                {pageApprovals.map((r) => (
                  <tr key={r.id}>
                    <td>{r.employee_name}</td><td>{r.employee_code}</td><td>{r.leave_type}</td><td>{r.start_date}</td><td>{r.end_date}</td><td>{r.days}</td>
                    <td><LeaveReasonPreview reason={r.reason} /></td>
                    <td><div style={{ display: "flex", gap: 6 }}>
                      <button className="btn btn-sm btn-success" disabled={busyRequestId === r.id} onClick={() => decide(r.id, "approved")}>Approve</button>
                      <button className="btn btn-sm btn-danger" disabled={busyRequestId === r.id} onClick={() => decide(r.id, "rejected")}>Reject</button>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-pagination">
            <span>{sortedApprovals.length ? `Showing ${approvalPageSize === 0 ? 1 : (approvalPage - 1) * approvalPageSize + 1}–${approvalPageSize === 0 ? sortedApprovals.length : Math.min(approvalPage * approvalPageSize, sortedApprovals.length)} of ${sortedApprovals.length}` : "0 requests"}</span>
            <label>Rows per page
              <select value={approvalPageSize} onChange={(event) => { setApprovalPageSize(Number(event.target.value)); setApprovalPage(1); }}>
                {[10, 25, 50].map((size) => <option key={size} value={size}>{size}</option>)}
                <option value={0}>Show All</option>
              </select>
            </label>
            <button type="button" className="btn btn-sm btn-outline" disabled={approvalPage <= 1} onClick={() => setApprovalPage((current) => current - 1)}>Previous</button>
            <span>Page {approvalPageSize === 0 ? 1 : Math.min(approvalPage, approvalPageCount)} of {approvalPageCount}</span>
            <button type="button" className="btn btn-sm btn-outline" disabled={approvalPage >= approvalPageCount} onClick={() => setApprovalPage((current) => current + 1)}>Next</button>
          </div>
        </div>
      )}

      {showForm && (
        <div className="modal-overlay" onClick={closeForm}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>Apply for Leave</h3>
            {formError && <div className="login-error" role="alert">{formError}</div>}
            <form onSubmit={submitLeave}>
              <div className="form-field">
                <label>Leave Type</label>
                <select required value={form.leave_type_id} onChange={(e) => setForm({ ...form, leave_type_id: e.target.value })}>
                  <option value="">Select type</option>
                  {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Start Date</label>
                  <input type="date" required min={minimumDate} value={form.start_date} onChange={(e) => updateLeaveDate("start_date", e.target.value)} />
                </div>
                <div className="form-field">
                  <label>End Date</label>
                  <input type="date" required min={minimumEndDate} value={form.end_date} onChange={(e) => updateLeaveDate("end_date", e.target.value)} />
                </div>
              </div>
              <LeaveBalancePreview
                leaveTypeId={form.leave_type_id}
                startDate={form.start_date}
                endDate={form.end_date}
              />
              <div className="form-field">
                <label>Reason</label>
                <textarea rows={3} maxLength={500} required value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-success" disabled={submitting}>
                  {submitting ? "Submitting..." : "Submit Request"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
