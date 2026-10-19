import { useCallback, useEffect, useState } from "react";
import client from "../api/client";

export default function LeaveApprovalsPanel() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadRequests = useCallback(async () => {
    setError("");
    try {
      const { data } = await client.get("/leave/pending-approvals");
      setRequests(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load leave requests.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadRequests(); }, [loadRequests]);

  const decide = async (requestId, decision) => {
    setError("");
    const comment = window.prompt(`Comment for this ${decision} decision (optional):`);
    if (comment === null) return;
    try {
      await client.post(`/leave/${requestId}/decision`, { decision, comment });
      await loadRequests();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update this leave request.");
    }
  };

  return (
    <div className="card section-gap">
      <div className="card-title-row"><h3>Pending Leave Approvals</h3></div>
      {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}
      {loading ? <p className="muted">Loading leave requests…</p> : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr><th>Employee</th><th>Type</th><th>From</th><th>To</th><th>Days</th><th>Reason</th><th>Action</th></tr>
            </thead>
            <tbody>
              {requests.length === 0 && <tr className="empty-row"><td colSpan={7}>No pending leave requests.</td></tr>}
              {requests.map((request) => (
                <tr key={request.id}>
                  <td>{request.employee_name}</td>
                  <td>{request.leave_type}</td>
                  <td>{request.start_date}</td>
                  <td>{request.end_date}</td>
                  <td>{request.days}</td>
                  <td>{request.reason || "—"}</td>
                  <td>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button className="btn btn-sm btn-success" onClick={() => decide(request.id, "approved")}>Approve</button>
                      <button className="btn btn-sm btn-danger" onClick={() => decide(request.id, "rejected")}>Deny</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
