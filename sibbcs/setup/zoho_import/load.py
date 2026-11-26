# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Write an extract into the ERP. Quietly, re-runnably, and reversibly.

    cd ~/frappe-bench/sites
    ../env/bin/python -P -m sibbcs.setup.zoho_import.load <site> [date] [--stages a,b] [--dry-run]
    ../env/bin/python -P -m sibbcs.setup.zoho_import.load <site> [date] --purge

**Re-runnable.** Every record written carries `legacy_source`: `zoho:<id>` for
one this created, `zoho:<id>:matched` for one that already existed here and was
recognised (a course, a term, an offering). A second run finds them and updates
in place, so a run that stops half-way is finished by running it again, and
marks the office enters in Zoho afterwards arrive by re-extracting and
re-loading.

**Quiet.** Everything runs inside `quiet()`: no LMS push, no mail, no fee.

**Reversible.** `--purge` deletes what the import created, newest first, and
clears the mark from what it only matched. It refuses if anybody has since
built on an imported record (a new registration on an imported student, say).

The stages, in order, each committed on its own:

  programmes   the programmes Zoho has and this ERP lacks (GDCS)
  courses      from review/courses_reviewed.csv -- the college's corrected copy
  terms        Zoho's terms; past and current ones Closed
  instructors  faculty and facilitators
  offerings    every run of a course in a term
  students     Student, a portal User (no mail), and the Program Enrollment
  history      one Course Registration per Zoho grade row
  balances     from review/opening_balances_filled.csv
  files        each student's documents, as private files on their record
  progress     credits and CGPA recomputed
"""

import csv
import os
import re
import sys
from collections import Counter, defaultdict

import frappe
from frappe.utils import cint, flt, getdate, today

from sibbcs.setup.zoho_import import quiet
from sibbcs.setup.zoho_import.extract import EXPORT_ROOT
from sibbcs.setup.zoho_import.review import (
	PROGRAMMES,
	course_code,
	display,
	load as load_records,
	ref_id,
	term_name,
	term_status,
	zoho_date,
)

STAGES = (
	"programmes", "courses", "terms", "instructors", "offerings",
	"students", "history", "balances", "files", "progress",
)

NEW_PROGRAMMES = {
	"GDCS": {
		"program_name": "Graduate Diploma in Christian Studies",
		"monthly_tuition": 1500,
		"tuition_total": 26000,
		"total_credits": 33,
		"total_courses": 12,
	},
}

STUDENT_STATUS = {
	"Active": "Active",
	"On Break": "On Leave",
	"Awaiting Graduation": "Active",
	"Awaiting Decision": "Active",
	"Graduated": "Graduated",
	"Withdrawn": "Withdrawn",
	"Suspended": "Dismissed",
	"Inactive": "On Leave",
}
ENROLLMENT_STATUS = {"Graduated": "Completed", "On Break": "On Leave", "Suspended": "Dismissed"}

# Zoho never recorded how a course was delivered. Pre-Recorded is the one format
# that needs no schedule (Zoom Live refuses to save without its weekdays); the
# Registrar sets the real one on an upcoming offering before publishing it.
DEFAULT_FORMAT = "Pre-Recorded"
TERM_MONTHS = 2


def created(zoho_id):
	return f"zoho:{zoho_id}"


def matched(zoho_id):
	return f"zoho:{zoho_id}:matched"


def find(doctype, zoho_id):
	return frappe.db.get_value(
		doctype, {"legacy_source": ("in", (created(zoho_id), matched(zoho_id)))}, "name"
	)


class Context:
	def __init__(self, folder):
		self.folder = folder
		self.records = load_records(folder)
		self.report = defaultdict(Counter)
		self.problems = []
		self._maps = {}

	def note(self, stage, outcome):
		self.report[stage][outcome] += 1

	def problem(self, stage, zoho_id, text):
		self.problems.append((stage, zoho_id, text))
		self.note(stage, "problem")

	def rows(self, name):
		return self.records.get(name) or []

	@property
	def onboarded(self):
		return [s for s in self.rows("students") if s.get("Onboarding_Status") == "Onboarded"]

	def sheet(self, name):
		path = os.path.join(self.folder, "review", name)
		if not os.path.exists(path):
			return None
		with open(path, newline="", encoding="utf-8-sig") as handle:
			return list(csv.DictReader(handle))


def upsert(doctype, zoho_id, values, existing=None, keep=()):
	"""Create, or update in place. `existing` is the name of a record that was
	here before the import; it is marked matched, and the fields in `keep` are
	never overwritten on it."""
	name = find(doctype, zoho_id)
	if not name and existing and frappe.db.exists(doctype, existing):
		name = existing
		frappe.db.set_value(doctype, name, "legacy_source", matched(zoho_id), update_modified=False)

	if not name:
		doc = frappe.get_doc({"doctype": doctype, "legacy_source": created(zoho_id), **values})
		doc.insert(ignore_permissions=True)
		return doc, "created"

	doc = frappe.get_doc(doctype, name)
	protected = keep if (doc.legacy_source or "").endswith(":matched") else ()
	changed = False
	for field, value in values.items():
		if field in protected:
			continue
		if isinstance(value, list):
			continue  # child tables are set on creation only
		if str(doc.get(field) or "") != str(value or ""):
			doc.set(field, value)
			changed = True
	if changed:
		doc.save(ignore_permissions=True)
	return doc, "updated" if changed else "unchanged"


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------


def stage_programmes(ctx):
	for abbr, values in NEW_PROGRAMMES.items():
		if frappe.db.exists("Program", abbr):
			ctx.note("programmes", "unchanged")
			continue
		frappe.get_doc({"doctype": "Program", "abbr": abbr, **values}).insert(ignore_permissions=True)
		ctx.note("programmes", "created")


def _course_map(ctx):
	"""Zoho course id -> course code here."""
	if "courses" not in ctx._maps:
		ctx._maps["courses"] = {
			row["ID"]: course_code(row.get("course_code")) for row in ctx.rows("courses")
		}
	return ctx._maps["courses"]


def stage_courses(ctx):
	sheet = ctx.sheet("courses_reviewed.csv")
	if sheet is None:
		ctx.problem("courses", "-", "review/courses_reviewed.csv is missing: the college's corrected course sheet")
		return
	for row in sheet:
		level = (row.get("level") or row.get("level (PROPOSED - confirm)") or "").strip()
		kind = (row.get("course_type") or row.get("course_type (PROPOSED - confirm)") or "Core").strip()
		code = row["course_code"].strip().upper()
		programmes = [p.strip() for p in (row.get("programs") or "").split(";") if p.strip()]
		values = {
			"course_code": code,
			"course_title": row["course_title"].strip(),
			"credits": flt(row.get("credits")) or 3,
			"level": level,
			"course_type": kind,
			"department": row["department"].strip().upper(),
			"is_active": 1,
			"programs": [{"program": p} for p in programmes if frappe.db.exists("Program", p)],
		}
		try:
			_doc, outcome = upsert("Course", row["zoho_id"], values, existing=code)
			ctx.note("courses", outcome)
		except Exception as exc:
			ctx.problem("courses", row["zoho_id"], f"{code}: {exc}")


def _term_map(ctx):
	"""Zoho term id -> term name here."""
	if "terms" not in ctx._maps:
		ctx._maps["terms"] = {
			row["ID"]: term_name(f"{row.get('Term')} {row.get('Academic_Year')}") for row in ctx.rows("terms")
		}
	return ctx._maps["terms"]


def stage_terms(ctx):
	now = getdate(today())
	for row in ctx.rows("terms"):
		name = term_name(f"{row.get('Term')} {row.get('Academic_Year')}")
		start, end = zoho_date(row.get("Start_Date")), zoho_date(row.get("End_Date"))
		values = {
			"term_name": name,
			"start_date": start,
			"end_date": end,
			"status": term_status(row.get("Status"), end, now),
			"duration_months": TERM_MONTHS,
		}
		try:
			# A term already here keeps its status and length: it may already
			# carry registrations and invoices. The dates follow Zoho, which the
			# college confirmed is the calendar (26 Nov 2026).
			_doc, outcome = upsert(
				"Academic Term", row["ID"], values, existing=name, keep=("status", "duration_months")
			)
			ctx.note("terms", outcome)
		except Exception as exc:
			ctx.problem("terms", row["ID"], f"{name}: {exc}")


def _instructor_map(ctx):
	if "instructors" not in ctx._maps:
		ctx._maps["instructors"] = {
			row["ID"]: find("Instructor", row["ID"]) for row in ctx.rows("faculty")
		}
	return ctx._maps["instructors"]


def stage_instructors(ctx):
	courses = _course_map(ctx)
	for row in ctx.rows("faculty"):
		qualified = [courses.get(ref_id(c)) for c in row.get("courses") or []]
		values = {
			"full_name": (row.get("facilitator_name") or "").strip(),
			"is_facilitator": 1 if row.get("Role") == "Facilitator" else 0,
			"is_active": 1,
			"courses_qualified": [
				{"course": c} for c in qualified if c and frappe.db.exists("Course", c)
			],
		}
		if not values["full_name"]:
			ctx.problem("instructors", row["ID"], "no name")
			continue
		try:
			_doc, outcome = upsert("Instructor", row["ID"], values)
			ctx.note("instructors", outcome)
		except Exception as exc:
			ctx.problem("instructors", row["ID"], str(exc))
	ctx._maps.pop("instructors", None)


def _offering_status(zoho_status, term):
	if frappe.db.get_value("Academic Term", term, "status") == "Closed":
		return "Completed"
	return "Draft" if zoho_status == "Upcoming" else "Running"


def stage_offerings(ctx):
	courses, terms, instructors = _course_map(ctx), _term_map(ctx), _instructor_map(ctx)
	for row in ctx.rows("offerings"):
		course = courses.get(ref_id((row.get("Course") or [{}])[0]))
		term = terms.get(ref_id(row.get("Term")))
		if not (course and term and frappe.db.exists("Course", course) and frappe.db.exists("Academic Term", term)):
			ctx.problem("offerings", row["ID"], f"course {course} or term {term} is not here")
			continue
		teacher = (row.get("facilitator_name1") or [{}])[0]
		facilitator = (row.get("facilitator_name") or [{}])[0]
		values = {
			"course": course,
			"term": term,
			"status": _offering_status(row.get("status"), term),
			"format": DEFAULT_FORMAT,
			"instructor": instructors.get(ref_id(teacher)) or None,
			"facilitator": instructors.get(ref_id(facilitator)) or None,
		}
		try:
			# One already here (published for registration) keeps its status.
			_doc, outcome = upsert(
				"Course Offering", row["ID"], values, existing=f"{course}-{term}", keep=("status", "format")
			)
			ctx.note("offerings", outcome)
		except Exception as exc:
			ctx.problem("offerings", row["ID"], f"{course}-{term}: {exc}")


def _user_for(email, full_name):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": full_name,
				"user_type": "Website User",
				# Invitations go out later, as their own step, when the college
				# chooses -- not a hundred at once in the middle of an import.
				"send_welcome_email": 0,
			}
		)
		user.flags.ignore_permissions = True
		user.insert(ignore_permissions=True)
	if not any(r.role == "Student" for r in user.roles):
		user.append("roles", {"role": "Student"})
		user.save(ignore_permissions=True)
	return user.name


def _enrollment_date(row, terms_by_label):
	for text in (row.get("admission_date"), row.get("application_received_date")):
		if text:
			try:
				return zoho_date(text)
			except ValueError:
				pass
	term = terms_by_label.get(term_name(row.get("onboarding_term") or ""))
	return term or getdate(today())


def stage_students(ctx):
	starts = {name: start for name, start in frappe.get_all("Academic Term", fields=["name", "start_date"], as_list=True)}
	for row in ctx.onboarded:
		zoho_id = row["ID"]
		programme = PROGRAMMES.get(row.get("program_enrolled"))
		if not programme or not frappe.db.exists("Program", programme):
			ctx.problem("students", zoho_id, f"no programme here for {row.get('program_enrolled')}")
			continue
		email = (row.get("email") or "").strip().lower()
		full_name = display(row.get("full_name")).strip()
		frappe.db.savepoint("zoho_student")
		try:
			existing = frappe.db.get_value("Student", {"email": email}, "name") if email else None
			student, outcome = upsert(
				"Student",
				zoho_id,
				{
					"full_name": full_name,
					"dob": zoho_date(row.get("date_of_birth")) if row.get("date_of_birth") else None,
					"gender": row.get("gender") if row.get("gender") in ("Male", "Female") else None,
					"mobile": (row.get("phone") or "").strip() or None,
					"email": email or None,
					"address": display(row.get("address")) or None,
					"status": STUDENT_STATUS.get(row.get("enrollment_status"), "Active"),
				},
				existing=existing,
				keep=("full_name", "dob", "gender", "mobile", "address", "status"),
			)
			if email and not student.user:
				student.db_set("user", _user_for(email, full_name), update_modified=False)

			start_term = term_name(row.get("onboarding_term") or "")
			level = re.sub(r"\D", "", row.get("current_level") or "") or "1"
			upsert(
				"Program Enrollment",
				zoho_id,
				{
					"student": student.name,
					"program": programme,
					"status": ENROLLMENT_STATUS.get(row.get("enrollment_status"), "Active"),
					"enrollment_date": _enrollment_date(row, starts),
					"start_term": start_term if start_term and frappe.db.exists("Academic Term", start_term) else None,
					"current_level": level,
				},
				existing=frappe.db.get_value("Program Enrollment", {"student": student.name, "program": programme}, "name"),
				keep=("current_level", "status", "enrollment_date", "start_term"),
			)
			ctx.note("students", outcome)
		except Exception as exc:
			frappe.db.rollback(save_point="zoho_student")
			ctx.problem("students", zoho_id, str(exc)[:300])


def stage_history(ctx):
	"""One Course Registration per Zoho grade row, for onboarded students.

	A Pass or Fail is Completed (a fail is Completed with passed=0, the
	convention `mark_pull` follows, so the F stays on the transcript). No mark
	yet is Active: it is filled in when the office finishes the grading in Zoho
	and the import runs again.
	"""
	onboarded = {s["ID"] for s in ctx.onboarded}
	offerings = {row["ID"]: find("Course Offering", row["ID"]) for row in ctx.rows("offerings")}
	enrollments = {}
	levels = dict(frappe.get_all("Course", fields=["name", "level"], as_list=True))
	starts = dict(frappe.get_all("Academic Term", fields=["name", "start_date"], as_list=True))

	for row in ctx.rows("grades"):
		student = ref_id(row.get("Student"))
		if student not in onboarded:
			ctx.note("history", "skipped: not an onboarded student" if student else "skipped: no student")
			continue
		if student not in enrollments:
			enrollments[student] = find("Program Enrollment", student)
		enrollment = enrollments[student]
		offering = offerings.get(ref_id(row.get("Course_Name")))
		if not (enrollment and offering):
			ctx.problem("history", row["ID"], "student or offering was not loaded")
			continue

		course, term = frappe.db.get_value("Course Offering", offering, ["course", "term"])
		outcome = row.get("Status")
		values = {
			"program_enrollment": enrollment,
			"course_offering": offering,
			"registration_date": starts.get(term) or today(),
			"status": "Completed" if outcome in ("Pass", "Fail") else "Active",
			"passed": 1 if outcome == "Pass" else 0,
			"final_marks": flt(row.get("Marks")) if row.get("Marks") not in (None, "") else None,
			# Zoho kept no record of the student's level when they took it. The
			# course's own level is the honest stand-in: it is what the
			# promotion count should credit the course to.
			"level_at_registration": levels.get(course),
		}
		frappe.db.savepoint("zoho_grade")
		try:
			_doc, result = upsert("Course Registration", row["ID"], values)
			ctx.note("history", result)
		except Exception as exc:
			frappe.db.rollback(save_point="zoho_grade")
			ctx.problem("history", row["ID"], str(exc)[:300])


def stage_balances(ctx):
	sheet = ctx.sheet("opening_balances_filled.csv")
	if sheet is None:
		ctx.problem("balances", "-", "review/opening_balances_filled.csv is missing: the office's filled sheet")
		return
	for row in sheet:
		zoho_id = (row.get("zoho_id") or "").strip()
		enrollment = find("Program Enrollment", zoho_id)
		if not enrollment:
			ctx.problem("balances", zoho_id, "no enrollment loaded for this student")
			continue
		billed = flt(row.get("tuition_billed_before_erp"))
		paid = flt(row.get("tuition_paid_before_erp"))
		covered = (row.get("term_6_2026_tuition_covered (Y/N)") or "").strip().upper().startswith("Y")
		if paid > billed:
			ctx.problem("balances", zoho_id, f"paid {paid} is more than billed {billed}; enter the difference as credit by hand")
			paid = billed
		student = frappe.db.get_value("Program Enrollment", enrollment, "student")
		try:
			if billed > 0:
				upsert(
					"Fee Invoice",
					f"opening:{zoho_id}",
					{
						"student": student,
						"program_enrollment": enrollment,
						"fee_type": "Monthly Tuition",
						# Named for Term 6 only when Term 6 is paid for: the
						# tuition job will not bill a term twice.
						"term": "2026-T6" if covered and frappe.db.exists("Academic Term", "2026-T6") else None,
						"gross_amount": billed,
						"discount_amount": 0,
						"direct_paid_amount": paid,
						"due_date": today(),
						"remarks": "Opening balance: tuition billed and paid before the ERP (from Zoho / the office's records).",
					},
				)
				ctx.note("balances", "opening invoice")
			scholarship = {
				"scholarship_total_cap": flt(row.get("scholarship_total_cap")),
				"scholarship_monthly_discount": flt(row.get("scholarship_monthly_discount")),
				"scholarship_used_to_date": flt(row.get("scholarship_used_to_date")),
			}
			if any(scholarship.values()):
				frappe.db.set_value("Program Enrollment", enrollment, scholarship, update_modified=False)
				ctx.note("balances", "scholarship")
			if flt(row.get("other_amount_outstanding")) > 0:
				ctx.problem("balances", zoho_id, f"other amount outstanding {row.get('other_amount_outstanding')}: enter by hand ({row.get('notes') or 'no note'})")
		except Exception as exc:
			ctx.problem("balances", zoho_id, str(exc)[:300])


def _label(field):
	text = re.sub(r"^Upload_", "", field).replace("_", " ").strip()
	return {"photo": "Photo", "Student Signature": "Signature"}.get(text, text)


def stage_files(ctx):
	import json

	path = os.path.join(ctx.folder, "manifest.json")
	if not os.path.exists(path):
		ctx.problem("files", "-", "manifest.json is missing: extract was run with --no-files")
		return
	with open(path) as handle:
		manifest = [e for e in json.load(handle) if "sha256" in e]

	# Resubmitted documents name the student by email only.
	by_email = {(s.get("email") or "").strip().lower(): s["ID"] for s in ctx.onboarded}
	document_owner = {}
	for row in ctx.rows("documents"):
		for key, value in row.items():
			if "mail" in key.lower() and isinstance(value, str) and value.strip().lower() in by_email:
				document_owner[row["ID"]] = by_email[value.strip().lower()]

	for entry in manifest:
		zoho_student = entry["record_id"] if entry["report"] == "students_Report" else document_owner.get(entry["record_id"])
		student = find("Student", zoho_student) if zoho_student else None
		if not student:
			ctx.problem("files", entry["record_id"], f"{entry['field']}: no student loaded for it")
			continue
		file_name = f"{_label(entry['field'])} - {os.path.basename(entry['path'])}"
		if frappe.db.exists("File", {"attached_to_doctype": "Student", "attached_to_name": student, "content_hash": _md5(ctx, entry)}):
			ctx.note("files", "unchanged")
			continue
		with open(os.path.join(ctx.folder, entry["path"]), "rb") as handle:
			content = handle.read()
		try:
			doc = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": file_name,
					"attached_to_doctype": "Student",
					"attached_to_name": student,
					"is_private": 1,
					"content": content,
				}
			).insert(ignore_permissions=True)
			if entry["field"] == "photo":
				frappe.db.set_value("Student", student, "photo", doc.file_url, update_modified=False)
			ctx.note("files", "attached")
		except Exception as exc:
			ctx.problem("files", entry["record_id"], f"{entry['field']}: {str(exc)[:200]}")


def _md5(ctx, entry):
	import hashlib

	with open(os.path.join(ctx.folder, entry["path"]), "rb") as handle:
		return hashlib.md5(handle.read()).hexdigest()


def stage_progress(ctx):
	from sibbcs.academic.doctype.course_registration.course_registration import refresh_enrollment_progress

	for name in frappe.get_all("Program Enrollment", filters={"legacy_source": ("like", "zoho:%")}, pluck="name"):
		refresh_enrollment_progress(name)
		ctx.note("progress", "refreshed")


STAGE_FUNCTIONS = {name: globals()[f"stage_{name}"] for name in STAGES}


# ---------------------------------------------------------------------------
# reconciliation and purge
# ---------------------------------------------------------------------------


def reconcile(ctx):
	"""Per student, what Zoho says against what is now here."""
	rows = []
	zoho_passed = Counter(
		ref_id(g.get("Student")) for g in ctx.rows("grades") if g.get("Status") == "Pass"
	)
	files_expected = Counter(e["record_id"] for e in _manifest(ctx) if e.get("report") == "students_Report")
	for s in ctx.onboarded:
		enrollment = find("Program Enrollment", s["ID"])
		student = find("Student", s["ID"])
		here_passed = frappe.db.count(
			"Course Registration", {"program_enrollment": enrollment, "status": "Completed", "passed": 1}
		) if enrollment else 0
		level = frappe.db.get_value("Program Enrollment", enrollment, "current_level") if enrollment else ""
		attached = frappe.db.count("File", {"attached_to_doctype": "Student", "attached_to_name": student}) if student else 0
		rows.append(
			[s["ID"], student or "", enrollment or "", zoho_passed.get(s["ID"], 0), here_passed,
			 re.sub(r"\D", "", s.get("current_level") or ""), level or "", files_expected.get(s["ID"], 0), attached]
		)
	path = os.path.join(ctx.folder, "review", "reconciliation.csv")
	with open(path, "w", newline="", encoding="utf-8") as handle:
		writer = csv.writer(handle)
		writer.writerow(["zoho_id", "student", "enrollment", "zoho_passed", "passed_here",
		                 "zoho_level", "level_here", "zoho_files", "files_here"])
		writer.writerows(rows)
	mismatched = [r for r in rows if not r[1] or r[3] != r[4] or r[5] != r[6] or r[7] > r[8]]
	return {"students": len(rows), "loaded": sum(1 for r in rows if r[1]), "mismatched": len(mismatched)}


def _manifest(ctx):
	import json

	path = os.path.join(ctx.folder, "manifest.json")
	if not os.path.exists(path):
		return []
	with open(path) as handle:
		return [e for e in json.load(handle) if "sha256" in e]


PURGE_ORDER = (
	"Fee Invoice", "Course Registration", "Program Enrollment", "Student",
	"Course Offering", "Instructor", "Academic Term", "Course",
)


def purge():
	"""Undo the import: delete what it created, unmark what it matched.

	Refuses when anything not from the import now points at an imported
	student (a registration or invoice raised in the ERP since), because
	deleting under it would lose real work.
	"""
	imported_students = frappe.get_all("Student", filters={"legacy_source": ("like", "zoho:%")}, pluck="name")
	if imported_students:
		for doctype in ("Course Registration", "Fee Invoice"):
			newer = frappe.get_all(
				doctype,
				filters={"student": ("in", imported_students), "legacy_source": ("in", ("", None))},
				pluck="name",
				limit=5,
			)
			if newer:
				frappe.throw(f"Not purging: {doctype} {', '.join(newer)} was created since, on an imported student.")

	counts = Counter()
	with quiet():
		for name in imported_students:
			for file in frappe.get_all("File", filters={"attached_to_doctype": "Student", "attached_to_name": name}, pluck="name"):
				frappe.delete_doc("File", file, ignore_permissions=True, force=True)
				counts["File"] += 1
		for doctype in PURGE_ORDER:
			for name in frappe.get_all(
				doctype, filters={"legacy_source": ("like", "zoho:%")}, fields=["name", "legacy_source"], as_list=True
			):
				record, source = name
				if source.endswith(":matched"):
					frappe.db.set_value(doctype, record, "legacy_source", None, update_modified=False)
					counts[f"{doctype} unmarked"] += 1
				else:
					frappe.delete_doc(doctype, record, ignore_permissions=True, force=True)
					counts[doctype] += 1
		if frappe.db.exists("Program", "GDCS") and not frappe.db.exists("Program Enrollment", {"program": "GDCS"}):
			frappe.delete_doc("Program", "GDCS", ignore_permissions=True, force=True)
			counts["Program"] += 1
	return dict(counts)


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------


def run(folder, stages=STAGES, dry_run=False, commit=True):
	ctx = Context(folder)
	mail_before = frappe.db.count("Email Queue")
	with quiet():
		for stage in stages:
			if dry_run and stage == "files":
				continue
			STAGE_FUNCTIONS[stage](ctx)
			if commit and not dry_run:
				frappe.db.commit()
	if dry_run:
		frappe.db.rollback()
	summary = {stage: dict(ctx.report[stage]) for stage in stages if stage in ctx.report}
	summary["mail_queued_during_load"] = frappe.db.count("Email Queue") - mail_before
	if not dry_run:
		summary["reconciliation"] = reconcile(ctx)
	if ctx.problems:
		path = os.path.join(folder, "review", "load_problems.csv")
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "w", newline="", encoding="utf-8") as handle:
			csv.writer(handle).writerows([("stage", "zoho_id", "problem"), *ctx.problems])
		summary["problems"] = len(ctx.problems)
	return summary


def main(argv):
	import json

	site = argv[0]
	rest = argv[1:]
	day = next((a for a in rest if re.match(r"\d{4}-\d\d-\d\d$", a)), None) or sorted(os.listdir(EXPORT_ROOT))[-1]
	folder = os.path.join(EXPORT_ROOT, day)
	stages = STAGES
	if "--stages" in rest:
		stages = tuple(rest[rest.index("--stages") + 1].split(","))
		unknown = set(stages) - set(STAGES)
		if unknown:
			sys.exit(f"Unknown stages: {', '.join(sorted(unknown))}")

	frappe.init(site=site, sites_path=".")
	frappe.connect()
	frappe.set_user("Administrator")
	try:
		if "--purge" in rest:
			result = purge()
			frappe.db.commit()
		else:
			result = run(folder, stages, dry_run="--dry-run" in rest)
		print(json.dumps(result, indent=1, default=str))
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main(sys.argv[1:])
