import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import ExportButton from "../components/ExportButton";
import client from "../api/client";
import AppLayout from "../components/AppLayout";
import Badge from "../components/Badge";
import Loader from "../components/Loader";
import VendorDetailModal from "../components/VendorDetailModal";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";

const TABS_BY_ROLE = {
  [ROLES.FINANCE_ACCOUNTS]: ["overview", "vendors", "invoices"],
  [ROLES.HR_OPERATIONS]: ["overview", "vendors", "invoices"],
  [ROLES.MANAGER]: ["overview", "vendors", "invoices"],
  [ROLES.OPERATIONS]: ["overview", "vendors", "invoices"],
};

export default function Vendors() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const canCreate = [ROLES.FINANCE_ACCOUNTS, ROLES.HR_OPERATIONS, ROLES.OPERATIONS].includes(user.role);
  const tabs = TABS_BY_ROLE[user.role] || ["overview"];
  const [tab, setTab] = useState(
    location.state?.vendorId || location.state?.tab === "vendors" ? "vendors" : tabs[0],
  );
  const addVendor = () => navigate("/vendors/new");

  return (
    <AppLayout title="Vendors" subtitle="Recruitment vendor agreements, hires, and billing.">
      <div className="tag-list section-gap">
        {tabs.map((t) => (
          <button key={t} className={`btn btn-sm ${tab === t ? "btn-primary" : "btn-outline"}`} onClick={() => setTab(t)}>
            {{ overview: "Overview", vendors: "Vendors", invoices: "All Invoices" }[t]}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab canCreate={canCreate} onAddVendor={addVendor} onGoToVendors={() => setTab("vendors")} />}
      {tab === "vendors" && <VendorsTab canCreate={canCreate} initialVendorId={location.state?.vendorId} />}
      {tab === "invoices" && <InvoicesTab />}
    </AppLayout>
  );
}

// ============================================================================
// Overview — the dashboard "wow" landing view
// ============================================================================

function OverviewTab({ canCreate, onAddVendor, onGoToVendors }) {
  const [vendors, setVendors] = useState([]);
  const [hires, setHires] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedVendorId, setSelectedVendorId] = useState(null);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [vRes, hRes, iRes] = await Promise.all([
        client.get("/vendors"), client.get("/vendors/hires"), client.get("/vendors/invoices"),
      ]);
      setVendors(vRes.data);
      setHires(hRes.data);
      setInvoices(iRes.data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load vendor overview.");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  if (loading) return <Loader />;
  if (error) return <div className="card"><div className="login-error" role="alert">{error}</div><button className="btn btn-outline" onClick={load}>Retry</button></div>;

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
    .flatMap((vendor) => (vendor.expiring_agreements || []).map((agreement) => ({
      vendor,
      agreement,
      daysLeft: agreement.days_remaining,
    })))
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
            <span className="muted" style={{ fontSize: 11 }}>Within 7 days</span>
          </div>
          {expiringAgreements.length === 0 && <div className="muted" style={{ fontSize: 13 }}>Nothing expiring soon.</div>}
          {expiringAgreements.map(({ vendor, agreement, daysLeft }) => (
            <div key={agreement.id} onClick={() => setSelectedVendorId(vendor.id)}
              className="flex-between" style={{ padding: "8px 0", borderBottom: "1px solid var(--color-border)", fontSize: 12.5, cursor: "pointer" }}>
              <span>{vendor.name} — {agreement.title || "Agreement"} · expires {agreement.expiry_date}</span>
              <span className="chip orange">{daysLeft} day(s) left</span>
            </div>
          ))}
        </div>
      </div>

      {canCreate && (
        <div className="card section-gap" style={{ marginTop: 20 }}>
          <div className="card-title-row">
            <h3>Onboard a Vendor</h3>
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>
            Create a vendor and add its agreement, role details, and signed PDF together.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" onClick={onAddVendor}>+ Add Vendor &amp; Agreement</button>
            <button className="btn btn-outline" onClick={onGoToVendors}>View All Vendors</button>
          </div>
        </div>
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

function VendorsTab({ canCreate, initialVendorId = null }) {
  const navigate = useNavigate();
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedVendorId, setSelectedVendorId] = useState(initialVendorId);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [agreementFilter, setAgreementFilter] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await client.get("/vendors", {
        params: {
          ...(search ? { q: search } : {}),
          ...(statusFilter ? { status: statusFilter } : {}),
          ...(agreementFilter ? { agreement_status: agreementFilter } : {}),
        },
      });
      setVendors(data);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load vendors.");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [search, statusFilter, agreementFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const expiringCount = vendors.reduce((total, vendor) => total + vendor.expiring_agreement_count, 0);
  const expiredCount = vendors.reduce((total, vendor) => total + vendor.expired_agreement_count, 0);

  return (
    <>
      <div className="stat-grid">
        <div className="stat-card"><div><div className="label">Total Vendors</div><div className="value">{vendors.length}</div></div></div>
        <div className="stat-card"><div><div className="label">Expiring in 7 Days</div><div className="value">{expiringCount}</div></div></div>
        <div className="stat-card"><div><div className="label">Expired Agreements</div><div className="value">{expiredCount}</div></div></div>
      </div>
      <div className="card">
        <div className="card-title-row">
          <h3>All Vendors</h3>
          {canCreate && <button className="btn btn-primary btn-sm" onClick={() => navigate("/vendors/new")}>+ Add Vendor &amp; Agreement</button>}
        </div>
        {error && <div className="login-error" role="alert">{error}</div>}
        <div className="vendor-filters">
          <input
            type="search"
            aria-label="Search vendors"
            placeholder="Search name, GSTIN, PAN, contact or email"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <select aria-label="Filter vendors by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">All vendor statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
          <select aria-label="Filter vendors by agreement status" value={agreementFilter} onChange={(event) => setAgreementFilter(event.target.value)}>
            <option value="">All agreement statuses</option>
            <option value="upcoming">Upcoming</option>
            <option value="active">Active</option>
            <option value="expiring_soon">Expiring Soon</option>
            <option value="expired">Expired</option>
            <option value="terminated">Terminated</option>
          </select>
        </div>
        {loading ? <Loader /> : vendors.length === 0 ? (
          <div className="muted" style={{ fontSize: 13, padding: 18 }}>
            {search || statusFilter || agreementFilter ? "No vendors match these filters." : "No vendors yet — upload an agreement or add one directly."}
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data-table vendor-directory-table">
              <thead>
                <tr><th>Company</th><th>Vendor</th><th>Contact</th><th>GSTIN</th><th>Status</th><th>Agreements</th><th>Agreement Expiry</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {vendors.map((vendor) => (
                  <tr key={vendor.id}>
                    <td>{vendor.company_name || "—"}</td>
                    <td>
                      <button className="vendor-name-link" onClick={() => setSelectedVendorId(vendor.id)}>{vendor.name}</button>
                      <div className="muted" style={{ fontSize: 11 }}>{vendor.state || "—"}</div>
                    </td>
                    <td>
                      {vendor.contact_person || "—"}
                      <div className="muted" style={{ fontSize: 11 }}>{vendor.contact_email || vendor.contact_phone || ""}</div>
                    </td>
                    <td>{vendor.gstin || "—"}</td>
                    <td><Badge status={vendor.status} /></td>
                    <td>{vendor.agreement_count}</td>
                    <td>
                      {vendor.agreement_status ? (
                        <><Badge status={vendor.agreement_status} />{vendor.agreement_title && <div className="muted" style={{ fontSize: 11 }}>{vendor.agreement_title}</div>}{vendor.agreement_expiry && <div className="muted" style={{ fontSize: 11 }}>{vendor.agreement_expiry}</div>}</>
                      ) : "—"}
                    </td>
                    <td>
                      <button className="btn btn-sm btn-outline" onClick={() => setSelectedVendorId(vendor.id)}>View</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedVendorId && (
        <VendorDetailModal vendorId={selectedVendorId} onClose={() => setSelectedVendorId(null)} onChanged={load} />
      )}
    </>
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
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <ExportButton filename="Vendor_Invoices" />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ border: "1px solid var(--color-border)", borderRadius: 6, padding: "6px 10px" }}>
            <option value="">All statuses</option>
            <option value="draft">Draft</option>
            <option value="pending_approval">Pending Approval</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="paid">Paid</option>
          </select>
        </div>
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
