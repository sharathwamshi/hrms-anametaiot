import ClockWidget from "./ClockWidget";
import AnnouncementFeedCard from "./AnnouncementFeedCard";

export default function DashboardTopWidgets({ summary, loading, error }) {
  return (
    <div className="two-col dashboard-top-widgets">
      <ClockWidget />
      <AnnouncementFeedCard
        announcements={summary?.recent_announcements}
        loading={loading}
        error={error}
      />
    </div>
  );
}
