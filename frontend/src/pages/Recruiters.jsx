import { useEffect, useMemo, useState } from "react";
import ExportButton from "../components/ExportButton";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import StatCard from "../components/StatCard";
import { downloadFile } from "../utils/download";

const money = (n) => `₹${Number(n || 0).toLocaleString("en-IN")}`;
const inputStyle = { border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" };

function RecruiterDrillDown({ recruiter, onClose }) {
  const [tab, setTab] = useState("candidates");
  const [candidates, setCandidates] = useState(null);
  const [placements, setPlacements] = useState(null);

  useEffect(() => {
    client.get("/recruitment/candidates", { params: { recruiter_id: recruiter.id, sort: "created_desc" } })
      .then(({ data }) => setCandidates(data));
    client.get("/vendors/hires", { params: { recruiter_id: recruiter.id } })
      .then(({ data }) => setPlacements(data));
  }, [recruiter.id]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ width: 760 }} onClick={(e) => e.stopPropagation()}>
        <div className="flex-between" style={{ marginBottom: 10 }}>
          <div>
            <h3 style={{ marginBottom: 2 }}>{recruiter.full_name}</h3>
            <span className="muted" style={{ fontSize: 12 }}>
              {recruiter.employee_code} · {recruiter.email}{recruiter.manager_name ? ` · reports to ${recruiter.manager_name}` : ""}
            </span>
          </div>
          <button className="btn btn-sm btn-outline" onClick={onClose}>Close</button>
        </div>

        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button className={`btn btn-sm ${tab === "candidates" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("candidates")}>
            Candidates ({recruiter.candidates_added})
          </button>
          <button className={`btn btn-sm ${tab === "placements" ? "btn-primary" : "btn-outline"}`} onClick={() => setTab("placements")}>
            Placements ({recruiter.placements_total})
          </button>
          <div style={{ flex: 1 }} />
          {tab === "candidates" ? (
            <button className="btn btn-sm btn-outline"
              onClick={() => downloadFile(`/recruitment/candidates/export?recruiter_id=${recruiter.id}`, `candidates_${recruiter.employee_code}.csv`)}>
              Download CSV
            </button>
          ) : (
            <button className="btn btn-sm btn-outline"
              onClick={() => downloadFile(`/vendors/hires/export?recruiter_id=${recruiter.id}`, `placements_${recruiter.employee_code}.csv`)}>
              Download CSV
            </button>
          )}
        </div>

        {tab === "candidates" ? (
          candidates === null ? <Loader /> : (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Candidate</th><th>Job</th><th>Stage</th></tr></thead>
                <tbody>
                  {candidates.length === 0 && <tr className="empty-row"><td colSpan={3}>No candidates added by this recruiter.</td></tr>}
                  {candidates.map((c) => (
                    <tr key={c.id}>
                      <td><strong>{c.full_name}</strong></td>
                      <td>
                        {c.job_title || "—"}
                        {c.requisition_type === "client" && <div className="chip orange" style={{ marginTop: 3, display: "inline-block" }}>{c.vendor_name}</div>}
                      </td>
                      <td><Badge status={c.stage} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : (
          placements === null ? <Loader /> : (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Candidate</th><th>Vendor</th><th>Type</th><th>Billing</th><th>CTC</th><th>Status</th></tr></thead>
                <tbody>
                  {placements.length === 0 && <tr className="empty-row"><td colSpan={6}>No placements credited to this recruiter.</td></tr>}
                  {placements.map((h) => (
                    <tr key={h.id}>
                      <td><strong>{h.candidate_name}</strong></td>
                      <td>{h.vendor_name || "—"}</td>
                      <td><span className="chip blue">{h.placement_type === "contract" ? "Contract" : "Direct"}</span></td>
                      <td><span className="chip orange">{h.billing_type === "continuous" ? "Monthly" : "One-time"}</span></td>
                      <td>{money(h.ctc)}</td>
                      <td><Badge status={h.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>
    </div>
  );
}

export default function Recruiters() {
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    client.get("/recruitment/recruiters")
      .then(({ data }) => setData(data))
      .catch((err) => setError(err?.response?.data?.message || "Could not load recruiters."));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    const term = q.trim().toLowerCase();
    return data.recruiters.filter((r) => {
      if (status === "active" && !r.is_active) return false;
      if (status === "inactive" && r.is_active) return false;
      if (!term) return true;
      return [r.full_name, r.employee_code, r.email].some((v) => (v || "").toLowerCase().includes(term));
    });
  }, [data, q, status]);

  const totals = useMemo(() => rows.reduce((t, r) => ({
    candidates: t.candidates + r.candidates_added,
    placements: t.placements + r.placements_total,
    billed: t.billed + r.fees_billed,
    pending: t.pending + r.fees_pending,
  }), { candidates: 0, placements: 0, billed: 0, pending: 0 }), [rows]);

  return (
    <AppLayout title="Recruiters" subtitle="The in-house recruiters behind every candidate and vendor placement — with what they sourced, placed and earned in fees.">
      {error && <div className="login-error">{error}</div>}
      {!data && !error ? <Loader /> : data && (
        <>
          <div className="stat-grid">
            <StatCard label="Recruiters" value={rows.length} icon={"\u25CF"} color="blue" />
            <StatCard label="Candidates Sourced" value={totals.candidates} icon={"\u25A4"} color="green" />
            <StatCard label="Vendor Placements" value={totals.placements} icon={"\u{1F517}"} color="orange" />
            <StatCard label="Fees Billed" value={money(totals.billed)} icon={"\u20B9"} color="green" />
            <StatCard label="Fees Pending" value={money(totals.pending)} icon={"\u20B9"} color="orange" />
          </div>

          <div className="card">
            <div className="card-title-row">
              <h3>In-house Recruiters</h3>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 12 }}>{rows.length} result(s)</span>
                <ExportButton filename="In_house_Recruiters" />
                <button className="btn btn-sm btn-outline" onClick={() => downloadFile("/recruitment/recruiters/export", "recruiters_export.csv")}>
                  Download CSV
                </button>
              </div>
            </div>

            {data.unattributed_placements > 0 && (
              <div className="callout warn" style={{ marginBottom: 12 }}>
                {data.unattributed_placements} placement(s) were recorded by hand and are not credited to any recruiter.
                Credit them from All Placements or when assigning a hire.
              </div>
            )}

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, code or email..."
                style={{ ...inputStyle, flex: 1, minWidth: 220 }} />
              <select value={status} onChange={(e) => setStatus(e.target.value)} style={inputStyle}>
                <option value="">Active + inactive</option>
                <option value="active">Active only</option>
                <option value="inactive">Inactive only</option>
              </select>
            </div>

            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Recruiter</th><th>Manager</th><th>Payroll</th><th>Candidates</th><th>Hired</th>
                    <th>Placements</th><th>Direct / Contract</th><th>Fees Billed</th><th>Fees Pending</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 && <tr className="empty-row"><td colSpan={9}>No recruiters match.</td></tr>}
                  {rows.map((r) => (
                    <tr key={r.id} onClick={() => setSelected(r)} style={{ cursor: "pointer" }}>
                      <td>
                        <strong>{r.full_name}</strong>{" "}
                        {!r.is_active && <span className="chip">Inactive</span>}
                        <div className="muted" style={{ fontSize: 11 }}>{r.employee_code}</div>
                      </td>
                      <td>{r.manager_name || "—"}</td>
                      <td>
                        {r.has_salary_structure
                          ? <span className="chip green">{money(r.monthly_gross)}/mo</span>
                          : <span className="chip orange">Not set</span>}
                      </td>
                      <td>{r.candidates_added} <span className="muted" style={{ fontSize: 11 }}>({r.candidates_active} active)</span></td>
                      <td>{r.candidates_hired}</td>
                      <td>{r.placements_total}</td>
                      <td>{r.placements_direct} / {r.placements_contract}</td>
                      <td>{money(r.fees_billed)}</td>
                      <td>{money(r.fees_pending)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
      {selected && <RecruiterDrillDown recruiter={selected} onClose={() => setSelected(null)} />}
    </AppLayout>
  );
}
