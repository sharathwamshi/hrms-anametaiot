import { useEffect, useState } from "react";
import ExportButton from "../components/ExportButton";
import client from "../api/client";
import Loader from "../components/Loader";
import { ROLES, ROLE_LABELS } from "../config/roles";

const money = (n) => `₹${Number(n || 0).toLocaleString("en-IN")}`;
const inputStyle = { border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" };
const STATE = {
  missing: { label: "Not set up", cls: "orange" },
  set: { label: "Ready", cls: "blue" },
  draft: { label: "Draft", cls: "orange" },
  processed: { label: "Payslip processed", cls: "blue" },
  published: { label: "Published", cls: "green" },
  updated: { label: "Updated", cls: "blue" },
  paid: { label: "Paid", cls: "green" },
};

// Every active in-house person, whatever their role — recruiters, managers,
// employees, contract logins — with where they stand in the payroll flow.
export default function PayrollPeopleTab({ month, year, version, onSetStructure, onOpenPayslips }) {
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [payroll, setPayroll] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      const params = { month, year };
      if (q) params.q = q;
      if (role) params.role = role;
      if (payroll) params.payroll = payroll;
      client.get("/payroll/coverage", { params }).then(({ data }) => setData(data));
    }, 250);
    return () => clearTimeout(t);
  }, [q, role, payroll, month, year, version]);

  if (!data) return <Loader />;
  const s = data.summary;

  return (
    <div className="card">
      <div className="card-title-row">
        <h3>People &amp; Payroll</h3>
        <span style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span className="muted" style={{ fontSize: 12 }}>{data.people.length} shown · {s.total_active} active in total</span>
          <ExportButton filename="People_and_Payroll" />
        </span>
      </div>

      {s.missing_structure > 0 && (
        <div className="callout warn" style={{ marginBottom: 12 }}>
          <strong>{s.missing_structure} active {s.missing_structure === 1 ? "person has" : "people have"} no salary structure</strong> and
          will be skipped when payslips are generated. Set them up below.
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or code..." style={{ ...inputStyle, flex: 1, minWidth: 200 }} />
        <select value={role} onChange={(e) => setRole(e.target.value)} style={inputStyle}>
          <option value="">All roles</option>
          {Object.values(ROLES).map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
        </select>
        <select value={payroll} onChange={(e) => setPayroll(e.target.value)} style={inputStyle}>
          <option value="">Any payroll status</option>
          <option value="missing">Not set up</option>
          <option value="set">Ready (structure set)</option>
          <option value="processed">Payslip processed</option>
          <option value="paid">Paid</option>
        </select>
      </div>

      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr><th>Person</th><th>Role</th><th>Department</th><th>Manager</th><th>Monthly Gross</th><th>Net</th><th>This Month</th><th></th></tr>
          </thead>
          <tbody>
            {data.people.length === 0 && <tr className="empty-row"><td colSpan={8}>No one matches these filters.</td></tr>}
            {data.people.map((p) => {
              const st = STATE[p.payroll_state] || STATE.missing;
              return (
                <tr key={p.id}>
                  <td><strong>{p.full_name}</strong><div className="muted" style={{ fontSize: 11 }}>{p.employee_code}{p.designation ? ` · ${p.designation}` : ""}</div></td>
                  <td><span className="chip blue">{ROLE_LABELS[p.role] || p.role}</span></td>
                  <td>{p.department || "—"}</td>
                  <td>{p.manager_name || "—"}</td>
                  <td>{p.has_structure ? money(p.monthly_gross) : "—"}</td>
                  <td>{p.has_structure ? money(p.monthly_net) : "—"}</td>
                  <td><span className={`chip ${st.cls}`}>{st.label}</span></td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button className="btn btn-sm btn-outline" onClick={() => onSetStructure(p)}>
                      {p.has_structure ? "Edit Salary" : "Set Up Salary"}
                    </button>
                    {p.payslip_id && <button className="btn btn-sm btn-outline" style={{ marginLeft: 6 }} onClick={onOpenPayslips}>Payslips</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
