import { useCallback, useEffect, useMemo, useState } from "react";
import AppLayout from "../components/AppLayout";
import Loader from "../components/Loader";
import client from "../api/client";
import { ROLES } from "../config/roles";
import { useAuth } from "../context/AuthContext";

const HR_ROLES = [ROLES.HR, ROLES.HR_EXECUTIVE, ROLES.HR_OPERATIONS, ROLES.SUPER_ADMIN];
const FINANCE_ROLES = [ROLES.FINANCE_ACCOUNTS, ROLES.SUPER_ADMIN];
const ROUTING_ROLES = [ROLES.HR_OPERATIONS, ROLES.SUPER_ADMIN];
const TIMELINE = [
  ["employee", "Submitted"],
  ["manager", "Manager Approval"],
  ["l2", "L2 / Director Approval"],
  ["hr", "HR Review"],
  ["finance", "Finance Clearance"],
  ["exit", "Exit & Relieving"],
];
const EMPTY_FORM = { exit_choice: "", proposed_last_working_date: "", reason: "", comments: "" };
const EMPTY_FINANCE = {
  pending_salary: "", advances: "", reimbursements: "", other_dues: "",
  final_settlement_amount: "", final_settlement_status: "pending",
  buyback_payment_reference: "",
};

const labelStatus = (status) => (status || "").replaceAll("_", " ");
const shortDate = (date) => date ? new Date(`${date}T00:00:00`).toLocaleDateString("en-IN", {
  day: "numeric", month: "short", year: "numeric",
}) : "—";
const formatMoney = (amount) => amount == null ? "—" : `₹${Number(amount).toLocaleString("en-IN", {
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})}`;
const exitChoiceLabel = (choice) => choice === "full_notice_buyback"
  ? "Full Notice Period Buyback"
  : choice === "serve_full_notice" ? "Serve Full Notice Period" : "—";

function Status({ value }) {
  const tone = ["approved", "completed", "withdrawn", "revoked"].includes(value) ? "badge-success"
    : ["rejected"].includes(value) ? "badge-danger"
      : "badge-warning";
  return <span className={`badge ${tone}`}>{labelStatus(value) || "pending"}</span>;
}

function ResignationTimeline({ resignation }) {
  const revokedStage = resignation.status === "revoked"
    ? [...(resignation.history || [])].reverse().find((event) => event.event_type === "revoked")?.stage
    : null;
  const timelineStage = resignation.current_stage === "withdrawal" || resignation.status === "withdrawn"
    ? resignation.withdrawal_previous_stage
    : revokedStage || resignation.current_stage;
  const activeStage = timelineStage
    ? TIMELINE.findIndex(([key]) => key === timelineStage)
    : TIMELINE.findIndex(([key]) => key === resignation.current_stage);
  const terminal = ["rejected", "withdrawn", "revoked", "completed"].includes(resignation.status);
  return (
    <ol className="resignation-timeline">
      {TIMELINE.map(([key, title], index) => {
        const complete = resignation.status === "completed" || (terminal
          ? key === "employee" || index < Math.max(activeStage, 0)
          : index < activeStage);
        const current = !terminal && index === activeStage;
        return (
          <li key={key} className={complete ? "complete" : current ? "current" : resignation.status === "rejected" && index === activeStage ? "rejected" : ""}>
            <span className="resignation-timeline-dot">{complete ? "✓" : index + 1}</span>
            <span>{title}</span>
          </li>
        );
      })}
    </ol>
  );
}

function ResignationCard({ resignation, onDateChange, onWithdraw, onDocument, onEdit, onChecklist, submitting }) {
  return (
    <div className="card resignation-request-card">
      <div className="card-title-row">
        <div>
          <h3>Resignation dashboard</h3>
          <p className="muted" style={{ margin: "5px 0 0" }}>
            Submitted {shortDate(resignation.resignation_date)}
          </p>
        </div>
        <Status value={resignation.status} />
      </div>
      <div className="resignation-summary-grid">
        <div><span>Exit choice</span><strong>{exitChoiceLabel(resignation.exit_choice)}</strong></div>
        <div><span>{resignation.exit_choice === "full_notice_buyback" ? "Full-notice date (if served)" : "Proposed last working date"}</span><strong>{shortDate(resignation.pending_revision?.proposed_last_working_date || resignation.proposed_last_working_date)}</strong></div>
        <div><span>Approved last working date</span><strong>{shortDate(resignation.approved_last_working_date)}</strong></div>
        <div><span>Notice period</span><strong>{resignation.notice_period_days == null ? "Pending HR review" : `${resignation.notice_period_days} days`}</strong></div>
        <div><span>Remaining notice period</span><strong>{resignation.exit_choice === "full_notice_buyback" ? "No countdown — full notice buyback" : resignation.remaining_notice_period_days == null ? "Starts after HR approval" : `${resignation.remaining_notice_period_days} days`}</strong></div>
        {resignation.exit_choice === "full_notice_buyback" && (
          <>
            <div><span>Estimated buyback</span><strong>{formatMoney(resignation.buyback_estimated_amount)}</strong></div>
            <div><span>Payment status</span><strong>{labelStatus(resignation.buyback_payment_status) || "pending"}</strong></div>
          </>
        )}
      </div>
      <div className="resignation-reason">
        <strong>Reason</strong>
        <p>{resignation.reason}</p>
        {resignation.comments && <p className="muted">{resignation.comments}</p>}
      </div>
      <ResignationTimeline resignation={resignation} />
      <div className="resignation-actions">
        {resignation.document_available && <button className="btn btn-outline btn-sm" onClick={() => onDocument(resignation)}>Download supporting document</button>}
        {resignation.active_key && resignation.status !== "withdrawal_pending" && !["rejected", "withdrawn", "revoked", "completed"].includes(resignation.status) && (
          <>
            {resignation.status === "manager_pending" && !resignation.pending_revision && (
              <button className="btn btn-outline btn-sm" onClick={() => onEdit(resignation)}>Edit reason</button>
            )}
            {!resignation.pending_revision && (
              <>
                <button className="btn btn-outline btn-sm" onClick={() => onDateChange(resignation)}>Request date change / extension</button>
                <button className="btn btn-outline btn-sm" onClick={() => onWithdraw(resignation)}>Request withdrawal</button>
              </>
            )}
          </>
        )}
      </div>
      {resignation.pending_revision && (
        <p className="resignation-inline-note">
          Date change awaiting {labelStatus(resignation.pending_revision.current_stage)} review: {shortDate(resignation.pending_revision.proposed_last_working_date)}
        </p>
      )}
      {resignation.current_stage === "exit" && (
        <div className="resignation-checklist">
          <strong>Handover checklist</strong>
          {resignation.checklist.map((item) => (
            <div key={item.key}>
              <span>{item.label}</span>
              <Status value={item.status} />
              {["knowledge_transfer", "project_handover"].includes(item.key) && item.status !== "completed" && (
                <button className="btn btn-outline btn-sm" disabled={submitting} onClick={() => onChecklist(resignation, item.key, "completed")}>Mark complete</button>
              )}
            </div>
          ))}
        </div>
      )}
      {!!resignation.history?.length && (
        <details className="resignation-history-inline">
          <summary>Approval history ({resignation.history.length})</summary>
          <div className="resignation-events">
            {resignation.history.map((event) => (
              <div key={event.id}>
                <strong>{event.actor?.full_name || "System"} · {labelStatus(event.event_type)}</strong>
                <span>{new Date(event.created_at).toLocaleString("en-IN")}</span>
                {event.comments && <p>{event.comments}</p>}
                {event.details?.proposed_last_working_date && <p>Proposed last working date: {shortDate(event.details.proposed_last_working_date)}</p>}
                {event.details?.approved_last_working_date && <p>Approved last working date: {shortDate(event.details.approved_last_working_date)}</p>}
                {event.details?.updated_reason && <p>Updated reason: {event.details.updated_reason}{event.details.previous_reason ? ` (previous: ${event.details.previous_reason})` : ""}</p>}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function ResignationPolicyPanel({ onError, onNotice }) {
  const [companies, setCompanies] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [companyName, setCompanyName] = useState("");
  const [policyForm, setPolicyForm] = useState({
    notice_period_days: "",
    buyback_daily_divisor: "",
    buyback_multiplier: "",
  });
  const [saving, setSaving] = useState(false);

  const loadPolicies = useCallback(async () => {
    try {
      const { data } = await client.get("/resignations/policy");
      setCompanies(data.companies);
      setPolicies(data.policies);
      setCompanyName((current) => current || data.companies[0] || "");
    } catch (err) {
      onError(err?.response?.data?.message || "Could not load resignation policies.");
    }
  }, [onError]);

  useEffect(() => {
    loadPolicies();
  }, [loadPolicies]);

  useEffect(() => {
    const policy = policies.find((item) => item.company_name === companyName);
    setPolicyForm({
      notice_period_days: policy?.notice_period_days ?? "",
      buyback_daily_divisor: policy?.buyback_daily_divisor ?? "",
      buyback_multiplier: policy?.buyback_multiplier ?? "",
    });
  }, [companyName, policies]);

  const savePolicy = async (event) => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    onError("");
    try {
      const { data } = await client.put("/resignations/policy", {
        company_name: companyName,
        ...policyForm,
      });
      setPolicies((items) => [
        ...items.filter((item) => item.company_name !== data.company_name),
        data,
      ]);
      onNotice("Resignation policy saved.");
    } catch (err) {
      onError(err?.response?.data?.message || "Could not save resignation policy.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="card">
      <h3>Resignation exit policy</h3>
      <p className="muted">Set the required notice duration and full buyback calculation for each company. New requests save a snapshot; later policy edits do not change submitted requests.</p>
      <form className="resignation-routing-form" onSubmit={savePolicy}>
        <label className="form-field">
          <span>Company / unit</span>
          <select required value={companyName} onChange={(event) => setCompanyName(event.target.value)}>
            <option value="">Select company</option>
            {companies.map((company) => <option key={company} value={company}>{company}</option>)}
          </select>
        </label>
        <label className="form-field">
          <span>Required notice period (days)</span>
          <input required type="number" min="1" max="3650" step="1" value={policyForm.notice_period_days} onChange={(event) => setPolicyForm({ ...policyForm, notice_period_days: event.target.value })} />
        </label>
        <label className="form-field">
          <span>Annual CTC divisor</span>
          <input required type="number" min="1" max="366" step="1" value={policyForm.buyback_daily_divisor} onChange={(event) => setPolicyForm({ ...policyForm, buyback_daily_divisor: event.target.value })} />
        </label>
        <label className="form-field">
          <span>Buyback multiplier</span>
          <input required type="number" min="0.0001" max="100" step="0.0001" value={policyForm.buyback_multiplier} onChange={(event) => setPolicyForm({ ...policyForm, buyback_multiplier: event.target.value })} />
        </label>
        <button className="btn btn-primary" type="submit" disabled={saving || !companyName}>{saving ? "Saving…" : "Save policy"}</button>
      </form>
      <p className="muted">Estimated buyback = annual CTC ÷ divisor × multiplier × all configured notice days. Partial buyback is not available.</p>
    </section>
  );
}

export default function Resignation() {
  const { user } = useAuth();
  const userRole = user?.role || "";
  const isHr = HR_ROLES.includes(userRole);
  const isFinance = FINANCE_ROLES.includes(userRole);
  const canConfigureRouting = ROUTING_ROLES.includes(userRole);
  const [tab, setTab] = useState("mine");
  const [myRequests, setMyRequests] = useState([]);
  const [queue, setQueue] = useState([]);
  const [selected, setSelected] = useState(null);
  const [organizationHistory, setOrganizationHistory] = useState([]);
  const [routing, setRouting] = useState([]);
  const [routingUsers, setRoutingUsers] = useState([]);
  const [routingForm, setRoutingForm] = useState({ company_name: "", approver_user_id: "" });
  const [today, setToday] = useState("");
  const [policyQuote, setPolicyQuote] = useState(null);
  const [policyError, setPolicyError] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [dateChange, setDateChange] = useState(null);
  const [dateChangeForm, setDateChangeForm] = useState({ proposed_last_working_date: "", reason: "" });
  const [editReason, setEditReason] = useState(null);
  const [editReasonForm, setEditReasonForm] = useState({ reason: "", comments: "" });
  const [reviewComment, setReviewComment] = useState("");
  const [approvedDate, setApprovedDate] = useState("");
  const [financeForm, setFinanceForm] = useState(EMPTY_FINANCE);
  const [buybackCalculationVerified, setBuybackCalculationVerified] = useState(false);
  const [buybackPaymentVerified, setBuybackPaymentVerified] = useState(false);
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadMain = useCallback(async () => {
    if (!user?.id) {
      setLoading(false);
      setError("");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const requests = [
        client.get("/resignations/my"),
        client.get("/resignations/queue"),
        client.get("/resignations/context"),
      ];
      if (isHr || isFinance) requests.push(client.get("/resignations/history"));
      if (canConfigureRouting) requests.push(client.get("/resignations/routing"), client.get("/resignations/routing/users"));
      const result = await Promise.all(requests);
      setMyRequests(result[0].data);
      setQueue(result[1].data);
      setToday(result[2].data.company_today);
      let index = 3;
      if (isHr || isFinance) setOrganizationHistory(result[index++].data);
      if (canConfigureRouting) {
        setRouting(result[index].data);
        setRoutingUsers(result[index + 1].data);
      }
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load resignation information.");
    } finally {
      setLoading(false);
    }
  }, [canConfigureRouting, isFinance, isHr, user?.id]);

  useEffect(() => {
    if (!user) return;
    loadMain();
  }, [user, loadMain]);

  const activeRequest = useMemo(
    () => myRequests.find((item) => item.active_key) || myRequests[0],
    [myRequests],
  );
  useEffect(() => {
    if (!user?.id || activeRequest?.active_key) return undefined;
    let cancelled = false;
    setPolicyQuote(null);
    setPolicyError("");
    client.get("/resignations/policy/quote")
      .then(({ data }) => {
        if (!cancelled) setPolicyQuote(data);
      })
      .catch((err) => {
        if (!cancelled) setPolicyError(err?.response?.data?.message || "Could not load the resignation policy.");
      });
    return () => { cancelled = true; };
  }, [activeRequest?.id, activeRequest?.active_key, user?.id]);

  const openRequestDetails = async (item) => {
    setSelected(item);
    setReviewComment("");
    setApprovedDate(item.pending_revision?.proposed_last_working_date || item.approved_last_working_date || item.proposed_last_working_date || "");
    setFinanceForm({ ...EMPTY_FINANCE, ...(item.finance || {}) });
    setBuybackCalculationVerified(false);
    setBuybackPaymentVerified(false);
    try {
      const { data } = await client.get(`/resignations/${item.id}`);
      setSelected(data);
      setApprovedDate(data.pending_revision?.proposed_last_working_date || data.approved_last_working_date || data.proposed_last_working_date || "");
      setFinanceForm({ ...EMPTY_FINANCE, ...(data.finance || {}) });
      setBuybackCalculationVerified(Boolean(data.buyback_calculation_verified_at));
      setBuybackPaymentVerified(false);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load resignation details.");
    }
  };

  const submitResignation = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError("");
    setNotice("");
    const body = new FormData();
    body.append("exit_choice", form.exit_choice);
    body.append("policy_version", String(policyQuote?.policy_version || ""));
    body.append("proposed_last_working_date", policyQuote?.expected_last_working_date || "");
    body.append("reason", form.reason);
    body.append("comments", form.comments);
    if (file) body.append("document", file);
    try {
      await client.post("/resignations", body);
      setForm(EMPTY_FORM);
      setFile(null);
      setNotice("Your resignation request was submitted for approval.");
      await loadMain();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not submit your resignation.");
    } finally {
      setSubmitting(false);
    }
  };

  const requestDateChange = async (event) => {
    event.preventDefault();
    if (!dateChange || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      await client.post(`/resignations/${dateChange.id}/date-change`, dateChangeForm);
      setDateChange(null);
      setNotice("Your last working date change was sent for reapproval.");
      await loadMain();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not request the date change.");
    } finally {
      setSubmitting(false);
    }
  };

  const saveReason = async (event) => {
    event.preventDefault();
    if (!editReason || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      await client.patch(`/resignations/${editReason.id}/details`, editReasonForm);
      setEditReason(null);
      setNotice("Your resignation reason was updated.");
      await loadMain();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update your resignation details.");
    } finally {
      setSubmitting(false);
    }
  };

  const requestWithdrawal = async (item) => {
    if (!window.confirm("Send a resignation withdrawal request to the current approver?")) return;
    setError("");
    try {
      await client.post(`/resignations/${item.id}/withdrawal`);
      setNotice("Your withdrawal request was sent for approval.");
      await loadMain();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not request resignation withdrawal.");
    }
  };

  const revokeResignation = async (item) => {
    if (!window.confirm("Revoke this resignation request and restore the employee to Active?")) return;
    const reason = window.prompt("Enter the reason for revoking this resignation:");
    if (!reason?.trim()) return;
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await client.post(`/resignations/${item.id}/revoke`, { reason: reason.trim() });
      setSelected(null);
      setNotice("The resignation was revoked.");
      await loadMain();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not revoke this resignation.");
    } finally {
      setSubmitting(false);
    }
  };

  const decideRequest = async (item, decision) => {
    if (submitting) return;
    setSubmitting(true);
    setError("");
    const payload = { decision, comment: reviewComment };
    if (item.current_stage === "hr" && decision === "approve") payload.approved_last_working_date = approvedDate;
    if (item.current_stage === "hr" && decision === "approve" && item.exit_choice === "full_notice_buyback") {
      payload.buyback_calculation_verified = buybackCalculationVerified;
    }
    if (item.current_stage === "finance" && decision === "approve") {
      payload.final_settlement_status = financeForm.final_settlement_status;
      payload.pending_salary = financeForm.pending_salary;
      payload.advances = financeForm.advances;
      payload.reimbursements = financeForm.reimbursements;
      payload.other_dues = financeForm.other_dues;
      payload.final_settlement_amount = financeForm.final_settlement_amount;
      if (item.exit_choice === "full_notice_buyback") {
        payload.buyback_payment_reference = financeForm.buyback_payment_reference;
        payload.buyback_payment_verified = buybackPaymentVerified;
      }
    }
    try {
      const endpoint = item.status === "withdrawal_pending"
        ? `/resignations/${item.id}/withdrawal-decision`
        : `/resignations/${item.id}/decision`;
      await client.post(endpoint, payload);
      setNotice(`Resignation ${decision === "approve" ? "approved" : "rejected"}.`);
      setSelected(null);
      await loadMain();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save this decision.");
    } finally {
      setSubmitting(false);
    }
  };

  const saveFinanceDetails = async (item) => {
    if (submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const { data } = await client.patch(`/resignations/${item.id}/finance`, {
        ...financeForm,
        final_settlement_status: "pending",
      });
      setSelected(data);
      setFinanceForm({ ...EMPTY_FINANCE, ...data.finance });
      setNotice("Interim Finance settlement details saved.");
      await loadMain();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save Finance settlement details.");
    } finally {
      setSubmitting(false);
    }
  };

  const updateChecklist = async (item, key, status) => {
    if (submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const { data } = await client.patch(`/resignations/${item.id}/checklist/${key}`, { status });
      setSelected(data);
      await loadMain();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not update the exit checklist.");
    } finally {
      setSubmitting(false);
    }
  };
  const canUpdateExitItem = (key) => (
    (isHr && ["assets_returned", "system_access_revocation", "hr_clearance", "relieving_letter"].includes(key))
    || (isFinance && key === "finance_clearance")
  );

  const downloadDocument = async (item) => {
    setError("");
    try {
      const { data } = await client.get(`/resignations/${item.id}/document`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = url;
      link.download = item.document_filename || "resignation-document";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not download the resignation document.");
    }
  };

  const saveRouting = async (event) => {
    event.preventDefault();
    setError("");
    try {
      await client.post("/resignations/routing", {
        ...routingForm,
        approver_user_id: Number(routingForm.approver_user_id),
      });
      setRoutingForm({ ...routingForm, approver_user_id: "" });
      setNotice("L2 / Director approver mapping added.");
      const { data } = await client.get("/resignations/routing");
      setRouting(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not add the approver mapping.");
    }
  };

  const deleteRouting = async (routingId) => {
    setError("");
    try {
      await client.delete(`/resignations/routing/${routingId}`);
      setRouting((items) => items.filter((item) => item.id !== routingId));
      setNotice("Approver mapping removed.");
    } catch (err) {
      setError(err?.response?.data?.message || "Could not remove the approver mapping.");
    }
  };

  const tabs = [
    ["mine", "My Resignation"],
    ["history", "Resignation History"],
    ...((isHr || isFinance) ? [["organization", "Organization History"]] : []),
    ["approvals", "Approvals"],
    ...(isHr ? [["exit", "Exit & Relieving"]] : []),
    ...(isHr ? [["policy", "Exit Policy"]] : []),
    ...(canConfigureRouting ? [["routing", "Approver Routing"]] : []),
  ];
  const exitRequests = queue.filter((item) => item.current_stage === "exit");
  const historyRows = tab === "organization" ? organizationHistory : myRequests;
  const showingOrganizationHistory = tab === "organization";

  return (
    <AppLayout title="Resignation">
      <div className="resignation-page">
        <div className="card resignation-page-header">
          <div>
            <h2>Resignation Management</h2>
            <p className="muted">Submit, review and complete resignation workflows securely.</p>
          </div>
          {today && <span className="resignation-company-date">Company date · {shortDate(today)}</span>}
        </div>
        {error && <div className="login-error" role="alert">{error}</div>}
        {notice && <div className="resignation-notice" role="status">{notice}</div>}
        <div className="resignation-tabs" role="tablist">
          {tabs.map(([key, title]) => (
            <button
              key={key}
              className={`resignation-tab${tab === key ? " active" : ""}`}
              onClick={() => { setTab(key); setError(""); }}
              role="tab"
              aria-selected={tab === key}
            >
              {title}{key === "approvals" && queue.length > 0 ? ` (${queue.length})` : ""}
            </button>
          ))}
        </div>
        {loading ? <Loader label="Loading resignation data..." /> : (
          <>
            {tab === "mine" && (
              <div className="resignation-content">
                {activeRequest && activeRequest.active_key ? (
                  <ResignationCard
                    resignation={activeRequest}
                    onDateChange={(item) => {
                      setDateChange(item);
                      setDateChangeForm({ proposed_last_working_date: item.proposed_last_working_date, reason: "" });
                    }}
                    onEdit={(item) => {
                      setEditReason(item);
                      setEditReasonForm({ reason: item.reason, comments: item.comments || "" });
                    }}
                    onChecklist={updateChecklist}
                    submitting={submitting}
                    onWithdraw={requestWithdrawal}
                    onDocument={downloadDocument}
                  />
                ) : (
                  <section className="card resignation-form-card">
                    <h3>Submit resignation</h3>
                    <p className="muted">Your request follows the Manager → L2 / Director → HR → Finance → Exit approval workflow.</p>
                    {policyError && <p className="resignation-inline-note" role="alert">{policyError}</p>}
                    {policyQuote && (
                      <p className="muted">
                        Company policy: {policyQuote.notice_period_days} notice days. Full-notice last working date: {shortDate(policyQuote.expected_last_working_date)}.
                      </p>
                    )}
                    <form onSubmit={submitResignation}>
                      <label className="form-field">
                        <span>Resignation date</span>
                        <input value={today} readOnly aria-readonly="true" />
                      </label>
                      <fieldset className="form-field">
                        <legend>Choose exactly one exit option</legend>
                        <label>
                          <input
                            type="radio"
                            name="exit_choice"
                            value="serve_full_notice"
                            required
                            disabled={!policyQuote}
                            checked={form.exit_choice === "serve_full_notice"}
                            onChange={(event) => setForm({ ...form, exit_choice: event.target.value })}
                          />
                          <span>Serve Full Notice Period</span>
                        </label>
                        <label>
                          <input
                            type="radio"
                            name="exit_choice"
                            value="full_notice_buyback"
                            disabled={!policyQuote || !policyQuote.buyback_available}
                            checked={form.exit_choice === "full_notice_buyback"}
                            onChange={(event) => setForm({ ...form, exit_choice: event.target.value })}
                          />
                          <span>Full Notice Period Buyback</span>
                        </label>
                      </fieldset>
                      {form.exit_choice === "serve_full_notice" && policyQuote && (
                        <p className="resignation-inline-note">Expected Last Working Day: {shortDate(policyQuote.expected_last_working_date)}. HR will verify and approve the final notice duration and date.</p>
                      )}
                      {form.exit_choice === "full_notice_buyback" && policyQuote && (
                        <p className="resignation-inline-note">
                          Estimated full buyback for {policyQuote.buyback_unserved_days} days: <strong>{formatMoney(policyQuote.buyback_estimated_amount)}</strong>. No partial buyback is available. Finance will set your Last Working Day when payment is verified and cleared.
                        </p>
                      )}
                      {policyQuote && !policyQuote.buyback_available && <p className="muted" role="status">{policyQuote.message}</p>}
                      <label className="form-field">
                        <span>Reason for resignation</span>
                        <textarea required rows="4" maxLength="5000" value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} />
                      </label>
                      <label className="form-field">
                        <span>Additional comments <small>(optional)</small></span>
                        <textarea rows="3" maxLength="5000" value={form.comments} onChange={(event) => setForm({ ...form, comments: event.target.value })} />
                      </label>
                      <label className="form-field resignation-file-field">
                        <span>Supporting document <small>(PDF, DOC, or DOCX)</small></span>
                        <input type="file" accept=".pdf,.doc,.docx" onChange={(event) => setFile(event.target.files?.[0] || null)} />
                      </label>
                      {file && <span className="muted">{file.name}</span>}
                      <div className="form-actions">
                        <button className="btn btn-outline" type="reset" disabled={submitting} onClick={() => { setForm(EMPTY_FORM); setFile(null); }}>Cancel</button>
                        <button className="btn btn-primary" type="submit" disabled={submitting || !today || !policyQuote || !form.exit_choice || (form.exit_choice === "full_notice_buyback" && !policyQuote.buyback_available)}>
                          {submitting ? "Submitting…" : "Submit resignation"}
                        </button>
                      </div>
                    </form>
                  </section>
                )}
              </div>
            )}
            {(tab === "history" || tab === "organization") && (
              <section className="card">
                <h3>{showingOrganizationHistory ? "Organization resignation history" : "Resignation history"}</h3>
                {historyRows.length === 0 ? <p className="muted">No resignation requests are available.</p> : (
                  <div className="table-wrap">
                    <table className="data-table resignation-table">
                      <thead><tr>{showingOrganizationHistory && <th>Employee</th>}<th>Resignation date</th><th>Proposed last day</th><th>Approved last day</th><th>Notice</th><th>Status</th></tr></thead>
                      <tbody>{historyRows.map((item) => (
                        <tr key={item.id} onClick={() => openRequestDetails(item)} className="resignation-row-clickable">
                          {showingOrganizationHistory && <td>{item.employee?.full_name || "—"}<small>{item.employee?.employee_code}</small></td>}
                          <td>{shortDate(item.resignation_date)}</td>
                          <td>{shortDate(item.proposed_last_working_date)}</td>
                          <td>{shortDate(item.approved_last_working_date)}</td>
                          <td>{item.notice_period_days == null ? "—" : `${item.notice_period_days} days`}</td>
                          <td><Status value={item.status} /></td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
              </section>
            )}
            {tab === "approvals" && (
              <section className="card">
                <div className="card-title-row"><h3>Assigned resignation requests</h3><span className="chip orange">{queue.length} pending</span></div>
                {queue.length === 0 ? <p className="muted">There are no resignation requests assigned to you.</p> : (
                  <div className="table-wrap">
                    <table className="data-table resignation-table">
                      <thead><tr><th>Employee</th><th>Company / Department</th><th>Resignation date</th><th>Proposed last day</th><th>Reason</th><th>Approval stage</th><th>Status</th><th>Action</th></tr></thead>
                      <tbody>{queue.map((item) => (
                        <tr key={item.id}>
                          <td>{item.employee?.full_name || "—"}<small>{item.employee?.employee_code}</small></td>
                          <td>{item.company_name}<small>{item.department_name || "—"}</small></td>
                          <td>{shortDate(item.resignation_date)}</td>
                          <td>{shortDate(item.pending_revision?.proposed_last_working_date || item.proposed_last_working_date)}</td>
                          <td className="resignation-table-reason">{item.pending_revision?.reason || item.reason}</td>
                          <td>{labelStatus(item.status === "withdrawal_pending" ? "withdrawal approval" : item.current_stage)}</td>
                          <td><Status value={item.status} /></td>
                          <td><button className="btn btn-primary btn-sm" onClick={() => openRequestDetails(item)}>View details</button></td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
              </section>
            )}
            {tab === "exit" && (
              <section className="card">
                <div className="card-title-row"><h3>Exit & Relieving</h3><span className="chip orange">{exitRequests.length} active</span></div>
                {exitRequests.length === 0 ? <p className="muted">No requests are awaiting exit formalities.</p> : (
                  <div className="resignation-exit-list">
                    {exitRequests.map((item) => (
                      <div className="resignation-exit-card" key={item.id}>
                        <div className="card-title-row">
                          <div><strong>{item.employee?.full_name}</strong><small>{item.employee?.employee_code} · {item.company_name}</small></div>
                          <Status value={item.status} />
                        </div>
                        <div className="resignation-checklist">
                          {item.checklist.map((check) => (
                            <div key={check.key}>
                              <span>{check.label}</span>
                              <Status value={check.status} />
                              {check.status !== "completed" && canUpdateExitItem(check.key) && (
                                <button
                                  className="btn btn-outline btn-sm"
                                  onClick={() => updateChecklist(item, check.key, "completed")}
                                >
                                  Mark complete
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}
            {tab === "routing" && canConfigureRouting && (
              <section className="card">
                <h3>L2 / Director approver routing</h3>
                <p className="muted">Approvers configured for each company can review at the L2 / Director stage.</p>
                <form className="resignation-routing-form" onSubmit={saveRouting}>
                  <label className="form-field">
                    <span>Company / unit</span>
                    <select required value={routingForm.company_name} onChange={(event) => setRoutingForm({ ...routingForm, company_name: event.target.value })}>
                      <option value="">Select company</option>
                      {[...new Set(routingUsers.map((person) => person.company_name))].map((company) => <option key={company} value={company}>{company}</option>)}
                    </select>
                  </label>
                  <label className="form-field">
                    <span>Approver</span>
                    <select required value={routingForm.approver_user_id} onChange={(event) => setRoutingForm({ ...routingForm, approver_user_id: event.target.value })}>
                      <option value="">Select approver</option>
                      {routingUsers.filter((person) => !routingForm.company_name || person.company_name === routingForm.company_name).map((person) => (
                        <option key={person.id} value={person.id}>{person.full_name} · {person.employee_code} ({person.role})</option>
                      ))}
                    </select>
                  </label>
                  <button className="btn btn-primary" type="submit">Add mapping</button>
                </form>
                {routing.length === 0 ? <p className="muted">No approver mappings are configured yet.</p> : (
                  <div className="table-wrap">
                    <table className="data-table resignation-table">
                      <thead><tr><th>Company / unit</th><th>Approver</th><th>Role</th><th>Action</th></tr></thead>
                      <tbody>{routing.map((item) => (
                        <tr key={item.id}>
                          <td>{item.company_name}</td>
                          <td>{item.approver.full_name} · {item.approver.employee_code}</td>
                          <td>{item.approver.role}</td>
                          <td><button className="btn btn-outline btn-sm" onClick={() => deleteRouting(item.id)}>Remove</button></td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
              </section>
            )}
            {tab === "policy" && isHr && (
              <ResignationPolicyPanel
                onError={setError}
                onNotice={setNotice}
              />
            )}
          </>
        )}
      </div>
      {dateChange && (
        <div className="modal-overlay" onClick={() => setDateChange(null)}>
          <div className="modal-box resignation-modal" onClick={(event) => event.stopPropagation()}>
            <h3>Request a last working date change</h3>
            {error && <div className="login-error" role="alert">{error}</div>}
            <p className="muted">The revised date will restart approval with your Manager.</p>
            <form onSubmit={requestDateChange}>
              <label className="form-field"><span>Proposed last working date</span><input type="date" required min={today} value={dateChangeForm.proposed_last_working_date} onChange={(event) => setDateChangeForm({ ...dateChangeForm, proposed_last_working_date: event.target.value })} /></label>
              <label className="form-field"><span>Reason for change</span><textarea rows="3" required maxLength="2000" value={dateChangeForm.reason} onChange={(event) => setDateChangeForm({ ...dateChangeForm, reason: event.target.value })} /></label>
              <div className="form-actions"><button className="btn btn-outline" type="button" onClick={() => setDateChange(null)}>Cancel</button><button className="btn btn-primary" disabled={submitting}>{submitting ? "Submitting…" : "Submit date change"}</button></div>
            </form>
          </div>
        </div>
      )}
      {editReason && (
        <div className="modal-overlay" onClick={() => setEditReason(null)}>
          <div className="modal-box resignation-modal" onClick={(event) => event.stopPropagation()}>
            <h3>Edit resignation reason</h3>
            {error && <div className="login-error" role="alert">{error}</div>}
            <p className="muted">You can edit these details while your request is awaiting its initial Manager review.</p>
            <form onSubmit={saveReason}>
              <label className="form-field"><span>Reason for resignation</span><textarea rows="4" required maxLength="5000" value={editReasonForm.reason} onChange={(event) => setEditReasonForm({ ...editReasonForm, reason: event.target.value })} /></label>
              <label className="form-field"><span>Additional comments <small>(optional)</small></span><textarea rows="3" maxLength="5000" value={editReasonForm.comments} onChange={(event) => setEditReasonForm({ ...editReasonForm, comments: event.target.value })} /></label>
              <div className="form-actions"><button className="btn btn-outline" type="button" onClick={() => setEditReason(null)}>Cancel</button><button className="btn btn-primary" disabled={submitting}>{submitting ? "Saving…" : "Save changes"}</button></div>
            </form>
          </div>
        </div>
      )}
      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal-box resignation-modal resignation-detail-modal" onClick={(event) => event.stopPropagation()}>
            <div className="card-title-row"><h3>Resignation review</h3><Status value={selected.status} /></div>
            {error && <div className="login-error" role="alert">{error}</div>}
            <p className="muted">{selected.employee?.full_name} · {selected.employee?.employee_code} · {selected.company_name}</p>
            <div className="resignation-summary-grid">
              <div><span>Exit choice</span><strong>{exitChoiceLabel(selected.exit_choice)}</strong></div>
              <div><span>Resignation date</span><strong>{shortDate(selected.resignation_date)}</strong></div>
              <div><span>{selected.exit_choice === "full_notice_buyback" ? "Full-notice date (if served)" : "Proposed last day"}</span><strong>{shortDate(selected.pending_revision?.proposed_last_working_date || selected.proposed_last_working_date)}</strong></div>
              <div><span>Approved last day</span><strong>{shortDate(selected.approved_last_working_date)}</strong></div>
              <div><span>Notice period</span><strong>{selected.notice_period_days == null ? "Pending" : `${selected.notice_period_days} days`}</strong></div>
            </div>
            {selected.exit_choice === "full_notice_buyback" && (
              <div className="resignation-inline-note">
                <p>Estimated full buyback: <strong>{formatMoney(selected.buyback_estimated_amount)}</strong> for {selected.buyback_unserved_days} days.</p>
                <p>Calculation: annual CTC {formatMoney(selected.exit_policy_snapshot?.annual_ctc)} ÷ {selected.exit_policy_snapshot?.buyback_daily_divisor} × {selected.exit_policy_snapshot?.buyback_multiplier} × {selected.buyback_unserved_days} full notice days.</p>
                <p>Calculation verification: {selected.buyback_calculation_verified_at ? "Verified by HR" : "Pending HR review"} · Payment: {labelStatus(selected.buyback_payment_status) || "pending"}{selected.buyback_payment_reference ? ` · Reference ${selected.buyback_payment_reference}` : ""}</p>
                <p>Finance sets the Last Working Day on the date payment is verified and cleared; no notice countdown applies to a full buyback.</p>
              </div>
            )}
            <div className="resignation-reason"><strong>Reason</strong><p>{selected.pending_revision?.reason || selected.reason}</p></div>
            {selected.document_available && <button className="btn btn-outline btn-sm" onClick={() => downloadDocument(selected)}>Download supporting document</button>}
            {selected.current_stage === "hr" && selected.exit_choice !== "full_notice_buyback" && (
              <label className="form-field"><span>HR-approved last working date</span><input type="date" min={selected.exit_policy_snapshot?.expected_last_working_date || today} value={approvedDate} disabled={!!selected.pending_revision} onChange={(event) => setApprovedDate(event.target.value)} /></label>
            )}
            {selected.current_stage === "hr" && selected.exit_choice === "full_notice_buyback" && (
              <label className="form-field">
                <span>
                  <input type="checkbox" checked={buybackCalculationVerified} onChange={(event) => setBuybackCalculationVerified(event.target.checked)} />
                  I verified the full-notice buyback calculation against the saved policy and salary basis.
                </span>
              </label>
            )}
            {selected.current_stage === "finance" && (
              <div className="resignation-form-grid">
                {[
                  ["pending_salary", "Pending salary"],
                  ["advances", "Advances"],
                  ["reimbursements", "Reimbursements"],
                  ["other_dues", "Other dues"],
                  ["final_settlement_amount", "Final settlement amount"],
                ].map(([key, title]) => (
                  <label className="form-field" key={key}><span>{title}</span><input type="number" min="0" step="0.01" value={financeForm[key] ?? ""} onChange={(event) => setFinanceForm({ ...financeForm, [key]: event.target.value })} /></label>
                ))}
                {selected.exit_choice === "full_notice_buyback" && (
                  <>
                    <label className="form-field"><span>Buyback payment reference</span><input required maxLength="255" value={financeForm.buyback_payment_reference || ""} onChange={(event) => setFinanceForm({ ...financeForm, buyback_payment_reference: event.target.value })} /></label>
                    <label className="form-field">
                      <span>
                        <input type="checkbox" checked={buybackPaymentVerified} onChange={(event) => setBuybackPaymentVerified(event.target.checked)} />
                        I verified receipt of the full buyback payment.
                      </span>
                    </label>
                  </>
                )}
                <label className="form-field"><span>Clearance status</span><select value={financeForm.final_settlement_status || "pending"} onChange={(event) => setFinanceForm({ ...financeForm, final_settlement_status: event.target.value })}><option value="pending">Pending</option><option value="cleared">Cleared</option></select></label>
              </div>
            )}
            {selected.status === "withdrawal_pending" && <p className="resignation-inline-note">The employee requested withdrawal; approve or reject with a comment.</p>}
            {selected.current_stage !== "exit" && (
              <label className="form-field"><span>{selected.current_stage === "manager" || selected.current_stage === "l2" ? "Review comments (required on rejection)" : "Comments (required on rejection)"}</span><textarea rows="3" value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} /></label>
            )}
            {selected.current_stage === "exit" && selected.checklist?.length > 0 && (
              <div className="resignation-checklist">
                {selected.checklist.map((item) => (
                  <div key={item.key}><span>{item.label}</span><Status value={item.status} /></div>
                ))}
              </div>
            )}
            {selected.current_stage === "exit" && selected.checklist?.some((item) => item.status !== "completed") && (
              <p className="muted">Complete each item in the Exit & Relieving tab before the resignation is closed.</p>
            )}
            {selected.status === "withdrawal_pending" || ["manager", "l2", "hr", "finance"].includes(selected.current_stage) ? (
              <div className="form-actions resignation-review-actions">
                <button className="btn btn-outline" onClick={() => setSelected(null)}>Close</button>
                {isHr && selected.employee_id !== user.id && selected.active_key
                  && selected.status !== "withdrawal_pending"
                  && !["rejected", "withdrawn", "revoked", "completed"].includes(selected.status)
                  && <button className="btn btn-danger" disabled={submitting} onClick={() => revokeResignation(selected)}>Revoke</button>}
                {selected.current_stage === "finance" && <button className="btn btn-outline" disabled={submitting} onClick={() => saveFinanceDetails(selected)}>{submitting ? "Saving…" : "Save pending details"}</button>}
                <button className="btn btn-danger" disabled={submitting || !reviewComment.trim()} onClick={() => decideRequest(selected, "reject")}>Reject</button>
                <button
                  className="btn btn-primary"
                  disabled={submitting
                    || (selected.current_stage === "hr" && selected.exit_choice === "full_notice_buyback" && !buybackCalculationVerified)
                    || (selected.current_stage === "finance" && selected.exit_choice === "full_notice_buyback" && (!buybackPaymentVerified || !financeForm.buyback_payment_reference?.trim()))}
                  onClick={() => decideRequest(selected, "approve")}
                >
                  {submitting ? "Saving…" : "Approve"}
                </button>
              </div>
            ) : (
              <div className="form-actions">
                <button className="btn btn-outline" onClick={() => setSelected(null)}>Close</button>
                {isHr && selected.employee_id !== user.id && selected.active_key
                  && selected.status !== "withdrawal_pending"
                  && !["rejected", "withdrawn", "revoked", "completed"].includes(selected.status)
                  && <button className="btn btn-danger" disabled={submitting} onClick={() => revokeResignation(selected)}>Revoke</button>}
              </div>
            )}
          </div>
        </div>
      )}
    </AppLayout>
  );
}
