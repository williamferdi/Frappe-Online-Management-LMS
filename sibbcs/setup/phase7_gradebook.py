"""The gradebook: a grade scheme and the assignments that feed it.

    bench --site online.sibbc.org execute \\
        sibbcs.setup.phase7_gradebook.build

Idempotent.

**Nothing here replaces the grade pipeline; it feeds it.** Canvas totals a
course as the sum over assignment groups of (earned / possible) x group
weight. `Course Registration.compute_grade` already totals the sum over grade
components of (obtained / max) x weight_pct. Those are the same formula, so a
Course Grade Scheme is an assignment-group table under another name, and the
gradebook's job is to write the `Grade Component` rows a human used to type.
`compute_grade`, `apply_grade_scale`, the Grade Scale, `grade_points`, CGPA
and the transcript are untouched.

That is also why there is no migration. `Grade Component.component` is a
Select whose options are only ever **appended**, so every stored row stays
valid, and `_component_choices()` reads the DocType rather than a list in the
front end, so it picks the new ones up for free. Two fields are added:
`auto_computed`, which defaults to 0 so every existing row correctly reads as
hand-entered, and `source_assignments`, so a marker can see where a number
came from.

A registration only becomes assignment-driven when somebody creates a Course
Grade Scheme for its offering. That is the whole migration: opt-in, per
offering, and reversed by deleting the scheme. Hand-typed marking goes on
working for attendance and offline papers, which is how it has to stay.

**Deferred on purpose.** `Course Assignment` carries no `rubric` or
`course_quiz` link yet -- Course Rubric arrives in Phase 2 and Course Quiz in
Phase 4, and a Link field pointing at a DocType that does not exist fails on
insert. Those phases add their own field with `add_fields`, which is what that
helper is for.
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

# Appended to the existing four, never reordered and never removed: a stored
# row naming a dropped option is a row that can no longer be read back.
NEW_COMPONENTS = ["Quiz", "Exam", "Participation", "Project", "Reading"]

SUBMISSION_TYPES = [
	"No Submission",
	"Text Entry",
	"File Upload",
	"URL",
	"On Paper",
]

LATE_POLICIES = ["Accept", "Accept with penalty", "Refuse"]

GRADING_TYPES = ["Points", "Percentage", "Complete/Incomplete"]

POSTING_POLICIES = ["Automatic", "Manual"]


def component_choices():
	"""The Select options as they stand, so the scheme cannot drift from the
	component table it has to roll up into."""
	options = frappe.get_meta("Grade Component").get_field("component").options or ""
	return [line.strip() for line in options.split("\n") if line.strip()]


# ---------------------------------------------------------------------------
# the existing child table, extended
# ---------------------------------------------------------------------------


def _extend_grade_component():
	meta = frappe.get_meta("Grade Component")
	field = meta.get_field("component")
	existing = [line.strip() for line in (field.options or "").split("\n") if line.strip()]

	missing = [choice for choice in NEW_COMPONENTS if choice not in existing]
	if missing:
		doc = frappe.get_doc("DocType", "Grade Component")
		for row in doc.fields:
			if row.fieldname == "component":
				row.options = "\n".join(existing + missing)
		doc.save(ignore_permissions=True)

	add_fields(
		"Grade Component",
		[
			check(
				"marked",
				"Marked",
				0,
				in_list_view=1,
				description=(
					"Whether this component has been marked at all. Separate from "
					"the score because a student can be given a genuine zero, and "
					"because the score column cannot hold a blank -- it is NOT NULL "
					"DEFAULT 0, so an unmarked component reads as 0 the moment it "
					"is read back."
				),
			),
			check(
				"auto_computed",
				"Computed from Assignments",
				0,
				read_only=1,
				description=(
					"Set by the gradebook. A hand-typed mark on this row would be "
					"overwritten by the next roll-up."
				),
			),
			f(
				"source_assignments",
				"Assignments Counted",
				"Int",
				read_only=1,
				description="How many posted assignment scores produced this mark.",
			),
		],
	)
	return bool(missing)


# ---------------------------------------------------------------------------
# the scheme
# ---------------------------------------------------------------------------


def _grade_scheme_row():
	return ensure_doctype(
		"Grade Scheme Row",
		MODULE,
		istable=1,
		fields=[
			select("component", "Component", component_choices(), reqd=1, in_list_view=1),
			f("weight_pct", "Weight %", "Float", reqd=1, in_list_view=1),
			f(
				"drop_lowest",
				"Drop Lowest",
				"Int",
				default="0",
				in_list_view=1,
				description="Discard this many of the lowest scores in the group.",
			),
			select(
				"posting_policy",
				"Posting Policy",
				POSTING_POLICIES,
				default="Manual",
				description=(
					"Manual holds a mark back until the marker posts it. It is the "
					"default because a mark a student sees before the marker meant "
					"them to cannot be taken back."
				),
			),
		],
	)


def _course_grade_scheme():
	return ensure_doctype(
		"Course Grade Scheme",
		MODULE,
		autoname="format:{course_offering}",
		naming_rule="Expression (old style)",
		title_field="course_title",
		fields=[
			section("sb_what"),
			link("course_offering", "Course Offering", "Course Offering", reqd=1, unique=1),
			fetched("course_title", "Course", "course_offering.course_title"),
			column("cb_what"),
			fetched("term", "Term", "course_offering.term", "Data"),
			f("total_weight", "Total Weight %", "Float", read_only=1),
			section("sb_rows", "Components"),
			table("rows", "Components", "Grade Scheme Row"),
		],
		permissions=[
			full(SM), full(COORDINATOR), full(FACULTY),
			read(REGISTRAR), read(FACILITATOR),
		],
	)


# ---------------------------------------------------------------------------
# the assignments
# ---------------------------------------------------------------------------


def _course_assignment():
	return ensure_doctype(
		"Course Assignment",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["CA-.#####"], default="CA-.#####",
				   hidden=1, print_hide=1),
			link("course_offering", "Course Offering", "Course Offering", reqd=1),
			fetched("course_title", "Course", "course_offering.course_title"),
			f("title", "Title", "Data", reqd=1, in_list_view=1),
			column("cb_what"),
			select("component", "Counts Towards", component_choices(), reqd=1,
				   in_list_view=1,
				   description="Which row of the grade scheme this score rolls into."),
			f("points_possible", "Points Possible", "Float", default="100", reqd=1,
			  in_list_view=1),
			select("grading_type", "Grading Type", GRADING_TYPES, default="Points"),

			section("sb_brief", "Brief"),
			f("description", "Description", "Text Editor"),

			section("sb_when", "Dates"),
			f("available_from", "Available From", "Datetime"),
			f("due_date", "Due", "Datetime", in_list_view=1),
			column("cb_when"),
			f("available_until", "Closes", "Datetime",
			  description="After this nothing is accepted, late policy or not."),

			section("sb_how", "Submission"),
			select("submission_type", "Submission Type", SUBMISSION_TYPES,
				   default="Text Entry", reqd=1),
			f("allowed_attempts", "Allowed Attempts", "Int", default="1",
			  description="0 means no limit."),
			column("cb_how"),
			select("late_policy", "Late Policy", LATE_POLICIES, default="Accept with penalty"),
			f("late_penalty_pct_per_day", "Late Penalty % per Day", "Float", default="0",
			  depends_on="eval:doc.late_policy=='Accept with penalty'"),

			section("sb_state"),
			check("published", "Published", 0,
				  description="Unpublished work is invisible to students."),
		],
		permissions=[
			full(SM), full(COORDINATOR), full(FACULTY),
			read(REGISTRAR), read(FACILITATOR),
		],
	)


# ---------------------------------------------------------------------------


def build():
	appended = _extend_grade_component()
	_grade_scheme_row()
	_course_grade_scheme()
	_course_assignment()

	frappe.db.commit()
	frappe.clear_cache()

	print("Grade Component:", "options appended" if appended else "options already present")
	for name in ("Grade Scheme Row", "Course Grade Scheme", "Course Assignment"):
		print(f"  {name}: {'ok' if frappe.db.exists('DocType', name) else 'MISSING'}")
	print("Components now:", ", ".join(component_choices()))
