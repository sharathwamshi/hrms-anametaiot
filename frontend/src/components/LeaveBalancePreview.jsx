import { useEffect, useState } from "react";
import client from "../api/client";
import { leaveDaysByYear, localDateStr } from "../utils/attendanceTime";

const moneyDays = (value) => `${Number(value || 0)} days`;

export default function LeaveBalancePreview({ leaveTypeId, startDate, endDate, duration = "full_day" }) {
  const [balances, setBalances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const daysByYear = leaveDaysByYear(startDate, endDate);
  const years = Object.keys(daysByYear).map(Number);
  if (!years.length) years.push(Number(localDateStr().slice(0, 4)));

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.all(years.map((year) => client.get("/leave/balances", { params: { year } })))
      .then((responses) => {
        if (!cancelled) {
          setBalances(responses.flatMap((response, index) =>
            response.data.map((balance) => ({ ...balance, year: years[index] }))
          ));
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err?.response?.data?.message || "Could not load leave balances.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [years.join(",")]);

  const requested = duration === "full_day"
    ? Object.values(daysByYear).reduce((sum, days) => sum + days, 0)
    : 0.5;
  const selectedBalance = leaveTypeId
    ? balances.filter((balance) => String(balance.leave_type_id) === String(leaveTypeId))
    : [];
  const selectedType = selectedBalance[0]?.leave_type?.toLowerCase() || "";
  const paidLeaveSelected = selectedType.includes("paid") || selectedType.includes("earned");
  const casualLeaveSelected = selectedType.includes("casual");
  const sickLeaveSelected = selectedType.includes("sick");
  const insufficient = paidLeaveSelected && leaveTypeId && requested > 0 && years.some((year) => {
    const balance = selectedBalance.find((item) => item.year === year);
    const requestedForYear = duration === "full_day" ? (daysByYear[year] || 0) : 0.5;
    return requestedForYear > Number(balance?.available || 0);
  });

  return (
    <section className="card" aria-labelledby="leave-application-balance-heading" style={{ margin: "12px 0" }}>
      <h4 id="leave-application-balance-heading" style={{ margin: "0 0 8px" }}>Available leave balance</h4>
      {loading ? <p className="muted">Loading balances…</p> : error ? (
        <div className="login-error" role="alert">{error}</div>
      ) : balances.length === 0 ? (
        <p className="muted">No leave balances are configured for the selected year.</p>
      ) : (
        years.map((year) => {
          const rows = balances.filter((balance) => balance.year === year);
          return (
            <div key={year} style={{ marginBottom: 8 }}>
              <strong>{year}</strong>
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr><th>Leave type</th><th>Allocated</th><th>Used</th><th>Remaining</th></tr></thead>
                  <tbody>
                    {rows.map((balance) => {
                      const unlimited = /casual|sick/i.test(balance.leave_type);
                      return (
                      <tr key={`${year}-${balance.leave_type_id}`}>
                        <td>{balance.leave_type}</td>
                        <td>{unlimited ? "No fixed limit" : moneyDays(balance.allocated)}</td>
                        <td>{moneyDays(balance.used)}</td>
                        <td>{unlimited ? "No fixed limit" : moneyDays(balance.remaining_leave)}</td>
                      </tr>
                      );
                    })}
                    {!rows.length && <tr className="empty-row"><td colSpan={4}>No balances configured.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })
      )}
      {!loading && !error && insufficient && (
        <p className="login-error" role="alert">
          Insufficient available balance for this date range. Pending requests are reserved; reduce the requested days or contact your manager.
        </p>
      )}
      {!loading && !error && requested > 0 && !insufficient && leaveTypeId && (
        <p className="muted" role="status">Eligible leave days requested: {requested} (Sundays are excluded).</p>
      )}
      {!loading && paidLeaveSelected && selectedBalance[0]?.eligibility_status === "not_eligible" && (
        <p className="login-error" role="alert">
          Paid Leave is unavailable during your first three months. Eligibility begins {selectedBalance[0].eligibility_date || "after completing three months"}.
        </p>
      )}
      {!loading && paidLeaveSelected && selectedBalance[0]?.exhausted && (
        <p className="login-error" role="alert">Your Paid Leave balance is exhausted. Casual Leave and Sick Leave remain available; Casual Leave results in salary deduction.</p>
      )}
      {!loading && casualLeaveSelected && (
        <p className="login-error" role="alert">Approved Casual Leave counts as absence and results in salary deduction.</p>
      )}
      {!loading && sickLeaveSelected && (
        <p className="muted" role="status">Sick Leave requires Manager approval and will be classified as Paid or Casual Leave.</p>
      )}
    </section>
  );
}
