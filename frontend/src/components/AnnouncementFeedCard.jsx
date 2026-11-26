import { Link } from "react-router-dom";
import { parseUtc } from "../utils/datetime";
import { selectDashboardAnnouncements } from "../utils/officialAnnouncements.js";

function localTime(value) {
  const parsed = parseUtc(value);
  return parsed
    ? parsed.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" })
    : "";
}

export default function AnnouncementFeedCard({ announcements, loading, error }) {
  const latestAnnouncements = selectDashboardAnnouncements(announcements || []);

  return (
    <div className="card announcement-feed-card">
      <div className="card-title-row">
        <h3>Announcements</h3>
        <Link to="/announcements" className="btn btn-outline btn-sm">View All</Link>
      </div>
      {loading ? (
        <div className="muted" role="status">Loading announcements…</div>
      ) : error ? (
        <div className="muted" role="status">Announcements could not be loaded.</div>
      ) : latestAnnouncements.length ? (
        <div className="announcement-feed-list">
          {latestAnnouncements.map((announcement) => (
            <article
              className={`announcement-feed-item${announcement.priority === "urgent" ? " urgent" : ""}${announcement.priority === "important" ? " important" : ""}`}
              key={`${announcement.kind}-${announcement.id}`}
            >
              <div className="announcement-feed-heading">
                <div className="announcement-feed-title">
                  {announcement.kind === "birthday" && <span aria-label="Birthday" title="Birthday">🎂</span>}
                  <strong>{announcement.title}</strong>
                </div>
                {announcement.kind !== "birthday" && announcement.priority !== "normal" && (
                  <span className={`announcement-priority-badge ${announcement.priority}`}>
                    {announcement.priority}
                  </span>
                )}
              </div>
              {announcement.kind === "birthday" && (
                <div className="announcement-birthday-people">
                  {announcement.employees.map((employee) => (
                    <div className="announcement-birthday-person" key={employee.id}>
                      {employee.avatar_url ? (
                        <img src={employee.avatar_url} alt="" />
                      ) : (
                        <span className="announcement-avatar-fallback" aria-hidden="true">
                          {employee.name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase()}
                        </span>
                      )}
                      <span>
                        <strong>{employee.name}</strong>
                        {employee.designation && <small>{employee.designation}</small>}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <p>{announcement.message}</p>
              <div className="announcement-feed-meta">
                {announcement.kind === "birthday" ? "Automatic birthday announcement" : (
                  <>From: {announcement.author_name}
                    {announcement.author_designation
                      ? ` — ${announcement.author_designation}`
                      : announcement.author_role_label
                        ? ` — ${announcement.author_role_label}`
                        : ""}
                  </>
                )}
                {announcement.publish_at && <> · {localTime(announcement.publish_at)}</>}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="muted">No announcements or birthdays to show.</div>
      )}
    </div>
  );
}
