export default function StatCard({ label, value, icon, color = "blue" }) {
  return (
    <div className="stat-card">
      <div>
        <div className="label">{label}</div>
        <div className="value">{value}</div>
      </div>
      <div className={`icon-wrap chip-${color}`}>{icon}</div>
    </div>
  );
}
