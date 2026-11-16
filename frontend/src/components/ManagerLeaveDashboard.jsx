import { useCallback, useEffect, useRef, useState } from "react";
import client from "../api/client";
import Badge from "./Badge";
import Loader from "./Loader";
import StatCard from "./StatCard";
import LeaveReasonPreview from "./LeaveReasonPreview";

const EMPTY_FILTERS = {
  employee_id: "",
  leave_type_id: "",
  status: "all",
  start_date: "",
  end_date: "",
};

export default function ManagerLeaveDashboard() {
  const [summary, setSummary] = useState(null);
  const [requests, setRequests] = useState([]);
  const [types, setTypes] = useState([]);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busyRequestId, setBusyRequestId] = useState(null);
  const [policyOpen, setPolicyOpen] = useState(false);
  const [policyMode, setPolicyMode] = useState("default");
  const [policyValues, setPolicyValues] = useState({});
  const [editingEmployee, setEditingEmployee] = useState(null);
  const [employeeForm, setEmployeeForm] = useState({
    employee_id: "",
    leave_type_id: "",
    annual_entitlement: "",
  });
  const [savingEntitlement, setSavingEntitlement] = useState(false);
  const [selectedRequestStatus, setSelectedRequestStatus] = useState(null);
  const [sort, setSort] = useState({ key: "start_date", direction: "desc" });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [balanceSort, setBalanceSort] = useState({ key: "employee_name", direction: "asc" });
  const [balancePage, setBalancePage] = useState(1);
  const [balancePageSize, setBalancePageSize] = useState(10);
  const requestsSectionRef = useRef(null);

  const loadData = useCallback(async (activeFilters = EMPTY_FILTERS) => {
    setError("");
    setLoading(true);
    const params = Object.fromEntries(
      Object.entries(activeFilters).filter(([, value]) => value && value !== "all")
    );
    try {
      const [summaryResponse, requestsResponse, typesResponse] = await Promise.all([
        client.get("/leave/team-summary"),
        client.get("/leave/team-requests", { params }),
        client.get("/leave/types"),
      ]);
      setSummary(summaryResponse.data);
      setRequests(requestsResponse.data);
      setTypes(typesResponse.data);
      setPolicyValues((current) => {
        const values = { ...current };
        for (const type of typesResponse.data) {
          if (!(type.id in values)) values[type.id] = type.annual_quota;
        }
        return values;
      });
      return true;
    } catch (err) {
      setError(err?.response?.data?.message || "Could not load team leave information.");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const updateFilter = (event) => {
    setFilters((current) => ({ ...current, [event.target.name]: event.target.value }));
  };

  const applyFilters = (event) => {
    event.preventDefault();
    setSuccess("");
    setSelectedRequestStatus(null);
    loadData(filters);
  };

  const clearFilters = () => {
    setFilters(EMPTY_FILTERS);
    setSelectedRequestStatus(null);
    setSuccess("");
    loadData(EMPTY_FILTERS);
  };

  const showRequestsForStatus = (status) => {
    const nextFilters = { ...EMPTY_FILTERS, status };
    setFilters(nextFilters);
    setSelectedRequestStatus(status);
    setSuccess("");
    loadData(nextFilters);
    requestsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const openEmployeeEditor = (employee, leaveTypeId, entitlement) => {
    setEditingEmployee(employee);
    setEmployeeForm({
      employee_id: String(employee.employee_id),
      leave_type_id: String(leaveTypeId),
      annual_entitlement: String(entitlement),
    });
  };

  const savePolicy = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    const changed = types
      .filter((type) => Number(policyValues[type.id]) !== Number(type.annual_quota))
      .map((type) => ({
        leave_type_id: type.id,
        annual_quota: Number(policyValues[type.id]),
        annual_entitlement: Number(policyValues[type.id]),
        leave_type: type.name,
        old_entitlement: Number(type.annual_quota || 0),
      }));
    if (!changed.length) {
      setPolicyOpen(false);
      setSuccess("No entitlement changes to save.");
      return;
    }

    if (policyMode === "team") {
      const employees = (summary?.employees || []).filter(
        (employee) => employee.eligible_for_entitlement_edit
      );
      if (!employees.length) {
        setError("There are no eligible active employees on your team.");
        return;
      }
      const details = changed.map((item) => {
        const currentValues = [...new Set(employees.flatMap((employee) =>
          employee.balances
            .filter((balance) => balance.leave_type === item.leave_type)
            .map((balance) => Number(balance.annual_entitlement))
        ))].sort((a, b) => a - b);
        return `${item.leave_type}: current entitlement${currentValues.length === 1 ? "" : "s"} ${currentValues.join(", ") || item.old_entitlement}, new entitlement ${item.annual_entitlement} days`;
      });
      const message = `Apply these entitlements to all ${employees.length} eligible active direct reports for ${summary.year}?\n\n${details.join("\n")}\n\nThis updates employee allocations in your authorized team scope.`;
      if (!window.confirm(message)) return;
    }

    setSavingEntitlement(true);
    try {
      if (policyMode === "default") {
        await client.put("/leave/policy/defaults", {
          entitlements: changed.map(({ leave_type_id, annual_quota }) => ({
            leave_type_id,
            annual_quota,
          })),
        });
      } else {
        await client.put("/leave/policy/team", {
          entitlements: changed.map(({ leave_type_id, annual_entitlement }) => ({
            leave_type_id,
            annual_entitlement,
          })),
        });
      }
      setPolicyOpen(false);
      if (await loadData(filters)) {
        setSuccess(policyMode === "default"
          ? "Default leave policy updated for future allocations."
          : "Leave entitlements updated for your team.");
      }
    } catch (err) {
      const response = err?.response?.data;
      const conflicts = response?.conflicts || (response?.conflict ? [response.conflict] : []);
      const conflictDetails = conflicts.map((conflict) =>
        `${conflict.employee_name}: ${conflict.leave_type} has ${conflict.approved_leave_taken} approved days`
      );
      setError([
        response?.message || "Could not save leave entitlements.",
        ...conflictDetails,
      ].join(" "));
    } finally {
      setSavingEntitlement(false);
    }
  };

  const saveEmployeeEntitlement = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    setSavingEntitlement(true);
    try {
      await client.put(`/leave/policy/employees/${employeeForm.employee_id}`, {
        leave_type_id: Number(employeeForm.leave_type_id),
        annual_entitlement: Number(employeeForm.annual_entitlement),
      });
      setEditingEmployee(null);
      if (await loadData(filters)) {
        setSuccess("Employee leave entitlement updated.");
      }
    } catch (err) {
      const response = err?.response?.data;
      const conflict = response?.conflict;
      const conflictDetail = conflict
        ? ` Approved leave taken: ${conflict.approved_leave_taken} days.`
        : "";
      setError(`${response?.message || "Could not update this employee's entitlement."}${conflictDetail}`);
    } finally {
      setSavingEntitlement(false);
    }
  };

  const decide = async (request, decision) => {
    const action = decision === "approved" ? "approve" : "reject";
    if (!window.confirm(`${action === "approve" ? "Approve" : "Reject"} ${request.employee_name}'s ${request.leave_type} request?`)) {
      return;
    }
    const comment = window.prompt("Optional review comment:", "");
    if (comment === null) return;

    setError("");
    setSuccess("");
    setBusyRequestId(request.id);
    try {
      await client.post(`/leave/${request.id}/decision`, { decision, comment });
      if (await loadData(filters)) {
        setSuccess(`Leave request ${decision}.`);
      }
    } catch (err) {
      setError(err?.response?.data?.message || `Could not ${action} this leave request.`);
    } finally {
      setBusyRequestId(null);
    }
  };

  const counts = summary?.counts || {};
  const hasPendingRequests = requests.some((request) => request.status === "pending");
  const sortedRequests = [...requests].sort((a, b) => {
    const left = a[sort.key] ?? "";
    const right = b[sort.key] ?? "";
    const comparison = typeof left === "number" && typeof right === "number"
      ? left - right
      : String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
    return comparison * (sort.direction === "asc" ? 1 : -1);
  });
  const pageCount = Math.max(1, Math.ceil(sortedRequests.length / pageSize));
  const pageRequests = sortedRequests.slice((page - 1) * pageSize, page * pageSize);
  const balanceRows = (summary?.employees || []).flatMap((employee) => employee.balances.map((balance) => ({
    ...balance,
    employee_id: employee.employee_id,
    employee_code: employee.employee_code,
    employee_name: employee.employee_name,
    eligible_for_entitlement_edit: employee.eligible_for_entitlement_edit,
  })));
  const sortedBalanceRows = [...balanceRows].sort((a, b) => {
    const left = a[balanceSort.key] ?? "";
    const right = b[balanceSort.key] ?? "";
    const comparison = typeof left === "number" && typeof right === "number"
      ? left - right
      : String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
    return comparison * (balanceSort.direction === "asc" ? 1 : -1);
  });
  const balancePageCount = Math.max(1, Math.ceil(sortedBalanceRows.length / balancePageSize));
  const pageBalances = sortedBalanceRows.slice((balancePage - 1) * balancePageSize, balancePage * balancePageSize);

  useEffect(() => { setPage(1); }, [requests, pageSize]);
  useEffect(() => { setBalancePage(1); }, [summary, balancePageSize]);

  const sortButton = (key, label) => (
    <button
      type="button"
      className="table-sort-button"
      onClick={() => {
        setSort((current) => ({ key, direction: current.key === key && current.direction === "asc" ? "desc" : "asc" }));
        setPage(1);
      }}
    >
      {label}{sort.key === key ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
    </button>
  );
  const balanceSortButton = (key, label) => (
    <button
      type="button"
      className="table-sort-button"
      onClick={() => {
        setBalanceSort((current) => ({ key, direction: current.key === key && current.direction === "asc" ? "desc" : "asc" }));
        setBalancePage(1);
      }}
    >
      {label}{balanceSort.key === key ? (balanceSort.direction === "asc" ? " ▲" : " ▼") : ""}
    </button>
  );

  return (
    <section className="section-gap" aria-labelledby="manager-leave-heading">
      <div className="card-title-row">
        <h3 id="manager-leave-heading">Team Leave Management</h3>
        <span className="muted">{summary?.year || new Date().getFullYear()}</span>
      </div>
      {error && <div className="login-error" role="alert">{error}</div>}
      {success && <div className="notice-success" role="status">{success}</div>}
      {loading && summary && <div className="muted" role="status">Refreshing team leave information...</div>}

      {loading && !summary ? <Loader label="Loading team leave information..." /> : !summary ? (
        <div className="muted">
          Team leave information is unavailable.{" "}
          <button className="btn btn-sm btn-outline" type="button" onClick={() => loadData()}>
            Retry
          </button>
        </div>
      ) : (
        <>
          <div className="card-title-row" style={{ justifyContent: "flex-end" }}>
            <button className="btn btn-sm btn-outline" type="button" onClick={() => setPolicyOpen(true)}>
              Edit Leave Policy
            </button>
          </div>
          <div className="stat-grid section-gap">
            <a href="#team-leave-requests" className={`manager-leave-stat-button${selectedRequestStatus === "all" ? " selected" : ""}`} onClick={(event) => { event.preventDefault(); showRequestsForStatus("all"); }} aria-current={selectedRequestStatus === "all" ? "true" : undefined}>
              <StatCard label="Total Leave Requests" value={counts.total || 0} icon="✈" color="blue" />
            </a>
            <a href="#team-leave-requests" className={`manager-leave-stat-button${selectedRequestStatus === "pending" ? " selected" : ""}`} onClick={(event) => { event.preventDefault(); showRequestsForStatus("pending"); }} aria-current={selectedRequestStatus === "pending" ? "true" : undefined}>
              <StatCard label="Pending Requests" value={counts.pending || 0} icon="!" color="amber" />
            </a>
            <a href="#team-leave-requests" className={`manager-leave-stat-button${selectedRequestStatus === "approved" ? " selected" : ""}`} onClick={(event) => { event.preventDefault(); showRequestsForStatus("approved"); }} aria-current={selectedRequestStatus === "approved" ? "true" : undefined}>
              <StatCard label="Approved Requests" value={counts.approved || 0} icon="✓" color="green" />
            </a>
            <a href="#team-leave-requests" className={`manager-leave-stat-button${selectedRequestStatus === "rejected" ? " selected" : ""}`} onClick={(event) => { event.preventDefault(); showRequestsForStatus("rejected"); }} aria-current={selectedRequestStatus === "rejected" ? "true" : undefined}>
              <StatCard label="Rejected Requests" value={counts.rejected || 0} icon="×" color="orange" />
            </a>
          </div>

          <div className="card section-gap">
            <div className="card-title-row"><h3>Employee Leave Balances</h3></div>
            {!summary?.employees?.length ? (
              <div className="muted">No employees are assigned to your team.</div>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{balanceSortButton("employee_name", "Employee")}</th>
                      <th>{balanceSortButton("employee_code", "Employee ID")}</th>
                      <th>{balanceSortButton("leave_type", "Leave Type")}</th>
                      <th>{balanceSortButton("annual_entitlement", "Annual Entitlement")}</th>
                      <th>{balanceSortButton("approved_leave_taken", "Approved Leave Taken")}</th>
                      <th>{balanceSortButton("remaining_leave", "Remaining Leave")}</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {!balanceRows.length && <tr className="empty-row"><td colSpan={7}>No employee leave balances to show.</td></tr>}
                    {pageBalances.map((row) => (
                      <tr key={`${row.employee_id}-${row.leave_type}`}>
                        <td>{row.employee_name}</td>
                        <td>{row.employee_code}</td>
                        <td>{row.leave_type}</td>
                        <td>{row.annual_entitlement} days</td>
                        <td>{row.approved_leave_taken} days</td>
                        <td>{row.remaining_leave} days</td>
                        <td>{row.eligible_for_entitlement_edit ? (
                          <button
                            className="btn btn-sm btn-outline"
                            type="button"
                            onClick={() => openEmployeeEditor(row, row.leave_type_id, row.annual_entitlement)}
                          >
                            Edit
                          </button>
                        ) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!!balanceRows.length && (
              <div className="table-pagination">
                <span>{`Showing ${(balancePage - 1) * balancePageSize + 1}–${Math.min(balancePage * balancePageSize, sortedBalanceRows.length)} of ${sortedBalanceRows.length}`}</span>
                <label>Rows per page
                  <select value={balancePageSize} onChange={(event) => { setBalancePageSize(Number(event.target.value)); setBalancePage(1); }}>
                    {[10, 25, 50].map((size) => <option key={size} value={size}>{size}</option>)}
                  </select>
                </label>
                <button type="button" className="btn btn-sm btn-outline" disabled={balancePage <= 1} onClick={() => setBalancePage((current) => current - 1)}>Previous</button>
                <span>Page {Math.min(balancePage, balancePageCount)} of {balancePageCount}</span>
                <button type="button" className="btn btn-sm btn-outline" disabled={balancePage >= balancePageCount} onClick={() => setBalancePage((current) => current + 1)}>Next</button>
              </div>
            )}
          </div>

          <div id="team-leave-requests" className="card manager-leave-requests" ref={requestsSectionRef}>
            <div className="card-title-row">
              <h3>Team Leave History &amp; Approvals</h3>
              {selectedRequestStatus && (
                <span className="manager-leave-filter-label">
                  Showing {selectedRequestStatus === "all" ? "all" : selectedRequestStatus} requests ({requests.length})
                </span>
              )}
            </div>
            <form className="form-grid section-gap" onSubmit={applyFilters}>
              <div className="form-field">
                <label htmlFor="team-leave-employee">Employee</label>
                <select id="team-leave-employee" name="employee_id" value={filters.employee_id} onChange={updateFilter}>
                  <option value="">All employees</option>
                  {summary?.employees?.map((employee) => (
                    <option key={employee.employee_id} value={employee.employee_id}>
                      {employee.employee_name} ({employee.employee_code})
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="team-leave-type">Leave Type</label>
                <select id="team-leave-type" name="leave_type_id" value={filters.leave_type_id} onChange={updateFilter}>
                  <option value="">All leave types</option>
                  {types.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="team-leave-status">Status</label>
                <select id="team-leave-status" name="status" value={filters.status} onChange={updateFilter}>
                  <option value="all">All statuses</option>
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="team-leave-start">From date</label>
                <input id="team-leave-start" type="date" name="start_date" value={filters.start_date} onChange={updateFilter} />
              </div>
              <div className="form-field">
                <label htmlFor="team-leave-end">To date</label>
                <input id="team-leave-end" type="date" name="end_date" value={filters.end_date} onChange={updateFilter} />
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "end" }}>
                <button className="btn btn-sm btn-primary" type="submit" disabled={loading}>Filter</button>
                <button className="btn btn-sm btn-outline" type="button" onClick={clearFilters} disabled={loading}>Clear</button>
              </div>
            </form>
            <div className="table-wrap manager-leave-table-wrap">
              <table className={`data-table manager-leave-table${hasPendingRequests ? " has-actions" : " no-actions"}`}>
                <colgroup>
                  <col className="manager-leave-col-employee" />
                  <col className="manager-leave-col-id" />
                  <col className="manager-leave-col-type" />
                  <col className="manager-leave-col-date" />
                  <col className="manager-leave-col-date" />
                  <col className="manager-leave-col-days" />
                  <col className="manager-leave-col-reason" />
                  <col className="manager-leave-col-remaining" />
                  <col className="manager-leave-col-status" />
                  {hasPendingRequests && <col className="manager-leave-col-action" />}
                </colgroup>
                <thead>
                  <tr><th>{sortButton("employee_name", "Employee")}</th><th>{sortButton("employee_code", "Employee ID")}</th><th>{sortButton("leave_type", "Leave Type")}</th><th>{sortButton("start_date", "From")}</th><th>{sortButton("end_date", "To")}</th><th>{sortButton("days", "Days")}</th><th>Reason</th><th>{sortButton("remaining_leave", "Remaining")}</th><th>{sortButton("status", "Status")}</th>{hasPendingRequests && <th>Action</th>}</tr>
                </thead>
                <tbody>
                  {!requests.length && <tr className="empty-row"><td colSpan={hasPendingRequests ? 10 : 9}>No team leave requests match these filters.</td></tr>}
                  {pageRequests.map((request) => (
                    <tr key={request.id}>
                      <td>{request.employee_name}</td>
                      <td>{request.employee_code}</td>
                      <td>{request.leave_type}</td>
                      <td>{request.start_date}</td>
                      <td>{request.end_date}</td>
                      <td>{request.days}</td>
                      <td><LeaveReasonPreview reason={request.reason} /></td>
                      <td>{request.remaining_leave == null ? "—" : `${request.remaining_leave} days`}</td>
                      <td><Badge status={request.status} /></td>
                      {hasPendingRequests && (
                        <td>
                          {request.status === "pending" ? (
                            <div className="manager-leave-actions">
                              <button className="btn btn-sm btn-success" disabled={busyRequestId !== null} onClick={() => decide(request, "approved")}>
                                {busyRequestId === request.id ? "Saving..." : "Approve"}
                              </button>
                              <button className="btn btn-sm btn-danger" disabled={busyRequestId !== null} onClick={() => decide(request, "rejected")}>Reject</button>
                            </div>
                          ) : "—"}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-pagination">
              <span>{sortedRequests.length ? `Showing ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, sortedRequests.length)} of ${sortedRequests.length}` : "0 requests"}</span>
              <label>Rows per page
                <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}>
                  {[10, 25, 50].map((size) => <option key={size} value={size}>{size}</option>)}
                </select>
              </label>
              <button type="button" className="btn btn-sm btn-outline" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Previous</button>
              <span>Page {Math.min(page, pageCount)} of {pageCount}</span>
              <button type="button" className="btn btn-sm btn-outline" disabled={page >= pageCount} onClick={() => setPage((current) => current + 1)}>Next</button>
            </div>
          </div>
        </>
      )}

      {policyOpen && (
        <div className="modal-overlay" onClick={() => !savingEntitlement && setPolicyOpen(false)}>
          <div className="modal-box" onClick={(event) => event.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>Edit Leave Policy</h3>
            <form onSubmit={savePolicy}>
              {types.map((type) => (
                <div className="form-field" key={type.id}>
                  <label htmlFor={`policy-${type.id}`}>{type.name} annual entitlement (days)</label>
                  <input
                    id={`policy-${type.id}`}
                    type="number"
                    min="0"
                    max="365"
                    step="0.5"
                    required
                    value={policyValues[type.id] ?? type.annual_quota}
                    onChange={(event) => setPolicyValues((current) => ({
                      ...current,
                      [type.id]: event.target.value,
                    }))}
                  />
                </div>
              ))}
              <fieldset className="form-field" style={{ border: 0, padding: 0 }}>
                <legend style={{ fontWeight: 700, marginBottom: 8 }}>How should these changes apply?</legend>
                <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
                  <input type="radio" name="policy-mode" value="default" checked={policyMode === "default"} onChange={() => setPolicyMode("default")} />
                  Update Default Policy Only — future allocations only; existing employee entitlements stay unchanged.
                </label>
                <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input type="radio" name="policy-mode" value="team" checked={policyMode === "team"} onChange={() => setPolicyMode("team")} />
                  Apply to All Employees — eligible active direct reports for this year.
                </label>
              </fieldset>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" disabled={savingEntitlement} onClick={() => setPolicyOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={savingEntitlement}>
                  {savingEntitlement ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingEmployee && (
        <div className="modal-overlay" onClick={() => !savingEntitlement && setEditingEmployee(null)}>
          <div className="modal-box" onClick={(event) => event.stopPropagation()}>
            <h3 style={{ marginBottom: 16 }}>Edit Employee Leave Entitlement</h3>
            <form onSubmit={saveEmployeeEntitlement}>
              <div className="form-field">
                <label htmlFor="edit-leave-employee">Employee</label>
                <select
                  id="edit-leave-employee"
                  required
                  value={employeeForm.employee_id}
                  onChange={(event) => {
                    const selectedEmployee = summary.employees.find(
                      (employee) => String(employee.employee_id) === event.target.value
                    );
                    const selectedBalance = selectedEmployee?.balances.find(
                      (balance) => String(balance.leave_type_id) === employeeForm.leave_type_id
                    );
                    setEmployeeForm((current) => ({
                      ...current,
                      employee_id: event.target.value,
                      annual_entitlement: String(selectedBalance?.annual_entitlement ?? ""),
                    }));
                  }}
                >
                  {summary.employees.filter((employee) => employee.eligible_for_entitlement_edit).map((employee) => (
                    <option key={employee.employee_id} value={employee.employee_id}>
                      {employee.employee_name} ({employee.employee_code})
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="edit-leave-type">Leave type</label>
                <select
                  id="edit-leave-type"
                  required
                  value={employeeForm.leave_type_id}
                  onChange={(event) => {
                    const selectedType = summary.employees
                      .find((employee) => String(employee.employee_id) === employeeForm.employee_id)
                      ?.balances.find((balance) => String(balance.leave_type_id) === event.target.value);
                    setEmployeeForm((current) => ({
                      ...current,
                      leave_type_id: event.target.value,
                      annual_entitlement: String(selectedType?.annual_entitlement ?? ""),
                    }));
                  }}
                >
                  {types.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="edit-employee-entitlement">Annual entitlement (days)</label>
                <input
                  id="edit-employee-entitlement"
                  type="number"
                  min="0"
                  max="365"
                  step="0.5"
                  required
                  value={employeeForm.annual_entitlement}
                  onChange={(event) => setEmployeeForm((current) => ({ ...current, annual_entitlement: event.target.value }))}
                />
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-outline" disabled={savingEntitlement} onClick={() => setEditingEmployee(null)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={savingEntitlement}>
                  {savingEntitlement ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
