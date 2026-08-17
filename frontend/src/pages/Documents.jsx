import { useEffect, useState } from "react";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Loader from "../components/Loader";

const DOC_TYPES = [
  { value: "academic", label: "Academic Document" },
  { value: "experience", label: "Experience Document" },
  { value: "relieving_letter", label: "Relieving Letter" },
];

export default function Documents() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [docType, setDocType] = useState("academic");
  const [title, setTitle] = useState("");
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);

  const load = async () => {
    setLoading(true);
    const { data } = await client.get("/documents");
    setDocs(data);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const upload = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }
    setError("");
    setUploading(true);
    try {
      const form = new FormData();
      form.append("doc_type", docType);
      form.append("title", title || file.name);
      form.append("file", file);
      await client.post("/documents", form, { headers: { "Content-Type": "multipart/form-data" } });
      setTitle("");
      setFile(null);
      document.getElementById("doc-file-input").value = "";
      load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not upload this document.");
    } finally {
      setUploading(false);
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Remove this document?")) return;
    await client.delete(`/documents/${id}`);
    load();
  };

  const grouped = DOC_TYPES.map((t) => ({
    ...t,
    items: docs.filter((d) => d.doc_type === t.value),
  }));

  return (
    <AppLayout title="Documents" subtitle="Your academic documents, experience letters, and relieving letter.">
      <div className="two-col">
        <div className="card">
          <div className="card-title-row"><h3>Upload a Document</h3></div>
          {error && <div className="login-error">{error}</div>}
          <form onSubmit={upload}>
            <div className="form-field">
              <label>Document Type</label>
              <select value={docType} onChange={(e) => setDocType(e.target.value)}>
                {DOC_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label>Title (optional)</label>
              <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. B.Tech Marksheet" />
            </div>
            <div className="form-field">
              <label>File</label>
              <input id="doc-file-input" type="file" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" onChange={(e) => setFile(e.target.files[0])} />
            </div>
            <button className="btn btn-primary" disabled={uploading} type="submit">
              {uploading ? "Uploading..." : "Upload"}
            </button>
          </form>
        </div>

        <div className="card">
          <div className="card-title-row"><h3>Your Documents</h3></div>
          {loading ? <Loader /> : (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {grouped.map((group) => (
                <div key={group.value}>
                  <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--color-text-muted)", marginBottom: 6 }}>
                    {group.label} ({group.items.length})
                  </div>
                  {group.items.length === 0 && <div className="muted" style={{ fontSize: 12.5 }}>None uploaded yet.</div>}
                  {group.items.map((d) => (
                    <div key={d.id} className="flex-between" style={{ padding: "6px 0", borderBottom: "1px solid var(--color-border)" }}>
                      <a href={d.file_path} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>{d.title}</a>
                      <button className="btn btn-sm btn-outline" onClick={() => remove(d.id)}>Remove</button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
