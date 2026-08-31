# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Read endpoints for the student portal.

Thin on purpose. The rules live in `academic/portal.py` and `academic/
eligibility.py`; this module composes what one screen needs into one response
so the browser does not make five calls to draw a page.

Everything is scoped to the logged-in student. None of these take a student or
enrollment argument -- there is no parameter here through which one student
could read another's record.
"""

import base64

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from sibbcs.academic.eligibility import explain
from sibbcs.academic.portal import available_offerings, get_enrollment, my_registrations

ENROLLMENT_FIELDS = (
	"student",
	"student_name",
	"program",
	"current_level",
	"credits_earned",
	"cgpa",
	"status",
	"expected_completion",
)

# A student may correct how the college reaches them. Their legal name, date of
# birth, gender and email are the Registrar's record of who they are, and are
# not editable from here -- changing them is an office procedure, not a form.
EDITABLE_PROFILE_FIELDS = ("mobile", "whatsapp", "address")

SETTLED_FEE_STATES = ("Paid", "Waived", "Cancelled")
LIVE_REGISTRATION_STATES = ("Registered", "Active")


def _require_enrollment():
	"""The caller's active enrollment, or None.

	A logged-in applicant with no enrollment yet is an ordinary state, not an
	error -- the portal explains it rather than showing a stack trace.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)

	return get_enrollment()


def _enrollment_header(enrollment):
	fields = [f for f in ENROLLMENT_FIELDS if frappe.db.has_column("Program Enrollment", f)]
	row = frappe.db.get_value("Program Enrollment", enrollment, fields, as_dict=True) or {}
	row["name"] = enrollment
	# Program Enrollment stores the code; the student knows the programme by its
	# name, so resolve it here rather than showing "MDIV" on every screen.
	row["program_name"] = (
		frappe.db.get_value("Program", row.get("program"), "program_name") or row.get("program")
	)
	return row


def _lms_links(registrations):
	"""Where each registration's course lives in the LMS, and how far along.

	The portal deliberately does not render lessons -- it links out to the LMS
	course player, which already runs quizzes, assignments and progress.
	Course.lms_course is written by `lms_sync.ensure_lms_course`.
	"""
	courses = {row["course"] for row in registrations if row.get("course")}
	if not courses:
		return

	lms_course_by_course = {
		row.name: row.lms_course
		for row in frappe.get_all(
			"Course",
			filters={"name": ("in", list(courses))},
			fields=["name", "lms_course"],
		)
		if row.lms_course
	}

	progress_by_course = {}
	if lms_course_by_course:
		for row in frappe.get_all(
			"LMS Enrollment",
			filters={
				"member": frappe.session.user,
				"course": ("in", list(lms_course_by_course.values())),
			},
			fields=["course", "progress"],
		):
			progress_by_course[row.course] = row.progress or 0

	for row in registrations:
		lms_course = lms_course_by_course.get(row.get("course"))
		row["lms_course"] = lms_course or None
		row["lms_url"] = f"/lms/courses/{lms_course}" if lms_course else None
		row["progress"] = progress_by_course.get(lms_course, 0) if lms_course else 0


@frappe.whitelist()
def my_courses():
	"""Everything the My Courses screen draws, in one call."""
	enrollment = _require_enrollment()
	if not enrollment:
		return {"enrollment": None, "registrations": []}

	registrations = my_registrations(enrollment)
	_lms_links(registrations)

	return {
		"enrollment": _enrollment_header(enrollment),
		"registrations": registrations,
	}


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------


def _open_fees(student):
	"""Unsettled invoices, soonest due first."""
	rows = frappe.get_all(
		"Fee Invoice",
		filters={"student": student, "status": ("not in", SETTLED_FEE_STATES)},
		fields=[
			"name", "status", "category", "fee_type", "term",
			"net_amount", "outstanding_amount", "due_date", "payment_link",
		],
		order_by="due_date asc, creation asc",
	)
	for row in rows:
		row["overdue"] = bool(row.due_date and getdate(row.due_date) < getdate(today()))
	return rows


def _registration_windows():
	"""Terms accepting registrations, with the date the window shuts.

	`registration_closes` is the question students actually ask, and the one
	the office fields by phone when it is not on screen.
	"""
	rows = frappe.get_all(
		"Academic Term",
		filters={"status": ("in", ("Open", "Active"))},
		fields=["name", "term_name", "start_date", "end_date", "registration_closes"],
		order_by="start_date asc",
	)
	for row in rows:
		row["closes_in_days"] = (
			(getdate(row.registration_closes) - getdate(today())).days
			if row.registration_closes
			else None
		)
	return rows


@frappe.whitelist()
def dashboard():
	"""One view of what needs the student's attention."""
	enrollment = _require_enrollment()
	if not enrollment:
		return {"enrollment": None}

	header = _enrollment_header(enrollment)
	registrations = my_registrations(enrollment)
	_lms_links(registrations)

	in_progress = [r for r in registrations if r["status"] in LIVE_REGISTRATION_STATES]
	graded = [r for r in registrations if r.get("grade")]
	graded.sort(key=lambda r: r.get("term") or "", reverse=True)

	fees = _open_fees(header.get("student"))
	terms = _registration_windows()

	# Offerings are only worth counting while a window is open; the eligibility
	# engine runs per offering and there is no point paying for that otherwise.
	eligible_now = 0
	if terms:
		eligible_now = sum(
			1 for offering in available_offerings(enrollment) if offering["eligibility"]["allowed"]
		)

	return {
		"enrollment": header,
		"in_progress": in_progress[:6],
		"in_progress_count": len(in_progress),
		"recent_grades": graded[:4],
		"fees": {
			"open": fees[:5],
			"count": len(fees),
			"outstanding": flt(sum(flt(f.outstanding_amount) for f in fees), 2),
			"overdue_count": sum(1 for f in fees if f["overdue"]),
		},
		"registration": {
			"terms": terms,
			"eligible_count": eligible_now,
			"open": bool(terms),
		},
	}


# ---------------------------------------------------------------------------
# grades
# ---------------------------------------------------------------------------


def _grade_scale():
	"""The bands a grade is read against, so a letter means something."""
	name = frappe.db.get_value("Grade Scale", {"is_default": 1}, "name") or frappe.db.get_value(
		"Grade Scale", {}, "name"
	)
	if not name:
		return None

	scale = frappe.db.get_value(
		"Grade Scale", name, ["name", "scale_name", "pass_percentage"], as_dict=True
	)
	scale["rows"] = frappe.get_all(
		"Grade Scale Row",
		filters={"parent": name},
		fields=["grade", "min_pct", "max_pct", "grade_points", "is_pass"],
		order_by="min_pct desc",
	)
	return scale


@frappe.whitelist()
def grades():
	"""Every graded course, the marks behind each grade, and the scale.

	Components are fetched in one query for all registrations rather than one
	query per row -- a student finishing the programme has forty of them.
	"""
	enrollment = _require_enrollment()
	if not enrollment:
		return {"enrollment": None, "terms": [], "scale": None}

	registrations = frappe.get_all(
		"Course Registration",
		filters={"program_enrollment": enrollment},
		fields=[
			"name", "course", "course_title", "term", "status", "credits",
			"final_marks", "grade", "grade_points", "passed", "level_at_registration",
		],
		order_by="term desc, course asc",
	)

	components = {}
	if registrations:
		for row in frappe.get_all(
			"Grade Component",
			filters={"parent": ("in", [r.name for r in registrations])},
			fields=[
				"parent", "component", "weight_pct", "max_marks",
				"obtained_marks", "weighted_score", "idx",
			],
			order_by="parent asc, idx asc",
		):
			components.setdefault(row.parent, []).append(row)

	terms = {}
	for row in registrations:
		row["components"] = components.get(row.name, [])
		terms.setdefault(row.term, []).append(row)

	term_dates = {
		row.name: row
		for row in frappe.get_all(
			"Academic Term",
			filters={"name": ("in", list(terms) or [""])},
			fields=["name", "term_name", "start_date", "end_date"],
		)
	}

	grouped = [
		{
			"term": term,
			"term_name": (term_dates.get(term) or {}).get("term_name") or term,
			"start_date": (term_dates.get(term) or {}).get("start_date"),
			"rows": rows,
			"credits": flt(sum(flt(r.credits) for r in rows if r.passed), 2),
		}
		for term, rows in terms.items()
	]
	grouped.sort(key=lambda group: group["start_date"] or group["term"], reverse=True)

	return {
		"enrollment": _enrollment_header(enrollment),
		"terms": grouped,
		"scale": _grade_scale(),
	}


# ---------------------------------------------------------------------------
# course registration
# ---------------------------------------------------------------------------


@frappe.whitelist()
def registration_options():
	"""Offerings the student could take, grouped by term, each with a verdict.

	Blocked offerings are returned *with the reason*, because "why can't I take
	this?" is the question the Registrar otherwise answers by email. Grouping by
	term is not cosmetic: a course runs in several terms, and a flat list of
	near-identical rows is how students registered for the wrong one during
	acceptance testing.
	"""
	enrollment = _require_enrollment()
	if not enrollment:
		return {"enrollment": None, "terms": []}

	offerings = available_offerings(enrollment)

	grouped = {}
	for offering in offerings:
		grouped.setdefault(offering["term"], []).append(offering)

	term_rows = {
		row.name: row
		for row in frappe.get_all(
			"Academic Term",
			filters={"name": ("in", list(grouped) or [""])},
			fields=["name", "term_name", "start_date", "end_date", "registration_closes"],
		)
	}

	terms = [
		{
			"term": term,
			"term_name": (term_rows.get(term) or {}).get("term_name") or term,
			"start_date": (term_rows.get(term) or {}).get("start_date"),
			"end_date": (term_rows.get(term) or {}).get("end_date"),
			"registration_closes": (term_rows.get(term) or {}).get("registration_closes"),
			"rows": rows,
			"eligible_count": sum(1 for row in rows if row["eligibility"]["allowed"]),
		}
		for term, rows in grouped.items()
	]
	terms.sort(key=lambda group: group["start_date"] or group["term"])

	return {"enrollment": _enrollment_header(enrollment), "terms": terms}


@frappe.whitelist()
def offering_detail(course_offering):
	"""One offering with its verdict, for the confirmation step.

	The verdict is recomputed here rather than trusted from the list the
	browser is holding: that list may be minutes old, and a seat or a
	registration window can close in between.
	"""
	enrollment = _require_enrollment()
	if not enrollment:
		frappe.throw(_("No active enrollment found for your account."), frappe.PermissionError)

	offering = frappe.db.get_value(
		"Course Offering",
		course_offering,
		[
			"name", "course", "course_title", "term", "format", "status",
			"capacity", "enrolled_count", "zoom_time", "credits", "course_level",
		],
		as_dict=True,
	)
	if not offering:
		frappe.throw(_("Course Offering not found."))

	offering["eligibility"] = explain(enrollment, course_offering)
	offering["seats_left"] = (
		max(0, int(offering.capacity) - int(offering.enrolled_count or 0))
		if offering.capacity
		else None
	)
	return offering


# ---------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------


def _student_record():
	student = frappe.db.get_value("Student", {"user": frappe.session.user}, "name")
	if not student:
		return None
	return frappe.db.get_value(
		"Student",
		student,
		[
			"name", "full_name", "dob", "gender", "photo", "status",
			"mobile", "whatsapp", "email", "address",
		],
		as_dict=True,
	)


@frappe.whitelist()
def profile():
	"""The student's own record, and which parts of it they may change."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)

	student = _student_record()
	enrollment = get_enrollment()

	user = frappe.db.get_value(
		"User", frappe.session.user, ["full_name", "user_image", "username"], as_dict=True
	) or {}

	return {
		"user": {"name": frappe.session.user, **user},
		"student": student,
		"enrollment": _enrollment_header(enrollment) if enrollment else None,
		"editable": list(EDITABLE_PROFILE_FIELDS),
	}


@frappe.whitelist(methods=["POST"])
def update_profile(mobile=None, whatsapp=None, address=None):
	"""Change how the college reaches you -- and nothing else.

	Named arguments, not a dict: a `**values` signature here would write any
	field on the Student record the caller cared to name, including `status`.
	"""
	student = frappe.db.get_value("Student", {"user": frappe.session.user}, "name")
	if not student:
		frappe.throw(_("Your account is not linked to a student record."), frappe.PermissionError)

	values = {"mobile": mobile, "whatsapp": whatsapp, "address": address}
	updates = {k: (v or "").strip() for k, v in values.items() if v is not None}

	for field in ("mobile", "whatsapp"):
		number = updates.get(field)
		if number and not _looks_like_a_phone_number(number):
			frappe.throw(
				_("{0} does not look like a phone number.").format(frappe.unscrub(field)),
				title=_("Check the number"),
			)

	if updates:
		frappe.db.set_value("Student", student, updates)
		frappe.db.commit()

	return _student_record()


def _looks_like_a_phone_number(value):
	"""Deliberately loose. Students write +91 98765 43210, 098765-43210 and
	worse, and rejecting a reachable number helps nobody."""
	digits = [c for c in value if c.isdigit()]
	return 7 <= len(digits) <= 15 and all(c.isdigit() or c in "+-() ." for c in value)


@frappe.whitelist(methods=["POST"])
def update_photo(filename, content, content_type=None):
	"""Replace the student's photograph.

	Reuses the admissions validator, which checks the bytes rather than the
	name or the declared type, and opens the image to be sure it is one.
	"""
	from sibbcs.admissions.uploads import _validate_file

	student = frappe.db.get_value("Student", {"user": frappe.session.user}, "name")
	if not student:
		frappe.throw(_("Your account is not linked to a student record."), frappe.PermissionError)

	try:
		raw = base64.b64decode(content, validate=True)
	except Exception:
		frappe.throw(_("The upload was not readable."), title=_("Upload Failed"))

	extension = _validate_file(filename, raw, content_type)
	if extension == "pdf":
		frappe.throw(_("A photograph must be a JPG or PNG."), title=_("Unsupported File"))

	photo = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{student}-photo.{extension}",
			"attached_to_doctype": "Student",
			"attached_to_name": student,
			"is_private": 1,
			"content": raw,
		}
	)
	photo.insert(ignore_permissions=True)

	frappe.db.set_value("Student", student, "photo", photo.file_url)
	frappe.db.commit()
	return {"photo": photo.file_url}
