# AnametaIOT HRMS
**Powered by +veGroww**

A production-structured HRMS built for 7 roles: **Manager, Contract Employee, HR Operations,
Finance & Accounts, Operations, HR Recruiter, Employee**.

Every person in the system is fundamentally an employee — HR Operations, Recruiters, and
Managers are all employees too, just with additional capabilities layered on their base
employee record. Every user has a Manager (except the top of the org chart), and a **Manager
can onboard people directly onto their own team** — creating their profile and assigning
their role — without needing HR Operations to do it for them. HR Operations can still onboard
and manage anyone, anywhere in the org.

Stack: **Flask (REST API) + React (Vite) + MySQL**.

> Note on Contract Employees: their scope is intentionally narrow — they manage their own
> **Documents** and check their **Payroll**, that's it. No attendance, no leave, no recruitment
> access. This is enforced both in the UI (nav only shows Documents/Payroll/Profile) and
> server-side (`/api/leave/apply` returns 403 for this role).
>
> Every other role gets Clock In / Clock Out (enforced server-side on `/api/attendance/*`).

---

## 1. Database setup (MySQL — root / no password)

```bash
mysql -u root < backend/schema.sql
```

This creates the `anametaiot_hrms` database and every table (25 total, including the
recruiter/mock-test/screening tables below). The backend can also auto-create tables via
`python seed.py` if you'd rather skip this step — `schema.sql` is auto-generated from the
SQLAlchemy models via `python -c "from sqlalchemy.schema import CreateTable; ..."`, so it
always matches what `db.create_all()` produces.

For an existing database, run `mysql -u root anametaiot_hrms < backend/migration_attendance_regularization.sql`
to add the regularization request history table and backfill this month's existing submissions.
Also run `mysql -u root anametaiot_hrms < backend/migration_attendance_work_rules.sql` to add the
configurable check-in buffer (defaults to 10 minutes) and manager edit-time audit details.

Attendance uses the company timezone configured by `COMPANY_TIMEZONE` (default `Asia/Kolkata`).
Existing attendance `DATETIME` values are stored as naive UTC; the application converts them
for company-local attendance dates, arrival rules, screens, and exports. No data migration is
needed for timezone support.

## 2. Backend (Flask API)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # already defaults to root / no password / localhost
python seed.py                    # creates tables (if not already) + 1 demo user per role
python run.py                     # runs on http://localhost:5000
```

`seed.py` also loads a ready-to-use **100-question Java mock test template** (see
`seed_data/java_questions.py`) owned by the demo Recruiter, so the Mock Tests tab has real
content immediately instead of an empty question list — split it into more templates or add
more topics anytime from the UI.

**Demo logins** (password for all: `Welcome@123`). In the seed data, **everyone reports to
the Manager** — sign in as Manager to see the whole team and try onboarding, or as any other
role to see their own scope:

| Role | Email |
|---|---|
| Manager | manager@anametaiot.com |
| Contract Employee | contract@anametaiot.com |
| HR Operations | hrops@anametaiot.com |
| Finance & Accounts | finance@anametaiot.com |
| Operations | operations@anametaiot.com |
| HR Recruiter | recruiter@anametaiot.com |
| Employee | employee@anametaiot.com |

### Optional integrations (recruitment features work fully without these)

Set these in `backend/.env` to unlock real external behavior instead of the built-in
fallback. Nothing breaks or needs code changes if you leave them blank:

| Variable | Unlocks | Without it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Real AI grading of mock-test subjective answers + real screening-call summarization/classification | Falls back to a labeled heuristic grader/classifier |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | Real AI voice-bot screening calls | Calls are simulated (clearly labeled `[SIMULATED]` in the transcript) so the Yes/No/Neutral flow, reschedule loop, and call history all still work end to end |
| `LINKEDIN_API_TOKEN` | Real one-click LinkedIn job posting | Endpoint responds with a clear "not configured" status — requires a LinkedIn Talent Solutions partnership, which is a business step outside this codebase |
| `NAUKRI_API_TOKEN` | Real one-click Naukri job posting | Same — requires a Naukri RMS corporate account |

## 3. Frontend (React)

```bash
cd frontend
cp .env.example .env
npm install
npm run dev                       # runs on http://localhost:5173, proxies /api to :5000
```

Open `http://localhost:5173` and sign in with any demo login above.

Candidates take mock tests at a public, no-login link: `http://localhost:5173/test/<token>`
(the token comes from the assignment created in the Mock Tests tab).

## 4. Production build

```bash
cd frontend && npm run build      # outputs static build to frontend/dist
cd backend  && gunicorn -w 4 -b 0.0.0.0:5000 run:app
```

Serve `frontend/dist` behind Nginx (or any static host) pointing `/api` **and `/static`** at
the Gunicorn backend — uploaded resumes, employee documents, and generated job-post images
are served from `/static/uploads/...`, so it needs the same reverse-proxy rule as `/api` or
those links will 404 against the frontend host instead of reaching Flask.

## 5. Running the backend test suite

```bash
cd backend
python tests/test_recruiter_features.py
```

An end-to-end smoke test (in-memory SQLite) covering job approval, candidate sourcing,
duplicate detection, verification + self-verify rights + re-validation timing, screening
calls, mock tests (assign/take/grade/rank/retest), panel interviews, offers, hire→employee
conversion, and recruiter performance reporting — with explicit RBAC checks (asserting the
right roles get 403'd, not just that the right roles succeed).

---

## What's included

**Backend** (`backend/`)
- JWT auth with role claims + `roles_required()` RBAC decorator on every sensitive route
- **Attendance** — clock in/out (blocked server-side for Contract Employee), daily/monthly
  history, team view for Manager/HR Operations/Operations, regularization approval and a
  maximum of five regularization requests per employee per month
- **Leave** — apply from today or a future date on the attendance calendar (or Leave page),
  track pending requests, and let Managers review their direct reports' requests from Profile;
  approval automatically deducts the balance
- **Employees** — directory, search; HR Operations can onboard/edit anyone, a **Manager can
  onboard and edit their own direct reports** (their `manager_id` is forced server-side —
  a Manager can never create or edit someone outside their own team)
- **Documents** — every employee has their own document locker (academic documents,
  experience documents, relieving letter). Visible to the owner, their Manager, and HR
  Operations. Contract Employees' entire scope is this plus Payroll.
- **Payroll** — configurable salary structure per employee, one-click monthly payslip
  generation (computes loss-of-pay from attendance + approved leave), mark-as-paid, and a
  **professional, printable payslip view** (letterhead, itemized earnings/deductions, Print
  / Save as PDF via the browser) for every employee's own payslip history
- **Recruitment** — the full pipeline: Applied → Auto-Validated → Verified → Screening Call →
  Mock Test → Interview → Offer → Hired/Rejected. See the dedicated section below.
- **Vendor Management** — under Finance & Accounts (with Manager approval oversight, and
  HR Operations having full org-wide control). See the dedicated section below.
- **Announcements** and **Assets** (laptops, ID cards, SIMs) for HR Operations / Operations
- **Dashboard** — role-tailored summary stats (`/api/dashboard/summary`) plus a dedicated
  Recruiter Performance endpoint (`/api/dashboard/recruiter-performance/<id>`) for Manager/Admin

**Frontend** (`frontend/`)
- Role-aware sidebar navigation (`src/config/roles.js` controls what each role sees) — Manager
  now also has Recruitment access (job approval, verification, feed, performance)
- Every page reflects the RBAC rules the backend enforces — e.g. Contract Employee never sees
  a clock in/out control; only HR Operations sees "Add Employee"
- Brand theme sampled from the actual AnametaIOT logo — navy/blue sidebar, orange primary
  actions, green success states (`src/styles/theme.css`)
- Built and verified with `npm run build` — no errors
- Public, unauthenticated mock-test-taking page at `/test/:token`

### Recruitment in depth

Everything below is implemented server-side with full RBAC, an audit trail, and passing
tests — not a mockup. This is the same feature set documented in `Recruiter-Specifications.pdf`.

- **Job requisitions** — draft → Manager/Admin approval → open; clone an existing posting;
  auto-generate a branded, shareable job-post image (real Pillow rendering, no template
  assets required); one-click post to LinkedIn/Naukri (wired end-to-end, needs real API
  credentials — see the table above)
- **Candidate sourcing** — single add with resume upload, or bulk import via Excel with a
  preview-then-confirm step (nothing is created silently); company-wide duplicate detection
  by normalized email/phone, with an explicit "link as new application" choice rather than
  a silent block or silent merge. Candidates carry a **skills** tag list, shown as chips in
  the list view alongside one-tap **Call / Message / Email** quick actions.
- **Two-tier verification** — automatic format/duplicate/external-cross-check validation on
  every new candidate, plus manual verification restricted to Admin, the recruiter's own
  Manager, or the recruiter themself *only if their Manager has granted self-verify rights*
  (`POST /api/recruitment/recruiters/<id>/self-verify`, Manager-only, own reports only)
- **Periodic re-validation** — each recruiter has a Manager-configurable re-validation
  interval (`revalidation_interval_days` on their user record); the verify action is
  server-side locked until that interval elapses, then reopens automatically
- **AI screening calls** — Twilio-based voice-bot calling with Yes/No/Neutral outcome
  classification (real via Anthropic if configured, heuristic fallback otherwise); a
  Neutral (or manually chosen) outcome reschedules for another attempt
- **Mock tests** — recruiter builds a template (topics, complexity, duration, passing
  threshold, MCQ + subjective questions), assigns it to verified candidates via a public
  no-login access-token link, answers are auto-graded (MCQ directly, subjective via AI/
  heuristic), rankings are computed per mock test (not per job, not global), and retesting
  is recruiter-assigned only
- **Interviews** — panel interviews (multiple interviewers per round), conflict checking
  against each interviewer's existing schedule, reschedule/cancel with a required reason
- **Offers** — draft → submit for approval → Manager/Admin approve/reject → send →
  candidate accepts/declines, feeding the candidate's stage automatically
- **Hire → Employee handoff** — one action pre-fills a new Employee record from the
  candidate + accepted offer; prevents converting the same candidate twice
- **Recruiter performance** — Manager/Admin-only view combining audit-trail-derived metrics
  (candidates added, interviews scheduled, conversion rate) with the recruiter's *existing*
  attendance data — no separate login-tracking system was built, by design

### Vendor Management in depth

Recruitment vendors (staffing agencies who supply manpower for a service fee) — real PDF
parsing, real invoice generation, tested against actual sample agreements and invoices.

- **Agreement upload & parsing** — upload a signed agreement PDF; the vendor's identity,
  effective dates, notice/confidentiality/feedback terms, and the **entire role-wise fee
  table** (role name, service fee %, replacement window, billable-after-tenure days) are
  read automatically. The fee table is parsed deterministically from the PDF's actual table
  structure (not guessed by AI) — these are money numbers, so a hallucinated percentage
  would be a real financial risk. Free-text fields fall back to AI assistance only when the
  regex genuinely can't find them, and every field is shown for review/edit before anything
  is saved — nothing is ever auto-committed from a parse.
- **Vendor matching** — if the agreement's vendor matches an existing one (by name), it's
  added as a new agreement on that vendor's record (supports renewals over time). If it's
  new, a **New Vendor** form appears pre-filled from the parsed data, with an explicit
  Add button — never silently created.
- **Hiring & rate cards** — a hired person is assigned to a vendor's specific rate-card role
  (e.g. "Telesales Executive — 7.55%"), starting a tenure clock. **Payroll starts
  automatically** — a starter salary structure is created from the CTC the moment someone is
  assigned, so Finance doesn't have to remember a manual first step (they can still refine
  the Basic/HRA/etc. breakdown afterward from the Payroll page).
- **Billing** — once a hire's tenure period completes (per the agreement's terms, e.g. 60
  days), it becomes billable. Generating an invoice computes each billable hire's fee
  (CTC × fee%), applies CGST+SGST (same state) or IGST (different state) based on the
  vendor's and company's configured state, and produces a **real PDF** (pure-Python via
  reportlab — no external binary needed) matching a professional tax invoice layout:
  letterhead, particulars table, GST breakdown, amount in words (proper Indian lakh/crore
  number-to-words), bank details, and declaration.
- **Approval workflow** — Draft → Pending Approval → Approved → Paid, mirroring the same
  pattern as job requisition and offer approval elsewhere in the app. Finance generates and
  submits; **Manager or Admin approves** (Finance cannot approve its own invoice); Finance
  marks paid once settled. A rejected invoice frees its hires back up to be re-billed.
- **Replacement handling** — if a vendor-supplied hire needs replacing within the
  agreement's replacement window, one action marks the original as replaced and creates
  the replacement under the same vendor/role, preserving the billing history.
- **Company Settings** — AnametaIOT's own details (name, address, GSTIN, PAN, state) used
  as the "Buyer" block on every generated invoice — editable by HR Operations.

### Payroll, extended

- **Salary Templates** — Finance defines a reusable earnings/deductions split once (e.g.
  "Standard Employee": 50% Basic / 20% HRA / 20% Special / 10% Other, 6% PF, ₹200 PT) and
  applies it to any employee's CTC instead of typing flat numbers every time. Applying a
  template computes each component from the CTC and writes it straight into that
  employee's salary structure.
- **Real, downloadable payslip PDFs** — every payslip generated by the monthly payroll run
  now gets an actual PDF file (pure-Python via reportlab, same visual style as the vendor
  invoices) with a direct download link, in addition to the existing in-app
  print-friendly view.

### The recruiting-for-vendors model

This is the core business model the recruitment and vendor modules are actually built
around: AnametaIOT's own recruiters source candidates both for AnametaIOT itself **and**
for client companies (vendors) — recruiting-as-a-service, the same relationship shown in
this project's original sample agreements/invoices. Two things had to stay cleanly
separated for this to work, and both are now enforced at the data model level, not just
in the UI:

- **Internal Hiring vs. Client Requisition** — every job posting now has a
  `requisition_type`. "Internal" is AnametaIOT's own hiring, completely unchanged from
  before. "Client" requires picking which vendor the requisition is for, and every
  candidate sourced against it is tagged accordingly — filterable everywhere (Jobs, All
  Candidates, exports) so the two pipelines are never visually or functionally mixed.
- **Direct vs. Contract placement** — once someone is placed with a vendor
  (`vendors/hires`), the placement is one of two types:
  - **Direct** — they join the vendor's own payroll entirely. No AnametaIOT account is
    ever created for them; they will never appear in the Employees directory.
  - **Contract** — still placed with (and working for) the vendor, but a narrow internal
    login is created (role: **Contract Employee**, which already existed for exactly this
    scope) purely so they can access their Documents and Payroll inside this tool. This
    does not make them an AnametaIOT employee in any other sense.
- **Billing follows the placement type** — a **one-time** fee (the original tenure-gated
  flow, unchanged) for direct hires, or a **continuous monthly** fee for contract
  placements, computed as CTC/12 × the rate-card fee %, generated via a separate
  "Generate Monthly Invoice" action and guarded against ever double-billing the same
  month twice.
- **All Placements** — a dedicated, vendor-agnostic list of everyone ever placed with any
  vendor (`/all-placements`), completely separate from both the internal Employees
  directory and the Candidates recruiting pipeline. Same search/filter/sort/CSV pattern
  as All Candidates.
- **Downloads** — CSV export is now available on All Candidates, per-job Candidates, and
  All Placements. These go through an authenticated blob download (`utils/download.js`)
  rather than a plain link, since the JWT lives in `localStorage`, not a cookie — a plain
  `<a href>` to a protected endpoint would silently fail.

### Vendor onboarding, refined

- **Vendor-first upload flow** — after an agreement is parsed, a vendor **dropdown** is
  always shown first (pre-selected to any auto-matched vendor), with "+ Add New Vendor" as
  an explicit option — only once a vendor is chosen do the agreement terms and rate card
  appear for review.
- **Add Vendor directly** — a vendor can now be created with full basic + billing
  information (`POST /api/vendors`) independent of any agreement, for when the
  relationship starts before a contract is signed.

### Manager-facing employee management

- Clicking an employee in the **Employees** directory now opens a detail view with their
  **performance snapshot** (attendance, leave usage, and recruiting stats if they're a
  recruiter), **editable info** (name, phone, designation, role), and **roles &
  permissions** — scoped to a Manager's own direct reports, or anyone for HR Operations.
- **Permissions system** — a Manager can extend specific approval capabilities (approving
  candidates/offers, job postings, or vendor invoices) to an individual employee without
  changing their base role — e.g. letting a trusted senior team member approve offers
  without making them a Manager. This is additive: every existing role-based approval path
  still works exactly as before; a granted permission only adds access, never removes it.
  See `PERMISSION_CATALOGUE` in `app/models/permission.py` to add more grantable
  permissions the same way.

## Extending this

- Payroll currently covers PF/ESI/PT/TDS as flat configurable amounts per employee. Slab-based
  statutory calculation (e.g. auto PF at 12% of Basic capped at ₹15,000) can be added in
  `backend/app/routes/payroll.py`.
- LMS/training and formal exit-management workflows aren't included yet — the `Asset` and
  `Candidate` models are the closest analogues and can be extended the same way.
- Mock test proctoring (tab-switch detection, webcam monitoring) was deliberately left out —
  see `Recruiter-Specifications.pdf` Section 11 for why, and add it behind the existing
  `MockTestAssignment` model if it becomes necessary.
- Employee referral bonus payout isn't wired into Payroll yet — `Candidate.referral_bonus_status`
  is tracked but there's no automated payout step; Finance & Accounts would action it manually
  for now.
- Vendor agreement parsing is built for the "Agreement for Permanent Recruitment" template
  format (party names, effective date range, and a Details/Role/Role fee table). A
  differently-structured agreement will still be readable and editable in the upload
  preview, but may need more manual correction — the parser degrades gracefully rather than
  failing, since every field is reviewed before saving regardless.
- Vendor invoices currently only send PDF generation — there's no automated emailing of the
  invoice to the vendor or reminder system for upcoming agreement expiry beyond the
  dashboard's "Agreements Expiring Soon" panel. Both would be natural next additions using
  the same optional-integration pattern as the AI screening calls.
