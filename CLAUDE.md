# SIBBCS ERP — `sibbcs` app

University ERP for South India Baptist Bible College & Seminary (Online), Coimbatore.
Built on Frappe Framework v15, with teaching in **Campus LMS Lite** at `lms.sibbc.org`.
Scale: 200 students → 1,000 in 2 years.

Full spec: `SIBBCS_ERP_Architecture.md`. This file is the always-in-context summary —
read it before touching anything, and keep it current as phases land.

---

## 1. Stack decision

| Layer | Choice | Why |
|---|---|---|
| Platform | **Frappe Framework v15** | Owns DocTypes, workflows, roles, web forms, portal |
| Learning delivery | **Campus LMS Lite** at `lms.sibbc.org` | A separate Node/Postgres application. Courses, modules, pages, assignments, quizzes and marking all live there — see §10 |
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
  `programs`, `is_active`. The `lms_course` link went with the bundled app in Phase 7
  - child **`Course Prerequisite`** — `prerequisite_course`, `is_hard`
  - child **`Course Program Link`** — `program`
- **`Academic Term`** — `term_name` (docname, e.g. `2026-T4`), `term_code`, `start_date`,
  `end_date`, `application_deadline`, `registration_opens`, `registration_closes`,
  `duration_months` (default 2), `status` (Planned/Open/Active/Closed)
- **`Course Offering`** — docname `{course}-{term}`; `course`, `term`, `format`,
  `instructor`, `facilitator`, `zoom_days`, `zoom_time`, `capacity`, `enrolled_count`,
  `status` (Draft/Published/Running/Completed). `lms_batch` went in Phase 7
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

### LMS sync — `sibbcs/integrations/campus_lms.py`

Students, offerings and registrations are **pushed** to Campus LMS Lite; released marks
are **pulled** back. See §10 for the whole picture. `academic/lms_sync.py` was the
equivalent for the bundled `lms` app and went in Phase 7 with that app.

Each push is a background job enqueued after commit, so a registrar saving a record never
waits on another system nor fails because it is down.

### Registration, payment and promotion — Phase 5

**The course opens on payment, not on Register.** The rule lived in
`Course Registration.maybe_sync_lms`, which gated enrolment into the bundled LMS; Phase 7
moved it to **`campus_lms.registration_payload`**, which sends an unpaid registration as
`inactive`. Settling the invoice re-pushes from `Fee Invoice.refresh_payment_state`, not
from a doc hook: payment almost always arrives as a Payment Entry allocation, which uses
`db_set` and so never runs `on_update`. The gate only ever narrows — a settled fee does
not make a withdrawn registration active.

**The gate is only as good as the gateway behind it.** With none configured it would shut
everyone out, so it is a setting and `require_fee_for_lms_access` is currently **0** on
`online.sibbc.org`. Turn it on the day Razorpay or Jodo goes live.

**A level takes eight passed courses**, counted on `level_at_registration` — the level the
student was at when they took them, not a lifetime total, which would let a Level 3
student promote on courses passed years earlier at Level 1. The figure lives on
`Program.courses_per_level` (seeded 8; zero disables). `Level Promotion.override_shortfall`
lets an approver promote anyway, with the reason in Remarks.

**Promotion is a Dean, Registrar or Academic Coordinator decision.** `Dean` is a new role.
`may_approve()` guards both the DocType and `eligible_for_promotion()`, the working list
of students ready to move up.

**The Dean's page** is a Desk page at `/app/level-promotions` (module `Academic`, roles
Dean / Registrar / Academic Coordinator / System Manager). It lists active enrollments with
passed-vs-required, a progress bar and a Promote button; a checkbox shows the ones who are
not ready yet, because "who is nearly ready" is the same question a fortnight earlier.
Promoting asks for Remarks as a required field — a level change is the one thing on a
transcript nobody can reconstruct later.

`promotion_board()` is **three queries for the whole college**, not three per student. The
obvious version calls `eligibility()` in a loop, which is a `get_doc` and two counts each:
fine for eight students, three thousand queries at a thousand. A test asserts the loop has
not crept back.

Students see the fee state on `/my-courses` with a Pay button per row, and an unpaid row
reads "Opens on payment" rather than a bare "Pending".

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
- **The applicant gets no role here at all.** They used to be granted `LMS Student`, a
  role belonging to the bundled app; Phase 7 removed both. The exam is sat in Campus LMS
  Lite under its own account, which `enroll_in_exam` creates and whose activation link
  this module emails — the LMS has no SMTP of its own.

Where the exam lives is config, not code — `entrance_exam_url` wins for an exam hosted
outside the LMS entirely; otherwise `campus_lms_url`. With **neither set the account is
still created** and the step reports why nothing was sent, rather than mailing a dead
link. `entrance_exam_lms_course` named a course in the bundled app and is no longer read.

### The preliminary orientation course

Step 12 is delivered as a **course**, not a PDF. `Reading Manual.delivery` is `Document`
or `LMS Course`; on the course path the candidate is enrolled in Campus LMS Lite, and
`/manual-reading` refuses their signature until **every required item** is complete.

That distinction is the point: onboarding is gated on this step, and acknowledging a PDF
is one click — it records that somebody pressed a button, not that anybody read anything.
A course records an item at a time.

**The course is `ADMISSIONS-ORIENTATION` in Campus LMS Lite** — 5 modules, 49 pages,
migrated from the bundled app's `m-div-preliminary-orientation` in Phase 6.
`Reading Manual.lms_course` still holds that old slug, which
`campus_lms.MOVED_COURSES` maps to the course over there; the field is **Data**, not a
Link, because the app it pointed at is gone. `manuals.manual_course` validates it against
that mapping rather than asking whether an LMS Course exists — the old check would answer
False for every manual once the app was uninstalled.

`manuals.course_progress` asks `/sync/progress` rather than counting rows: the LMS knows
which items ask something of a candidate and which are only there to be read past. An
unmapped course, or a person the LMS has never heard of, is reported and treated as **not
complete** — a signature must never be let through on an absence of evidence.

**The two handbook PDFs are attached to the `Reading Manual`.** They were attached to the
bundled LMS course, and all 49 migrated pages link to them by absolute URL
(`https://online.sibbc.org/files/...`), so deleting that course would have cascade-deleted
the files and broken every one of those links. Re-homed in Phase 7 before the uninstall.

**The Formation Handbook is only partly imported, on purpose.** Its Level 1-4 sections are
reflection and goal-setting forms filled at the start of each level *with a mentor*.
Importing them would have a new admit writing Level 4 goals before beginning Level 1,
guided by a mentor not assigned until Phase 6. Only the Welcome Note, "Before You Begin"
and the Formation Covenant are in.

**The handbooks said Canvas.** The college wrote them for Canvas; six sentences asserted
Canvas behaviour this college does not have (a mobile app, `Account → Settings`, an
emailed password, an enrolment invitation, an Announcements section, and a claim that the
seminary cannot reset a password — false here). Those were rewritten before the migration,
so the pages now in Campus LMS Lite carry the corrections. **The attached PDFs are
untouched** and still say Canvas.

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

**`onboard_level` decides the level once, and then stops deciding anything — 21 Nov 2026.**
It is copied into `Program Enrollment.current_level` at the instant the Student is created,
and the enrolment owns it from then on. Two live applications read Level 2 while the
students they had created sat at Level 1: both had been edited the day *after* conversion,
and one had been **blank** at conversion, so the `or "1"` fallback decided. Nothing on
screen said the edit could not reach the student. `warn_level_is_settled()` now refuses to
change `onboard_level` once a Student exists, naming the student, the level they are
actually on and the Level Promotion that moves it — a refusal rather than a note because
the staff console reads `_server_messages` **only on failure**, so a `msgprint` on a
successful save is invisible there. `entry_level` stays editable: it is advisory, never read
by conversion, and so cannot mislead anybody. The student page also warns when the two
disagree, which is the state the live records were already in.

### The entrance exam

Three essays, **25 marks each, 75 total, pass at 40%**, one attempt, marked by hand.
It lives in Campus LMS Lite as `ADMISSIONS-ENTRANCE-EXAM` — a `short_answer` quiz with no
answer key, which that system leaves `pending_review` for a human. Ramsem is enrolled as
`teacher`; the marking rubric is an **unpublished page**, visible to markers and not to
candidates. Migrated from the bundled app's `entrance-exam` course in Phase 6.

**Results are pulled, not pushed.** A cron every 15 minutes runs
`sibbcs.admissions.entrance_exam.pull_marked_exams`, which asks `/sync/quiz-results` for
marked attempts and writes the `Qualifying Exam Result`. Pulling keeps every credential on
this side and retries itself; an officer may wait a few minutes after marking, which is
the price. **That job must be registered**, and it was declared in `hooks.py` for a while
without being synced into `Scheduled Job Type`, so nothing pulled at all —
`sync_jobs()` lives in
`frappe.core.doctype.scheduled_job_type.scheduled_job_type`, not `frappe.utils.scheduler`.

Two rules in `admissions/entrance_exam.py` are the reason that module was kept rather
than rewritten:

- essays map **positionally** onto `ESSAYS`; an open-ended question carries no key to
  match on, and a submission without exactly three answers is reported, not guessed at.
- **Sat is not marked.** The LMS records a submission the moment a candidate presses
  submit, unmarked. Recording that would tell the college they scored nothing, so the
  pull refuses it and the screen says "Sat, not marked".

The pass mark is the college's (`Qualifying Exam Result.pass_mark`, **40**), never the
quiz's own figure. `Qualifying Exam Result.total` is a **percentage** — 45 of 75 stores as
60.0 — so a raw mark and the stored figure are not meant to match.

**A result can also be entered by hand** through `entrance_exam.record`, and was for
APP-2026-00015: its LMS rows were never marked, so the archive shows 0/75 while
QER-2026-00002 holds the real 20/20/25.

### Production was cleared of test data on 31 Aug 2026

Everything the college had been testing with is gone: 8 admission applications,
2 students and their enrollments, the qualifying exam result, interview, scholarship
request, 5 fee invoices, the lead, all 7 catalog courses (6 `DEMO` plus `BISTO608`),
12 course offerings, both `DEMO-TERM` terms, 2 instructors, 4 LMS courses
(Frappe's own `a-guide-to-frappe-learning`, plus `pastoral-ministry`, `history` and
`church-history`), every LMS enrolment and progress row, the placeholder reading
manual, and the accounts `ash@ipp.com`, `william.ferdi@gmail.com` and
`vignesh.g@elmeasure.in` with their contacts and queued mail.

**Kept on instruction:** the `entrance-exam` and `m-div-preliminary-orientation` LMS
courses with their chapters, lessons, quiz, questions and attached PDFs; the four
Programs; the five real 2026 terms; the six Fee Types; `ramsemz@sibbc.org`; and the
**`DEMO Grade Scale`**, which is the only grade scale on the site — grading needs one,
so it stays until the college supplies the real bands. Rename it then; do not seed a
guess.

`setup/demo_data.py` still exists and is **never** wired into install or migrate — it
only runs when somebody types `bench execute sibbcs.setup.demo_data.seed`. Its `purge`
counterpart removes only what it seeded, which is why the clear-out above was done with
a separate survey-then-apply script rather than by calling it.

Two ordering traps if this is ever repeated. Chapters hold `Lesson Reference` rows
pointing at their lessons while each lesson links back to its chapter, and the same
shape occurs between a Course Registration and its fee invoice, a Student and its
application, and a Scholarship Request and its application. Cut one side of each cycle
and delete normally; reaching for `force=True` across the whole set would skip the link
checks that catch a reference from something you meant to keep — which is exactly how
`entrance-exam` was found still listing a deleted user as an instructor.

### The React front end — `frontend/`

One Vite app serves two products: the **student portal** at `/portal` and the
**staff console** at `/staff`. React 19 + TypeScript + Tailwind v4 + shadcn-style
components copied into `src/components/ui/` and restyled — deliberately not
frappe-ui, whose look the college did not want.

```
frontend/                    source; `yarn build` (needs no NODE_OPTIONS, ~1s)
  ↓
sibbcs/public/portal/        built bundle, committed, served at /assets/sibbcs/portal/
  ↓  index.html is copied over
sibbcs/www/_portal.html      GENERATED. Do not hand-edit; the next build overwrites it
sibbcs/www/_portal.py        get_context() -> the boot payload
```

**Nothing you edit in `frontend/src` reaches the site until `yarn build` runs.**
The bundle is committed so deployment needs no Node toolchain. `TestPortalPage`
asserts the file `_portal.html` names is actually on disk, so a forgotten or
half-finished build fails a test rather than a page.

**Boot data, not a round trip.** `_portal.html` carries the loop LMS uses:
`{% for key in boot %}window["{{ key }}"] = {{ boot[key] | tojson }};{% endfor %}`,
appended by our own `plugins/jinja-boot.ts` at build time. It is where
`window.csrf_token` comes from. `_portal.py` commits after minting the token —
without that the page and the server disagree and every write from a freshly
loaded page is rejected. Every value must be JSON-serialisable; one that is not
breaks the whole page, not one field, so a test round-trips the payload.

**`/staff`, never `/console`.** Werkzeug's debug middleware reserves `/console`
for its own interactive console (`console_path="/console"`) and `bench start`
wraps the app in it — so `/console` answered **400 before Frappe saw the
request** while `/console/anything` worked, which reads exactly like a routing
bug of ours. It would come back the day the site moves to gunicorn. A test
asserts the route is not reintroduced.

**Data layer is TanStack Query, not frappe-ui resources.** `lib/frappe.ts` is the
only thing that talks to the server: it unwraps Frappe's `{message: ...}`
envelope, digs the real text out of `_server_messages` (a JSON string holding an
array of JSON strings), sends `X-Frappe-CSRF-Token` on writes only, and omits the
header entirely when there is no token — Frappe rejects an empty one rather than
skipping the check. Query caches **data** keyed by a query key, so it cannot
repeat the frappe-ui failure where one component inherited another's callbacks.

**Route guards are cosmetic.** `RequireAuth` only decides what to render;
`setup/permissions.py` and each endpoint's own checks are the boundary.

**Development.** `yarn dev` proxies `/api`, `/assets`, `/files`, `/app` and `/login`
to `FRAPPE_URL` (default `http://127.0.0.1:8000`) with the site named
in `FRAPPE_SITE` (default `test.local`) — the bench is DNS multi-tenant, so a
request on localhost must say which site it means. Develop against `test.local`
with `demo_data.seed`, not production.

**jsdom has no `matchMedia`**, so anything reading the colour scheme throws on
render. `src/test/setup.ts` stubs it.

### The student portal — `sibbcs/api/student.py` + `frontend/src/routes/portal`

Nine sections, the order the college specified. Dashboard, My Courses, Grades and
Profile are built; registration hangs off My Courses at `/portal/courses/register`
rather than taking a tenth slot in a navigation specified as nine.

**One call per screen.** `dashboard()`, `grades()`, `my_courses()` and
`registration_options()` each compose what one page draws. The rules stay in
`academic/portal.py` and `academic/eligibility.py`; this layer only assembles.
Components, LMS progress and fee state are fetched with one grouped query each, not
one per row — a student finishing the programme has forty registrations.

**No endpoint takes a student or enrollment argument.** Every one answers for
`frappe.session.user`. A test asserts the signatures stay empty, because a `student=`
parameter is how one student reads another's marks by guessing a name.

**`update_profile` takes three named arguments, never `**values`.** Mobile, WhatsApp
and address are how the college reaches you. Name, date of birth, gender and email are
the Registrar's record of who you are and are shown read-only. A `**values` signature
would let a student write any field on their own Student row — `status` included,
which is how somebody marks themselves Active again after being withdrawn.

**Blocked offerings are returned with their reason.** `eligibility.explain` already
says why; hiding the row instead is what turns *"why can't I take this?"* into an
email to the Registrar. Offerings are grouped by term because a course runs in
several, and a flat list of near-identical rows is how students registered for the
wrong one during acceptance testing.

**`QueryState` renders the page heading while loading**, so a test that waits on the
heading is still looking at skeletons. Wait for `[data-slot="skeleton"]` to clear.

**`demo_data.seed()` now creates a student**, `DEMO Ruth Anandhi`, with two graded
courses behind her, one registered and unpaid, one course whose prerequisite she has
just met, and two above her level the rule engine refuses with a reason. Without her
the seeder produced a catalog and nothing that exercises the portal at all. Give her a
password with `demo_data.set_student_password`; `purge()` still removes her, because
she matches on the `@example.invalid` domain it already looked for.

**Fee Invoice cannot be marked paid by assignment.** `paid_amount` is derived from the
Payment Allocation rows pointing at the invoice, so `status = "Paid"` is undone by its
own `validate()`. The demo seeder settles fees through a real Payment Entry.

### Portal communications — `sibbcs/api/comms.py`, `sibbcs/api/agenda.py`

Phase 2 completed the nine sections. **Two new DocTypes only**, built by
`setup/phase6_portal_comms.py`: `Announcement` (+ `Announcement Read`) and
`Portal Message` (+ `Portal Message Recipient`).

**To Do and Calendar are derived, never stored.** An unpaid invoice is already a
thing to do and a live class is already a calendar entry; writing them down again
means keeping two copies of one fact in step, and the copy is the one that goes
stale. `agenda.todo()` assembles from Fee Invoice, blocked registrations and open
registration windows. `agenda.calendar()` is the weekly recurrence expanded from
`Course Offering.zoom_days` + `zoom_time`, fee due dates and term milestones. The
bundled LMS's assignments, live classes and batch timetable were sources here too and
went in Phase 7 -- all three were empty on the live site, because the college schedules
its Zoom sessions on the Course Offering.

**Read state is its own DocType, not a child row.** A thousand students marking one
notice as read would otherwise rewrite that notice a thousand times, every write
colliding with the next.

**An unknown announcement audience reaches nobody.** `_addressed_to_me` returns
False for an audience it does not recognise. Defaulting the other way is how a
notice for one cohort lands on every student's screen the day somebody adds a new
audience type.

**A student cannot name a message recipient.** `send_message(subject, body,
reply_to)` — no recipient parameter at all. A reply reaches whoever is already on
the thread; a new message goes to whoever holds Registrar, Admissions Officer or
Academic Coordinator. Without that the portal is a way to message every account on
the site. Those roles **are** held now (checked 18 Nov 2026: Registrar 3, Academic
Coordinator 2, Admissions Officer 1), so `office_contacts()` answers — it used to be
empty, and the compose form still says so rather than failing on send when it is.

**Discussions reuse Frappe's `Discussion Topic` / `Discussion Reply`**, scoped to a
Course Offering the student is registered on. That DocType is shared — Frappe uses
it for blog comments too — so every entry point re-checks `reference_doctype` is
`Course Offering` before opening a thread.

**Badges are polled, not pushed.** `unread_counts()` on a 60-second interval. Frappe
has socketio, but a count a minute stale costs a student nothing, and a websocket
per signed-in student costs the box something at a thousand of them.

**Rich text is sanitised on every render.** `RichText` runs DOMPurify over the
Text Editor HTML. Staff write these, but a compromised staff account should not
become script running in every student's browser.

### `before_tests` raises the user-creation throttle

`sibbcs/install.py::before_tests`, wired in hooks.py. Frappe refuses more than **60
new Users a minute** (`throttle_user_creation`); this suite makes several hundred in
about a minute. When it trips, the tests that fail are whichever module was running
when the budget ran out — so it reads as an unrelated regression in `test_lms_sync`
or `test_conversion` rather than as a rate limit. Written to the test site's config,
because the runner re-initialises `frappe.local` between modules and an in-memory
value survives only the first one.

Fixture emails use `frappe.generate_hash`, not a counter: inserting a User commits,
so those records outlive the run that made them and a counter restarts into a
collision.

### The staff console — `sibbcs/api/admissions_api.py`, `sibbcs/api/console.py`

`/staff` is the overview, `/staff/admissions` the pipeline, `/staff/admissions/:name`
one candidate. All of it arranges what `sibbcs/admissions` already does; nothing here
decides anything.

**Console panels are gated on ROLE, never on `has_permission`.** Students hold read
on Fee Invoice and Program Enrollment — they have to, to see their own — and these
panels are SQL aggregates over *every* row. Gating them on the DocType permission
handed a signed-in student the whole college's billing totals. `PANEL_ROLES` decides,
and a test asserts a student is refused the console outright. `_require_staff()` in
admissions_api checks a role **alongside** the DocType permission for the same reason:
the day somebody grants Student read on Admission Application so an applicant can see
their own, a permission check alone would hand them the whole intake.

**The browser names an action, never a method.** `ACTION_HANDLERS` maps the names
`checklist.ACTIONS` hands out to dotted paths, and `run_action` refuses anything not
in that table — so a crafted request cannot reach an arbitrary whitelisted function.
Tests assert every action the checklist offers has a handler, that each resolves to
something callable, and that each is separately whitelisted.

**A step with no checklist row yet is still outstanding.** Eleven of the thirteen
default to a status that is not done, and a fresh application has no rows at all —
counting only stored rows reports it as finished. The funnel adds the absent ones.

**`_progress_for` counts in one grouped query**, not one `checklist.progress()` per
application; a test asserts the fast path agrees with the per-document one.

**`or_filters` with a bare value means `=`, not `LIKE`.** The search box matched
nothing until the operator was spelled out: `{field: ("like", pattern)}`.

**`Interview Record.panel` is a child table, not a column** — selecting it fails at
the database rather than in Python.

**`LIST_FIELDS` is deliberately not `*`.** A pipeline row is a name and a state; date
of birth, address and the candidate's photograph belong behind a click. Tests assert
both field lists exist on the DocType, so a rename fails a test rather than rendering
empty rows.

### The academic console — `sibbcs/api/academic_api.py`

`/staff/academic` with two tabs (offerings, promotions) kept in the query string
so a link to the promotions board is a link to the promotions board. The grade
sheet is `/staff/academic/offerings/:name`. **Students moved out** to their own
place in the left menu -- see below.

**Grade entry saves through the document, never around it.** `Course Registration`
keeps the grade fields at **permlevel 1**, so an ordinary `doc.save()` already *is*
the permission check — `ignore_permissions` there would quietly remove it. A test
walks the function's syntax tree looking for that keyword; the first version grepped
the source and matched the docstring explaining the rule.

**A blank mark is not a zero.** `compute_grade` holds the letter back until every
component carries a mark, leaving `final_marks` at its previous value — `0.0` on a
registration never graded. So the endpoint returns an explicit `marks_complete`
rather than letting each screen re-derive it, the number field sends `null` for an
empty box, and the sheet shows *Not graded* instead of a score that is a lie.

**`weighted_score` is recomputed, never accepted.** A caller can send any figure it
likes; the document derives it from the raw marks. A test sends 999 and expects 30.

**Component and status choices come from the DocType**, not from a list in the
front end — hard-coding them is how the sheet offers a value the Select refuses on
save. Tests assert both still match.

**The console is role-gated, like the rest.** Students hold read on Student and
Course Registration because they must see their own; these endpoints list everybody.

**Test fixtures build their own registration.** Grading the first `Registered` row on
the site moves it to `Completed`, so a test that borrows one leaves the next run with
nothing to borrow and silently skips. Note `make_offering` leaves an offering in
**Draft**, which the rule engine correctly refuses to register anyone onto — pass
`status="Published"`.



### The demographics panel — `/staff/students`

Six donuts above the roll: programme, gender, current status, academic level,
mature candidates, transfer students. `academic_api.demographics()` builds them
in four queries whatever the number of students -- the obvious version asks the
enrolment and the application per student, which is 200 round trips today and
2,000 next year.

**The panels describe the whole roll, not the filtered list.** They are a
standing description of the college; a search box that made them jump would
make them useless for the thing they are for.

**Colour is assigned by the job it does**, and the palette was validated rather
than eyeballed (`scripts/validate_palette.js` from the dataviz skill, both
modes, our own surfaces):

- **categorical** (programme, gender) -- a fixed slot order, never cycled, and
  a slice keeps its slot whatever else is drawn, so a programme emptying out
  cannot repaint the others. Validated on the *adjacent* pairlist, which is the
  honest one for a ring: a slice only touches its neighbours and the legend does
  the identifying.
- **status** (active, withdrawn) -- the reserved status colours, never reused as
  a series.
- **ordinal** (Level 1-4) -- one hue, light to dark, so the order is in the
  colour.
- **binary** (yes / the rest of the roll) -- one hue against a neutral, because
  "no" is a remainder rather than a competing identity.

The lighter slots sit under 3:1 on a white surface, which the validator flags as
requiring relief: the legend under every donut carries the label **and** the
count, so identity never rests on colour alone. Empty categories stay in the
legend -- "B.Th 0" is a fact worth seeing.

Series colours live in `index.css` beside the rest of the theme, under `:root`
and `.dark`. The dark values are steps chosen for the dark surface, not a flip
of the light ones, and `light-dark()` is deliberately not used: the app switches
theme with a class, which that function would not follow.

**Faces in both lists.** `Student.photo` and `Admission Application.photo` now
reach `/staff/students` and `/staff/admissions`. The files are private, so they
load on the reader's own session and fall back to initials. Note this reverses
an earlier judgement that the pipeline should not ship a photograph to a list --
the college asked for it, and a row is easier to find by the person than by the
reference. Date of birth, address, the ID document and the officer's notes are
still behind a click, and the test says so.

### The student profile -- `/staff/students`, `academic_api.student()`

The roll is its own item in the left menu rather than a tab inside Academic:
looking a student up is the most common thing anyone does in this console, and
it is not only an academic question. `/staff/students` lists, and
`/staff/students/:name` is the whole profile. The old `/staff/academic/students/:name`
still resolves -- it redirects, so bookmarks and old links keep working.

**A profile is two records read together.** `Student` holds identity and contact
and nothing else -- no schooling, no church, no certificates. All of that was
asked once on the **Admission Application** and `conversion.py` deliberately does
not copy it across, so `academic_api.student()` reads the linked application for
the education, the ministry, the documents, the references and the mentor. Change
one of those fields and the profile follows; there is no second copy to drift.

**The block is omitted, never faked.** `_admission_profile()` returns `None` when
there is no application *or* when `frappe.has_permission("Admission Application",
"read")` says no -- **Faculty** hold nothing on that DocType but are in
`ACADEMIC_ROLES` and can open a student. The page then says *which* of the two it
is: "created directly rather than admitted" and "your role may not read it" are
different facts, and a registrar chasing a missing certificate needs to know
which one they are looking at.

**The onboarding statuses are `checklist.board()`, read live.** Not a copy, not a
second derivation -- two pages disagreeing about where a candidate stands is
worse than one page showing nothing. A test asserts the profile's rows equal the
board's.

**The evidence cards are shared.** `components/AdmissionEvidence.tsx` holds
`DocumentsCard` and `ResponsesCard`; the application under review and the student
it became use the same two. The reference and mentor answers still come from
`reference_form.view` / `mentor_form.view`, which render the questions
server-side, so the forms cannot drift from what is displayed.

**The twelve fields the old system carried were added on 1 Sep 2026**, in two
groups that must not be confused:

* **Declared by the candidate**, and asked on `/apply`: `mother_tongue`,
  `nationality`, `church_denomination`, `salvation_status`, `baptism_status`,
  `sense_of_call`. All optional -- a required field added to a live form
  breaks the application somebody is halfway through.
* **Determined by the college**, and never on the public form: `ata_eligible`,
  `mature_candidate`, `transfer_student`, `education_sequence_mismatch`,
  `whatsapp_groups`, `theological_writing_status`.

`public_form.APPLICANT_FIELDS` is a whitelist, so leaving the second group out of
it *is* the guarantee that a crafted payload cannot claim ATA eligibility. A test
posts all six and asserts every one stayed at its default.

`_clean()` also drops a Select value the DocType does not offer rather than
letting `doc.insert()` throw -- Frappe's validation error names our field
internals, and it would go back to whoever asked. Only a crafted payload can
reach it; the form lists exactly the offered values.

The four Check flags are **badged only when true**. A row of "No" badges is
noise the eye has to read past to find the one that matters.

The option lists (`I am Saved` / `Still Seeking`, `Baptised` / `Not Baptised` /
`Planning to be Baptised`, `Yes, clearly` / `Yes, still discerning` / `Not yet
sure`) were chosen to match the wording in the college's old profile; changing
them is a DocType edit plus the matching `<option>` in `www/apply.html`. A test
asserts every whitelisted field actually appears on that page -- a field the form
never asks for collects nothing.

### Finance and accounts — `sibbcs/api/finance_api.py`, `sibbcs/api/users_api.py`

`/staff/finance` (invoices, payments, scholarships) and `/staff/users`. This
completed the console: **no screen is a placeholder any more**, and `ComingSoon` was
deleted with the last of them.

**A payment is created through the document.** `Payment Entry.validate_allocations`
refuses over-allocating an invoice or spending more than the payment is worth —
exactly the mistake worth catching now rather than at reconciliation. With no
allocation given, the document's own `auto_allocate` settles the oldest invoices
first. Money left over comes back as `unallocated` rather than being hidden.

**`users_api` will not do three things, on purpose.** It never touches a **password**
— Frappe owns those, and a test greps the module for `update_password` and friends.
It cannot grant **System Manager**, because handing that out from a web form is how
one compromised account becomes every account. And it **disables rather than
deletes**, because a User is linked to a Student, to payments and to an audit trail.

**`set_roles` touches only the managed list.** Roles outside it are left exactly as
found, so a crafted request cannot use it to promote anybody and an honest one cannot
drop a role the screen never displayed. An unmanaged role in the request is *refused*
rather than silently dropped — dropping it would tell the caller it worked.

**The role summary counts enabled accounts only**, and the screen warns when a role
has nobody: an empty Registrar is why a student's portal message has nowhere to
arrive and why no promotion can be approved. Every one of them has a holder as of
18 Nov 2026 — Registrar 3, Academic Coordinator 2, Accounts 2, Admissions Officer 1,
Dean 1 — so the warnings that used to cover this screen are gone.

**A capped list says it was capped.** `api/paging.py::fetch_capped` asks for one row
beyond the limit and reports `truncated`. Two hundred results with no sign there are
four hundred is a Registrar reading a truncated list and believing it. A test
surfaced this: searching a fragment shared by every fixture student hit the cap.


### The app shell must not be cached — 3 Sep 2026

`/staff/...` and `/portal/...` are one 1.8 KB HTML shell that **names a
content-hashed bundle**. It was served with **no `Cache-Control` header at
all**, so browsers applied heuristic freshness and kept it -- and a kept shell
goes on loading the *previous* build. A change ships, the page does not move,
and the deploy looks like it did nothing.

That is what "the photograph is not showing" turned out to be. The evidence was
in `logs/bench-start.log`: at 18:50 the browser fetched
`/private/files/APP-2026-00014-photo.jpeg` and got **200** -- the image was
there, the file was readable, the component rendered it -- and later views of
the same list never asked for it again, because they were running the bundle
from before the change.

`sibbcs.setup.website.no_store_on_app_shell`, registered as an `after_request`
hook, sends `no-store, must-revalidate` on those two prefixes only. Guest pages
are ordinary documents and are left alone.

**`no_cache = 1` in a page controller does not do this.** It disables Frappe's
*server-side* page cache (`X-From-Cache: False`) and says nothing to the
browser. There is no per-page hook for response headers either -- a template
page renderer only carries `self.headers` for web forms -- which is why this is
an `after_request` hook rather than something in `_portal.py`.

The shell also carries the boot payload: the viewer's name, their roles and a
**CSRF token**. `no-store` is the right directive for that on its own merits,
cache-busting aside.

**Two deploys in a row were invisible for this reason** (the guest stylesheet,
then the console bundle). If a front-end change appears not to have shipped,
check the served bundle hash against the built one before touching the code.

### The guest pages — `templates/sibbcs_public.html`, `public/css/public.css`

The six no-login pages (apply, reference, mentor consent, scholarship, manual
acknowledgement, fee receipt) now sit on our own shell instead of Frappe's
`templates/web.html`. Each page changed by exactly one line: its `{% extends %}`.
**No form logic, token handling or submission code moved** — the risk in these pages
is in the submitting, not the styling.

**Hand-written CSS, not Tailwind.** Coupling six server-rendered pages to the portal's
build would put a hashed filename in a Jinja template and force a rebuild every time a
form gained a field. The tokens are the same values as `frontend/src/index.css`, so an
applicant who later signs in sees the same college. The class names stay Bootstrap's
because that is what the existing markup uses.

**The shell must carry `<!-- csrf_token -->` and a `window.frappe` shim.**
`base_template_page.py::add_csrf_token` injects the token by replacing that comment,
and the comment lives in **Frappe's** `base.html` — which this shell deliberately does
not extend. Without repeating it the token is never injected, every form still works
for guests (whose session has no token to check), and a **signed-in** user gets
*Invalid Request*. That is the manual-acknowledgement bug this project already shipped
once; swapping the base template would have shipped it again. The shim comes first
because the injected line assigns to `frappe`, which exists on a Desk page and not
here. `TestPublicShell` pins the marker, the shim, and their order.

**`noindex` on the shell.** A token address is personal to one referee.

`www/my-courses.html` is **not** on the new shell: it is the old server-rendered
student page, superseded by `/portal/courses`, and left alone rather than quietly
retired — old emails may still link to it.


### The apply form's UI — 1 Sep 2026

**The guest stylesheet is cached under a name that never changes.**
`/assets/sibbcs/css/public.css` is served with a long cache life, so a
returning applicant keeps the CSS they downloaded last time and a restyle
simply does not apply -- which is exactly how it was found, a rebuilt form
coming back looking identical. The shell now asks for
`public.css?v={{ asset_version }}`, supplied by
`sibbcs.setup.website.add_asset_version` through the `update_website_context`
hook. It has to arrive that way: `frappe.utils` is **not** reachable from the
Jinja sandbox, so `{{ frappe.utils.get_build_version() }}` renders nothing.
The version is the mtime of `assets.json`, so **`bench build` must be run
after a CSS change** or the query does not move.

**A floated `<legend>` breaks the layout below it.** The section heading band
was first put on the legend with `float: left`, which made it a float *inside*
the fieldset: the two-column grid then laid out beside it instead of collapsing
at 560px, and the page ran 27px wider than a phone. The band is now a
`<span class="sib-legend-bar">` inside an unstyled legend -- which also avoids
`display: flex` on a legend, honoured inconsistently across engines.

**Controls are 16px below 640px.** Anything smaller makes iOS Safari zoom the
page the moment a field is focused, which throws the layout sideways in the
middle of a form.

**Drag and drop is `templates/includes/dropzone.html`**, shared by `/apply` and
`/documents`. The real `<input type="file">` stays in the page, invisible but
present, and a drop sets `input.files` through a `DataTransfer` and dispatches
`change` -- so both pages' upload code is untouched and neither knows the
include exists. Type and size are checked as the file lands; the server still
checks both, this only saves somebody on a phone waiting for an upload that was
never going to be accepted.

**A phone number is two boxes and one field.** `mobile_code` + `mobile_number`
(and the same for WhatsApp and the mentor) are digits-only as you type and are
joined into `+<code> <number>` on submit. Server-side, `_phone()` runs **before**
the `MAX_LEN` cap -- capping the raw text first truncated the number itself --
and anything under `MIN_PHONE_DIGITS` is dropped, so a bare country code is not
stored as a contact.

**The two references are named, not numbered**: Spiritual & Ministerial
(`Pastor-Mentor`) and Academic & Professional (`Professor-Employer`), on the
form and in the console's `ResponsesCard`. The stored `referee_type` values are
unchanged -- the checklist, `reference_form.py` and the pipeline all key on
them. The checklist step labels are still "Reference 1/2 Review" because those
strings are stored on every application's child rows; renaming them is a data
migration, not a label change.

### Generic records and reports — `api/records.py`, `api/reports.py`

The console now owns create, edit and reports as well as the workflows, which
reverses the original alongside-Desk decision. Built **once from metadata**, not
forty times: `describe()` returns the field definitions Frappe already holds and one
React form renders any DocType. `/staff/data`, `/staff/data/:doctype`,
`/staff/data/:doctype/:name`, `/staff/reports`.

**`ALLOWED` is checked before permissions.** A generic write endpoint is a wide door;
the allow-list makes it a narrow one. `User` is deliberately absent — it carries
`new_password`, `api_key` and the role table, and generic CRUD over it is how a form
ends up setting a password. `users_api` handles accounts, narrowly, and
`create_user` takes **no password parameter at all**: Frappe emails a set-password
link so nobody here ever chooses or sees one.

**`Student` was missing from it and the Edit button proved it — 21 Nov 2026.**
`StudentDetail` linked at `/staff/data/Student/<name>`, which could only ever answer
"Student cannot be edited from the console." It is in the academic list now: the record
carries no permlevel-gated and no password field, so the generic form is the whole of
what correcting one takes. **The academic level is not on it**, and must not be — it
lives on `Program Enrollment.current_level`, which is permlevel-gated and moves only
through a **Level Promotion**, the document that records who approved the move and on
what evidence. `/staff/data/:doctype/new` seeds a new record from the query string
(fieldnames the DocType actually has, nothing else), so the student page's **Change
level** button opens a promotion that already knows the enrolment and the level it is
coming from.

**Writable fields come from the metadata, never the payload.** `_assignable()` builds
the set from the DocType, so naming `docstatus`, `owner` or a read-only field in the
request changes nothing. Reads use `frappe.get_list` (applies permissions and user
permissions), not `get_all` (does not). Deletes carry no `force`.

**Permlevels must be read from the permission rows, not `get_valid_perms`.** That
function answers the main permission question and returns **only level 0**, so using
it reported every permlevel-gated field as read-only for everybody — the Registrar
the level was granted to included. Custom DocPerm replaces DocPerm entirely when any
row exists, which is how Frappe resolves them, and Administrator is not uniquely
restricted here when it is exempt everywhere else.

**The report engine puts a field name into `GROUP BY` and `SUM()`**, so
`_checked_field` resolves it through `meta.get_field` and checks its type before it
reaches a query. That is a metadata lookup, not a pattern match on the string.

**`workflow_state` is derived, so do not set it.** The demo seeder used to force it
and the next save of the application recomputed it from the checklist; the
Rejected candidate is now produced by setting the decision step, which is what
actually makes it read as Rejected.

Two honest limits: a **Text Editor field is a textarea holding HTML** and the form
says so, and **CSV export writes the rows already on screen**, not a second
unfiltered fetch — an export that quietly holds more than the table it came from is
how data leaves by accident.

**A grouped report's `limit` caps groups, not records.** `run()` returns
`count` (every record in scope), `shown` (those inside the groups listed) and
`truncated`. It used to return only the sum of the rows, so a field with more
distinct values than the cap under-reported its own total -- exactly what its
test claimed to prevent, and the test only caught it once the test site grew
past a hundred terms.


### Document review -- `sibbcs/admissions/documents.py`, `www/documents.html`

Step 2 is the only checklist step whose verdict is per-file, so it has its own
module and its own controls on `/staff/admissions/:name`: a tick box and a
remarks field on every row, and one button that asks the candidate for whatever
is still outstanding.

**Nothing in `documents.py` sets the step's status.** `set_docs_verified()`
already derives the gate from `REQUIRED_DOCUMENTS` and
`mirror_gates_to_checklist()` moves the step from it, so ticking the last
required box verifies the step on the same save. That is why `review()` saves
through the parent document -- a `frappe.db.set_value` would tick the box and
leave the step where it was.

**The gate is the four required documents, not all seven.** Verify an optional
one and nothing moves, which looks broken unless the screen says so: the card
shows "3 of 7 verified · 4 of 4 required" and the endpoint returns the required
list rather than the front end keeping its own copy.

**"Resubmit Requested" had to be made sticky.** `mirror_gates_to_checklist`
runs on every save and would have put the step straight back to Awaiting Review
-- the documents on file have not changed since the officer asked -- losing the
fact that anybody was ever asked. `STICKY_STATUSES` on the DocType stops that,
and `uploads._answer_resubmit_request()` is the one event allowed to clear it,
because a file arriving is the answer. Both directions have tests.

**Every application now gets an `upload_token` at insert**, not only the ones
that came through `/apply`. One typed into Desk had none, so there was no link
to send it.

**`/documents?application=…&token=…`** is the candidate's page: each accepted
type with where it stands, the officer's remark on anything rejected, and a
file input that uploads on change through the endpoint that already existed.
`uploads.upload_document` replaces the row, clears `verified`, and now clears
the remark too -- keeping it would read as a complaint about the new file.

**Remarks are quoted to the candidate** in the resubmit email, and both the
review card and the dialog say so. They are a reason, not an internal note; if
the college wants private notes, `notes` on the application is the field.

A resubmit is refused, with advice rather than a raw error, when nothing is
outstanding, the application has moved past `uploads.OPEN_STATES`, there is no
email address, or no outgoing mail account is configured.

### Uploading a document from a phone — 19 Nov 2026

Both `/apply` and `/documents` post a file as **base64 inside a JSON body**, which is a
third larger than the file itself. nginx closes a stalled request body after **60
seconds** (`client_body_timeout`, left at its default) and answers 408. On a mobile
uplink a 4 MB photograph of a mark sheet does not reliably survive that.

That is the whole of what APP-2026-00014 was. The submit itself returned 200 in under a
second on both attempts and the applicant was emailed each time — but every document
then died at nginx: three 408s, each taking three and a half minutes to come back. The
page read *"Uploading documents…"* throughout with nothing moving, because the counter
only advanced on a **success**. It was taken for a frozen page, the candidate submitted
again, and the application reached the console with no documents on it at all. The
submit was never the problem; the evidence is one line per failed file in
`/var/log/nginx/access.log`, which is the first place to look next time.

Three changes, none of them to the endpoint:

- **`templates/includes/image_shrink.html`** re-encodes a photograph to 2000px on the
  long edge at JPEG q0.82 before sending — typically 4 MB down to a few hundred KB,
  which goes up in seconds and never meets the timeout. PDFs and anything already small
  pass through untouched, and **any** failure falls back to the original file: this may
  cost an upload its size, never the upload itself. It applies the camera's own rotation
  while drawing, which Frappe's `strip_exif_data` does *not* do before discarding the
  metadata, so a portrait mark sheet no longer arrives on its side.
  A re-encoded file is **renamed to `.jpg` with a matching content type** —
  `uploads._validate_file` checks the extension, the declared type and the magic bytes
  against one another, so one that kept its old name would be refused outright.
- **The progress text names the file before the attempt**, not after a success.
- **The candidate keeps a way back.** `uploads.candidate_document_url()` is the one
  builder for `/documents?application=…&token=…`, and that address is now on the done
  screen *and* in the acknowledgement email every applicant receives — not only in the
  officer's resubmit message. Without it, a failed upload is recoverable only by somebody
  noticing.

`/documents` also parsed the response as JSON **before** checking `response.ok`, so a 408
— an nginx HTML page — threw a SyntaxError about an unexpected `<`, and that was what the
candidate was shown in place of the reason.

The form also promised the application would move *"from Draft to **Submitted**"*. It
moves to **In Review**: `checklist.derive_state` is what runs, and `Submitted` belongs to
the Frappe workflow in `phase2_workflow.py`, which is not active on the site.

**Still open, and it needs root:** `client_body_timeout` is nginx's default 60s for the
whole server. Raising it (300s) at the `http` level in a `conf.d` file that sorts before
`frappe-bench.conf` would survive `bench setup nginx` regenerating that file.

### Nothing is sent before it has been seen — 19 Nov 2026

The college asked for a look at the whole application before it is saved, and for
the same courtesy on the resubmission page.

**`/apply` now has a review step.** The button says *Review my application*; the
form's own submit builds a summary and goes nowhere near the server, and only
*Confirm and submit* posts. A test asserts there is no `fetch(` in the submit
handler, because a review screen the application has already gone past is worse
than none.

The summary is **read out of the form itself** — every `<fieldset>`, its
`.sib-legend-bar` heading, its `.sub-head` sub-headings and each control's own
`<label for>`. A hand-kept list of field names would be one more thing to update
the day a field is added, and the failure is silent: the field is collected and
saved and simply never shown to the person confirming it. Three details the
generic walk has to get right, each with a test: the honeypot (`#website`) is
never shown back; a phone is one joined value under the number's label, not a
country code on its own; and a field left empty is shown as **Not given** rather
than dropped, because *"did I fill that in?"* is the question the page exists to
answer. The sub-headings matter more than they look — without them the two
references read as "Their name / Their email" twice over.

Documents are **shown, not listed**: a thumbnail for an image, a link that opens
the file for a PDF. "marksheet.jpg, 2.1 MB" does not tell anybody whether they
photographed the right side of the page. Every object URL is revoked on rebuild
and on success; one held open is the whole file held in memory.

**`/documents` no longer uploads the instant a file is chosen.** Choose, see it,
and then press *Send this document* — or *Remove* and pick another. Until now the
wrong file was on the record before the candidate had seen it, with no way to
take it back.

**And the drop zones on that page had never worked at all.** `dropzone.html`
upgrades every `.dropzone` it can find *at the moment it runs*, and it runs where
it is included — which on `/documents` was the top of the block, before any of
them existed. Every zone there rendered with no prompt in it and never named a
chosen file back to the candidate. `/apply` has always had the include at the
foot, which is why the same include worked on one page and not the other.
`TestTheDropZoneIncludeComesAfterTheMarkup` pins the ordering on both.

### The office is told when documents arrive — 19 Nov 2026

A candidate could send every certificate we had asked for and nobody was told:
the resubmit request went out from the console and the answer to it came back in
silence. `notifications.notify_officers_of_documents()` now emails everyone
holding **Admissions Officer** with the candidate, what is outstanding, and a
link straight to `/staff/admissions/<APP>`.

It is called from `uploads.upload_document` **outside the save and unable to fail
it** — a mail problem must never cost a candidate the document they have just
sent.

**Throttled to one email per application per quarter of an hour**, because a
candidate sends six certificates one after another and six emails about one
application is how a useful alert becomes one an officer filters away. Each email
lists everything outstanding rather than just the file that triggered it, so a
throttled one costs the officer nothing.

The throttle is **Redis INCR, not `get_value`/`set_value`** — the trap
`public_form._rate_limit` already documents: `set_value(..., expires_in_sec=...)`
does not populate `frappe.local.cache` while the `get_value` miss before it caches
`None` there, so within one process the throttle silently never fires. The first
version used get-then-set, and the test that proves six uploads are one email is
what caught it.

**`admissions_api.attention()` is the console's nav badge**, polled on a minute
like the portal's unread counts. It counts *applications* with an unverified
document that has a file on it — outstanding work, not unread notices. A per-user
read mark would clear the moment somebody glanced at a list whether or not the
work was done; counting what is actually unverified means the badge goes out when
the documents have been checked and comes back when the next candidate sends one.
It needs no read-state DocType and can never go stale.

### "Draft" is called Awaiting Application Fee — 19 Nov 2026

An application sitting at `Draft` is complete in every respect except the ₹350
fee. To an officer that reads as *"the candidate never finished"*, which is the
opposite of the truth and is how one candidate was asked to apply again.

Relabelled in `frontend/src/lib/states.ts`, not renamed: the value is stored on
every application, is a Select option, and is what the pipeline's filter chips
send back as `state`. A rename is a patch plus a DocType change plus every stored
row; a label is a label. `stateLabel()` is used by the pipeline badge, the filter
chips, the candidate header and the Overview funnel, and passes every other state
through untouched.

### The Mentor Handbook goes with the consent request — 19 Nov 2026

A mentor is a stranger with no login, asked on the strength of one email to take
on a student for the length of a degree. `notifications.mentor_handbook_attachment()`
attaches the handbook to that email, and the fallback wording says it is there —
an attachment nobody is told about is an attachment nobody opens.

**Which file is site config, not code**, because the college rewrites this
document and a new edition should not need a deploy:

```bash
bench --site online.sibbc.org set-config mentor_handbook_file \
    "/private/files/SIBBCS Mentor Handbook - Guiding Holistic Formation.pdf"
```

Set on 19 Nov 2026 to a private 804 KB `File` on the site; the PDF is **not** in
the repo. Unset, or pointing at a file that has gone, it returns `[]` and the
request still goes out — a mentor can answer without the handbook, but not an
email that was never sent. The attachment is passed as `{"file_url": ...}` so the
queue resolves it at send time and the queue row stays small.

Note Frappe scans an uploaded PDF for embedded JavaScript, and pypdf refuses a
stub that merely starts with `%PDF` — so a test fixture standing in for the
handbook must not be named `.pdf`.

### The exam invitation opens the right account — 19 Nov 2026

The entrance exam is sat in **Campus LMS Lite**, and until now the invitation
sent the candidate to **Frappe**. "Set your password" was a
`/update-password?key=` link, so a candidate set a password on a portal where
they hold no roles and have nothing to read; "Go to the entrance exam" pointed at
`lms.sibbc.org` for an account they had **no way to open**. The LMS activation
link existed the whole time — `enrol_applicant` returns it — and
`create_and_send` put it in the officer's report and **never passed it to
`send_invite`**. The account could not be opened at all unless somebody noticed
the report and passed the link on by hand.

The invitation now carries the LMS activation link and says it is good for seven
days. `set_password_link` is gone, and **nothing in the app mints a Frappe
password link any more**.

**The Frappe account is still created**, silently. `conversion._create_user`
adopts it by email at onboarding, so one person keeps one login on this side too.
It carries no role and the candidate is never emailed about it.

**The LMS issues an activation link exactly once**, when it creates the account,
and it lasts 168 hours. A re-sync returns `activationUrl: null` deliberately —
issuing a second token invalidates the first, and a routine sync would break the
link somebody was about to use. So Campus LMS Lite gained
**`POST /sync/people/:externalId/activation-link`**, guarded by the service
token, and `campus_lms.reissue_activation_link()` is what the resend uses. It is
**activation only**: an account that is already active has a password, and giving
a service token the power to mint password resets for live accounts is a far
larger thing than letting it finish an onboarding nobody completed. The 422 says
so in words an officer can read, and `reissue_activation_link` passes the LMS's
own message through rather than paraphrasing it.

**Half an invitation is never sent.** With no activation link the step records
the warning and stays at *Created* rather than *Link Sent*: telling somebody to
sit an exam and giving them no way into the account it is sat under is worse than
sending nothing.

**A lapsed link is still not self-service.** Campus LMS Lite's Forgot password
serves an account that is already **active**, never one that was never opened —
so a candidate who misses the seven days needs the officer to press Resend.

### An Email Template carries its message twice — 19 Nov 2026

`Email Template` has **`response`** and **`response_html`**, the builders fill
both, and `notifications.render_template` sends **`response_html`** and falls
back to `response`. Every template on both sites has `use_html = 1`.

Two template rewrites on 19 Nov 2026 touched only `response`. Both reported
success, both left the delivered email exactly as it was, and nothing said so —
the new wording read correctly in Desk's rich-text box while the HTML box beside
it, which is the one that goes out, still held the old text. So:

- **A patch that brings a template forward must write both fields.**
  `patches/invite_names_the_lms_activation_link` and
  `patches/mentor_consent_names_the_handbook` each do, and each rewrites only a
  template still carrying the stale content, so a rewording survives.
- **`render_template` prints an unknown variable rather than refusing it.** A
  template naming a variable the code stopped passing delivers the characters
  `{{ password_link }}` to the candidate where the button should be. That is
  exactly what `lms_account_invite` would have done. `TestTheInvitationRendersWithNothingLeftOver`
  asserts no `{{` survives in a sent invitation.

### A status may not claim a fact that never happened — 20 Nov 2026

The checklist's gates say *when* a step may be completed. They never asked
whether the thing a status claims had actually happened, and for three statuses
those are different questions.

APP-2026-00013 read **Onboarded** for a day on a site with **zero Student
records**. Every gate was legitimately open — admitted, manuals acknowledged —
and somebody pressed the `Onboarded` status button, which sits on the board
immediately beside the **Onboard student** button that does the work.
`checklist.set_status` wrote the row, `derive_state` moved the application to
`Onboarded`, and nothing else happened: no Student, no Program Enrollment, no
Fee Invoice. `/staff/students` was empty and correct. The whole record of it was
one `Version` row showing two fields had changed, and the Error Log was clean,
because nothing had failed — the work was simply never asked for.

**Why it never self-corrected.** `mirror_gates_to_checklist` already derives
these statuses from their facts (`applicant_user`, `exam_link_sent_on`,
`student`) and moves the step forward when one appears. But it only ever walks
a step *forward*, deliberately — so a status claimed with no fact behind it
stands indefinitely, and the pipeline goes on saying a candidate is enrolled
while the roll says the college has no students.

`checklist.EVIDENCE` is the fix: step → status → what must exist.

```python
EVIDENCE = {
	(NO["lms_account"], "Created"):    _an_account_exists,   # applicant_user
	(NO["lms_account"], "Link Sent"):  _the_invitation_was_sent,  # exam_link_sent_on
	(NO["onboarding"], "Onboarded"):   _a_student_exists,    # student
}
```

- **Both ways in are guarded.** `set_status` covers the API and the console;
  `AdmissionApplication.validate_checklist` covers an officer editing the child
  grid in Desk and pressing Save, which goes nowhere near `set_status`. A guard
  on one path only would have been found out by the first person to use Desk.
- **The refusal names the button.** "Press *Onboard student* — it creates the
  Student, the Program Enrollment and the fee records, and records this status
  itself." An error that only says no leaves the officer where they started.
- **The board stops offering them.** `board()` returns `needs_action` per row
  and the console disables those buttons with a line saying which action
  records them. The server refusal is the boundary; this is the courtesy.
- **Only these three.** Every other status records an opinion — "Reviewed"
  means somebody read the reference and formed a view, and there is nothing to
  check it against. Asking for evidence of a judgement would make the board
  unusable. `admission_fee` "Paid" is deliberately left alone too: a Registrar
  does record cash in hand, and `conversion._fee_settled` does not trust that
  status anyway.
- **Fixtures had to become honest.** `ready_to_onboard` and two other test
  helpers set step 6 to `Link Sent` on applications that had sent nothing, and
  `demo_data` did the same — the seeder swallows a refusal, so without the
  stamp its demo candidates would silently lose step 6 and the exam pass gated
  on it. A fixture standing in the state that broke production is a fixture
  that cannot catch it.

**Samuel Sas was onboarded properly afterwards** — `SIB-2026-0002`,
`SIB-2026-0002-M.DIV.` at Level 1 in `2026-T6`, his approved scholarship
(₹1,500/month, ₹24,000 cap) copied onto the enrollment, the `Student` role
granted on his existing login, and Campus LMS Lite re-filed him from
`APP-2026-00013` to `SIB-2026-0002` so his orientation progress and exam attempt
stayed attached to him.

Two things that onboarding surfaced and nobody has decided:

- **`orientation_course_code` is still `DEMO GEST501`**, demo data purged in
  August, so `_register_orientation` defers with "not in the course catalog" for
  every student onboarded. The live catalog holds one course, `BISTO502`.
- **M.DIV. has `requires_ata_fee = 0`** on the live Program, though §2.4 and
  `conversion._raise_ata_invoice` treat the ATA fee as M.Div's. No ATA invoice is
  raised for anybody.

### The bundled `lms` app is gone — 18 Nov 2026

Phase 7 removed it: uninstalled from both sites, removed from the bench, and the 69
DocTypes and 777 rows dropped. `installed_apps` is now `frappe`, `payments`, `sibbcs`,
and `/lms` on this site is a 404.

**Everything of the college's was moved first, and verified before the uninstall:**

- 135 lessons of taught content → four **unpublished** `LEGACY-` courses in Campus LMS
  Lite (History of Christianity 86 pages, New Testament 30, Ramsem's church-history 26,
  Hermeneutics 3). Unpublished and prefixed so the registrar can never match an enrolment
  onto an archive, and so they do not compete with the courses being authored by hand.
- the orientation course and the entrance exam → `ADMISSIONS-ORIENTATION` (49 pages) and
  `ADMISSIONS-ENTRANCE-EXAM`.
- the three original entrance-exam scripts → `~/sibbcs-archive/entrance-exam-scripts-*.json`.
- the two handbook PDFs → re-attached to the `Reading Manual`.

Archives on the server, all in `~/sibbcs-archive/`: the exam scripts, the Frappe-side
teaching-layer rows (`teaching-layer-*.json`), the `Course.lms_course` /
`Course Offering.lms_batch` pairs (`lms-links-*.json`), and a full pre-uninstall database
dump kept out of the backup rotation.

So the LMS patch set, `deploy/apply-lms-patches.sh`, the
`NODE_OPTIONS=--max-old-space-size=5120` frontend build and the service-worker staleness
that went with it are all **no longer relevant**. `bench update` has nothing of ours to
discard any more.

**Two things to know if this is ever revisited.** `bench migrate` deletes a DocType whose
JSON has gone, but leaves the physical table — those are dropped separately, after
checking each is empty. And `bench remove-app` shells out to `bench` by name, so it needs
`~/.local/bin` on PATH in a non-interactive shell; it also refuses while the app is
installed on *any* site, which is why the test site had to be uninstalled first.

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
- Renaming a step is a **data change too**. `step` is a Select, so a row left holding an
  option the field no longer offers cannot be saved at all: the DocType options, `STEPS`
  and every stored row have to move together. `patches/rename_reference_steps.py` does the
  rows, matching on the old label rather than on `step_no` for the same reason the
  renumbering does. `RENAMED_LABELS` in `checklist.py` keeps the old names resolvable, so
  restoring a pre-rename backup does not leave those rows unrecognised by the renumbering.
  Done once so far: Reference 1 / 2 became **Spiritual & Ministerial Reference Review** and
  **Academic & Professional Reference Review** on 1 Sep 2026, matching what `/apply` asks
  for and what the referee's own form is titled.
- `test_step_order.py` pins the invariants — contiguous 1..n, unique keys and labels,
  defaults inside their own status list, and **no gate pointing at a later step** (which
  could never be satisfied).

**Deploy order matters.** Upload the code and run `bench migrate` together. In between,
the running code believes the new numbering while the rows still hold the old one, so any
save writes a status onto the wrong step. Nothing was saved during the window this time —
an audit of all eight live applications confirmed it — but the window is real.


### The exam and the interview reach the record — 1 Sep 2026

**The entrance exam is sat in the LMS and recorded in admissions, and nothing
joined the two.** An essay marked 20/25 in the Entrance Exam course stayed
there; `Admission Application.qualifying_exam_score` went on saying 0, and the
Assessment panel said "Not sat" for a candidate who had sat it and passed.

`admissions/entrance_exam.py` is that join, one way only: **the LMS is where
marking happens, and a `Qualifying Exam Result` is what we make of it.**

- The paper is found by quiz **title** (`Entrance Exam — Essays`), not by name,
  so a rebuilt quiz is still recognised. The candidate is found by
  `applicant_user` -- a submission by anyone else is not their exam.
- Essays map **positionally** onto `ESSAYS`; an open-ended question carries no
  key to match on. A submission without exactly three answers is reported, not
  guessed at.
- **Sat is not marked.** The LMS writes a submission the moment they press
  submit, every open-ended answer at zero. Recording that would tell the college
  they scored nothing, so `pull` refuses it and the screen says "Sat, not
  marked".
- **Marks are pulled on a schedule, not pushed.** A `doc_events` hook on
  `LMS Quiz Submission` used to carry marking into admissions on the same save.
  The exam left this system in Phase 6, so a cron every 15 minutes asks the LMS
  instead -- see "The entrance exam" above. Everything in it is best-effort: an
  admissions bookkeeping failure must never stop somebody marking a quiz.
- The pass mark is the college's (`Qualifying Exam Result.pass_mark`, currently
  **40**), never the quiz's own `passing_percentage`, which the LMS sets for its
  own purposes. Note `phase2n_exam_fields.py` once claimed 70 in its docstring
  while its constant said 40 -- the docstring was wrong and is fixed, but
  **which figure the college actually wants is still worth confirming**.

**`checklist.record_fact()` is the other half.** `set_status` is the officer's
path -- it validates and refuses to complete a step whose gates are unmet.
`record_fact` is for things that simply happened: an exam marked, an interview
held. It writes the row directly, never walks a step out of a status an officer
already recorded, and does not wait for gates -- they sat the exam and passed it
whether or not the LMS-account step was ever ticked. `QualifyingExamResult` and
`InterviewRecord` both call it from `on_update`; before this, both DocTypes
could be filled in and the checklist would not move.

**`record_interview` keeps one record per application.** The college holds one
interview; a second row is only a question about which one counts.

**The scholarship is answerable from the application now**, not only from
Finance: the card shows what the candidate wrote and their signature, the
programme cap, and Approve/Reject. The decision still goes through
`scholarship.decide`, which enforces the cap.

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

### 2.3 Formation — NOT BUILT (no `sibbcs/formation` directory at all)
The original plan called these Phase 6, which now collides with what Phase 6 actually
was (admissions moving to Campus LMS Lite); the numbers below are not a schedule.
`conversion.py:245` still carries a **deferred** `Mentor` branch that has never run —
see the gotcha about deferred branches going live silently.

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

A remainder of **less than one month** is not billed at all. The live ceilings (M.Div.
₹78,000, MACS ₹52,000) are not multiples of a ₹4,332 term, so billing used to end with an
invoice of ₹24 (M.Div.) or ₹16 (MACS). Now a student is billed ₹77,976 / ₹51,984 — whole
months only — and the unbilled ₹24 / ₹16 is simply not charged. A remainder of exactly one
month is still billed (`remaining < monthly`).

**Where an officer sees the ceiling.** The nightly job used to stop billing a student at the
ceiling and say so only in a log nobody reads; a student found out by asking where their invoice
was. Now:

- `fees.ceiling_state(ceiling, billed, monthly)` is the **one** statement of when billing stops.
  `compute_tuition` (the job), `tuition_position` (one student) and `tuition_positions`
  (everyone) all call it, so the screens cannot say something the job will not do.
- Nothing is stored. A position is computed from the non-cancelled tuition invoices on every
  call, so a cancelled or waived invoice moves it at once and it cannot go stale.
- **Finance → Tuition** (`finance_api.tuition`): every active enrolment, those at the ceiling
  first, with billed-of-ceiling, scholarship used-of-cap, and "At the ceiling only".
- **The student page's Fees card** shows the same figures for one student
  (`academic_api.student` → `tuition`).
- Both follow the permission on Fee Invoice, not the academic role: a teacher is sent
  `tuition: null` and no Fees card, because the position is money.

**When tuition is billed.** The daily job offers *every started Open/Active term*
(`fees.terms_to_bill`) to `bill_enrollment_for_term`, which is idempotent per term and
skips anyone with no registration. It used to match `start_date == today`, so a student
who registered even a day after a term began was never billed — registration runs for
weeks into a term (2026-T6: began 16 Nov, registration closes 30 Nov), so that was the
ordinary case. A late invoice falls due 14 days from **today**, not from the term's
start, so it is not overdue when it appears (`_billing_date`). A term the college has
Closed is never offered, so closing it is how billing stops.

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

**All three of its write paths were broken, and nothing said so — 19 Nov 2026.** The
gateway-neutralisation refactor reached the builder and `razorpay.py` and never reached
the schema: `ensure_doctype` leaves an existing DocType untouched, so `payment_provider`
(declared in `phase4_finance` for both Fee Invoice and Payment Entry) existed on neither,
and `Payment Entry.mode` still offered `Razorpay` while the webhook wrote `Online`. Link
generation and both settlement paths would have failed on the first real payment, *after
the money was taken*. `razorpay.py` had **no test file at all**; `test_razorpay.py` now
reads the module's own source and checks every field and Select value it writes against
the DocType metadata, so the next field renamed in the builder alone fails a test instead
of a payment. `sibbcs.patches.gateway_neutral_payment_mode` moves any stored `Razorpay`
onto `Online`, **pre_model_sync** — a Select is validated on save, so a row holding a
dropped option could never be saved again.

### Taking an application fee without a gateway — `fees.settle_application_fee`

Until 19 Nov 2026 the Razorpay webhook was the *only* thing that could settle an
application fee, so with no gateway configured an application could be submitted and then
stand in Draft for ever. `Payment Entry.student` is mandatory and an applicant is not a
Student until the conversion point, so there is no Payment Entry to write; and
`Fee Invoice.compute_totals` derives `paid_amount` from the allocation rows, so marking
the invoice Paid in Desk is undone by its own `validate`.

`settle_application_fee(application, amount=None, mode=…, reference_no=…)` records it:
mode is one of **UPI / Bank Transfer / Cash / Cheque** (`Online` is refused — that is the
gateway's word for its own rows), how and by whom goes into the invoice's remarks, and a
re-run is idempotent rather than taking the fee twice. A **part** payment leaves the gate
shut and the application in Draft, which is the honest answer. It has no UI yet: it is run
with `bench execute`, and the officer-facing button belongs on the candidate screen.

**`Fee Invoice.direct_paid_amount` is why such a payment survives.** `get_paid_amount` now
returns allocations **plus** that field. Writing `paid_amount` straight through — which
the gateway path did — left a settlement the invoice reversed the moment anybody saved it,
because an application fee has no allocation rows to recompute from. `payment_provider` is
left blank for money taken by hand, and the field says so: blank means a human recorded it.

**A waived application fee still has no route.** `Fee Invoice.status` offers `Waived` and
`set_status` makes it stick, but nothing flips `application_fee_paid` from a waiver, so a
waived candidate stays in Draft. `conversion.onboard` already treats a waived *admission*
fee as settled; the application fee has no equivalent. Not built — nobody has asked yet.

### 2.5 Output — NOT BUILT
`Degree Audit`, `Transcript` (print format), `Graduation Record`. Originally Phase 7,
which now collides with the Phase 7 that removed the bundled `lms` app.
**`completed_registrations()` is the only transcript code that exists** and nothing but
its own test calls it — so the shape of a transcript is still an open question, not a
settled one.

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
- **`zoom_time` is the start of a class, not a window.** The bundled LMS needed both ends
  and `lms_sync` added a two-hour default; that app is gone, but the field still carries
  only a start, which `agenda._weekly_sessions` expands.
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
| Apps | frappe 15.117.0, payments 0.0.1, sibbcs 0.0.1 (lms removed 18 Nov 2026) |

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

**`Student` carries `desk_access = 0`, and must keep it — 21 Nov 2026.** Frappe promotes
anybody holding a role with desk access to **System User**, whatever `user_type` the code
asked for. The role was created with the `ensure_role` default of 1, which silently
overrode the `"user_type": "Website User"` that `conversion._create_user` spells out — so
every onboarded student could open `/app`. Fixed in `phase1_academic.build` for new sites
and by `patches/students_are_not_desk_users` for this one, which demotes only users whose
roles are *nothing but* Student: a registrar who is also enrolled keeps their console.
Note that `_only_a_student()` in `academic/permissions.py` is **not** that test — it asks
whether a *teaching* role outranks Student, so a Registrar passes it.

**And `Fee Invoice` now has a query condition.** It had none, so a student listing it got
every invoice on the site, names and amounts included. The portal was never the hole; the
Desk list and the generic records API were.

**A query condition runs only after the DocType permission check**, which is worth stating
because it was got wrong here on 21 Nov 2026: Faculty were reported as "still seeing every
invoice" on the strength of the condition returning `""` for them. They see none. The
`Fee Invoice` permission table names **Accounts, Registrar, Student, System Manager** and
nobody else, so a teaching role never reaches the condition at all. Before reading a wide
condition as a hole, check whether the role can open the DocType in the first place. The
teaching roles are scoped in the condition regardless, so that adding them to that table
later — to show a tutor whether a student has paid — does not silently open it.

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
and the API. DNS: `online.sibbc.org` → `14.98.31.75`; `sibbc.org` stays on the
marketing host `216.198.79.1`. The gateway forwards 80, 443 and 2222 to `192.168.7.213`.
The host has no local firewall (ufw inactive, iptables ACCEPT).

**Still the development server**, by explicit choice — gunicorn/supervisor production mode
(`bench setup production`) has *not* been run, because it needs a sudoers drop-in for the
bench user. `bench start` runs under the `sibbcs-bench` systemd unit with
`Restart=always`, fronted by nginx. Switch before go-live: the dev server is
single-process and will not hold 200+ concurrent students.

---

## 10. Campus LMS Lite — where teaching happens

A separate application, not a Frappe app: **Node 24 / Fastify 5 / Drizzle / PostgreSQL**
with a React front end, live at **https://lms.sibbc.org**, source in
`/home/theiox/campus-lms-lite` on branch `Claude-for-online-erp`. The database is a
**Neon** instance in `us-east-2` — about **265 ms** away, which is why nothing here reads
it per-row on a page that draws a list.

Served by the same nginx. Its TLS settings **must mirror the frappe-bench block exactly**
(`ssl_protocols`, `ssl_ciphers`, `ssl_ecdh_curve`, `ssl_prefer_server_ciphers`,
`ssl_session_tickets`) and must **not** set `http2 on`: settings come from the *default
server* per listening socket, and BoringSSL (Chrome, Edge, Android) aborts on an
inconsistency with `illegal_parameter` while OpenSSL clients accept it happily. A curl or
`openssl s_client` check will pass while every browser fails — verify with a browser
engine.

Runs as the **`campus-lms`** systemd unit from `server/dist`, so a code change needs
`npm run build` *then* `sudo systemctl restart campus-lms`. Restarting before the build
finishes silently leaves the old bundle running.

### The boundary

**Frappe is the registrar; the LMS teaches.** Nothing is enrolled twice and the two never
argue about who is on a course.

- **Pushed** by `integrations/campus_lms.py`: Student, Instructor, Course Offering and
  Course Registration, as `/sync/people`, `/sync/courses`, `/sync/enrollments`. Queued
  after commit, never inline. Silent until both `campus_lms_url` and `campus_lms_token`
  are in site config.
- **Pulled**: `/sync/progress` for the orientation course, `/sync/quiz-results` for
  the entrance exam, `/sync/grades` for course results. A 404 from any of them means
  "the LMS has never heard of this person",
  which is an answer and not a fault — `_get(..., allow_missing=True)` returns None.
  Asking by application number legitimately 404s twice over: before an account exists,
  and again after conversion re-files the person under their student number.
- **A released mark comes back** through `api/lms_bridge.post_final_mark`, which calls
  `gradebook.sync_components` first and then `academic_api.save_grades`. Sending one
  bucket without syncing first would make it the *whole* set — 90 in a 60%-weighted
  bucket would land as a final 54.

  **What knocks on that door is `academic/mark_pull.py`, hourly.** Until 18 Nov 2026
  nothing did: `post_final_mark` had no caller but its own tests, and the LMS makes no
  outbound call to this system at all — so a course result released over there never
  reached a transcript, while this file said it did. If that claim ever looks true again,
  check for a caller before believing it.

  **Deciding a figure is final needs both sides, and neither has both halves.** The
  registrar says a course is *over* — the term's `end_date` has passed, or somebody
  marked the offering `Completed`; only then is anything taken. The LMS says whether
  *marking* is finished, through `awaitingMarking` and `gradedUnposted`; while either is
  above zero the pull records nothing for that student. Drop the first and week two of a
  twelve-week course records `final`, which counts unsubmitted work as zero. Drop the
  second and a half-marked course records as a fail — the entrance exam's "sat is not
  marked", wearing different clothes.

  `final` is the figure taken, not `current`: once the term is over, work never handed
  in *is* a zero. And the pull sets `status = "Completed"`, which is not decoration —
  `completed_registrations()`, the transcript, filters on it, so a graded registration
  left at `Registered` is invisible there. A fail is `Completed` too; `passed` records
  the outcome, and routing it to `Failed` would drop the F off the transcript.

  The offerings asked about are **work outstanding, not all of history**: any offering
  with an unrecorded registration, plus 120 days after a term ends for corrections. A
  plain `limit` would cut the oldest unrecorded offerings off the end of the query and
  those marks would never arrive, with nothing to say so.
- **`external_id` is the join.** A Student is `SIB-…`, an applicant is their
  `APP-…` number, and `/sync/people` takes `replacesExternalId` so conversion moves the
  key rather than making a second account. Without that it correctly *refuses* an address
  already linked.

- **Who teaches an offering travels with it — 20 Nov 2026.** The LMS reads a course's
  teachers from its *enrolments*, the same table the students are in, and until today
  nothing here wrote them: `offering_payload` carried the code, the term, the level and
  the programmes, and never the staff. So "Introduction to Old Testament"
  (`BISTO502-2026-T6`) had Ramsemz as its instructor on this side and **no teacher at
  all** on that one, which is how it was noticed. The course had been synced, the
  instructor was set, and there was simply nothing in the integration that said so.

  `campus_lms.TEACHING_ROLE` is the whole mapping: `instructor → teacher`,
  `facilitator → ta`. The registrar draws no line between the two — `SCOPE_FIELDS` in
  `academic/permissions.py` scopes an offering by either, and the staff course list says
  "A course appears here once you are named as its instructor or facilitator" — so the
  LMS's two staff roles are spent on keeping the instructor of record the one who can
  also *manage* the course. Neither is wider than the access the registrar already
  grants the same person here.

  **The enrolment is filed under the person, not the slot:**
  `MARKER-{instructor}-{offering}`, the same shape `phase6_admissions_lms` puts on the
  entrance exam. `/sync/enrollments` finds its row by `externalId` and then sets the
  role and the status on it — it never moves that row to somebody else — so an id of
  `{offering}-TEACHER` would leave the outgoing instructor teaching the course for ever
  and never let the new one in.

  **A leaver is named by the hook, not by the job.** `push` reads the offering inside
  the background job and can only see who teaches it *now*, so `on_offering_change`
  compares against `_doc_before_save` and queues the retirement while the previous
  version is still in front of it — the same reason `queue_payload` exists for
  deletions. That retirement **sends the role they held**: `/sync/enrollments` defaults
  a missing role to `student`, so leaving it out would not retire an instructor, it
  would re-file them as a student of their own course. Moving somebody between the two
  slots is not leaving — the row is theirs, so the push just rewrites its role.

  `patches/teaching_reaches_the_lms.py` is the catch-up for offerings that may never be
  saved again. An insert fires both `after_insert` and `on_update`, so everything an
  offering sends on creation is sent twice; the endpoints upsert on `externalId`, so the
  tests assert on the distinct payloads rather than the count.

- **Every door to the learning site, and where it opens — 20 Nov 2026.** There are four,
  and two of them were shut. `send_manual_row` enrolled a candidate in Campus LMS Lite
  and then, in the same letter, sent them to `/lms/courses/...` on **this** site — the
  bundled lms app, which Phase 7 removed. `/manual-reading` carried the same address, and
  so did the Open link on the old `/my-courses` page. All of them go through
  **`campus_lms.course_url(course_id=None)`** now.

  **With an id it opens the course; without one, the LMS front door — and that is a real
  answer, not a shrug.** The LMS shows a person the courses they are enrolled on and
  nothing else, so an applicant lands on their exam and their orientation. The id has to
  be the LMS's own: `/courses/:courseId` over there is validated as a UUID, so
  `BISTO502-2026-T6` opens nothing. `/sync/courses` answers with the record it wrote, and
  **`_remember_course_id` keeps that `id` on `Course Offering.lms_course_id`** — typed,
  not merely truthy, because it is another system's answer and it ends up in a link handed
  to a student. Written with `update_modified=False` and no `save`: this runs inside the
  push job, and stamping `modified` would re-fire `on_update`, which enqueues the push
  again. `patches/learn_the_lms_course_ids` re-pushes every offering so the ids are known
  for courses already running.

  `api.student._lms_links` reads them **in one query however many courses are on the
  screen**, and `session_payload` carries `lms_url` so the app shell can offer a way
  across from every page rather than only from a course row.

- **A password link nobody could open — 20 Nov 2026.** Every one this site sent carried
  `online.sibbc.org:8000`. `frappe.utils.get_url` appends `conf.http_port or
  conf.webserver_port` unless `restart_supervisor_on_update` or
  `restart_systemd_on_update` is set, and this bench is neither — it runs under its own
  `sibbcs-bench` unit. `host_name` being right does not help: the port is appended to it.

  Fixed **twice, on purpose**. On the site, with
  `bench --site online.sibbc.org set-config -p webserver_port 0` — which corrects every
  Frappe-generated address, the footer of every outgoing mail included. The key is set on
  the **site**, never on `common_site_config.json`, where bench still needs the real 8000
  to write the Procfile and the nginx upstream. And in code, in
  **`sibbcs/overrides/user.py`** via `override_doctype_class`, because a site config is
  one restored backup away from being the old one and a dead password link locks somebody
  out of their own account.

  **`_reset_password`, underscored**, is the one method all three mails pass through: the
  forgot-password form (through the module-level `reset_password(user)` function), the
  Desk **Reset Password** button, and `send_welcome_mail_to_user`. The override calls
  `super()` with `send_email=False`, corrects the host, then sends — so key generation,
  its hash and the issued-at stamp stay the base class's job.

- **Onboarding now writes to the student — 20 Nov 2026.** It wrote to nobody. A candidate
  heard from the college at nearly every step and then, at the one step that changes what
  they are, nothing: no Student number, no portal address, no password.
  `admissions/welcome.py` sends it at the end of `conversion.convert`, and never raises —
  a mail server that is down must not undo an enrolment the Registrar has accepted.

  **A link, not a password.** And a link in every case, not only for a new account: the
  Frappe User is made silently at step 6 so the candidate keeps one login for life, but
  nobody ever sets a password on it — the one they chose when they applied is Campus LMS
  Lite's. `send_welcome_email` is **0** on the User now; Frappe's generic mail would
  otherwise arrive alongside ours with a second password link that invalidates the first.

- **Students are told when a course opens — 20 Nov 2026.** Registration was a pull: sign
  in, open Register, find out — inside a window a fortnight wide.
  `academic/offer_notice.py` pushes it, at the level the college asked about.

  **Who is asked is `eligibility.evaluate`, not a level comparison** — the same engine the
  Register page runs, so the letter can never point at a course the page will then refuse.
  Two filters come first and both are real: the roll is scoped to the programmes the
  course counts toward (an empty `Course.programs` is universal, as everywhere else), and
  `check_level` runs as a pure function with no queries. Without them the nightly sweep
  evaluates the whole college against every course, at six queries a pair.

  **`students_notified_on` is the whole of the idempotency**, and it is stamped even when
  nobody was eligible: "nobody yet" is an answer, and a sweep that retried it would ask
  the same question every morning until the term closed. A term whose registration has
  not opened is the one case left unstamped, so the daily
  `offer_notice.announce_open_offerings` finds it again when it does. Clearing the field,
  or `announce_now(offering, force=True)`, is how to say it again.

  One letter per offering, not a digest. If publishing a whole catalogue in an afternoon
  turns out to be noisy, the grouping belongs in `announce_open_offerings`, which already
  has every offering in hand.

**An offering taught there must be graded as one bucket.** `gradebook.use_single_component`
puts it on a single **Coursework** component worth 100%, because `compute_grade` holds the
letter back until *every* bucket is marked — so with several buckets one release can never
finish a transcript. Both offerings on the live site are now in that shape —
`0507-2026-T1` was the 6-bucket one and `DEMO BIST502-DEMO-TERM-B` went with the demo
data. A new offering taught in the LMS needs `use_single_component` before anyone is
marked on it, and `lms_bridge.post_final_mark` *refuses* a release against an offering
with no scheme at all rather than guessing a bucket.

### Things that cost time

- **Applicants are isolated by enrolment, not by a permission.** `GET /courses` forces
  `scope: "mine"` for anyone who is not an admin, and there is no self-signup — so an
  applicant enrolled only in the admissions courses sees only those. Verified on a trial
  candidate: 2 of 6 courses.
- **An unpublished page is dropped from the student view entirely**, items and all, so the
  exam's marking rubric neither shows nor counts: the course reports `required: 2` where
  the module holds three items.
- **`Referrer-Policy: no-referrer`** — helmet's default — breaks YouTube and Vimeo embeds
  with "Video unavailable" (Error 153). Set to `strict-origin-when-cross-origin`.
- **The importer keys a page on (course, title)**, so two lessons sharing a title land on
  one page and the second overwrites the first, silently. `_course_export` numbers repeats
  and reports what it numbered.
- **PGlite is single-process**: the local CLI cannot run while the dev server is up. Tests
  use `pglite:memory`, never Neon.
- **No SMTP.** The LMS sends nothing; `/sync/people` returns an `activationUrl` on
  creation and Frappe emails it.

### Service tokens

`npm run create-service-token` prints the token once and stores only its SHA-256. A token
authenticates as a *service*, not a person, and deliberately **cannot author pages or
quizzes** — that is session-only, so the Phase 6/7 content migration had to export from
Frappe and import through the LMS's own CLI rather than widening the token.
