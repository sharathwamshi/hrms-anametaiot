import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import { parseUtc } from "../utils/datetime";
import AppLayout from "../components/AppLayout";
import StatCard from "../components/StatCard";
import Loader from "../components/Loader";
import ClockWidget from "../components/ClockWidget";
import Badge from "../components/Badge";
import CandidateDetailModal from "../components/CandidateDetailModal";
import LeaveBalanceSummary from "../components/LeaveBalanceSummary";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";

const STAT_META = {
  headcount: { label: "Total Headcount", icon: "\u25A5", color: "blue" },
  present_today: { label: "Present Today", icon: "\u2713", color: "green" },
  pending_leave_requests: { label: "Pending Leave Requests", icon: "\u2708", color: "amber" },
  open_positions: { label: "Open Positions", icon: "\u2605", color: "orange" },
  team_size: { label: "Team Size", icon: "\u25A5", color: "blue" },
  team_present_today: { label: "Team Present Today", icon: "\u2713", color: "green" },
  pending_approvals: { label: "Pending Approvals", icon: "\u2757", color: "purple" },
  payslips_this_month: { label: "Payslips This Month", icon: "\u20B9", color: "indigo" },
  pending_payout: { label: "Pending Payout", icon: "\u23F3", color: "amber" },
  active_candidates: { label: "Active Candidates", icon: "\u25CF", color: "purple" },
  hired_this_month: { label: "Hired This Month", icon: "\u2713", color: "green" },
  candidates_added_today: { label: "Candidates Added Today", icon: "\u002B", color: "green" },
  pending_verification_count: { label: "Pending Verification", icon: "\u2753", color: "amber" },
};

export default function Dashboard() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [summaryError, setSummaryError] = useState("");
  const [leaveBalances, setLeaveBalances] = useState([]);
  const [leaveBalancesLoading, setLeaveBalancesLoading] = useState(user.role !== ROLES.CONTRACT_EMPLOYEE);
  const [leaveBalancesError, setLeaveBalancesError] = useState("");

  useEffect(() => {
    let active = true;
    client
      .get("/dashboard/summary")
      .then(({ data }) => {
        if (active) setSummary(data);
      })
      .catch((err) => {
        if (active) setSummaryError(err?.response?.data?.message || "Could not load the dashboard.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    if (user.role !== ROLES.CONTRACT_EMPLOYEE) {
      client
        .get("/leave/balances")
        .then(({ data }) => {
          if (active) setLeaveBalances(data);
        })
        .catch((err) => {
          if (active) setLeaveBalancesError(err?.response?.data?.message || "Could not load your leave balance.");
        })
        .finally(() => {
          if (active) setLeaveBalancesLoading(false);
        });
    }
    return () => {
      active = false;
    };
  }, [user.role]);

  const showClock = user.role !== ROLES.HR_OPERATIONS; // HR ops dashboard is admin-focused; still reachable via Attendance page

  return (
    <AppLayout title={`Welcome, ${user.full_name.split(" ")[0]}`} subtitle="Here's what's happening today.">
      {loading ? (
        <Loader />
      ) : !summary ? (
        <div className="login-error" role="alert">{summaryError || "Could not load the dashboard."}</div>
      ) : (
        <>
          <div className="stat-grid">
            {Object.entries(summary)
              .filter(([key]) => STAT_META[key])
              .map(([key, value]) => (
                <StatCard
                  key={key}
                  label={STAT_META[key].label}
                  value={value}
                  icon={STAT_META[key].icon}
                  color={STAT_META[key].color}
                />
              ))}
          </div>

          {user.role !== ROLES.CONTRACT_EMPLOYEE && (
            <LeaveBalanceSummary
              balances={leaveBalances}
              loading={leaveBalancesLoading}
              error={leaveBalancesError}
            />
          )}

          <div className="two-col">
            {showClock ? <ClockWidget /> : <div />}

            <div className="card">
              <div className="card-title-row">
                <h3>Announcements</h3>
              </div>
              {summary.recent_announcements?.length ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {summary.recent_announcements.map((a) => (
                    <div key={a.id} style={{ borderBottom: "1px solid var(--color-border)", paddingBottom: 12 }}>
                      <div style={{ fontWeight: 700, fontSize: 13.5 }}>{a.title}</div>
                      <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>{a.body}</div>
                      <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                        {a.author_name} &middot; {parseUtc(a.created_at).toLocaleDateString("en-IN")}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="muted" style={{ fontSize: 13 }}>No announcements yet.</div>
              )}
            </div>
          </div>

          {user.role === ROLES.HR_RECRUITER && <RecruiterPanel summary={summary} />}
        </>
      )}
    </AppLayout>
  );
}

function RecruiterPanel({ summary }) {
  const [selectedCandidateId, setSelectedCandidateId] = useState(null);
  const maxDay = Math.max(1, ...(summary.candidates_by_day || []).map((d) => d.count));

  return (
    <div className="two-col section-gap">
      <div className="card">
        <div className="card-title-row"><h3>Candidates Added — Last 7 Days</h3></div>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 110, padding: "0 4px" }}>
          {(summary.candidates_by_day || []).map((d) => (
            <div key={d.date} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <div className="muted" style={{ fontSize: 11, fontWeight: 700 }}>{d.count}</div>
              <div
                style={{
                  width: "100%", maxWidth: 28, borderRadius: "4px 4px 0 0",
                  background: d.count > 0 ? "var(--color-primary-500)" : "var(--color-border)",
                  height: `${Math.max(4, (d.count / maxDay) * 70)}px`,
                }}
              />
              <div className="muted" style={{ fontSize: 10.5 }}>
                {new Date(d.date).toLocaleDateString("en-IN", { weekday: "short" })}
              </div>
            </div>
          ))}
        </div>

        <div className="card-title-row" style={{ marginTop: 18 }}><h3>Quick Actions</h3></div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link className="btn btn-sm btn-primary" to="/recruitment">+ Add Candidate</Link>
          <Link className="btn btn-sm btn-outline" to="/recruitment">+ New Requisition</Link>
          <Link className="btn btn-sm btn-outline" to="/all-candidates">View All Candidates</Link>
          {summary.pending_verification_count > 0 && (
            <Link className="btn btn-sm btn-outline" to="/all-candidates">
              {summary.pending_verification_count} Pending Verification
            </Link>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-title-row"><h3>Recently Status-Changed</h3></div>
        {summary.recent_stage_changes?.length ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {summary.recent_stage_changes.map((c) => (
              <div
                key={`${c.candidate_id}-${c.changed_at}`}
                onClick={() => setSelectedCandidateId(c.candidate_id)}
                style={{ cursor: "pointer", borderBottom: "1px solid var(--color-border)", paddingBottom: 8 }}
              >
                <div className="flex-between">
                  <strong style={{ fontSize: 13 }}>{c.candidate_name}</strong>
                  <Badge status={c.stage} />
                </div>
                <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>
                  {c.detail} &middot; {parseUtc(c.changed_at).toLocaleString("en-IN")}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted" style={{ fontSize: 13 }}>No stage changes yet.</div>
        )}
      </div>

      {selectedCandidateId && (
        <CandidateDetailModal candidateId={selectedCandidateId} onClose={() => setSelectedCandidateId(null)} />
      )}
    </div>
  );
}
