import { useEffect, useState, useCallback } from "react";
import client from "../api/client";
import Badge from "./Badge";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import { parseUtc } from "../utils/datetime";

const STAGES = ["applied", "screening", "mock_test", "interview", "offer", "hired", "rejected"];

export default function CandidateDetailModal({ candidateId, onClose, onChanged }) {
  const { user } = useAuth();
  const [candidate, setCandidate] = useState(null);
  const [calls, setCalls] = useState([]);
  const [interviews, setInterviews] = useState([]);
  const [offers, setOffers] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [noteText, setNoteText] = useState("");
  const [copiedAssignmentId, setCopiedAssignmentId] = useState(null);

  const canRecruit = [ROLES.HR_RECRUITER, ROLES.HR_OPERATIONS].includes(user.role);
  const canApprove = [ROLES.MANAGER, ROLES.HR_OPERATIONS].includes(user.role);

  const loadAll = useCallback(async () => {
    setLoading(true);
    const [candRes, callsRes, interviewsRes, offersRes, assignRes] = await Promise.all([
      client.get(`/recruitment/candidates/${candidateId}`),
      client.get(`/screening/candidates/${candidateId}/calls`),
      client.get(`/recruitment/candidates/${candidateId}/interviews`),
      client.get(`/offers`, { params: { candidate_id: candidateId } }),
      client.get(`/mocktest/assignments`, { params: { candidate_id: candidateId } }),
    ]);
    setCandidate(candRes.data);
    setCalls(callsRes.data);
    setInterviews(interviewsRes.data);
    setOffers(offersRes.data);
    setAssignments(assignRes.data);
    setLoading(false);
  }, [candidateId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const notify = () => {
    loadAll();
    onChanged && onChanged();
  };

  const handleError = (err, fallback) => setError(err?.response?.data?.message || fallback);

  const verify = async () => {
    setError("");
    try {
      await client.post(`/recruitment/candidates/${candidateId}/verify`);
      notify();
    } catch (err) {
      handleError(err, "Could not verify candidate.");
    }
  };

  const changeStage = async (stage) => {
    await client.put(`/recruitment/candidates/${candidateId}/stage`, { stage });
    notify();
  };

  const triggerCall = async () => {
    setError("");
    try {
      await client.post(`/screening/candidates/${candidateId}/trigger-call`);
      notify();
    } catch (err) {
      handleError(err, "Could not trigger screening call.");
    }
  };

  const rescheduleCall = async (callId) => {
    await client.post(`/screening/calls/${callId}/reschedule`);
    notify();
  };

  const scheduleInterview = async () => {
    const dt = window.prompt("Interview date & time (YYYY-MM-DDTHH:MM):");
    if (!dt) return;
    const round = window.prompt("Round name:", "Technical Round") || "Technical Round";
    const interviewerId = window.prompt("Interviewer employee ID (see Employees page):");
    try {
      const { data } = await client.post(`/recruitment/candidates/${candidateId}/interviews`, {
        scheduled_at: dt, round_name: round,
        interviewer_ids: interviewerId ? [Number(interviewerId)] : [],
      });
      if (data.conflict_warning) alert(`Scheduled, but: ${data.conflict_warning}`);
      notify();
    } catch (err) {
      handleError(err, "Could not schedule interview.");
    }
  };

  const rescheduleInterview = async (interviewId) => {
    const dt = window.prompt("New date & time (YYYY-MM-DDTHH:MM):");
    if (!dt) return;
    const reason = window.prompt("Reason for rescheduling:");
    if (!reason) return;
    try {
      await client.post(`/recruitment/interviews/${interviewId}/reschedule`, { scheduled_at: dt, reason });
      notify();
    } catch (err) {
      handleError(err, "Could not reschedule interview.");
    }
  };

  const submitFeedback = async (interviewId) => {
    const feedback = window.prompt("Feedback:");
    if (feedback === null) return;
    const result = window.prompt("Result (selected / rejected / pending):", "pending");
    await client.put(`/recruitment/interviews/${interviewId}`, { feedback, result });
    notify();
  };

  const copyTestLink = async (assignment) => {
    const link = `${window.location.origin}/test/${assignment.access_token}`;
    await navigator.clipboard.writeText(link);
    setCopiedAssignmentId(assignment.id);
    setTimeout(() => setCopiedAssignmentId(null), 2000);
  };

  const assignRetest = async (assignmentId) => {
    const start = window.prompt("Retest window start (YYYY-MM-DDTHH:MM):");
    if (!start) return;
    const end = window.prompt("Retest window end (YYYY-MM-DDTHH:MM):");
    if (!end) return;
    try {
      await client.post(`/mocktest/assignments/${assignmentId}/retest`, { window_start: start, window_end: end });
      notify();
    } catch (err) {
      handleError(err, "Could not assign retest.");
    }
  };

  const draftOffer = async () => {
    const designation = window.prompt("Designation:");
    if (!designation) return;
    const salary = window.prompt("Annual salary (CTC):");
    if (!salary) return;
    const joiningDate = window.prompt("Joining date (YYYY-MM-DD):");
    if (!joiningDate) return;
    try {
      await client.post("/offers", { candidate_id: candidateId, designation, salary: Number(salary), joining_date: joiningDate });
      notify();
    } catch (err) {
      handleError(err, "Could not draft offer.");
    }
  };

  const approveOffer = async (offerId) => { await client.post(`/offers/${offerId}/approve`); notify(); };
  const rejectOffer = async (offerId) => {
    const comment = window.prompt("Reason for rejecting this offer:");
    await client.post(`/offers/${offerId}/reject`, { comment });
    notify();
  };
  const sendOffer = async (offerId) => { await client.post(`/offers/${offerId}/send`); notify(); };
  const respondOffer = async (offerId, response) => {
    await client.post(`/offers/${offerId}/respond`, { response });
    notify();
  };

  const addNote = async () => {
    if (!noteText.trim()) return;
    await client.post(`/recruitment/candidates/${candidateId}/notes`, { body: noteText });
    setNoteText("");
    notify();
  };

  const editSkills = async () => {
    const skills = window.prompt("Skills (comma-separated):", (candidate.skills || []).join(", "));
    if (skills === null) return;
    try {
      await client.put(`/recruitment/candidates/${candidateId}/skills`, { skills });
      notify();
    } catch (err) {
      handleError(err, "Could not update skills.");
    }
  };

  const convertToEmployee = async () => {
    const employeeCode = window.prompt("New employee code (e.g. EMP-1010):");
    if (!employeeCode) return;
    const password = window.prompt("Temporary password:");
    if (!password) return;
    const role = window.prompt("Role (manager / employee / hr_operations / etc.):", "employee");
    const managerId = window.prompt("Manager employee ID (optional):");
    try {
      await client.post(`/employees/convert-candidate/${candidateId}`, {
        employee_code: employeeCode, password, role,
        manager_id: managerId ? Number(managerId) : undefined,
      });
      alert("Employee record created.");
      notify();
    } catch (err) {
      handleError(err, "Could not convert candidate.");
    }
  };

  if (loading || !candidate) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-box" onClick={(e) => e.stopPropagation()}>Loading…</div>
      </div>
    );
  }

  const acceptedOffer = offers.find((o) => o.status === "accepted");

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ width: 640 }} onClick={(e) => e.stopPropagation()}>
        <div className="flex-between" style={{ marginBottom: 6 }}>
          <h3>{candidate.full_name}</h3>
          <Badge status={candidate.stage} />
        </div>
        <div className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
          {candidate.email} &middot; {candidate.phone} &middot; {candidate.source}
          {candidate.resume_file_path && (
            <> &middot; <a href={candidate.resume_file_path} target="_blank" rel="noreferrer">Resume</a></>
          )}
        </div>
        {error && <div className="login-error">{error}</div>}
        {candidate.duplicate_of_candidate_id && (
          <div className="callout" style={{ background: "var(--color-warning-100)", marginBottom: 12 }}>
            Linked as a re-application of candidate #{candidate.duplicate_of_candidate_id}.
          </div>
        )}

        <div style={{ marginBottom: 14 }}>
          <div className="flex-between">
            <strong style={{ fontSize: 13 }}>Skills</strong>
            {canRecruit && <button className="btn btn-sm btn-outline" onClick={editSkills}>Edit</button>}
          </div>
          <div className="chip-row" style={{ marginTop: 6 }}>
            {(candidate.skills || []).length === 0 && <span className="muted" style={{ fontSize: 12 }}>No skills recorded yet.</span>}
            {(candidate.skills || []).map((s) => <span key={s} className="chip blue">{s}</span>)}
          </div>
        </div>

        <div className="form-field">
          <label>Stage</label>
          <select value={candidate.stage} onChange={(e) => changeStage(e.target.value)}>
            {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div className="card" style={{ marginBottom: 14, padding: 14 }}>
          <div className="flex-between">
            <div>
              <Badge status={candidate.validation_status} /> <Badge status={candidate.verification_status} />
              {candidate.validation_notes && (
                <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>{candidate.validation_notes}</div>
              )}
              {candidate.next_revalidation_due && (
                <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>
                  Next re-validation: {parseUtc(candidate.next_revalidation_due).toLocaleDateString("en-IN")}
                </div>
              )}
            </div>
            <button className="btn btn-sm btn-outline" disabled={!candidate.can_reverify_now} onClick={verify}>
              {candidate.verification_status === "verified" ? "Re-Verify" : "Verify"}
            </button>
          </div>
        </div>

        {canRecruit && (
          <div style={{ marginBottom: 14 }}>
            <div className="flex-between">
              <strong style={{ fontSize: 13 }}>Screening Calls</strong>
              <button className="btn btn-sm btn-outline" onClick={triggerCall}>Trigger Call</button>
            </div>
            {calls.length === 0 && <div className="muted" style={{ fontSize: 12 }}>No calls yet.</div>}
            {calls.map((c) => (
              <div key={c.id} style={{ fontSize: 12, padding: "8px 0", borderBottom: "1px solid var(--color-border)" }}>
                <div className="flex-between">
                  <span>Attempt #{c.attempt_number} — <Badge status={c.outcome || "pending"} /></span>
                  {c.outcome === "neutral" && (
                    <button className="btn btn-sm btn-outline" onClick={() => rescheduleCall(c.id)}>Reschedule</button>
                  )}
                </div>
                {c.summary && <div className="muted" style={{ marginTop: 4 }}>{c.summary}</div>}
              </div>
            ))}
          </div>
        )}

        {assignments.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <strong style={{ fontSize: 13 }}>Mock Tests</strong>
            {assignments.map((a) => (
              <div key={a.id} style={{ fontSize: 12, padding: "8px 0", borderBottom: "1px solid var(--color-border)" }}>
                <div className="flex-between">
                  <span>{a.template_title} — Attempt #{a.attempt_number} — {a.status}</span>
                  <div style={{ display: "flex", gap: 6 }}>
                    {["assigned", "in_progress"].includes(a.status) && (
                      <button className="btn btn-sm btn-outline" onClick={() => copyTestLink(a)}>
                        {copiedAssignmentId === a.id ? "Copied" : "Copy Link"}
                      </button>
                    )}
                    {canRecruit && (
                      <button className="btn btn-sm btn-outline" onClick={() => assignRetest(a.id)}>Assign Retest</button>
                    )}
                  </div>
                </div>
                {a.result && (
                  <div className="muted" style={{ marginTop: 4 }}>
                    Score: {a.result.score}/{a.result.max_score} ({a.result.percentage}%) — {a.result.passed ? "Passed" : "Not passed"}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <div style={{ marginBottom: 14 }}>
          <div className="flex-between">
            <strong style={{ fontSize: 13 }}>Interviews</strong>
            {canRecruit && <button className="btn btn-sm btn-outline" onClick={scheduleInterview}>Schedule</button>}
          </div>
          {interviews.length === 0 && <div className="muted" style={{ fontSize: 12 }}>No interviews yet.</div>}
          {interviews.map((iv) => (
            <div key={iv.id} style={{ fontSize: 12, padding: "8px 0", borderBottom: "1px solid var(--color-border)" }}>
              <div className="flex-between">
                <span>{iv.round_name} — {parseUtc(iv.scheduled_at).toLocaleString("en-IN")} — <Badge status={iv.status} /></span>
              </div>
              <div className="muted" style={{ marginTop: 4 }}>
                Panel: {iv.panelists.map((p) => p.interviewer_name).join(", ") || "—"} &middot; Result: {iv.result}
              </div>
              {canRecruit && (
                <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  <button className="btn btn-sm btn-outline" onClick={() => rescheduleInterview(iv.id)}>Reschedule</button>
                  <button className="btn btn-sm btn-outline" onClick={() => submitFeedback(iv.id)}>Add Feedback</button>
                </div>
              )}
            </div>
          ))}
        </div>

        <div style={{ marginBottom: 14 }}>
          <div className="flex-between">
            <strong style={{ fontSize: 13 }}>Offers</strong>
            {canRecruit && <button className="btn btn-sm btn-outline" onClick={draftOffer}>Draft Offer</button>}
          </div>
          {offers.length === 0 && <div className="muted" style={{ fontSize: 12 }}>No offers yet.</div>}
          {offers.map((o) => (
            <div key={o.id} style={{ fontSize: 12, padding: "8px 0", borderBottom: "1px solid var(--color-border)" }}>
              <div className="flex-between">
                <span>{o.designation} — ₹{o.salary.toLocaleString("en-IN")} — <Badge status={o.status} /></span>
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                {o.status === "drafted" && canRecruit && (
                  <button className="btn btn-sm btn-outline" onClick={() => client.post(`/offers/${o.id}/submit-for-approval`).then(notify)}>Submit for Approval</button>
                )}
                {o.status === "pending_approval" && canApprove && (
                  <>
                    <button className="btn btn-sm btn-success" onClick={() => approveOffer(o.id)}>Approve</button>
                    <button className="btn btn-sm btn-danger" onClick={() => rejectOffer(o.id)}>Reject</button>
                  </>
                )}
                {o.status === "approved" && canRecruit && (
                  <button className="btn btn-sm btn-outline" onClick={() => sendOffer(o.id)}>Send to Candidate</button>
                )}
                {o.status === "sent" && canRecruit && (
                  <>
                    <button className="btn btn-sm btn-success" onClick={() => respondOffer(o.id, "accepted")}>Mark Accepted</button>
                    <button className="btn btn-sm btn-danger" onClick={() => respondOffer(o.id, "declined")}>Mark Declined</button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>

        {candidate.stage === "hired" && !candidate.linked_employee_id && canRecruit && (
          <div className="callout note" style={{ marginBottom: 14 }}>
            <div className="flex-between">
              <span><strong>Ready to onboard.</strong> {acceptedOffer ? "Offer accepted." : "No accepted offer on file yet."}</span>
              <button className="btn btn-sm btn-primary" onClick={convertToEmployee}>Convert to Employee</button>
            </div>
          </div>
        )}
        {candidate.linked_employee_id && (
          <div className="callout note" style={{ marginBottom: 14 }}>
            Converted to Employee record #{candidate.linked_employee_id}.
          </div>
        )}

        <div style={{ marginBottom: 14 }}>
          <strong style={{ fontSize: 13 }}>Notes</strong>
          {(candidate.notes_thread || []).map((n) => (
            <div key={n.id} style={{ fontSize: 12, padding: "6px 0", borderBottom: "1px solid var(--color-border)" }}>
              <strong>{n.author_name}:</strong> {n.body}
            </div>
          ))}
          <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
            <input
              value={noteText} onChange={(e) => setNoteText(e.target.value)}
              placeholder="Add a note…" style={{ flex: 1, border: "1px solid var(--color-border)", borderRadius: 6, padding: "6px 10px" }}
            />
            <button className="btn btn-sm btn-outline" onClick={addNote}>Post</button>
          </div>
        </div>

        <div>
          <strong style={{ fontSize: 13 }}>Audit Trail</strong>
          <div style={{ maxHeight: 140, overflowY: "auto", marginTop: 6 }}>
            {(candidate.audit_log || []).map((a) => (
              <div key={a.id} className="muted" style={{ fontSize: 11, padding: "4px 0" }}>
                {parseUtc(a.created_at).toLocaleString("en-IN")} — <strong>{a.action}</strong> by {a.actor_name}
                {a.detail && ` — ${a.detail}`}
              </div>
            ))}
          </div>
        </div>

        <div style={{ textAlign: "right", marginTop: 16 }}>
          <button className="btn btn-outline" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
