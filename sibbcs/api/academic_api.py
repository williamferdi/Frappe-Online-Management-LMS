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

from sibbcs.academic import gradebook
from sibbcs.academic import permissions as academic_permissions
from sibbcs.admissions import checklist
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

STUDENT_LIST_FIELDS = (
	"name",
	"full_name",
	"email",
	"mobile",
	"status",
	"user",
	# A roll of names is a spreadsheet; a roll of faces is a college.
	"photo",
)


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
		"admission": _admission_profile(record.admission_application),
		"promotions": frappe.get_all(
			"Level Promotion",
			filters={"program_enrollment": enrollment.name} if enrollment else {"name": ""},
			fields=["name", "from_level", "to_level", "approved_by", "approved_on",
			        "courses_passed", "credits_at_promotion", "remarks"],
			order_by="creation desc",
		),
	}


# ---------------------------------------------------------------------------
# the admission record behind a student
# ---------------------------------------------------------------------------

# A `Student` row is identity and contact only. Everything else a college holds
# about a person -- their schooling, their ministry, who vouched for them, which
# certificates they sent -- was asked once on the Admission Application and
# deliberately never copied across, so the full profile is the two read
# together.
ADMISSION_FIELDS = (
	"name",
	"creation",
	"workflow_state",
	"program",
	"intake_term",
	"entry_level",
	"age",
	"photo",
	"church_name",
	"current_role",
	"years_of_ministry",
	"has_bachelors",
	"previous_theological_education",
	"mother_tongue",
	"nationality",
	"church_denomination",
	"salvation_status",
	"baptism_status",
	"sense_of_call",
	"ata_eligible",
	"mature_candidate",
	"transfer_student",
	"education_sequence_mismatch",
	"whatsapp_groups",
	"theological_writing_status",
	"ssc_status",
	"ssc_year",
	"hslc_status",
	"hslc_year",
	"ug_status",
	"ug_year",
	"id_document",
	"ministry_experience_doc",
	"application_fee_paid",
	"docs_verified",
	"qualifying_exam_score",
	"interview_outcome",
	"offer_sent_on",
	"admission_fee_paid",
	"onboard_term",
	"onboard_level",
	"enrolled_on",
	"applicant_user",
	"scholarship_request",
)


def _child_rows(doctype, parent, fields):
	return frappe.get_all(
		doctype,
		filters={"parent": parent, "parenttype": "Admission Application"},
		fields=fields,
		order_by="idx",
	)


def _admission_profile(application):
	"""What the candidate told us, or None when it is not this user's to read.

	Faculty may see a student and enter their grades but hold no permission on
	Admission Application. The profile then does without this block rather than
	the whole page failing -- and the omission is the permission matrix
	speaking, not a bug.
	"""
	if not application or not frappe.db.exists("Admission Application", application):
		return None

	if not frappe.has_permission("Admission Application", "read", doc=application):
		return None

	record = frappe.db.get_value(
		"Admission Application", application, list(ADMISSION_FIELDS), as_dict=True
	)

	scholarship = None
	if record.scholarship_request and frappe.has_permission("Scholarship Request", "read"):
		scholarship = frappe.db.get_value(
			"Scholarship Request",
			record.scholarship_request,
			["name", "status", "requested_amount", "approved_amount", "monthly_discount"],
			as_dict=True,
		)

	return {
		"application": record,
		"checklist": checklist.board(application),
		"documents": _child_rows(
			"Application Document",
			application,
			["name", "document_type", "file", "verified", "verified_by", "remarks", "idx"],
		),
		"references": _child_rows(
			"Reference Request",
			application,
			[
				"name", "referee_name", "referee_email", "referee_type",
				"sent_on", "submitted_on", "recommendation", "idx",
			],
		),
		"mentors": _child_rows(
			"Mentor Consent",
			application,
			[
				"name", "mentor_name", "mentor_email", "mentor_mobile", "church",
				"denomination", "current_position", "years_of_ministry",
				"mentoring_experience", "prior_theological_education",
				"handbook_acknowledged", "consent_file", "sent_on", "consented_on", "idx",
			],
		),
		"manuals": _child_rows(
			"Manual Acknowledgement",
			application,
			["name", "manual", "sent_on", "acknowledged_on", "acknowledged_name", "idx"],
		),
		"scholarship": scholarship,
	}




# ---------------------------------------------------------------------------
# who is on the roll
# ---------------------------------------------------------------------------

# Every panel names its own categories rather than counting whatever happens to
# be in the data: a category with nobody in it is a fact worth seeing, and a
# donut that silently drops "B.Th 0" answers a question nobody asked.
YES_NO = ("Yes", "No")


def _tally(rows, field, categories, unknown="Not set"):
	"""Counts in the order the categories were declared, plus what fell outside.

	Anything not in `categories` lands in one bucket rather than inventing a
	slice per stray value -- a status somebody added in Desk should show up as
	a number to ask about, not as a new colour.
	"""
	counts = {category: 0 for category in categories}
	stray = 0
	for row in rows:
		value = row.get(field)
		value = str(value) if value not in (None, "") else None
		if value in counts:
			counts[value] += 1
		else:
			stray += 1

	slices = [{"label": category, "count": counts[category]} for category in categories]
	if stray:
		slices.append({"label": unknown, "count": stray})
	return slices


def _options(doctype, fieldname):
	field = frappe.get_meta(doctype).get_field(fieldname)
	return [line.strip() for line in (field.options or "").split("\n") if line.strip()]


@frappe.whitelist()
def demographics():
	"""The roll at a glance: six breakdowns of the enrolled students.

	Deliberately the whole roll rather than whatever the list is filtered to.
	The panels are a standing description of the college -- a search box that
	made them jump would make them useless for the thing they are for.

	Four queries, whatever the number of students. The obvious version of this
	asks the enrolment and the application per student, which is 200 round
	trips today and 2,000 next year.
	"""
	_require_academic()

	students = frappe.get_all(
		"Student",
		fields=["name", "gender", "status", "admission_application"],
	)
	total = len(students)

	enrollments = {}
	for row in frappe.get_all(
		"Program Enrollment",
		fields=["student", "program", "current_level", "creation"],
		order_by="creation desc",
	):
		# Newest first, so the first one seen for a student wins.
		enrollments.setdefault(row.student, row)

	for row in students:
		enrolment = enrollments.get(row.name) or {}
		row["program"] = enrolment.get("program")
		row["current_level"] = enrolment.get("current_level")

	panels = [
		{
			"key": "program",
			"title": "Programme",
			"kind": "categorical",
			"slices": _tally(
				students, "program", frappe.get_all("Program", pluck="name"), "No programme"
			),
		},
		{
			"key": "gender",
			"title": "Gender",
			"kind": "categorical",
			"slices": _tally(students, "gender", _options("Student", "gender")),
		},
		{
			"key": "status",
			"title": "Current status",
			"kind": "status",
			"slices": _tally(students, "status", _options("Student", "status")),
		},
		{
			"key": "level",
			"title": "Academic level",
			"kind": "ordinal",
			"slices": _tally(
				students,
				"current_level",
				_options("Program Enrollment", "current_level"),
				"Not enrolled",
			),
		},
	]

	# The last two live on the admission application, which Faculty hold nothing
	# on. The panels are dropped rather than shown empty -- a zero that means
	# "you may not read this" is a lie.
	if frappe.has_permission("Admission Application", "read"):
		applications = {
			row.name: row
			for row in frappe.get_all(
				"Admission Application",
				filters={"name": ("in", [s.admission_application for s in students if s.admission_application] or [""])},
				fields=["name", "mature_candidate", "transfer_student"],
			)
		}

		for field, title in (
			("mature_candidate", "Mature candidates"),
			("transfer_student", "Transfer students"),
		):
			yes = sum(
				1
				for student in students
				if cint(applications.get(student.admission_application, {}).get(field))
			)
			panels.append(
				{
					"key": field,
					"title": title,
					"kind": "binary",
					"slices": [
						{"label": "Yes", "count": yes},
						{"label": "No", "count": total - yes},
					],
				}
			)

	return {"total": total, "panels": panels}

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

	# None means the whole register; a list means these and no others. An
	# empty list is a teacher who has been given no course, and must not
	# read as no filter at all.
	scope = academic_permissions.offering_scope()
	if scope is not None:
		filters["name"] = ("in", scope)

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
	# Read below with frappe.get_all, which bypasses permissions, so neither
	# the query condition nor has_permission ever sees this. Ask by hand.
	academic_permissions.assert_may_teach(course_offering)

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

	# Where a scheme exists this merges rather than replaces. A payload naming
	# only the hand-marked buckets -- which is what a screen showing only the
	# rows it can edit would send -- would otherwise wipe every bucket the
	# gradebook computes, and with it the marks behind them.
	incoming = {
		row["component"]: row for row in components if (row or {}).get("component")
	}
	if gradebook.is_scheme_driven(doc.course_offering):
		for existing in doc.grade_components:
			if existing.component not in incoming:
				incoming[existing.component] = {
					"component": existing.component,
					"weight_pct": existing.weight_pct,
					"max_marks": existing.max_marks,
					"obtained_marks": (
						existing.obtained_marks if existing.marked else None
					),
				}
		components = list(incoming.values())

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
				# The blank itself cannot be stored -- the column is NOT NULL
				# DEFAULT 0 -- so what "unmarked" means is recorded here.
				"marked": int(row.get("obtained_marks") not in (None, "")),
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
				# A screen that draws 0 where nobody has marked is the same lie
				# the database tells; send the blank back as a blank.
				"obtained_marks": c.obtained_marks if cint(c.marked) else None,
				"marked": cint(c.marked),
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
