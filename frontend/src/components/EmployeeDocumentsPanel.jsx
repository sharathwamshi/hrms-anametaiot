import { useEffect, useState } from "react";
import client from "../api/client";

const DOC_TYPES = [
  ["education_10th", "10th Certificate / Marks Card"],
  ["education_12th", "12th Certificate / Marks Card"],
  ["diploma", "Diploma Certificate / Marks Card"],
  ["undergraduate_degree", "Undergraduate Degree Certificate"],
  ["undergraduate_marks", "Undergraduate Marks Card"],
  ["postgraduate_degree", "Postgraduate Degree Certificate"],
  ["postgraduate_marks", "Postgraduate Marks Card"],
  ["other_education", "Other Education Document"],
  ["pan", "PAN Card"],
  ["aadhaar", "Aadhaar Card"],
  ["government_id", "Other Government ID"],
  ["experience", "Experience Document"],
  ["relieving_letter", "Relieving Letter"],
  ["previous_offer", "Previous Offer Letter"],
  ["current_appointment", "Current Appointment Letter"],
  ["resume", "Resume"],
  ["professional_certification", "Professional Certification"],
  ["academic", "Academic Document"],
  ["other", "Other Document"],
];

const VERIFICATION_PRESENTATION = {
  rejected: { label: "Rejected · Action needed", badge: "badge-danger", row: "document-verification-rejected" },
  verified: { label: "Approved", badge: "badge-success", row: "document-verification-verified" },
  pending: { label: "Pending", badge: "badge-warning", row: "document-verification-pending" },
};

export default function EmployeeDocumentsPanel({ employeeId, canUpload = true, canReview = false }) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [docType, setDocType] = useState("education_10th");
  const [title, setTitle] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => () => {
    if (preview?.url) URL.revokeObjectURL(preview.url);
  }, [preview]);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await client.get("/documents", {
        params: employeeId ? { user_id: employeeId } : undefined,
      });
      setDocuments(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load employee documents.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [employeeId]);

  const upload = async (event) => {
    event.preventDefault();
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const payload = new FormData();
      payload.append("doc_type", docType);
      payload.append("title", title || file.name);
      payload.append("file", file);
      if (employeeId) payload.append("user_id", String(employeeId));
      await client.post("/documents", payload, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setFile(null);
      setTitle("");
      event.target.reset();
      setSuccess("Document uploaded. It will remain pending until HR verifies it.");
      await load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not upload this document.");
    } finally {
      setBusy(false);
    }
  };

  const openDocument = async (document) => {
    setError("");
    setPreviewLoading(true);
    try {
      const { data } = await client.get(document.file_path, { responseType: "blob" });
      setPreview({
        document,
        url: URL.createObjectURL(data),
        mimeType: data.type || document.mime_type || "",
      });
    } catch (err) {
      setError(err?.response?.data?.message || "Could not open this document.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const closePreview = () => {
    setPreview((current) => {
      if (current?.url) URL.revokeObjectURL(current.url);
      return null;
    });
  };

  const downloadPreview = () => {
    if (!preview) return;
    const link = window.document.createElement("a");
    link.href = preview.url;
    link.download = preview.document.original_filename || preview.document.title;
    window.document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const remove = async (documentId) => {
    if (!window.confirm("Remove this document?")) return;
    setError("");
    try {
      await client.delete(`/documents/${documentId}`);
      await load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not remove this document.");
    }
  };

  const updateVerification = async (documentId, status, currentNote) => {
    setError("");
    try {
      const note = window.prompt("Optional verification note", currentNote || "");
      if (note === null) return;
      await client.patch(`/documents/${documentId}/verification`, { status, note });
      await load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update verification status.");
    }
  };

  return (
    <section id={!employeeId ? "documents" : undefined} className="card" aria-labelledby={`employee-documents-${employeeId || "me"}`}>
      <div className="card-title-row">
        <h3 id={`employee-documents-${employeeId || "me"}`}>Documents</h3>
      </div>
      {error && <div className="login-error" role="alert">{error}</div>}
      {success && <p role="status" className="muted">{success}</p>}
      {canUpload && (
        <form onSubmit={upload} style={{ marginBottom: 18 }}>
          <div className="form-grid">
            <div className="form-field">
              <label>Document type</label>
              <select value={docType} onChange={(event) => setDocType(event.target.value)}>
                {DOC_TYPES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label>Title</label>
              <input value={title} maxLength={150} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Bachelor of Engineering certificate" />
            </div>
          </div>
          <div className="form-field">
            <label>File (PDF, JPG, PNG, DOC or DOCX; max. 10 MB)</label>
            <input
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </div>
          <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
            {busy ? "Uploading…" : "Upload document"}
          </button>
        </form>
      )}
      {loading ? <p className="muted">Loading documents…</p> : documents.length === 0 ? (
        <p className="muted">No documents uploaded yet.</p>
      ) : (
        <div style={{ display: "grid", gap: 8 }}>
          {documents.map((document) => {
            const verification = VERIFICATION_PRESENTATION[document.verification_status] || VERIFICATION_PRESENTATION.pending;
            return (
              <div key={document.id} className={`flex-between document-verification-row ${verification.row}`} style={{ gap: 12, borderTop: "1px solid var(--color-border)", paddingTop: 9 }}>
                <div>
                  <button
                    className="btn btn-sm btn-outline"
                    disabled={previewLoading}
                    onClick={() => openDocument(document)}
                    style={{ padding: "2px 6px", textAlign: "left" }}
                  >
                    {previewLoading ? "Loading…" : `View ${document.title}`}
                  </button>
                  <div className="muted" style={{ fontSize: 11.5 }}>
                    {document.doc_type_label} · <span className={`badge ${verification.badge}`}>{verification.label}</span>
                    {document.file_size ? ` · ${(document.file_size / 1024).toFixed(0)} KB` : ""}
                  </div>
                  {document.verification_note && (
                    <div className={document.verification_status === "rejected" ? "document-rejection-note" : "muted"} style={{ fontSize: 11.5 }}>
                      {document.verification_note}
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  {canReview && (
                    <select
                      aria-label={`Verification status for ${document.title}`}
                      value={document.verification_status}
                      onChange={(event) => updateVerification(document.id, event.target.value, document.verification_note)}
                    >
                      <option value="pending">Pending</option>
                      <option value="verified">Verified</option>
                      <option value="rejected">Rejected</option>
                    </select>
                  )}
                  {(canUpload || !employeeId) && (
                    <button className="btn btn-sm btn-outline" onClick={() => remove(document.id)}>Remove</button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {preview && (
        <div className="modal-overlay" role="presentation" onClick={closePreview}>
          <div
            className="modal-box"
            role="dialog"
            aria-modal="true"
            aria-label={`Preview ${preview.document.title}`}
            onClick={(event) => event.stopPropagation()}
            style={{ width: "min(1000px, 94vw)", height: "min(85vh, 900px)", display: "flex", flexDirection: "column" }}
          >
            <div className="flex-between" style={{ gap: 12, marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>{preview.document.title}</h3>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-sm btn-outline" onClick={downloadPreview}>Download</button>
                <button className="btn btn-sm btn-outline" onClick={closePreview}>Close</button>
              </div>
            </div>
            {preview.mimeType.startsWith("image/") ? (
              <div style={{ flex: 1, minHeight: 0, display: "grid", placeItems: "center", overflow: "auto" }}>
                <img
                  src={preview.url}
                  alt={preview.document.title}
                  style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
                />
              </div>
            ) : preview.mimeType === "application/pdf" ? (
              <iframe
                title={`Preview ${preview.document.title}`}
                src={preview.url}
                style={{ flex: 1, width: "100%", minHeight: 0, border: 0 }}
              />
            ) : (
              <div style={{ flex: 1, display: "grid", placeContent: "center", textAlign: "center", gap: 12 }}>
                <p className="muted">This file type cannot be previewed in the browser. Download it to view the document.</p>
                <button className="btn btn-primary" onClick={downloadPreview}>Download document</button>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
