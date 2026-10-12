import { useEffect, useState } from "react";
import client from "../api/client";
import Loader from "./Loader";
import ExportButton from "./ExportButton";
import { fmtTime, localDateStr } from "../utils/attendanceTime";

const inputStyle = { border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" };

/** Everyone who checked in AGAIN after checking out, with the reason they gave. */
export default function ReentriesPanel() {
  const [range, setRange] = useState({ from: localDateStr(new Date(Date.now() - 6 * 864e5)), to: localDateStr() });
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let off = false;
    setData(null); setError("");
    client.get("/attendance/team/reentries", { params: range })
      .then(({ data: d }) => { if (!off) setData(d); })
      .catch((e) => { if (!off) setError(e?.response?.data?.message || "Could not load the report."); });
    return () => { off = true; };
  }, [range]);

  return (
    <div className="card">
      <div className="card-title-row" style={{ flexWrap: "wrap", gap: 10 }}>
        <h3>Re-entries — who checked in again, and why</h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input type="date" value={range.from} max={range.to} onChange={(e) => e.target.value && setRange({ ...range, from: e.target.value })} style={inputStyle} />
          <span className="muted">to</span>
          <input type="date" value={range.to} min={range.from} max={localDateStr()} onChange={(e) => e.target.value && setRange({ ...range, to: e.target.value })} style={inputStyle} />
          <ExportButton url="/attendance/export/reentries" params={range} filename={`Re_entries_${range.from}_to_${range.to}`} />
        </div>
      </div>
      {error && <div className="login-error">{error}</div>}
      {!data && !error && <Loader />}
      {data && (
        <>
          <div className="att-sum">
            <div><b>{data.total}</b><span>Re-entries</span></div>
            <div><b>{data.people_count}</b><span>People</span></div>
            {data.by_person.slice(0, 2).map((p) => <div key={p.user.id}><b>{p.count}</b><span>{p.user.full_name}</span></div>)}
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Date</th><th>Employee</th><th>Check-in #</th><th>Checked out</th><th>Checked in again</th><th>Time away</th><th>Reason given</th><th>Where</th></tr></thead>
              <tbody>
                {data.reentries.length === 0 && <tr className="empty-row"><td colSpan={8}>No one checked in again in this period.</td></tr>}
                {data.reentries.map((r) => (
                  <tr key={r.session_id}>
                    <td>{r.work_date}</td>
                    <td><strong>{r.user.full_name}</strong><div className="muted" style={{ fontSize: 11.5 }}>{r.user.employee_code}</div></td>
                    <td>{r.session_no}</td>
                    <td>{fmtTime(r.previous_clock_out)}</td>
                    <td>{fmtTime(r.clock_in)}{r.still_clocked_in && <span className="att-chip green" style={{ marginLeft: 6 }}>still in</span>}</td>
                    <td>{r.gap_minutes != null ? `${r.gap_minutes} min` : "—"}</td>
                    <td style={{ maxWidth: 260 }}><em style={{ color: "var(--color-brand-orange-700)" }}>“{r.reason}”</em></td>
                    <td>{r.outside_office ? <span className="att-chip red">Out of office</span> : <span className="att-chip green">In office</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
