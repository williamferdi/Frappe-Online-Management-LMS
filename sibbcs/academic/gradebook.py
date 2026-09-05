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
from frappe.utils import flt

DEFAULT_MAX_MARKS = 100


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


def auto_components(course_offering):
	"""Buckets that at least one assignment counts towards.

	A bucket with no assignment stays hand-markable: attendance and an offline
	paper are real, and the gradebook has nothing to say about them.
	"""
	if not course_offering:
		return set()
	return set(
		frappe.get_all(
			"Course Assignment",
			filters={"course_offering": course_offering},
			pluck="component",
		)
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

	automatic = auto_components(registration.course_offering)
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
				"auto_computed": int(scheme_row.component in automatic),
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
			# The marks carried across are the ones already stored, so this is
			# not a hand edit and must not be refused as one.
			registration.flags.gradebook_roll_up = True
			registration.save(ignore_permissions=True)
			touched += 1
	return touched


def _stored_marks(registration):
	"""What the components held before this save.

	Without this the guard cannot tell a mark somebody just typed from one
	that has been sitting there since before the bucket became computed --
	and `sync_offering` re-saves every registration, carrying those marks
	forward, so a guard that fires on both would make a scheme unsaveable.
	"""
	if registration.is_new():
		return {}
	return {
		row.component: (row.obtained_marks if row.marked else None)
		for row in frappe.get_all(
			"Grade Component",
			filters={"parent": registration.name, "parenttype": "Course Registration"},
			fields=["component", "obtained_marks", "marked"],
		)
	}


def refuse_hand_marks_on_automatic(registration):
	"""A hand-typed mark on a bucket the gradebook owns is data about to be lost.

	The next roll-up recomputes that bucket from posted submissions and writes
	over whatever was typed, so refusing now is kinder than losing it later.

	Only a *changed* mark is refused. A bucket that already carried a mark
	when it became computed keeps it until the roll-up replaces it, because
	throwing on an untouched row would mean nobody could save the record at
	all. The roll-up itself sets `flags.gradebook_roll_up`, which is the one
	way past this.
	"""
	if registration.flags.get("gradebook_roll_up"):
		return
	if not is_scheme_driven(registration.course_offering):
		return

	automatic = auto_components(registration.course_offering)
	if not automatic:
		return

	before = _stored_marks(registration)

	for row in registration.grade_components:
		if row.component not in automatic:
			continue
		if not row.marked or row.obtained_marks in (None, ""):
			continue
		was = before.get(row.component)
		if was not in (None, "") and flt(was) == flt(row.obtained_marks):
			continue
		frappe.throw(
			_(
				"{0} is marked from its assignments. Mark the assignments "
				"rather than typing a total here."
			).format(row.component),
			title=_("Computed Component"),
		)
