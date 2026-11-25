import { useEffect, useRef, useState } from "react";
import client from "../api/client";
import Loader from "./Loader";
import PayslipManagement from "./PayslipManagement";
import { PAYROLL_COMPANIES, PAYROLL_COMPANY_LABELS } from "../config/companies";
import { partitionEmployeesByExistingPayslip } from "../utils/salaryStructure";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const PAYROLL_SECTIONS = [
  { id: "create-template", label: "Create template" },
  { id: "saved-templates", label: "Saved template" },
  { id: "published-payslips", label: "Published Payslips" },
];
const EARNINGS_FIELDS = [
  { name: "Basic", field: "basic_pct", unit: "%" },
  { name: "ERA", field: "hra_pct", unit: "%" },
  { name: "Special Allowance", field: "special_allowance_pct", unit: "%" },
  { name: "Other Allowance", field: "other_allowance_pct", unit: "%" },
  { name: "Transport", field: "transport_flat", unit: "₹" },
];
const DEDUCTION_FIELDS = [
  { name: "Employee PF", field: "employee_pf_rate_pct", unit: "%" },
  { name: "Insurance", field: "insurance", unit: "₹" },
  { name: "Professional Tax", field: "professional_tax_flat", unit: "₹" },
  { name: "TDS", field: "tds_flat", unit: "₹" },
  { name: "Employer PF", field: "employer_pf_flat", unit: "₹" },
  { name: "Absent", field: "absent", unit: "₹" },
];
const getTemplateArrears = (template) => {
  if (Object.keys(template?.arrears_by_employee || {}).length > 0) {
    return template.arrears_by_employee;
  }
  if (template?.arrears_employee_id && template?.arrears_amount) {
    return {
      [String(template.arrears_employee_id)]: {
        description: template.arrears_description || "",
        amount: template.arrears_amount,
      },
    };
  }
  return {};
};
const getTemplateArrearsEmployeeIds = (template) => (
  Object.keys(getTemplateArrears(template)).map(Number)
);
const EMPTY_FORM = {
  name: "",
  description: "",
  company_name: "",
  basic_pct: 50,
  hra_pct: 20,
  special_allowance_pct: 20,
  other_allowance_pct: 10,
  transport_flat: 0,
  employee_pf_rate_pct: 0,
  employer_pf_rate_pct: 0,
  employer_pf_flat: 0,
  professional_tax_flat: 0,
  tds_flat: 0,
  insurance_months: [],
  insurance_amounts: {},
  include_arrears: false,
  arrears_employee_ids: [],
  arrears_by_employee: {},
};
const amount = (value) => `₹${Number(value || 0).toLocaleString("en-IN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})}`;

export default function SalaryStructuresWorkspace({ canGeneratePayslips = true }) {
  const now = new Date();
  const applyCandidatesRequestId = useRef(0);
  const [activeSection, setActiveSection] = useState("create-template");
  const [templates, setTemplates] = useState([]);
  const [assignedEmployees, setAssignedEmployees] = useState([]);
  const [expandedTemplateId, setExpandedTemplateId] = useState(null);
  const [loadingTemplates, setLoadingTemplates] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [editingTemplateId, setEditingTemplateId] = useState(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [publishError, setPublishError] = useState("");
  const [publishNotice, setPublishNotice] = useState("");
  const [publishingTemplateId, setPublishingTemplateId] = useState(null);
  const [deletingTemplateId, setDeletingTemplateId] = useState(null);
  const [deleteError, setDeleteError] = useState("");
  const [deleteNotice, setDeleteNotice] = useState("");
  const [applyTemplate, setApplyTemplate] = useState(null);
  const [applyCandidates, setApplyCandidates] = useState([]);
  const [applyCandidatesLoading, setApplyCandidatesLoading] = useState(false);
  const [applyEmployeeSearch, setApplyEmployeeSearch] = useState("");
  const [applyEmployeeIds, setApplyEmployeeIds] = useState([]);
  const [applyBusy, setApplyBusy] = useState(false);
  const [applyError, setApplyError] = useState("");
  const [applyNotice, setApplyNotice] = useState("");
  const [payrollMonth, setPayrollMonth] = useState(now.getMonth() + 1);
  const [payrollYear, setPayrollYear] = useState(now.getFullYear());
  const [generationVersion, setGenerationVersion] = useState(0);
  const [arrearsEmployeeSearch, setArrearsEmployeeSearch] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      client.get("/payroll/templates"),
      client.get("/payroll/people"),
    ])
      .then(([templatesResponse, employeesResponse]) => {
        if (!active) return;
        setTemplates(templatesResponse.data);
        setAssignedEmployees(employeesResponse.data);
      })
      .catch((requestError) => {
        if (active) {
          setLoadError(requestError?.response?.data?.message || "Could not load salary templates.");
        }
      })
      .finally(() => {
        if (active) setLoadingTemplates(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const updateForm = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const updateTemplateCompany = (companyName) => {
    setForm((current) => ({
      ...current,
      company_name: companyName,
      arrears_employee_ids: [],
      arrears_by_employee: {},
    }));
    setArrearsEmployeeSearch("");
    setNotice("");
  };

  const toggleArrearsEmployee = (employeeId) => {
    const employeeKey = String(employeeId);
    setForm((current) => {
      const selected = current.arrears_employee_ids.includes(Number(employeeId));
      const arrearsByEmployee = { ...current.arrears_by_employee };
      if (selected) {
        delete arrearsByEmployee[employeeKey];
      } else {
        arrearsByEmployee[employeeKey] = {
          description: "Salary arrears",
          amount: "",
        };
      }
      return {
        ...current,
        arrears_employee_ids: selected
          ? current.arrears_employee_ids.filter((id) => id !== Number(employeeId))
          : [...current.arrears_employee_ids, Number(employeeId)],
        arrears_by_employee: arrearsByEmployee,
      };
    });
    setNotice("");
  };

  const updateEmployeeArrears = (employeeId, field, value) => {
    const employeeKey = String(employeeId);
    setForm((current) => ({
      ...current,
      arrears_by_employee: {
        ...current.arrears_by_employee,
        [employeeKey]: {
          ...current.arrears_by_employee[employeeKey],
          [field]: value,
        },
      },
    }));
    setNotice("");
  };

  const resetTemplateEditor = () => {
    setEditingTemplateId(null);
    setForm({ ...EMPTY_FORM });
    setError("");
    setNotice("");
  };

  const editTemplate = (template) => {
    const arrearsByEmployee = getTemplateArrears(template);
    const arrearsEmployeeIds = Object.keys(arrearsByEmployee);
    setActiveSection("create-template");
    setEditingTemplateId(template.id);
    if (arrearsEmployeeIds.length && template.arrears_month) setPayrollMonth(Number(template.arrears_month));
    if (arrearsEmployeeIds.length && template.arrears_year) setPayrollYear(Number(template.arrears_year));
    setForm({
      ...EMPTY_FORM,
      ...template,
      company_name: template.company_name || "",
      insurance_months: (template.insurance_months || []).map(Number),
      insurance_amounts: template.insurance_amounts || {},
      include_arrears: arrearsEmployeeIds.length > 0,
      arrears_employee_ids: arrearsEmployeeIds.map(Number),
      arrears_by_employee: arrearsByEmployee,
    });
    setArrearsEmployeeSearch("");
    setError("");
    setNotice("");
  };

  const saveTemplate = async (event) => {
    event.preventDefault();
    setError("");
    setNotice("");
    if (form.include_arrears) {
      if (form.arrears_employee_ids.length === 0) {
        setError("Select at least one employee for arrears.");
        return;
      }
      const invalidArrears = form.arrears_employee_ids.some((employeeId) => {
        const arrears = form.arrears_by_employee[String(employeeId)] || {};
        return !arrears.description?.trim()
          || !Number.isFinite(Number(arrears.amount))
          || Number(arrears.amount) <= 0;
      });
      if (invalidArrears) {
        setError("Enter a description and a positive arrears amount for every selected employee.");
        return;
      }
    }
    setSaving(true);
    const isEditing = editingTemplateId !== null;
    const payload = {
      ...form,
      name: form.name.trim(),
      company_name: form.company_name,
      insurance_months: form.insurance_months.map(Number),
      insurance_amounts: Object.fromEntries(
        Object.entries(form.insurance_amounts || {}).filter(
          ([key]) => form.insurance_months.includes(Number(key)),
        ),
      ),
      arrears_by_employee: form.include_arrears
        ? Object.fromEntries(form.arrears_employee_ids.map((employeeId) => {
          const arrears = form.arrears_by_employee[String(employeeId)];
          return [String(employeeId), {
            description: arrears.description.trim(),
            amount: arrears.amount,
          }];
        }))
        : {},
      arrears_employee_id: null,
      arrears_description: null,
      arrears_amount: null,
      arrears_month: form.include_arrears ? Number(payrollMonth) : null,
      arrears_year: form.include_arrears ? Number(payrollYear) : null,
      earnings_confirmed: true,
      deductions_confirmed: true,
    };
    try {
      const { data } = isEditing
        ? await client.put(`/payroll/templates/${editingTemplateId}`, payload)
        : await client.post("/payroll/templates", payload);
      setTemplates((current) => {
        const byId = new Map(current.map((template) => [template.id, template]));
        byId.set(data.id, data);
        return [...byId.values()].sort((first, second) => (
          String(first.company_name || "").localeCompare(String(second.company_name || ""))
          || first.name.localeCompare(second.name)
        ));
      });
      if (isEditing) {
        setAssignedEmployees((current) => current.map((employee) => (
          employee.salary_structure?.salary_template_id === data.id
            ? {
              ...employee,
              salary_structure_published_at: null,
              salary_structure_published_by: null,
            }
            : employee
        )));
        const arrearsByEmployee = getTemplateArrears(data);
        const arrearsEmployeeIds = Object.keys(arrearsByEmployee);
        setForm({
          ...EMPTY_FORM,
          ...data,
          company_name: data.company_name || "",
          insurance_months: (data.insurance_months || []).map(Number),
          insurance_amounts: data.insurance_amounts || {},
          include_arrears: arrearsEmployeeIds.length > 0,
          arrears_employee_ids: arrearsEmployeeIds.map(Number),
          arrears_by_employee: arrearsByEmployee,
        });
      } else {
        setEditingTemplateId(null);
        setForm({ ...EMPTY_FORM });
      }
      setArrearsEmployeeSearch("");
      setNotice(`Template "${data.name}" ${isEditing ? "updated" : "created"} successfully.`);
    } catch (requestError) {
      setError(requestError?.response?.data?.message || "Could not save this salary template.");
    } finally {
      setSaving(false);
    }
  };

  const publishTemplate = async (template) => {
    const assigned = assignedEmployees.filter(
      (employee) => employee.salary_structure?.salary_template_id === template.id,
    );
    const toPublish = assigned.filter((employee) => !employee.salary_structure_published_at);
    setPublishError("");
    setPublishNotice("");
    if (assigned.length === 0) {
      setPublishError("Apply this template to employees before publishing it.");
      return;
    }
    if (toPublish.length === 0) {
      setPublishNotice(`All employees assigned to "${template.name}" are already published.`);
      return;
    }
    setPublishingTemplateId(template.id);
    try {
      const results = await Promise.allSettled(toPublish.map((employee) => (
        client.post(`/payroll/people/${employee.id}/salary-structure/publish`)
      )));
      const published = [];
      const failed = [];
      let notificationsSent = 0;
      results.forEach((result, index) => {
        const employee = toPublish[index];
        if (result.status === "fulfilled") {
          published.push({
            id: employee.id,
            salary_structure_published_at: result.value.data.published_at,
            salary_structure_published_by: result.value.data.published_by,
          });
          if (result.value.data.notification_sent) notificationsSent += 1;
        } else {
          failed.push(employee.full_name);
        }
      });
      setAssignedEmployees((current) => current.map((employee) => {
        const publication = published.find((item) => item.id === employee.id);
        return publication ? { ...employee, ...publication } : employee;
      }));
      setPublishNotice(
        `Published ${published.length} employee structure${published.length === 1 ? "" : "s"}; push notifications sent to ${notificationsSent}.`,
      );
      if (failed.length > 0) {
        setPublishError(`Could not publish for: ${failed.join(", ")}.`);
      }
    } finally {
      setPublishingTemplateId(null);
    }
  };

  const openApplyToEmployees = async (template) => {
    const requestId = ++applyCandidatesRequestId.current;
    const arrearsEmployeeIds = getTemplateArrearsEmployeeIds(template);
    setApplyTemplate(template);
    setApplyCandidates([]);
    setApplyCandidatesLoading(true);
    setApplyEmployeeSearch("");
    setApplyEmployeeIds([]);
    setApplyError("");
    setApplyNotice("");
    try {
      const { data } = await client.get("/payroll/people");
      if (requestId === applyCandidatesRequestId.current) {
        const candidates = data.filter(
          (employee) => employee.company_name === template.company_name
            && (arrearsEmployeeIds.length === 0 || arrearsEmployeeIds.includes(employee.id)),
        );
        setApplyCandidates(candidates);
        if (arrearsEmployeeIds.length > 0) {
          setApplyEmployeeIds(candidates
            .filter((employee) => Number(employee.annual_ctc) > 0)
            .map((employee) => employee.id));
        }
      }
    } catch (requestError) {
      if (requestId === applyCandidatesRequestId.current) {
        setApplyError(requestError?.response?.data?.message || "Could not load employees for this template.");
      }
    } finally {
      if (requestId === applyCandidatesRequestId.current) setApplyCandidatesLoading(false);
    }
  };

  const closeApplyModal = () => {
    if (applyBusy) return;
    applyCandidatesRequestId.current += 1;
    setApplyTemplate(null);
    setApplyCandidates([]);
    setApplyEmployeeIds([]);
    setApplyError("");
  };

  const toggleApplyEmployee = (employeeId) => {
    if (applyEmployeeIds.includes(employeeId)) {
      setApplyEmployeeIds((current) => current.filter((id) => id !== employeeId));
      setApplyError("");
      return;
    }
    if (applyEmployeeIds.length >= 200) {
      setApplyError("Select no more than 200 employees at a time.");
      return;
    }
    setApplyEmployeeIds((current) => [...current, employeeId]);
    setApplyError("");
  };

  const applySearchTerm = applyEmployeeSearch.trim().toLowerCase();
  const visibleApplyCandidates = applyCandidates.filter((employee) => (
    !applySearchTerm || [
      employee.full_name,
      employee.employee_code,
      employee.department,
      employee.salary_structure_name,
    ].some((value) => String(value || "").toLowerCase().includes(applySearchTerm))
  ));
  const eligibleVisibleApplyIds = visibleApplyCandidates
    .filter((employee) => Number(employee.annual_ctc) > 0)
    .map((employee) => employee.id);
  const allVisibleApplyEmployeesSelected = eligibleVisibleApplyIds.length > 0
    && eligibleVisibleApplyIds.every((id) => applyEmployeeIds.includes(id));
  const applyArrearsEmployeeIds = getTemplateArrearsEmployeeIds(applyTemplate);
  const hasApplyArrears = applyArrearsEmployeeIds.length > 0;
  const applyMonth = hasApplyArrears ? Number(applyTemplate.arrears_month) : payrollMonth;
  const applyYear = hasApplyArrears ? Number(applyTemplate.arrears_year) : payrollYear;

  const toggleVisibleApplyEmployees = () => {
    const next = allVisibleApplyEmployeesSelected
      ? applyEmployeeIds.filter((id) => !eligibleVisibleApplyIds.includes(id))
      : [...new Set([...applyEmployeeIds, ...eligibleVisibleApplyIds])];
    if (next.length > 200) {
      setApplyError("Select no more than 200 employees at a time.");
      return;
    }
    setApplyError("");
    setApplyEmployeeIds(next);
  };

  const applyStructureAndGenerate = async () => {
    if (!applyTemplate || applyEmployeeIds.length === 0) return;
    if (
      hasApplyArrears
      && applyEmployeeIds.some((employeeId) => !applyArrearsEmployeeIds.includes(employeeId))
    ) {
      setApplyError("This arrears template can only be applied to employees selected for arrears.");
      return;
    }
    const templateId = applyTemplate.id;
    const employeeIds = [...applyEmployeeIds];
    const targetMonth = applyMonth;
    const targetYear = applyYear;
    setApplyError("");
    setApplyBusy(true);
    let structureApplied = false;
    try {
      const { data: coverage } = await client.get("/payroll/coverage", {
        params: {
          month: targetMonth,
          year: targetYear,
          company_name: applyTemplate.company_name,
        },
      });
      const { employeesWithPayslips, employeeIdsToGenerate } = partitionEmployeesByExistingPayslip(
        employeeIds,
        coverage.people,
      );

      await client.post(`/payroll/templates/${templateId}/assign`, {
        employee_ids: employeeIds,
      });
      structureApplied = true;
      setAssignedEmployees((current) => {
        const byId = new Map(current.map((employee) => [employee.id, employee]));
        applyCandidates
          .filter((employee) => employeeIds.includes(employee.id))
          .forEach((employee) => {
            const previousTemplateId = employee.salary_structure?.salary_template_id;
            byId.set(employee.id, {
              ...employee,
              salary_structure: {
                ...employee.salary_structure,
                salary_template_id: templateId,
                employee_overrides: previousTemplateId === templateId
                  ? employee.salary_structure?.employee_overrides || {}
                  : {},
              },
              salary_structure_name: applyTemplate.name,
              salary_structure_published_at: previousTemplateId === templateId
                ? employee.salary_structure_published_at
                : null,
              salary_structure_published_by: previousTemplateId === templateId
                ? employee.salary_structure_published_by
                : null,
            });
          });
        return [...byId.values()];
      });
      if (employeeIdsToGenerate.length > 0) {
        await client.post("/payroll/generate-selected", {
          salary_template_id: templateId,
          company_name: applyTemplate.company_name,
          month: targetMonth,
          year: targetYear,
          user_ids: employeeIdsToGenerate,
        });
        setGenerationVersion((current) => current + 1);
      }
      setPayrollMonth(targetMonth);
      setPayrollYear(targetYear);
      const skippedMessage = employeesWithPayslips.length > 0
        ? ` No duplicate payslip was created for ${employeesWithPayslips.map((employee) => employee.full_name).join(", ")} because a payslip already exists for ${MONTHS[targetMonth - 1]} ${targetYear}; review it in Published Payslips if it needs updating.`
        : "";
      const generatedMessage = employeeIdsToGenerate.length > 0
        ? ` Generated ${employeeIdsToGenerate.length} draft payslip${employeeIdsToGenerate.length === 1 ? "" : "s"}; publish each employee's payslip separately in Published Payslips.`
        : " No new payslips were generated.";
      setApplyNotice(
        `Salary structure applied to ${employeeIds.length} employee${employeeIds.length === 1 ? "" : "s"}.${generatedMessage}${skippedMessage}`,
      );
      setApplyTemplate(null);
      setApplyCandidates([]);
      setApplyEmployeeIds([]);
    } catch (requestError) {
      const message = requestError?.response?.data?.message
        || "Could not apply the salary structure and generate payslips.";
      setApplyError(structureApplied
        ? `The structure was applied, but payslips were not generated: ${message}`
        : message);
    } finally {
      setApplyBusy(false);
    }
  };

  const assignedToTemplate = (templateId) => assignedEmployees.filter(
    (employee) => employee.salary_structure?.salary_template_id === templateId,
  );
  const arrearsEmployeeOptions = assignedEmployees.filter(
    (employee) => employee.company_name === form.company_name,
  );
  const arrearsEmployeeSearchTerm = arrearsEmployeeSearch.trim().toLowerCase();
  const visibleArrearsEmployeeOptions = arrearsEmployeeOptions.filter((employee) => (
    !arrearsEmployeeSearchTerm || [
      employee.full_name,
      employee.employee_code,
      employee.company_name,
    ].some((value) => String(value || "").toLowerCase().includes(arrearsEmployeeSearchTerm))
  ));

  const deleteTemplate = async (template) => {
    const assigned = assignedToTemplate(template.id);
    if (assigned.length > 0) {
      setDeleteError("Unassign employees before deleting this template.");
      return;
    }
    if (!window.confirm(`Delete "${template.name}"? This cannot be undone.`)) return;

    setDeleteError("");
    setDeleteNotice("");
    setDeletingTemplateId(template.id);
    try {
      await client.delete(`/payroll/templates/${template.id}`);
      setTemplates((current) => current.filter((item) => item.id !== template.id));
      setDeleteNotice(`Template "${template.name}" was deleted.`);
      if (editingTemplateId === template.id) resetTemplateEditor();
    } catch (requestError) {
      setDeleteError(requestError?.response?.data?.message || "Could not delete this template.");
    } finally {
      setDeletingTemplateId(null);
    }
  };

  const clearTemplateEditor = () => {
    setEditingTemplateId(null);
    setForm({ ...EMPTY_FORM });
    setError("");
    setNotice("");
  };

  return (
    <div className="salary-structures-workspace">
      <div className="tag-list section-gap">
        <div className="tag-list" role="tablist" aria-label="Payroll sections">
          {PAYROLL_SECTIONS.filter(
            (section) => section.id !== "published-payslips" || canGeneratePayslips,
          ).map((section) => (
            <button
              key={section.id}
              id={`payroll-tab-${section.id}`}
              type="button"
              role="tab"
              aria-selected={activeSection === section.id}
              aria-controls="payroll-section-panel"
              className={`btn btn-sm ${activeSection === section.id ? "btn-primary" : "btn-outline"}`}
              onClick={() => setActiveSection(section.id)}
            >
              {section.label}
            </button>
          ))}
        </div>
      </div>

      <div
        id="payroll-section-panel"
        role="tabpanel"
        aria-labelledby={`payroll-tab-${activeSection}`}
        tabIndex={0}
      >
        {activeSection === "create-template" && (
          <section className="card section-gap">
            <div className="card-title-row">
              <div>
                <h2>Create template</h2>
                <p className="muted">Create a reusable salary template, then apply it to employees when you're ready.</p>
              </div>
              {editingTemplateId && (
                <button type="button" className="btn btn-sm btn-outline" onClick={clearTemplateEditor}>
                  Cancel edit
                </button>
              )}
            </div>
            {error && <div className="login-error section-gap" role="alert">{error}</div>}
            {notice && <div className="callout note section-gap" role="status">{notice}</div>}

            <form className="salary-structure-editor" onSubmit={saveTemplate}>
              <div className="salary-template-period">
                <div className="form-field">
                  <label htmlFor="salary-template-payroll-month">Payroll month for payslip</label>
                  <select
                    id="salary-template-payroll-month"
                    value={payrollMonth}
                    onChange={(event) => setPayrollMonth(Number(event.target.value))}
                  >
                    {MONTHS.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}
                  </select>
                </div>
                <div className="form-field">
                  <label htmlFor="salary-template-payroll-year">Payroll year</label>
                  <input
                    id="salary-template-payroll-year"
                    type="number"
                    min="2000"
                    max="2200"
                    value={payrollYear}
                    onChange={(event) => setPayrollYear(Number(event.target.value))}
                  />
                </div>
                <p className="muted">
                  Used for payslip generation. For an arrears template, this period is saved with the arrears entry.
                </p>
              </div>
              <div className="salary-template-identity">
                <div className="form-field">
                  <label htmlFor="salary-template-name">Template name</label>
                  <input
                    id="salary-template-name"
                    maxLength="100"
                    required
                    value={form.name}
                    onChange={(event) => updateForm("name", event.target.value)}
                    placeholder="Enter a template name"
                  />
                </div>
                <div className="form-field">
                  <label htmlFor="salary-template-company">Company</label>
                  <select
                    id="salary-template-company"
                    required
                    value={form.company_name}
                    onChange={(event) => updateTemplateCompany(event.target.value)}
                  >
                    <option value="">Select company</option>
                    {PAYROLL_COMPANIES.map((company) => (
                      <option key={company} value={company}>
                        {PAYROLL_COMPANY_LABELS[company] || company}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-field">
                  <label htmlFor="salary-template-description">Description (optional)</label>
                  <input
                    id="salary-template-description"
                    maxLength="255"
                    value={form.description || ""}
                    onChange={(event) => updateForm("description", event.target.value)}
                    placeholder="Add a short description"
                  />
                </div>
              </div>

              <div className="salary-structure-sections">
                <section className="salary-structure-section">
                  <h3>Earnings</h3>
                  <table className="data-table salary-structure-table">
                    <thead><tr><th>Component</th><th>Input</th><th>MTD</th><th>YTD</th></tr></thead>
                    <tbody>
                      {EARNINGS_FIELDS.map((item) => (
                        <tr key={item.field}>
                          <td>{item.name}</td>
                          <td>
                            <div className="salary-structure-input-control">
                              <input
                                aria-label={`${item.name} ${item.unit === "%" ? "percentage" : "amount"}`}
                                type="number"
                                min="0"
                                max={item.unit === "%" ? "100" : undefined}
                                step="0.01"
                                value={form[item.field]}
                                onChange={(event) => updateForm(item.field, event.target.value)}
                              />
                              <span>{item.unit}</span>
                            </div>
                          </td>
                          <td className="salary-structure-value"><strong>—</strong></td>
                          <td className="salary-structure-value"><strong>—</strong></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>

                <section className="salary-structure-section">
                  <h3>Deductions</h3>
                  <table className="data-table salary-structure-table">
                    <thead><tr><th>Component</th><th>Input</th><th>MTD</th><th>YTD</th></tr></thead>
                    <tbody>
                      {DEDUCTION_FIELDS.map((item) => (
                        <tr key={item.field}>
                          <td>{item.name}</td>
                          <td>
                            {item.field === "insurance" ? (
                              <div className="salary-structure-insurance-input">
                                <select
                                  aria-label="Insurance month"
                                  value={Number(form.insurance_months[0] || "")}
                                  onChange={(event) => {
                                    const month = Number(event.target.value);
                                    setForm((current) => ({
                                      ...current,
                                      insurance_months: month ? [month] : [],
                                      insurance_amounts: month
                                        ? { [String(month)]: current.insurance_amounts[String(month)] || "" }
                                        : {},
                                    }));
                                  }}
                                >
                                  <option value="">Not scheduled</option>
                                  <option value={1}>January</option>
                                  <option value={2}>February</option>
                                </select>
                                {Number(form.insurance_months[0]) > 0 && (
                                  <div className="salary-structure-input-control">
                                    <input
                                      aria-label="Insurance amount"
                                      type="number"
                                      min="0"
                                      step="0.01"
                                      value={form.insurance_amounts[String(form.insurance_months[0])] || ""}
                                      onChange={(event) => setForm((current) => ({
                                        ...current,
                                        insurance_amounts: {
                                          [String(current.insurance_months[0])]: event.target.value,
                                        },
                                      }))}
                                    />
                                    <span>₹</span>
                                  </div>
                                )}
                              </div>
                            ) : item.field === "absent" ? (
                              <span className="muted">Calculated from attendance</span>
                            ) : (
                              <div className="salary-structure-input-control">
                                <input
                                  aria-label={`${item.name} ${item.unit === "%" ? "percentage" : "amount"}`}
                                  type="number"
                                  min="0"
                                  max={item.unit === "%" ? "100" : undefined}
                                  step="0.01"
                                  value={form[item.field]}
                                  onChange={(event) => updateForm(item.field, event.target.value)}
                                />
                                <span>{item.unit}</span>
                              </div>
                            )}
                            {item.field === "insurance" && Number(form.insurance_months[0]) > 0 && (
                              <small className="salary-structure-calculation">
                                Deducted in {MONTHS[Number(form.insurance_months[0]) - 1]} only
                              </small>
                            )}
                          </td>
                          <td className="salary-structure-value"><strong>—</strong></td>
                          <td className="salary-structure-value"><strong>—</strong></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              </div>

              <section className="salary-template-totals" aria-label="Salary totals">
                <div><span>Total Earnings</span><strong>—</strong></div>
                <div><span>Total Deductions</span><strong>—</strong></div>
                <div><span>Net Salary</span><strong>—</strong></div>
              </section>
              <section className="salary-arrears-section">
                <h3>Arrears</h3>
                <div className="form-field salary-arrears-company-field">
                  <label htmlFor="salary-arrears-company">Company for employee selection</label>
                  <select
                    id="salary-arrears-company"
                    value={form.company_name}
                    onChange={(event) => updateTemplateCompany(event.target.value)}
                  >
                    <option value="">Select company</option>
                    {PAYROLL_COMPANIES.map((company) => (
                      <option key={company} value={company}>
                        {PAYROLL_COMPANY_LABELS[company] || company}
                      </option>
                    ))}
                  </select>
                </div>
                <label className="salary-arrears-toggle">
                  <input
                    type="checkbox"
                    checked={form.include_arrears}
                    onChange={(event) => updateForm("include_arrears", event.target.checked)}
                  />
                  Add arrears for selected employees
                </label>
                {form.include_arrears && (
                  <>
                    <details className="salary-arrears-employee-dropdown">
                      <summary>
                        {form.arrears_employee_ids.length > 0
                          ? `${form.arrears_employee_ids.length} employee${form.arrears_employee_ids.length === 1 ? "" : "s"} selected`
                          : "Select employees"}
                      </summary>
                      <div className="salary-arrears-employee-options" role="group" aria-label="Employees eligible for arrears">
                        <input
                          type="search"
                          aria-label="Search arrears employees"
                          value={arrearsEmployeeSearch}
                          onChange={(event) => setArrearsEmployeeSearch(event.target.value)}
                          placeholder="Search by name or employee ID"
                        />
                        {visibleArrearsEmployeeOptions.length === 0 ? (
                          <p className="muted">
                            {arrearsEmployeeOptions.length === 0
                              ? form.company_name
                                ? "No active employees are available in this company."
                                : "Select a company to list its active employees."
                              : "No employees match this search."}
                          </p>
                        ) : visibleArrearsEmployeeOptions.map((employee) => (
                          <label key={employee.id} className="salary-arrears-employee-option">
                            <input
                              type="checkbox"
                              checked={form.arrears_employee_ids.includes(employee.id)}
                              onChange={() => toggleArrearsEmployee(employee.id)}
                            />
                            <span>
                              <strong>{employee.full_name}</strong>
                              <small>
                                {employee.employee_code || "No employee ID"} · {employee.company_name}
                              </small>
                            </span>
                          </label>
                        ))}
                      </div>
                    </details>
                    {form.arrears_employee_ids.length > 0 && (
                      <div className="salary-arrears-employee-amounts">
                        {form.arrears_employee_ids.map((employeeId) => {
                          const employee = arrearsEmployeeOptions.find((option) => option.id === employeeId);
                          const arrears = form.arrears_by_employee[String(employeeId)] || {};
                          return (
                            <div className="salary-arrears-employee-row" key={employeeId}>
                              <div className="salary-arrears-employee-details">
                                <strong>{employee?.full_name || `Employee ID ${employeeId}`}</strong>
                                <small>
                                  {employee?.employee_code || "Employee"}
                                  {employee?.company_name ? ` · ${employee.company_name}` : ""}
                                </small>
                              </div>
                              <label>
                                Description
                                <input
                                  type="text"
                                  maxLength="150"
                                  required
                                  value={arrears.description || ""}
                                  onChange={(event) => updateEmployeeArrears(
                                    employeeId, "description", event.target.value,
                                  )}
                                  placeholder="e.g. Previous month adjustment"
                                />
                              </label>
                              <label>
                                Amount (₹)
                                <input
                                  type="number"
                                  min="0.01"
                                  step="0.01"
                                  required
                                  value={arrears.amount ?? ""}
                                  onChange={(event) => updateEmployeeArrears(
                                    employeeId, "amount", event.target.value,
                                  )}
                                />
                              </label>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    <p className="muted salary-template-calculation-note">
                      Enter a separate amount for each selected employee. Arrears apply in {MONTHS[payrollMonth - 1]} {payrollYear};
                      the template remains limited to {PAYROLL_COMPANY_LABELS[form.company_name] || "the selected company"}.
                    </p>
                  </>
                )}
              </section>
              <p className="muted salary-template-calculation-note">
                MTD, YTD, and rupee totals are calculated for each employee from their Annual CTC when the template is applied.
              </p>
              <div className="payslip-editor-actions">
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? "Saving..." : editingTemplateId ? "Update Template" : "Save Template"}
                </button>
                <button type="button" className="btn btn-outline" disabled={saving} onClick={resetTemplateEditor}>
                  Clear
                </button>
              </div>
            </form>
          </section>
        )}

        {activeSection === "saved-templates" && (
          <section className="card section-gap">
            <div className="card-title-row">
              <div>
                <h2>Saved template</h2>
                <p className="muted">All reusable salary templates are listed here.</p>
              </div>
              <button
                type="button"
                className="btn btn-sm btn-primary"
                onClick={() => {
                  resetTemplateEditor();
                  setActiveSection("create-template");
                }}
              >
                Create template
              </button>
            </div>
            {loadError && <div className="login-error section-gap" role="alert">{loadError}</div>}
            {publishError && <div className="login-error section-gap" role="alert">{publishError}</div>}
            {deleteError && <div className="login-error section-gap" role="alert">{deleteError}</div>}
            {publishNotice && <div className="callout note section-gap" role="status">{publishNotice}</div>}
            {deleteNotice && <div className="callout note section-gap" role="status">{deleteNotice}</div>}
            {applyNotice && <div className="callout note section-gap" role="status">{applyNotice}</div>}
            {loadingTemplates ? <Loader /> : templates.length === 0 ? (
              <p className="muted">No templates have been saved yet.</p>
            ) : (
              <div className="table-wrap salary-saved-structures-wrap">
                <table className="data-table salary-saved-structures-table">
                  <thead>
                    <tr>
                      <th>Template</th>
                      <th>Company</th>
                      <th>Assigned Employees</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {templates.map((template) => {
                      const assigned = assignedToTemplate(template.id).sort(
                        (first, second) => String(first.full_name || "").localeCompare(String(second.full_name || "")),
                      );
                      const employeesExpanded = expandedTemplateId === template.id;
                      const allPublished = assigned.length > 0
                        && assigned.every((employee) => employee.salary_structure_published_at);
                      const arrearsEmployeeIds = getTemplateArrearsEmployeeIds(template);
                      return (
                        <tr key={template.id}>
                          <td>
                            <strong>{template.name}</strong>
                            {template.description && (
                              <small className="salary-template-description">{template.description}</small>
                            )}
                            {arrearsEmployeeIds.length > 0 && (
                              <small className="salary-template-description">
                                Arrears for {arrearsEmployeeIds.map((employeeId) => (
                                  assignedEmployees.find((employee) => employee.id === employeeId)?.full_name
                                    || `employee ID ${employeeId}`
                                )).join(", ")}
                                {" · "}
                                {MONTHS[Number(template.arrears_month) - 1]} {template.arrears_year}
                              </small>
                            )}
                          </td>
                          <td>{PAYROLL_COMPANY_LABELS[template.company_name] || template.company_name || "Company not set"}</td>
                          <td>
                            {assigned.length === 0 ? (
                              "None"
                            ) : (
                              <>
                                <span>{`${assigned.length} employee${assigned.length === 1 ? "" : "s"}`}</span>
                                <button
                                  type="button"
                                  className="btn btn-sm btn-outline salary-template-assigned-toggle"
                                  aria-expanded={employeesExpanded}
                                  aria-controls={`salary-template-assigned-${template.id}`}
                                  onClick={() => setExpandedTemplateId(
                                    employeesExpanded ? null : template.id,
                                  )}
                                >
                                  {employeesExpanded ? "Hide employees" : "View employees"}
                                </button>
                                {employeesExpanded && (
                                  <ul
                                    id={`salary-template-assigned-${template.id}`}
                                    className="salary-template-assigned-list"
                                    aria-label={`Employees assigned to ${template.name}`}
                                  >
                                    {assigned.map((employee) => (
                                      <li key={employee.id}>
                                        <span>{employee.full_name}</span>
                                        {employee.employee_code && (
                                          <small>{employee.employee_code}</small>
                                        )}
                                      </li>
                                    ))}
                                  </ul>
                                )}
                              </>
                            )}
                          </td>
                          <td>
                            <div className="salary-saved-structure-actions">
                              <button
                                type="button"
                                className="btn btn-sm btn-outline"
                                onClick={() => editTemplate(template)}
                                disabled={deletingTemplateId !== null}
                              >
                                Edit
                              </button>
                              {canGeneratePayslips && (
                                <button
                                  type="button"
                                  className="btn btn-sm btn-outline"
                                  onClick={() => openApplyToEmployees(template)}
                                  disabled={!template.company_name || deletingTemplateId !== null}
                                >
                                  Apply to Employees
                                </button>
                              )}
                              {allPublished ? (
                                <span className="badge badge-success">Structure Published</span>
                              ) : (
                                <button
                                  type="button"
                                  className="btn btn-sm btn-primary"
                                  onClick={() => publishTemplate(template)}
                                  disabled={assigned.length === 0 || publishingTemplateId !== null || deletingTemplateId !== null}
                                  title={assigned.length === 0 ? "Apply this template to employees first" : ""}
                                >
                                  {publishingTemplateId === template.id ? "Publishing..." : "Publish Structure"}
                                </button>
                              )}
                              <button
                                type="button"
                                className="btn btn-sm btn-outline"
                                onClick={() => deleteTemplate(template)}
                                disabled={assigned.length > 0 || deletingTemplateId !== null || publishingTemplateId !== null}
                                title={assigned.length > 0 ? "Unassign employees before deleting this template" : ""}
                              >
                                {deletingTemplateId === template.id ? "Deleting..." : "Delete"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {activeSection === "published-payslips" && canGeneratePayslips && (
          <section className="card section-gap">
            <div className="card-title-row">
              <div>
                <h2>Published Payslips</h2>
                <p className="muted">
                  Published payslips across all payroll periods, listed separately by employee.
                </p>
              </div>
            </div>
            <div className="salary-monthly-generation">
              <span className="muted">
                Drafts appear here with an individual Publish Payslip action. Publishing one employee does not publish the others.
              </span>
            </div>
            <PayslipManagement
              key={`published-${generationVersion}`}
              embedded
              simple
              includeAllStatuses
              allPeriods
            />
          </section>
        )}
      </div>

      {applyTemplate && (
        <div className="modal-overlay" onClick={closeApplyModal}>
          <section
            className="modal-box salary-apply-structure-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="salary-apply-structure-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="salary-apply-structure-header">
              <div>
                <h3 id="salary-apply-structure-title">Apply to Employees</h3>
                <p className="muted">
                  {applyTemplate.name} · {PAYROLL_COMPANY_LABELS[applyTemplate.company_name] || applyTemplate.company_name}
                </p>
              </div>
              <button
                type="button"
                className="salary-employee-search-clear"
                aria-label="Close apply-to-employees dialog"
                title="Close"
                onClick={closeApplyModal}
                disabled={applyBusy}
              >
                &times;
              </button>
            </div>
            {applyError && <div className="login-error section-gap" role="alert">{applyError}</div>}
            <p className="muted salary-apply-period-note">
              Payslips will be generated for {MONTHS[applyMonth - 1]} {applyYear}.
              {hasApplyArrears && " This template includes separate arrears for the selected employees and period only."}
            </p>
            <div className="form-field salary-apply-employee-search">
              <label htmlFor="apply-employee-search">Search employees by name, ID, or department</label>
              <input
                id="apply-employee-search"
                type="search"
                value={applyEmployeeSearch}
                onChange={(event) => setApplyEmployeeSearch(event.target.value)}
                placeholder="Search employees"
                disabled={applyCandidatesLoading || applyBusy}
              />
            </div>
            <div className="salary-apply-employee-toolbar">
              <span className="muted">
                {applyEmployeeIds.length} selected · {MONTHS[applyMonth - 1]} {applyYear}
              </span>
              <button
                type="button"
                className="btn btn-sm btn-outline"
                onClick={toggleVisibleApplyEmployees}
                disabled={applyCandidatesLoading || applyBusy || eligibleVisibleApplyIds.length === 0}
              >
                {allVisibleApplyEmployeesSelected ? "Deselect visible" : "Select visible"}
              </button>
            </div>
            <div className="salary-apply-employee-list" role="group" aria-label="Employees to apply this template to">
              {applyCandidatesLoading ? (
                <Loader />
              ) : visibleApplyCandidates.length === 0 ? (
                <p className="muted salary-apply-empty">
                  {applyCandidates.length === 0
                    ? "No active employees are available in this company."
                    : "No employees match this search."}
                </p>
              ) : visibleApplyCandidates.map((employee) => {
                const hasCtc = Number(employee.annual_ctc) > 0;
                const currentTemplateId = employee.salary_structure?.salary_template_id;
                const replacingStructure = currentTemplateId && currentTemplateId !== applyTemplate.id;
                return (
                  <label className="salary-apply-employee-option" key={employee.id}>
                    <input
                      type="checkbox"
                      checked={applyEmployeeIds.includes(employee.id)}
                      onChange={() => toggleApplyEmployee(employee.id)}
                      disabled={!hasCtc || applyBusy}
                    />
                    <span className="salary-apply-employee-details">
                      <strong>{employee.full_name}</strong>
                      <small>
                        {employee.employee_code || "No employee ID"} · {employee.department || "No department"}
                        {replacingStructure
                          ? ` · Replaces ${employee.salary_structure_name || "current template"}`
                          : ""}
                      </small>
                    </span>
                    <span className="salary-apply-employee-ctc">
                      {hasCtc ? amount(employee.annual_ctc) : "CTC not set"}
                    </span>
                  </label>
                );
              })}
            </div>
            {applyEmployeeIds.length > 200 && (
              <div className="login-error" role="alert">Select no more than 200 employees at a time.</div>
            )}
            <div className="callout warn salary-apply-warning">
              Applying a different template keeps each employee's Annual CTC but resets their individual salary overrides.
              Payslips are generated as drafts. They appear in Published Payslips, where each employee's payslip can be published separately.
            </div>
            <div className="payslip-editor-actions">
              <button type="button" className="btn btn-outline" onClick={closeApplyModal} disabled={applyBusy}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={applyStructureAndGenerate}
                disabled={applyBusy || applyCandidatesLoading || applyEmployeeIds.length === 0 || applyEmployeeIds.length > 200}
              >
                {applyBusy ? "Applying and generating..." : "Apply & Generate Draft Payslips"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
