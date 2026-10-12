import { useEffect, useState } from "react";
import ExportButton from "../components/ExportButton";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import { downloadFile } from "../utils/download";
import { parseUtc } from "../utils/datetime";
import { fetchRecruiterOptions } from "../utils/recruiters";

export default function AllPlacements() {
  const [placements, setPlacements] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [recruiters, setRecruiters] = useState([]);
  const [recruiterId, setRecruiterId] = useState("");
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [vendorId, setVendorId] = useState("");
  const [placementType, setPlacementType] = useState("");
  const [billingType, setBillingType] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("assigned_desc");

  const load = async () => {
    setLoading(true);
    const params = { sort };
    if (q) params.q = q;
    if (vendorId) params.vendor_id = vendorId;
    if (recruiterId) params.recruiter_id = recruiterId;
    if (placementType) params.placement_type = placementType;
    if (billingType) params.billing_type = billingType;
    if (status) params.status = status;
    const { data } = await client.get("/vendors/hires", { params });
    setPlacements(data);
    setLoading(false);
  };

  useEffect(() => {
    client.get("/vendors").then(({ data }) => setVendors(data));
    fetchRecruiterOptions().then(setRecruiters);
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, vendorId, recruiterId, placementType, billingType, status, sort]);

  const exportCsv = () => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (vendorId) params.set("vendor_id", vendorId);
    if (recruiterId) params.set("recruiter_id", recruiterId);
    if (placementType) params.set("placement_type", placementType);
    if (billingType) params.set("billing_type", billingType);
    if (status) params.set("status", status);
    downloadFile(`/vendors/hires/export?${params.toString()}`, "vendor_placements_export.csv");
  };

  return (
    <AppLayout title="All Placements" subtitle="Every candidate placed with a vendor — direct or contract, across every vendor. These are not AnametaIOT employees.">
      <div className="card">
        <div className="card-title-row">
          <h3>All Placements</h3>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="muted" style={{ fontSize: 12 }}>{placements.length} result(s)</span>
            <ExportButton filename="All_Placements" />
            <button className="btn btn-sm btn-outline" onClick={exportCsv}>Download CSV</button>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          <input
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search candidate name..."
            style={{ flex: 1, minWidth: 220, border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}
          />
          <select value={vendorId} onChange={(e) => setVendorId(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
            <option value="">All vendors</option>
            {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
          {recruiters.length > 0 && (
            <select value={recruiterId} onChange={(e) => setRecruiterId(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
              <option value="">All recruiters</option>
              {recruiters.map((r) => <option key={r.id} value={r.id}>{r.name}{r.active ? "" : " (inactive)"}</option>)}
            </select>
          )}
          <select value={placementType} onChange={(e) => setPlacementType(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
            <option value="">Direct + Contract</option>
            <option value="direct">Direct only</option>
            <option value="contract">Contract only</option>
          </select>
          <select value={billingType} onChange={(e) => setBillingType(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
            <option value="">Any billing</option>
            <option value="one_time">One-time</option>
            <option value="continuous">Continuous (monthly)</option>
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
            <option value="">Any status</option>
            <option value="active">Active</option>
            <option value="invoiced">Invoiced</option>
            <option value="replaced">Replaced</option>
            <option value="terminated">Terminated</option>
          </select>
          <select value={sort} onChange={(e) => setSort(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px" }}>
            <option value="assigned_desc">Newest first</option>
            <option value="assigned_asc">Oldest first</option>
            <option value="name_asc">Name A–Z</option>
            <option value="name_desc">Name Z–A</option>
          </select>
        </div>

        {loading ? <Loader /> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Candidate</th><th>Vendor</th><th>Role</th><th>Recruiter</th><th>Type</th><th>Billing</th>
                  <th>CTC</th><th>Internal Login</th><th>Status</th><th>Assigned</th>
                </tr>
              </thead>
              <tbody>
                {placements.length === 0 && <tr className="empty-row"><td colSpan={10}>No placements match these filters.</td></tr>}
                {placements.map((h) => (
                  <tr key={h.id}>
                    <td><strong>{h.candidate_name}</strong></td>
                    <td>{h.vendor_name || "—"}</td>
                    <td>{h.role_name || "—"}</td>
                    <td>{h.recruiter_name || <span className="muted" title="Recorded by hand — not credited to a recruiter">Unassigned</span>}</td>
                    <td><span className="chip blue">{h.placement_type === "contract" ? "Contract" : "Direct"}</span></td>
                    <td><span className="chip orange">{h.billing_type === "continuous" ? "Monthly" : "One-time"}</span></td>
                    <td>₹{h.ctc.toLocaleString("en-IN")}</td>
                    <td>{h.employee_id ? <span className="chip green">Yes</span> : "—"}</td>
                    <td><Badge status={h.status} /></td>
                    <td className="muted" style={{ fontSize: 12 }}>{parseUtc(h.assigned_at).toLocaleDateString("en-IN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
