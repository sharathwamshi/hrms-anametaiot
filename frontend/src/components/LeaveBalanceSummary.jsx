import { Link } from "react-router-dom";
import Loader from "./Loader";

const quantity = (request) => (
  request.duration && request.duration !== "full_day"
    ? 0.5
    : Number(request.days || 0)
);

export default function LeaveBalanceSummary({
  balances,
  requests = [],
  loading = false,
  error = "",
  showLink = true,
}) {
  const paid = balances.find((balance) => /paid/i.test(balance.leave_type));
  const casualRequests = requests.filter((request) => /casual/i.test(request.leave_type) && request.status === "approved");
  const casualTaken = casualRequests.reduce((total, request) => total + quantity(request), 0);
  const sickRequests = requests.filter((request) => /sick/i.test(request.leave_type) && request.status !== "cancelled");
  const sickApplied = sickRequests.reduce((total, request) => total + quantity(request), 0);
  const sickPending = sickRequests.filter((request) => request.status === "pending").length;
  const sickApproved = sickRequests.filter((request) => request.status === "approved").length;
  const sickRejected = sickRequests.filter((request) => request.status === "rejected").length;
  const sickPaid = sickRequests.filter((request) => request.final_classification === "paid")
    .reduce((total, request) => total + quantity(request), 0);
  const sickCasual = sickRequests.filter((request) => request.final_classification === "casual")
    .reduce((total, request) => total + quantity(request), 0);
  const salaryDeductibleDays = casualTaken + sickCasual;

  return (
    <section className="card section-gap" aria-labelledby="leave-balance-heading">
      <div className="card-title-row">
        <h3 id="leave-balance-heading">Leave Balances</h3>
        {showLink && <Link className="btn btn-sm btn-outline" to="/leave">View Leave</Link>}
      </div>
      {loading ? (
        <Loader label="Loading leave balances..." />
      ) : error ? (
        <div className="login-error" role="alert">{error}</div>
      ) : balances.length === 0 ? (
        <div className="muted" style={{ fontSize: 13 }}>No leave balances are set up for this year.</div>
      ) : (
        <div className="leave-balance-grid">
          <div className="leave-balance-card">
            <h4>Paid Leave</h4>
            {paid ? (
              <div className="leave-balance-metrics">
                <div>
                  <span>Allocated</span>
                  <strong>{paid.allocated} days</strong>
                </div>
                <div>
                  <span>Used</span>
                  <strong>{paid.used} days</strong>
                </div>
                <div>
                  <span>Remaining leave</span>
                  <strong>{paid.remaining_leave} days</strong>
                </div>
              </div>
            ) : <p className="muted">No Paid Leave allocation is configured.</p>}
            {paid?.eligibility_status === "not_eligible" && (
              <p className="muted">Eligible from {paid.eligibility_date || "after completing three months of employment"}.</p>
            )}
          </div>
          <div className="leave-balance-card">
            <h4>Casual Leave</h4>
            <div className="leave-balance-metrics">
              <div><span>Approved days taken</span><strong>{casualTaken} days</strong></div>
              <div><span>Salary-deductible</span><strong>{salaryDeductibleDays} days</strong></div>
              <div><span>Usage limit</span><strong>No fixed limit</strong></div>
            </div>
            <p className="muted">Approved Casual Leave is treated as absence and deducted from salary.</p>
          </div>
          <div className="leave-balance-card">
            <h4>Sick Leave</h4>
            <div className="leave-balance-metrics">
              <div><span>Applied</span><strong>{sickApplied} days</strong></div>
              <div><span>Pending</span><strong>{sickPending}</strong></div>
              <div><span>Approved</span><strong>{sickApproved}</strong></div>
            </div>
            <p className="muted">
              Rejected: {sickRejected} · Approved as Paid: {sickPaid} days · Approved as Casual: {sickCasual} days
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
