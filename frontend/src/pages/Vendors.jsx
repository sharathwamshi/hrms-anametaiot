import { useEffect, useState } from "react";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import UploadAgreementModal from "../components/UploadAgreementModal";
import AddVendorModal from "../components/AddVendorModal";
import VendorDetailModal from "../components/VendorDetailModal";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";

const TABS_BY_ROLE = {
  [ROLES.FINANCE_ACCOUNTS]: ["overview", "vendors", "invoices"],
  [ROLES.HR_OPERATIONS]: ["overview", "vendors", "invoices"],
  [ROLES.MANAGER]: ["overview", "vendors", "invoices"],
};

export default function Vendors() {
  const { user } = useAuth();
  const canManage = [ROLES.FINANCE_ACCOUNTS, ROLES.HR_OPERATIONS].includes(user.role);
  const tabs = TABS_BY_ROLE[user.role] || ["overview"];
  const [tab, setTab] = useState(tabs[0]);

  return (
    <AppLayout title="Vendors" subtitle="Recruitment vendor agreements, hires, and billing.">
      <div className="tag-list section-gap">
        {tabs.map((t) => (
          <button key={t} className={`btn btn-sm ${tab === t ? "btn-primary" : "btn-outline"}`} onClick={() => setTab(t)}>
            {{ overview: "Overview", vendors: "Vendors", invoices: "All Invoices" }[t]}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab canManage={canManage} onGoToVendors={() => setTab("vendors")} />}
      {tab === "vendors" && <VendorsTab canManage={canManage} />}
      {tab === "invoices" && <InvoicesTab />}
    </AppLayout>
  );
}

// ============================================================================
// Overview — the dashboard "wow" landing view
// ============================================================================

function OverviewTab({ canManage, onGoToVendors }) {
  const [vendors, setVendors] = useState([]);
  const [hires, setHires] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [showAddVendor, setShowAddVendor] = useState(false);
  const [selectedVendorId, setSelectedVendorId] = useState(null);

  const load = async () => {
    setLoading(true);
    const [vRes, hRes, iRes] = await Promise.all([
      client.get("/vendors"), client.get("/vendors/hires"), client.get("/vendors/invoices"),
    ]);
    setVendors(vRes.data);
    setHires(hRes.data);
    setInvoices(iRes.data);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  if (loading) return <Loader />;

  const activeVendors = vendors.filter((v) => v.status === "active").length;
  const billableHires = hires.filter((h) => h.is_billable);
  const pendingApproval = invoices.filter((i) => i.status === "pending_approval").length;
  const awaitingPayment = invoices.filter((i) => i.status === "approved");
  const awaitingPaymentTotal = awaitingPayment.reduce((sum, i) => sum + i.total_amount, 0);
  const upcomingTenure = hires
    .filter((h) => h.status === "active" && !h.is_billable && h.tenure_progress_pct >= 70)
    .sort((a, b) => b.tenure_progress_pct - a.tenure_progress_pct)
    .slice(0, 6);

  const expiringAgreements = vendors
    .filter((v) => v.active_agreement?.effective_to)
    .map((v) => ({ vendor: v, daysLeft: Math.ceil((new Date(v.active_agreement.effective_to) - new Date()) / 86400000) }))
    .filter((x) => x.daysLeft <= 60 && x.daysLeft >= 0)
    .sort((a, b) => a.daysLeft - b.daysLeft);

  return (
    <>
      <div className="stat-grid">
        <div className="stat-card"><div><div className="label">Active Vendors</div><div className="value">{activeVendors}</div></div><div className="icon-wrap chip-blue">&#127970;</div></div>
        <div className="stat-card"><div><div className="label">Billable Hires (unbilled)</div><div className="value">{billableHires.length}</div></div><div className="icon-wrap chip-green">&#10003;</div></div>
        <div className="stat-card"><div><div className="label">Invoices Pending Approval</div><div className="value">{pendingApproval}</div></div><div className="icon-wrap chip-amber">&#10071;</div></div>
        <div className="stat-card"><div><div className="label">Approved, Awaiting Payment</div><div className="value">₹{awaitingPaymentTotal.toLocaleString("en-IN")}</div></div><div className="icon-wrap chip-orange">&#8377;</div></div>
      </div>

      <div className="two-col">
        <div className="card">
          <div className="card-title-row">
            <h3>Tenure Nearing Completion</h3>
            <span className="muted" style={{ fontSize: 11 }}>70%+ through their billable tenure</span>
          </div>
          {upcomingTenure.length === 0 && <div className="muted" style={{ fontSize: 13 }}>Nothing approaching its billing date right now.</div>}
          {upcomingTenure.map((h) => (
            <div key={h.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--color-border)" }}>
              <div className="flex-between" style={{ fontSize: 12.5 }}>
                <span>{h.candidate_name} — {h.role_name}</span>
                <span className="muted">{h.tenure_days_elapsed}/{h.tenure_days_required}d</span>
              </div>
              <div style={{ marginTop: 4, height: 6, background: "var(--color-border)", borderRadius: 4, overflow: "hidden" }}>
                <div style={{ width: `${h.tenure_progress_pct}%`, height: "100%", background: "var(--color-primary-500)" }} />
              </div>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-title-row">
            <h3>Agreements Expiring Soon</h3>
            <span className="muted" style={{ fontSize: 11 }}>Within 60 days</span>
          </div>
          {expiringAgreements.length === 0 && <div className="muted" style={{ fontSize: 13 }}>Nothing expiring soon.</div>}
          {expiringAgreements.map(({ vendor, daysLeft }) => (
            <div key={vendor.id} onClick={() => setSelectedVendorId(vendor.id)}
              className="flex-between" style={{ padding: "8px 0", borderBottom: "1px solid var(--color-border)", fontSize: 12.5, cursor: "pointer" }}>
              <span>{vendor.name}</span>
              <span className="chip orange">{daysLeft} day(s) left</span>
            </div>
          ))}
        </div>
      </div>

      {canManage && (
        <div className="card section-gap" style={{ marginTop: 20 }}>
          <div className="card-title-row">
            <h3>Onboard a Vendor</h3>
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>
            Upload a signed agreement — AnametaIOT HRMS reads the vendor, terms, and role-wise fee table automatically.
            Or add a vendor directly if the agreement isn't signed yet.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" onClick={() => setShowUpload(true)}>+ Upload Agreement</button>
            <button className="btn btn-outline" onClick={() => setShowAddVendor(true)}>+ Add Vendor</button>
            <button className="btn btn-outline" onClick={onGoToVendors}>View All Vendors</button>
          </div>
        </div>
      )}

      {showUpload && (
        <UploadAgreementModal
          onClose={() => setShowUpload(false)}
          onSaved={(vendor) => { setShowUpload(false); load(); setSelectedVendorId(vendor.id); }}
        />
      )}
      {showAddVendor && (
        <AddVendorModal
          onClose={() => setShowAddVendor(false)}
          onSaved={(vendor) => { setShowAddVendor(false); load(); setSelectedVendorId(vendor.id); }}
        />
      )}
      {selectedVendorId && (
        <VendorDetailModal vendorId={selectedVendorId} onClose={() => setSelectedVendorId(null)} onChanged={load} />
      )}
    </>
  );
}

// ============================================================================
// Vendors list
// ============================================================================

function VendorsTab({ canManage }) {
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [showAddVendor, setShowAddVendor] = useState(false);
  const [selectedVendorId, setSelectedVendorId] = useState(null);

  const load = async () => {
    setLoading(true);
    const { data } = await client.get("/vendors");
    setVendors(data);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="card">
      <div className="card-title-row">
        <h3>All Vendors</h3>
        {canManage && (
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn btn-outline btn-sm" onClick={() => setShowAddVendor(true)}>+ Add Vendor</button>
            <button className="btn btn-primary btn-sm" onClick={() => setShowUpload(true)}>+ Upload Agreement</button>
          </div>
        )}
      </div>
      {loading ? <Loader /> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {vendors.length === 0 && <div className="muted" style={{ fontSize: 13 }}>No vendors yet — upload an agreement or add one directly.</div>}
          {vendors.map((v) => (
            <div key={v.id} onClick={() => setSelectedVendorId(v.id)}
              style={{ cursor: "pointer", border: "1px solid var(--color-border)", borderRadius: 10, padding: 14 }}>
              <div className="flex-between">
                <div>
                  <strong>{v.name}</strong>
                  <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>
                    {v.agreement_count} agreement(s)
                    {v.active_agreement && ` · active through ${v.active_agreement.effective_to || "open-ended"}`}
                    {v.gstin && ` · GSTIN ${v.gstin}`}
                  </div>
                </div>
                <Badge status={v.status} />
              </div>
            </div>
          ))}
        </div>
      )}

      {showAddVendor && (
        <AddVendorModal
          onClose={() => setShowAddVendor(false)}
          onSaved={(vendor) => { setShowAddVendor(false); load(); setSelectedVendorId(vendor.id); }}
        />
      )}
      {showUpload && (
        <UploadAgreementModal
          onClose={() => setShowUpload(false)}
          onSaved={(vendor) => { setShowUpload(false); load(); setSelectedVendorId(vendor.id); }}
        />
      )}
      {selectedVendorId && (
        <VendorDetailModal vendorId={selectedVendorId} onClose={() => setSelectedVendorId(null)} onChanged={load} />
      )}
    </div>
  );
}

// ============================================================================
// All invoices (cross-vendor)
// ============================================================================

function InvoicesTab() {
  const { user } = useAuth();
  const canManage = [ROLES.FINANCE_ACCOUNTS, ROLES.HR_OPERATIONS].includes(user.role);
  const canApprove = [ROLES.MANAGER, ROLES.HR_OPERATIONS].includes(user.role);

  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");

  const load = async () => {
    setLoading(true);
    const { data } = await client.get("/vendors/invoices", { params: statusFilter ? { status: statusFilter } : {} });
    setInvoices(data);
    setLoading(false);
  };
  useEffect(() => { load(); }, [statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const approveInvoice = async (id) => { await client.post(`/vendors/invoices/${id}/approve`); load(); };
  const rejectInvoice = async (id) => {
    const comment = window.prompt("Reason for rejecting this invoice:");
    await client.post(`/vendors/invoices/${id}/reject`, { comment });
    load();
  };
  const markPaid = async (id) => { await client.post(`/vendors/invoices/${id}/mark-paid`); load(); };
  const submitForApproval = async (id) => { await client.post(`/vendors/invoices/${id}/submit-for-approval`); load(); };

  return (
    <div className="card">
      <div className="card-title-row">
        <h3>All Vendor Invoices</h3>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "6px 10px" }}>
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="pending_approval">Pending Approval</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="paid">Paid</option>
        </select>
      </div>
      {loading ? <Loader /> : (
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Invoice No.</th><th>Vendor</th><th>Date</th><th>Total</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>
              {invoices.length === 0 && <tr className="empty-row"><td colSpan={6}>No invoices found.</td></tr>}
              {invoices.map((inv) => (
                <tr key={inv.id}>
                  <td>{inv.invoice_number}</td>
                  <td>{inv.vendor_name}</td>
                  <td>{inv.invoice_date}</td>
                  <td>₹{inv.total_amount.toLocaleString("en-IN")}</td>
                  <td><Badge status={inv.status} /></td>
                  <td>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {inv.pdf_path && <a className="btn btn-sm btn-outline" href={inv.pdf_path} target="_blank" rel="noreferrer">PDF</a>}
                      {inv.status === "draft" && canManage && (
                        <button className="btn btn-sm btn-outline" onClick={() => submitForApproval(inv.id)}>Submit</button>
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
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
