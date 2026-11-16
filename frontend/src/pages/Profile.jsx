import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import { useAuth } from "../context/AuthContext";
import { ROLE_LABELS, ROLES } from "../config/roles";
import LeaveApprovalsPanel from "../components/LeaveApprovalsPanel";
import EmployeeFamilyPanel from "../components/EmployeeFamilyPanel";
import EmployeeDocumentsPanel from "../components/EmployeeDocumentsPanel";

const APPROVER_ROLES = [ROLES.MANAGER, ROLES.HR_OPERATIONS, ROLES.SUPER_ADMIN];

export default function Profile() {
  const { user, roleLabel, setUser } = useAuth();
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [employmentError, setEmploymentError] = useState("");
  const [profile, setProfile] = useState(null);
  const [savedProfile, setSavedProfile] = useState(null);
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [profileSuccess, setProfileSuccess] = useState("");
  const [uan, setUan] = useState(null);
  const [uanError, setUanError] = useState("");

  useEffect(() => {
    client.get(`/employees/${user.id}`)
      .then(({ data }) => setUser(data))
      .catch((err) => setEmploymentError(err?.response?.data?.message || "Could not load your employment status."));
  }, [setUser, user.id]);

  useEffect(() => {
    client.get("/profile/me")
      .then(({ data }) => {
        setProfile(data);
        setSavedProfile(data);
      })
      .catch((err) => setProfileError(err?.response?.data?.message || "Could not load your personal information."));
  }, []);

  useEffect(() => {
    client.get(`/employees/${user.id}/statutory`)
      .then(({ data }) => setUan(data.uan))
      .catch((err) => setUanError(err?.response?.data?.message || "Could not load your PF information."));
  }, [user.id]);

  const employmentStatusLabels = {
    active: "Active",
    resignation_pending: "Resignation in progress",
    notice_period: "Serving notice period",
    left: "Left the company",
  };
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

  const saveProfile = async (event) => {
    event.preventDefault();
    setProfileBusy(true);
    setProfileError("");
    setProfileSuccess("");
    try {
      const editableFields = [
        "full_name", "email", "phone", "date_of_birth", "gender",
        "residential_address", "permanent_address", "emergency_contact_name",
        "emergency_contact_relationship", "emergency_contact_phone",
      ];
      const payload = Object.fromEntries(editableFields.map((field) => [field, profile[field]]));
      const { data } = await client.patch("/profile/me", payload);
      setProfile(data.profile);
      setSavedProfile(data.profile);
      setUser(data.user);
      setEditingProfile(false);
      setProfileSuccess(data.message || "Profile updated successfully.");
    } catch (err) {
      setProfileError(err?.response?.data?.message || "Could not save your profile.");
    } finally {
      setProfileBusy(false);
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
            <div>
              <div className="muted" style={{ fontSize: 11.5 }}>UAN</div>
              <div>{uanError ? "Unavailable" : uan || "Not provided"}</div>
              {uanError && <div className="muted" role="alert" style={{ fontSize: 11 }}>{uanError}</div>}
            </div>
            <div><div className="muted" style={{ fontSize: 11.5 }}>Manager</div><div>{user.manager_name || "—"}</div></div>
            <div><div className="muted" style={{ fontSize: 11.5 }}>Date of Joining</div><div>{user.date_of_joining || "—"}</div></div>
            <div>
              <div className="muted" style={{ fontSize: 11.5 }}>Employment Status</div>
              <div>{employmentStatusLabels[user.employment_status || "active"] || "Active"}</div>
              {user.employment_status === "notice_period" && user.last_working_day && (
                <div className="muted" style={{ fontSize: 12 }}>
                  Last working day: {user.last_working_day}{user.notice_period_days != null ? ` · ${user.notice_period_days} day notice period` : ""}
                </div>
              )}
              {user.employment_status === "resignation_pending" && (
                <div className="muted" style={{ fontSize: 12 }}>Your manager or HR will review your request and confirm the notice period if accepted.</div>
              )}
            </div>
          </div>
          {employmentError && <div className="login-error" style={{ marginTop: 12 }}>{employmentError}</div>}
          {user.role !== ROLES.CONTRACT_EMPLOYEE && (
            <div style={{ marginTop: 16 }}>
              <Link className="btn btn-primary btn-sm" to="/resignation">Open Resignation</Link>
            </div>
          )}
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
      <section className="card section-gap">
        <div className="card-title-row">
          <h3>Personal Information</h3>
          {profile && !editingProfile && (
            <button
              type="button"
              className="btn btn-sm btn-outline"
              onClick={() => {
                setProfile(savedProfile);
                setEditingProfile(true);
                setProfileError("");
                setProfileSuccess("");
              }}
            >
              Edit
            </button>
          )}
        </div>
        <p className="muted" style={{ fontSize: 12.5 }}>
          You can update your contact and personal details here. Employee number, role, designation, department, manager, and compensation remain HR-managed.
        </p>
        {profileError && <div className="login-error" role="alert">{profileError}</div>}
        {profileSuccess && <p className="muted" role="status">{profileSuccess}</p>}
        {profile ? (
          <form onSubmit={saveProfile} className={!editingProfile ? "profile-readonly" : ""}>
            <div className="form-grid">
              <div className="form-field">
                <label>Full name</label>
                {editingProfile
                  ? <input required maxLength={150} value={profile.full_name || ""} onChange={(event) => setProfile({ ...profile, full_name: event.target.value })} />
                  : <div className="profile-value">{profile.full_name || "—"}</div>}
              </div>
              <div className="form-field">
                <label>Email address</label>
                {editingProfile
                  ? <input type="email" required maxLength={150} value={profile.email || ""} onChange={(event) => setProfile({ ...profile, email: event.target.value })} />
                  : <div className="profile-value">{profile.email || "—"}</div>}
              </div>
            </div>
            <div className="form-grid">
              <div className="form-field">
                <label>Phone number</label>
                {editingProfile
                  ? <input type="tel" maxLength={20} value={profile.phone || ""} onChange={(event) => setProfile({ ...profile, phone: event.target.value })} />
                  : <div className="profile-value">{profile.phone || "—"}</div>}
              </div>
              <div className="form-field">
                <label>Date of birth</label>
                {editingProfile
                  ? <input type="date" max={new Date().toISOString().slice(0, 10)} value={profile.date_of_birth || ""} onChange={(event) => setProfile({ ...profile, date_of_birth: event.target.value })} />
                  : <div className="profile-value">{profile.date_of_birth || "—"}</div>}
              </div>
            </div>
            <div className="form-field">
              <label>Gender (if applicable)</label>
              {editingProfile
                ? <input maxLength={30} value={profile.gender || ""} onChange={(event) => setProfile({ ...profile, gender: event.target.value })} />
                : <div className="profile-value">{profile.gender || "—"}</div>}
            </div>
            <div className="form-grid">
              <div className="form-field">
                <label>Residential address</label>
                {editingProfile
                  ? <textarea rows={3} maxLength={2000} value={profile.residential_address || ""} onChange={(event) => setProfile({ ...profile, residential_address: event.target.value })} />
                  : <div className="profile-value">{profile.residential_address || "—"}</div>}
              </div>
              <div className="form-field">
                <label>Permanent address</label>
                {editingProfile
                  ? <textarea rows={3} maxLength={2000} value={profile.permanent_address || ""} onChange={(event) => setProfile({ ...profile, permanent_address: event.target.value })} />
                  : <div className="profile-value">{profile.permanent_address || "—"}</div>}
              </div>
            </div>
            <h4>Emergency contact</h4>
            <div className="form-grid">
              <div className="form-field">
                <label>Contact name</label>
                {editingProfile
                  ? <input maxLength={150} value={profile.emergency_contact_name || ""} onChange={(event) => setProfile({ ...profile, emergency_contact_name: event.target.value })} />
                  : <div className="profile-value">{profile.emergency_contact_name || "—"}</div>}
              </div>
              <div className="form-field">
                <label>Relationship</label>
                {editingProfile
                  ? <input maxLength={100} value={profile.emergency_contact_relationship || ""} onChange={(event) => setProfile({ ...profile, emergency_contact_relationship: event.target.value })} />
                  : <div className="profile-value">{profile.emergency_contact_relationship || "—"}</div>}
              </div>
            </div>
            <div className="form-field">
              <label>Emergency contact phone</label>
              {editingProfile
                ? <input type="tel" maxLength={30} value={profile.emergency_contact_phone || ""} onChange={(event) => setProfile({ ...profile, emergency_contact_phone: event.target.value })} />
                : <div className="profile-value">{profile.emergency_contact_phone || "—"}</div>}
            </div>
            {editingProfile && (
              <div className="form-actions">
                <button
                  type="button"
                  className="btn btn-outline"
                  disabled={profileBusy}
                  onClick={() => {
                    setProfile(savedProfile);
                    setEditingProfile(false);
                    setProfileError("");
                    setProfileSuccess("");
                  }}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={profileBusy || !profile}>
                  {profileBusy ? "Saving…" : "Save changes"}
                </button>
              </div>
            )}
          </form>
        ) : !profileError && <p className="muted">Loading personal information…</p>}
      </section>
      <div className="two-col section-gap">
        <EmployeeFamilyPanel />
        <EmployeeDocumentsPanel />
      </div>
      {APPROVER_ROLES.includes(user.role) && <LeaveApprovalsPanel />}
    </AppLayout>
  );
}
