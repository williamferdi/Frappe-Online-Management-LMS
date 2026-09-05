# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Which dates actually apply to one student on one assignment.

An assignment carries dates for everybody. An override moves them for one
student, or for a group -- an extension, a resit window, a placement that ate
somebody's fortnight.

**Dates only.** An override never touches a score, a weighting or a submission.
Anything that did would be a second way to change a grade, and the whole design
rests on there being one.

**The student's own override beats the group's**, because it was set with them
in mind. Between two group overrides -- a student can be in more than one group
set -- the latest due date wins, on the grounds that a course which has told
somebody two different things should honour the kinder one rather than catch
them out.

Everything that asks "is this open?" or "how late is this?" resolves through
here, so a student with an extension is not late in one screen and late in
another.
"""

import frappe
from frappe.utils import get_datetime

DATE_FIELDS = ("available_from", "due_date", "available_until")


def _groups_of(course_registration):
	if not course_registration:
		return []
	return frappe.get_all(
		"Course Group Member",
		filters={
			"course_registration": course_registration,
			"parenttype": "Course Group",
		},
		pluck="parent",
	)


def override_for(assignment, course_registration):
	"""The override that applies, or None.

	One query for the student's own, one for their groups'. Called on every
	assignment a student sees, so it does not grow a query per group.
	"""
	if not assignment or not course_registration:
		return None

	mine = frappe.get_all(
		"Assignment Override",
		filters={
			"assignment": assignment,
			"course_registration": course_registration,
		},
		fields=["name"] + list(DATE_FIELDS),
		limit=1,
	)
	if mine:
		return mine[0]

	groups = _groups_of(course_registration)
	if not groups:
		return None

	theirs = frappe.get_all(
		"Assignment Override",
		filters={"assignment": assignment, "course_group": ("in", groups)},
		fields=["name"] + list(DATE_FIELDS),
	)
	if not theirs:
		return None

	# The kinder deadline, when a student is in two groups that were told
	# different things.
	def latest(row):
		return get_datetime(row.due_date) if row.due_date else get_datetime("1900-01-01")

	return max(theirs, key=latest)


def dates_for(assignment_row, course_registration):
	"""The assignment's dates with any override applied.

	Takes the assignment as a dict so the caller's single query is reused
	rather than repeated. An override that leaves a field blank does not blank
	the assignment's own date -- it says nothing about that one.
	"""
	dates = {field: assignment_row.get(field) for field in DATE_FIELDS}

	name = assignment_row.get("name")
	override = override_for(name, course_registration)
	if not override:
		return dates

	for field in DATE_FIELDS:
		if override.get(field):
			dates[field] = override[field]

	dates["overridden"] = True
	return dates


def apply_to(assignment_row, course_registration):
	"""The same assignment dict, with its dates replaced in place."""
	dates = dates_for(assignment_row, course_registration)
	for field in DATE_FIELDS:
		assignment_row[field] = dates[field]
	if dates.get("overridden"):
		assignment_row["dates_overridden"] = 1
	return assignment_row


def due_for(assignment, course_registration):
	"""Just the due date, for the lateness calculation."""
	row = frappe.db.get_value(
		"Course Assignment", assignment, ["name"] + list(DATE_FIELDS), as_dict=True
	)
	if not row:
		return None
	return dates_for(row, course_registration).get("due_date")
