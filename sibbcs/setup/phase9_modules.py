"""Modules: a course as an ordered sequence, with unlock rules.

    bench --site online.sibbc.org execute \\
        sibbcs.setup.phase9_modules.build

Idempotent.

Phase 1 gave a course its grading shape and Phase 2 made marking work. This is
the course as a student walks through it: modules holding items -- a lesson, a
piece of work, a page, a file, a link -- in an order somebody chose, with rules
about what has to be finished before the next thing opens.

**Content belongs to the Course; dates and sequence belong to the Offering.**
That split is already in the existing fields (`Course.lms_course` is content
shared across runs, `Course Offering.lms_batch` is one run), and it is what
makes a term roll over cheaply: create a new Offering, and the pages, files and
lessons come with it. So `Course Page` and `Course File` hang off Course, while
`Course Module` hangs off Course Offering.

**A module item is a DocType, not a child row**, for the same reason a rubric
criterion is: `Module Item Progress` has to Link to the item a student
finished, and a Link cannot point at a child row -- reordering a module would
break every progress record.

**A lesson item Links to `Course Lesson`, which belongs to the vendored LMS
app.** That is deliberate and is the whole "LMS as content store" arrangement:
we point at its content from our own structure rather than copying it, and we
never write to it.
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
STUDENT = "Student"

ITEM_TYPES = [
	"Lesson",
	"Assignment",
	"Page",
	"File",
	"URL",
	"Sub-header",
]

# What counts as having done a thing. Canvas's own vocabulary, because a
# teacher who has seen Canvas should not have to learn new words for it.
COMPLETION_RULES = [
	"Nothing",
	"View it",
	"Mark it done",
	"Hand it in",
	"Score at least",
]

PROGRESS_STATES = ["Not started", "In progress", "Complete"]


def _teaching_perms():
	"""Students read modules; only staff build them.

	Unlike a submission, a module is not confidential -- it is the shape of the
	course -- so Student gets read here. What a student may *reach* is decided
	by the unlock rules in `academic.modules`, not by row permissions.
	"""
	return [
		full(SM), full(COORDINATOR), full(FACULTY),
		read(REGISTRAR), read(FACILITATOR), read(STUDENT),
	]


# ---------------------------------------------------------------------------
# modules
# ---------------------------------------------------------------------------


def _module_prerequisite():
	return ensure_doctype(
		"Module Prerequisite",
		MODULE,
		istable=1,
		fields=[
			link("module", "Module", "Course Module", reqd=1, in_list_view=1),
		],
	)


def _course_module():
	return ensure_doctype(
		"Course Module",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["CM-.#####"], default="CM-.#####",
				   hidden=1, print_hide=1),
			link("course_offering", "Course Offering", "Course Offering", reqd=1),
			fetched("course_title", "Course", "course_offering.course_title"),
			f("title", "Title", "Data", reqd=1),
			column("cb_what"),
			f("position", "Position", "Int", default="0"),
			check("published", "Published", 0,
				  description="An unpublished module is invisible to students."),

			section("sb_rules", "When it opens"),
			f("unlock_at", "Unlocks At", "Datetime",
			  description="Before this the module is visible but locked."),
			check("require_sequential_progress", "Items must be done in order", 0),
			# The prerequisites table is added by `_module_prerequisite_field`
			# once its child DocType exists -- see the note there.
		],
		permissions=_teaching_perms(),
	)


def _module_prerequisite_field():
	"""Add the table after both sides exist.

	Course Module wants a table of Module Prerequisite; Module Prerequisite
	Links back to Course Module. Frappe checks that a Link names a real
	DocType, so neither can declare the other first.
	"""
	return add_fields(
		"Course Module",
		[table("prerequisites", "Requires", "Module Prerequisite")],
	)


def _course_module_item():
	return ensure_doctype(
		"Course Module Item",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["CMI-.#####"], default="CMI-.#####",
				   hidden=1, print_hide=1),
			link("module", "Module", "Course Module", reqd=1),
			# Carried so the permission query can filter without a join.
			fetched("course_offering", "Course Offering", "module.course_offering"),
			select("item_type", "Type", ITEM_TYPES, reqd=1, in_list_view=1),
			f("title", "Title", "Data", in_list_view=1,
			  description="Leave blank to use the name of the thing it points at."),
			column("cb_what"),
			f("position", "Position", "Int", default="0"),
			f("indent", "Indent", "Int", default="0"),
			check("published", "Published", 1),

			section("sb_target", "What it points at"),
			# The LMS holds the lesson content; we point at it rather than
			# copying it, and never write to it.
			link("lesson", "Lesson", "Course Lesson",
				 depends_on="eval:doc.item_type=='Lesson'"),
			link("assignment", "Assignment", "Course Assignment",
				 depends_on="eval:doc.item_type=='Assignment'"),
			link("page", "Page", "Course Page",
				 depends_on="eval:doc.item_type=='Page'"),
			column("cb_target"),
			link("file", "File", "Course File",
				 depends_on="eval:doc.item_type=='File'"),
			f("url", "Link", "Data", depends_on="eval:doc.item_type=='URL'"),

			section("sb_done", "What counts as done"),
			select("completion_requirement", "Requirement", COMPLETION_RULES,
				   default="Nothing"),
			column("cb_done"),
			f("min_score", "Minimum Score", "Float",
			  depends_on="eval:doc.completion_requirement=='Score at least'"),
		],
		permissions=_teaching_perms(),
	)


def _module_item_progress():
	return ensure_doctype(
		"Module Item Progress",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		fields=[
			select("naming_series", "Series", ["MIP-.#####"], default="MIP-.#####",
				   hidden=1, print_hide=1),
			link("module_item", "Item", "Course Module Item", reqd=1),
			fetched("course_offering", "Course Offering", "module_item.course_offering"),
			link("course_registration", "Registration", "Course Registration", reqd=1),
			column("cb_state"),
			select("status", "Status", PROGRESS_STATES, default="Not started"),
			f("completed_on", "Completed", "Datetime"),
			f("score", "Score", "Float"),
		],
		# Deliberately not in `records.ALLOWED` and no Student row: progress is
		# written by the endpoints a student's own session reaches, never by
		# generic CRUD, or completing somebody else's course is a POST away.
		permissions=[
			full(SM), full(COORDINATOR), full(FACULTY),
			read(REGISTRAR), read(FACILITATOR),
		],
	)


# ---------------------------------------------------------------------------
# pages and files -- content, so hung off the Course
# ---------------------------------------------------------------------------


def _course_page():
	return ensure_doctype(
		"Course Page",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["CPG-.#####"], default="CPG-.#####",
				   hidden=1, print_hide=1),
			link("course", "Course", "Course", reqd=1,
				 description="A page belongs to the course, so it survives into next term."),
			f("title", "Title", "Data", reqd=1),
			column("cb_what"),
			check("published", "Published", 0),
			section("sb_body"),
			f("body", "Body", "Text Editor"),
		],
		permissions=_teaching_perms(),
	)


def _course_file():
	return ensure_doctype(
		"Course File",
		MODULE,
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="title",
		fields=[
			section("sb_what"),
			select("naming_series", "Series", ["CFL-.#####"], default="CFL-.#####",
				   hidden=1, print_hide=1),
			link("course", "Course", "Course", reqd=1),
			f("title", "Title", "Data", reqd=1),
			column("cb_what"),
			# Self-linking, so a course's files can be foldered without a
			# second DocType that would only ever hold a name.
			link("folder", "Inside", "Course File",
				 description="Another Course File marked as a folder."),
			check("is_folder", "Is a folder", 0),
			section("sb_file"),
			f("file", "File", "Attach", depends_on="eval:!doc.is_folder"),
			f("description", "Description", "Small Text"),
		],
		permissions=_teaching_perms(),
	)


# ---------------------------------------------------------------------------


def build():
	# Pages and files first: Course Module Item Links to both, and Frappe
	# refuses a Link whose options do not name an existing DocType.
	_course_page()
	_course_file()
	_course_module()
	_module_prerequisite()
	_module_prerequisite_field()
	_course_module_item()
	_module_item_progress()

	frappe.db.commit()
	frappe.clear_cache()

	for name in (
		"Course Module", "Module Prerequisite", "Course Module Item",
		"Module Item Progress", "Course Page", "Course File",
	):
		print(f"  {name}: {'ok' if frappe.db.exists('DocType', name) else 'MISSING'}")
