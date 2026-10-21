import { useEffect, useState } from "react";
import ExportButton from "../components/ExportButton";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import { localDateStr } from "../utils/attendanceTime";

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
  const isApprover = APPROVER_ROLES.includes(user.role);

  const loadAll = async () => {
    setLoading(true);
    const calls = [
      client.get("/leave/types"),
      client.get("/leave/balances"),
      client.get("/leave/my-requests"),
    ];
    if (isApprover) calls.push(client.get("/leave/pending-approvals"));

    const results = await Promise.all(calls);
    setTypes(results[0].data);
    setBalances(results[1].data);
    setMyRequests(results[2].data);
    if (isApprover) setApprovals(results[3].data);
    setLoading(false);
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submitLeave = async (e) => {
    e.preventDefault();
    setError("");
    try {
      if (editingRequestId) {
        await client.put(`/leave/${editingRequestId}`, form);
      } else {
        await client.post("/leave/apply", form);
      }
      setShowForm(false);
      setEditingRequestId(null);
      setForm({ leave_type_id: "", start_date: "", end_date: "", reason: "" });
      loadAll();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not submit leave request.");
    }
  };

  const editRequest = (request) => {
    setEditingRequestId(request.id);
    setForm({
      leave_type_id: String(request.leave_type_id),
      start_date: request.start_date,
      end_date: request.end_date,
      reason: request.reason || "",
    });
    setError("");
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingRequestId(null);
    setForm({ leave_type_id: "", start_date: "", end_date: "", reason: "" });
    setError("");
  };

  const decide = async (id, decision) => {
    const comment = window.prompt(`Comment for this ${decision} decision (optional):`) || "";
    await client.post(`/leave/${id}/decision`, { decision, comment });
    loadAll();
  };

  const cancelRequest = async (request) => {
    if (!window.confirm("Cancel this leave request?")) return;
    try {
      await client.post(`/leave/${request.id}/cancel`);
      await loadAll();
    } catch (err) {
      window.alert(err?.response?.data?.message || "Could not cancel leave request.");
    }
  };

  if (loading) return <AppLayout title="Leave"><Loader /></AppLayout>;

  return (
    <AppLayout title="Leave" subtitle="Apply for leave and track approvals.">
      <div className="stat-grid">
        {balances.map((b) => (
          <div className="stat-card" key={b.leave_type}>
            <div>
              <div className="label">{b.leave_type}</div>
              <div className="value">{b.balance}</div>
              <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>of {b.allocated} days allocated</div>
            </div>
          </div>
        ))}
      </div>

      <div className="card section-gap">
        <div className="card-title-row">
          <h3>My Leave Requests</h3>
          <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>+ Apply for Leave</button>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr><th>Type</th><th>From</th><th>To</th><th>Days</th><th>Status</th><th>Reviewer</th><th>Action</th></tr>
            </thead>
            <tbody>
              {myRequests.length === 0 && (
                <tr className="empty-row"><td colSpan={7}>No leave requests yet.</td></tr>
              )}
              {myRequests.map((r) => (
                <tr key={r.id}>
                  <td>{r.leave_type}</td>
                  <td>{r.start_date}</td>
                  <td>{r.end_date}</td>
                  <td>{r.days}</td>
                  <td><Badge status={r.status} /></td>
                  <td>{r.reviewer_name || "—"}</td>
                  <td>{r.status === "pending" && user.role !== ROLES.CONTRACT_EMPLOYEE && (
                    <div style={{ display: "flex", gap: 6 }}>
                      <button className="btn btn-sm btn-outline" onClick={() => editRequest(r)}>Edit</button>
                      <button className="btn btn-sm btn-danger" onClick={() => cancelRequest(r)}>Cancel</button>
                    </div>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {isApprover && (
        <div className="card">
          <div className="card-title-row"><h3>Pending Approvals</h3><ExportButton filename="Leave_Pending_Approvals" /></div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr><th>Employee</th><th>Type</th><th>From</th><th>To</th><th>Days</th><th>Reason</th><th>Action</th></tr>
              </thead>
              <tbody>
                {approvals.length === 0 && (
                  <tr className="empty-row"><td colSpan={7}>No pending requests.</td></tr>
                )}
                {approvals.map((r) => (
                  <tr key={r.id}>
                    <td>{r.employee_name}</td>
                    <td>{r.leave_type}</td>
                    <td>{r.start_date}</td>
                    <td>{r.end_date}</td>
                    <td>{r.days}</td>
                    <td>{r.reason}</td>
                    <td>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="btn btn-sm btn-success" onClick={() => decide(r.id, "approved")}>Approve</button>
                        <button className="btn btn-sm btn-danger" onClick={() => decide(r.id, "rejected")}>Reject</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showForm && (
        <div className="modal-overlay" onClick={closeForm}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>{editingRequestId ? "Edit Leave Request" : "Apply for Leave"}</h3>
            {error && <div className="login-error">{error}</div>}
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
                  <input type="date" required min={localDateStr()} value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value, end_date: form.end_date < e.target.value ? e.target.value : form.end_date })} />
                </div>
                <div className="form-field">
                  <label>End Date</label>
                  <input type="date" required min={form.start_date || localDateStr()} value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
                </div>
              </div>
              <div className="form-field">
                <label>Reason</label>
                <textarea rows={3} maxLength={500} required value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" onClick={closeForm}>Cancel</button>
                <button type="submit" className="btn btn-primary">{editingRequestId ? "Save Changes" : "Submit Request"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
