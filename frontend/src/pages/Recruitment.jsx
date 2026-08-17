import { useEffect, useState, useCallback } from "react";
import client from "../api/client";
import { parseUtc } from "../utils/datetime";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import BulkImportModal from "../components/BulkImportModal";
import CandidateDetailModal from "../components/CandidateDetailModal";
import PostImageModal from "../components/PostImageModal";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";

const TABS_BY_ROLE = {
  [ROLES.HR_RECRUITER]: ["jobs", "candidates", "mocktests"],
  [ROLES.HR_OPERATIONS]: ["jobs", "candidates", "mocktests", "feed", "performance"],
  [ROLES.MANAGER]: ["jobs", "candidates", "feed", "performance"],
};

export default function Recruitment() {
  const { user } = useAuth();
  const canRecruit = [ROLES.HR_RECRUITER, ROLES.HR_OPERATIONS].includes(user.role);
  const canApprove = [ROLES.MANAGER, ROLES.HR_OPERATIONS].includes(user.role);
  const tabs = TABS_BY_ROLE[user.role] || ["jobs"];
  const [tab, setTab] = useState(tabs[0]);

  return (
    <AppLayout title="Recruitment" subtitle="Job postings, candidate pipeline, screening, mock tests, and offers.">
      <div className="tag-list section-gap">
        {tabs.map((t) => (
          <button key={t} className={`btn btn-sm ${tab === t ? "btn-primary" : "btn-outline"}`} onClick={() => setTab(t)}>
            {{ jobs: "Jobs", candidates: "Candidates", mocktests: "Mock Tests", feed: "Newly Added Feed", performance: "Recruiter Performance" }[t]}
          </button>
        ))}
      </div>

      {tab === "jobs" && <JobsTab canRecruit={canRecruit} canApprove={canApprove} />}
      {tab === "candidates" && <CandidatesTab canRecruit={canRecruit} />}
      {tab === "mocktests" && <MockTestsTab />}
      {tab === "feed" && <FeedTab />}
      {tab === "performance" && <PerformanceTab user={user} />}
    </AppLayout>
  );
}

// ============================================================================
// Jobs
// ============================================================================

function JobsTab({ canRecruit, canApprove }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", employment_type: "full_time", openings: 1, salary_min: "", salary_max: "", priority: "standard", description: "" });
  const [error, setError] = useState("");
  const [imageModal, setImageModal] = useState(null);

  const load = async () => {
    setLoading(true);
    const { data } = await client.get("/recruitment/jobs");
    setJobs(data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const createJob = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await client.post("/recruitment/jobs", form);
      setShowForm(false);
      setForm({ title: "", employment_type: "full_time", openings: 1, salary_min: "", salary_max: "", priority: "standard", description: "" });
      load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not create job posting.");
    }
  };

  const approve = async (id) => { await client.post(`/recruitment/jobs/${id}/approve`); load(); };
  const reject = async (id) => { await client.post(`/recruitment/jobs/${id}/reject`); load(); };
  const clone = async (id) => { await client.post(`/recruitment/jobs/${id}/clone`); load(); };

  const generateImage = async (id, title) => {
    const { data } = await client.post(`/recruitment/jobs/${id}/generate-post-image`, {});
    setImageModal({ url: data.post_image_url, title });
    load();
  };

  const postSocial = async (id) => {
    const { data } = await client.post(`/recruitment/jobs/${id}/post-social`);
    alert(`LinkedIn: ${data.linkedin.message}\n\nNaukri: ${data.naukri.message}`);
  };

  return (
    <div className="card">
      <div className="card-title-row">
        <h3>Job Postings</h3>
        {canRecruit && <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>+ New Requisition</button>}
      </div>
      {loading ? <Loader /> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {jobs.map((j) => (
            <div key={j.id} style={{ border: "1px solid var(--color-border)", borderRadius: 10, padding: 14 }}>
              <div className="flex-between">
                <div>
                  <strong>{j.title}</strong> <span className="muted">({j.department || "Unassigned"})</span>
                  <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>
                    {j.openings} opening(s) &middot; {j.candidate_count} candidate(s) &middot; priority: {j.priority}
                    {j.salary_min && ` · ₹${j.salary_min.toLocaleString("en-IN")}–₹${j.salary_max.toLocaleString("en-IN")}`}
                  </div>
                </div>
                <Badge status={j.requisition_status} />
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
                {j.requisition_status === "pending_approval" && canApprove && (
                  <>
                    <button className="btn btn-sm btn-success" onClick={() => approve(j.id)}>Approve</button>
                    <button className="btn btn-sm btn-danger" onClick={() => reject(j.id)}>Hold</button>
                  </>
                )}
                {canRecruit && (
                  <>
                    <button className="btn btn-sm btn-outline" onClick={() => clone(j.id)}>Clone</button>
                    <button className="btn btn-sm btn-outline" onClick={() => generateImage(j.id, j.title)}>Generate Post Image</button>
                    <button className="btn btn-sm btn-outline" onClick={() => postSocial(j.id)}>Post to LinkedIn/Naukri</button>
                  </>
                )}
              </div>
              {j.post_image_url && (
                <button
                  className="btn btn-sm btn-outline"
                  style={{ marginTop: 8 }}
                  onClick={() => setImageModal({ url: j.post_image_url, title: j.title })}
                >
                  View Post Image
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>New Job Requisition</h3>
            {error && <div className="login-error">{error}</div>}
            <form onSubmit={createJob}>
              <div className="form-field">
                <label>Title</label>
                <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Employment Type</label>
                  <select value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value })}>
                    <option value="full_time">Full-time</option>
                    <option value="contract">Contract</option>
                  </select>
                </div>
                <div className="form-field">
                  <label>Openings</label>
                  <input type="number" min={1} value={form.openings} onChange={(e) => setForm({ ...form, openings: Number(e.target.value) })} />
                </div>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Salary Min</label>
                  <input type="number" value={form.salary_min} onChange={(e) => setForm({ ...form, salary_min: e.target.value })} />
                </div>
                <div className="form-field">
                  <label>Salary Max</label>
                  <input type="number" value={form.salary_max} onChange={(e) => setForm({ ...form, salary_max: e.target.value })} />
                </div>
              </div>
              <div className="form-field">
                <label>Priority</label>
                <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                  <option value="standard">Standard</option>
                  <option value="urgent">Urgent</option>
                </select>
              </div>
              <div className="form-field">
                <label>Description</label>
                <textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Submit for Approval</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {imageModal && (
        <PostImageModal
          imageUrl={imageModal.url}
          jobTitle={imageModal.title}
          onClose={() => setImageModal(null)}
        />
      )}
    </div>
  );
}

// ============================================================================
// Candidates
// ============================================================================

function CandidatesTab({ canRecruit }) {
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [showBulk, setShowBulk] = useState(false);
  const [selectedCandidateId, setSelectedCandidateId] = useState(null);
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", source: "referral", skills: "" });
  const [resumeFile, setResumeFile] = useState(null);
  const [error, setError] = useState("");
  const [duplicateMatch, setDuplicateMatch] = useState(null);

  const loadJobs = async () => {
    const { data } = await client.get("/recruitment/jobs", { params: { status: "open" } });
    setJobs(data);
    if (data.length && !selectedJob) setSelectedJob(data[0].id);
  };

  const loadCandidates = async (jobId) => {
    if (!jobId) return;
    setLoading(true);
    const { data } = await client.get(`/recruitment/jobs/${jobId}/candidates`);
    setCandidates(data);
    setLoading(false);
  };

  useEffect(() => { loadJobs(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (selectedJob) loadCandidates(selectedJob); }, [selectedJob]);

  const submitCandidate = async (e, duplicateAction) => {
    if (e) e.preventDefault();
    setError("");
    setDuplicateMatch(null);
    try {
      if (resumeFile) {
        const fd = new FormData();
        Object.entries(form).forEach(([k, v]) => fd.append(k, v));
        fd.append("job_id", selectedJob);
        fd.append("resume", resumeFile);
        if (duplicateAction) fd.append("duplicate_action", duplicateAction);
        await client.post("/recruitment/candidates", fd, { headers: { "Content-Type": "multipart/form-data" } });
      } else {
        await client.post("/recruitment/candidates", { ...form, job_id: selectedJob, duplicate_action: duplicateAction });
      }
      setShowAddForm(false);
      setForm({ full_name: "", email: "", phone: "", source: "referral", skills: "" });
      setResumeFile(null);
      loadCandidates(selectedJob);
    } catch (err) {
      if (err?.response?.status === 409) {
        setDuplicateMatch(err.response.data.candidate);
        setError(err.response.data.message);
      } else {
        setError(err?.response?.data?.message || "Could not add candidate.");
      }
    }
  };

  const initials = (name = "") => name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 20 }}>
      <div className="card">
        <div className="card-title-row"><h3>Open Postings</h3></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {jobs.map((j) => (
            <div key={j.id} onClick={() => setSelectedJob(j.id)}
              style={{ padding: "10px 12px", borderRadius: 8, cursor: "pointer",
                border: `1px solid ${selectedJob === j.id ? "var(--color-primary-500)" : "var(--color-border)"}`,
                background: selectedJob === j.id ? "var(--color-primary-50)" : "#fff" }}>
              <div style={{ fontWeight: 700, fontSize: 13 }}>{j.title}</div>
              <div className="muted" style={{ fontSize: 11 }}>{j.candidate_count} candidate(s)</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title-row">
          <h3>Candidates</h3>
          {canRecruit && selectedJob && (
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-sm btn-outline" onClick={() => setShowBulk(true)}>Bulk Import</button>
              <button className="btn btn-sm btn-primary" onClick={() => setShowAddForm(true)}>+ Add Candidate</button>
            </div>
          )}
        </div>
        {loading ? <Loader /> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {candidates.length === 0 && <div className="muted" style={{ fontSize: 13 }}>No candidates for this posting yet.</div>}
            {candidates.map((c) => (
              <div key={c.id} className="candidate-card" onClick={() => setSelectedCandidateId(c.id)}>
                <div className="candidate-card-main">
                  <div className="avatar-circle" style={{ width: 40, height: 40, fontSize: 14, flexShrink: 0 }}>
                    {initials(c.full_name)}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="flex-between">
                      <div style={{ fontWeight: 700, fontSize: 13.5 }}>{c.full_name}</div>
                      <div style={{ display: "flex", gap: 4 }}>
                        <Badge status={c.validation_status} />
                        <Badge status={c.stage} />
                      </div>
                    </div>
                    <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>
                      {c.email || "no email"} &middot; {c.phone || "no phone"} &middot; source: {c.source || "—"}
                    </div>
                    {c.skills?.length > 0 && (
                      <div className="chip-row" style={{ marginTop: 6 }}>
                        {c.skills.slice(0, 5).map((s) => <span key={s} className="chip blue">{s}</span>)}
                        {c.skills.length > 5 && <span className="chip">+{c.skills.length - 5} more</span>}
                      </div>
                    )}
                  </div>
                </div>
                <div className="candidate-card-actions" onClick={(e) => e.stopPropagation()}>
                  <a className={`icon-action ${!c.phone ? "disabled" : ""}`} href={c.phone ? `tel:${c.phone}` : undefined} title="Call">&#9742;</a>
                  <a className={`icon-action ${!c.phone ? "disabled" : ""}`} href={c.phone ? `sms:${c.phone}` : undefined} title="Message">&#128172;</a>
                  <a className={`icon-action ${!c.email ? "disabled" : ""}`} href={c.email ? `mailto:${c.email}` : undefined} title="Email">&#9993;</a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showAddForm && (
        <div className="modal-overlay" onClick={() => setShowAddForm(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>Add Candidate</h3>
            {error && <div className="login-error">{error}</div>}
            {duplicateMatch && (
              <div className="callout warn" style={{ marginBottom: 12 }}>
                Existing candidate: <strong>{duplicateMatch.full_name}</strong> ({duplicateMatch.email}), stage: {duplicateMatch.stage}.
                <div style={{ marginTop: 8 }}>
                  <button className="btn btn-sm btn-primary" onClick={() => submitCandidate(null, "link_new_application")}>
                    Link as new application anyway
                  </button>
                </div>
              </div>
            )}
            <form onSubmit={submitCandidate}>
              <div className="form-field">
                <label>Full Name</label>
                <input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Email</label>
                  <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                </div>
                <div className="form-field">
                  <label>Phone</label>
                  <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
                </div>
              </div>
              <div className="form-field">
                <label>Source</label>
                <select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}>
                  <option value="referral">Referral</option>
                  <option value="naukri">Naukri</option>
                  <option value="linkedin">LinkedIn</option>
                  <option value="walk-in">Walk-in</option>
                </select>
              </div>
              <div className="form-field">
                <label>Skills (comma-separated)</label>
                <input value={form.skills} onChange={(e) => setForm({ ...form, skills: e.target.value })} placeholder="Java, Spring Boot, SQL" />
              </div>
              <div className="form-field">
                <label>Resume</label>
                <input type="file" accept=".pdf,.doc,.docx" onChange={(e) => setResumeFile(e.target.files[0])} />
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowAddForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Add Candidate</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showBulk && (
        <BulkImportModal
          onClose={() => setShowBulk(false)}
          onImported={() => { setShowBulk(false); loadCandidates(selectedJob); }}
        />
      )}

      {selectedCandidateId && (
        <CandidateDetailModal
          candidateId={selectedCandidateId}
          onClose={() => setSelectedCandidateId(null)}
          onChanged={() => loadCandidates(selectedJob)}
        />
      )}
    </div>
  );
}

// ============================================================================
// Mock Tests
// ============================================================================

function MockTestsTab() {
  const [templates, setTemplates] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", job_id: "", topics: "", complexity: "medium", duration_minutes: 30, passing_threshold_pct: 60 });
  const [questions, setQuestions] = useState([{ question_text: "", question_type: "mcq", options: "", correct_answer: "", marks: 1, topic: "" }]);
  const [rankingsFor, setRankingsFor] = useState(null);
  const [rankings, setRankings] = useState([]);
  const [assignModal, setAssignModal] = useState(null);
  const [assignJobId, setAssignJobId] = useState(null);
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const [assignError, setAssignError] = useState("");
  const [linksModal, setLinksModal] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [selectedCandidates, setSelectedCandidates] = useState([]);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    const [tRes, jRes] = await Promise.all([client.get("/mocktest/templates"), client.get("/recruitment/jobs")]);
    setTemplates(tRes.data);
    setJobs(jRes.data);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const addQuestion = () => setQuestions([...questions, { question_text: "", question_type: "mcq", options: "", correct_answer: "", marks: 1, topic: "" }]);
  const updateQuestion = (i, field, value) => {
    const next = [...questions];
    next[i][field] = value;
    setQuestions(next);
  };

  const createTemplate = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await client.post("/mocktest/templates", {
        ...form,
        job_id: form.job_id || null,
        questions: questions.filter((q) => q.question_text).map((q) => ({
          ...q, options: q.options ? q.options.split(",").map((o) => o.trim()) : undefined,
        })),
      });
      setShowForm(false);
      setForm({ title: "", job_id: "", topics: "", complexity: "medium", duration_minutes: 30, passing_threshold_pct: 60 });
      setQuestions([{ question_text: "", question_type: "mcq", options: "", correct_answer: "", marks: 1, topic: "" }]);
      load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not create template.");
    }
  };

  const viewRankings = async (templateId) => {
    const { data } = await client.get(`/mocktest/templates/${templateId}/rankings`);
    setRankings(data);
    setRankingsFor(templateId);
  };

  const loadCandidatesForAssign = async (jobId) => {
    if (!jobId) {
      setCandidates([]);
      return;
    }
    const { data } = await client.get(`/recruitment/jobs/${jobId}/candidates`);
    setCandidates(data.filter((c) => c.verification_status === "verified"));
  };

  const toDatetimeLocal = (date) => {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };

  // <input type="datetime-local"> gives back the browser's LOCAL wall-clock
  // time with no timezone info (e.g. "2026-08-07T15:00" meaning 3pm IST).
  // The backend stores and compares everything in UTC, so this must be
  // converted before it's sent — otherwise "now" in IST looks like it's
  // still in the future once the backend reads it as UTC.
  const toUtcBackendString = (localDatetimeValue) => {
    const local = new Date(localDatetimeValue);
    const pad = (n) => String(n).padStart(2, "0");
    return `${local.getUTCFullYear()}-${pad(local.getUTCMonth() + 1)}-${pad(local.getUTCDate())}T${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}`;
  };

  const openAssign = async (template) => {
    const initialJobId = template.job_id || (jobs[0] && jobs[0].id) || null;
    setAssignJobId(initialJobId);
    setSelectedCandidates([]);
    setAssignError("");
    const now = new Date();
    const twoDaysOut = new Date(now.getTime() + 2 * 24 * 60 * 60 * 1000);
    setWindowStart(toDatetimeLocal(now));
    setWindowEnd(toDatetimeLocal(twoDaysOut));
    setAssignModal(template);
    await loadCandidatesForAssign(initialJobId);
  };

  const changeAssignJob = async (jobId) => {
    setAssignJobId(jobId);
    setSelectedCandidates([]);
    await loadCandidatesForAssign(jobId);
  };

  const assign = async () => {
    setAssignError("");
    if (!windowStart || !windowEnd) {
      setAssignError("Both a start and end time are required.");
      return;
    }
    if (new Date(windowEnd) <= new Date(windowStart)) {
      setAssignError("The end time must be after the start time.");
      return;
    }
    try {
      const { data } = await client.post("/mocktest/assign", {
        template_id: assignModal.id, candidate_ids: selectedCandidates,
        window_start: toUtcBackendString(windowStart), window_end: toUtcBackendString(windowEnd),
      });
      setAssignModal(null);
      setLinksModal(data);
    } catch (err) {
      setAssignError(err?.response?.data?.message || "Could not assign the test.");
    }
  };

  return (
    <div className="card">
      <div className="card-title-row">
        <h3>Mock Test Templates</h3>
        <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>+ New Template</button>
      </div>
      {loading ? <Loader /> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {templates.map((t) => (
            <div key={t.id} style={{ border: "1px solid var(--color-border)", borderRadius: 10, padding: 14 }}>
              <div className="flex-between">
                <div>
                  <strong>{t.title}</strong>
                  <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>
                    {t.topics} &middot; {t.complexity} &middot; {t.duration_minutes} min &middot; pass @ {t.passing_threshold_pct}% &middot; {t.question_count} question(s)
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                <button className="btn btn-sm btn-outline" onClick={() => openAssign(t)}>Assign to Candidates</button>
                <button className="btn btn-sm btn-outline" onClick={() => viewRankings(t.id)}>View Rankings</button>
              </div>
              {rankingsFor === t.id && (
                <div className="table-wrap" style={{ marginTop: 10 }}>
                  <table className="data-table">
                    <thead><tr><th>Rank</th><th>Candidate</th><th>Attempt</th><th>Score</th><th>%</th><th>Result</th></tr></thead>
                    <tbody>
                      {rankings.length === 0 && <tr className="empty-row"><td colSpan={6}>No completed attempts yet.</td></tr>}
                      {rankings.map((r) => (
                        <tr key={r.candidate_id}>
                          <td>#{r.rank}</td><td>{r.candidate_name}</td><td>{r.attempt_number}</td>
                          <td>{r.score}</td><td>{r.percentage}%</td>
                          <td><Badge status={r.passed ? "hired" : "rejected"} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal-box" style={{ width: 560 }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>New Mock Test Template</h3>
            {error && <div className="login-error">{error}</div>}
            <form onSubmit={createTemplate}>
              <div className="form-field">
                <label>Title</label>
                <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Job Posting</label>
                  <select value={form.job_id} onChange={(e) => setForm({ ...form, job_id: e.target.value })}>
                    <option value="">Unassigned</option>
                    {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
                  </select>
                </div>
                <div className="form-field">
                  <label>Topics (comma-separated)</label>
                  <input required value={form.topics} onChange={(e) => setForm({ ...form, topics: e.target.value })} placeholder="Java, OOP" />
                </div>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label>Complexity</label>
                  <select value={form.complexity} onChange={(e) => setForm({ ...form, complexity: e.target.value })}>
                    <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
                  </select>
                </div>
                <div className="form-field">
                  <label>Duration (min)</label>
                  <input type="number" value={form.duration_minutes} onChange={(e) => setForm({ ...form, duration_minutes: Number(e.target.value) })} />
                </div>
              </div>
              <div className="form-field">
                <label>Passing Threshold %</label>
                <input type="number" value={form.passing_threshold_pct} onChange={(e) => setForm({ ...form, passing_threshold_pct: Number(e.target.value) })} />
              </div>

              <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--color-text-muted)" }}>Questions</label>
              {questions.map((q, i) => (
                <div key={i} style={{ border: "1px solid var(--color-border)", borderRadius: 8, padding: 10, marginTop: 6 }}>
                  <input placeholder="Question text" value={q.question_text} onChange={(e) => updateQuestion(i, "question_text", e.target.value)}
                    style={{ width: "100%", marginBottom: 6, border: "1px solid var(--color-border)", borderRadius: 6, padding: 6 }} />
                  <div style={{ display: "flex", gap: 6 }}>
                    <select value={q.question_type} onChange={(e) => updateQuestion(i, "question_type", e.target.value)}>
                      <option value="mcq">MCQ</option><option value="subjective">Subjective</option>
                    </select>
                    <input placeholder="Topic" value={q.topic} onChange={(e) => updateQuestion(i, "topic", e.target.value)} style={{ width: 90 }} />
                    <input type="number" placeholder="Marks" value={q.marks} onChange={(e) => updateQuestion(i, "marks", Number(e.target.value))} style={{ width: 70 }} />
                  </div>
                  {q.question_type === "mcq" && (
                    <>
                      <input placeholder="Options, comma-separated" value={q.options} onChange={(e) => updateQuestion(i, "options", e.target.value)}
                        style={{ width: "100%", marginTop: 6, border: "1px solid var(--color-border)", borderRadius: 6, padding: 6 }} />
                      <input placeholder="Correct answer (must match an option)" value={q.correct_answer} onChange={(e) => updateQuestion(i, "correct_answer", e.target.value)}
                        style={{ width: "100%", marginTop: 6, border: "1px solid var(--color-border)", borderRadius: 6, padding: 6 }} />
                    </>
                  )}
                </div>
              ))}
              <button type="button" className="btn btn-sm btn-outline" style={{ marginTop: 8 }} onClick={addQuestion}>+ Add Question</button>

              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Create Template</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {assignModal && (
        <div className="modal-overlay" onClick={() => setAssignModal(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 6 }}>Assign "{assignModal.title}"</h3>
            <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>Only Verified candidates are eligible.</p>
            {assignError && <div className="login-error">{assignError}</div>}

            <div className="form-field">
              <label>Job Posting (candidate pool)</label>
              <select value={assignJobId || ""} onChange={(e) => changeAssignJob(Number(e.target.value))}>
                {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
              </select>
            </div>

            <div className="form-grid">
              <div className="form-field">
                <label>Test Window Start</label>
                <input type="datetime-local" value={windowStart} onChange={(e) => setWindowStart(e.target.value)} />
              </div>
              <div className="form-field">
                <label>Test Window End</label>
                <input type="datetime-local" value={windowEnd} onChange={(e) => setWindowEnd(e.target.value)} />
              </div>
            </div>

            <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--color-text-muted)" }}>Candidates</label>
            {candidates.length === 0 && <div className="muted" style={{ marginTop: 6 }}>No verified candidates yet for this posting.</div>}
            <div style={{ marginTop: 6 }}>
              {candidates.map((c) => (
                <label key={c.id} style={{ display: "block", fontSize: 13, marginBottom: 6 }}>
                  <input type="checkbox" checked={selectedCandidates.includes(c.id)}
                    onChange={(e) => setSelectedCandidates(e.target.checked
                      ? [...selectedCandidates, c.id] : selectedCandidates.filter((id) => id !== c.id))}
                    style={{ marginRight: 8 }} />
                  {c.full_name} ({c.email})
                </label>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
              <button className="btn btn-outline" onClick={() => setAssignModal(null)}>Cancel</button>
              <button className="btn btn-primary" disabled={!selectedCandidates.length} onClick={assign}>Assign</button>
            </div>
          </div>
        </div>
      )}

      {linksModal && (
        <TestLinksModal assignments={linksModal} onClose={() => setLinksModal(null)} />
      )}
    </div>
  );
}

function TestLinksModal({ assignments, onClose }) {
  const [copiedId, setCopiedId] = useState(null);

  const linkFor = (a) => `${window.location.origin}/test/${a.access_token}`;

  const copy = async (a) => {
    await navigator.clipboard.writeText(linkFor(a));
    setCopiedId(a.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const copyAll = async () => {
    const text = assignments.map((a) => `${a.candidate_name}: ${linkFor(a)}`).join("\n");
    await navigator.clipboard.writeText(text);
    setCopiedId("all");
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 6 }}>Test Assigned</h3>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
          Share each link with the candidate — by email, WhatsApp, or however you'd normally reach them. No HRMS login is needed to take the test.
        </p>

        {assignments.map((a) => (
          <div key={a.id} style={{ marginBottom: 10, paddingBottom: 10, borderBottom: "1px solid var(--color-border)" }}>
            <div style={{ fontWeight: 700, fontSize: 13 }}>{a.candidate_name}</div>
            <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 4 }}>
              <input
                readOnly value={linkFor(a)} onFocus={(e) => e.target.select()}
                style={{ flex: 1, fontSize: 12, border: "1px solid var(--color-border)", borderRadius: 6, padding: "6px 8px", color: "var(--color-text-muted)" }}
              />
              <button className="btn btn-sm btn-outline" onClick={() => copy(a)}>
                {copiedId === a.id ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
        ))}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
          <button className="btn btn-outline" onClick={copyAll}>{copiedId === "all" ? "Copied All" : "Copy All Links"}</button>
          <button className="btn btn-primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Newly Added Candidates Feed (Manager / Admin)
// ============================================================================

function FeedTab() {
  const [feed, setFeed] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCandidateId, setSelectedCandidateId] = useState(null);

  const load = async () => {
    setLoading(true);
    const { data } = await client.get("/recruitment/candidates/feed");
    setFeed(data);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="card">
      <div className="card-title-row"><h3>Newly Added Candidates (last 14 days)</h3></div>
      {loading ? <Loader /> : (
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Name</th><th>Job</th><th>Source</th><th>Validation</th><th>Verification</th><th>Added</th></tr></thead>
            <tbody>
              {feed.length === 0 && <tr className="empty-row"><td colSpan={6}>No new candidates in this window.</td></tr>}
              {feed.map((c) => (
                <tr key={c.id} onClick={() => setSelectedCandidateId(c.id)} style={{ cursor: "pointer" }}>
                  <td>{c.full_name}</td><td>{c.job_title}</td><td>{c.source}</td>
                  <td><Badge status={c.validation_status} /></td>
                  <td><Badge status={c.verification_status} /></td>
                  <td>{parseUtc(c.created_at).toLocaleDateString("en-IN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selectedCandidateId && (
        <CandidateDetailModal candidateId={selectedCandidateId} onClose={() => setSelectedCandidateId(null)} onChanged={load} />
      )}
    </div>
  );
}

// ============================================================================
// Recruiter Performance (Manager / Admin) + self-verify rights & interval
// ============================================================================

function PerformanceTab({ user }) {
  const [recruiters, setRecruiters] = useState([]);
  const [selected, setSelected] = useState(null);
  const [perf, setPerf] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const { data } = await client.get("/employees", { params: { role: "hr_recruiter" } });
    const scoped = user.role === ROLES.MANAGER ? data.filter((r) => r.manager_id === user.id) : data;
    setRecruiters(scoped);
    if (scoped.length) setSelected(scoped[0].id);
    setLoading(false);
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadPerf = async (id) => {
    const { data } = await client.get(`/dashboard/recruiter-performance/${id}`);
    setPerf(data);
  };
  useEffect(() => { if (selected) loadPerf(selected); }, [selected]);

  const toggleSelfVerify = async () => {
    const rights = !perf.recruiter.self_verify_rights;
    await client.post(`/recruitment/recruiters/${selected}/self-verify`, { rights });
    loadPerf(selected);
  };

  const setInterval_ = async () => {
    const days = window.prompt("Re-validation interval in days (e.g. 60):", perf.recruiter.revalidation_interval_days);
    if (!days) return;
    await client.post(`/recruitment/recruiters/${selected}/revalidation-interval`, { days: Number(days) });
    loadPerf(selected);
  };

  if (loading) return <Loader />;
  if (!recruiters.length) return <div className="card">No recruiters found in your scope.</div>;

  return (
    <div className="two-col">
      <div className="card">
        <div className="card-title-row"><h3>Recruiters</h3></div>
        {recruiters.map((r) => (
          <div key={r.id} onClick={() => setSelected(r.id)}
            style={{ padding: "8px 10px", borderRadius: 8, cursor: "pointer", marginBottom: 4,
              background: selected === r.id ? "var(--color-primary-50)" : "transparent" }}>
            {r.full_name}
          </div>
        ))}
      </div>
      <div className="card">
        {perf && (
          <>
            <div className="card-title-row"><h3>{perf.recruiter.full_name}</h3></div>
            <div className="stat-grid">
              <div className="stat-card"><div><div className="label">Candidates Added</div><div className="value">{perf.candidates_added}</div></div></div>
              <div className="stat-card"><div><div className="label">Interviews Scheduled</div><div className="value">{perf.interviews_scheduled}</div></div></div>
              <div className="stat-card"><div><div className="label">Hired</div><div className="value">{perf.hired_count}</div></div></div>
              <div className="stat-card"><div><div className="label">Conversion Rate</div><div className="value">{perf.conversion_rate_pct}%</div></div></div>
              <div className="stat-card"><div><div className="label">Present Days (month)</div><div className="value">{perf.attendance_present_days_this_month}</div></div></div>
            </div>
            {user.role === ROLES.MANAGER && perf.recruiter.manager_id === user.id && (
              <div className="callout" style={{ marginTop: 10 }}>
                <div className="flex-between">
                  <span>Self-verify rights: <strong>{perf.recruiter.self_verify_rights ? "Granted" : "Not granted"}</strong></span>
                  <button className="btn btn-sm btn-outline" onClick={toggleSelfVerify}>
                    {perf.recruiter.self_verify_rights ? "Revoke" : "Grant"}
                  </button>
                </div>
              </div>
            )}
            <div className="callout" style={{ marginTop: 10 }}>
              <div className="flex-between">
                <span>Re-validation interval: <strong>{perf.recruiter.revalidation_interval_days} days</strong></span>
                <button className="btn btn-sm btn-outline" onClick={setInterval_}>Change</button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
