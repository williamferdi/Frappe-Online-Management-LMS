# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""Read endpoints for the student portal.

Thin on purpose. The rules live in `academic/portal.py` and `academic/
eligibility.py`; this module composes what one screen needs into one response
so the browser does not make five calls to draw a page.

Everything is scoped to the logged-in student. None of these take a student or
enrollment argument -- there is no parameter here for one student to read
another's record through.
"""

import frappe
from frappe import _

from sibbcs.academic.portal import get_enrollment, my_registrations

ENROLLMENT_FIELDS = (
	"student",
	"student_name",
	"program",
	"program_name",
	"current_level",
	"credits_earned",
	"cgpa",
	"status",
)


def _require_enrollment():
	"""The caller's active enrollment, or a message explaining its absence.

	A logged-in applicant with no enrollment yet is an ordinary state, not an
	error -- the portal shows them what to do next rather than a stack trace.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)

	enrollment = get_enrollment()
	if not enrollment:
		return None
	return enrollment


def _enrollment_header(enrollment):
	fields = [f for f in ENROLLMENT_FIELDS if frappe.db.has_column("Program Enrollment", f)]
	row = frappe.db.get_value("Program Enrollment", enrollment, fields, as_dict=True) or {}
	row["name"] = enrollment
	return row


def _lms_links(registrations):
	"""Where each registration's course lives in the LMS, and how far along.

	The portal deliberately does not render lessons -- it links out to the LMS
	course player, which already knows how to run quizzes, assignments and
	progress. Course.lms_course is written by `lms_sync.ensure_lms_course`.
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
