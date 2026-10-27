import { parseUtc } from "../utils/datetime";
import ClockWidget from "./ClockWidget";

export default function DashboardTopWidgets({ summary, loading, error }) {
  return (
    <div className="two-col dashboard-top-widgets">
      <ClockWidget />
      <div className="card">
        <div className="card-title-row">
          <h3>Announcements</h3>
        </div>
        {loading ? (
          <div className="muted" style={{ fontSize: 13 }}>Loading announcements…</div>
        ) : error ? (
          <div className="muted" role="status" style={{ fontSize: 13 }}>Announcements could not be loaded.</div>
        ) : summary?.recent_announcements?.length ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {summary.recent_announcements.map((announcement) => (
              <div key={announcement.id} style={{ borderBottom: "1px solid var(--color-border)", paddingBottom: 12 }}>
                <div style={{ fontWeight: 700, fontSize: 13.5 }}>{announcement.title}</div>
                <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>{announcement.body}</div>
                <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                  {announcement.author_name} &middot; {parseUtc(announcement.created_at).toLocaleDateString("en-IN")}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted" style={{ fontSize: 13 }}>No announcements yet.</div>
        )}
      </div>
    </div>
  );
}
