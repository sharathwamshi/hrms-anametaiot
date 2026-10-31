import { useState } from "react";
import client from "../api/client";

const MONTH_NAMES = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const THEMES = {
  "Ana Meta IoT": { primary: "#633a9b", accent: "#f28c28" },
  "Acknowledger First Pvt Ltd": { primary: "#12345a", accent: "#20a6a6" },
  "Vkalpa Innovations": { primary: "#173a63", accent: "#76bce8" },
};

export default function PayslipDetailModal({ payslip, onClose, onDownload }) {
  const [error, setError] = useState("");
  const employee = payslip.employee_info || {};
  const theme = THEMES[payslip.company_name] || THEMES["Ana Meta IoT"];
  const isAnaMeta = payslip.company_name === "Ana Meta IoT";
  const isVkalpa = payslip.company_name === "Vkalpa Innovations";
  const infoSurface = isAnaMeta ? "#fbf8fe" : isVkalpa ? "#f2f9fd" : "#f7fafc";
  const infoBorder = isAnaMeta ? theme.accent : isVkalpa ? "#d7eaf7" : "#dce3eb";
  const inr = (value) => `₹${Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const details = [
    ["Employee Name", employee.full_name || payslip.employee_name],
    ["Employee ID", employee.employee_code],
    ["Designation", employee.designation],
    ["Department", employee.department],
    ["Date of Joining", employee.date_of_joining],
    ["PAN number", employee.pan],
    ["PF number", employee.pf_number],
    ["UAN number", employee.uan_number || employee.uan],
    ["Bank name", employee.bank_name],
    ["Bank account number", employee.bank_account_number],
    ["Pay mode", employee.pay_mode],
    ["Location", employee.location],
    ["Total working days", payslip.total_working_days],
    ["Total paid days", payslip.total_paid_days],
    ["Present days", payslip.days_present],
    ["LOP days", payslip.lop_days],
  ];

  const downloadPdf = async () => {
    if (onDownload) {
      onDownload();
      return;
    }
    if (!payslip.id) return;
    setError("");
    try {
      const { data } = await client.get(`/payroll/payslips/${payslip.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${employee.employee_code || payslip.user_id}_${payslip.year}_${String(payslip.month).padStart(2, "0")}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not download the payslip PDF.");
    }
  };

  const columns = [
    ["Earnings", payslip.earnings || [], "Total Earnings", payslip.gross_earnings, theme.primary],
    ["Deductions", payslip.deductions || [], "Total Deductions", payslip.total_deductions, theme.accent],
  ];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box payslip-print" style={{ width: "min(760px, 96vw)", maxHeight: "92vh", overflowY: "auto" }} onClick={(event) => event.stopPropagation()}>
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", border: `1px solid ${theme.primary}`, borderBottom: `3px solid ${theme.accent}`, background: isAnaMeta ? theme.primary : isVkalpa ? "#eaf5fc" : "#f6f8fb", padding: 14, gap: 12 }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 20, color: isAnaMeta ? "white" : theme.primary }}>{payslip.company_name || "Ana Meta IoT"}</div>
            <div style={{ fontSize: 12, color: isAnaMeta ? "#f4eefe" : "var(--color-text-muted)" }}>PAYSLIP · {MONTH_NAMES[payslip.month - 1]} {payslip.year}</div>
          </div>
          <div style={{ fontSize: 12, color: isAnaMeta ? "white" : theme.primary, textAlign: "right" }}>
            <strong>{payslip.total_working_days || 0} working days</strong>
            <div>{payslip.status}</div>
          </div>
        </header>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", border: `1px solid ${infoBorder}`, borderTop: 0, background: infoSurface, marginBottom: 12 }}>
          {details.map(([label, value]) => (
            <div key={label} style={{ padding: "8px 7px", border: `1px solid ${infoBorder}`, minWidth: 0, fontSize: 11.5, overflowWrap: "anywhere" }}>
              <span className="muted">{label}</span>
              <div style={{ fontWeight: 600, marginTop: 3 }}>{value === 0 ? 0 : value || "—"}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
          {columns.map(([title, rows, totalTitle, totalValue, color]) => (
            <section key={title} style={{ border: "1px solid var(--color-border)" }}>
              <div style={{ background: color, color: "white", padding: 8, fontWeight: 700 }}>{title}</div>
              {(rows.length ? rows : [{ name: "Component detail unavailable", amount: 0 }]).map((row, index) => (
                <div key={`${title}-${index}`} style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "7px 8px", borderBottom: "1px solid #edf0f4", fontSize: 12 }}>
                  <span>{row.name}</span><span>{inr(row.amount)}</span>
                </div>
              ))}
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: 8, fontWeight: 700, borderTop: `1px solid ${color}`, fontSize: 12 }}>
                <span>{totalTitle}</span><span>{inr(totalValue)}</span>
              </div>
            </section>
          ))}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, background: isVkalpa ? "#e5f3fc" : theme.primary, color: isVkalpa ? theme.primary : "white", border: isVkalpa ? `1px solid ${theme.primary}` : `1px solid ${theme.accent}`, borderLeft: isVkalpa ? `5px solid ${theme.accent}` : undefined, padding: "12px 14px", marginTop: 12, fontWeight: 800, fontSize: 16 }}>
          <span>Net Pay</span><span>{inr(payslip.net_pay)}</span>
        </div>
        <p style={{ fontSize: 12, marginTop: 9 }}><strong>Net Pay in words:</strong> INR {payslip.amount_in_words || "—"}</p>
        <p className="muted" style={{ fontSize: 10.5, marginTop: 10 }}>This is a system-generated payslip and does not require a signature.</p>
        {error && <div className="login-error" role="alert">{error}</div>}

        <div className="no-print" style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <button className="btn btn-outline" onClick={onClose}>Close</button>
          {payslip.id && <button className="btn btn-outline" onClick={downloadPdf}>Download PDF</button>}
          <button className="btn btn-primary" onClick={() => window.print()}>Print Payslip</button>
        </div>
      </div>
    </div>
  );
}
