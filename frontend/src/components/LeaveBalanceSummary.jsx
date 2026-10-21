import { Link } from "react-router-dom";
import Loader from "./Loader";

export default function LeaveBalanceSummary({ balances, loading = false, error = "", showLink = true }) {
  return (
    <section className="card section-gap" aria-labelledby="leave-balance-heading">
      <div className="card-title-row">
        <h3 id="leave-balance-heading">Annual Leave Balance</h3>
        {showLink && <Link className="btn btn-sm btn-outline" to="/leave">View Leave</Link>}
      </div>
      {loading ? (
        <Loader label="Loading leave balances..." />
      ) : error ? (
        <div className="login-error" role="alert">{error}</div>
      ) : balances.length === 0 ? (
        <div className="muted" style={{ fontSize: 13 }}>No annual leave balances are set up for this year.</div>
      ) : (
        <div className="leave-balance-grid">
          {balances.map((balance) => (
            <div className="leave-balance-card" key={balance.leave_type}>
              <h4>{balance.leave_type}</h4>
              <div className="leave-balance-metrics">
                <div>
                  <span>Annual entitlement</span>
                  <strong>{balance.annual_entitlement} days</strong>
                </div>
                <div>
                  <span>Approved leave taken</span>
                  <strong>{balance.approved_leave_taken} days</strong>
                </div>
                <div>
                  <span>Remaining leave</span>
                  <strong>{balance.remaining_leave} days</strong>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
