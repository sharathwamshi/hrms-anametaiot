import { useState, useEffect } from "react";
import client from "../api/client";

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
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const selectedAgreement = activeAgreements.find((a) => a.id === Number(agreementId));
  const roles = selectedAgreement?.roles || [];

  useEffect(() => {
    if (roles.length && !roleId) setRoleId(roles[0].id);
  }, [agreementId]); // eslint-disable-line react-hooks/exhaustive-deps

  const searchEmployees = async (q) => {
    setEmployeeQuery(q);
    if (q.length < 2) { setEmployees([]); return; }
    const { data } = await client.get("/employees", { params: { q } });
    setEmployees(data);
  };

  const assign = async () => {
    setError("");
    const candidateName = selectedEmployee ? selectedEmployee.full_name : manualName;
    if (!candidateName.trim()) {
      setError("Select an employee or enter a name.");
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
    setSaving(true);
    try {
      await client.post("/vendors/hires", {
        vendor_id: vendor.id, agreement_id: Number(agreementId), agreement_role_id: Number(roleId),
        employee_id: selectedEmployee?.id, candidate_name: candidateName,
        ctc: Number(ctc), tenure_start_date: tenureStart,
      });
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
          Starts the tenure clock for vendor billing. If linked to an existing employee, their payroll starter structure is created automatically.
        </p>
        {error && <div className="login-error">{error}</div>}

        {activeAgreements.length === 0 ? (
          <div className="callout warn">This vendor has no active agreement to assign against.</div>
        ) : (
          <>
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
