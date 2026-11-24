import os
import calendar
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from app.utils.number_to_words import number_to_words_inr


PAGE_WIDTH, PAGE_HEIGHT = A4
MONTHS = (
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _hex(value, fallback):
    try:
        return colors.HexColor(value)
    except (TypeError, ValueError):
        return colors.HexColor(fallback)


def _inr(value):
    amount = f"{float(value or 0):.2f}"
    whole, paise = amount.split(".")
    if len(whole) > 3:
        tail, head = whole[-3:], whole[:-3]
        groups = []
        while head:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(groups + [tail])
    return f"{whole}.{paise}"


def _draw_rupee(c, x, y, size, color):
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(max(0.7, size * 0.075))
    c.setLineCap(1)
    c.line(x, y + size, x + size * 0.72, y + size)
    c.line(x, y + size * 0.78, x + size * 0.66, y + size * 0.78)
    path = c.beginPath()
    path.moveTo(x + size * 0.08, y + size * 0.82)
    path.curveTo(x + size * 0.65, y + size * 0.82, x + size * 0.58, y + size * 0.48, x + size * 0.08, y + size * 0.48)
    path.lineTo(x + size * 0.62, y)
    c.drawPath(path, stroke=1, fill=0)
    c.restoreState()


def _draw_amount(c, right_x, y, value, *, size=8, color=colors.black):
    text = _inr(value)
    text_width = stringWidth(text, "Helvetica", size)
    symbol_width = size * 0.82
    symbol_x = right_x - text_width - symbol_width - 3
    _draw_rupee(c, symbol_x, y, size * 0.8, color)
    c.setFillColor(color)
    c.setFont("Helvetica", size)
    c.drawString(symbol_x + symbol_width + 2, y, text)


def _wrap(text, max_width, font, size):
    words = str(text or "—").split()
    lines, line = [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if line and stringWidth(candidate, font, size) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def _draw_wrapped(c, text, x, y, width, font="Helvetica", size=8, leading=10, max_lines=3):
    c.setFont(font, size)
    lines = _wrap(text, width, font, size)[:max_lines]
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def _logo_path(template):
    value = str(template.get("logo_path") or "")
    app_dir = Path(__file__).resolve().parents[1]
    if value.startswith("assets/"):
        path = (app_dir / value).resolve()
        return str(path) if path.is_relative_to(app_dir.resolve()) else None
    if value.startswith("uploads/"):
        from flask import current_app

        folder = Path(current_app.config["PAYSLIP_TEMPLATE_FOLDER"]).resolve()
        path = (folder / value).resolve()
        return str(path) if path.is_relative_to(folder) else None
    return None


def _draw_logo(c, template, x, y, width, height):
    path = _logo_path(template)
    if not path or not os.path.isfile(path):
        return
    image = ImageReader(path)
    c.drawImage(image, x, y, width, height, preserveAspectRatio=True, anchor="c", mask="auto")


def _component_table(
    c, x, top, width, title, entries, total, primary, accent, *,
    variant="plain", max_height=235,
):
    entries = entries or []
    header_height, total_height = 26, 22
    row_height = min(23, max(13, (max_height - header_height - total_height) / max(1, len(entries))))
    label_width = width * 0.40
    value_width = (width - label_width) / 3
    bottom = top - header_height - row_height * len(entries) - total_height

    if variant == "vkalpa":
        c.setFillColor(colors.HexColor("#EAF3FC") if title == "EARNINGS" else colors.HexColor("#FFF0EE"))
        c.setStrokeColor(colors.HexColor("#CADBED"))
        c.roundRect(x, bottom, width, top - bottom, 7, fill=1, stroke=1)
        c.setFillColor(primary if title == "EARNINGS" else colors.HexColor("#A52B2B"))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + 10, top - 17, title)
        c.setFont("Helvetica-Bold", 7)
        c.drawRightString(x + label_width + value_width - 5, top - 17, "Current")
        c.drawRightString(x + label_width + value_width * 2 - 5, top - 17, "YTD")
        c.drawRightString(x + width - 8, top - 17, "MTD")
    else:
        c.setFillColor(primary if title == "EARNINGS" else accent)
        c.rect(x, top - header_height, width, header_height, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + 9, top - 17, title)
        c.setFont("Helvetica-Bold", 7)
        c.drawRightString(x + label_width + value_width - 5, top - 17, "Current")
        c.drawRightString(x + label_width + value_width * 2 - 5, top - 17, "YTD")
        c.drawRightString(x + width - 8, top - 17, "MTD")
        c.setStrokeColor(primary)
        c.setLineWidth(0.65)
        c.rect(x, bottom, width, top - bottom, fill=0, stroke=1)

    y = top - header_height
    for item in entries:
        row_bottom = y - row_height
        if variant == "vkalpa":
            c.setFillColor(colors.white)
            c.rect(x + 1, row_bottom, width - 2, row_height, fill=1, stroke=0)
            c.setStrokeColor(colors.HexColor("#D4DFE9"))
            c.setLineWidth(0.4)
            c.line(x + 1, row_bottom, x + width - 1, row_bottom)
        else:
            c.setFillColor(colors.white)
            c.rect(x + 1, row_bottom, width - 2, row_height, fill=1, stroke=0)
            c.setStrokeColor(colors.HexColor("#D0D0D0"))
            c.setLineWidth(0.45)
            if variant == "acknowledger":
                c.setDash(2, 2)
            c.line(x + 1, row_bottom, x + width - 1, row_bottom)
            c.setDash()
            c.line(x + label_width, row_bottom, x + label_width, y)

        text_y = row_bottom + (row_height - 8) / 2 + 1
        c.setFillColor(colors.HexColor("#1F2937"))
        label_font = "Helvetica-Bold" if variant != "vkalpa" else "Helvetica"
        _draw_wrapped(
            c,
            item.get("name"),
            x + 8,
            text_y + 7,
            label_width - 16,
            font=label_font,
            size=6.5,
            leading=7,
            max_lines=3,
        )
        c.setFont("Helvetica", 7)
        _draw_amount(c, x + label_width + value_width - 5, text_y, item.get("amount"), size=6.5)
        _draw_amount(c, x + label_width + value_width * 2 - 5, text_y, item.get("ytd"), size=6.5)
        _draw_amount(c, x + width - 8, text_y, item.get("mtd"), size=6.5)
        y = row_bottom

    c.setFillColor(colors.HexColor("#E8F0F5") if variant == "acknowledger" else (
        colors.HexColor("#E7F5E9") if variant == "vkalpa" and title == "EARNINGS" else (
            colors.HexColor("#FCE9E8") if variant == "vkalpa" else colors.white
        )
    ))
    c.rect(x + 1, bottom + 1, width - 2, total_height - 1, fill=1, stroke=0)
    c.setFillColor(primary if title == "EARNINGS" else (
        colors.HexColor("#A52B2B") if variant == "vkalpa" else accent
    ))
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x + 8, bottom + 8, "TOTAL EARNINGS" if title == "EARNINGS" else "TOTAL DEDUCTIONS")
    _draw_amount(c, x + width - 8, bottom + 8, total, size=8.5, color=primary if title == "EARNINGS" else accent)
    return bottom


def _employee_details(employee, working, paid, days_on_leave, lop, variant):
    left = [
        ("Employee Name", employee.get("full_name")),
        ("Employee ID", employee.get("employee_code")),
        ("Employment Type", employee.get("employment_type")),
        ("Annual CTC", f"INR {float(employee['annual_ctc']):,.2f}" if employee.get("annual_ctc") is not None else "Not set"),
        ("Designation", employee.get("designation")),
        ("Department", employee.get("department")),
        ("Date of Joining", employee.get("date_of_joining")),
        ("Location", employee.get("location")),
        ("PAN", employee.get("pan")),
    ]
    right = [
        ("Total Working Days", working),
        ("Total Leaves", days_on_leave),
        ("LOP", lop),
        ("Total Paid Days", paid),
        ("PF Number", employee.get("pf_number")),
        ("UAN", employee.get("uan_number") or employee.get("uan")),
        ("Bank Name", employee.get("bank_name")),
        ("Bank Account Name", employee.get("bank_account_name")),
        ("A/C Number", employee.get("bank_account_number")),
        ("Pay Mode", employee.get("pay_mode")),
    ]
    return left, right


def _draw_details(c, employee, working, paid, days_on_leave, lop, primary, variant, top=640):
    x, width = 20, PAGE_WIDTH - 40
    rows = max(len(_employee_details(employee, working, paid, days_on_leave, lop, variant)[0]), 9)
    row_height = 12
    height = rows * row_height + 18
    bottom = top - height

    if variant == "ana_meta_iot":
        c.setFillColor(colors.HexColor("#F3F3F3"))
        c.roundRect(x, bottom, width, height, 12, fill=1, stroke=0)
    elif variant == "acknowledger_first":
        c.setFillColor(colors.white)
        c.setStrokeColor(colors.HexColor("#A8B0B9"))
        c.setLineWidth(1)
        c.roundRect(x, bottom, width, height, 13, fill=1, stroke=1)
    else:
        c.setFillColor(colors.HexColor("#F1F6FC"))
        c.setStrokeColor(colors.HexColor("#DFE7F1"))
        c.roundRect(x, bottom, width, height, 8, fill=1, stroke=1)
    c.setStrokeColor(primary)
    c.setLineWidth(1)
    c.line(PAGE_WIDTH / 2, bottom + 10, PAGE_WIDTH / 2, top - 10)

    left, right = _employee_details(employee, working, paid, days_on_leave, lop, variant)
    c.setFont("Helvetica", 8.3)
    for index in range(rows):
        y = top - 14 - index * row_height
        for column, items in enumerate((left, right)):
            if index >= len(items):
                continue
            label, value = items[index]
            start_x = x + 24 if column == 0 else PAGE_WIDTH / 2 + 22
            c.setFillColor(primary)
            c.setFont("Helvetica-Bold", 8.1)
            c.drawString(start_x, y, str(label)[:24])
            c.setFillColor(colors.HexColor("#334155"))
            c.setFont("Helvetica", 8.2)
            c.drawString(start_x + 112, y, ":")
            _draw_wrapped(c, value, start_x + 126, y, 122, size=8.1, leading=9, max_lines=1)
    return bottom


def _draw_ana_header(c, template, month, year):
    primary = _hex(template.get("primary_color"), "#1A00B5")
    accent = _hex(template.get("accent_color"), "#FF7618")
    c.setFillColor(colors.white)
    c.rect(0, PAGE_HEIGHT - 150, PAGE_WIDTH, 150, fill=1, stroke=0)
    _draw_logo(c, template, 26, PAGE_HEIGHT - 132, 255, 112)
    c.setFillColor(accent)
    p = c.beginPath()
    p.moveTo(330, PAGE_HEIGHT - 150)
    p.lineTo(PAGE_WIDTH, PAGE_HEIGHT - 150)
    p.lineTo(PAGE_WIDTH, PAGE_HEIGHT)
    p.lineTo(392, PAGE_HEIGHT)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.setFillColor(primary)
    p = c.beginPath()
    p.moveTo(344, PAGE_HEIGHT - 150)
    p.lineTo(PAGE_WIDTH, PAGE_HEIGHT - 150)
    p.lineTo(PAGE_WIDTH, PAGE_HEIGHT)
    p.lineTo(407, PAGE_HEIGHT)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(377, PAGE_HEIGHT - 55, "PAYSLIP")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(377, PAGE_HEIGHT - 87, "For the Month of")
    c.setFillColor(accent)
    c.drawString(377, PAGE_HEIGHT - 111, f"{MONTHS[month]} {year}")
    return primary, accent


def _draw_acknowledger_header(c, template, month, year):
    primary = _hex(template.get("primary_color"), "#16325C")
    accent = _hex(template.get("accent_color"), "#00867F")
    _draw_logo(c, template, 22, PAGE_HEIGHT - 132, 285, 100)
    c.setStrokeColor(colors.HexColor("#A9B2BC"))
    c.setLineWidth(1)
    c.line(332, PAGE_HEIGHT - 18, 332, PAGE_HEIGHT - 132)
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(350, PAGE_HEIGHT - 35, template.get("company_name") or "Acknowledger First Pvt Ltd")
    _draw_wrapped(c, template.get("address"), 350, PAGE_HEIGHT - 53, PAGE_WIDTH - 370, size=8.5, leading=13, max_lines=7)
    c.setFillColor(primary)
    c.rect(0, PAGE_HEIGHT - 173, PAGE_WIDTH, 31, fill=1, stroke=0)
    c.setFillColor(accent)
    p = c.beginPath()
    p.moveTo(216, PAGE_HEIGHT - 197)
    p.lineTo(379, PAGE_HEIGHT - 197)
    p.lineTo(360, PAGE_HEIGHT - 165)
    p.lineTo(235, PAGE_HEIGHT - 165)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 166, "PAYSLIP")
    c.setFillColor(primary)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 218, f"For The Month Of {MONTHS[month]} {year}")
    return primary, accent


def _draw_vkalpa_header(c, template, month, year):
    primary = _hex(template.get("primary_color"), "#073568")
    accent = _hex(template.get("accent_color"), "#F5C400")
    _draw_logo(c, template, 18, PAGE_HEIGHT - 145, 153, 125)
    c.setFillColor(primary)
    c.setFont("Helvetica-Bold", 23)
    c.drawString(177, PAGE_HEIGHT - 55, "Vkalpa")
    c.drawString(177, PAGE_HEIGHT - 81, "Innovations")
    _draw_wrapped(c, template.get("address"), 178, PAGE_HEIGHT - 103, 210, font="Helvetica-Bold", size=7.1, leading=9, max_lines=4)
    c.setFillColor(primary)
    p = c.beginPath()
    p.moveTo(404, PAGE_HEIGHT)
    p.lineTo(PAGE_WIDTH, PAGE_HEIGHT)
    p.lineTo(PAGE_WIDTH, PAGE_HEIGHT - 140)
    p.lineTo(449, PAGE_HEIGHT - 140)
    p.lineTo(377, PAGE_HEIGHT - 56)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.setFillColor(accent)
    p = c.beginPath()
    p.moveTo(382, PAGE_HEIGHT)
    p.lineTo(406, PAGE_HEIGHT)
    p.lineTo(368, PAGE_HEIGHT - 55)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#F0F4F7"))
    c.roundRect(16, PAGE_HEIGHT - 181, 345, 53, 12, fill=1, stroke=0)
    c.setFillColor(primary)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(40, PAGE_HEIGHT - 163, "PAYSLIP")
    c.setFont("Helvetica-Bold", 8)
    c.drawString(42, PAGE_HEIGHT - 176, f"FOR THE MONTH OF {MONTHS[month].upper()}")
    c.setFillColor(primary)
    c.roundRect(351, PAGE_HEIGHT - 181, PAGE_WIDTH - 367, 53, 12, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 8)
    c.drawString(365, PAGE_HEIGHT - 151, "PAY PERIOD")
    c.setFont("Helvetica-Bold", 9)
    last_day = calendar.monthrange(year, month)[1]
    c.drawString(365, PAGE_HEIGHT - 167, f"01 {MONTHS[month][:3]} {year} - {last_day:02d} {MONTHS[month][:3]} {year}")
    return primary, accent


def generate_reference_payslip_pdf(
    output_path, *, template, employee_info, month, year, earnings, deductions,
    days_present, days_on_leave, lop_days, total_working_days, total_paid_days,
    gross_earnings, total_deductions, net_pay,
):
    layout = template.get("layout_key")
    if hasattr(output_path, "write"):
        c = canvas.Canvas(output_path, pagesize=A4)
    else:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        c = canvas.Canvas(output_path, pagesize=A4)
    if layout == "ana_meta_iot":
        primary, accent = _draw_ana_header(c, template, month, year)
        variant = "ana_meta_iot"
        details_top = PAGE_HEIGHT - 198
        tables_top = details_top - 148
    elif layout == "acknowledger_first":
        primary, accent = _draw_acknowledger_header(c, template, month, year)
        variant = "acknowledger"
        details_top = PAGE_HEIGHT - 238
        tables_top = details_top - 150
    elif layout == "vkalpa_innovations":
        primary, accent = _draw_vkalpa_header(c, template, month, year)
        variant = "vkalpa"
        details_top = PAGE_HEIGHT - 197
        tables_top = details_top - 150
    else:
        raise ValueError(f"Unknown payslip layout: {layout}")

    details_bottom = _draw_details(
        c, employee_info, total_working_days, total_paid_days, days_on_leave, lop_days,
        primary, variant, top=details_top,
    )
    tables_top = min(tables_top, details_bottom - 15)
    c.setFillColor(primary)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(20, tables_top + 6, "SALARY STRUCTURE")
    gap = 18
    table_width = (PAGE_WIDTH - 40 - gap) / 2
    earnings_bottom = _component_table(
        c, 20, tables_top, table_width, "EARNINGS", earnings, gross_earnings,
        primary, accent, variant=variant,
    )
    deductions_bottom = _component_table(
        c, 20 + table_width + gap, tables_top, table_width, "DEDUCTIONS", deductions, total_deductions,
        primary, accent, variant=variant,
    )
    table_bottom = min(earnings_bottom, deductions_bottom)
    words = number_to_words_inr(net_pay)

    if variant == "ana_meta_iot":
        net_y = table_bottom - 82
        c.setFillColor(primary)
        c.roundRect(30, net_y, 246, 78, 13, fill=1, stroke=0)
        c.setFillColor(accent)
        c.circle(63, net_y + 39, 23, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 18)
        _draw_rupee(c, 56, net_y + 30, 13, colors.white)
        c.setFont("Helvetica", 9)
        c.drawString(103, net_y + 56, "Net Pay (A-B)")
        c.setFont("Helvetica-Bold", 20)
        _draw_amount(c, 260, net_y + 31, net_pay, size=18, color=colors.white)
        c.setFont("Helvetica", 8)
        c.drawString(44, net_y + 22, "Amount in Words:")
        _draw_wrapped(c, words, 108, net_y + 22, 151, size=6.5, leading=7.5, max_lines=3)
        c.setFillColor(accent)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(320, net_y + 54, "Note*")
        c.setFillColor(colors.black)
        _draw_wrapped(c, "This is a system generated payslip and does not require any seal or signature.", 320, net_y + 34, 245, font="Helvetica-Bold", size=8.8, leading=13, max_lines=3)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(PAGE_WIDTH / 2, 24, template.get("address") or "")
    elif variant == "acknowledger":
        net_y = table_bottom - 71
        c.setFillColor(primary)
        c.roundRect(20, net_y, PAGE_WIDTH - 40, 62, 12, fill=1, stroke=0)
        c.setFillColor(accent)
        c.circle(57, net_y + 31, 23, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 18)
        _draw_rupee(c, 50, net_y + 23, 13, colors.white)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(95, net_y + 39, "NET PAY")
        c.drawString(95, net_y + 22, "(A-B)")
        c.setFillColor(colors.HexColor("#61F065"))
        c.setFont("Helvetica-Bold", 22)
        _draw_amount(c, PAGE_WIDTH / 2 + 55, net_y + 34, net_pay, size=18, color=colors.HexColor("#61F065"))
        c.setStrokeColor(colors.white)
        c.line(PAGE_WIDTH / 2 + 66, net_y + 10, PAGE_WIDTH / 2 + 66, net_y + 52)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(PAGE_WIDTH / 2 + 78, net_y + 41, "AMOUNT IN WORDS")
        _draw_wrapped(c, words, PAGE_WIDTH / 2 + 78, net_y + 26, PAGE_WIDTH / 2 - 100, size=7.3, leading=9, max_lines=2)
        c.setFillColor(accent)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(PAGE_WIDTH / 2, net_y - 24, "This is a system generated payslip & does not require any seal or signature.")
    else:
        net_y = table_bottom - 77
        c.setFillColor(primary)
        c.roundRect(20, net_y, PAGE_WIDTH - 40, 68, 10, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(82, net_y + 42, "NET PAY")
        c.setFont("Helvetica", 9)
        c.drawString(82, net_y + 26, "(Total Earnings - Total Deductions)")
        c.setStrokeColor(colors.white)
        c.line(PAGE_WIDTH / 2 + 8, net_y + 10, PAGE_WIDTH / 2 + 8, net_y + 58)
        c.setFillColor(colors.HexColor("#83E385"))
        c.setFont("Helvetica-Bold", 20)
        _draw_amount(c, PAGE_WIDTH - 40, net_y + 38, net_pay, size=20, color=colors.HexColor("#83E385"))
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 7.5)
        _draw_wrapped(c, f"({words})", PAGE_WIDTH / 2 + 27, net_y + 22, PAGE_WIDTH / 2 - 60, size=7.5, leading=9, max_lines=2)
        c.setFillColor(colors.HexColor("#EEF4FA"))
        c.roundRect(20, net_y - 50, 365, 39, 8, fill=1, stroke=0)
        c.setFillColor(primary)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(36, net_y - 26, "Note")
        _draw_wrapped(c, "This is a system generated payslip and does not require a signature.", 36, net_y - 40, 335, size=7.5, leading=9, max_lines=1)

    c.showPage()
    c.save()
    if hasattr(output_path, "seek"):
        output_path.seek(0)
    return output_path
