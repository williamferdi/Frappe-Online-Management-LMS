# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""The academic console: students, offerings, promotions and grade entry.

Arrangement, again. `course_registration.py` computes grades from the
components and maps them onto the Grade Scale; `level_promotion.py` decides who
may move a level and on what evidence. Neither is re-implemented here.

Grade entry is the one place this module writes, and it deliberately saves
through the document rather than around it: `Course Registration` keeps the
grade fields at permlevel 1, so an ordinary save is already the permission
check. Nothing here passes `ignore_permissions`.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from sibbcs.api.paging import fetch_capped
from sibbcs.academic.doctype.course_registration.course_registration import (
	refresh_enrollment_progress,
)
from sibbcs.academic.doctype.level_promotion.level_promotion import (
	may_approve,
	promotion_board,
)

# Who may work in the academic console at all. Narrower checks live on each
# endpoint -- promotions answer to `may_approve`, grades to the permlevel.
ACADEMIC_ROLES = (
	"System Manager",
	"Registrar",
	"Academic Coordinator",
	"Dean",
	"Faculty",
	"Facilitator",
)

LIVE_REGISTRATION_STATES = ("Registered", "Active")


def _require_academic():
	roles = set(frappe.get_roles())
	if not roles.intersection(ACADEMIC_ROLES):
		frappe.throw(
			_("You do not have access to academic records."), frappe.PermissionError
		)


# ---------------------------------------------------------------------------
# students
# ---------------------------------------------------------------------------

STUDENT_LIST_FIELDS = ("name", "full_name", "email", "mobile", "status", "user")


@frappe.whitelist()
def students(search=None, program=None, level=None, status=None, limit=200):
	"""The roll, with each student's enrolment beside them.

	Enrolments are fetched once for the whole page rather than once per row.
	"""
	_require_academic()

	filters = {}
	if status:
		filters["status"] = status

	or_filters = None
	if search:
		like = f"%{search}%"
		# A bare value in or_filters means `=`; a fragment search needs the
		# operator spelled out.
		or_filters = {
			field: ("like", like) for field in ("name", "full_name", "email", "mobile")
		}

	rows, truncated = fetch_capped(
		"Student",
		limit,
		filters=filters,
		or_filters=or_filters,
		fields=list(STUDENT_LIST_FIELDS),
		order_by="full_name asc",
	)
	if not rows:
		return _student_page([], program, level, truncated)

	enrollments = {}
	for row in frappe.get_all(
		"Program Enrollment",
		filters={"student": ("in", [r.name for r in rows])},
		fields=[
			"name", "student", "program", "current_level", "status",
			"credits_earned", "cgpa",
		],
		order_by="creation desc",
	):
		# Newest first, so the first one seen for a student wins.
		enrollments.setdefault(row.student, row)

	for row in rows:
		row["enrollment"] = enrollments.get(row.name)

	if program:
		rows = [r for r in rows if (r["enrollment"] or {}).get("program") == program]
	if level:
		rows = [
			r for r in rows if str((r["enrollment"] or {}).get("current_level")) == str(level)
		]

	return _student_page(rows, program, level, truncated)


def _student_page(rows, program, level, truncated=False):
	return {
		"rows": rows,
		"truncated": truncated,
		"programs": frappe.get_all("Program", pluck="name"),
		"levels": ["1", "2", "3", "4"],
		"filters": {"program": program, "level": level},
	}


@frappe.whitelist()
def student(name):
	"""One student: enrolment, registrations, grades and money owed."""
	_require_academic()

	record = frappe.db.get_value(
		"Student",
		name,
		["name", "full_name", "email", "mobile", "whatsapp", "dob", "gender",
		 "status", "photo", "address", "user", "admission_application"],
		as_dict=True,
	)
	if not record:
		frappe.throw(_("Student not found."))

	enrollment = frappe.db.get_value(
		"Program Enrollment",
		{"student": name},
		["name", "program", "current_level", "status", "credits_earned", "cgpa",
		 "enrollment_date", "expected_completion", "start_term"],
		as_dict=True,
		order_by="creation desc",
	)

	registrations = []
	if enrollment:
		registrations = frappe.get_all(
			"Course Registration",
			filters={"program_enrollment": enrollment.name},
			fields=[
				"name", "course", "course_title", "term", "status", "credits",
				"level_at_registration", "final_marks", "grade", "grade_points",
				"passed", "registration_fee_invoice", "course_offering",
			],
			order_by="term desc, course asc",
		)

	return {
		"student": record,
		"enrollment": enrollment,
		"registrations": registrations,
		"invoices": frappe.get_all(
			"Fee Invoice",
			filters={"student": name},
			fields=["name", "fee_type", "category", "status", "net_amount",
			        "outstanding_amount", "due_date"],
			order_by="creation desc",
		)
		if frappe.has_permission("Fee Invoice", "read")
		else [],
		"promotions": frappe.get_all(
			"Level Promotion",
			filters={"program_enrollment": enrollment.name} if enrollment else {"name": ""},
			fields=["name", "from_level", "to_level", "approved_by", "approved_on",
			        "courses_passed", "credits_at_promotion", "remarks"],
			order_by="creation desc",
		),
	}


# ---------------------------------------------------------------------------
# offerings and the roster
# ---------------------------------------------------------------------------


@frappe.whitelist()
def offerings(term=None, status=None, limit=200):
	"""Every run of a course, with how full it is."""
	_require_academic()

	filters = {}
	if term:
		filters["term"] = term
	if status:
		filters["status"] = status

	rows = frappe.get_all(
		"Course Offering",
		filters=filters,
		fields=[
			"name", "course", "course_title", "term", "status", "format",
			"instructor", "facilitator", "capacity", "enrolled_count",
			"credits", "course_level", "zoom_time",
		],
		order_by="term desc, course asc",
		limit_page_length=cint(limit),
	)

	# `enrolled_count` is maintained by the registration document, but a roster
	# that disagrees with its own counter is worth seeing rather than trusting.
	live = {}
	if rows:
		for row in frappe.get_all(
			"Course Registration",
			filters={
				"course_offering": ("in", [r.name for r in rows]),
				"status": ("in", LIVE_REGISTRATION_STATES),
			},
			fields=["course_offering", "count(name) as n"],
			group_by="course_offering",
		):
			live[row.course_offering] = cint(row.n)

	graded = {}
	if rows:
		for row in frappe.get_all(
			"Course Registration",
			filters={"course_offering": ("in", [r.name for r in rows]), "grade": ("is", "set")},
			fields=["course_offering", "count(name) as n"],
			group_by="course_offering",
		):
			graded[row.course_offering] = cint(row.n)

	for row in rows:
		row["registered"] = live.get(row.name, 0)
		row["graded"] = graded.get(row.name, 0)

	return {
		"rows": rows,
		"terms": frappe.get_all(
			"Academic Term", fields=["name", "term_name", "status"], order_by="start_date desc"
		),
	}


@frappe.whitelist()
def roster(course_offering):
	"""Who is on one offering, and where their grading stands."""
	_require_academic()

	offering = frappe.db.get_value(
		"Course Offering",
		course_offering,
		["name", "course", "course_title", "term", "status", "format", "instructor",
		 "facilitator", "capacity", "enrolled_count", "credits", "course_level"],
		as_dict=True,
	)
	if not offering:
		frappe.throw(_("Course Offering not found."))

	registrations = frappe.get_all(
		"Course Registration",
		filters={"course_offering": course_offering},
		fields=[
			"name", "student", "student_name", "status", "credits",
			"final_marks", "grade", "grade_points", "passed", "program_enrollment",
		],
		order_by="student_name asc",
	)

	components = {}
	if registrations:
		for row in frappe.get_all(
			"Grade Component",
			filters={"parent": ("in", [r.name for r in registrations])},
			fields=["name", "parent", "component", "weight_pct", "max_marks",
			        "obtained_marks", "weighted_score", "idx"],
			order_by="parent asc, idx asc",
		):
			components.setdefault(row.parent, []).append(row)

	for row in registrations:
		row["components"] = components.get(row.name, [])
		row["marks_complete"] = _marks_complete(row["components"])

	return {
		"offering": offering,
		"registrations": registrations,
		"components": _component_choices(),
		# The grade fields sit at permlevel 1; this is what the screen greys out
		# on, and the save still checks for itself.
		"can_grade": bool(frappe.has_permission("Course Registration", "write")),
		"statuses": _registration_statuses(),
	}


def _marks_complete(components):
	"""True once every component carries a mark.

	`compute_grade` holds the letter back until then, leaving final_marks at
	its previous value -- 0.0 on a registration that has never been graded.
	Shown as a score that is a lie, so each screen needs to know the
	difference between "nothing yet" and "zero".
	"""
	if not components:
		return False
	return all(c.get("obtained_marks") not in (None, "") for c in components)

def _component_choices():
	meta = frappe.get_meta("Grade Component")
	field = meta.get_field("component")
	return [choice for choice in (field.options or "").split("\n") if choice]


def _registration_statuses():
	meta = frappe.get_meta("Course Registration")
	field = meta.get_field("status")
	return [choice for choice in (field.options or "").split("\n") if choice]


# ---------------------------------------------------------------------------
# grade entry
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def save_grades(registration, components, status=None):
	"""Record marks against one registration.

	Saved through the document, never around it. `compute_grade` derives the
	weighted score, the total and the letter from the Grade Scale, and the
	grade fields are permlevel 1 -- so an ordinary save is already the
	permission check, and passing `ignore_permissions` here would quietly
	remove it.
	"""
	_require_academic()

	if isinstance(components, str):
		components = frappe.parse_json(components)
	if not isinstance(components, list):
		frappe.throw(_("Marks must be a list of components."))

	doc = frappe.get_doc("Course Registration", registration)
	doc.check_permission("write")

	doc.set("grade_components", [])
	for row in components:
		if not (row or {}).get("component"):
			continue
		doc.append(
			"grade_components",
			{
				"component": row["component"],
				"weight_pct": flt(row.get("weight_pct")),
				"max_marks": flt(row.get("max_marks")) or 100,
				# Blank stays blank: compute_grade holds off on the letter until
				# every component is marked, and a missing mark is not a zero.
				"obtained_marks": (
					flt(row["obtained_marks"])
					if row.get("obtained_marks") not in (None, "")
					else None
				),
			},
		)

	if status:
		doc.status = status

	doc.save()
	refresh_enrollment_progress(doc.program_enrollment)
	frappe.db.commit()

	return {
		"registration": doc.name,
		"final_marks": doc.final_marks,
		"grade": doc.grade,
		"grade_points": doc.grade_points,
		"passed": doc.passed,
		"status": doc.status,
		"marks_complete": _marks_complete(
			[{"obtained_marks": c.obtained_marks} for c in doc.grade_components]
		),
		"components": [
			{
				"component": c.component,
				"weight_pct": c.weight_pct,
				"max_marks": c.max_marks,
				"obtained_marks": c.obtained_marks,
				"weighted_score": c.weighted_score,
			}
			for c in doc.grade_components
		],
	}


# ---------------------------------------------------------------------------
# promotions
# ---------------------------------------------------------------------------


@frappe.whitelist()
def promotions(include_blocked=1):
	"""The Dean's list. `promotion_board` already refuses anyone else."""
	return {
		"rows": promotion_board(include_blocked=include_blocked),
		"may_approve": may_approve(),
	}
