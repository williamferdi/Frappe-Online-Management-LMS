"""Work handed in, marked, and posted -- and the mark reaching the transcript.

    bench --site online.sibbc.org execute \\
        sibbcs.setup.phase8_submissions.build

Idempotent.

Phase 1 gave a course its shape. This is where a student's work arrives, a
marker scores it, and `gradebook.roll_up` turns a set of posted scores into
the `Grade Component` rows `compute_grade` has always read. The pipeline below
that -- the Grade Scale, `grade_points`, CGPA, the transcript -- is still
untouched.

**A submission is where the two halves join.** It links an assignment to a
`Course Registration`, which is the record already carrying the grade, so no
new path to a transcript is invented: a score reaches the same row a marker
used to type into.

**Posting is separate from marking, deliberately.** A mark a student sees
before the marker meant them to cannot be taken back, so `posted` is its own
field at permlevel 1, and the portal reads through endpoints that filter on
it rather than through the DocType. Students get no permission row on
Assignment Submission at all -- permlevel cannot express "you may read your
own score once it is posted", because Student holds level-1 read on Course
Registration and would inherit it here too.

**A rubric criterion is a standalone DocType, not a child row.** An assessment
has to Link to the criterion it scored, and a Link cannot point at a child
row -- it would break the moment the rubric was edited.
"""

import frappe

from sibbcs.setup.schema import (
	add_fields,
	check,
	column,
	ensure_doctype,
	f,
	fetched,
	full,
	level,
	link,
	read,
	section,
	select,
	table,
)

MODULE = "Academic"

SM = "System Manager"
REGISTRAR = "Registrar"
COORDINATOR = "Academic Coordinator"
FACULTY = "Faculty"
FACILITATOR = "Facilitator"

SUBMISSION_STATES = [
	"Draft",
	"Submitted",
	"Graded",
	"Returned",
	"Missing",
	"Excused",
]


def _teaching_perms(with_grades=False):
	"""Who may touch a piece of marking.

	No Student row, on purpose -- see the module docstring.
	"""
	rows = [
		full(SM), full(COORDINATOR), full(FACULTY),
		read(REGISTRAR), read(FACILITATOR),
	]
	if with_grades:
		rows += [
			level(SM, 1), level(COORDINATOR, 1), level(FACULTY, 1),
			level(REGISTRAR, 1, write=0), level(FACILITATOR, 1, write=0),
		]
	return rows


# ---------------------------------------------------------------------------
# rubrics
# ---------------------------------------------------------------------------


def _rubric_rating():
	return ensure_doctype(
		"Rubric Rating",
		MODULE,
		istable=1,
		fields=[
			f("title", "Rating", "Data", reqd=1, in_list_view=1),
			f("points", "Points", "Float", reqd=1, in_list_view=1),
			f("description", "What this looks like", "Small Text", in_list_view=1),
		],
	)


def _course_rubric():
	return ensure_doctype(
		"Course Rubric",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			select("naming_series", "Series", ["RUB-.#####"], default="RUB-.#####",
				   hidden=1, print_hide=1),
			f("title", "Title", "Data", reqd=1),
			link("course", "Course", "Course",
				 description="Leave blank for a rubric any course may use."),
			column("cb_head"),
			f("total_points", "Total Points", "Float", read_only=1),
			section("sb_about"),
			f("description", "Description", "Small Text"),
		],
		permissions=_teaching_perms(),
	)


def _rubric_criterion():
	return ensure_doctype(
		"Rubric Criterion",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			select("naming_series", "Series", ["RCR-.#####"], default="RCR-.#####",
				   hidden=1, print_hide=1),
			link("rubric", "Rubric", "Course Rubric", reqd=1),
			f("title", "Criterion", "Data", reqd=1),
			column("cb_head"),
			f("position", "Position", "Int", default="0"),
			f("points_possible", "Points", "Float", reqd=1),
			section("sb_about"),
			f("description", "Description", "Small Text"),
			section("sb_ratings", "Ratings"),
			table("ratings", "Ratings", "Rubric Rating"),
		],
		permissions=_teaching_perms(),
	)


def _rubric_assessment_row():
	return ensure_doctype(
		"Rubric Assessment Row",
		MODULE,
		istable=1,
		fields=[
			# A Link, which is why Rubric Criterion is a DocType of its own: a
			# child row cannot be linked to, and an assessment has to say which
			# criterion it scored even after the rubric is edited.
			link("criterion", "Criterion", "Rubric Criterion", reqd=1, in_list_view=1),
			fetched("criterion_title", "Criterion", "criterion.title", in_list_view=1),
			fetched("points_possible", "Out of", "criterion.points_possible", "Float"),
			f("points", "Points", "Float", in_list_view=1),
			f("comment", "Comment", "Small Text"),
		],
	)


# ---------------------------------------------------------------------------
# submissions
# ---------------------------------------------------------------------------


def _submission_attachment():
	return ensure_doctype(
		"Submission Attachment",
		MODULE,
		istable=1,
		fields=[
			f("file", "File", "Attach", reqd=1, in_list_view=1),
			f("file_name", "Name", "Data", in_list_view=1),
		],
	)


def _assignment_submission():
	return ensure_doctype(
		"Assignment Submission",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="student_name",
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["SUB-.#####"], default="SUB-.#####",
				   hidden=1, print_hide=1),
			link("assignment", "Assignment", "Course Assignment", reqd=1),
			fetched("assignment_title", "Title", "assignment.title"),
			# Carried rather than looked up: the permission query filters on it
			# on every list, and a join per row is a join too many.
			fetched("course_offering", "Course Offering", "assignment.course_offering"),
			fetched("component", "Counts Towards", "assignment.component"),
			fetched("points_possible", "Out of", "assignment.points_possible", "Float"),
			column("cb_what"),
			# The join to the grade pipeline. A score reaches a transcript
			# through the row a marker used to type into, not a new path.
			link("course_registration", "Registration", "Course Registration", reqd=1),
			fetched("student", "Student", "course_registration.student"),
			fetched("student_name", "Name", "course_registration.student_name"),
			f("attempt", "Attempt", "Int", default="1"),

			section("sb_state"),
			select("status", "Status", SUBMISSION_STATES, default="Draft", reqd=1),
			f("submitted_on", "Handed In", "Datetime"),
			column("cb_state"),
			f("late_days", "Days Late", "Int", read_only=1),
			check("excused", "Excused", 0,
				  description="Excused work is left out of the total rather than scored zero."),

			section("sb_work", "The work"),
			f("body", "Text", "Text Editor"),
			f("url", "Link", "Data"),
			table("attachments", "Files", "Submission Attachment"),

			# --- permlevel 1: the marking ---------------------------------
			section("sb_marking", "Marking"),
			f("score", "Score", "Float", permlevel=1),
			# `score` is decimal NOT NULL DEFAULT 0 and so cannot hold "nobody
			# has marked this" -- and a marker can legitimately give a zero.
			# This is the same distinction `Grade Component.marked` carries,
			# for the same reason.
			check("scored", "Scored", 0, permlevel=1, read_only=1),
			check("posted", "Posted", 0, permlevel=1,
				  description="Until this is set the student cannot see the score."),
			column("cb_marking"),
			link("graded_by", "Marked By", "User", read_only=1, permlevel=1),
			f("graded_on", "Marked On", "Datetime", read_only=1, permlevel=1),
			section("sb_feedback"),
			f("feedback", "Feedback", "Text Editor", permlevel=1),
			table("rubric_assessment", "Rubric", "Rubric Assessment Row", permlevel=1),
		],
		permissions=_teaching_perms(with_grades=True),
	)


# ---------------------------------------------------------------------------


def _assignment_rubric_field():
	"""Course Assignment could not carry this in Phase 1 -- Course Rubric did
	not exist, and a Link to a missing DocType fails on insert."""
	return add_fields(
		"Course Assignment",
		[
			link("rubric", "Rubric", "Course Rubric",
				 description="Optional. A rubric gives the marker criteria to score against."),
		],
	)


def _submission_scored_field():
	"""Added with add_fields, not in the definition above.

	`ensure_doctype` leaves an existing DocType alone -- deliberately, so that
	a re-run never discards a hand edit -- which means a field added after the
	first build has to come this way or it silently never appears. The first
	build of this phase had already run when `scored` was found to be needed.
	"""
	return add_fields(
		"Assignment Submission",
		[
			check(
				"scored",
				"Scored",
				0,
				permlevel=1,
				read_only=1,
				description=(
					"Whether this has been marked at all. Separate from the score "
					"because the score column is NOT NULL DEFAULT 0, so an "
					"untouched submission is indistinguishable from one marked zero."
				),
			),
		],
	)


def build():
	_rubric_rating()
	_course_rubric()
	_rubric_criterion()
	_rubric_assessment_row()
	_submission_attachment()
	_assignment_submission()
	_assignment_rubric_field()
	_submission_scored_field()

	frappe.db.commit()
	frappe.clear_cache()

	for name in (
		"Rubric Rating", "Course Rubric", "Rubric Criterion",
		"Rubric Assessment Row", "Submission Attachment", "Assignment Submission",
	):
		print(f"  {name}: {'ok' if frappe.db.exists('DocType', name) else 'MISSING'}")

	has_rubric = frappe.get_meta("Course Assignment").get_field("rubric")
	print("  Course Assignment.rubric:", "ok" if has_rubric else "MISSING")
