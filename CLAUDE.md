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

### 2.1 Admissions — Phase 2, not built
`Lead`, `Admission Application` (+ `Application Document`, `Reference Request`,
`Mentor Consent`), `Scholarship Request`, `Qualifying Exam Result`, `Interview Record`.

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

Phase 3 adds `Student`, `Program Enrollment`, `Course Registration` (+ `Grade Component`),
`Level Promotion`.

### 2.3 Formation — Phase 6, not built
`Mentor`, `Mentor Monthly Report`, `Chapel Session` + `Chapel Attendance`,
`Internship Record` (+ `Internship Log Entry`), `Campus Visit` + `Campus Visit Attendance`.

### 2.4 Finance — Phase 4, not built
`Fee Type`, `Fee Invoice`, `Payment Entry` (+ `Payment Allocation`).
`Student Fee Ledger` is a **report, not a DocType**.

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
- Definition cycles (`Course` ↔ `Course Prerequisite`) need a two-pass build: create the
  parent, then the child, then extend the parent. See `setup/schema.add_fields`.

## 5. Layout and conventions

```
sibbcs/
  academic/doctype/<snake_case>/    DocType JSON (source of truth) + .py + test_*.py
  setup/schema.py                   helpers for declaring DocTypes in code
  setup/phase1_academic.py          idempotent Phase 1 DocType builder
  setup/phase1_seed.py              programs, terms, course CSV importer
  setup/data/courses_template.csv   catalog import template
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

**Port 443 is not configured yet** — no TLS certificate. Blocked on inbound 80/443
reaching this host (see §9).

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

## 9. Public access — not yet working

`online.sibbc.org` resolves to `14.98.31.75` (correct). `sibbc.org` stays on the
marketing host, `216.198.79.1`.

From the internet, **only 2222 is reachable**; 80 and 443 are not. The host itself has no
firewall (ufw inactive, iptables ACCEPT) and nginx does listen on 80, so the block is
upstream of the VM — the NAT gateway `192.168.4.100` does not forward 80/443 to
`192.168.7.213`, and/or the ISP blocks inbound web ports on this connection.

Consequences until that is fixed:
- Nobody outside the LAN can reach the site; use an SSH tunnel
  (`ssh -L 8080:127.0.0.1:80 -p 2222 theiox@14.98.31.75`).
- **Let's Encrypt HTTP-01 cannot validate**, so TLS/443 cannot be completed. If the ISP
  blocks 80 permanently, use DNS-01 validation instead — but note the site still needs
  inbound 443 to be usable at all.

Production mode (`bench setup production`: gunicorn + workers under supervisor, replacing
the `sibbcs-bench` dev unit) has deliberately **not** been run. It needs a sudoers
drop-in for the bench user — an explicit decision, not a default.
