import { useState } from "react";

const PREVIEW_LENGTH = 100;

export default function LeaveReasonPreview({ reason }) {
  const [expanded, setExpanded] = useState(false);
  const text = reason == null ? "" : String(reason);
  if (!text) return <span className="muted">—</span>;
  if (text.length <= PREVIEW_LENGTH) return <span>{text}</span>;
  return (
    <span className="leave-reason-preview">
      {expanded ? text : `${text.slice(0, PREVIEW_LENGTH).trimEnd()}…`}{" "}
      <button type="button" className="leave-reason-toggle" onClick={() => setExpanded((value) => !value)}>
        {expanded ? "View Less" : "View More"}
      </button>
    </span>
  );
}
