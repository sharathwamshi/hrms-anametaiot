import { useEffect, useState } from "react";
import client from "../api/client";

const MONTH_NAMES = ["January","February","March","April","May","June","July","August","September","October","November","December"];

export default function PayslipDetailModal({ payslip, onClose }) {
  const [structure, setStructure] = useState(null);
  const [employee, setEmployee] = useState(null);

  useEffect(() => {
    client.get(`/employees/${payslip.user_id}`).then(({ data }) => setEmployee(data)).catch(() => {});
    client.get(`/payroll/structure/${payslip.user_id}`).then(({ data }) => setStructure(data)).catch(() => setStructure(null));
  }, [payslip.user_id]);

  const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box payslip-print" style={{ width: 620 }} onClick={(e) => e.stopPropagation()}>
        <div className="payslip-header">
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: 18, color: "var(--color-navy-900)" }}>
              AnametaIOT
            </div>
            <div className="muted" style={{ fontSize: 11.5 }}>Payslip for {MONTH_NAMES[payslip.month - 1]} {payslip.year}</div>
          </div>
          <div className="muted" style={{ fontSize: 10.5, textAlign: "right" }}>
            Powered by <strong style={{ color: "var(--color-primary-600)" }}>+veGroww</strong>
          </div>
        </div>

        <div className="payslip-employee-grid">
          <div><span className="pl">Employee</span><span className="pv">{employee?.full_name || payslip.employee_name || "—"}</span></div>
          <div><span className="pl">Employee Code</span><span className="pv">{employee?.employee_code || "—"}</span></div>
          <div><span className="pl">Designation</span><span className="pv">{employee?.designation || "—"}</span></div>
          <div><span className="pl">Department</span><span className="pv">{employee?.department || "—"}</span></div>
          <div><span className="pl">Days Present</span><span className="pv">{payslip.days_present}</span></div>
          <div><span className="pl">Loss of Pay Days</span><span className="pv">{payslip.lop_days}</span></div>
        </div>

        <div className="payslip-columns">
          <div>
            <div className="payslip-col-title">Earnings</div>
            <div className="payslip-row"><span>Basic</span><span>{inr(structure?.basic)}</span></div>
            <div className="payslip-row"><span>HRA</span><span>{inr(structure?.hra)}</span></div>
            <div className="payslip-row"><span>Special Allowance</span><span>{inr(structure?.special_allowance)}</span></div>
            <div className="payslip-row"><span>Other Allowance</span><span>{inr(structure?.other_allowance)}</span></div>
            <div className="payslip-row payslip-total"><span>Gross Earnings</span><span>{inr(payslip.gross_earnings)}</span></div>
          </div>
          <div>
            <div className="payslip-col-title">Deductions</div>
            <div className="payslip-row"><span>Provident Fund</span><span>{inr(structure?.pf_employee)}</span></div>
            <div className="payslip-row"><span>ESI</span><span>{inr(structure?.esi_employee)}</span></div>
            <div className="payslip-row"><span>Insurance</span><span>{inr(structure?.insurance)}</span></div>
            <div className="payslip-row"><span>Professional Tax</span><span>{inr(structure?.professional_tax)}</span></div>
            <div className="payslip-row"><span>TDS</span><span>{inr(structure?.tds)}</span></div>
            <div className="payslip-row payslip-total"><span>Total Deductions</span><span>{inr(payslip.total_deductions)}</span></div>
          </div>
        </div>

        <div className="payslip-net">
          <span>Net Pay</span>
          <span>{inr(payslip.net_pay)}</span>
        </div>

        <div className="muted" style={{ fontSize: 10, marginTop: 10 }}>
          This is a system-generated payslip and does not require a signature.
        </div>

        <div className="no-print" style={{ textAlign: "right", marginTop: 18, display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button className="btn btn-outline" onClick={onClose}>Close</button>
          {payslip.pdf_path && (
            <a className="btn btn-outline" href={payslip.pdf_path} target="_blank" rel="noreferrer" download>
              Download PDF
            </a>
          )}
          <button className="btn btn-primary" onClick={() => window.print()}>Print / Save as PDF</button>
        </div>
      </div>
    </div>
  );
}
