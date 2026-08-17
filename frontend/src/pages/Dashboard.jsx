import { useEffect, useState } from "react";
import client from "../api/client";
import { parseUtc } from "../utils/datetime";
import AppLayout from "../components/AppLayout";
import StatCard from "../components/StatCard";
import Loader from "../components/Loader";
import ClockWidget from "../components/ClockWidget";
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
};

export default function Dashboard() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    client
      .get("/dashboard/summary")
      .then(({ data }) => setSummary(data))
      .finally(() => setLoading(false));
  }, []);

  const showClock = user.role !== ROLES.HR_OPERATIONS; // HR ops dashboard is admin-focused; still reachable via Attendance page

  return (
    <AppLayout title={`Welcome, ${user.full_name.split(" ")[0]}`} subtitle="Here's what's happening today.">
      {loading || !summary ? (
        <Loader />
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
        </>
      )}
    </AppLayout>
  );
}
