from copy import deepcopy


DEFAULT_COMPANY_TEMPLATES = {
    "Ana Meta IoT": {
        "company_name": "Ana Meta IoT",
        "layout_key": "ana_meta_iot",
        "address": "WeWork Manyata Mahogany, Embassy Manyata Business Park, F2 Block, Nagavara, Bangalore - 560045",
        "primary_color": "#1A00B5",
        "accent_color": "#FF7618",
        "logo_path": "assets/payslip_templates/ana_meta_iot.png",
        "earnings_components": [
            "Basic Pay", "House Rent Allowance", "Conveyance Allowance", "Personal Pay", "Bonus",
        ],
        "deductions_components": [
            "Professional Tax", "PF", "Advance Salary", "Other Deductions", "GPA",
        ],
    },
    "Acknowledger First Pvt Ltd": {
        "company_name": "Acknowledger First Pvt Ltd",
        "layout_key": "acknowledger_first",
        "address": "# 53, 1st Main Road, Dollars Colony, RMV 2nd Stage, Sanjaynagar, Bangalore - 560 094.",
        "primary_color": "#16325C",
        "accent_color": "#00867F",
        "logo_path": "assets/payslip_templates/acknowledger_first.png",
        "earnings_components": [
            "Basic Pay", "House Rent Allowance", "Conveyance Allowance", "Personal Pay", "Bonus",
        ],
        "deductions_components": [
            "Professional Tax", "PF", "Advance Salary", "Other Deductions", "GPA",
        ],
    },
    "Vkalpa Innovations": {
        "company_name": "Vkalpa Innovations",
        "layout_key": "vkalpa_innovations",
        "address": "UB CITY, REGUS LEVEL 15, CONCORD TOWER 1, VITTAL MALLYA ROAD, BANGALORE-560001",
        "primary_color": "#073568",
        "accent_color": "#F5C400",
        "logo_path": "assets/payslip_templates/vkalpa_innovations.png",
        "earnings_components": [
            "Basic Salary", "HRA", "Conveyance Allowance", "Medical Allowance",
            "Special Allowance", "Performance Incentive",
        ],
        "deductions_components": [
            "Provident Fund (PF)", "Employee State Insurance (ESI)", "Professional Tax",
            "Income Tax (TDS)", "Other Deductions",
        ],
    },
}

EMPLOYEE_CATEGORIES = {
    "full_time": "Full Time",
    "part_time": "Part Time",
    "internship": "Intern",
}


def default_company_template(company_name):
    template = DEFAULT_COMPANY_TEMPLATES.get(company_name)
    return deepcopy(template) if template else None
