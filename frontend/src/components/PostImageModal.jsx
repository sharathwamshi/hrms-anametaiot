import { useState } from "react";

export default function PostImageModal({ imageUrl, jobTitle, onClose }) {
  const [copied, setCopied] = useState(false);

  // imageUrl is a relative path like /static/uploads/job_posts/xyz.png —
  // resolve it against the current origin so the <img>, download, and share
  // link all point at wherever the app is actually running (dev proxy or
  // production host), never a hardcoded address.
  const absoluteUrl = new URL(imageUrl, window.location.origin).href;

  const canShare = typeof navigator !== "undefined" && !!navigator.share;

  const share = async () => {
    try {
      await navigator.share({
        title: `We're hiring — ${jobTitle}`,
        text: `Check out this opening: ${jobTitle}`,
        url: absoluteUrl,
      });
    } catch {
      // user cancelled the share sheet — nothing to do
    }
  };

  const copyLink = async () => {
    await navigator.clipboard.writeText(absoluteUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ width: 480 }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 4 }}>Job Post Image</h3>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>{jobTitle}</p>

        <img
          src={absoluteUrl}
          alt={`Job post for ${jobTitle}`}
          style={{ width: "100%", borderRadius: "var(--radius-md)", border: "1px solid var(--color-border)", display: "block" }}
        />

        <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
          <a className="btn btn-primary" href={absoluteUrl} download>
            Download
          </a>
          <button className="btn btn-outline" onClick={copyLink}>
            {copied ? "Link Copied" : "Copy Link"}
          </button>
          {canShare && (
            <button className="btn btn-outline" onClick={share}>
              Share
            </button>
          )}
          <a className="btn btn-outline" href={absoluteUrl} target="_blank" rel="noreferrer">
            Open Full Size
          </a>
        </div>

        <div style={{ textAlign: "right", marginTop: 16 }}>
          <button className="btn btn-outline" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
