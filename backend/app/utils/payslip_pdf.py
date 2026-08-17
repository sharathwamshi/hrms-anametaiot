"""
Generates a professional, downloadable payslip PDF — company letterhead,
employee details, earnings/deductions breakdown, and net pay. Pure Python
(reportlab), no external binary needed.
"""
import os
import calendar
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.utils.number_to_words import number_to_words_inr

NAVY = colors.HexColor("#062454")
BORDER = colors.HexColor("#B8C2D9")

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8.5, leading=11))
    ss.add(ParagraphStyle("PayslipTitle", parent=ss["Normal"], fontSize=15, leading=18,
                           fontName="Helvetica-Bold", alignment=1, textColor=NAVY))


def generate_payslip_pdf(
    output_path,
    company,  # dict: company_name, address
    employee,  # dict: full_name, employee_code, designation, department
    month, year,
    structure,  # dict: basic, hra, special_allowance, other_allowance, pf_employee, esi_employee, professional_tax, tds
    days_present, days_on_leave, lop_days,
    gross_earnings, total_deductions, net_pay,
):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=14 * mm, bottomMargin=14 * mm, leftMargin=14 * mm, rightMargin=14 * mm,
    )
    ss = getSampleStyleSheet()
    small = ParagraphStyle("Small", parent=ss["Normal"], fontSize=8.5, leading=11)
    title = ParagraphStyle("PayslipTitle", parent=ss["Normal"], fontSize=15, leading=18,
                            fontName="Helvetica-Bold", alignment=1, textColor=NAVY)
    story = []

    story.append(Paragraph(f"PAYSLIP — {MONTH_NAMES[month]} {year}", title))
    story.append(Spacer(1, 8))

    company_block = Paragraph(
        f"<b>{company['company_name']}</b><br/>{(company.get('address') or '').replace(chr(10), '<br/>')}",
        small,
    )
    days_in_month = calendar.monthrange(year, month)[1]
    meta_block = Paragraph(
        f"<b>Pay Period</b><br/>{MONTH_NAMES[month]} {year} ({days_in_month} days)<br/><br/>"
        f"<b>Days Present</b>: {days_present} &nbsp; <b>LOP</b>: {lop_days}",
        small,
    )
    header_table = Table([[company_block, meta_block]], colWidths=[110 * mm, 66 * mm])
    header_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.75, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))

    emp_block = Paragraph(
        f"<b>Employee</b><br/><b>{employee['full_name']}</b> ({employee.get('employee_code') or '—'})<br/>"
        f"{employee.get('designation') or '—'} · {employee.get('department') or '—'}",
        small,
    )
    emp_table = Table([[emp_block]], colWidths=[176 * mm])
    emp_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(emp_table)
    story.append(Spacer(1, 8))

    earnings_rows = [
        ["Earnings", "Amount"],
        ["Basic", f"{structure.get('basic', 0):,.2f}"],
        ["HRA", f"{structure.get('hra', 0):,.2f}"],
        ["Special Allowance", f"{structure.get('special_allowance', 0):,.2f}"],
        ["Other Allowance", f"{structure.get('other_allowance', 0):,.2f}"],
        ["Gross Earnings", f"{gross_earnings:,.2f}"],
    ]
    deductions_rows = [
        ["Deductions", "Amount"],
        ["Provident Fund", f"{structure.get('pf_employee', 0):,.2f}"],
        ["ESI", f"{structure.get('esi_employee', 0):,.2f}"],
        ["Professional Tax", f"{structure.get('professional_tax', 0):,.2f}"],
        ["TDS", f"{structure.get('tds', 0):,.2f}"],
        ["Total Deductions", f"{total_deductions:,.2f}"],
    ]

    def styled_table(rows, width_left):
        t = Table(rows, colWidths=[width_left, 30 * mm])
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 1, NAVY),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    earnings_table = styled_table(earnings_rows, 55 * mm)
    deductions_table = styled_table(deductions_rows, 55 * mm)
    side_by_side = Table([[earnings_table, deductions_table]], colWidths=[88 * mm, 88 * mm])
    side_by_side.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(side_by_side)
    story.append(Spacer(1, 12))

    net_table = Table([["Net Pay", f"INR {net_pay:,.2f}"]], colWidths=[146 * mm, 30 * mm])
    net_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(net_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph(f"<b>Net Pay (in words):</b> INR {number_to_words_inr(net_pay)}", small))
    story.append(Spacer(1, 20))
    story.append(Paragraph("This is a system-generated payslip and does not require a signature.", small))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Powered by <b>+veGroww</b>", small))

    doc.build(story)
    return output_path
