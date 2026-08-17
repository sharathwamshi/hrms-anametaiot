const MAP = {
  present: "badge-success",
  approved: "badge-success",
  active: "badge-success",
  paid: "badge-success",
  hired: "badge-success",
  selected: "badge-success",
  open: "badge-success",
  verified: "badge-success",
  auto_validated: "badge-success",
  accepted: "badge-success",
  completed: "badge-success",
  yes: "badge-success",

  pending: "badge-warning",
  half_day: "badge-warning",
  processed: "badge-warning",
  screening: "badge-warning",
  mock_test: "badge-warning",
  interview: "badge-warning",
  offer: "badge-warning",
  on_hold: "badge-warning",
  needs_review: "badge-warning",
  pending_approval: "badge-warning",
  sent: "badge-warning",
  neutral: "badge-warning",
  in_progress: "badge-warning",
  assigned: "badge-warning",

  absent: "badge-danger",
  rejected: "badge-danger",
  closed: "badge-danger",
  declined: "badge-danger",
  no: "badge-danger",
  expired: "badge-danger",

  draft: "badge-neutral",
  drafted: "badge-neutral",
  regularized: "badge-neutral",
  applied: "badge-neutral",
  cancelled: "badge-neutral",
  unverified: "badge-neutral",
};

export default function Badge({ status }) {
  const cls = MAP[status] || "badge-neutral";
  return <span className={`badge ${cls}`}>{(status || "").replace(/_/g, " ")}</span>;
}
