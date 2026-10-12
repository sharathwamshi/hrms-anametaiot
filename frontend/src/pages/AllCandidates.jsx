import { useEffect, useState } from "react";
import ExportButton from "../components/ExportButton";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import CandidateDetailModal from "../components/CandidateDetailModal";
import { parseUtc } from "../utils/datetime";
import { downloadFile } from "../utils/download";
import { fetchRecruiterOptions } from "../utils/recruiters";

export default function AllCandidates() {
  const [candidates, setCandidates] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [recruiters, setRecruiters] = useState([]);
  const [recruiterId, setRecruiterId] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedCandidateId, setSelectedCandidateId] = useState(null);
  const [q, setQ] = useState("");
  const [stage, setStage] = useState("");
  const [jobId, setJobId] = useState("");
  const [source, setSource] = useState("");
  const [requisitionType, setRequisitionType] = useState("");
  const [sort, setSort] = useState("created_desc");

  const load = async () => {
    setLoading(true);
    const params = { sort };
    if (q) params.q = q;
    if (stage) params.stage = stage;
    if (jobId) params.job_id = jobId;
    if (source) params.source = source;
    if (requisitionType) params.requisition_type = requisitionType;
    if (recruiterId) params.recruiter_id = recruiterId;
    const { data } = await client.get("/recruitment/candidates", { params });
    setCandidates(data);
    setLoading(false);
  };

  useEffect(() => {
    client.get("/recruitment/jobs").then(({ data }) => setJobs(data));
    fetchRecruiterOptions().then(setRecruiters);
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 300); // debounce search-as-you-type
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, stage, jobId, source, requisitionType, recruiterId, sort]);

  const exportCsv = () => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (stage) params.set("stage", stage);
    if (jobId) params.set("job_id", jobId);
    if (source) params.set("source", source);
    if (requisitionType) params.set("requisition_type", requisitionType);
    if (recruiterId) params.set("recruiter_id", recruiterId);
    params.set("sort", sort);
    downloadFile(`/recruitment/candidates/export?${params.toString()}`, "candidates_export.csv");
  };

  const initials = (name = "") => name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();

  return (
    <AppLayout title="All Candidates" subtitle="Every candidate across every job posting, searchable and sortable.">
      <div className="card">
        <div className="card-title-row">
          <h3>All Candidates</h3>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="muted" style={{ fontSize: 12 }}>{candidates.length} result(s)</span>
            <ExportButton filename="All_Candidates" />
            <button className="btn btn-sm btn-outline" onClick={exportCsv}>Download CSV</button>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          <input
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search name, email, or phone..."
            style={{ flex: 1, minWidth: 220, border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}
          />
          <select value={requisitionType} onChange={(e) => setRequisitionType(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
            <option value="">Internal + Client</option>
            <option value="internal">Internal Hiring only</option>
            <option value="client">Client Requisitions only</option>
          </select>
          {recruiters.length > 0 && (
            <select value={recruiterId} onChange={(e) => setRecruiterId(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
              <option value="">All recruiters</option>
              {recruiters.map((r) => <option key={r.id} value={r.id}>{r.name}{r.active ? "" : " (inactive)"}</option>)}
            </select>
          )}
          <select value={jobId} onChange={(e) => setJobId(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
            <option value="">All jobs</option>
            {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}{j.requisition_type === "client" ? ` (${j.vendor_name})` : ""}</option>)}
          </select>
          <select value={stage} onChange={(e) => setStage(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
            <option value="">All stages</option>
            {["applied", "screening", "mock_test", "interview", "offer", "hired", "rejected"].map((s) => (
              <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
            ))}
          </select>
          <select value={source} onChange={(e) => setSource(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
            <option value="">All sources</option>
            <option value="referral">Referral</option>
            <option value="naukri">Naukri</option>
            <option value="linkedin">LinkedIn</option>
            <option value="walk-in">Walk-in</option>
          </select>
          <select value={sort} onChange={(e) => setSort(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
            <option value="created_desc">Newest first</option>
            <option value="created_asc">Oldest first</option>
            <option value="name_asc">Name A–Z</option>
            <option value="name_desc">Name Z–A</option>
            <option value="stage_asc">Stage</option>
            <option value="job_asc">Job title</option>
          </select>
        </div>

        {loading ? <Loader /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Candidate</th><th>Job</th><th>Recruiter</th><th>Contact</th><th>Location</th>
                  <th>Skills</th><th>Source</th><th>Stage</th><th>Level</th><th>Validation</th><th>Added</th>
                </tr>
              </thead>
              <tbody>
                {candidates.length === 0 && <tr className="empty-row"><td colSpan={11}>No candidates match these filters.</td></tr>}
                {candidates.map((c) => (
                  <tr key={c.id} onClick={() => setSelectedCandidateId(c.id)} style={{ cursor: "pointer" }}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div className="avatar-circle" style={{ width: 28, height: 28, fontSize: 11 }}>{initials(c.full_name)}</div>
                        <strong>{c.full_name}</strong>
                      </div>
                    </td>
                    <td>
                      {c.job_title || "—"}
                      {c.requisition_type === "client" && <div className="chip orange" style={{ marginTop: 3, display: "inline-block" }}>{c.vendor_name}</div>}
                    </td>
                    <td>{c.recruiter_name || "—"}</td>
                    <td className="muted" style={{ fontSize: 12 }}>{c.email || "—"}<br />{c.phone || "—"}</td>
                    <td>
                      {c.location || "—"}
                      {c.open_to_relocation && <div className="chip green" style={{ marginTop: 3, display: "inline-block" }}>Relocation OK</div>}
                    </td>
                    <td>
                      <div className="chip-row">
                        {(c.skills || []).slice(0, 3).map((s) => <span key={s} className="chip blue">{s}</span>)}
                        {(c.skills || []).length > 3 && <span className="chip">+{c.skills.length - 3}</span>}
                      </div>
                    </td>
                    <td>{c.source || "—"}</td>
                    <td><Badge status={c.stage} /></td>
                    <td>{c.current_level ? <span className="chip orange">{c.current_level}</span> : "—"}</td>
                    <td><Badge status={c.validation_status} /></td>
                    <td className="muted" style={{ fontSize: 12 }}>{parseUtc(c.created_at).toLocaleDateString("en-IN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {selectedCandidateId && (
          <CandidateDetailModal
            candidateId={selectedCandidateId}
            onClose={() => setSelectedCandidateId(null)}
            onChanged={load}
          />
        )}
      </div>
    </AppLayout>
  );
}
