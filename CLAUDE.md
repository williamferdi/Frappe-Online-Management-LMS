# SIBBCS ERP — `sibbcs` app

University ERP for South India Baptist Bible College & Seminary (Online), Coimbatore.
Built on Frappe Framework v15 + Frappe LMS. Scale: 200 students → 1,000 in 2 years.

Full spec: `SIBBCS_ERP_Architecture.md`. This file is the always-in-context summary —
read it before touching anything, and keep it current as phases land.

---

## 1. Stack decision

| Layer | Choice | Why |
|---|---|---|
| Platform | **Frappe Framework v15** | Owns DocTypes, workflows, roles, web forms, portal |
| Learning delivery | **Frappe LMS** | Courses, lessons, quizzes, assignments, batches, live class links, certificates |
| Custom app | **`sibbcs`** | Admissions, enrollment, registration, fees, grading, formation, degree audit |
| Payments | **Razorpay** (via `payments` app) | Native Frappe integration exists |
| Accounting | ERPNext — **deferred to Phase 8, optional** | Only for GST invoices / P&L. Not needed for "who paid what" |

### Do NOT install the Frappe Education app

It hard-codes `Academic Year → Academic Term → Student Group` on a semester assumption,
and its fee module cannot express our structure (paused monthly tuition +
per-registration fee + flexible scholarship). Building ~25 clean DocTypes we control is
cheaper than patching someone else's model.

### The three-layer academic model — the core insight

Keep these strictly separate:

```
Course              = catalog entry. Immutable. "BIST O502 Intro to OT, 3 Cr, Level 1"
Course Offering     = a run of that course. "BIST O502, Term 2026-T4, Zoom Live, Rev. X"
Course Registration = one student in one offering. Carries fee, grade, LMS enrollment.
```

A student's **transcript is their set of completed Course Registrations**. Their **level
is a stored field** on Program Enrollment that only the Registrar / Academic Coordinator
changes. The two are deliberately decoupled — that is exactly what makes "a Level 1
student sits in a Level 2 course but stays Level 1" work with zero special-case code.

---

## 2. DocType map

Modules: `Academic` (Phase 1, built), plus `Admissions`, `Formation`, `Finance`,
`SIBBCS ERP` (misc) to come.

### 2.1 Admissions — Phase 2, BUILT
- **`Lead`** — `LEAD-.YYYY.-.#####`; source, program_interest, status, owner_officer
- **`Admission Application`** — `APP-.YYYY.-.#####`; applicant / ministry / program
  sections, `age` derived from `dob`, gate fields, `workflow_state`
  - child **`Application Document`** — `document_type`, `file`, `verified`, `verified_by`
  - child **`Reference Request`** — referee, `token`, `sent_on`, `submitted_on`,
    `response_json`, `recommendation`
  - child **`Mentor Consent`** — mentor details, `token`, `consented_on`, `consent_file`
- **`Scholarship Request`** — `SCH-.YYYY.-.#####`; approval writes `monthly_discount` +
  `approved_amount` (the cap) onto Program Enrollment
- **`Qualifying Exam Result`** — `QER-.YYYY.-.#####`; `total` is the mean of the four
  sections, `result` vs `pass_mark` (60), mirrored onto the application
- **`Interview Record`** — `INT-.YYYY.-.#####`; `panel` multiselect, `outcome` mirrored
  onto the application

### 2.2 Academic — Phase 1, BUILT
- **`Program`** — `program_name`, `abbr` (docname), `total_credits`, `total_courses`,
  `min_years`, `max_years`, `internship_hours`, `requires_ata_fee`, `is_active`
  - child **`Program Requirement`** — `rule_type` (Level Credits / Elective Minimum /
    Practicum / Residential / Internship Hours), `level`, `min_credits`, `min_courses`,
    `min_hours`
- **`Course`** — `course_code` (docname), `course_title`, `credits`, `level` (1–4),
  `course_type`, `department` (BIST/THST/CHMI/HIST/REMI/GEST), `default_format`,
  `programs`, `lms_course` → LMS Course, `is_active`
  - child **`Course Prerequisite`** — `prerequisite_course`, `is_hard`
  - child **`Course Program Link`** — `program`
- **`Academic Term`** — `term_name` (docname, e.g. `2026-T4`), `term_code`, `start_date`,
  `end_date`, `application_deadline`, `registration_opens`, `registration_closes`,
  `duration_months` (default 2), `status` (Planned/Open/Active/Closed)
- **`Course Offering`** — docname `{course}-{term}`; `course`, `term`, `format`,
  `instructor`, `facilitator`, `zoom_days`, `zoom_time`, `capacity`, `enrolled_count`,
  `lms_batch` → LMS Batch, `status` (Draft/Published/Running/Completed)
  - child **`Course Offering Weekday`** — `weekday` → Weekday
- **`Instructor`** — `INS-.#####`; `full_name`, `user`, `email`, `mobile`,
  `qualification`, `courses_qualified`, `is_facilitator`, `is_active`
  - child **`Instructor Course`** — `course`
- **`Grade Scale`** — `scale_name`, `is_default`, `pass_percentage` (60)
  - child **`Grade Scale Row`** — `grade`, `min_pct`, `max_pct`, `grade_points`, `is_pass`
- **`Weekday`** — lookup, seeded Monday–Sunday

Built in Phase 2 because the conversion point produces them:
- **`Student`** — `SIB-.YYYY.-.####`; `user` is the single login for portal *and* LMS
- **`Program Enrollment`** — docname `{student}-{program}`; `current_level` sits at
  **permlevel 1**, writable only by Registrar / Academic Coordinator;
  `scholarship_total_cap` + `scholarship_used_to_date` are what stop a flexible discount
  running forever (`discount_for_months()` clips to the remaining headroom)

Built in Phase 3:
- **`Course Registration`** — docname `{program_enrollment}-{course_offering}`; carries
  `level_at_registration` (audit), `override_reason`/`override_by`,
  `lms_enrollment_created`, and the grade fields at **permlevel 1** (Faculty and above
  may write a grade; Students and Facilitators read only)
  - child **`Grade Component`** — `component`, `weight_pct`, `max_marks`,
    `obtained_marks`, `weighted_score`
- **`Level Promotion`** — `LPR-.YYYY.-.#####`; the audit trail for a level change.
  `current_level` is never edited silently — it moves through this document, which
  records the approver and the credit evidence.

### The eligibility rule engine — `sibbcs/academic/eligibility.py`

Pure functions returning a `Decision`, so each rule is testable alone and the portal can
grey out offerings *before* anyone clicks Register. §3 exactly:

| | student L vs course C | outcome |
|---|---|---|
| 1 | `C == L` | allow |
| 2 | `{L,C} ⊆ {1,2}` | allow — levels 1 and 2 interchangeable |
| 3 | `{L,C} ⊆ {3,4}` | **hard block** — no override clears it |
| 4 | anything else | block unless an Academic Coordinator override |

**Confirmed:** a Level 2 student may **not** take a Level 3 course — it lands in rule 4,
blocked, override required. `Decision.hard` marks rules an override cannot clear;
`needs_override` marks ones it can, so the UI offers the escape hatch instead of a dead
end. A student can never grant themselves an override: `portal.register` takes no
override argument, and `validate_override_authority` re-checks the acting user's roles.

Further gates: hard prerequisites, duplicate-pass (hard — this is what stops a Level 1
student re-taking a Level 2 course after promotion), in-progress duplicate, offering
status/capacity, closed term, inactive enrollment. **Fees warn by default**, matching the
practice of chasing rather than locking out; `block_registration_on_overdue` flips it to a
hard gate with no code change.

**Level 4 gate**: `Level Promotion` refuses `to_level = 4` until every Level 3 course for
the program is completed and passed.

### LMS sync — `sibbcs/academic/lms_sync.py`

`Course Registration → Registered` ensures an LMS Course, ensures/creates an LMS Batch for
the offering, and enrolls `student.user`. **Two records are needed, not one**: `LMS Batch
Enrollment` grants batch membership, but `LMS Enrollment` is what actually opens the
course — batch membership alone leaves the student staring at an empty dashboard. Sync
never raises into the registration: a misconfigured LMS must not undo a registration the
registrar accepted. An hourly `sync_pending` sweep retries anything left behind.

### The conversion point — `sibbcs/admissions/conversion.py`

`convert(application)` does the six things in architecture doc §4 in one transaction.
Steps that depend on later phases (Mentor → Phase 6, Fee Invoice → Phase 4, Course
Registration → Phase 3) are attempted only if their DocType exists and are otherwise
listed in the returned report under `deferred` — **never silently skipped**. The same
function completes itself as those phases land. It is idempotent: a second call returns
`already_converted` rather than making a second Student.

Enrollment always starts at `current_level = 1`; the application's `entry_level` is
advisory only.

### Admission workflow — `setup/phase2_workflow.py`

15 states, 32 transitions, `Draft → … → Orientation Registered`, with `Reject` and
`Withdraw` reachable from every mid-flight state. Gates are enforced as transition
`condition` expressions (`doc.docs_verified`, `doc.qualifying_exam_score >= 60`,
`doc.admission_fee_paid`, `doc.student`) so they do not depend on an officer remembering.

### Token forms — `sibbcs/admissions/tokens.py`

One controller for every no-login form; registering a new one is a single entry in
`TOKEN_TARGETS`. Tokens are `secrets.token_urlsafe(32)`, single-use, and scoped to one
child row of one parent — a reference token is rejected by the mentor form. Pages live at
`/reference` and `/mentor-consent`; submissions go to the guest endpoint
`sibbcs.admissions.tokens.submit`, which writes only fields present in the row's own meta,
so a crafted payload cannot reach `parent`, `token`, or another document.

### LMS Account Creation — `sibbcs/admissions/lms_account.py`

Creates the applicant's login and sends the entrance exam link. Step 8 (Entrance Exam
Review) is gated on it because the exam is sat inside the LMS.

- **One account, kept for life.** `conversion._create_user` adopts an existing User by
  email, so an admitted applicant keeps the login they sat the exam with.
- **No password is ever emailed** — the invite carries a `/update-password?key=` link.
  `User._reset_password` builds that URL with `get_url()`, which appends `:8000` here, so
  the key is kept and the address rebuilt through `gateway.public_url()`.
- The applicant gets **`LMS Student` only**; `Student` is granted at conversion.

Where the exam lives is config, not code — `entrance_exam_url` wins over
`entrance_exam_lms_course`; with the course set the applicant is also enrolled in it.
With **neither set the account is still created** and the step reports why nothing was
sent, rather than mailing a dead link. **Neither is set on `online.sibbc.org` yet.**

### The preliminary orientation course

Step 12 is delivered as an **LMS course**, not a PDF. `Reading Manual.delivery` is
`Document` or `LMS Course`; on the course path the candidate is enrolled, and
`/manual-reading` refuses their signature until **every lesson** is complete.

That distinction is the point: onboarding is gated on this step, and acknowledging a PDF
is one click — it records that somebody pressed a button, not that anybody read anything.
A course records a lesson at a time.

`setup/phase2j_preliminary_course.py` imports the college's two handbooks into
**`m-div-preliminary-orientation`** — 5 chapters, 49 lessons, both PDFs attached. It
reflows the PDF's hard line breaks back into paragraphs by line width, since extracted
text has one line per *visual* line and paragraph boundaries are gone.

**The Formation Handbook is only partly imported, on purpose.** Its Level 1-4 sections are
reflection and goal-setting forms filled at the start of each level *with a mentor*.
Importing them would have a new admit writing Level 4 goals before beginning Level 1,
guided by a mentor not assigned until Phase 6. Only the Welcome Note, "Before You Begin"
and the Formation Covenant are in. Sections 9-12 (FAQs, Your Mentor & You, Choosing a
Mentor, Suggested Practices) are not level-bound either and can be added to
`HANDBOOK_PARTS`.

`course_progress()` counts completed lessons against lessons that exist rather than
reading `LMS Enrollment.progress`, which is a rounded figure the LMS maintains and can
read 100 with a lesson skipped.

### Manual Reading and Onboarding — `sibbcs/admissions/manuals.py`, `conversion.onboard`

**Step 12, reading manuals.** A candidate who has passed the entrance exam is emailed a
token link per applicable manual (`/manual-reading?token=`). They read it, type their
name, tick a box. `Manual Acknowledgement.acknowledged_name` is **what they typed**, not
what the office believes their name to be — if those differ, that difference is the
evidence, and overwriting it would destroy the only thing the record is for. The step
reaches `Acknowledged` only when **every** applicable manual is in.

A `Reading Manual` with no programs listed is universal; one with programs listed applies
to those only. Attachments are private files, so the candidate fetches them through
`tokens.download_manual` (resolved with `allow_used`) rather than a `/files/` link a
guest cannot open.

**The gate.** `REQUIRES[NO["manual_reading"]]` is `(NO["decision"], "Admitted")`: manuals go out after the admission
decision, so nobody is asked to read a handbook for a place they may not be offered. This
was briefly changed to gate on the exam pass instead and the college corrected it. Step 13
requires `(11, "Admitted")` **and** `(12, None)`.

**Step 13, onboarding.** `conversion.onboard()` checks the step-13 gate *before* creating
anything — a Student created and then found to be ungated is unpicked by hand. The
enrollment is made at `onboard_level` (falling back to Level 1) in `onboard_term` or the
intake term. A **waived** admission fee counts as settled: a waiver is a decision recorded
at step 10, not a payment, so `admission_fee_paid` stays false and a fee-paid-only check
would block every waived candidate.

### Step order — a position, not an identity

`step_no` is **where a step sits**, not what it is. The college has reordered once already
(the scholarship form moved from second to after the interview, because the interview is
where they learn whether a candidate needs one) and will again. So:

- Each entry in `STEPS` carries a **stable key** as its last element, and `NO["scholarship"]`
  is how every other module addresses it. `REQUIRES` and `ACTIONS` are keyed through `NO`
  too. **Nothing outside `checklist.py` may hardcode a step number** — tests included.
- Existing rows are remapped by their stored **label**, never by their old number, in
  `patches/renumber_checklist_steps.py`. An unrecognised label is reported and skipped
  rather than guessed at: a wrong guess silently rewrites somebody's admission record.
- `test_step_order.py` pins the invariants — contiguous 1..n, unique keys and labels,
  defaults inside their own status list, and **no gate pointing at a later step** (which
  could never be satisfied).

**Deploy order matters.** Upload the code and run `bench migrate` together. In between,
the running code believes the new numbering while the rows still hold the old one, so any
save writes a status onto the wrong step. Nothing was saved during the window this time —
an audit of all eight live applications confirmed it — but the window is real.

### The checklist board — `checklist.board()` + the form script

The 13 steps render as one row each at the top of the application: number, status
tick/lock/circle, step name with its owner role, a status select, who last moved it and
when, and — for the six steps that have something to *do* — the action button for that
step sitting next to it. A progress bar counts completed steps.

`ACTIONS` in `checklist.py` maps step → form-script trigger, so the toolbar and the board
cannot drift: adding an action is one entry there plus the handler.

Two things the board deliberately does:

- A blocked step still offers its **intermediate** statuses and greys out only the ones
  that would complete it — an exam can be Scheduled before step 7 is done, not Passed.
  The select is a convenience; `update_step` re-checks every gate server-side.
- A **new application already reads 1/13**, because Scholarship Form Review defaults to
  Not Applicable, which is a done status. Most candidates never ask for one, so the
  default is the finished state rather than a task nobody will do.

The raw child grid still exists, in a collapsed `Checklist Rows` section below the board:
it is where remarks and the audit stamps are stored. The old `Admission Gates` dashboard
summary was removed — the board says the same thing better.

### Scholarship Form Review — `sibbcs/admissions/scholarship.py`

It sits **after the Zoom interview and before the admission fee**: the interview is where
the college learns whether a candidate needs a scholarship at all.

The college's own scholarship form, rebuilt from their Zoho original: student name and
email (prefilled, read-only), a financial-need statement capped at **250 words**, and a
drawn signature. Public at `/scholarship?token=`.

**It does not use `tokens.py`.** That controller resolves a token to one *child row* of a
parent; a `Scholarship Request` is a standalone document referenced by
`Admission Application.scholarship_request`, so there is no row to point at. The token
lives on the application beside `upload_token` and is resolved in `scholarship.resolve`.
One application, one form — the token is spent the moment a request exists.

**Caps live on `Program.scholarship_max`**, seeded from the college's form: M.Div 24,000,
M.A.C.S. 16,000, GDCS 8,000 — 8,000 a year over three, two and one year. `decide()`
refuses an award above the cap. **BTH-TAM has no cap declared** and is therefore
unchecked; set one when the college states it. The seeder never overwrites a figure edited
in Desk.

The signature arrives as a canvas data URL, so the bytes are ours to check rather than a
file the candidate chose: PNG magic bytes, 512 KB ceiling, stored private. It is validated
**before** the request is created, so a refused signature cannot leave an empty
`Scholarship Request` behind.

Approval is `scholarship.decide`, never a hand-edited `status`: it stamps the approver,
checks the cap, and moves step 5. `conversion._apply_scholarship` then copies
`approved_amount` and `monthly_discount` onto the Program Enrollment, which is what makes
the cap real — the Phase 4 tuition job stops discounting once `scholarship_used_to_date`
reaches it.

Step 5 gained **`Form Sent`**, for the same reason step 9 gained `Invite Sent`: the
default is `Not Applicable`, which counts as done because most candidates never ask. Once
the form goes out the step is genuinely outstanding again.

### Zoom Interview Review — `sibbcs/admissions/interview.py`

Zoom interviews are booked through **Calendly on the free plan**, so this is deliberately
one-way: the button emails the candidate a booking link and step 9 moves to **`Invite
Sent`** — a new status between Awaiting and Scheduled, because a sent link is not a
booking and nobody here learns a slot was taken until an officer looks. Calendly webhooks
would close that loop but need a paid plan; the college has chosen not to buy one. The
module is shaped so adding them later is an addition, not a rewrite.

The link is not the bare event URL. It prefills `name` and `email`, and carries the
application number in `utm_content`, which is what lets an officer match a booking to an
application without guessing from the name — two candidates called Kumar is not
hypothetical. It is also stored on `interview_booking_url`, because a good few of these
conversations happen over WhatsApp.

**`event_url()` discards the configured URL's query string on purpose.** A Calendly link
copied out of a browser carries `?month=2026-08&date=2026-08-28`, which pins the widget to
one month and one day; emailed a month later it opens on a date that has already passed.

    bench --site online.sibbc.org set-config calendly_interview_url \
        "https://calendly.com/admissions-online-sibbc/30min"

### 2.3 Formation — Phase 6, not built
`Mentor`, `Mentor Monthly Report`, `Chapel Session` + `Chapel Attendance`,
`Internship Record` (+ `Internship Log Entry`), `Campus Visit` + `Campus Visit Attendance`.

### 2.4 Finance — Phase 4, BUILT
- **`Fee Type`** — `category` (One-Time / Per-Registration / Recurring Tuition),
  `default_amount`, `trigger_event`, `discountable`, `applies_to_programs` (empty = all)
- **`Fee Invoice`** — `FEE-.YYYY.-.#####`; gross / discount / net / paid / outstanding,
  `months_billed` (counts toward the ceiling), `razorpay_link`
- **`Payment Entry`** — `PAY-.YYYY.-.#####` + child **`Payment Allocation`**;
  tracks `unallocated_amount`, and `auto_allocate()` settles oldest invoices first
- **`Student Fee Ledger`** is a **Script Report, not a DocType** — invoices and payments
  are the records; the ledger is a view with a running balance

### The fee engine — `sibbcs/finance/fees.py`

Four streams, never merged into one invoice (a student can owe an application fee, a
registration fee and a tuition instalment at once, each with its own due date):

1. **One-time** — application, admission, ATA (M.Div only), graduation
2. **Per-registration** — ₹350 per Course Registration, **not discountable**; raised by a
   `doc_events` hook plus a daily sweep, and a billing failure never rolls back a
   registration the registrar accepted
3. **Recurring tuition** — the *paused* subscription: bills only in terms where the
   student registered at least one course
4. **Scholarship** — `monthly_discount` clipped to `scholarship_total_cap −
   scholarship_used_to_date`; spending it is what makes the cap real

**Tuition ceiling (decision #1, answered "cap at ₹54,000, pay-as-you-go").** The ceiling
lives on `Program.tuition_total`, not in code — clear it for uncapped billing. The final
invoice is *trimmed* so the advertised total is never overshot.

`Program.cap_on_gross` defaults to **1**, and this matters: §5 says "net tuition billed",
but measuring the ceiling against net means a student with a scholarship simply takes
longer to reach ₹54,000 and pays the same total — the discount would stretch the payment
period instead of reducing the bill, cancelling out Stream 4 entirely. Measured on gross,
the scholarship is a real saving. Flip the flag if the college wants the literal reading.

### Payment gateway — `sibbcs/finance/gateway.py`

Everything outside `finance/<provider>.py` talks to the gateway through this module.
Which provider is live is site config, not code:

```bash
bench --site online.sibbc.org set-config payment_provider razorpay
```

A provider module exposes `is_configured()`, `create_payment_link(invoice)` and
`PROVIDER_NAME`. **Webhooks stay provider-specific on purpose** — each gateway signs
differently, and signature verification is the one thing that must not be generalised
into a lowest common denominator. Adding a provider (Jodo is under evaluation) is one new
module plus one `PROVIDERS` entry; the schema, the public form and the fee engine do not
move.

The schema is vendor-neutral: `payment_link`, `payment_reference`, `gateway_payment_id`,
and a `payment_provider` column recording which gateway handled each row. Payment mode is
`Online`, not a brand.

**Use `gateway.public_url()`, never `frappe.utils.get_url()`, for anything a gateway or a
candidate's browser will see.** `get_url()` appends the dev webserver port unless the site
runs under supervisor/systemd, so on this bench-start deployment it produced
`online.sibbc.org:8000` — an address the outside world cannot reach. It had silently
poisoned both the webhook URL and the post-payment callback. `public_url()` builds from
`host_name` instead; a test asserts no `:8000` can come back.

### Razorpay — `sibbcs/finance/razorpay.py`

Payment *Links*, one per invoice, not a hosted checkout. Credentials live in site config,
never the repo:

```bash
bench --site online.sibbc.org set-config -g razorpay_key_id rzp_live_xxx
bench --site online.sibbc.org set-config -g razorpay_key_secret xxx
bench --site online.sibbc.org set-config -g razorpay_webhook_secret xxx
```

Webhook: `https://online.sibbc.org/api/method/sibbcs.finance.razorpay.webhook`

The webhook verifies Razorpay's HMAC-SHA256 signature over the **raw body** with
`hmac.compare_digest` *before parsing anything* — without it, anyone who found the URL
could mark invoices paid. It is idempotent on `razorpay_payment_id`, because Razorpay
retries. **Not yet configured** — no keys are set, so links cannot be generated.

### 2.5 Output — Phase 7, not built
`Degree Audit`, `Transcript` (print format), `Graduation Record`.

---

## 3. Deliberate deviations from the spec

Recorded so nobody "corrects" them back:

1. **`Course.programs`** (Table MultiSelect → `Course Program Link`) is an addition. The
   spec's Course had no program link, but Degree Audit must know which courses count
   toward which program, and one course can serve several. A course with **no** links is
   treated as universal (`Course.counts_toward`) so a partly-seeded catalog does not
   silently drop courses from audits.
2. **`Weekday` + `Course Offering Weekday`** exist only so `zoom_days` can be a real
   Table MultiSelect — Frappe multiselects need a Link target, not a Select.
3. **`Program Requirement.min_hours`** is an addition; the Internship Hours rule needs a
   target figure that `min_credits`/`min_courses` cannot express.

## 4. Frappe gotchas found the hard way

- **Normalise naming fields in `before_insert`, not `validate`.** `Document.insert()`
  calls `set_new_name()` *before* `validate()`, so upper-casing `abbr`/`course_code` in
  `validate` leaves a lower-cased docname. See `Program.before_insert`.
- **Time fields are never empty.** `insert()` → `_set_defaults()` → `new_doc`, and
  `frappe/model/create_new.py` sets *every* Time field to `nowtime()` unconditionally.
  "This Time field is required" can never be enforced by an emptiness check. Guarded by
  `test_time_fields_are_never_empty_on_insert`.
- **`Bench.reload()` always pokes supervisor.** `supervisor=True` is a default argument,
  so `restart_supervisor_on_update: false` does not stop it; when plain `supervisorctl`
  fails it retries with `sudo` and aborts the whole command. Fixed at the OS level by
  making the supervisor socket group-readable (see §6) rather than granting sudo.
- Definition cycles (`Course` ↔ `Course Prerequisite`, `Student` ↔ `Admission
  Application`, `Admission Application` ↔ `Scholarship Request`) need a two-pass build:
  create the parent, then the child, then extend the parent. See `setup/schema.add_fields`.
- **`User.mobile_no` carries a UNIQUE index.** Copying a student's mobile onto their User
  unconditionally makes the *second* student who shares a handset impossible to enroll —
  and shared phones are ordinary here (a married couple, a family phone, a church office
  number). `conversion._create_user` only claims a number nobody holds; `Student.mobile`
  stays authoritative. Guarded by `test_two_students_may_share_a_phone_number`.
- **Never `frappe.db.commit()` in library code.** Frappe commits automatically at the end
  of a successful request, so the commit buys nothing — but it also commits the
  surrounding transaction, which defeats `FrappeTestCase` rollback. An early version of
  `tokens.mark_submitted` did this and left 27 test applications on the live site.
- **`bench console` is not a script runner.** It reads piped stdin as separate IPython
  cells, and even `exec(open(...).read())` puts module-level names in *locals*, invisible
  to nested function scopes — so a script with helper functions raises `NameError`. Use
  `bench execute <dotted.path>` for anything real; keep console one-liners function-free.
- **`LMS Batch.validate_batch_time` rejects `start_time >= end_time`.** Deriving both ends
  of the class window from `Course Offering.zoom_time` produced a zero-length slot and
  broke every batch creation. `zoom_time` is the *start* only; `lms_sync` adds a two-hour
  default. (Compounded by the Time-field default above — the field is never empty, so this
  failed silently on every offering, not just scheduled ones.)
- **Batch membership is not course access.** `LMS Batch Enrollment` alone leaves a student
  with an empty dashboard; `LMS Enrollment` is the record that opens the course. Guarded
  by `test_student_is_enrolled_in_the_course_itself`.
- **Renaming a field on a standard DocType takes three steps, not one.**
  `frappe.rename_field` is not enough: the JSON on disk is the source of truth and the
  phase builders skip DocTypes that already exist, so the next `bench migrate` restores
  the old column. Change the fieldname on the DocType doc and save it. Then fix
  `search_fields` / `title_field` / `sort_field`, which reference fieldnames and fail
  validation with *"Search field X is not valid"*. DDL (dropping the orphaned column)
  must go through `frappe.db.sql_ddl`, not `frappe.db.sql`, which refuses it with
  `ImplicitCommitError`.
- **Deferred steps go live silently.** `conversion.py` skips steps whose DocType does not
  exist yet and reports them as `deferred`. The moment that phase lands, the branch runs
  *for the first time in production conditions* — the ATA path hand-built a Fee Invoice
  without the required `gross_amount` and broke every conversion test the day Phase 4
  arrived. **Deferred branches must delegate to the owning module's tested function**, not
  re-implement it. Re-run the full suite after each phase for exactly this reason.

## 4a. Testing

Run tests against **`test.local`**, never the production site:

```bash
bench --site test.local run-tests --app sibbcs
```

`bench setup production` has not been run, and neither has anything that would make the
production site safe to test against. Phase 2 leaked 27 records onto the live site before
the stray `frappe.db.commit()` was found; `test.local` exists so that cannot recur.

## 5. Layout and conventions

```
sibbcs/
  academic/doctype/<snake_case>/     DocType JSON (source of truth) + .py + test_*.py
  admissions/doctype/<snake_case>/   same, for the Admissions module
  admissions/tokens.py               reusable token-link controller
  admissions/conversion.py           the conversion point
  www/reference.html|.py             public referee form  (/reference)
  www/mentor-consent.html            public mentor form   (/mentor-consent)
  www/mentor_consent.py              its controller (Frappe maps - to _)
  setup/schema.py                    helpers for declaring DocTypes in code
  setup/phase1_academic.py           idempotent Phase 1 DocType builder
  setup/phase1_seed.py               programs, terms, course CSV importer
  setup/phase2_admissions.py         Phase 2 DocType builder
  setup/phase2_workflow.py           admission workflow
  setup/phase2_email_templates.py    reference / mentor / offer emails
  setup/phase1_workspace.py          Academic workspace
  setup/phase2_workspace.py          Admissions workspace
  setup/data/courses_template.csv    catalog import template
```

- DocType JSON is generated by running the builder with `developer_mode` on, then
  **committed**. The builder is the reproducible recipe; the JSON is the artifact.
- Builders and seeders are **idempotent** — re-running must never duplicate or clobber.
- Tabs for indentation in Python (Frappe house style). Business rules live in the
  DocType controller's `validate`, with a test per rule.

## 6. Environment

Server `14.98.31.75:2222` (SSH), user `theiox`. Site **`online.sibbc.org`**,
bench at `/home/theiox/frappe-bench`, database `sibbcs_erp`.

| | |
|---|---|
| OS | Ubuntu 26.04 "resolute", kernel 7.0 |
| Python | 3.14.4 (system) — Frappe v15 declares `>=3.10,<3.15` |
| Node | 22.23.2 via nvm (LMS requires ≥22; Frappe only ≥18) |
| MariaDB | 11.8.6, `utf8mb4` / `utf8mb4_unicode_ci` |
| Redis | 8.0.5 · **nginx** 1.28.3 · **supervisor** 4.3.0 |
| Apps | frappe 15.117.0, payments 0.0.1, lms 2.61.0, sibbcs 0.0.1 |

- `bench start` runs as the **`sibbcs-bench`** systemd unit (`Restart=always`, enabled at
  boot). `systemctl restart sibbcs-bench` after changing Procfile-level things.
- Credentials (MariaDB root, Administrator) are in `/home/theiox/.sibbcs-credentials`,
  mode 0600.
- `sudo` here is **sudo-rs**, which has no `-A`/askpass. Use `echo <pw> | sudo -S -p ""`.
- IPv6 has no route on this host but DNS returns AAAA first, so `/etc/gai.conf` prefers
  IPv4 and apt is pinned to `Acquire::ForceIPv4`. `raw.githubusercontent.com` is
  intermittently reset — clone from `github.com` instead of `curl | bash` installers.
- `theiox` is in the `supervisor` group; the socket is `root:supervisor 0770`.

### nginx

`bench setup nginx` output is symlinked to `/etc/nginx/conf.d/frappe-bench.conf`; it
upstreams to `127.0.0.1:8000` (web) and `:9000` (socketio), which both the dev server and
a production gunicorn bind — so the config is valid either way. Two fixes were needed:

- Frappe's template logs with `access_log ... main`, a format the **nginx.org** default
  `nginx.conf` defines but **Ubuntu's does not**. Defined in
  `/etc/nginx/conf.d/00-log-format.conf`, which must sort before `frappe-bench.conf`
  because `conf.d/*.conf` is parsed alphabetically and an unknown log format is a
  parse-time error.
- `chmod o+x /home/theiox` so the nginx worker can traverse into the bench to serve
  `/assets` and `/files`.
- The stock page was moved aside to `/etc/nginx/conf.d/default.disabled`.

### TLS

Live on **https://online.sibbc.org** with a Let's Encrypt certificate; port 80 returns
`301` to https. Two things were needed beyond issuing the cert:

- **`dns_multitenant` must be on.** `bench/config/nginx.py:prepare_sites()` only fills
  `sites["that_use_ssl"]` — the list the template renders as `listen 443 ssl` — when
  `common_site_config.dns_multitenant` is set. Without it the site falls into port-based
  multitenancy and gets a plain `listen 80`, *no matter what `ssl_certificate` says in
  site_config*. This is the whole reason 443 stayed silent after the cert was issued.
- **Cert paths belong in `site_config.json`**, not hand-edited into the nginx file —
  bench's template reads `ssl_certificate` / `ssl_certificate_key` from there, so
  `bench setup nginx` regenerates a correct TLS config instead of clobbering edits.

Issued with the **standalone** challenge, not webroot: Frappe's nginx template has no
`/.well-known/acme-challenge` location and proxies unmatched paths to the backend, so a
webroot challenge 404s. Standalone needs port 80 free, so `systemctl stop/start nginx`
are registered as renewal `pre_hook`/`post_hook`; `certbot.timer` is enabled and
`certbot renew --dry-run` passes. Renewal costs a few seconds of downtime, twice a year.

### Common commands

```bash
cd /home/theiox/frappe-bench
bench --site online.sibbc.org migrate
bench --site online.sibbc.org run-tests --app sibbcs
bench --site online.sibbc.org execute sibbcs.setup.phase1_academic.build
bench --site online.sibbc.org execute sibbcs.setup.phase1_seed.seed_all
bench --site online.sibbc.org console
```

## 7. Roles

`Registrar`, `Admissions Officer`, `Academic Coordinator`, `Faculty`, `Facilitator`,
`Formation Coordinator`, `Accounts`, `Student`. **Mentors never log in** — token-link web
forms only (Phase 6). Faculty scoping needs a User Permission on Course Offering *plus* a
permission query condition, or faculty see the whole gradebook.

## 8. Open decisions that block later phases

| # | Question | Blocks |
|---|---|---|
| 1 | Tuition ceiling — cap ₹54,000, pay-as-you-go, or cap at 8 years? | Phase 4 |
| 2 | Grade component weights (Assignment / Forum / Attendance / Final Paper) | Phase 5 |
| 3 | GPA scale — letters, % bands, grade points (pass = 60% confirmed) | Phase 5 |
| 4 | Attendance thresholds for pre-recorded courses | Phase 5 |
| 5 | May a Level 2 student take a Level 3 course? **Currently blocked** | Phase 3 |

Phase 1 data still needed: the course catalog (CSV), faculty list, program credit
totals and durations, and real term teaching dates (seeded dates are derived from
application deadlines and flagged for review).

## 9. Public access — live

**https://online.sibbc.org** is reachable from the internet and serves Desk, `/login`,
`/lms` and the API. DNS: `online.sibbc.org` → `14.98.31.75`; `sibbc.org` stays on the
marketing host `216.198.79.1`. The gateway forwards 80, 443 and 2222 to `192.168.7.213`.
The host has no local firewall (ufw inactive, iptables ACCEPT).

**Still the development server**, by explicit choice — gunicorn/supervisor production mode
(`bench setup production`) has *not* been run, because it needs a sudoers drop-in for the
bench user. `bench start` runs under the `sibbcs-bench` systemd unit with
`Restart=always`, fronted by nginx. Switch before go-live: the dev server is
single-process and will not hold 200+ concurrent students.
