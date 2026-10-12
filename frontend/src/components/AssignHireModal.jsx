import { useState, useEffect } from "react";
import client from "../api/client";
import { fetchRecruiterOptions } from "../utils/recruiters";

export default function AssignHireModal({ vendor, onClose, onAssigned }) {
  const activeAgreements = vendor.agreements.filter((a) => a.status === "active");
  const [agreementId, setAgreementId] = useState(activeAgreements[0]?.id || "");
  const [roleId, setRoleId] = useState("");
  const [employeeQuery, setEmployeeQuery] = useState("");
  const [employees, setEmployees] = useState([]);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [manualName, setManualName] = useState("");
  const [ctc, setCtc] = useState("");
  const [tenureStart, setTenureStart] = useState(new Date().toISOString().slice(0, 10));
  const [placementType, setPlacementType] = useState("direct");
  const [billingType, setBillingType] = useState("one_time");
  const [contractEmail, setContractEmail] = useState("");
  const [contractPassword, setContractPassword] = useState("");
  const [hiredCandidates, setHiredCandidates] = useState([]);
  const [candidateId, setCandidateId] = useState("");
  const [recruiters, setRecruiters] = useState([]);
  const [recruiterId, setRecruiterId] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  // People AnametaIOT's recruiters hired for THIS vendor's client requisitions and
  // that are not placed yet — picking one carries the recruiter credit automatically.
  useEffect(() => {
    client
      .get("/recruitment/candidates", { params: { vendor_id: vendor.id, stage: "hired", unplaced: "true" } })
      .then(({ data }) => setHiredCandidates(data))
      .catch(() => setHiredCandidates([]));
    fetchRecruiterOptions().then(setRecruiters);
  }, [vendor.id]);

  const pickCandidate = (id) => {
    setCandidateId(id);
    setSelectedEmployee(null);
    setEmployeeQuery("");
    const c = hiredCandidates.find((x) => x.id === Number(id));
    setManualName(c ? c.full_name : "");
    if (c && !contractEmail) setContractEmail(c.email || "");
  };
  const pickedCandidate = hiredCandidates.find((x) => x.id === Number(candidateId));

  const selectedAgreement = activeAgreements.find((a) => a.id === Number(agreementId));
  const roles = selectedAgreement?.roles || [];

  useEffect(() => {
    if (roles.length && !roleId) setRoleId(roles[0].id);
  }, [agreementId]); // eslint-disable-line react-hooks/exhaustive-deps

  const changePlacementType = (type) => {
    setPlacementType(type);
    setBillingType(type === "contract" ? "continuous" : "one_time");
    setSelectedEmployee(null);
    setEmployeeQuery("");
    if (!candidateId) setManualName("");
  };

  const searchEmployees = async (q) => {
    setEmployeeQuery(q);
    if (q.length < 2) { setEmployees([]); return; }
    const { data } = await client.get("/employees", { params: { q } });
    setEmployees(data);
  };

  const assign = async () => {
    setError("");
    const candidateName = placementType === "direct" && selectedEmployee ? selectedEmployee.full_name : manualName;
    if (!candidateName.trim()) {
      setError(placementType === "contract" ? "Enter the candidate's name." : "Select an employee or enter a name.");
      return;
    }
    if (!ctc || Number(ctc) <= 0) {
      setError("A valid CTC is required.");
      return;
    }
    if (!roleId) {
      setError("Select a rate-card role.");
      return;
    }
    if (placementType === "contract" && (!contractEmail.trim() || !contractPassword.trim())) {
      setError("A contract placement needs a login email and password — this is how they'll access their Documents and Payroll here.");
      return;
    }
    setSaving(true);
    try {
      const body = {
        vendor_id: vendor.id, agreement_id: Number(agreementId), agreement_role_id: Number(roleId),
        candidate_name: candidateName, ctc: Number(ctc), tenure_start_date: tenureStart,
        placement_type: placementType, billing_type: billingType,
      };
      if (candidateId) body.candidate_id = Number(candidateId);
      else if (recruiterId) body.recruiter_id = Number(recruiterId);
      if (placementType === "direct") {
        body.employee_id = selectedEmployee?.id;
      } else {
        body.contract_login_email = contractEmail.trim();
        body.contract_login_password = contractPassword;
      }
      await client.post("/vendors/hires", body);
      onAssigned();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not assign this hire.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 6 }}>Assign Hire to {vendor.name}</h3>
        <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
          Starts the tenure/billing clock. This person is placed with the vendor — they are never added to AnametaIOT's own Employees directory.
        </p>
        {error && <div className="login-error">{error}</div>}

        {activeAgreements.length === 0 ? (
          <div className="callout warn">This vendor has no active agreement to assign against.</div>
        ) : (
          <>
            <div className="form-field">
              <label>Placement Type</label>
              <div style={{ display: "flex", gap: 16, padding: "6px 0" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 400 }}>
                  <input type="radio" checked={placementType === "direct"} onChange={() => changePlacementType("direct")} />
                  Direct <span className="muted">(joins the vendor's own payroll — no login here)</span>
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 400 }}>
                  <input type="radio" checked={placementType === "contract"} onChange={() => changePlacementType("contract")} />
                  Contract <span className="muted">(tracked here with a Contract Employee login)</span>
                </label>
              </div>
            </div>

            <div className="form-field">
              <label>Sourced Candidate</label>
              <select value={candidateId} onChange={(e) => pickCandidate(e.target.value)}>
                <option value="">— Not from the pipeline (enter details by hand) —</option>
                {hiredCandidates.map((c) => (
                  <option key={c.id} value={c.id}>{c.full_name} · {c.job_title}{c.recruiter_name ? ` · sourced by ${c.recruiter_name}` : ""}</option>
                ))}
              </select>
              {pickedCandidate ? (
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {pickedCandidate.recruiter_name
                    ? `This placement will be credited to ${pickedCandidate.recruiter_name}, who sourced this candidate.`
                    : "This candidate has no recruiter on record."}
                </div>
              ) : hiredCandidates.length === 0 ? (
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  No hired, unplaced candidates for this vendor's client requisitions right now.
                </div>
              ) : null}
            </div>

            {!candidateId && recruiters.length > 0 && (
              <div className="form-field">
                <label>Credit to Recruiter (optional)</label>
                <select value={recruiterId} onChange={(e) => setRecruiterId(e.target.value)}>
                  <option value="">— Unassigned —</option>
                  {recruiters.map((r) => <option key={r.id} value={r.id}>{r.name}{r.active ? "" : " (inactive)"}</option>)}
                </select>
              </div>
            )}

            <div className="form-grid">
              <div className="form-field">
                <label>Agreement</label>
                <select value={agreementId} onChange={(e) => { setAgreementId(e.target.value); setRoleId(""); }}>
                  {activeAgreements.map((a) => (
                    <option key={a.id} value={a.id}>{a.effective_from} → {a.effective_to || "open-ended"}</option>
                  ))}
                </select>
              </div>
              <div className="form-field">
                <label>Rate-Card Role</label>
                <select value={roleId} onChange={(e) => setRoleId(e.target.value)}>
                  {roles.map((r) => <option key={r.id} value={r.id}>{r.role_name} ({r.service_fee_pct}%)</option>)}
                </select>
              </div>
            </div>

            <div className="form-field">
              <label>Billing</label>
              <select value={billingType} onChange={(e) => setBillingType(e.target.value)}>
                <option value="one_time">One-time fee (billed once tenure completes)</option>
                <option value="continuous">Continuous (billed monthly for as long as active)</option>
              </select>
            </div>

            {placementType === "direct" && candidateId ? (
              <div className="form-field">
                <label>Candidate Name</label>
                <input value={manualName} readOnly />
              </div>
            ) : placementType === "direct" ? (
              <>
                <div className="form-field">
                  <label>Employee (search directory)</label>
                  <input
                    value={selectedEmployee ? selectedEmployee.full_name : employeeQuery}
                    onChange={(e) => { setSelectedEmployee(null); searchEmployees(e.target.value); }}
                    placeholder="Type a name..."
                  />
                  {employees.length > 0 && !selectedEmployee && (
                    <div style={{ border: "1px solid var(--color-border)", borderRadius: 6, marginTop: 4, maxHeight: 140, overflowY: "auto" }}>
                      {employees.map((emp) => (
                        <div key={emp.id} onClick={() => { setSelectedEmployee(emp); setEmployees([]); }}
                          style={{ padding: "6px 10px", cursor: "pointer", fontSize: 12.5 }}>
                          {emp.full_name} — {emp.employee_code}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {!selectedEmployee && (
                  <div className="form-field">
                    <label>Or enter candidate name directly (not yet an Employee record)</label>
                    <input value={manualName} onChange={(e) => setManualName(e.target.value)} placeholder="e.g. someone still being onboarded" />
                  </div>
                )}
              </>
            ) : (
              <>
                <div className="form-field">
                  <label>Candidate Name</label>
                  <input value={manualName} readOnly={!!candidateId} onChange={(e) => setManualName(e.target.value)} placeholder="Full name" />
                </div>
                <div className="callout" style={{ marginBottom: 10 }}>
                  This creates a limited internal login (role: Contract Employee) so they can access their
                  Documents and Payroll here — it does not make them an AnametaIOT employee for any other purpose.
                </div>
                <div className="form-grid">
                  <div className="form-field">
                    <label>Contract Login Email</label>
                    <input type="email" value={contractEmail} onChange={(e) => setContractEmail(e.target.value)} placeholder="name@example.com" />
                  </div>
                  <div className="form-field">
                    <label>Contract Login Password</label>
                    <input type="password" value={contractPassword} onChange={(e) => setContractPassword(e.target.value)} placeholder="Set an initial password" />
                  </div>
                </div>
              </>
            )}

            <div className="form-grid">
              <div className="form-field">
                <label>CTC (annual)</label>
                <input type="number" value={ctc} onChange={(e) => setCtc(e.target.value)} />
              </div>
              <div className="form-field">
                <label>Tenure Start Date</label>
                <input type="date" value={tenureStart} onChange={(e) => setTenureStart(e.target.value)} />
              </div>
            </div>

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
              <button className="btn btn-outline" onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" disabled={saving} onClick={assign}>
                {saving ? "Assigning..." : "Assign"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
