"""Excel (.xlsx) downloads.

* Employees export their own attendance history (the sheet only says whether a photo was sent,
  and whether each punch was in/out of office).
* Managers / HR Ops / Operations export every attendance table they can see, with exactly
  the same scope and privacy redaction as the on-screen views.
* A generic table exporter turns any table a signed-in user is looking at into an .xlsx.
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from app.extensions import db
from app.models import Attendance, AttendanceSession, Holiday, LeaveRequest, User, AttendanceRegularizationReason
from app.roles import MANAGER, HR_OPERATIONS, OPERATIONS, SUPER_ADMIN
from app.utils.excel import fmt_time, fmt_datetime, xlsx_response
from app.routes import attendance as att

bp = Blueprint("exports", __name__, url_prefix="/api")

VIEW_ROLES = (MANAGER, HR_OPERATIONS, OPERATIONS, SUPER_ADMIN)
MAX_GRID_CELLS = 20000        # people x days in one team export
MAX_TABLE_ROWS = 50000
MAX_TABLE_COLS = 60

STATUS_LABELS = {
    "present": "Present", "half_day": "Half day", "absent": "Absent", "on_leave": "On leave",
    "regularized": "Regularized", "holiday": "Holiday", "not_clocked_in": "Not clocked in yet",
}


def _place(within, has_coords=True):
    if within is True:
        return "In office"
    if within is False:
        return "Out of office"
    return "Location not captured" if not has_coords else "No office set"


def _photo(has):
    return "Photo sent" if has else "No photo"


def _day_name(d):
    return d.strftime("%a")


def _daterange(first, last):
    d = first
    while d <= last:
        yield d
        d += timedelta(days=1)


def _range_args(default_first=None):
    """?from&to, or ?month&year. Returns ((first, last), None) or (None, error)."""
    try:
        if request.args.get("month") and request.args.get("year"):
            m, y = int(request.args["month"]), int(request.args["year"])
            first = date(y, m, 1)
            last = (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)) - timedelta(days=1)
        else:
            today = date.today()
            first = datetime.strptime(request.args["from"], "%Y-%m-%d").date() if request.args.get("from") else (default_first or today.replace(day=1))
            last = datetime.strptime(request.args["to"], "%Y-%m-%d").date() if request.args.get("to") else today
    except (ValueError, KeyError):
        return None, (jsonify({"message": "Please give a valid date range."}), 400)
    if first > last:
        return None, (jsonify({"message": "'from' must not be after 'to'."}), 400)
    if (last - first).days > 365:
        return None, (jsonify({"message": "Please choose a range of one year or less."}), 400)
    return (first, last), None


DAY_HEADERS = ["Date", "Day", "Employee code", "Employee", "Designation", "Status", "First check-in", "Last check-out",
               "Hours worked", "Check-ins", "Re-entries", "Time away (min)", "Any punch out of office",
               "Regularization", "Regularization reason", "Regularization note", "Reviewed by", "Review comment",
               "Corrected by manager", "Correction note", "Holiday / leave"]
SESSION_HEADERS_FULL = ["Date", "Employee code", "Employee", "Check-in #", "Check-in time", "Check-in location",
                        "Check-in latitude", "Check-in longitude", "Check-in photo", "Check-out time", "Check-out location",
                        "Check-out latitude", "Check-out longitude", "Check-out photo", "Hours", "Gap before (min)",
                        "Re-entry reason", "Check-in note", "Check-out note"]


def _build_people_sheets(users, first, last, redact_fn, note):
    """Daily summary + per-check-in detail for `users` over [first, last].
    redact_fn(user) -> True when the viewer may NOT see coordinates / photo flags."""
    ids = [u.id for u in users] or [0]
    recs = {}
    for r in Attendance.query.filter(Attendance.user_id.in_(ids), Attendance.work_date >= first, Attendance.work_date <= last).all():
        recs[(r.user_id, r.work_date)] = r
    holidays = {h.holiday_date: h.name for h in Holiday.query.filter(Holiday.holiday_date >= first, Holiday.holiday_date <= last).all()}
    leave_by_user = {}
    for lv in LeaveRequest.query.filter(LeaveRequest.user_id.in_(ids), LeaveRequest.status == "approved",
                                         LeaveRequest.start_date <= last, LeaveRequest.end_date >= first).all():
        d = max(lv.start_date, first)
        while d <= min(lv.end_date, last):
            leave_by_user.setdefault(lv.user_id, {})[d] = lv.leave_type.name if lv.leave_type else "Leave"
            d += timedelta(days=1)

    today = date.today()
    day_rows, session_rows = [], []
    for u in users:
        redact = redact_fn(u)
        for d in _daterange(first, last):
            rec = recs.get((u.id, d))
            leave = leave_by_user.get(u.id, {}).get(d)
            hol = holidays.get(d)
            if rec and (rec.clock_in or rec.status):
                status = STATUS_LABELS.get(rec.status, rec.status or "")
            elif leave:
                status = "On leave"
            elif hol:
                status = "Holiday"
            elif d.weekday() >= 5:
                status = "Weekend"
            elif d > today:
                status = ""
            else:
                status = "No record"
            sessions = rec.effective_sessions() if rec else []
            reentries = max(0, len(sessions) - 1)
            away = 0
            prev = None
            for s in sessions:
                if prev is not None and prev.clock_out:
                    away += max(0, round((s.clock_in - prev.clock_out).total_seconds() / 60))
                prev = s
            outside = any(x is False for s in sessions for x in (s.clock_in_within_geofence, s.clock_out_within_geofence))
            any_loc = any(x is not None for s in sessions for x in (s.clock_in_within_geofence, s.clock_out_within_geofence))
            reg = rec.regularization_status if rec else None
            day_rows.append([
                d, _day_name(d), u.employee_code, u.full_name, u.designation or "", status,
                fmt_time(rec.clock_in) if rec else "", fmt_time(rec.clock_out) if rec and rec.clock_out else ("Still clocked in" if rec and rec.clock_in else ""),
                round(rec.total_hours or 0, 2) if rec and rec.clock_in else "", len(sessions) or "", reentries or "", away or "",
                ("Yes" if outside else "No") if any_loc else ("" if not sessions else "Location not captured"),
                (reg or ("Regularized" if rec and rec.is_regularized else "")).title() if (reg or (rec and rec.is_regularized)) else "",
                rec.reason.label if rec and rec.reason else "", rec.regularization_note or "" if rec else "",
                rec.reviewed_by_user.full_name if rec and rec.reviewed_by_user else "", rec.regularization_review_comment or "" if rec else "",
                rec.edited_by_user.full_name if rec and rec.edited_by_user else "", rec.edit_note or "" if rec else "",
                hol or leave or "",
            ])
            prev = None
            for s in sessions:
                gap = ""
                if prev is not None and prev.clock_out:
                    gap = max(0, round((s.clock_in - prev.clock_out).total_seconds() / 60))
                has_in = s.clock_in_lat is not None
                has_out = s.clock_out_lat is not None
                session_rows.append([
                    d, u.employee_code, u.full_name, s.session_no,
                    fmt_time(s.clock_in), _place(s.clock_in_within_geofence, has_in),
                    "—" if redact else (s.clock_in_lat if s.clock_in_lat is not None else ""),
                    "—" if redact else (s.clock_in_lng if s.clock_in_lng is not None else ""),
                    "—" if redact else _photo(bool(s.clock_in_selfie)),
                    fmt_time(s.clock_out) if s.clock_out else "Still clocked in",
                    _place(s.clock_out_within_geofence, has_out) if s.clock_out else "",
                    "—" if redact else (s.clock_out_lat if s.clock_out_lat is not None else ""),
                    "—" if redact else (s.clock_out_lng if s.clock_out_lng is not None else ""),
                    "—" if redact else (_photo(bool(s.clock_out_selfie)) if s.clock_out else ""),
                    s.duration_hours() if s.clock_out else "", gap, s.reentry_reason or "",
                    s.clock_in_note or "", s.clock_out_note or "",
                ])
                prev = s
    return [
        {"name": "Daily summary", "headers": DAY_HEADERS, "rows": day_rows, "note": note},
        {"name": "Check-in details", "headers": SESSION_HEADERS_FULL, "rows": session_rows, "note": note},
    ]


def _summary_sheet(users, first, last, day_rows_sheet):
    """Per-person totals for the range (present / half / absent / leave / hours / re-entries)."""
    idx = {h: i for i, h in enumerate(DAY_HEADERS)}
    per = {}
    for row in day_rows_sheet["rows"]:
        key = row[idx["Employee code"]]
        t = per.setdefault(key, {"name": row[idx["Employee"]], "present": 0, "half": 0, "absent": 0, "leave": 0,
                                  "hol": 0, "hours": 0.0, "re": 0, "out": 0, "norec": 0})
        st = row[idx["Status"]]
        t["present"] += st in ("Present", "Regularized")
        t["half"] += st == "Half day"
        t["absent"] += st == "Absent"
        t["leave"] += st == "On leave"
        t["hol"] += st == "Holiday"
        t["norec"] += st == "No record"
        t["hours"] += row[idx["Hours worked"]] or 0
        t["re"] += row[idx["Re-entries"]] or 0
        t["out"] += row[idx["Any punch out of office"]] == "Yes"
    rows = [[code, t["name"], t["present"], t["half"], t["absent"], t["leave"], t["hol"], t["norec"],
             round(t["hours"], 2), t["re"], t["out"]] for code, t in per.items()]
    return {"name": "Summary", "rows": rows, "note": day_rows_sheet.get("note"),
            "headers": ["Employee code", "Employee", "Present (incl. regularized)", "Half days", "Absent", "On leave",
                        "Holidays", "No record", "Hours worked", "Re-entries", "Days with a punch out of office"]}


# ---------------------------------------------------------------------------------------
# Employee: my own history
# ---------------------------------------------------------------------------------------

@bp.get("/attendance/export/my")
@jwt_required()
def export_my_attendance():
    """The signed-in person's own attendance for a month (?month&year) or range (?from&to),
    default this month — every check-in with in/out-of-office and 'photo sent' flags."""
    rng, err = _range_args()
    if err:
        return err
    first, last = rng
    me = db.session.get(User, int(get_jwt_identity()))
    note = f"Attendance history — {me.full_name} ({me.employee_code}) — {first.strftime('%d-%b-%Y')} to {last.strftime('%d-%b-%Y')}"
    sheets = _build_people_sheets([me], first, last, lambda _user: False, note)
    sheets.insert(0, _summary_sheet([me], first, last, sheets[0]))
    return xlsx_response(sheets, f"My_Attendance_{first.isoformat()}_to_{last.isoformat()}")


# ---------------------------------------------------------------------------------------
# Manager / HR Ops / Operations
# ---------------------------------------------------------------------------------------

def _guard_viewer():
    claims = get_jwt()
    if claims.get("role") not in VIEW_ROLES:
        return None, None, (jsonify({"message": "You do not have permission to export team attendance."}), 403)
    return claims, int(get_jwt_identity()), None


@bp.get("/attendance/export/team")
@jwt_required()
def export_team_attendance():
    """Everyone in scope (or one person via ?user_id) over a date range: summary, daily
    rows and every individual check-in. Same scope + privacy as the on-screen views."""
    claims, viewer_id, err = _guard_viewer()
    if err:
        return err
    rng, err = _range_args()
    if err:
        return err
    first, last = rng
    scope = att._viewer_scope(claims, viewer_id)
    if request.args.get("user_id"):
        try:
            uid = int(request.args["user_id"])
        except ValueError:
            return jsonify({"message": "user_id must be a number."}), 400
        if uid not in scope:
            return jsonify({"message": "You do not have permission to export this person's attendance."}), 403
        scope = {uid}
    users = (User.query.filter(User.id.in_(scope or {0}), User.is_active.is_(True), User.role != "contract_employee")
             .order_by(User.full_name.asc()).all())
    days = (last - first).days + 1
    if len(users) * days > MAX_GRID_CELLS:
        return jsonify({"message": f"That is too much in one file ({len(users)} people x {days} days). Please choose a shorter range."}), 400
    note = f"Team attendance — {first.strftime('%d-%b-%Y')} to {last.strftime('%d-%b-%Y')} — {len(users)} people"
    sheets = _build_people_sheets(
        users, first, last,
        lambda user: not att._can_view_sensitive(claims, viewer_id, user),
        note,
    )
    sheets.insert(0, _summary_sheet(users, first, last, sheets[0]))
    return xlsx_response(sheets, f"Team_Attendance_{first.isoformat()}_to_{last.isoformat()}")


@bp.get("/attendance/export/team-day")
@jwt_required()
def export_team_day():
    """The 'who is where' table for one day, including people who have not clocked in."""
    claims, viewer_id, err = _guard_viewer()
    if err:
        return err
    try:
        target = datetime.strptime(request.args.get("date", date.today().isoformat()), "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"message": "date must be YYYY-MM-DD."}), 400
    data = att._build_overview(claims, viewer_id, target)
    rows = []
    for p in data["people"]:
        u, rec = p["user"], p["record"] or {}
        loc = p["last_known_location"]
        rows.append([
            u["employee_code"], u["full_name"], u["designation"] or "", STATUS_LABELS.get(p["status"], p["status"]),
            _fmt_iso_time(rec.get("clock_in")), _fmt_iso_time(rec.get("clock_out")) if rec.get("clock_out") else ("Still clocked in" if rec.get("clock_in") else ""),
            rec.get("total_hours") or "", p["session_count"] or "", p["reentry_count"] or "",
            (p["latest_reentry"] or {}).get("reason", ""), "Yes" if p["outside_office"] else "No",
            ("" if not loc else loc["latitude"]), ("" if not loc else loc["longitude"]),
            ("" if not loc else _place(loc["within_geofence"])), ("" if not loc else _fmt_iso_dt(loc["as_of"])),
        ])
    sheet = {"name": "Team today", "note": f"Team attendance on {target.strftime('%d-%b-%Y')}" + (f" — {data['holiday_name']}" if data["holiday_name"] else ""),
             "headers": ["Employee code", "Employee", "Designation", "Status", "First check-in", "Last check-out", "Hours worked",
                         "Check-ins", "Re-entries", "Latest re-entry reason", "Any punch out of office",
                         "Last known latitude", "Last known longitude", "Last known place", "Last known at"],
             "rows": rows}
    return xlsx_response([sheet], f"Team_Attendance_{target.isoformat()}")


def _parse_iso(value):
    return datetime.fromisoformat(value.replace("Z", "")) if value else None


def _fmt_iso_time(value):
    return fmt_time(_parse_iso(value))


def _fmt_iso_dt(value):
    return fmt_datetime(_parse_iso(value))


@bp.get("/attendance/export/reentries")
@jwt_required()
def export_reentries():
    claims, viewer_id, err = _guard_viewer()
    if err:
        return err
    rng, err = att._parse_range()
    if err:
        return err
    data = att._build_reentries(claims, viewer_id, *rng)
    rows = [[
        i["work_date"], i["user"]["employee_code"], i["user"]["full_name"], i["user"]["designation"] or "", i["session_no"],
        _fmt_iso_time(i["previous_clock_out"]), _fmt_iso_time(i["clock_in"]), i["gap_minutes"] if i["gap_minutes"] is not None else "",
        i["reason"] or "", "Yes" if i["outside_office"] else "No", "Yes" if i["still_clocked_in"] else "No",
    ] for i in data["reentries"]]
    sheet = {"name": "Re-entries", "note": f"Re-entries (checked in again) — {data['from']} to {data['to']}",
             "headers": ["Date", "Employee code", "Employee", "Designation", "Check-in #", "Previous check-out", "Checked in again at",
                         "Time away (min)", "Reason given", "Out of office", "Still clocked in"], "rows": rows}
    return xlsx_response([sheet], f"Re_entries_{data['from']}_to_{data['to']}")


@bp.get("/attendance/export/regularization-requests")
@jwt_required()
def export_regularization_requests():
    claims = get_jwt()
    status = request.args.get("status", "all")
    query = att._scoped_regularization_query(claims, int(get_jwt_identity()), None if status == "all" else status)
    if query is None:
        return jsonify({"message": "You do not have permission to export regularization requests."}), 403
    rows = [[
        r.work_date, r.user.employee_code, r.user.full_name,
        (r.regularization_status or "").title(), r.reason.label if r.reason else "", r.regularization_note or "",
        fmt_datetime(r.regularization_requested_at), r.reviewed_by_user.full_name if r.reviewed_by_user else "",
        fmt_datetime(r.regularization_reviewed_at), r.regularization_review_comment or "",
    ] for r in query.order_by(Attendance.regularization_requested_at.desc()).all()]
    sheet = {"name": "Regularization", "note": f"Regularization requests ({status})",
             "headers": ["Date", "Employee code", "Employee", "Status", "Reason", "Employee note", "Requested at",
                         "Reviewed by", "Reviewed at", "Review comment"], "rows": rows}
    return xlsx_response([sheet], f"Regularization_Requests_{status}")


@bp.get("/attendance/export/holidays")
@jwt_required()
def export_holidays():
    try:
        year = int(request.args.get("year") or date.today().year)
    except ValueError:
        return jsonify({"message": "year must be a number."}), 400
    rows = [[h.holiday_date, _day_name(h.holiday_date), h.name, h.description or ""] for h in
            Holiday.query.filter(Holiday.holiday_date >= date(year, 1, 1), Holiday.holiday_date <= date(year, 12, 31))
            .order_by(Holiday.holiday_date.asc()).all()]
    return xlsx_response([{"name": f"Holidays {year}", "headers": ["Date", "Day", "Holiday", "Note"], "rows": rows}], f"Holidays_{year}")


@bp.get("/attendance/export/regularization-reasons")
@jwt_required()
def export_reasons():
    if get_jwt().get("role") not in att.APPROVER_ROLES:
        return jsonify({"message": "Only a manager or HR Operations can export the rules."}), 403
    rows = [[r.label, r.description or "", "Active" if r.is_active else "Retired"]
            for r in AttendanceRegularizationReason.query.order_by(AttendanceRegularizationReason.label.asc()).all()]
    return xlsx_response([{"name": "Reasons", "headers": ["Reason", "Description", "Status"], "rows": rows}], "Regularization_Reasons")


# ---------------------------------------------------------------------------------------
# Generic: export any table the user is looking at
# ---------------------------------------------------------------------------------------

@bp.post("/export/table")
@jwt_required()
def export_table():
    """Turns the table currently on screen into an .xlsx. It only formats what the browser
    sends (which the person could already see) — it never reads any data itself."""
    payload = request.get_json(silent=True) or {}
    headers, rows = payload.get("headers"), payload.get("rows")
    if not isinstance(headers, list) or not isinstance(rows, list) or not headers:
        return jsonify({"message": "headers and rows are required."}), 400
    if len(headers) > MAX_TABLE_COLS or len(rows) > MAX_TABLE_ROWS:
        return jsonify({"message": "That table is too large to export in one file."}), 400
    clean_rows = []
    for row in rows:
        if not isinstance(row, list):
            return jsonify({"message": "Each row must be a list."}), 400
        clean_rows.append((row + [""] * len(headers))[:len(headers)])
    name = str(payload.get("sheet") or payload.get("filename") or "Export")[:31]
    return xlsx_response([{"name": name, "headers": [str(h) for h in headers], "rows": clean_rows,
                           "note": f"{payload.get('title') or name} — exported {datetime.utcnow().strftime('%d-%b-%Y')}"}],
                         str(payload.get("filename") or "Export"))
