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


# ---------------------------------------------------------------------------
# the roll-up
# ---------------------------------------------------------------------------


def effective_score(submission, assignment=None):
	"""What a submission is worth after its late penalty.

	The penalty is applied here rather than written into `score`, so it can
	only ever be applied once: `score` stays the mark the marker gave, and
	re-saving, re-posting or re-rolling cannot compound the deduction.

	Excused work has no score at all -- it is left out of the total rather
	than counted as zero, which is the difference between "did not have to"
	and "did not".
	"""
	if submission.get("excused"):
		return None
	# `scored`, not the number: the column is NOT NULL DEFAULT 0, so an
	# unmarked submission reads back as a zero somebody could be given.
	if not submission.get("scored"):
		return None
	if submission.get("score") in (None, ""):
		return None

	score = flt(submission.get("score"))
	days = cint(submission.get("late_days"))
	if days <= 0:
		return score

	assignment = assignment or frappe.db.get_value(
		"Course Assignment",
		submission.get("assignment"),
		["late_policy", "late_penalty_pct_per_day"],
		as_dict=True,
	)
	if not assignment or assignment.get("late_policy") != "Accept with penalty":
		return score

	penalty = flt(assignment.get("late_penalty_pct_per_day")) * days
	# A penalty cannot take a mark below zero, and cannot turn into a bonus.
	return max(score * (1 - min(penalty, 100) / 100.0), 0.0)


def _posted_scores(course_offering, registration):
	"""Every posted score for one registration, grouped by component.

	Only posted. An unposted mark is one the marker has not stood behind yet,
	and rolling it into a total would show the student the number the posting
	policy exists to withhold.
	"""
	assignments = {
		row.name: row
		for row in frappe.get_all(
			"Course Assignment",
			filters={"course_offering": course_offering},
			fields=[
				"name", "component", "points_possible",
				"late_policy", "late_penalty_pct_per_day",
			],
		)
	}
	if not assignments:
		return {}

	by_component = {}
	for submission in frappe.get_all(
		"Assignment Submission",
		filters={
			"course_registration": registration,
			"assignment": ("in", list(assignments)),
			"posted": 1,
		},
		fields=[
			"name", "assignment", "score", "scored", "late_days", "excused",
		],
	):
		assignment = assignments[submission.assignment]
		earned = effective_score(submission, assignment)
		if earned is None:
			continue
		by_component.setdefault(assignment.component, []).append(
			(earned, flt(assignment.points_possible))
		)

	return by_component


def _bucket_percentage(pairs, drop_lowest=0):
	"""Earned over possible, as a percentage, dropping the worst few.

	Dropped by ratio rather than by raw score: a 4/5 is a better piece of work
	than a 40/100, and dropping the larger number because it is larger would
	be arithmetic pretending to be judgement.
	"""
	usable = [(earned, possible) for earned, possible in pairs if possible > 0]
	if not usable:
		return None

	if drop_lowest > 0 and len(usable) > drop_lowest:
		usable.sort(key=lambda pair: pair[0] / pair[1])
		usable = usable[drop_lowest:]

	possible = sum(pair[1] for pair in usable)
	if possible <= 0:
		return None
	return flt(sum(pair[0] for pair in usable) / possible * 100, 2)


def roll_up(registration):
	"""Turn posted submission scores into this registration's component marks.

	Mutates and saves the document. Sets `flags.gradebook_roll_up` so the
	guard against hand-typed marks on computed buckets does not refuse the
	gradebook's own writing.

	A bucket with no posted score is left **unmarked** rather than zero, so
	`compute_grade` goes on holding the letter back until the course is
	actually finished. That is the whole reason `marked` exists.
	"""
	if isinstance(registration, str):
		registration = frappe.get_doc("Course Registration", registration)

	scheme = scheme_for(registration.course_offering)
	if not scheme:
		return False

	sync_components(registration)

	scored = _posted_scores(registration.course_offering, registration.name)
	drops = {row.component: cint(row.drop_lowest) for row in scheme.rows}
	automatic = auto_components(registration.course_offering)

	for row in registration.grade_components:
		if row.component not in automatic:
			# Hand-marked buckets -- attendance, an offline paper -- are not
			# the gradebook's to touch.
			continue

		pairs = scored.get(row.component, [])
		percentage = _bucket_percentage(pairs, drops.get(row.component, 0))

		row.source_assignments = len(pairs)
		if percentage is None:
			row.obtained_marks = None
			row.marked = 0
		else:
			row.max_marks = row.max_marks or DEFAULT_MAX_MARKS
			row.obtained_marks = flt(percentage * flt(row.max_marks) / 100, 2)
			row.marked = 1

	registration.flags.gradebook_roll_up = True
	registration.save(ignore_permissions=True)
	return True


def roll_up_for_assignment(assignment):
	"""Re-roll every registration touched by one assignment.

	Called when a score is posted or withdrawn.
	"""
	offering = frappe.db.get_value("Course Assignment", assignment, "course_offering")
	if not offering or not is_scheme_driven(offering):
		return 0

	names = frappe.get_all(
		"Assignment Submission",
		filters={"assignment": assignment},
		pluck="course_registration",
	)

	rolled = 0
	for name in set(names):
		if roll_up(name):
			rolled += 1
	return rolled
