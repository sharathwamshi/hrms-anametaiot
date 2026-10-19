import { useState } from "react";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import { useAuth } from "../context/AuthContext";
import { ROLE_LABELS, ROLES } from "../config/roles";
import LeaveApprovalsPanel from "../components/LeaveApprovalsPanel";

const APPROVER_ROLES = [ROLES.MANAGER, ROLES.HR_OPERATIONS, ROLES.SUPER_ADMIN];

export default function Profile() {
  const { user, roleLabel } = useAuth();
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

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
    </AppLayout>
  );
}
