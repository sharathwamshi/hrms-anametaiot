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
from xml.sax.saxutils import escape

from app.utils.number_to_words import number_to_words_inr

BORDER = colors.HexColor("#B8C2D9")
COMPANY_THEMES = {
    "Ana Meta IoT": (colors.HexColor("#633A9B"), colors.HexColor("#F28C28")),
    "Acknowledger First Pvt Ltd": (colors.HexColor("#12345A"), colors.HexColor("#20A6A6")),
    "Vkalpa Innovations": (colors.HexColor("#173A63"), colors.HexColor("#76BCE8")),
}
COMPANY_ADDRESSES = {
    "Ana Meta IoT": os.environ.get("ANA_META_IOT_ADDRESS", ""),
    "Acknowledger First Pvt Ltd": os.environ.get("ACKNOWLEDGER_FIRST_ADDRESS", ""),
    "Vkalpa Innovations": os.environ.get("VKALPA_INNOVATIONS_ADDRESS", ""),
}

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def generate_payslip_pdf(
    output_path,
    company,  # dict: company_name, address
    employee,  # dict: full_name, employee_code, designation, department
    month, year,
    structure,  # dict: basic, hra, special_allowance, other_allowance, pf_employee, esi_employee, professional_tax, tds
    days_present, days_on_leave, lop_days,
    gross_earnings, total_deductions, net_pay,
    employee_info=None, earnings=None, deductions=None,
    total_working_days=None, total_paid_days=None,
):
    company_name = company.get("company_name") or "Ana Meta IoT"
    employee_info = {
        "full_name": employee.get("full_name"),
        "employee_code": employee.get("employee_code"),
        "designation": employee.get("designation"),
        "department": employee.get("department"),
        **(employee_info or {}),
    }
    if earnings is None:
        earnings = [
            {"name": name, "amount": structure.get(field, 0)}
            for name, field in (
                ("Basic Salary", "basic"), ("House Rent Allowance", "hra"),
                ("Special Allowance", "special_allowance"), ("Other Earnings", "other_allowance"),
            )
            if structure.get(field, 0)
        ]
    if deductions is None:
        deductions = [
            {"name": name, "amount": structure.get(field, 0)}
            for name, field in (
                ("Provident Fund (PF)", "pf_employee"), ("Employee State Insurance (ESI)", "esi_employee"),
                ("Insurance", "insurance"), ("Professional Tax", "professional_tax"), ("Income Tax (TDS)", "tds"),
            )
            if structure.get(field, 0)
        ]
    return generate_company_payslip_pdf(
        output_path,
        company_name=company_name,
        company_address=company.get("address") or "",
        employee_info=employee_info,
        month=month,
        year=year,
        earnings=earnings,
        deductions=deductions,
        days_present=days_present,
        days_on_leave=days_on_leave,
        lop_days=lop_days,
        total_working_days=total_working_days or calendar.monthrange(year, month)[1],
        total_paid_days=total_paid_days if total_paid_days is not None else days_present + days_on_leave,
        gross_earnings=gross_earnings,
        total_deductions=total_deductions,
        net_pay=net_pay,
    )


def generate_company_payslip_pdf(
    output_path, *, company_name, company_address, employee_info, month, year,
    earnings, deductions, days_present, days_on_leave, lop_days,
    total_working_days, total_paid_days, gross_earnings, total_deductions, net_pay,
):
    """Render one A4 payslip using the assigned company's own color theme."""
    primary, accent = COMPANY_THEMES.get(company_name, COMPANY_THEMES["Ana Meta IoT"])
    company_address = company_address or COMPANY_ADDRESSES.get(company_name, "")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=12 * mm, bottomMargin=12 * mm, leftMargin=12 * mm, rightMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("PayslipNormal", parent=styles["Normal"], fontSize=8.3, leading=10.5)
    small = ParagraphStyle("PayslipSmall", parent=normal, fontSize=7.6, leading=9)
    title = ParagraphStyle(
        "PayslipTitle", parent=styles["Normal"], fontSize=16, leading=19,
        fontName="Helvetica-Bold", textColor=primary,
    )
    subtitle = ParagraphStyle("PayslipSubtitle", parent=small, textColor=colors.HexColor("#536174"))
    story = []
    safe = lambda value: escape(str(value if value not in (None, "") else "—"))

    address = safe(company_address).replace("\n", "<br/>") or "Company address placeholder"
    period = Paragraph(
        f"<b>PAYSLIP</b><br/>{MONTH_NAMES[month]} {year}<br/>"
        f"{total_working_days:g} working days",
        ParagraphStyle("Period", parent=normal, alignment=2, textColor=primary),
    )
    if company_name == "Ana Meta IoT":
        white_title = ParagraphStyle(
            "AnaMetaTitle", parent=title, alignment=1, textColor=colors.white,
        )
        white_small = ParagraphStyle(
            "AnaMetaSmall", parent=small, alignment=1, textColor=colors.white,
        )
        header = Table(
            [[
                Paragraph(safe(company_name), white_title),
                Paragraph(f"<b>{MONTH_NAMES[month]} {year}</b><br/>PAYSLIP", white_small),
            ], [
                Paragraph(address, white_small),
                Paragraph(f"{total_working_days:g} working days", white_small),
            ]],
            colWidths=[130 * mm, 54 * mm],
        )
        header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), primary),
            ("BOX", (0, 0), (-1, -1), 1, primary),
            ("LINEBELOW", (0, 1), (-1, 1), 3, accent),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
    elif company_name == "Acknowledger First Pvt Ltd":
        company_block = [
            Paragraph(safe(company_name), title),
            Paragraph(address, subtitle),
        ]
        header = Table([[company_block, period]], colWidths=[130 * mm, 54 * mm])
        header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6F8FB")),
            ("BOX", (0, 0), (-1, -1), 1, primary),
            ("LINEBELOW", (0, 0), (-1, 0), 2, accent),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
    else:
        modern_title = ParagraphStyle("VkalpaTitle", parent=title, fontSize=17, leading=20)
        modern_meta = ParagraphStyle(
            "VkalpaPeriod", parent=normal, alignment=2, textColor=primary,
        )
        header = Table(
            [[
                [Paragraph(safe(company_name), modern_title), Paragraph(address, subtitle)],
                Paragraph(
                    f"<font color='#76BCE8'><b>PAY PERIOD</b></font><br/>"
                    f"<b>{MONTH_NAMES[month]} {year}</b><br/>{total_working_days:g} working days",
                    modern_meta,
                ),
            ]],
            colWidths=[130 * mm, 54 * mm],
        )
        header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.white),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#EAF5FC")),
            ("BOX", (0, 0), (-1, -1), 0.75, accent),
            ("LINEBELOW", (0, 0), (-1, -1), 2, primary),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
    story.extend([header, Spacer(1, 8)])

    details = [
        ("Employee Name", employee_info.get("full_name")),
        ("Employee ID", employee_info.get("employee_code")),
        ("Designation", employee_info.get("designation")),
        ("Department", employee_info.get("department")),
        ("Date of Joining", employee_info.get("date_of_joining")),
        ("PAN", employee_info.get("pan")),
        ("PF Number", employee_info.get("pf_number")),
        ("UAN Number", employee_info.get("uan_number") or employee_info.get("uan")),
        ("Bank Name", employee_info.get("bank_name")),
        ("Bank Account", employee_info.get("bank_account_number")),
        ("Pay Mode", employee_info.get("pay_mode")),
        ("Location", employee_info.get("location")),
        ("Present Days", days_present),
        ("Paid Days", total_paid_days),
        ("LOP Days", lop_days),
        ("Leave Days", days_on_leave),
    ]
    detail_rows = []
    for row_start in range(0, len(details), 4):
        row = []
        for label, value in details[row_start:row_start + 4]:
            row.append(Paragraph(f"<font color='#536174'>{safe(label)}</font><br/><b>{safe(value)}</b>", small))
        while len(row) < 4:
            row.append("")
        detail_rows.append(row)
    info_table = Table(detail_rows, colWidths=[46 * mm] * 4)
    if company_name == "Ana Meta IoT":
        detail_style = [
            ("BOX", (0, 0), (-1, -1), 1, primary),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, accent),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBF8FE")),
        ]
    elif company_name == "Acknowledger First Pvt Ltd":
        detail_style = [
            ("BOX", (0, 0), (-1, -1), 1, primary),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
        ]
    else:
        detail_style = [
            ("BOX", (0, 0), (-1, -1), 0.75, accent),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7EAF7")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F9FD")),
        ]
    info_table.setStyle(TableStyle(detail_style + [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([info_table, Spacer(1, 8)])

    def component_table(heading, entries, total_label, total, header_color):
        rows = [[heading, "Amount"]]
        rows.extend([[safe(item["name"]), f"₹{float(item['amount']):,.2f}"] for item in entries])
        rows.append([total_label, f"₹{float(total):,.2f}"])
        table = Table(rows, colWidths=[66 * mm, 26 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("BACKGROUND", (0, 0), (-1, 0), header_color),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 1, header_color),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        if company_name == "Vkalpa Innovations" and entries:
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 1), (-1, len(rows) - 2), colors.HexColor("#F7FBFE")),
                ("LINEBELOW", (0, 0), (-1, 0), 2, colors.HexColor("#76BCE8")),
            ]))
        return table

    pair = Table(
        [[
            component_table("Earnings", earnings, "Total Earnings", gross_earnings, primary),
            component_table("Deductions", deductions, "Total Deductions", total_deductions, accent),
        ]],
        colWidths=[93 * mm, 93 * mm],
    )
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([pair, Spacer(1, 9)])

    net = Table(
        [["NET PAY", f"₹{float(net_pay):,.2f}"]],
        colWidths=[138 * mm, 48 * mm],
    )
    net_style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]
    if company_name == "Vkalpa Innovations":
        net_style.extend([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E5F3FC")),
            ("TEXTCOLOR", (0, 0), (-1, -1), primary),
            ("BOX", (0, 0), (-1, -1), 1.5, primary),
            ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
        ])
    else:
        net_style.extend([
            ("BACKGROUND", (0, 0), (-1, -1), primary),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 1.25, accent if company_name == "Ana Meta IoT" else primary),
        ])
    net.setStyle(TableStyle(net_style))
    story.extend([
        net, Spacer(1, 7),
        Paragraph(f"<b>Net Pay in words:</b> INR {safe(number_to_words_inr(net_pay))}", normal),
        Spacer(1, 15),
        Paragraph("This is a system-generated payslip and does not require a signature.", small),
        Paragraph("Powered by <b>+veGroww</b>", small),
    ])
    doc.build(story)
    return output_path
