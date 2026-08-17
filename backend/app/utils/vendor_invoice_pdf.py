"""
Generates a professional tax invoice PDF for a vendor billing, matching the
layout/fields of the reference invoices this feature was built from:
letterhead, invoice no/date block, buyer block, candidate/CTC particulars
table, CGST/SGST breakdown, amount in words, bank details, declaration,
and signatory line.
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT

from app.utils.number_to_words import number_to_words_inr

NAVY = colors.HexColor("#062454")
ORANGE = colors.HexColor("#F2650A")
BORDER = colors.HexColor("#B8C2D9")
LIGHT = colors.HexColor("#F5F6FB")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8.5, leading=11))
    ss.add(ParagraphStyle("SmallBold", parent=ss["Small"], fontName="Helvetica-Bold"))
    ss.add(ParagraphStyle("InvoiceTitle", parent=ss["Normal"], fontSize=15, leading=18,
                           fontName="Helvetica-Bold", alignment=1, textColor=NAVY))
    ss.add(ParagraphStyle("RightSmall", parent=ss["Small"], alignment=TA_RIGHT))
    return ss


def generate_vendor_invoice_pdf(
    output_path,
    invoice_number, invoice_date_str,
    vendor, company,  # dicts: name, address, gstin, pan, bank_name/account/ifsc/branch (vendor only)
    line_items,  # list of dicts: candidate_name, role_name, ctc, fee_pct, fee_amount
    subtotal, cgst_amount, sgst_amount, igst_amount, total_amount,
    hsn_sac="9985",
):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=14 * mm, bottomMargin=14 * mm, leftMargin=14 * mm, rightMargin=14 * mm,
    )
    ss = _styles()
    story = []

    story.append(Paragraph("TAX INVOICE", ss["InvoiceTitle"]))
    story.append(Spacer(1, 8))

    # --- Header: vendor letterhead | invoice no/date ---
    vendor_block = Paragraph(
        f"<b>{vendor['name']}</b><br/>{(vendor.get('address') or '').replace(chr(10), '<br/>')}"
        f"<br/>GSTIN: {vendor.get('gstin') or '—'}",
        ss["Small"],
    )
    meta_block = Paragraph(
        f"<b>Invoice No.</b><br/>{invoice_number}<br/><br/>"
        f"<b>Dated</b><br/>{invoice_date_str}<br/><br/>"
        f"<b>Mode/Terms of Payment</b><br/>A/C Transfer",
        ss["Small"],
    )
    header_table = Table([[vendor_block, meta_block]], colWidths=[110 * mm, 66 * mm])
    header_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.75, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_table)

    # --- Buyer block ---
    buyer_block = Paragraph(
        f"<b>Buyer</b><br/><b>{company['company_name']}</b><br/>"
        f"{(company.get('address') or '').replace(chr(10), '<br/>')}"
        f"<br/>GSTIN: {company.get('gstin') or '—'}",
        ss["Small"],
    )
    buyer_table = Table([[buyer_block]], colWidths=[176 * mm])
    buyer_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(buyer_table)
    story.append(Spacer(1, 8))

    # --- Particulars table ---
    header_row = ["Sl No.", "Particulars", "HSN/SAC", "CTC", "Rate", "Amount"]
    rows = [header_row]

    for idx, item in enumerate(line_items, start=1):
        particulars = f"{item['candidate_name']}" + (f" — {item['role_name']}" if item.get("role_name") else "")
        rows.append([
            str(idx), particulars, hsn_sac,
            f"{item['ctc']:,.0f}", f"{item['fee_pct']}%", f"{item['fee_amount']:,.2f}",
        ])

    rows.append(["", "Sub Total", "", "", "", f"{subtotal:,.2f}"])
    if cgst_amount:
        rows.append(["", "CGST", "", "", "9%", f"{cgst_amount:,.2f}"])
        rows.append(["", "SGST", "", "", "9%", f"{sgst_amount:,.2f}"])
    if igst_amount:
        rows.append(["", "IGST", "", "", "18%", f"{igst_amount:,.2f}"])
    rows.append(["", "Total", "", "", "", f"INR {total_amount:,.2f}"])

    particulars_table = Table(
        rows, colWidths=[14 * mm, 68 * mm, 20 * mm, 24 * mm, 20 * mm, 30 * mm], repeatRows=1
    )
    style = [
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, NAVY),
    ]
    particulars_table.setStyle(TableStyle(style))
    story.append(particulars_table)
    story.append(Spacer(1, 8))

    # --- Amount in words ---
    words = number_to_words_inr(total_amount)
    story.append(Paragraph(f"<b>Amount Chargeable (in words):</b> INR {words}", ss["Small"]))
    story.append(Spacer(1, 10))

    # --- Bank details + declaration ---
    bank_text = (
        f"<b>Vendor's Bank Details</b><br/>"
        f"Bank Name: {vendor.get('bank_name') or '—'}<br/>"
        f"A/c No.: {vendor.get('bank_account_no') or '—'}<br/>"
        f"Branch: {vendor.get('bank_branch') or '—'}<br/>"
        f"IFSC: {vendor.get('bank_ifsc') or '—'}<br/>"
        f"PAN: {vendor.get('pan') or '—'}"
    )
    declaration_text = (
        "<b>Declaration</b><br/>"
        "We declare that this invoice being raised is against professional "
        "recruitment services provided to your organization."
    )
    info_table = Table(
        [[Paragraph(bank_text, ss["Small"]), Paragraph(declaration_text, ss["Small"])]],
        colWidths=[88 * mm, 88 * mm],
    )
    info_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.75, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 22))

    # --- Signatory ---
    story.append(Paragraph(f"for {vendor['name']}", ss["RightSmall"]))
    story.append(Spacer(1, 18))
    story.append(Paragraph("Authorized Signatory", ss["RightSmall"]))
    story.append(Spacer(1, 14))
    story.append(Paragraph("This is a computer generated Invoice.", ss["Small"]))

    doc.build(story)
    return output_path
