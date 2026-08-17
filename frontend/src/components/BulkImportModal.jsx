import { useState } from "react";
import client from "../api/client";

export default function BulkImportModal({ onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [linkDuplicates, setLinkDuplicates] = useState({});

  const runPreview = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await client.post("/recruitment/candidates/bulk-import/preview", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not process this file.");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      const duplicateRows = preview.duplicate_rows
        .filter((r) => linkDuplicates[r.row])
        .map((r) => ({ ...r, link_duplicate: true }));
      const rows = [...preview.valid_rows, ...duplicateRows];
      const { data } = await client.post("/recruitment/candidates/bulk-import/confirm", { rows });
      onImported(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Import failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ width: 560 }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 6 }}>Bulk Import Candidates</h3>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
          Columns expected: <code>name, email, phone, job, source</code>. Nothing is created until you review and confirm below.
        </p>
        {error && <div className="login-error">{error}</div>}

        {!preview && (
          <>
            <input type="file" accept=".xlsx,.xls,.csv" onChange={(e) => setFile(e.target.files[0])} />
            <div style={{ marginTop: 16, textAlign: "right" }}>
              <button className="btn btn-outline" onClick={onClose} style={{ marginRight: 8 }}>Cancel</button>
              <button className="btn btn-primary" disabled={!file || busy} onClick={runPreview}>
                {busy ? "Checking..." : "Preview"}
              </button>
            </div>
          </>
        )}

        {preview && (
          <>
            <div className="chip-row" style={{ marginBottom: 10 }}>
              <span className="chip green">{preview.summary.valid} valid</span>
              <span className="chip orange">{preview.summary.flagged} flagged</span>
              <span className="chip blue">{preview.summary.duplicates} duplicates</span>
            </div>

            {preview.valid_rows.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <strong style={{ fontSize: 12.5 }}>Ready to import</strong>
                {preview.valid_rows.map((r) => (
                  <div key={r.row} className="muted" style={{ fontSize: 12 }}>Row {r.row}: {r.name} — {r.email} — {r.job_title}</div>
                ))}
              </div>
            )}

            {preview.flagged_rows.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <strong style={{ fontSize: 12.5 }}>Flagged — will be skipped</strong>
                {preview.flagged_rows.map((r) => (
                  <div key={r.row} className="muted" style={{ fontSize: 12 }}>
                    Row {r.row}: {r.name} — {(r.reasons || []).join(", ")}
                  </div>
                ))}
              </div>
            )}

            {preview.duplicate_rows.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <strong style={{ fontSize: 12.5 }}>Possible duplicates — choose whether to link</strong>
                {preview.duplicate_rows.map((r) => (
                  <label key={r.row} style={{ display: "block", fontSize: 12, marginTop: 4 }}>
                    <input
                      type="checkbox"
                      checked={!!linkDuplicates[r.row]}
                      onChange={(e) => setLinkDuplicates({ ...linkDuplicates, [r.row]: e.target.checked })}
                      style={{ marginRight: 6 }}
                    />
                    Row {r.row}: {r.name} matches existing candidate #{r.existing_candidate.id} ({r.existing_candidate.full_name}) — link as new application
                  </label>
                ))}
              </div>
            )}

            <div style={{ marginTop: 16, textAlign: "right" }}>
              <button className="btn btn-outline" onClick={onClose} style={{ marginRight: 8 }}>Cancel</button>
              <button className="btn btn-primary" disabled={busy} onClick={confirm}>
                {busy ? "Importing..." : `Confirm Import (${preview.valid_rows.length + Object.values(linkDuplicates).filter(Boolean).length})`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
