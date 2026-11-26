import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import Loader from "./Loader";

export default function DashboardPendingRequests() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [sickApprovalRequest, setSickApprovalRequest] = useState(null);
  const [sickClassification, setSickClassification] = useState("");
  const [sickApprovalComment, setSickApprovalComment] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [leaveResponse, attendanceResponse] = await Promise.all([
        client.get("/leave/pending-approvals"),
        client.get("/attendance/regularization-requests", { params: { status: "pending" } }),
      ]);
      const leaveRequests = leaveResponse.data.map((request) => ({
        ...request,
        requestType: "Leave",
        key: `leave-${request.id}`,
      }));
      const attendanceRequests = attendanceResponse.data.map((request) => ({
        ...request,
        requestType: "Attendance correction",
        key: `attendance-${request.id}`,
      }));
      setRequests([...leaveRequests, ...attendanceRequests].slice(0, 6));
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load pending requests.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const decide = async (request, decision) => {
    if (
      request.requestType === "Leave"
      && decision === "approve"
      && /sick/i.test(request.leave_type || "")
    ) {
      setSickApprovalRequest(request);
      setSickClassification("");
      setSickApprovalComment("");
      return;
    }

    let comment = "";
    if (decision === "reject" && request.requestType === "Attendance correction") {
      comment = window.prompt("Enter a reason for rejecting this correction request.") || "";
      if (!comment.trim()) return;
    } else if (request.requestType === "Leave") {
      const response = window.prompt(`Optional comment for this ${decision} decision.`);
      if (response === null) return;
      comment = response;
    }

    setBusy(request.key);
    setError("");
    try {
      if (request.requestType === "Leave") {
        await client.post(`/leave/${request.id}/decision`, {
          decision: decision === "approve" ? "approved" : "rejected",
          comment,
        });
      } else {
        await client.post(`/attendance/regularization-requests/${request.id}/${decision}`, { comment });
      }
      await load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update this request.");
    } finally {
      setBusy("");
    }
  };

  const approveSickLeave = async (event) => {
    event.preventDefault();
    if (!sickApprovalRequest || !["paid", "casual"].includes(sickClassification)) return;
    setBusy(sickApprovalRequest.key);
    setError("");
    try {
      await client.post(`/leave/${sickApprovalRequest.id}/decision`, {
        decision: "approved",
        final_classification: sickClassification,
        comment: sickApprovalComment,
      });
      setSickApprovalRequest(null);
      await load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not approve this Sick Leave request.");
    } finally {
      setBusy("");
    }
  };

  return (
    <>
    <section className="card dashboard-pending section-gap" aria-label="Pending requests">
      <div className="card-title-row">
        <div>
          <h3>Pending Requests</h3>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Leave and attendance correction approvals</div>
        </div>
      </div>
      {error && <div className="login-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}
      {loading ? <Loader /> : requests.length === 0 ? (
        <div className="muted" style={{ fontSize: 13 }}>There are no pending requests in your approval scope.</div>
      ) : (
        <div className="table-wrap dashboard-pending-table-wrap">
          <table className="data-table dashboard-pending-table">
            <colgroup>
              <col className="dashboard-pending-col-employee" />
              <col className="dashboard-pending-col-request" />
              <col className="dashboard-pending-col-details" />
              <col className="dashboard-pending-col-dates" />
              <col className="dashboard-pending-col-action" />
            </colgroup>
            <thead><tr><th>Employee</th><th>Request</th><th>Details</th><th>Dates</th><th>Action</th></tr></thead>
            <tbody>
              {requests.map((request) => {
                const details = request.requestType === "Leave"
                  ? `${request.leave_type || "Leave"} · ${request.days || 0} day(s)`
                  : `${request.regularization_reason_label || "Punch correction"}${request.regularization_note ? ` · ${request.regularization_note}` : ""}`;
                const dates = request.requestType === "Leave"
                  ? `${request.start_date} – ${request.end_date}`
                  : request.work_date;
                return (
                  <tr key={request.key}>
                    <td data-label="Employee"><strong>{request.employee_name || "Employee"}</strong><div className="muted" style={{ fontSize: 11 }}>{request.employee_code || ""}</div></td>
                    <td data-label="Request">{request.requestType}</td>
                    <td data-label="Details" className="dashboard-pending-details" title={details}>{details}</td>
                    <td data-label="Dates" className="dashboard-pending-dates">{dates}</td>
                    <td data-label="Action" className="dashboard-pending-action">
                      <div className="dashboard-pending-actions">
                        <button className="btn btn-sm btn-success" disabled={busy === request.key} onClick={() => decide(request, "approve")}>Approve</button>
                        <button className="btn btn-sm btn-danger" disabled={busy === request.key} onClick={() => decide(request, "reject")}>Reject</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="dashboard-request-footer">
        <span className="muted" style={{ fontSize: 11.5 }}>Approval actions use the existing HRMS APIs and permissions.</span>
        <Link to="/leave">View all requests ›</Link>
      </div>
    </section>
    {sickApprovalRequest && (
      <div className="modal-overlay" onClick={() => busy === "" && setSickApprovalRequest(null)}>
        <div className="modal-box" onClick={(event) => event.stopPropagation()}>
          <h3 style={{ marginBottom: 8 }}>Approve Sick Leave</h3>
          <p className="muted" style={{ marginBottom: 16 }}>
            {sickApprovalRequest.employee_name} · {sickApprovalRequest.start_date} to {sickApprovalRequest.end_date} · {sickApprovalRequest.days} day(s)
          </p>
          <form onSubmit={approveSickLeave}>
            <div className="form-field">
              <label htmlFor="dashboard-sick-classification">Approve this request as</label>
              <select
                id="dashboard-sick-classification"
                required
                value={sickClassification}
                onChange={(event) => setSickClassification(event.target.value)}
              >
                <option value="">Select classification</option>
                <option value="paid">Paid Leave (no salary deduction)</option>
                <option value="casual">Casual Leave (salary deduction)</option>
              </select>
            </div>
            <p className="muted" style={{ fontSize: 12 }}>
              Paid Leave classification is allowed only after the employee completes three months of service.
            </p>
            <div className="form-field">
              <label htmlFor="dashboard-sick-comment">Manager remarks (optional)</label>
              <textarea
                id="dashboard-sick-comment"
                rows={3}
                maxLength={255}
                value={sickApprovalComment}
                onChange={(event) => setSickApprovalComment(event.target.value)}
              />
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                type="button"
                className="btn btn-outline"
                disabled={busy !== ""}
                onClick={() => setSickApprovalRequest(null)}
              >
                Cancel
              </button>
              <button type="submit" className="btn btn-success" disabled={busy !== "" || !sickClassification}>
                {busy === sickApprovalRequest.key ? "Approving..." : "Confirm Approval"}
              </button>
            </div>
          </form>
        </div>
      </div>
    )}
    </>
  );
}
