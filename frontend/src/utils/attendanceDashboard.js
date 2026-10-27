import { fmtTime, fromLocalInput, localDateStr } from "./attendanceTime.js";

export const DEMO_EMPLOYEES = [
  { employee_code: "DEMO-2001", full_name: "Maya Chen", department: "Development", designation: "Software Engineer" },
  { employee_code: "DEMO-2002", full_name: "Noah Williams", department: "Development", designation: "Software Engineer" },
  { employee_code: "DEMO-2003", full_name: "Aisha Patel", department: "Design", designation: "Product Designer" },
  { employee_code: "DEMO-2004", full_name: "Lucas Martin", department: "QA", designation: "QA Engineer" },
  { employee_code: "DEMO-2005", full_name: "Sofia Garcia", department: "Backend", designation: "Backend Engineer" },
  { employee_code: "DEMO-2006", full_name: "Ethan Brooks", department: "Backend", designation: "Backend Engineer" },
  { employee_code: "DEMO-2007", full_name: "Isabella Kim", department: "Frontend", designation: "Frontend Engineer" },
  { employee_code: "DEMO-2008", full_name: "Oliver Singh", department: "Frontend", designation: "Frontend Engineer" },
  { employee_code: "DEMO-2009", full_name: "Amara Okafor", department: "HR", designation: "People Operations" },
  { employee_code: "DEMO-2010", full_name: "Daniel Costa", department: "QA", designation: "QA Engineer" },
];

const ONE_DAY_MS = 24 * 60 * 60 * 1000;

export function parseDateKey(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

export function dateKey(date) {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
}

export function addDays(value, amount) {
  const date = parseDateKey(value);
  date.setUTCDate(date.getUTCDate() + amount);
  return dateKey(date);
}

export function dateRange(period, selectedDate, today = localDateStr()) {
  const selected = parseDateKey(selectedDate);
  let start = selectedDate;
  let end = selectedDate;

  if (period === "weekly") {
    const mondayOffset = (selected.getUTCDay() + 6) % 7;
    start = addDays(selectedDate, -mondayOffset);
    end = addDays(start, 6);
  } else if (period === "monthly") {
    start = `${selected.getUTCFullYear()}-${String(selected.getUTCMonth() + 1).padStart(2, "0")}-01`;
    end = dateKey(new Date(Date.UTC(selected.getUTCFullYear(), selected.getUTCMonth() + 1, 0)));
  }

  if (start <= today && end > today) end = today;
  return { from: start, to: end };
}

export function dateKeys(from, to) {
  if (from > to) return [];
  const count = Math.round((parseDateKey(to) - parseDateKey(from)) / ONE_DAY_MS) + 1;
  return Array.from({ length: count }, (_, index) => addDays(from, index));
}

export function dateRangeError(from, to) {
  if (!from || !to) return "Select both a from date and a to date.";
  const validDateKey = (value) => (
    /^\d{4}-\d{2}-\d{2}$/.test(value)
    && dateKey(parseDateKey(value)) === value
  );
  if (!validDateKey(from) || !validDateKey(to)) return "Enter valid from and to dates.";
  if (from > to) return "The from date must not be later than the to date.";
  if (dateKeys(from, to).length > 93) return "Choose a date range of 93 days or less.";
  return "";
}

function localMinutes(iso) {
  if (!iso) return null;
  const text = fmtTime(iso);
  const match = text.match(/(\d{1,2}):(\d{2})\s+(AM|PM)/i);
  if (!match) return null;
  let hour = Number(match[1]) % 12;
  if (match[3].toUpperCase() === "PM") hour += 12;
  return hour * 60 + Number(match[2]);
}

function presentRecord(record) {
  return Boolean(record) && (
    ["present", "regularized", "half_day"].includes(record.status) || Boolean(record.clock_in)
  );
}

function localTimeToIso(date, minutes) {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return fromLocalInput(`${date}T${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}`);
}

export function formatMinutes(minutes) {
  if (minutes === null || minutes === undefined || !Number.isFinite(minutes)) return "—";
  const rounded = Math.round(minutes);
  const hour24 = Math.floor(rounded / 60) % 24;
  const hour12 = hour24 % 12 || 12;
  return `${String(hour12).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")} ${hour24 >= 12 ? "PM" : "AM"}`;
}

export function formatPercent(value) {
  return value === null || value === undefined ? "—" : `${value}%`;
}

export function createDemoEmployees(from, to, sourceEmployees = DEMO_EMPLOYEES) {
  const holidays = [];
  const dates = dateKeys(from, to);
  const employees = sourceEmployees.map((employee, employeeIndex) => {
    const records = dates.map((workDate) => {
      const date = parseDateKey(workDate);
      const weekend = date.getUTCDay() === 0 || date.getUTCDay() === 6;
      const fixedHoliday = (
        (date.getUTCMonth() === 0 && date.getUTCDate() === 26)
        || (date.getUTCMonth() === 7 && date.getUTCDate() === 15)
        || (date.getUTCMonth() === 9 && date.getUTCDate() === 2)
        || (date.getUTCMonth() === 11 && date.getUTCDate() === 25)
      );
      if (weekend || fixedHoliday) {
        holidays.push({ holiday_date: workDate, name: weekend ? "Weekend" : "Public holiday" });
        return {
          id: `demo-${employeeIndex}-${workDate}`,
          work_date: workDate,
          clock_in: null,
          clock_out: null,
          status: "holiday",
          check_in_status: null,
        };
      }
      if (workDate > localDateStr()) {
        return {
          id: `demo-${employeeIndex}-${workDate}`,
          work_date: workDate,
          clock_in: null,
          clock_out: null,
          status: "scheduled",
          check_in_status: null,
        };
      }
      const ordinal = Math.floor(date.getTime() / ONE_DAY_MS);
      const absent = (ordinal + employeeIndex * 5) % 19 === 0;
      const checkInMinutes = 9 * 60 + 10 + ((ordinal * 3 + employeeIndex * 7) % 41);
      const checkOutMinutes = 18 * 60 + 15 + ((ordinal * 5 + employeeIndex * 11) % 46);
      const checkIn = absent ? null : localTimeToIso(workDate, checkInMinutes);
      const checkOut = absent ? null : localTimeToIso(workDate, checkOutMinutes);
      return {
        id: `demo-${employeeIndex}-${workDate}`,
        work_date: workDate,
        clock_in: checkIn,
        clock_out: checkOut,
        status: absent ? "absent" : "present",
        check_in_status: absent ? null : checkInMinutes <= 9 * 60 + 40 ? "in_time" : "late",
      };
    });
    return {
      id: employee.id || `demo-user-${employeeIndex}`,
      employee_code: employee.employee_code,
      full_name: employee.full_name,
      designation: employee.designation,
      department: employee.department,
      records,
      approved_leave_dates: [],
      is_demo: true,
    };
  });

  return {
    employees,
    holidays: [...new Map(holidays.map((holiday) => [holiday.holiday_date, holiday])).values()],
  };
}

export function attendanceMetrics(employees, dates, holidays, policy, today = localDateStr()) {
  const holidayDates = new Set((holidays || []).map((holiday) => holiday.holiday_date));
  const checkInDeadline = timeMinutes(policy?.official_check_in, 9 * 60 + 30)
    + Number(policy?.attendance_buffer_minutes ?? 10);
  const checkOutDeadline = timeMinutes(policy?.official_check_out, 18 * 60 + 30);
  const eligible = [];
  const present = [];
  const checkIns = [];
  const checkOuts = [];
  let onTimeCheckIns = 0;
  let onTimeCheckOuts = 0;
  let holidaysInRange = 0;

  for (const date of dates) {
    const weekday = parseDateKey(date).getUTCDay();
    const isHoliday = holidayDates.has(date);
    if (date > today) continue;
    let markedHoliday = false;
    if (isHoliday) {
      holidaysInRange += 1;
      continue;
    }

    for (const employee of employees) {
      if ((employee.approved_leave_dates || []).includes(date)) continue;
      const record = (employee.records || []).find((item) => item.work_date === date);
      if (record?.status === "holiday") {
        markedHoliday = true;
        continue;
      }
      const scheduledDay = (weekday >= 1 && weekday <= 5)
        || Boolean(record && ["present", "regularized", "half_day", "absent"].includes(record.status));
      if (!scheduledDay) continue;
      const presentRecord = record && (
        ["present", "regularized", "half_day"].includes(record.status) || Boolean(record.clock_in)
      );
      eligible.push({ employee, date, record });

      if (!presentRecord) continue;
      present.push({ employee, date, record });
      const checkIn = localMinutes(record.clock_in);
      const checkOut = localMinutes(record.clock_out);
      if (checkIn !== null) {
        checkIns.push(checkIn);
        if (checkIn <= checkInDeadline) onTimeCheckIns += 1;
      }
      if (checkOut !== null) {
        checkOuts.push(checkOut);
        if (checkOut >= checkOutDeadline) onTimeCheckOuts += 1;
      }
    }
    if (markedHoliday && weekday !== 0 && weekday !== 6) holidaysInRange += 1;
  }

  const percentage = (value) => eligible.length ? Math.round((value / eligible.length) * 100) : null;
  const average = (values) => values.length
    ? values.reduce((sum, value) => sum + value, 0) / values.length
    : null;
  const presentDates = new Set(present.map((item) => `${item.employee.id}:${item.date}`));

  return {
    eligibleDays: eligible.length,
    presentDays: present.length,
    absentDays: Math.max(0, eligible.length - presentDates.size),
    holidays: holidaysInRange,
    totalDays: dates.length,
    attendancePct: percentage(present.length),
    onTimeCheckInPct: percentage(onTimeCheckIns),
    onTimeCheckOutPct: percentage(onTimeCheckOuts),
    averageCheckIn: average(checkIns),
    averageCheckOut: average(checkOuts),
    onTimeCheckIns,
    onTimeCheckOuts,
    isFutureRange: dates.length > 0 && dates.every((date) => date > today),
  };
}

function timeMinutes(value, fallback) {
  if (!value || !/^\d{2}:\d{2}$/.test(value)) return fallback;
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

export function buildAttendanceTrend(employees, dates, holidays, policy, today = localDateStr()) {
  return dates.map((date) => {
    const metrics = attendanceMetrics(employees, [date], holidays, policy, today);
    const dayRecords = employees.flatMap((employee) => (
      (employee.records || [])
        .filter((record) => record.work_date === date)
        .map((record) => ({ employee, record }))
    ));
    const inTimes = dayRecords.map(({ record }) => localMinutes(record.clock_in)).filter((value) => value !== null);
    const outTimes = dayRecords.map(({ record }) => localMinutes(record.clock_out)).filter((value) => value !== null);
    return {
      date,
      checkIn: inTimes.length ? inTimes.reduce((sum, value) => sum + value, 0) / inTimes.length : null,
      checkOut: outTimes.length ? outTimes.reduce((sum, value) => sum + value, 0) / outTimes.length : null,
      attendancePct: metrics.attendancePct,
    };
  });
}

export function dayRecordFor(employee, selectedDate) {
  return (employee?.records || []).find((record) => record.work_date === selectedDate) || null;
}
