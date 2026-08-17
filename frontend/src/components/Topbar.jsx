import { useAuth } from "../context/AuthContext";

function initials(name = "") {
  return name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export default function Topbar({ title, subtitle }) {
  const { user, roleLabel, logout } = useAuth();

  return (
    <header className="topbar">
      <div className="topbar-title">
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="topbar-right">
        <span className="role-pill">{roleLabel}</span>
        <div className="user-chip">
          <div className="avatar-circle">{initials(user?.full_name)}</div>
          <div className="meta">
            <div className="name">{user?.full_name}</div>
            <div className="desg">{user?.designation || user?.employee_code}</div>
          </div>
        </div>
        <button className="logout-btn" onClick={logout}>
          Log out
        </button>
      </div>
    </header>
  );
}
