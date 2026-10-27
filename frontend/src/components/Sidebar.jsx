import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { NAV_BY_ROLE, NAV_ITEMS } from "../config/roles";

const STORAGE_KEY = "hrms_sidebar_collapsed";

export default function Sidebar() {
  const { user, roleLabel, logout } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(STORAGE_KEY) === "1");

  if (!user) return null;

  const items = (NAV_BY_ROLE[user.role] || ["dashboard", "profile"]).map((key) => ({
    key,
    ...NAV_ITEMS[key],
  }));

  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      return next;
    });
  };

  return (
    <aside className={`sidebar${collapsed ? " collapsed" : ""}`}>
      <div className="sidebar-brand">
        <div className="mark">
          <img src="/logo.png" alt="Ana Meta IoT" />
        </div>
        <div className="name">
          AnametaIOT HRMS
          <small>Human Resource Management</small>
        </div>
        <button
          className="sidebar-toggle-btn"
          onClick={toggle}
          title={collapsed ? "Expand menu" : "Collapse menu"}
          aria-label={collapsed ? "Expand menu" : "Collapse menu"}
        >
          {"\u2039"}
        </button>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-section-label">{collapsed ? "\u2022" : roleLabel}</div>
        {items.map((item) => (
          <NavLink
            key={item.key}
            to={item.path}
            end={item.path === "/"}
            className={() => {
              const [path, search = ""] = item.path.split("?");
              const isActive = location.pathname === path && location.search.slice(1) === search;
              return `sidebar-link${isActive ? " active" : ""}`;
            }}
            title={collapsed ? item.label : undefined}
          >
            <span className="icon">{item.icon}</span>
            <span className="label">{item.label}</span>
          </NavLink>
        ))}
        <button type="button" className="sidebar-link sidebar-logout-link" onClick={logout}>
          <span className="icon">{"\u21AA"}</span>
          <span className="label">Logout</span>
        </button>
      </nav>

      <div className="sidebar-footer">
        {collapsed ? <strong>+vG</strong> : <>Powered by <strong>+veGroww</strong></>}
      </div>
    </aside>
  );
}
