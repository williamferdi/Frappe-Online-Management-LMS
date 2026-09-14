# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""The marking queue: work waiting, one piece at a time, and posting.

Faculty-facing. The student half lives in `sibbcs.api.coursework`, which never
takes a student argument and never returns an unposted score.

Two habits from the rest of the API. Reads go through `frappe.get_all`, which
bypasses permissions, so every endpoint calls `permissions.assert_may_teach`
for itself. Writes go through the document, so the submission controller's
rules -- days late, score within the marks, excused work carrying no score --
apply, and the roll-up fires from `on_update` rather than from here.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from sibbcs.academic import gradebook
from sibbcs.academic import permissions as academic_permissions
from sibbcs.api.academic_api import ACADEMIC_ROLES

QUEUE_FIELDS = (
	"name",
	"course_registration",
	"student",
	"student_name",
	"attempt",
	"status",
	"submitted_on",
	"late_days",
	"excused",
	"score",
	"scored",
	"posted",
	"feedback",
	"graded_by",
	"graded_on",
	"body",
	"url",
)


def _require_teaching():
	roles = set(frappe.get_roles())
	if not roles.intersection(ACADEMIC_ROLES):
		frappe.throw(
			_("You do not have access to academic records."), frappe.PermissionError
		)


def _assignment_or_throw(assignment):
	row = frappe.db.get_value(
		"Course Assignment",
		assignment,
		[
			"name", "title", "course_offering", "component", "points_possible",
			"due_date", "late_policy", "late_penalty_pct_per_day", "submission_type",
			"published", "rubric", "description",
		],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Assignment not found."))
	academic_permissions.assert_may_teach(row.course_offering)
	return row


# ---------------------------------------------------------------------------
# the queue
# ---------------------------------------------------------------------------


@frappe.whitelist()
def queue(assignment):
	"""Everyone who should have handed this in, whether they did or not.

	A student with nothing handed in is a row too: "who has not submitted" is
	the question a marker actually asks, and a list of only the submissions
	answers a different one.
	"""
	_require_teaching()
	row = _assignment_or_throw(assignment)

	registrations = frappe.get_all(
		"Course Registration",
		filters={"course_offering": row.course_offering},
		fields=["name", "student", "student_name", "status"],
		order_by="student_name asc",
	)

	submissions = {}
	for submission in frappe.get_all(
		"Assignment Submission",
		filters={"assignment": assignment},
		fields=list(QUEUE_FIELDS),
		order_by="attempt desc",
	):
		# Highest attempt wins, and the order_by puts it first.
		submissions.setdefault(submission.course_registration, submission)

	rows = []
	for registration in registrations:
		submission = submissions.get(registration.name)
		rows.append(
			{
				"course_registration": registration.name,
				"student": registration.student,
				"student_name": registration.student_name,
				"submission": submission,
				"effective_score": (
					gradebook.effective_score(submission, row) if submission else None
				),
			}
		)

	return {
		"assignment": row,
		"rubric": _rubric_payload(row.rubric),
		"rows": rows,
		"ungraded": sum(
			1
			for entry in rows
			if entry["submission"]
			and not entry["submission"].get("scored")
			and not entry["submission"].get("excused")
		),
		"unposted": sum(
			1
			for entry in rows
			if entry["submission"]
			and entry["submission"].get("scored")
			and not cint(entry["submission"].get("posted"))
		),
		"missing": sum(1 for entry in rows if not entry["submission"]),
	}


def _rubric_payload(rubric):
	if not rubric or not frappe.db.exists("Course Rubric", rubric):
		return None

	criteria = frappe.get_all(
		"Rubric Criterion",
		filters={"rubric": rubric},
		fields=["name", "title", "description", "points_possible", "position"],
		order_by="position asc, creation asc",
	)
	for criterion in criteria:
		criterion["ratings"] = frappe.get_all(
			"Rubric Rating",
			filters={"parent": criterion.name, "parenttype": "Rubric Criterion"},
			fields=["title", "points", "description"],
			order_by="idx asc",
		)

	return {
		"name": rubric,
		"title": frappe.db.get_value("Course Rubric", rubric, "title"),
		"criteria": criteria,
	}


# ---------------------------------------------------------------------------
# marking
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def grade(assignment, course_registration, score=None, feedback=None, excused=None,
		  rubric_assessment=None, post=None):
	"""Mark one piece of work.

	Saved through the document and without `ignore_permissions`, so permlevel 1
	on `score` is the permission check -- a Facilitator holds level-1 read and
	no write, and this is where that stops being decorative.
	"""
	_require_teaching()
	row = _assignment_or_throw(assignment)

	submission = _submission_for(assignment, course_registration, row)

	if excused is not None:
		submission.excused = cint(excused)
		if submission.excused:
			submission.score = None
			submission.status = "Excused"

	if not submission.excused and score is not None:
		submission.score = None if score == "" else flt(score)

	if feedback is not None:
		submission.feedback = feedback

	if rubric_assessment is not None:
		_apply_rubric(submission, rubric_assessment, row)

	if post is not None:
		submission.posted = cint(post)

	# Automatic posting is the scheme's choice, not the marker's: a component
	# set to post automatically shows a mark as soon as it exists.
	elif submission.scored and _posts_automatically(row):
		submission.posted = 1

	submission.save()
	frappe.db.commit()

	return {"submission": _one(submission.name, row)}


def _posts_automatically(assignment_row):
	scheme = gradebook.scheme_for(assignment_row.course_offering)
	if not scheme:
		return False
	for scheme_row in scheme.rows:
		if scheme_row.component == assignment_row.component:
			return scheme_row.posting_policy == "Automatic"
	return False


def _submission_for(assignment, course_registration, assignment_row):
	"""The latest attempt, or a fresh row for work never handed in.

	A marker can score something that was never submitted -- an offline paper,
	or a zero for nothing handed in -- and that needs somewhere to live.
	"""
	existing = frappe.get_all(
		"Assignment Submission",
		filters={"assignment": assignment, "course_registration": course_registration},
		fields=["name"],
		order_by="attempt desc",
		limit=1,
	)
	if existing:
		return frappe.get_doc("Assignment Submission", existing[0].name)

	registration_offering = frappe.db.get_value(
		"Course Registration", course_registration, "course_offering"
	)
	if registration_offering != assignment_row.course_offering:
		frappe.throw(
			_("That registration is not on this course."), frappe.PermissionError
		)

	submission = frappe.new_doc("Assignment Submission")
	submission.assignment = assignment
	submission.course_registration = course_registration
	# Fetched from the assignment, but Frappe checks permission before it
	# fetches, so marking work nobody handed in was refused to every teacher.
	submission.course_offering = assignment_row.course_offering
	submission.attempt = 1
	submission.status = "Missing"
	return submission


def _apply_rubric(submission, assessment, assignment_row):
	if isinstance(assessment, str):
		assessment = frappe.parse_json(assessment)
	if not isinstance(assessment, list):
		frappe.throw(_("A rubric assessment must be a list of criteria."))

	allowed = set(
		frappe.get_all(
			"Rubric Criterion", filters={"rubric": assignment_row.rubric}, pluck="name"
		)
	)

	submission.set("rubric_assessment", [])
	total = 0.0
	for entry in assessment:
		criterion = (entry or {}).get("criterion")
		if criterion not in allowed:
			# A criterion from another rubric would score against a heading
			# this assignment never had.
			continue
		points = flt(entry.get("points"))
		total += points
		submission.append(
			"rubric_assessment",
			{"criterion": criterion, "points": points, "comment": entry.get("comment")},
		)

	if submission.get("rubric_assessment"):
		submission.score = flt(total, 2)


@frappe.whitelist(methods=["POST"])
def set_posted(assignment, posted, course_registration=None):
	"""Post or withdraw marks -- one student, or the whole assignment.

	Posting the lot at once is how a marker actually works: mark everybody,
	then release them together so nobody reads their own mark before their
	neighbour.
	"""
	_require_teaching()
	row = _assignment_or_throw(assignment)

	filters = {"assignment": assignment}
	if course_registration:
		filters["course_registration"] = course_registration

	names = frappe.get_all("Assignment Submission", filters=filters, pluck="name")

	touched = 0
	for name in names:
		submission = frappe.get_doc("Assignment Submission", name)
		if not submission.scored and not submission.excused:
			# Posting an unmarked submission would show a student a blank and
			# call it a result.
			continue
		if cint(submission.posted) == cint(posted):
			continue
		submission.posted = cint(posted)
		submission.status = "Returned" if cint(posted) else "Graded"
		submission.save()
		touched += 1

	frappe.db.commit()
	return {"posted": cint(posted), "changed": touched}


def _one(name, assignment_row=None):
	submission = frappe.db.get_value(
		"Assignment Submission", name, list(QUEUE_FIELDS), as_dict=True
	)
	if submission:
		submission["effective_score"] = gradebook.effective_score(
			submission, assignment_row
		)
	return submission


# ---------------------------------------------------------------------------
# the gradebook grid
# ---------------------------------------------------------------------------


@frappe.whitelist()
def gradebook_grid(course_offering):
	"""Every student against every assignment, plus where their grade stands.

	Three queries whatever the size of the class -- students times assignments
	is exactly the shape that turns into a query per cell if you let it.
	"""
	_require_teaching()
	academic_permissions.assert_may_teach(course_offering)

	# The description rides along so a marker can see what the work asked for
	# from its column, without leaving the grid.
	assignments = frappe.get_all(
		"Course Assignment",
		filters={"course_offering": course_offering},
		fields=[
			"name", "title", "component", "points_possible", "due_date", "published",
			"description",
		],
		order_by="due_date asc, creation asc",
	)

	registrations = frappe.get_all(
		"Course Registration",
		filters={"course_offering": course_offering},
		fields=["name", "student", "student_name", "final_marks", "grade", "passed"],
		order_by="student_name asc",
	)

	cells = {}
	if assignments:
		for submission in frappe.get_all(
			"Assignment Submission",
			filters={"assignment": ("in", [row.name for row in assignments])},
			fields=[
				"name", "assignment", "course_registration", "score", "posted",
				"excused", "status", "late_days",
			],
			order_by="attempt asc",
		):
			cells[(submission.course_registration, submission.assignment)] = submission

	# Which registrations are fully marked. `final_marks` is a Float and so
	# NOT NULL DEFAULT 0: a half-marked course reads back 0.0, and printing
	# that as a total is the same lie `marked` exists to stop telling.
	complete = _fully_marked([row.name for row in registrations])

	rows = []
	for registration in registrations:
		rows.append(
			{
				"course_registration": registration.name,
				"student_name": registration.student_name,
				"final_marks": (
					registration.final_marks if complete.get(registration.name) else None
				),
				"marks_complete": bool(complete.get(registration.name)),
				"grade": registration.grade,
				"passed": registration.passed,
				"cells": {
					assignment.name: cells.get((registration.name, assignment.name))
					for assignment in assignments
				},
			}
		)

	scheme = gradebook.scheme_for(course_offering)

	return {
		"assignments": assignments,
		"rows": rows,
		"scheme": (
			[
				{"component": row.component, "weight_pct": flt(row.weight_pct),
				 "posting_policy": row.posting_policy}
				for row in scheme.rows
			]
			if scheme
			else None
		),
	}


def _fully_marked(registrations):
	"""Registration -> whether every one of its components carries a mark.

	One grouped query for the class, not one per student: students times
	components is exactly the shape that turns into a query per cell.
	"""
	if not registrations:
		return {}

	counts = {name: [0, 0] for name in registrations}
	for row in frappe.get_all(
		"Grade Component",
		filters={"parent": ("in", registrations), "parenttype": "Course Registration"},
		fields=["parent", "marked"],
	):
		counts[row.parent][0] += 1
		if cint(row.marked):
			counts[row.parent][1] += 1

	# No components at all is not "complete" -- it is a course nobody has
	# started marking.
	return {
		name: bool(total and total == marked) for name, (total, marked) in counts.items()
	}


# ---------------------------------------------------------------------------
# rubrics
# ---------------------------------------------------------------------------


def _rubric_course(rubric):
	"""A rubric's course, or None when it is shared. One that does not exist
	is said so, rather than read as a shared one."""
	if not rubric or not frappe.db.exists("Course Rubric", rubric):
		frappe.throw(_("Rubric not found."))
	return frappe.db.get_value("Course Rubric", rubric, "course")


@frappe.whitelist()
def rubrics(course=None):
	"""Rubrics this user may use: their own courses', and the shared ones."""
	_require_teaching()
	return {
		"rows": frappe.get_all(
			"Course Rubric",
			or_filters=academic_permissions.course_record_filters(course),
			fields=["name", "title", "course", "total_points", "description"],
			order_by="title asc",
		)
	}


@frappe.whitelist()
def rubric(name):
	_require_teaching()
	academic_permissions.assert_may_see(_rubric_course(name))
	return _rubric_payload(name)


@frappe.whitelist(methods=["POST"])
def save_rubric(title, criteria, name=None, course=None, description=None):
	"""Create or rewrite a rubric and its criteria.

	The criteria are separate documents, so this reconciles rather than
	replaces: a criterion that survives keeps its name, and therefore keeps
	every assessment already made against it. Deleting and re-creating would
	silently orphan past marking.

	A course's rubric is its teachers' to change, and a shared one the
	office's: one teacher's edit to a shared rubric would change how every
	course using it is marked. Both where it is and where it would go are
	checked, or a rubric could be carried off another course.
	"""
	_require_teaching()
	if name:
		academic_permissions.assert_may_change(_rubric_course(name), _("rubric"))
	academic_permissions.assert_may_change(course or None, _("rubric"))

	if isinstance(criteria, str):
		criteria = frappe.parse_json(criteria)
	if not isinstance(criteria, list) or not criteria:
		frappe.throw(_("A rubric needs at least one criterion."))

	if name:
		doc = frappe.get_doc("Course Rubric", name)
	else:
		doc = frappe.new_doc("Course Rubric")

	doc.title = title
	doc.course = course or None
	doc.description = description
	doc.save()

	kept = set()
	for position, entry in enumerate(criteria):
		# Only this rubric's own criteria keep their names. A criterion named
		# from another rubric would be moved here, out from under the marking
		# already done against it there.
		existing = entry.get("name")
		criterion = (
			frappe.get_doc("Rubric Criterion", existing)
			if existing
			and frappe.db.get_value("Rubric Criterion", existing, "rubric") == doc.name
			else frappe.new_doc("Rubric Criterion")
		)
		criterion.rubric = doc.name
		criterion.title = entry.get("title")
		criterion.description = entry.get("description")
		criterion.points_possible = flt(entry.get("points_possible"))
		criterion.position = position
		criterion.set("ratings", [])
		for rating in entry.get("ratings") or []:
			criterion.append(
				"ratings",
				{
					"title": rating.get("title"),
					"points": flt(rating.get("points")),
					"description": rating.get("description"),
				},
			)
		criterion.save()
		kept.add(criterion.name)

	for existing in frappe.get_all(
		"Rubric Criterion", filters={"rubric": doc.name}, pluck="name"
	):
		if existing not in kept:
			frappe.delete_doc("Rubric Criterion", existing, ignore_permissions=False)

	frappe.db.commit()
	return _rubric_payload(doc.name)
