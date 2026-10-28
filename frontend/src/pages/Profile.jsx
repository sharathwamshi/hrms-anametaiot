import { useEffect, useState } from "react";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import { useAuth } from "../context/AuthContext";
import { ROLE_LABELS, ROLES } from "../config/roles";
import LeaveApprovalsPanel from "../components/LeaveApprovalsPanel";

const APPROVER_ROLES = [ROLES.MANAGER, ROLES.HR_OPERATIONS, ROLES.SUPER_ADMIN];

export default function Profile() {
  const { user, roleLabel, setUser } = useAuth();
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [employmentError, setEmploymentError] = useState("");
  const [employmentBusy, setEmploymentBusy] = useState(false);
  const [resignationDialogOpen, setResignationDialogOpen] = useState(false);
  const [today, setToday] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setToday(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    client.get(`/employees/${user.id}`)
      .then(({ data }) => setUser(data))
      .catch((err) => setEmploymentError(err?.response?.data?.message || "Could not load your employment status."));
  }, [setUser, user.id]);

  const requestResignation = async () => {
    setEmploymentBusy(true);
    setEmploymentError("");
    try {
      const { data } = await client.post("/employees/me/resignation");
      setUser(data.user);
      setResignationDialogOpen(false);
    } catch (err) {
      setEmploymentError(err?.response?.data?.message || "Could not submit your resignation request.");
    } finally {
      setEmploymentBusy(false);
    }
  };

  const withdrawResignation = async () => {
    if (!window.confirm("Withdraw your resignation request and return your employment status to Active?")) return;
    setEmploymentBusy(true);
    setEmploymentError("");
    try {
      const { data } = await client.post("/employees/me/resignation/withdraw");
      setUser(data.user);
    } catch (err) {
      setEmploymentError(err?.response?.data?.message || "Could not withdraw your resignation.");
    } finally {
      setEmploymentBusy(false);
    }
  };

  const employmentStatusLabels = {
    active: "Active",
    resignation_pending: "Resignation pending manager review",
    notice_period: "Serving notice period",
    left: "Left the company",
  };
  const daysUntilLastWorkingDay = (lastWorkingDay) => {
    if (!lastWorkingDay) return null;
    const [year, month, day] = lastWorkingDay.split("-").map(Number);
    const end = Date.UTC(year, month - 1, day);
    const current = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
    return Math.max(0, Math.ceil((end - current) / 86_400_000));
  };
  const noticeDaysRemaining = user.last_working_day
    ? daysUntilLastWorkingDay(user.last_working_day)
    : null;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      await client.post("/auth/change-password", form);
      setMessage("Password updated successfully.");
      setForm({ current_password: "", new_password: "" });
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update password.");
    }
  };

  return (
    <AppLayout title="My Profile" subtitle="Your account details.">
      <div className="two-col">
        <div className="card">
          <div className="card-title-row"><h3>Employee Details</h3></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px 20px", fontSize: 13.5 }}>
            <div><div className="muted" style={{ fontSize: 11.5 }}>Employee Code</div><div>{user.employee_code}</div></div>
            <div><div className="muted" style={{ fontSize: 11.5 }}>Full Name</div><div>{user.full_name}</div></div>
            <div><div className="muted" style={{ fontSize: 11.5 }}>Email</div><div>{user.email}</div></div>
            <div><div className="muted" style={{ fontSize: 11.5 }}>Phone</div><div>{user.phone || "—"}</div></div>
            <div><div className="muted" style={{ fontSize: 11.5 }}>Role</div><div>{roleLabel || ROLE_LABELS[user.role]}</div></div>
            <div><div className="muted" style={{ fontSize: 11.5 }}>Designation</div><div>{user.designation || "—"}</div></div>
            <div><div className="muted" style={{ fontSize: 11.5 }}>Department</div><div>{user.department || "—"}</div></div>
            <div><div className="muted" style={{ fontSize: 11.5 }}>Manager</div><div>{user.manager_name || "—"}</div></div>
            <div><div className="muted" style={{ fontSize: 11.5 }}>Date of Joining</div><div>{user.date_of_joining || "—"}</div></div>
            <div>
              <div className="muted" style={{ fontSize: 11.5 }}>Employment Status</div>
              <div>{employmentStatusLabels[user.employment_status || "active"] || "Active"}</div>
              {user.employment_status === "notice_period" && user.last_working_day && (
                <div className="muted" style={{ fontSize: 12 }}>
                  Last working day: {user.last_working_day} · {noticeDaysRemaining} {noticeDaysRemaining === 1 ? "day" : "days"} remaining
                </div>
              )}
              {user.employment_status === "resignation_pending" && (
                <div className="muted" style={{ fontSize: 12 }}>Your manager or HR will review your request and confirm the notice period if accepted.</div>
              )}
            </div>
          </div>
          {employmentError && <div className="login-error" style={{ marginTop: 12 }}>{employmentError}</div>}
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            {(user.employment_status || "active") === "active" && (
              <button className="btn btn-danger btn-sm" disabled={employmentBusy} onClick={() => setResignationDialogOpen(true)}>
                Submit resignation
              </button>
            )}
            {["resignation_pending", "notice_period"].includes(user.employment_status) && (
              <button className="btn btn-outline btn-sm" disabled={employmentBusy} onClick={withdrawResignation}>
                {employmentBusy ? "Please wait…" : "Withdraw resignation"}
              </button>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-title-row"><h3>Change Password</h3></div>
          {message && <div className="login-demo-hint" style={{ marginBottom: 14 }}>{message}</div>}
          {error && <div className="login-error">{error}</div>}
          <form onSubmit={submit}>
            <div className="form-field">
              <label>Current Password</label>
              <input type="password" required value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} />
            </div>
            <div className="form-field">
              <label>New Password (min. 8 characters)</label>
              <input type="password" required minLength={8} value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} />
            </div>
            <button type="submit" className="btn btn-primary">Update Password</button>
          </form>
        </div>
      </div>
      {APPROVER_ROLES.includes(user.role) && <LeaveApprovalsPanel />}
      {resignationDialogOpen && (
        <div className="modal-overlay" role="presentation">
          <div className="modal-box" role="dialog" aria-modal="true" aria-labelledby="resignation-confirm-title">
            <h3 id="resignation-confirm-title">Confirm resignation request</h3>
            <p className="muted" style={{ fontSize: 13, margin: "12px 0 18px" }}>
              Your request will be sent to your manager and HR for review. If accepted, they will discuss and confirm your notice period and last working day with you. You can withdraw your resignation while it is pending or during your notice period.
            </p>
            <div className="form-actions">
              <button className="btn btn-outline" disabled={employmentBusy} onClick={() => setResignationDialogOpen(false)}>Cancel</button>
              <button className="btn btn-danger" disabled={employmentBusy} onClick={requestResignation}>
                {employmentBusy ? "Submitting…" : "Confirm resignation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
