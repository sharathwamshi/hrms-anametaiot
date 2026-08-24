import { useEffect, useState, useCallback } from "react";
import client from "../api/client";
import Badge from "./Badge";
import Loader from "./Loader";
import AssignHireModal from "./AssignHireModal";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";

export default function VendorDetailModal({ vendorId, onClose, onChanged }) {
  const { user } = useAuth();
  const canManage = [ROLES.FINANCE_ACCOUNTS, ROLES.HR_OPERATIONS].includes(user.role);
  const canApprove = [ROLES.MANAGER, ROLES.HR_OPERATIONS].includes(user.role);

  const [vendor, setVendor] = useState(null);
  const [hires, setHires] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAssign, setShowAssign] = useState(false);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [vRes, hRes, iRes] = await Promise.all([
      client.get(`/vendors/${vendorId}`),
      client.get("/vendors/hires", { params: { vendor_id: vendorId } }),
      client.get("/vendors/invoices", { params: { vendor_id: vendorId } }),
    ]);
    setVendor(vRes.data);
    setHires(hRes.data);
    setInvoices(iRes.data);
    setLoading(false);
  }, [vendorId]);

  useEffect(() => { load(); }, [load]);

  const billableCount = hires.filter((h) => h.is_billable).length;
  const currentPeriod = new Date().toISOString().slice(0, 7);
  const recurringDueCount = hires.filter((h) => h.billing_type === "continuous" && h.status === "active" && h.last_billed_month !== currentPeriod).length;

  const generateInvoice = async () => {
    setError("");
    setGenerating(true);
    try {
      await client.post(`/vendors/${vendorId}/invoices/generate`, {});
      load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not generate invoice.");
    } finally {
      setGenerating(false);
    }
  };

  const generateRecurringInvoice = async () => {
    setError("");
    setGenerating(true);
    try {
      await client.post(`/vendors/${vendorId}/invoices/generate-recurring`, { period: currentPeriod });
      load();
    } catch (err) {
      setError(err?.response?.data?.message || "Could not generate the recurring invoice.");
    } finally {
      setGenerating(false);
    }
  };

  const replaceHire = async (hireId) => {
    const name = window.prompt("Replacement candidate's name:");
    if (!name) return;
    const ctc = window.prompt("Replacement CTC:");
    if (!ctc) return;
    await client.post(`/vendors/hires/${hireId}/replace`, { candidate_name: name, ctc: Number(ctc) });
    load();
  };

  const submitForApproval = async (invoiceId) => { await client.post(`/vendors/invoices/${invoiceId}/submit-for-approval`); load(); };
  const approveInvoice = async (invoiceId) => { await client.post(`/vendors/invoices/${invoiceId}/approve`); load(); };
  const rejectInvoice = async (invoiceId) => {
    const comment = window.prompt("Reason for rejecting this invoice:");
    await client.post(`/vendors/invoices/${invoiceId}/reject`, { comment });
    load();
  };
  const markPaid = async (invoiceId) => { await client.post(`/vendors/invoices/${invoiceId}/mark-paid`); load(); };

  if (loading || !vendor) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-box" onClick={(e) => e.stopPropagation()}><Loader /></div>
      </div>
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" style={{ width: 720 }} onClick={(e) => e.stopPropagation()}>
        <div className="flex-between" style={{ marginBottom: 4 }}>
          <h3>{vendor.name}</h3>
          <Badge status={vendor.status} />
        </div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 14 }}>
          {vendor.gstin && `GSTIN: ${vendor.gstin} · `}{vendor.state}
          {vendor.contact_person && ` · ${vendor.contact_person}`}
        </div>
        {error && <div className="login-error">{error}</div>}

        {/* Agreements & rate card */}
        <div style={{ marginBottom: 16 }}>
          <strong style={{ fontSize: 13 }}>Agreements</strong>
          {vendor.agreements.map((a) => (
            <div key={a.id} style={{ border: "1px solid var(--color-border)", borderRadius: 8, padding: 10, marginTop: 6 }}>
              <div className="flex-between">
                <span style={{ fontSize: 12.5 }}>
                  {a.effective_from} → {a.effective_to || "open-ended"}
                </span>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <Badge status={a.status} />
                  <a href={a.file_path} target="_blank" rel="noreferrer" style={{ fontSize: 11.5 }}>View PDF</a>
                </div>
              </div>
              <div className="table-wrap" style={{ marginTop: 6 }}>
                <table className="data-table">
                  <thead><tr><th>Role</th><th>Fee %</th><th>Replacement</th><th>Billable after</th></tr></thead>
                  <tbody>
                    {a.roles.map((r) => (
                      <tr key={r.id}>
                        <td>{r.role_name}</td><td>{r.service_fee_pct}%</td>
                        <td>{r.replacement_days} days</td><td>{r.tenure_days} days</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>

        {/* Hires */}
        <div style={{ marginBottom: 16 }}>
          <div className="flex-between">
            <strong style={{ fontSize: 13 }}>Hires</strong>
            {canManage && <button className="btn btn-sm btn-outline" onClick={() => setShowAssign(true)}>+ Assign Hire</button>}
          </div>
          {hires.length === 0 && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>No hires assigned yet.</div>}
          {hires.map((h) => (
            <div key={h.id} style={{ fontSize: 12, padding: "8px 0", borderBottom: "1px solid var(--color-border)" }}>
              <div className="flex-between">
                <span>
                  {h.candidate_name} — {h.role_name} — ₹{h.ctc.toLocaleString("en-IN")}
                  {h.employee_id && <span className="chip" style={{ marginLeft: 6 }}>Contract Login</span>}
                </span>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <span className="chip blue">{h.placement_type === "contract" ? "Contract" : "Direct"}</span>
                  <span className="chip orange">{h.billing_type === "continuous" ? "Monthly" : "One-time"}</span>
                  {h.is_billable && <span className="chip green">Billable</span>}
                  <Badge status={h.status} />
                </div>
              </div>
              {h.billing_type === "continuous" ? (
                <div className="muted" style={{ fontSize: 10.5, marginTop: 4 }}>
                  Last billed: {h.last_billed_month || "never"}
                </div>
              ) : (
                <div style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ flex: 1, height: 6, background: "var(--color-border)", borderRadius: 4, overflow: "hidden" }}>
                    <div style={{ width: `${h.tenure_progress_pct}%`, height: "100%", background: h.tenure_progress_pct >= 100 ? "var(--color-success)" : "var(--color-primary-500)" }} />
                  </div>
                  <span className="muted" style={{ fontSize: 10.5, whiteSpace: "nowrap" }}>
                    {h.tenure_days_elapsed}/{h.tenure_days_required}d
                  </span>
                </div>
              )}
              {canManage && h.status === "active" && (
                <button className="btn btn-sm btn-outline" style={{ marginTop: 6 }} onClick={() => replaceHire(h.id)}>Replace</button>
              )}
            </div>
          ))}
        </div>

        {/* Invoices */}
        <div>
          <div className="flex-between">
            <strong style={{ fontSize: 13 }}>Invoices</strong>
            {canManage && (
              <div style={{ display: "flex", gap: 6 }}>
                <button className="btn btn-sm btn-outline" disabled={!recurringDueCount || generating} onClick={generateRecurringInvoice}>
                  {generating ? "Generating..." : `Generate Monthly Invoice${recurringDueCount ? ` (${recurringDueCount} due)` : ""}`}
                </button>
                <button className="btn btn-sm btn-primary" disabled={!billableCount || generating} onClick={generateInvoice}>
                  {generating ? "Generating..." : `Generate One-time Invoice${billableCount ? ` (${billableCount} billable)` : ""}`}
                </button>
              </div>
            )}
          </div>
          {invoices.length === 0 && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>No invoices yet.</div>}
          {invoices.map((inv) => (
            <div key={inv.id} style={{ fontSize: 12, padding: "8px 0", borderBottom: "1px solid var(--color-border)" }}>
              <div className="flex-between">
                <span>{inv.invoice_number} — ₹{inv.total_amount.toLocaleString("en-IN")}</span>
                <Badge status={inv.status} />
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                {inv.pdf_path && <a className="btn btn-sm btn-outline" href={inv.pdf_path} target="_blank" rel="noreferrer">View PDF</a>}
                {inv.status === "draft" && canManage && (
                  <button className="btn btn-sm btn-outline" onClick={() => submitForApproval(inv.id)}>Submit for Approval</button>
                )}
                {inv.status === "pending_approval" && canApprove && (
                  <>
                    <button className="btn btn-sm btn-success" onClick={() => approveInvoice(inv.id)}>Approve</button>
                    <button className="btn btn-sm btn-danger" onClick={() => rejectInvoice(inv.id)}>Reject</button>
                  </>
                )}
                {inv.status === "approved" && canManage && (
                  <button className="btn btn-sm btn-success" onClick={() => markPaid(inv.id)}>Mark Paid</button>
                )}
              </div>
            </div>
          ))}
        </div>

        <div style={{ textAlign: "right", marginTop: 16 }}>
          <button className="btn btn-outline" onClick={onClose}>Close</button>
        </div>
      </div>

      {showAssign && (
        <AssignHireModal
          vendor={vendor}
          onClose={() => setShowAssign(false)}
          onAssigned={() => { setShowAssign(false); load(); onChanged && onChanged(); }}
        />
      )}
    </div>
  );
}
