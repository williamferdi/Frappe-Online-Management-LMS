# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

"""Where a course's grading structure meets the grade pipeline.

A Course Grade Scheme is a list of weighted buckets -- Assignment 40%, Exam
40%, Attendance 20%. `Course Registration.grade_components` is a list of
weighted buckets. They are the same list, so this module's whole job is to
keep the second in step with the first, and then to let `compute_grade` do
exactly what it has always done.

Two rules decide everything here:

**A blank mark is not a zero.** `compute_grade` holds the letter back until
every component carries a mark, which is what stops a half-marked course
reading as a fail. So a bucket nothing has been posted to gets
`obtained_marks = None`, never 0.

**A scheme is opt-in and reversible.** An offering with no Course Grade Scheme
is not touched by any of this, and grading it by hand works exactly as it did
before. Deleting a scheme hands the offering back to the hand-typed path with
the marks intact.

Phase 1 builds the structure: the buckets appear on every registration, empty.
Phase 2 fills them from posted submissions, which is why `auto_computed` is
set here but the mark itself is not.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

DEFAULT_MAX_MARKS = 100

# What a course taught in Campus LMS Lite is graded out of: one bucket covering
# everything the LMS marked -- assignments, quizzes, discussions, participation.
LMS_COMPONENT = "Coursework"


def scheme_for(course_offering):
	"""The offering's grade scheme, or None if it is graded by hand.

	The scheme is named after its offering, so this is an existence check
	rather than a filtered read.
	"""
	if not course_offering or not frappe.db.exists("Course Grade Scheme", course_offering):
		return None
	return frappe.get_doc("Course Grade Scheme", course_offering)


def is_scheme_driven(course_offering):
	return bool(course_offering) and frappe.db.exists(
		"Course Grade Scheme", course_offering
	)


def sync_components(registration):
	"""Mirror the offering's scheme onto one registration's components.

	Mutates the document and does not save it -- the caller decides when, and
	saving here would fight `compute_grade`, which runs on validate.

	Existing marks survive: a bucket is matched by its component name, so
	re-weighting a scheme or adding a bucket never disturbs a mark already
	entered. A bucket dropped from the scheme is removed only when it is
	empty; one carrying a mark is kept, because silently deleting somebody's
	score to tidy a table is not a trade worth making.
	"""
	scheme = scheme_for(registration.course_offering)
	if not scheme:
		return False

	existing = {row.component: row for row in registration.grade_components}
	wanted = [row.component for row in scheme.rows]

	kept = []
	for scheme_row in scheme.rows:
		row = existing.get(scheme_row.component)
		was_marked = int(bool(row and row.marked))
		kept.append(
			{
				"component": scheme_row.component,
				"weight_pct": flt(scheme_row.weight_pct),
				"max_marks": flt(row.max_marks) if row else DEFAULT_MAX_MARKS,
				# Never 0 for "nothing posted yet". The number cannot hold that
				# distinction -- the column is NOT NULL DEFAULT 0 -- so `marked`
				# is what compute_grade actually reads.
				"obtained_marks": row.obtained_marks if was_marked else None,
				"marked": was_marked,
				# Nothing computes a bucket any more. Assignments were the only
				# thing that did, and they are marked in Campus LMS Lite now,
				# which sends one released figure rather than feeding a bucket.
				# The two columns stay at zero rather than being dropped: they
				# are harmless, and removing a field from a live DocType is a
				# schema change earning nothing here.
				"auto_computed": 0,
				"source_assignments": 0,
			}
		)

	# A bucket the scheme no longer names, but somebody has marked.
	for component, row in existing.items():
		if component in wanted:
			continue
		if not row.marked:
			continue
		kept.append(
			{
				"component": component,
				"weight_pct": flt(row.weight_pct),
				"max_marks": flt(row.max_marks) or DEFAULT_MAX_MARKS,
				"obtained_marks": row.obtained_marks,
				"marked": 1,
				"auto_computed": 0,
				"source_assignments": 0,
			}
		)

	registration.set("grade_components", [])
	for row in kept:
		registration.append("grade_components", row)
	return True


def use_single_component(course_offering, component=LMS_COMPONENT):
	"""Grade an offering as one bucket worth the whole course.

	The shape a course taught in Campus LMS Lite needs. The LMS marks
	everything and releases one result, and `compute_grade` holds the letter
	back until *every* bucket is marked -- so with several buckets a single
	release can never finish a transcript, and somebody would have to type
	zeroes into the rest to make it complete.

	It used to refuse a bucket fed by a Course Assignment here, which was
	computed from posted scores and would have fought a mark arriving from the
	LMS. Assignments are set and marked over there now, so there is no longer
	such a thing as a bucket this gradebook fills by itself.

	Marks already entered are never thrown away. `sync_components` keeps a
	bucket that carries one, so a mid-term switch leaves those registrations
	with more than one bucket; they are counted and returned rather than
	quietly left for somebody to find at results time.
	"""
	if not frappe.db.exists("Course Offering", course_offering):
		frappe.throw(_("Course Offering {0} not found.").format(course_offering))

	scheme = scheme_for(course_offering)
	if not scheme:
		scheme = frappe.new_doc("Course Grade Scheme")
		scheme.course_offering = course_offering
	scheme.set("rows", [{"component": component, "weight_pct": 100}])
	# Saving the scheme rolls it onto every registration through sync_offering.
	scheme.save(ignore_permissions=True)

	kept = [
		name
		for name in frappe.get_all(
			"Course Registration", filters={"course_offering": course_offering}, pluck="name"
		)
		if frappe.db.count("Grade Component", {"parent": name, "parenttype": "Course Registration"}) > 1
	]
	return {
		"course_offering": course_offering,
		"component": component,
		"registrations_with_other_marks": kept,
	}


def sync_offering(course_offering):
	"""Bring every registration on an offering into step with its scheme.

	Called when a scheme changes. Saves each registration, because
	`compute_grade` runs on validate and the weights have moved.
	"""
	names = frappe.get_all(
		"Course Registration",
		filters={"course_offering": course_offering},
		pluck="name",
	)

	touched = 0
	for name in names:
		registration = frappe.get_doc("Course Registration", name)
		if sync_components(registration):
			registration.save(ignore_permissions=True)
			touched += 1
	return touched
