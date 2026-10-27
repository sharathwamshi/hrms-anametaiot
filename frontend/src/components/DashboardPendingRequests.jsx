import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import Loader from "./Loader";

export default function DashboardPendingRequests() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

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

  return (
    <section className="card dashboard-pending section-gap" aria-label="Pending requests">
      <div className="card-title-row">
        <div>
          <h3>Pending Requests</h3>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Leave and attendance correction approvals</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link className="btn btn-sm btn-outline" to="/leave">All leave requests</Link>
          <Link className="btn btn-sm btn-outline" to="/attendance?tab=approvals">Attendance corrections</Link>
        </div>
      </div>
      {error && <div className="login-error" role="alert" style={{ marginBottom: 12 }}>{error}</div>}
      {loading ? <Loader /> : requests.length === 0 ? (
        <div className="muted" style={{ fontSize: 13 }}>There are no pending requests in your approval scope.</div>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Employee</th><th>Request</th><th>Details</th><th>Dates</th><th>Action</th></tr></thead>
            <tbody>
              {requests.map((request) => (
                <tr key={request.key}>
                  <td><strong>{request.employee_name || "Employee"}</strong><div className="muted" style={{ fontSize: 11 }}>{request.employee_code || ""}</div></td>
                  <td>{request.requestType}</td>
                  <td>{request.requestType === "Leave"
                    ? `${request.leave_type || "Leave"} · ${request.days || 0} day(s)`
                    : `${request.regularization_reason_label || "Punch correction"}${request.regularization_note ? ` · ${request.regularization_note}` : ""}`}</td>
                  <td>{request.requestType === "Leave"
                    ? `${request.start_date} – ${request.end_date}`
                    : request.work_date}</td>
                  <td>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button className="btn btn-sm btn-success" disabled={busy === request.key} onClick={() => decide(request, "approve")}>Approve</button>
                      <button className="btn btn-sm btn-danger" disabled={busy === request.key} onClick={() => decide(request, "reject")}>Reject</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="dashboard-request-footer">
        <span className="muted" style={{ fontSize: 11.5 }}>Approval actions use the existing HRMS APIs and permissions.</span>
        <Link to="/leave">View all requests ›</Link>
      </div>
    </section>
  );
}
