import { useEffect, useState } from "react";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import ClockWidget from "../components/ClockWidget";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import { parseUtc } from "../utils/datetime";

const TEAM_VIEW_ROLES = [ROLES.MANAGER, ROLES.HR_OPERATIONS, ROLES.OPERATIONS];

export default function Attendance() {
  const { user } = useAuth();
  const [tab, setTab] = useState("mine");
  const [history, setHistory] = useState([]);
  const [team, setTeam] = useState([]);
  const [loading, setLoading] = useState(true);
  const [teamDate, setTeamDate] = useState(new Date().toISOString().slice(0, 10));

  const canSeeTeam = TEAM_VIEW_ROLES.includes(user.role);

  const loadHistory = async () => {
    setLoading(true);
    const { data } = await client.get("/attendance/history");
    setHistory(data);
    setLoading(false);
  };

  const loadTeam = async (date) => {
    setLoading(true);
    const { data } = await client.get("/attendance/team", { params: { date } });
    setTeam(data);
    setLoading(false);
  };

  useEffect(() => {
    if (tab === "mine") loadHistory();
    if (tab === "team") loadTeam(teamDate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const regularize = async (id) => {
    const reason = window.prompt("Reason for regularizing this record:");
    if (reason === null) return;
    await client.post(`/attendance/regularize/${id}`, { reason });
    loadTeam(teamDate);
  };

  return (
    <AppLayout title="Attendance" subtitle="Clock in/out and track attendance history.">
      <div className="section-gap">
        <ClockWidget />
      </div>

      {canSeeTeam && (
        <div className="tag-list section-gap">
          <button className={`btn btn-sm ${tab === "mine" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("mine")}>
            My History
          </button>
          <button className={`btn btn-sm ${tab === "team" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("team")}>
            Team Attendance
          </button>
        </div>
      )}

      {tab === "mine" && (
        <div className="card">
          <div className="card-title-row">
            <h3>My Attendance — This Month</h3>
          </div>
          {loading ? (
            <Loader />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th><th>Clock In</th><th>Clock Out</th><th>Hours</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {history.length === 0 && (
                    <tr className="empty-row"><td colSpan={5}>No attendance records for this month yet.</td></tr>
                  )}
                  {history.map((r) => (
                    <tr key={r.id}>
                      <td>{r.work_date}</td>
                      <td>{r.clock_in ? parseUtc(r.clock_in).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                      <td>{r.clock_out ? parseUtc(r.clock_out).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                      <td>{r.total_hours || "—"}</td>
                      <td><Badge status={r.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "team" && canSeeTeam && (
        <div className="card">
          <div className="card-title-row">
            <h3>Team Attendance</h3>
            <input
              type="date"
              value={teamDate}
              onChange={(e) => {
                setTeamDate(e.target.value);
                loadTeam(e.target.value);
              }}
              style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "7px 10px" }}
            />
          </div>
          {loading ? (
            <Loader />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Employee</th><th>Clock In</th><th>Clock Out</th><th>Hours</th><th>Status</th>
                    {(user.role === ROLES.MANAGER || user.role === ROLES.HR_OPERATIONS) && <th>Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {team.length === 0 && (
                    <tr className="empty-row"><td colSpan={6}>No attendance records for this date.</td></tr>
                  )}
                  {team.map((r) => (
                    <tr key={r.id}>
                      <td>{r.employee_name}</td>
                      <td>{r.clock_in ? parseUtc(r.clock_in).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                      <td>{r.clock_out ? parseUtc(r.clock_out).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                      <td>{r.total_hours || "—"}</td>
                      <td><Badge status={r.status} /></td>
                      {(user.role === ROLES.MANAGER || user.role === ROLES.HR_OPERATIONS) && (
                        <td>
                          {!r.is_regularized && (
                            <button className="btn btn-sm btn-outline" onClick={() => regularize(r.id)}>
                              Regularize
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </AppLayout>
  );
}
