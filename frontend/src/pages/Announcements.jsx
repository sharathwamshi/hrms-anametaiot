import { useCallback, useEffect, useMemo, useState } from "react";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Loader from "../components/Loader";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import {
  audienceCount,
  emptyAudiences,
  filterRecipients,
  isoToIstInput,
  istInputToIso,
  istInputValue,
  sortAnnouncementsByPublication,
  toggleAudience,
} from "../utils/officialAnnouncements.js";

const CATEGORIES = [
  ["general", "General"],
  ["hr", "HR"],
  ["policy", "Policy"],
  ["events", "Events"],
  ["operations", "Operations"],
];
const PRIORITIES = [
  ["normal", "Normal"],
  ["important", "Important"],
  ["urgent", "Urgent"],
];
function freshForm() {
  const now = new Date();
  return {
    title: "",
    message: "",
    category: "general",
    priority: "normal",
    audiences: emptyAudiences(),
    publishMode: "immediate",
    publishAt: istInputValue(now),
    durationUnit: "indefinite",
    durationValue: "1",
    customExpiry: istInputValue(new Date(now.getTime() + 24 * 60 * 60 * 1000)),
  };
}

function audienceChipList(audiences, users, roles, departments) {
  return [
    ...(audiences.everyone ? [{ key: "everyone", type: "everyone", value: "", label: "Everyone" }] : []),
    ...audiences.roles.map((value) => ({
      key: `role:${value}`,
      type: "role",
      value,
      label: roles.find((item) => item.value === value)?.label || value,
    })),
    ...audiences.department_ids.map((value) => ({
      key: `department:${value}`,
      type: "department",
      value,
      label: departments.find((item) => String(item.id) === String(value))?.name || `Department ${value}`,
    })),
    ...audiences.user_ids.map((value) => ({
      key: `user:${value}`,
      type: "user",
      value,
      label: users.find((item) => String(item.id) === String(value))?.full_name || `User ${value}`,
    })),
  ];
}

function displayTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : parsed.toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      dateStyle: "medium",
      timeStyle: "short",
    });
}

export default function Announcements() {
  const { user } = useAuth();
  const canManage = user.role !== ROLES.EMPLOYEE;
  const [items, setItems] = useState([]);
  const [directory, setDirectory] = useState({ users: [], roles: [], departments: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [form, setForm] = useState(freshForm);

  const loadAnnouncements = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await client.get("/announcements", {
        params: { scope: canManage ? "manage" : "visible", status: "all" },
      });
      setItems(data);
    } catch (requestError) {
      setError(requestError?.response?.data?.message || "Could not load announcements.");
    } finally {
      setLoading(false);
    }
  }, [canManage]);

  useEffect(() => {
    loadAnnouncements();
  }, [loadAnnouncements]);

  useEffect(() => {
    if (!canManage) return undefined;
    let active = true;
    client.get("/announcements/audiences")
      .then(({ data }) => {
        if (active) setDirectory(data);
      })
      .catch((requestError) => {
        if (active) setError(requestError?.response?.data?.message || "Could not load recipient options.");
      });
    return () => {
      active = false;
    };
  }, [canManage]);

  const filteredUsers = useMemo(
    () => filterRecipients(directory.users, search),
    [directory.users, search],
  );
  const selectedChips = useMemo(
    () => audienceChipList(form.audiences, directory.users, directory.roles, directory.departments),
    [form.audiences, directory],
  );
  const orderedItems = useMemo(() => sortAnnouncementsByPublication(items), [items]);
  const sections = useMemo(() => [
    { key: "active", title: "Active", items: orderedItems.filter((item) => item.status === "active") },
    ...(canManage
      ? [{ key: "scheduled", title: "Scheduled", items: orderedItems.filter((item) => item.status === "scheduled") }]
      : []),
    {
      key: "history",
      title: "History",
      items: orderedItems.filter((item) => item.status === "expired" || item.status === "history"),
    },
  ], [canManage, orderedItems]);

  const openCreate = () => {
    setEditingId(null);
    setForm(freshForm());
    setSearch("");
    setFormError("");
    setShowForm(true);
  };

  const openEdit = (announcement) => {
    setEditingId(announcement.id);
    setForm({
      title: announcement.title,
      message: announcement.message,
      category: announcement.category || "general",
      priority: announcement.priority || "normal",
      audiences: {
        ...emptyAudiences(),
        ...(announcement.audiences || {}),
      },
      publishMode: announcement.status === "scheduled" ? "scheduled" : "immediate",
      publishAt: isoToIstInput(announcement.publish_at),
      originalStatus: announcement.status,
      durationUnit: announcement.expires_at ? "custom" : "indefinite",
      durationValue: "1",
      customExpiry: isoToIstInput(announcement.expires_at),
    });
    setSearch("");
    setFormError("");
    setShowForm(true);
  };

  const changeAudience = (type, value) => {
    setForm((current) => ({
      ...current,
      audiences: toggleAudience(current.audiences, type, value),
    }));
  };

  const clearAudiences = () => {
    setForm((current) => ({ ...current, audiences: emptyAudiences() }));
  };

  const submit = async (event) => {
    event.preventDefault();
    setFormError("");
    if (audienceCount(form.audiences) === 0) {
      setFormError("Select at least one recipient.");
      return;
    }
    let payload;
    try {
      payload = {
        title: form.title,
        message: form.message,
        category: form.category,
        priority: form.priority,
        audiences: form.audiences,
        publish_at: form.publishMode === "scheduled"
          ? istInputToIso(form.publishAt)
          : editingId && form.originalStatus !== "scheduled"
            ? istInputToIso(form.publishAt)
            : null,
        duration_unit: form.durationUnit,
        duration_value: form.durationUnit === "indefinite" ? null : Number(form.durationValue),
        expires_at: form.durationUnit === "custom" ? istInputToIso(form.customExpiry) : null,
      };
    } catch (dateError) {
      setFormError(dateError.message);
      return;
    }

    setSaving(true);
    try {
      if (editingId) {
        await client.put(`/announcements/${editingId}`, payload);
      } else {
        await client.post("/announcements", payload);
      }
      setShowForm(false);
      setEditingId(null);
      await loadAnnouncements();
    } catch (requestError) {
      setFormError(requestError?.response?.data?.message || "Could not save this announcement.");
    } finally {
      setSaving(false);
    }
  };

  const deleteAnnouncement = async (announcement) => {
    if (!window.confirm(`Archive "${announcement.title}"? It will be removed from active feeds.`)) return;
    setError("");
    try {
      await client.delete(`/announcements/${announcement.id}`);
      await loadAnnouncements();
    } catch (requestError) {
      setError(requestError?.response?.data?.message || "Could not archive this announcement.");
    }
  };

  return (
    <AppLayout
      title="Announcements"
      subtitle="Company updates, important notices and team celebrations."
    >
      <section className="card announcement-history-card">
        <div className="card-title-row announcement-history-header">
          <div>
            <h3>Announcements</h3>
            <p className="muted">
              {canManage
                ? "Manage published, scheduled and expired announcements."
                : "View published announcements and their history."}
            </p>
          </div>
          {canManage && (
            <button type="button" className="btn btn-primary btn-sm" onClick={openCreate}>
              + Create Announcement
            </button>
          )}
        </div>
        {error && <div className="login-error" role="alert">{error}</div>}
        {loading ? <Loader /> : (
          <div className="announcement-history-sections">
            {sections.map((section) => (
              <section className="announcement-history-section" key={section.key} aria-labelledby={`announcement-section-${section.key}`}>
                <header className="announcement-history-section-header">
                  <h4 id={`announcement-section-${section.key}`}>{section.title}</h4>
                  <span>{section.items.length}</span>
                </header>
                {section.items.length ? (
                  <div className="announcement-history-list">
                    {section.items.map((announcement) => (
                      <article
                        className={`announcement-history-item ${announcement.priority}`}
                        key={`${announcement.kind}-${announcement.id}`}
                      >
                        <div className="announcement-history-item-header">
                          <div className="announcement-history-title">
                            {announcement.kind === "birthday" && <span aria-label="Birthday">🎂</span>}
                            <h4>{announcement.title}</h4>
                            {announcement.kind === "official" && (
                              <span className={`announcement-priority-badge ${announcement.priority}`}>
                                {announcement.priority}
                              </span>
                            )}
                          </div>
                          <span className={`announcement-status-badge ${announcement.status}`}>
                            {announcement.kind === "birthday" ? "Automatic" : announcement.status}
                          </span>
                        </div>
                        {announcement.kind === "birthday" ? (
                          <div className="announcement-birthday-people">
                            {announcement.employees.map((employee) => (
                              <div className="announcement-birthday-person" key={employee.id}>
                                {employee.avatar_url
                                  ? <img src={employee.avatar_url} alt="" />
                                  : <span className="announcement-avatar-fallback" aria-hidden="true">{employee.name.slice(0, 1)}</span>}
                                <span>
                                  <strong>{employee.name}</strong>
                                  {employee.designation && <small>{employee.designation}</small>}
                                </span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <>
                            <p className="announcement-history-message">{announcement.message}</p>
                            <div className="announcement-history-meta">
                              <span>From: {announcement.author_name}
                                {announcement.author_designation
                                  ? ` — ${announcement.author_designation}`
                                  : announcement.author_role_label
                                    ? ` — ${announcement.author_role_label}`
                                    : ""}
                              </span>
                              <span>{CATEGORIES.find(([value]) => value === announcement.category)?.[1] || announcement.category}</span>
                              <span>Published: {displayTime(announcement.publish_at)}</span>
                              <span>Expires: {displayTime(announcement.expires_at)}</span>
                            </div>
                            {canManage && (
                              <div className="announcement-item-actions">
                                <button type="button" className="btn btn-outline btn-sm" onClick={() => openEdit(announcement)}>Edit</button>
                                <button type="button" className="btn btn-outline btn-sm" onClick={() => deleteAnnouncement(announcement)}>Archive</button>
                              </div>
                            )}
                          </>
                        )}
                        {announcement.kind === "birthday" && (
                          <>
                            <p className="announcement-history-message">{announcement.message}</p>
                            <div className="announcement-history-meta">
                              <span>Automatic birthday announcement</span>
                              <span>Published: {displayTime(announcement.publish_at)}</span>
                            </div>
                          </>
                        )}
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="muted announcement-empty-history">No {section.title.toLowerCase()} announcements.</div>
                )}
              </section>
            ))}
          </div>
        )}
      </section>

      {showForm && (
        <div className="modal-overlay announcement-modal-overlay" onClick={() => !saving && setShowForm(false)}>
          <div
            className="modal-box announcement-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="announcement-form-title"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="announcement-modal-header">
              <h3 id="announcement-form-title">{editingId ? "Edit Announcement" : "Create Announcement"}</h3>
              <button type="button" className="announcement-modal-close" onClick={() => setShowForm(false)} disabled={saving} aria-label="Close form">×</button>
            </header>
            {formError && <div className="login-error" role="alert">{formError}</div>}
            <form className="announcement-form" onSubmit={submit}>
              <div className="form-grid">
                <div className="form-field">
                  <label htmlFor="announcement-title">Title</label>
                  <input id="announcement-title" required maxLength={200} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
                </div>
                <div className="form-field">
                  <label htmlFor="announcement-category">Category</label>
                  <select id="announcement-category" value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>
                    {CATEGORIES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                  </select>
                </div>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label htmlFor="announcement-priority">Priority</label>
                  <select id="announcement-priority" value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value })}>
                    {PRIORITIES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                  </select>
                </div>
                <div className="form-field">
                  <label htmlFor="announcement-publish-mode">Publish</label>
                  <select id="announcement-publish-mode" value={form.publishMode} onChange={(event) => setForm({ ...form, publishMode: event.target.value })}>
                    <option value="immediate">Publish immediately</option>
                    <option value="scheduled">Schedule for later</option>
                  </select>
                </div>
              </div>
              {form.publishMode === "scheduled" && (
                <div className="form-field">
                  <label htmlFor="announcement-publish-at">Publish date and time (Asia/Kolkata)</label>
                  <input id="announcement-publish-at" type="datetime-local" required value={form.publishAt} onChange={(event) => setForm({ ...form, publishAt: event.target.value })} />
                </div>
              )}
              <div className="form-field">
                <label htmlFor="announcement-message">Message</label>
                <textarea id="announcement-message" required rows={4} maxLength={20000} value={form.message} onChange={(event) => setForm({ ...form, message: event.target.value })} />
              </div>

              <fieldset className="announcement-audience-fieldset">
                <legend>Recipients</legend>
                <div className="recipient-selector-card">
                  <div className="recipient-selector-heading">
                    <h4>Select who should receive this announcement</h4>
                    <span className="recipient-count-badge">{audienceCount(form.audiences)} selected</span>
                  </div>
                  <label className="recipient-search" htmlFor="announcement-recipient-search">
                    <svg aria-hidden="true" viewBox="0 0 20 20" focusable="false">
                      <circle cx="8.5" cy="8.5" r="5.75" />
                      <path d="m13 13 4 4" />
                    </svg>
                    <input
                      id="announcement-recipient-search"
                      type="search"
                      aria-label="Search recipients"
                      placeholder="Search by name, role, designation, or department"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                    />
                  </label>
                  <div className="announcement-audience-options">
                    <label className={`announcement-audience-option${form.audiences.everyone ? " selected" : ""}`}>
                      <input type="checkbox" checked={form.audiences.everyone} onChange={() => changeAudience("everyone")} />
                      <span><strong>Entire company</strong><small>All active users</small></span>
                    </label>
                    {directory.roles.map((role) => (
                      <label className={`announcement-audience-option${form.audiences.roles.includes(role.value) ? " selected" : ""}`} key={role.value}>
                        <input type="checkbox" checked={form.audiences.roles.includes(role.value)} onChange={() => changeAudience("role", role.value)} />
                        <span><strong>{role.label}</strong><small>Role group</small></span>
                      </label>
                    ))}
                    {directory.departments.map((department) => (
                      <label className={`announcement-audience-option${form.audiences.department_ids.includes(Number(department.id)) ? " selected" : ""}`} key={department.id}>
                        <input type="checkbox" checked={form.audiences.department_ids.includes(Number(department.id))} onChange={() => changeAudience("department", department.id)} />
                        <span><strong>{department.name}</strong><small>Department</small></span>
                      </label>
                    ))}
                  </div>
                  <div className="recipient-user-list" aria-label="Available employees">
                    {filteredUsers.length ? filteredUsers.map((person) => {
                      const selected = form.audiences.user_ids.includes(Number(person.id));
                      return (
                        <label className={`recipient-user-row${selected ? " selected" : ""}`} key={person.id}>
                          <input type="checkbox" checked={selected} onChange={() => changeAudience("user", person.id)} aria-label={`Select ${person.full_name}`} />
                          <span className="recipient-user-copy">
                            <span className="recipient-user-name">{person.full_name}</span>
                            <span className="recipient-user-meta">
                              {[person.role_label, person.designation, person.department].filter(Boolean).join(" · ") || "No role or department"}
                            </span>
                          </span>
                        </label>
                      );
                    }) : <div className="recipient-list-empty">No employees match your search.</div>}
                  </div>
                  <section className="recipient-selected-section" aria-label="Selected recipients">
                    <div className="recipient-selected-heading">
                      <div><h5>Selected recipients</h5><span className="muted">{audienceCount(form.audiences)} selected</span></div>
                      <button type="button" className="recipient-clear-button" disabled={!audienceCount(form.audiences)} onClick={clearAudiences}>Clear all</button>
                    </div>
                    {selectedChips.length ? (
                      <div className="recipient-chips">
                        {selectedChips.map((chip) => (
                          <button type="button" className="recipient-chip" key={chip.key} onClick={() => changeAudience(chip.type, chip.value)} aria-label={`Remove ${chip.label}`}>
                            <span>{chip.label}</span><span className="recipient-chip-remove" aria-hidden="true">×</span>
                          </button>
                        ))}
                      </div>
                    ) : <p className="recipient-selection-empty">No recipients selected.</p>}
                  </section>
                </div>
              </fieldset>

              <div className="form-grid">
                <div className="form-field">
                  <label htmlFor="announcement-duration-unit">Display duration</label>
                  <select id="announcement-duration-unit" value={form.durationUnit} onChange={(event) => setForm({ ...form, durationUnit: event.target.value })}>
                    <option value="minutes">Minutes</option>
                    <option value="hours">Hours</option>
                    <option value="days">Days</option>
                    <option value="custom">Custom expiry date and time</option>
                    <option value="indefinite">No expiry (display until archived)</option>
                  </select>
                </div>
                {form.durationUnit === "custom" ? (
                  <div className="form-field">
                    <label htmlFor="announcement-expiry">Expiry date and time (Asia/Kolkata)</label>
                    <input id="announcement-expiry" type="datetime-local" required value={form.customExpiry} onChange={(event) => setForm({ ...form, customExpiry: event.target.value })} />
                  </div>
                ) : form.durationUnit === "indefinite" ? (
                  <div className="form-field announcement-no-expiry-note">
                    <p className="muted">This announcement remains visible until it is archived.</p>
                  </div>
                ) : (
                  <div className="form-field">
                    <label htmlFor="announcement-duration-value">Duration in {form.durationUnit}</label>
                    <input id="announcement-duration-value" type="number" min="0.01" max="365" step="any" required value={form.durationValue} onChange={(event) => setForm({ ...form, durationValue: event.target.value })} />
                  </div>
                )}
              </div>
              <div className="announcement-modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)} disabled={saving}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? "Saving…" : editingId ? "Save Changes" : "Create Announcement"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
