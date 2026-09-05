# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""A student's own coursework: what is set, what they handed in, what came back.

**No endpoint here takes a student argument.** Every one resolves the student
from the session, the same rule the rest of the portal follows -- an endpoint
that accepts a student is an endpoint that can be asked about somebody else's.

**Nothing here returns an unposted score.** A mark exists from the moment the
marker types it; whether the student may see it is what `posted` says, and
these payloads are built so that a score is simply absent until then rather
than present and hidden by the front end.

Students hold no permission row on Assignment Submission at all, so every read
below is `frappe.get_all` under an explicit registration filter.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, get_datetime

from sibbcs.academic import gradebook
from sibbcs.academic.portal import get_student

ASSIGNMENT_FIELDS = (
	"name",
	"title",
	"description",
	"component",
	"points_possible",
	"grading_type",
	"submission_type",
	"due_date",
	"available_from",
	"available_until",
	"late_policy",
	"late_penalty_pct_per_day",
	"allowed_attempts",
)


def _my_registration(course_registration):
	"""The registration, if it is this session's own. Otherwise a refusal."""
	student = get_student()
	if not student:
		frappe.throw(_("No student record for your account."), frappe.PermissionError)

	row = frappe.db.get_value(
		"Course Registration",
		course_registration,
		["name", "student", "course_offering", "course_title", "status"],
		as_dict=True,
	)
	if not row or row.student != student:
		# The same message either way: "that is not yours" and "that does not
		# exist" should not be distinguishable, or the endpoint answers
		# questions about other people's registrations by how it fails.
		frappe.throw(_("Registration not found."), frappe.PermissionError)
	return row


def _visible(submission):
	"""One submission as its own student may see it.

	The score, the feedback and the rubric are dropped entirely unless posted.
	"""
	if not submission:
		return None

	visible = {
		"name": submission.get("name"),
		"attempt": submission.get("attempt"),
		"status": submission.get("status"),
		"submitted_on": submission.get("submitted_on"),
		"late_days": submission.get("late_days"),
		"excused": cint(submission.get("excused")),
		"body": submission.get("body"),
		"url": submission.get("url"),
		"posted": cint(submission.get("posted")),
	}

	if cint(submission.get("posted")) and submission.get("scored"):
		visible["score"] = submission.get("score")
		visible["effective_score"] = gradebook.effective_score(submission)
		visible["feedback"] = submission.get("feedback")

	return visible


@frappe.whitelist()
def coursework(course_registration):
	"""Everything set on one of my courses, with where I stand on each."""
	registration = _my_registration(course_registration)

	assignments = frappe.get_all(
		"Course Assignment",
		filters={"course_offering": registration.course_offering, "published": 1},
		fields=list(ASSIGNMENT_FIELDS),
		order_by="due_date asc, creation asc",
	)

	mine = {}
	if assignments:
		for submission in frappe.get_all(
			"Assignment Submission",
			filters={
				"course_registration": course_registration,
				"assignment": ("in", [row.name for row in assignments]),
			},
			fields=[
				"name", "assignment", "attempt", "status", "submitted_on", "late_days",
				"excused", "body", "url", "score", "scored", "posted", "feedback",
			],
			order_by="attempt asc",
		):
			mine[submission.assignment] = submission

	rows = []
	for assignment in assignments:
		submission = mine.get(assignment.name)
		rows.append(
			{
				"assignment": assignment,
				"submission": _visible(submission),
				"open": _is_open(assignment),
			}
		)

	return {
		"registration": {
			"name": registration.name,
			"course_title": registration.course_title,
			"course_offering": registration.course_offering,
			"status": registration.status,
		},
		"rows": rows,
	}


def _is_open(assignment):
	"""Whether work can still be handed in, and why not when it cannot.

	A reason rather than a bare no: "why can't I submit?" is the question the
	registrar otherwise fields by email.
	"""
	now = now_datetime()

	if assignment.get("available_from") and now < get_datetime(assignment["available_from"]):
		return {"open": False, "reason": "This has not opened yet."}

	if assignment.get("available_until") and now > get_datetime(assignment["available_until"]):
		return {"open": False, "reason": "This has closed."}

	if assignment.get("submission_type") == "No Submission":
		return {"open": False, "reason": "Nothing is handed in for this one."}

	if assignment.get("due_date") and now > get_datetime(assignment["due_date"]):
		if assignment.get("late_policy") == "Refuse":
			return {"open": False, "reason": "This is past its due date."}
		if assignment.get("late_policy") == "Accept with penalty":
			return {
				"open": True,
				"reason": "This is late. {0}% is deducted for each day.".format(
					flt(assignment.get("late_penalty_pct_per_day"))
				),
			}
		return {"open": True, "reason": "This is late, but still accepted."}

	return {"open": True, "reason": None}


@frappe.whitelist(methods=["POST"])
def submit(course_registration, assignment, body=None, url=None):
	"""Hand work in.

	Inserted with `ignore_permissions`, because a student holds no permission
	row on Assignment Submission at all -- deliberately, since permlevel
	cannot express "your own score, once posted". `_my_registration` above is
	the permission check, and the fields a student may set are named here
	rather than taken from the payload.
	"""
	registration = _my_registration(course_registration)

	row = frappe.db.get_value(
		"Course Assignment",
		assignment,
		list(ASSIGNMENT_FIELDS) + ["course_offering", "published"],
		as_dict=True,
	)
	if not row or not cint(row.published):
		frappe.throw(_("Assignment not found."))
	if row.course_offering != registration.course_offering:
		frappe.throw(_("That assignment is not on this course."), frappe.PermissionError)

	state = _is_open(row)
	if not state["open"]:
		frappe.throw(state["reason"] or _("This is not open."))

	existing = frappe.get_all(
		"Assignment Submission",
		filters={"assignment": assignment, "course_registration": course_registration},
		fields=["name", "attempt", "posted"],
		order_by="attempt desc",
	)

	allowed = cint(row.allowed_attempts)
	if allowed and len(existing) >= allowed:
		frappe.throw(
			_("You have used all {0} attempt(s) for this.").format(allowed)
		)

	if existing and cint(existing[0].posted):
		# Re-handing-in after a mark has been returned would silently replace
		# the work the mark was given for.
		frappe.throw(_("This has been marked and returned, so it cannot be resubmitted."))

	submission = frappe.new_doc("Assignment Submission")
	submission.assignment = assignment
	submission.course_registration = course_registration
	submission.attempt = (cint(existing[0].attempt) + 1) if existing else 1
	submission.status = "Submitted"
	submission.submitted_on = now_datetime()
	submission.body = body
	submission.url = url
	submission.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"submission": _visible(submission.as_dict()), "attempt": submission.attempt}
