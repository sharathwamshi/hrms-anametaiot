import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import client from "../api/client";
import AppLayout from "./AppLayout";
import Badge from "./Badge";
import Loader from "./Loader";
import PayslipDetailModal from "./PayslipDetailModal";
import { numberToWordsInr } from "../utils/numberToWords";
import { PAYROLL_COMPANIES, PAYROLL_COMPANY_LABELS } from "../config/companies";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const EMPLOYEE_CATEGORIES = [
  ["full_time", "Full Time"], ["part_time", "Part Time"], ["internship", "Intern"],
];
const EARNING_DEFAULTS = [
  "Basic Salary", "House Rent Allowance", "Conveyance Allowance", "Medical Allowance",
  "Special Allowance", "Personal Pay", "Bonus", "Performance Incentive", "Other Earnings",
];
const DEDUCTION_DEFAULTS = [
  "Provident Fund (PF)", "Employee State Insurance (ESI)", "Professional Tax",
  "Income Tax (TDS)", "Advance Salary", "GPA", "Other Deductions",
];
const PUBLISHED_PAYSLIP_STATUSES = ["published", "updated", "paid"];
const EMPLOYEE_FIELDS = [
  ["designation", "Designation"], ["date_of_joining", "Date of Joining"],
  ["pan", "PAN number"], ["pf_number", "PF number"], ["uan_number", "UAN number"],
  ["bank_name", "Bank name"], ["bank_account_number", "Bank account number"],
  ["bank_account_name", "Bank account name"],
  ["pay_mode", "Pay mode"], ["location", "Location"],
];
const inputStyle = { border: "1px solid var(--color-border)", borderRadius: 6, padding: "8px 10px", width: "100%" };
const amount = (value) => Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const emptyComponents = (labels) => labels.map((name) => ({ name, amount: 0 }));
const isArrearsComponent = (component) => String(component.name || "").startsWith("Arrears - ");

function emptyDraft(month, year) {
  return {
    id: null, user_id: "", month, year, company_name: PAYROLL_COMPANIES[1],
    employee_info: {}, total_working_days: new Date(year, month, 0).getDate(), total_paid_days: 0,
    days_present: 0, lop_days: 0,
    earnings: emptyComponents(EARNING_DEFAULTS),
    deductions: emptyComponents(DEDUCTION_DEFAULTS),
  };
}

export default function PayslipManagement({
  defaultMonth,
  defaultYear,
  embedded = false,
  simple = false,
  publishedOnly = false,
  includeAllStatuses = false,
  allPeriods = false,
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const { payslipId } = useParams();
  const isEditor = location.pathname.endsWith("/create") || Boolean(payslipId);
  const [payslips, setPayslips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState(
    allPeriods ? "" : defaultMonth || new Date().getMonth() + 1,
  );
  const [year, setYear] = useState(
    allPeriods ? "" : defaultYear || new Date().getFullYear(),
  );
  const [company, setCompany] = useState("");
  const [search, setSearch] = useState("");
  const [employeeCategory, setEmployeeCategory] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [employees, setEmployees] = useState([]);
  const [employeeSearching, setEmployeeSearching] = useState(false);
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [preview, setPreview] = useState(null);
  const [revisionHistory, setRevisionHistory] = useState(null);
  const [companyTemplates, setCompanyTemplates] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [managementTab, setManagementTab] = useState("payslips");
  const [selectedIds, setSelectedIds] = useState([]);
  const [batchPreviews, setBatchPreviews] = useState([]);
  const [batchBusy, setBatchBusy] = useState(false);
  const [templateDraft, setTemplateDraft] = useState(null);
  const [templateSaving, setTemplateSaving] = useState(false);
  const [arrearsDraft, setArrearsDraft] = useState({
    description: "", amount: "", month: new Date().getMonth() + 1, year: new Date().getFullYear(),
  });

  useEffect(() => {
    if (!draft) return;
    setArrearsDraft((current) => ({
      ...current,
      month: Number(draft.month),
      year: Number(draft.year),
    }));
  }, [draft?.month, draft?.year]);

  useEffect(() => {
    if (isEditor) return undefined;
    const timer = setTimeout(() => {
      setLoading(true);
      const params = {
        ...(allPeriods
          ? {
            ...(month ? { month: Number(month) } : {}),
            ...(year ? { year: Number(year) } : {}),
          }
          : { month, year }),
          ...(company ? { company_name: company } : {}),
          ...(search ? { q: search } : {}),
      };
      const request = allPeriods
        ? client.get("/payroll/payslips", { params })
        : client.get("/payroll/coverage", {
          params: {
            ...params,
            ...(employeeCategory ? { employee_category: employeeCategory } : {}),
            ...(employeeId ? { employee_id: employeeId } : {}),
          },
        });
      request.then(({ data }) => {
        setPayslips(allPeriods ? data.map((payslip) => ({
          id: payslip.id,
          full_name: payslip.employee_name || payslip.employee_info?.full_name || "Employee",
          employee_code: payslip.employee_info?.employee_code || payslip.user_id,
          company_name: payslip.company_name,
          salary_structure_name: payslip.employee_info?.salary_structure_name,
          payslip_id: payslip.id,
          payslip,
        })) : data.people);
        setSelectedIds([]);
        setBatchPreviews([]);
      })
        .catch((err) => setError(err?.response?.data?.message || "Could not load payslips."))
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(timer);
  }, [isEditor, allPeriods, month, year, company, employeeCategory, employeeId, search, refresh]);

  useEffect(() => {
    client.get("/payroll/payslip-templates")
      .then(({ data }) => {
        setCompanyTemplates(data);
        if (data.length) {
          setTemplateDraft({
            ...data[0],
            earnings_components_text: data[0].earnings_components.join("\n"),
            deductions_components_text: data[0].deductions_components.join("\n"),
          });
        }
      })
      .catch((err) => setError(err?.response?.data?.message || "Could not load company payslip templates."));
  }, []);

  useEffect(() => {
    if (!isEditor) return;
    setError("");
    if (!payslipId) {
      const state = location.state || {};
      const newDraft = emptyDraft(
        Number(state.month || defaultMonth || new Date().getMonth() + 1),
        Number(state.year || defaultYear || new Date().getFullYear()),
      );
      const employee = state.employee;
      const selectedCompany = state.company || "";
      const selectedCategory = state.employeeCategory || "";
      setDraft({
        ...newDraft,
        ...(employee ? {
          user_id: employee.id,
          company_name: selectedCompany || employee.company_name,
          employee_info: employee.employee_info || {},
          earnings: employee.earnings?.length ? employee.earnings : newDraft.earnings,
          deductions: employee.deductions?.length ? employee.deductions : newDraft.deductions,
        } : {}),
      });
      setCompany(selectedCompany);
      setEmployeeCategory(selectedCategory);
      if (employee && selectedCompany && selectedCategory) {
        client.post("/payroll/preview-bulk", {
          company_name: selectedCompany,
          employee_category: selectedCategory,
          month: newDraft.month,
          year: newDraft.year,
          user_ids: [employee.id],
        }).then(({ data }) => setDraft((current) => ({
          ...current,
          ...data.previews[0],
          employee_info: employee.employee_info || data.previews[0].employee_info,
        }))).catch((err) => setError(err?.response?.data?.message || "Could not load attendance and salary information."));
      }
      return;
    }

    setLoading(true);
    client.get(`/payroll/payslip/${payslipId}`)
      .then(({ data }) => {
        setDraft({
          ...data,
          id: data.id,
          user_id: data.user_id,
          company_name: data.company_name || PAYROLL_COMPANIES[1],
          employee_category: data.employee_info?.employee_category || "",
          employee_info: {
            ...data.employee_info,
            full_name: data.employee_info?.full_name || data.employee_name || "",
            employee_code: data.employee_info?.employee_code || "",
          },
        });
        setEmployeeCategory(data.employee_info?.employee_category || "");
      })
      .catch((err) => setError(err?.response?.data?.message || "Could not load this payslip."))
      .finally(() => setLoading(false));
  }, [isEditor, payslipId, location.state, defaultMonth, defaultYear]);

  useEffect(() => {
    let active = true;
    if (!isEditor || !company || employeeSearch.trim().length < 2) {
      setEmployees([]);
      setEmployeeSearching(false);
      return undefined;
    }
    setEmployees([]);
    setEmployeeSearching(true);
    const timer = setTimeout(() => {
      client.get("/payroll/people", {
        params: {
          q: employeeSearch.trim(),
          company_name: company,
          ...(employeeCategory ? { employee_category: employeeCategory } : {}),
          include_uncategorized: true,
        },
      })
        .then(({ data }) => { if (active) setEmployees(data); })
        .catch((err) => { if (active) setError(err?.response?.data?.message || "Could not search employees."); })
        .finally(() => { if (active) setEmployeeSearching(false); });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [isEditor, company, employeeCategory, employeeSearch]);

  useEffect(() => {
    if (!isEditor) return;
    client.get("/employees/departments")
      .then(({ data }) => setDepartments(data))
      .catch((err) => setError(err?.response?.data?.message || "Could not load departments."));
  }, [isEditor]);

  const earnings = useMemo(
    () => (draft?.earnings || []).reduce((total, item) => total + Number(item.amount || 0), 0),
    [draft],
  );
  const deductions = useMemo(
    () => (draft?.deductions || []).reduce((total, item) => total + Number(item.amount || 0), 0),
    [draft],
  );
  const PageLayout = embedded ? "div" : AppLayout;
  const pageLayoutProps = embedded
    ? { className: "payslip-management-embedded" }
    : { title: "Payslip Management", subtitle: "Company templates, monthly payroll generation, and secure payslip history." };

  const startNew = () => {
    setError("");
    setEmployeeSearch("");
    navigate("/payroll/manage/create", {
      state: { company, employeeCategory, month: Number(month), year: Number(year) },
    });
  };

  const startNewForEmployee = (person) => {
    setError("");
    setEmployeeSearch("");
    navigate("/payroll/manage/create", {
      state: {
        company: person.company_name,
        employeeCategory: person.employee_category,
        employee: person,
        month: Number(month),
        year: Number(year),
      },
    });
  };

  const startEdit = (payslip) => {
    setError("");
    navigate(`/payroll/manage/${payslip.id}/edit`);
  };

  const chooseEmployee = async (person) => {
    const category = person.employee_category || employeeCategory;
    setError("");
    setEmployeeCategory(category);
    setDraft({
      ...draft,
      user_id: person.id,
      company_name: person.company_name || PAYROLL_COMPANIES[1],
      employee_info: person.employee_info || {},
      earnings: person.earnings?.length ? person.earnings : draft.earnings,
      deductions: person.deductions?.length ? person.deductions : draft.deductions,
    });
    setEmployeeSearch("");
    setEmployees([]);
    if (!category || !person.company_name) {
      setError("Set the employee category and company before loading payroll details.");
      return;
    }
    if (!person.employee_category) {
      setError("This employee needs a category. Save the employee profile to assign the selected category before loading payroll details.");
      return;
    }
    try {
      const { data } = await client.post("/payroll/preview-bulk", {
        company_name: person.company_name,
        employee_category: category,
        month: Number(draft.month),
        year: Number(draft.year),
        user_ids: [person.id],
      });
      setDraft((current) => ({
        ...current,
        ...data.previews[0],
        id: current.id,
        employee_info: person.employee_info || data.previews[0].employee_info,
      }));
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load attendance and salary information.");
    }
  };

  const setField = (field, value) => setDraft((current) => ({ ...current, [field]: value }));
  const setEmployeeField = (field, value) => setDraft((current) => ({
    ...current,
    employee_info: { ...current.employee_info, [field]: value },
  }));
  const setComponent = (field, index, key, value) => setDraft((current) => ({
    ...current,
    [field]: current[field].map((item, itemIndex) => (
      itemIndex === index ? { ...item, [key]: value } : item
    )),
  }));
  const addComponent = (field) => setDraft((current) => ({
    ...current,
    [field]: [...current[field], { name: "", amount: 0 }],
  }));
  const removeComponent = (field, index) => setDraft((current) => ({
    ...current,
    [field]: current[field].filter((_item, itemIndex) => itemIndex !== index),
  }));
  const addArrearsComponent = () => {
    const description = arrearsDraft.description.trim();
    const arrearsAmount = Number(arrearsDraft.amount);
    if (!description || !Number.isFinite(arrearsAmount) || arrearsAmount <= 0) {
      setError("Enter an arrears description and an amount greater than zero.");
      return;
    }
    const period = `${MONTHS[Number(arrearsDraft.month) - 1]} ${Number(arrearsDraft.year)}`;
    setDraft((current) => ({
      ...current,
      earnings: [...current.earnings, {
        name: `Arrears - ${description} (${period})`,
        amount: arrearsAmount,
      }],
    }));
    setArrearsDraft((current) => ({ ...current, description: "", amount: "" }));
    setError("");
  };

  const previewDraft = async () => {
    setError("");
    if (!draft.user_id) {
      setError("Search for and select an employee.");
      return;
    }
    if (deductions > earnings) {
      setError("Total deductions cannot exceed total earnings.");
      return;
    }
    const previewWindow = window.open("about:blank", "_blank");
    try {
      const payload = {
        ...draft,
        user_id: Number(draft.user_id),
        month: Number(draft.month),
        year: Number(draft.year),
        earnings: draft.earnings.map((row) => ({ ...row, amount: Number(row.amount) })),
        deductions: draft.deductions.map((row) => ({ ...row, amount: Number(row.amount) })),
      };
      if (!draft.id) payload.employee_category = employeeCategory;
      const { data } = await client.post("/payroll/preview", payload, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      if (previewWindow) previewWindow.location = url;
      else window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      previewWindow?.close();
      setError(err?.response?.data?.message || "Could not preview this payslip.");
    }
  };

  const saveEmployeeProfile = async () => {
    if (!draft.user_id) return;
    const departmentName = String(draft.employee_info.department || "").trim();
    const department = departments.find((item) => item.name.toLowerCase() === departmentName.toLowerCase());
    if (departmentName && !department) {
      setError("Choose a department from the employee profile list before saving.");
      return;
    }
    setError("");
    setNotice("");
    try {
      await client.put(`/payroll/people/${draft.user_id}/payroll-profile`, {
        ...draft.employee_info,
        employee_category: employeeCategory,
        department_id: department?.id || "",
      });
      setNotice("Employee profile saved. Loading payroll details...");
      const { data } = await client.post("/payroll/preview-bulk", {
        company_name: draft.company_name,
        employee_category: employeeCategory,
        month: Number(draft.month),
        year: Number(draft.year),
        user_ids: [Number(draft.user_id)],
      });
      setDraft((current) => ({
        ...current,
        ...data.previews[0],
        id: current.id,
        employee_info: current.employee_info,
      }));
      setNotice("Employee profile and payroll details loaded.");
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save employee profile.");
    }
  };

  const saveDraft = async (event, { downloadAfterSave = false, publishAfterSave = false } = {}) => {
    event?.preventDefault();
    setError("");
    if (!draft.user_id) {
      setError("Search for and select an employee.");
      return;
    }
    if (deductions > earnings) {
      setError("Total deductions cannot exceed total earnings.");
      return;
    }
    const payload = {
      ...draft,
      user_id: Number(draft.user_id),
      month: Number(draft.month),
      year: Number(draft.year),
      total_working_days: Number(draft.total_working_days),
      total_paid_days: Number(draft.total_paid_days),
      days_present: Number(draft.days_present),
      lop_days: Number(draft.lop_days),
      earnings: draft.earnings.map((row) => ({ ...row, amount: Number(row.amount) })),
      deductions: draft.deductions.map((row) => ({ ...row, amount: Number(row.amount) })),
    };
    if (!draft.id) payload.employee_category = employeeCategory;
    setSaving(true);
    try {
      let savedId = draft.id;
      let savedPayslip;
      if (draft.id) {
        const { data } = await client.put(`/payroll/payslips/${draft.id}`, payload);
        savedPayslip = data;
      } else {
        const { data } = await client.post("/payroll/payslips", payload);
        savedId = data.id;
        savedPayslip = data;
      }
      if (savedPayslip) setDraft(savedPayslip);
      if (publishAfterSave && savedId) {
        await client.post(`/payroll/payslips/${savedId}/publish`);
        navigate("/payroll/manage");
        return;
      }
      if (downloadAfterSave && savedId) {
        const { data: pdf } = await client.get(
          `/payroll/payslips/${savedId}/pdf`,
          { responseType: "blob" },
        );
        const objectUrl = URL.createObjectURL(pdf);
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = payslipDownloadName(savedPayslip || payload);
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
      } else if (!downloadAfterSave) {
        navigate("/payroll/manage");
      }
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save this payslip.");
    } finally {
      setSaving(false);
    }
  };

  const publish = async () => {
    await saveDraft(null, { publishAfterSave: true });
  };

  const deleteUnpublishedPayslip = async (payslip) => {
    if (!window.confirm("Delete this unpublished payslip? This cannot be undone.")) return;
    setError("");
    try {
      await client.delete(`/payroll/payslips/${payslip.id}`);
      setRefresh((value) => value + 1);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not delete this unpublished payslip.");
    }
  };

  const publishFromList = async (payslip) => {
    setError("");
    try {
      await client.post(`/payroll/payslips/${payslip.id}/publish`);
      setRefresh((value) => value + 1);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not publish this payslip.");
    }
  };

  const markPaid = async (payslip) => {
    setError("");
    try {
      await client.post(`/payroll/payslips/${payslip.id}/mark-paid`);
      setRefresh((value) => value + 1);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not mark this payslip as paid.");
    }
  };

  const getPdf = async (payslip, inline = false) => {
    setError("");
    const previewWindow = inline ? window.open("about:blank", "_blank") : null;
    try {
      const { data } = await client.get(
        `/payroll/payslips/${payslip.id}/pdf${inline ? "?inline=1" : ""}`,
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(data);
      if (inline) {
        if (previewWindow) previewWindow.location = url;
        else window.open(url, "_blank", "noopener,noreferrer");
      } else {
        const link = document.createElement("a");
        link.href = url;
        link.download = payslipDownloadName(payslip);
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      previewWindow?.close();
      setError(err?.response?.data?.message || "Could not open the payslip PDF.");
    }
  };

  const loadRevisionHistory = async (payslip) => {
    setError("");
    try {
      const { data } = await client.get(`/payroll/payslips/${payslip.id}/revisions`);
      setRevisionHistory({ payslip, revisions: data });
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load payslip revision history.");
    }
  };

  const downloadRevisionPdf = async (payslip, revision) => {
    setError("");
    try {
      const { data } = await client.get(
        `/payroll/payslips/${payslip.id}/revisions/${revision.revision}/pdf`,
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = url;
      link.download = payslipDownloadName(revision.snapshot).replace(".pdf", `_revision_${revision.revision}.pdf`);
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not download the historical payslip PDF.");
    }
  };

  const payslipDownloadName = (payslip) => {
    const employeeId = payslip.employee_info?.employee_code || payslip.user_id;
    const companyName = (payslip.company_name || "Company").replace(/[^a-z0-9]+/gi, "_");
    const monthName = MONTHS[Number(payslip.month) - 1] || "Month";
    return `${employeeId}_${companyName}_${monthName}_${payslip.year}_Payslip.pdf`;
  };

  const visiblePayslips = useMemo(
    () => payslips.filter((person) => {
      const isPublished = PUBLISHED_PAYSLIP_STATUSES.includes(person.payslip?.status);
      return (
        (!simple || Boolean(person.payslip_id))
        && (!simple || includeAllStatuses || isPublished === publishedOnly)
        && (!statusFilter || (person.payslip?.status || "pending") === statusFilter)
      );
    }),
    [payslips, statusFilter, simple, publishedOnly, includeAllStatuses],
  );
  const dashboardCounts = useMemo(() => ({
    total: payslips.length,
    generated: payslips.filter((person) => Boolean(person.payslip_id)).length,
    pending: payslips.filter((person) => !person.payslip_id).length,
    published: payslips.filter((person) => ["published", "updated", "paid"].includes(person.payslip?.status)).length,
  }), [payslips]);
  const pendingSelectable = visiblePayslips.filter((person) => (
    company && employeeCategory && person.company_name === company
    && person.employee_category === employeeCategory && person.has_structure && !person.payslip_id
  ));
  const selectableRows = simple
    ? visiblePayslips.filter((person) => Boolean(person.payslip_id))
    : pendingSelectable;
  const selectedUnprocessed = selectedIds.filter((id) => pendingSelectable.some((person) => person.id === id));
  const selectedGenerated = selectedIds
    .map((id) => payslips.find((row) => row.id === id)?.payslip)
    .filter(Boolean);

  const bulkRequest = (ids) => ({
    company_name: company,
    employee_category: employeeCategory,
    month: Number(month),
    year: Number(year),
    user_ids: ids,
  });

  const previewBatch = async () => {
    if (!company || !employeeCategory || !selectedUnprocessed.length) {
      setError("Select a company, employee category, and at least one employee with a salary structure.");
      return;
    }
    setError("");
    setBatchBusy(true);
    try {
      const { data } = await client.post("/payroll/preview-bulk", bulkRequest(selectedUnprocessed));
      setBatchPreviews(data.previews);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not preview selected payslips.");
    } finally {
      setBatchBusy(false);
    }
  };

  const updateBatchComponent = (userId, field, index, key, value) => {
    setBatchPreviews((current) => current.map((previewRow) => (
      previewRow.user_id === userId
        ? { ...previewRow, [field]: previewRow[field].map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value } : row) }
        : previewRow
    )));
  };

  const generateBatch = async () => {
    setError("");
    setBatchBusy(true);
    try {
      await client.post("/payroll/generate-selected", {
        ...bulkRequest(batchPreviews.map((row) => row.user_id)),
        adjustments: batchPreviews.map((row) => ({
          user_id: row.user_id,
          earnings: row.earnings.map((item) => ({ ...item, amount: Number(item.amount) })),
          deductions: row.deductions.map((item) => ({ ...item, amount: Number(item.amount) })),
        })),
      });
      setBatchPreviews([]);
      setSelectedIds([]);
      setRefresh((current) => current + 1);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not generate selected payslips.");
    } finally {
      setBatchBusy(false);
    }
  };

  const downloadBatch = async () => {
    if (!selectedGenerated.length) return;
    setError("");
    setBatchBusy(true);
    try {
      const { data } = await client.post("/payroll/payslips/bulk-download", {
        payslip_ids: selectedGenerated.map((payslip) => payslip.id),
      }, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `payslips_${year}_${String(month).padStart(2, "0")}.zip`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not download selected payslips.");
    } finally {
      setBatchBusy(false);
    }
  };

  const savePayslipTemplate = async () => {
    if (!templateDraft) return;
    setError("");
    setTemplateSaving(true);
    try {
      const { data } = await client.put(
        `/payroll/payslip-templates/${encodeURIComponent(templateDraft.company_name)}`,
        {
          address: templateDraft.address,
          primary_color: templateDraft.primary_color,
          accent_color: templateDraft.accent_color,
          earnings_components: templateDraft.earnings_components_text.split("\n").map((name) => name.trim()).filter(Boolean),
          deductions_components: templateDraft.deductions_components_text.split("\n").map((name) => name.trim()).filter(Boolean),
        },
      );
      const updated = {
        ...data,
        earnings_components_text: data.earnings_components.join("\n"),
        deductions_components_text: data.deductions_components.join("\n"),
      };
      setCompanyTemplates((current) => current.map((item) => item.company_name === data.company_name ? data : item));
      setTemplateDraft(updated);
    } catch (err) {
      setError(err?.response?.data?.message || "Could not save this company template.");
    } finally {
      setTemplateSaving(false);
    }
  };

  const uploadTemplateLogo = async (event) => {
    const file = event.target.files?.[0];
    if (!file || !templateDraft) return;
    setError("");
    setTemplateSaving(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const { data } = await client.post(
        `/payroll/payslip-templates/${encodeURIComponent(templateDraft.company_name)}/logo`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      setCompanyTemplates((current) => current.map((item) => item.company_name === data.company_name ? data : item));
      setTemplateDraft({
        ...data,
        earnings_components_text: data.earnings_components.join("\n"),
        deductions_components_text: data.deductions_components.join("\n"),
      });
    } catch (err) {
      setError(err?.response?.data?.message || "Could not upload this company logo.");
    } finally {
      setTemplateSaving(false);
      event.target.value = "";
    }
  };

  if (isEditor) {
    if (loading && payslipId) return <PageLayout {...pageLayoutProps}><Loader /></PageLayout>;
    if (!draft) return <PageLayout {...pageLayoutProps}><div className="card">{error || "Preparing payslip editor..."}</div></PageLayout>;

    return (
      <PageLayout {...(embedded ? pageLayoutProps : { title: draft.id ? "Edit Payslip" : "Create Payslip", subtitle: "Company-specific payslip editor" })}>
        <section className="card section-gap payslip-editor">
          <div className="card-title-row">
            <div>
              <h2>{draft.id ? "Edit Payslip" : "Create New Payslip"}</h2>
              <p className="muted">{draft.company_name} · {draft.id ? draft.status : "Draft"}</p>
            </div>
            <button type="button" className="btn btn-outline" onClick={() => navigate("/payroll/manage")}>Back to Management</button>
          </div>
          {error && <div className="login-error" role="alert">{error}</div>}
          {notice && <p className="muted" role="status">{notice}</p>}
          <form onSubmit={saveDraft}>
            {!draft.id && (
              <>
                <h3>Company and Employee</h3>
                <div className="form-grid">
                  <div className="form-field">
                    <label>Company</label>
                    <select
                      value={company}
                      required
                      onChange={(event) => {
                        setCompany(event.target.value);
                        setEmployeeSearch("");
                        setEmployees([]);
                        setDraft((current) => ({ ...current, user_id: "", company_name: event.target.value, employee_info: {} }));
                      }}
                    >
                      <option value="">Select a company</option>
                      {PAYROLL_COMPANIES.map((name) => <option key={name} value={name}>{PAYROLL_COMPANY_LABELS[name]}</option>)}
                    </select>
                  </div>
                  {draft.user_id && employeeCategory ? (
                    <div className="form-field">
                      <label>Employee Category</label>
                      <p>{EMPLOYEE_CATEGORIES.find(([value]) => value === employeeCategory)?.[1] || employeeCategory}</p>
                    </div>
                  ) : (
                    <div className="form-field">
                      <label>Employee Category</label>
                      <select value={employeeCategory} required onChange={(event) => {
                        setEmployeeCategory(event.target.value);
                        setEmployeeSearch("");
                        setEmployees([]);
                      }}>
                        <option value="">Select category</option>
                        {EMPLOYEE_CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </div>
                  )}
                  <div className="form-field">
                    <label>Search employees in {company || "selected company"}</label>
                    <input
                      value={employeeSearch}
                      onChange={(event) => setEmployeeSearch(event.target.value)}
                      placeholder={company ? "Search by name or employee ID" : "Select a company first"}
                      disabled={!company || !employeeCategory}
                    />
                    {employees.length > 0 && (
                      <div className="payslip-employee-results">
                        {employees.map((person) => (
                          <button key={person.id} type="button" onClick={() => chooseEmployee(person)}>
                            <span>
                              {person.full_name} · {person.employee_code || "No employee ID"} · {person.designation || "No designation"} ·
                              {person.department || "No department"} · {EMPLOYEE_CATEGORIES.find(([value]) => value === person.employee_category)?.[1] || "Employment type not set"}
                            </span>
                            <span>{PAYROLL_COMPANY_LABELS[person.company_name] || person.company_name}</span>
                          </button>
                        ))}
                      </div>
                    )}
                    {company && employeeCategory && employeeSearch.trim().length >= 2 && !employeeSearching && employees.length === 0 && (
                      <p className="muted">No employees found for this company and search.</p>
                    )}
                  </div>
                </div>
              </>
            )}
            {draft.user_id && (
              <>
                <section className="payslip-editor-section">
                  <h3>Employee Details</h3>
                  <div className="payslip-employee-summary">
                    <strong>{draft.employee_info.full_name}</strong>
                    <span>{draft.employee_info.employee_code}</span>
                    <span>Annual CTC: ₹{amount(draft.employee_info.annual_ctc)}</span>
                    <span>{draft.employee_info.designation || "Designation not set"}</span>
                    <span>{draft.employee_info.department || "Department not set"}</span>
                    <span>{EMPLOYEE_CATEGORIES.find(([value]) => value === employeeCategory)?.[1] || "Employment type not set"}</span>
                    <span>{PAYROLL_COMPANY_LABELS[draft.company_name] || draft.company_name}</span>
                  </div>
                  <div className="form-grid">
                    {EMPLOYEE_FIELDS.map(([key, label]) => (
                      <div className="form-field" key={key}>
                        <label>{label}</label>
                        <input type={key === "date_of_joining" ? "date" : "text"} value={draft.employee_info[key] || ""} onChange={(event) => setEmployeeField(key, event.target.value)} />
                      </div>
                    ))}
                    <div className="form-field">
                      <label>Employment Type</label>
                      <select value={employeeCategory} onChange={(event) => setEmployeeCategory(event.target.value)}>
                        <option value="">Not set</option>
                        {EMPLOYEE_CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </div>
                  </div>
                  {!draft.id && <button type="button" className="btn btn-sm btn-outline" style={{ marginTop: 10 }} onClick={saveEmployeeProfile}>Save Employee Profile</button>}
                </section>
                <section className="payslip-editor-section">
                  <h3>Payroll Details</h3>
                  <div className="form-grid">
                    <div className="form-field"><label>Payroll Month</label><select value={draft.month} onChange={(event) => setField("month", Number(event.target.value))}>{MONTHS.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}</select></div>
                    <div className="form-field"><label>Payroll Year</label><input type="number" min="2000" max="2200" value={draft.year} onChange={(event) => setField("year", event.target.value)} /></div>
                    <div className="form-field"><label>Total Working Days</label><input type="number" min="0" max="31" step="0.5" value={draft.total_working_days} onChange={(event) => setField("total_working_days", event.target.value)} /></div>
                    <div className="form-field"><label>Present Days</label><input type="number" min="0" max="31" step="0.5" value={draft.days_present} onChange={(event) => setField("days_present", event.target.value)} /></div>
                    <div className="form-field"><label>Total Paid Days</label><input type="number" min="0" max="31" step="0.5" value={draft.total_paid_days} onChange={(event) => setField("total_paid_days", event.target.value)} /></div>
                    <div className="form-field"><label>Total Leaves</label><input type="number" value={draft.days_on_leave || 0} readOnly /></div>
                    <div className="form-field"><label>LOP Days</label><input type="number" min="0" max="31" step="0.5" value={draft.lop_days} onChange={(event) => setField("lop_days", event.target.value)} /></div>
                  </div>
                </section>
                <div className="payslip-components-grid">
                  {[
                    ["earnings", "Earnings", earnings],
                    ["deductions", "Deductions", deductions],
                  ].map(([field, label, total]) => (
                    <section className="payslip-editor-section" key={field}>
                      <div className="card-title-row"><h3>{label}</h3><button type="button" className="btn btn-sm btn-outline" onClick={() => addComponent(field)}>+ Add component</button></div>
                      {draft[field].map((item, index) => ({ item, index }))
                        .filter(({ item }) => field !== "earnings" || !isArrearsComponent(item))
                        .map(({ item, index }) => (
                        <div className="payslip-component-row" key={`${field}-${index}`}>
                          <input aria-label={`${label} component name`} value={item.name} onChange={(event) => setComponent(field, index, "name", event.target.value)} placeholder="Component name" />
                          <input aria-label={`${label} amount`} type="number" min="0" step="0.01" value={item.amount} onChange={(event) => setComponent(field, index, "amount", event.target.value)} />
                          <button type="button" className="btn btn-sm btn-outline" aria-label={`Remove ${label} component`} onClick={() => removeComponent(field, index)}>Remove</button>
                        </div>
                      ))}
                      <strong>Total {label}: ₹{amount(total)}</strong>
                    </section>
                  ))}
                </div>
                <section className="payslip-editor-section">
                  <h3>Arrears</h3>
                  <p className="muted">Arrears apply only to this employee and payroll month. Edit an existing entry below or add one.</p>
                  {draft.earnings.map((item, index) => (
                    isArrearsComponent(item) && (
                      <div className="payslip-component-row" key={`arrears-${index}`}>
                        <input
                          aria-label="Arrears description"
                          required
                          value={item.name}
                          onChange={(event) => setComponent("earnings", index, "name", event.target.value)}
                        />
                        <input
                          aria-label="Arrears amount"
                          type="number"
                          min="0"
                          step="0.01"
                          required
                          value={item.amount}
                          onChange={(event) => setComponent("earnings", index, "amount", event.target.value)}
                        />
                        <button
                          type="button"
                          className="btn btn-sm btn-outline"
                          aria-label="Remove arrears"
                          onClick={() => removeComponent("earnings", index)}
                        >
                          Remove
                        </button>
                      </div>
                    )
                  ))}
                  <div className="salary-arrears-form">
                    <input
                      aria-label="New arrears description"
                      value={arrearsDraft.description}
                      onChange={(event) => setArrearsDraft({ ...arrearsDraft, description: event.target.value })}
                      placeholder="Description"
                    />
                    <input
                      aria-label="New arrears amount"
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={arrearsDraft.amount}
                      onChange={(event) => setArrearsDraft({ ...arrearsDraft, amount: event.target.value })}
                      placeholder="Amount ₹"
                    />
                    <select aria-label="Arrears salary month" value={arrearsDraft.month} onChange={(event) => setArrearsDraft({ ...arrearsDraft, month: Number(event.target.value) })}>
                      {MONTHS.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}
                    </select>
                    <input aria-label="Arrears salary year" type="number" min="2000" max="2200" value={arrearsDraft.year} onChange={(event) => setArrearsDraft({ ...arrearsDraft, year: Number(event.target.value) })} />
                    <button type="button" className="btn btn-sm btn-outline" onClick={addArrearsComponent}>Add Arrears</button>
                  </div>
                </section>
                <section className="payslip-net-summary">
                  <strong>Net Pay: ₹{amount(earnings - deductions)}</strong>
                  <span>{numberToWordsInr(earnings - deductions)}</span>
                </section>
                <section className="payslip-editor-section">
                  <h3>Payslip PDF</h3>
                  <div className="payslip-pdf-download-card">
                    <div className="payslip-pdf-details">
                      <strong>{draft.employee_info.full_name || "Employee not selected"}</strong>
                      <span>{PAYROLL_COMPANY_LABELS[draft.company_name] || draft.company_name}</span>
                      <span>{MONTHS[Number(draft.month) - 1]} {draft.year}</span>
                      <span>Template: {PAYROLL_COMPANY_LABELS[draft.company_name] || draft.company_name}</span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={saving || !draft.user_id}
                      onClick={() => saveDraft(null, { downloadAfterSave: true })}
                    >
                      {saving ? "Preparing PDF..." : "Download Payslip PDF"}
                    </button>
                  </div>
                </section>
              </>
            )}
            <div className="payslip-editor-actions">
              <button type="button" className="btn btn-outline" onClick={() => navigate("/payroll/manage")}>Cancel</button>
              <button type="button" className="btn btn-outline" disabled={!draft.user_id || saving} onClick={previewDraft}>Preview Payslip</button>
              <button type="submit" className="btn btn-primary" disabled={saving || !draft.user_id}>{saving ? "Saving..." : draft.id ? "Update Payslip" : "Save as Draft"}</button>
              <button type="button" className="btn btn-success" disabled={saving || !draft.user_id || draft.status === "paid"} onClick={publish}>{draft.status === "published" || draft.status === "updated" ? "Publish Update" : "Publish Payslip"}</button>
            </div>
          </form>
        </section>
      </PageLayout>
    );
  }

  return (
    <PageLayout {...pageLayoutProps}>
      {!simple && (
        <div className="section-gap" style={{ display: "flex", gap: 8 }}>
          <button className={`btn ${managementTab === "payslips" ? "btn-primary" : "btn-outline"}`} onClick={() => setManagementTab("payslips")}>Payslip Dashboard</button>
          <button className={`btn ${managementTab === "templates" ? "btn-primary" : "btn-outline"}`} onClick={() => setManagementTab("templates")}>Company Templates</button>
        </div>
      )}
      {error && <div className="login-error section-gap" role="alert">{error}</div>}

      {managementTab === "payslips" || simple ? (
        <>
          {!simple && <div className="payslip-dashboard-metrics section-gap">
            {[
              ["Total Employees", dashboardCounts.total],
              ["Generated Payslips", dashboardCounts.generated],
              ["Pending Payslips", dashboardCounts.pending],
              ["Published Payslips", dashboardCounts.published],
            ].map(([label, count]) => (
              <div className="card payslip-dashboard-metric" key={label}>
                <span className="muted">{label}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>}
          <section className={simple ? "payslip-simple-list section-gap" : "card section-gap"}>
            {!simple && <div className="card-title-row">
              <div>
                <h2>Monthly Payslips</h2>
                <p className="muted" style={{ fontSize: 12, margin: "4px 0 0" }}>
                  Select a company and category to generate accurate, attendance-aware payslips.
                </p>
              </div>
              <button className="btn btn-primary" onClick={startNew}>+ Create Payslip</button>
            </div>}
            <div className="form-grid section-gap" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
              {simple ? (
                <>
                  <div className="form-field">
                    <label>Company</label>
                    <select value={company} onChange={(event) => setCompany(event.target.value)}>
                      <option value="">All companies</option>
                      {PAYROLL_COMPANIES.map((name) => <option key={name} value={name}>{PAYROLL_COMPANY_LABELS[name]}</option>)}
                    </select>
                  </div>
                  {allPeriods && (
                    <>
                      <div className="form-field">
                        <label>Month</label>
                        <select
                          value={month}
                          onChange={(event) => setMonth(event.target.value ? Number(event.target.value) : "")}
                        >
                          <option value="">All months</option>
                          {MONTHS.map((name, index) => (
                            <option key={name} value={index + 1}>{name}</option>
                          ))}
                        </select>
                      </div>
                      <div className="form-field">
                        <label>Year</label>
                        <input
                          type="number"
                          min="2000"
                          max="2200"
                          value={year}
                          onChange={(event) => setYear(event.target.value ? Number(event.target.value) : "")}
                          placeholder="All years"
                        />
                      </div>
                    </>
                  )}
                  <div className="form-field">
                    <label>Search employee</label>
                    <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or employee ID" />
                  </div>
                  {!publishedOnly && (
                    <div className="form-field">
                      <label>Status</label>
                      <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                        <option value="">{simple && !includeAllStatuses ? "All unpublished" : "All statuses"}</option>
                        <option value="draft">Draft</option>
                        {simple && <option value="processed">Processed</option>}
                        {includeAllStatuses && (
                          <>
                            <option value="published">Published</option>
                            <option value="updated">Updated</option>
                            <option value="paid">Paid</option>
                          </>
                        )}
                        {!simple && (
                          <>
                            <option value="processed">Processed</option>
                            <option value="published">Published</option>
                            <option value="updated">Updated</option>
                            <option value="paid">Paid</option>
                          </>
                        )}
                      </select>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className="form-field">
                    <label>Company</label>
                    <select value={company} onChange={(event) => { setCompany(event.target.value); setEmployeeId(""); setSelectedIds([]); }}>
                      <option value="">All companies</option>
                      {PAYROLL_COMPANIES.map((name) => <option key={name} value={name}>{PAYROLL_COMPANY_LABELS[name]}</option>)}
                    </select>
                  </div>
                  <div className="form-field">
                    <label>Employee Category</label>
                    <select value={employeeCategory} onChange={(event) => { setEmployeeCategory(event.target.value); setEmployeeId(""); setSelectedIds([]); }}>
                      <option value="">All categories</option>
                      {EMPLOYEE_CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                  </div>
                  <div className="form-field">
                    <label>Employee</label>
                    <select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)}>
                      <option value="">All employees</option>
                      {payslips.map((person) => <option key={person.id} value={person.id}>{person.full_name} · {person.employee_code}</option>)}
                    </select>
                  </div>
                  <div className="form-field">
                    <label>Salary Month</label>
                    <select value={month} onChange={(event) => setMonth(Number(event.target.value))}>
                      {MONTHS.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}
                    </select>
                  </div>
                  <div className="form-field">
                    <label>Year</label>
                    <input type="number" min="2000" max="2200" value={year} onChange={(event) => setYear(Number(event.target.value))} />
                  </div>
                  <div className="form-field">
                    <label>Status</label>
                    <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                      <option value="">All statuses</option>
                      <option value="pending">Pending</option>
                      <option value="draft">Draft</option>
                      <option value="processed">Processed</option>
                      <option value="published">Published</option>
                      <option value="updated">Updated</option>
                      <option value="paid">Paid</option>
                    </select>
                  </div>
                  <div className="form-field">
                    <label>Search</label>
                    <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Employee name or ID" />
                  </div>
                </>
              )}
            </div>
            {!simple && <div className="payslip-bulk-actions">
              <span className="muted">{selectedIds.length} selected</span>
              {!company || !employeeCategory ? <span className="muted">Set Company and Employee Category to select pending payslips for generation.</span> : null}
              <button className="btn btn-sm btn-outline" disabled={!selectedUnprocessed.length || batchBusy} onClick={previewBatch}>
                {batchBusy ? "Preparing..." : "Preview Selected"}
              </button>
              <button className="btn btn-sm btn-outline" disabled={!selectedGenerated.length || batchBusy} onClick={downloadBatch}>
                {batchBusy ? "Preparing..." : "Download Selected ZIP"}
              </button>
            </div>}
            {loading ? <Loader /> : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      {!simple && <th>
                        <input
                          type="checkbox"
                          aria-label="Select all eligible employees"
                          checked={selectableRows.length > 0 && selectableRows.every((person) => selectedIds.includes(person.id))}
                          disabled={!selectableRows.length}
                          onChange={(event) => setSelectedIds((current) => event.target.checked
                            ? [...new Set([...current, ...selectableRows.map((person) => person.id)])]
                            : current.filter((id) => !selectableRows.some((person) => person.id === id)))}
                        />
                      </th>}
                      {!simple && <th>Employee ID</th>}
                      <th>Employee</th><th>Company</th>
                      {simple ? <><th>Salary Structure</th><th>Month / Year</th><th>Present Days</th><th>LOP Days</th><th>Gross Earnings</th><th>Deductions</th><th>Net Pay</th></> : <>
                        <th>Category</th><th>Designation</th><th>Gross Earnings</th><th>Deductions</th><th>Net Pay</th>
                      </>}
                      <th>Status</th><th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visiblePayslips.length === 0 && (
                      <tr className="empty-row">
                        <td colSpan={11}>
                          {publishedOnly
                            ? "No published payslips match these filters."
                            : includeAllStatuses
                              ? "No employee payslips have been generated for this period yet."
                            : simple
                              ? "No unpublished generated payslips match these filters."
                              : "No generated payslips match these filters."}
                        </td>
                      </tr>
                    )}
                    {visiblePayslips.map((person) => {
                      const payslip = person.payslip;
                      const status = payslip?.status || "pending";
                      const canSelect = Boolean(payslip || (
                        company && employeeCategory && person.company_name === company
                        && person.employee_category === employeeCategory && person.has_structure
                      ));
                      return (
                        <tr key={person.id}>
                          {!simple && <td>
                            <input
                              type="checkbox"
                              aria-label={`Select ${person.full_name}`}
                              disabled={!canSelect}
                              checked={selectedIds.includes(person.id)}
                              onChange={(event) => setSelectedIds((current) => event.target.checked
                                ? [...current, person.id]
                                : current.filter((id) => id !== person.id))}
                            />
                          </td>}
                          {!simple && <td>{person.employee_code || "—"}</td>}
                          <td>
                            <strong>{person.full_name}</strong>
                            {simple
                              ? <div className="muted" style={{ fontSize: 11 }}>{person.employee_code || "No employee ID"}</div>
                              : <div className="muted" style={{ fontSize: 11 }}>{person.department || "Department not set"}</div>}
                          </td>
                          <td>{PAYROLL_COMPANY_LABELS[person.company_name] || person.company_name}</td>
                          {simple ? <>
                            <td>{payslip?.employee_info?.salary_structure_name || person.salary_structure_name || "—"}</td>
                            <td>{payslip ? `${MONTHS[payslip.month - 1]} ${payslip.year}` : "—"}</td>
                            <td>{payslip?.days_present ?? "—"}</td>
                            <td>{payslip?.lop_days ?? "—"}</td>
                            <td>₹{amount(payslip?.gross_earnings)}</td>
                            <td>₹{amount(payslip?.total_deductions)}</td>
                            <td><strong>₹{amount(payslip?.net_pay)}</strong></td>
                          </> : <>
                            <td>{EMPLOYEE_CATEGORIES.find(([value]) => value === person.employee_category)?.[1] || "Not set"}</td>
                            <td>{person.designation || "—"}</td>
                            <td>₹{amount(payslip?.gross_earnings ?? person.monthly_gross)}</td>
                            <td>₹{amount(payslip?.total_deductions ?? (person.monthly_gross - person.monthly_net))}</td>
                            <td><strong>₹{amount(payslip?.net_pay ?? person.monthly_net)}</strong></td>
                          </>}
                          <td>{payslip ? <Badge status={status} /> : <span className="chip orange">{person.has_structure ? "Pending" : "Salary setup needed"}</span>}</td>
                          <td>
                            <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                              {payslip ? (
                                <>
                                  {!simple && <button className="btn btn-sm btn-outline" onClick={() => setPreview(payslip)}>View</button>}
                                  {!publishedOnly && <button className="btn btn-sm btn-outline" onClick={() => startEdit(payslip)}>{simple ? "Edit Payslip" : "Edit"}</button>}
                                  <button className="btn btn-sm btn-outline" onClick={() => getPdf(payslip, true)}>{simple ? "Preview Payslip" : "Preview PDF"}</button>
                                  <button className="btn btn-sm btn-outline" onClick={() => getPdf(payslip)}>{simple ? "Download PDF" : "Download"}</button>
                                  {!simple && payslip.revision_count > 0 && <button className="btn btn-sm btn-outline" onClick={() => loadRevisionHistory(payslip)}>History</button>}
                                  {!publishedOnly && status === "draft" && <button className="btn btn-sm btn-success" onClick={() => publishFromList(payslip)}>{simple ? "Publish Payslip" : "Publish"}</button>}
                                  {!simple && status === "processed" && <button className="btn btn-sm btn-success" onClick={() => markPaid(payslip)}>Mark Paid</button>}
                                  {!publishedOnly && ["draft", "processed"].includes(status) && (
                                    <button
                                      className="btn btn-sm btn-outline"
                                      onClick={() => deleteUnpublishedPayslip(payslip)}
                                    >
                                      Delete
                                    </button>
                                  )}
                                </>
                              ) : simple ? (
                                <span className="muted">—</span>
                              ) : (
                                <button className="btn btn-sm btn-primary" disabled={!person.has_structure} onClick={() => startNewForEmployee(person)}>Generate</button>
                              )}
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
          {batchPreviews.length > 0 && (
            <div className="modal-overlay" onClick={() => setBatchPreviews([])}>
              <div className="modal-box payslip-batch-preview" onClick={(event) => event.stopPropagation()}>
                <div className="card-title-row">
                  <div><h3>Review Bulk Payslips</h3><p className="muted">{MONTHS[Number(month) - 1]} {year} · {company}</p></div>
                  <button className="btn btn-sm btn-outline" onClick={() => setBatchPreviews([])}>Close</button>
                </div>
                <p className="muted">Review and edit each employee's amounts before creating these payslips.</p>
                <div className="payslip-batch-list">
                  {batchPreviews.map((row) => {
                    const rowEarnings = row.earnings.reduce((sum, item) => sum + Number(item.amount || 0), 0);
                    const rowDeductions = row.deductions.reduce((sum, item) => sum + Number(item.amount || 0), 0);
                    return (
                      <section className="payslip-batch-employee" key={row.user_id}>
                        <strong>{row.employee_info.full_name} · {row.employee_info.employee_code}</strong>
                        <div className="payslip-components-grid">
                          {[
                            ["earnings", "Earnings"], ["deductions", "Deductions"],
                          ].map(([field, label]) => (
                            <div key={field}>
                              <h4>{label}</h4>
                              {row[field].map((item, index) => (
                                <div className="payslip-component-row" key={`${row.user_id}-${field}-${index}`}>
                                  <input aria-label={`${label} name`} value={item.name} onChange={(event) => updateBatchComponent(row.user_id, field, index, "name", event.target.value)} />
                                  <input aria-label={`${label} amount`} type="number" min="0" step="0.01" value={item.amount} onChange={(event) => updateBatchComponent(row.user_id, field, index, "amount", event.target.value)} />
                                </div>
                              ))}
                            </div>
                          ))}
                        </div>
                        <strong>Gross ₹{amount(rowEarnings)} · Deductions ₹{amount(rowDeductions)} · Net ₹{amount(rowEarnings - rowDeductions)}</strong>
                      </section>
                    );
                  })}
                </div>
                <div className="payslip-editor-actions">
                  <button className="btn btn-outline" onClick={() => setBatchPreviews([])}>Cancel</button>
                  <button className="btn btn-primary" disabled={batchBusy || batchPreviews.some((row) => row.deductions.reduce((sum, item) => sum + Number(item.amount || 0), 0) > row.earnings.reduce((sum, item) => sum + Number(item.amount || 0), 0))} onClick={generateBatch}>
                    {batchBusy ? "Generating..." : `Generate ${batchPreviews.length} Payslip${batchPreviews.length === 1 ? "" : "s"}`}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <section className="card">
          <div className="card-title-row"><div><h2>Company Payslip Templates</h2><p className="muted">Configure each company's branded layout once; generated payslips retain a historical template snapshot.</p></div></div>
          {templateDraft && (
            <>
              <div className="form-field payslip-template-company">
                <label>Company Template</label>
                <select
                  value={templateDraft.company_name}
                  onChange={(event) => {
                    const selected = companyTemplates.find((item) => item.company_name === event.target.value);
                    if (selected) setTemplateDraft({
                      ...selected,
                      earnings_components_text: selected.earnings_components.join("\n"),
                      deductions_components_text: selected.deductions_components.join("\n"),
                    });
                  }}
                >
                  {companyTemplates.map((item) => <option key={item.company_name}>{item.company_name}</option>)}
                </select>
              </div>
              <p className="muted">Unique layout: <strong>{templateDraft.layout_key.replaceAll("_", " ")}</strong>. Each company uses its own logo placement and page design.</p>
              <div className="form-grid">
                <div className="form-field"><label>Company Address</label><textarea rows={3} value={templateDraft.address} onChange={(event) => setTemplateDraft({ ...templateDraft, address: event.target.value })} /></div>
                <div className="form-field"><label>Upload Company Logo</label><input type="file" accept="image/png,image/jpeg,image/webp" disabled={templateSaving} onChange={uploadTemplateLogo} /><span className="muted">PNG, JPEG, or WEBP; 5 MB maximum.</span></div>
                <div className="form-field"><label>Primary Colour</label><input type="color" value={templateDraft.primary_color} onChange={(event) => setTemplateDraft({ ...templateDraft, primary_color: event.target.value })} /></div>
                <div className="form-field"><label>Accent Colour</label><input type="color" value={templateDraft.accent_color} onChange={(event) => setTemplateDraft({ ...templateDraft, accent_color: event.target.value })} /></div>
                <div className="form-field"><label>Earnings Components (one per line)</label><textarea rows={7} value={templateDraft.earnings_components_text} onChange={(event) => setTemplateDraft({ ...templateDraft, earnings_components_text: event.target.value })} /></div>
                <div className="form-field"><label>Deductions Components (one per line)</label><textarea rows={7} value={templateDraft.deductions_components_text} onChange={(event) => setTemplateDraft({ ...templateDraft, deductions_components_text: event.target.value })} /></div>
              </div>
              <div className="payslip-editor-actions">
                <button className="btn btn-primary" disabled={templateSaving} onClick={savePayslipTemplate}>{templateSaving ? "Saving..." : "Save Template"}</button>
              </div>
            </>
          )}
        </section>
      )}
      {preview && <PayslipDetailModal payslip={preview} onClose={() => setPreview(null)} onDownload={() => getPdf(preview)} />}
      {revisionHistory && (
        <div className="modal-overlay" onClick={() => setRevisionHistory(null)}>
          <div className="modal-box payslip-batch-preview" onClick={(event) => event.stopPropagation()}>
            <div className="card-title-row">
              <div><h3>Payslip Revision History</h3><p className="muted">{revisionHistory.payslip.employee_name} · {MONTHS[revisionHistory.payslip.month - 1]} {revisionHistory.payslip.year}</p></div>
              <button className="btn btn-sm btn-outline" onClick={() => setRevisionHistory(null)}>Close</button>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Revision</th><th>Action</th><th>Created</th><th>Gross</th><th>Deductions</th><th>Net Pay</th><th>PDF</th></tr></thead>
                <tbody>
                  {revisionHistory.revisions.map((revision) => (
                    <tr key={revision.id}>
                      <td>{revision.revision}</td>
                      <td>{revision.action}</td>
                      <td>{new Date(revision.created_at).toLocaleString()}</td>
                      <td>₹{amount(revision.snapshot.gross_earnings)}</td>
                      <td>₹{amount(revision.snapshot.total_deductions)}</td>
                      <td>₹{amount(revision.snapshot.net_pay)}</td>
                      <td>
                        {revision.snapshot.pdf_path
                          ? <button className="btn btn-sm btn-outline" onClick={() => downloadRevisionPdf(revisionHistory.payslip, revision)}>Download</button>
                          : "—"}
                      </td>
                    </tr>
                  ))}
                  {revisionHistory.revisions.length === 0 && <tr className="empty-row"><td colSpan={7}>No revisions recorded.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}
