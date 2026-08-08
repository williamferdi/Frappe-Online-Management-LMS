"""Phase 1 -- academic master DocTypes for the Academic module.

Run with:

    bench --site online.sibbc.org execute sibbcs.setup.phase1_academic.build

Idempotent: safe to re-run. Creation order matters because Link and Table
fields are validated against existing DocTypes on insert, so children are
created before the parents that embed them.

Deviations from SIBBCS_ERP_Architecture.md §2.2, all deliberate:

* `Course.programs` (Table MultiSelect -> Course Program Link) is an addition.
  The spec's Course has no program link, but Degree Audit has to know which
  courses count toward which program, and one course can serve several
  programs. Without this the audit in Phase 7 has nothing to evaluate against.
* `Weekday` + `Course Offering Weekday` exist only to give `zoom_days` a real
  Table MultiSelect target, since Frappe multiselects need a Link, not a
  Select.
* `Program Requirement.min_hours` is an addition -- the "Internship Hours"
  rule type needs a target figure, and `min_credits`/`min_courses` cannot
  express it.
"""

import frappe

from sibbcs.setup.schema import (
	add_fields,
	check,
	column,
	edit,
	ensure_doctype,
	ensure_module,
	ensure_role,
	f,
	fetched,
	full,
	link,
	multiselect,
	read,
	section,
	select,
	table,
)

MODULE = "Academic"

# Roles from architecture doc §7. Mentor is intentionally absent: mentors never
# log in, they use tokenised web forms (Phase 6).
ROLES = [
	"Registrar",
	"Admissions Officer",
	"Academic Coordinator",
	"Faculty",
	"Facilitator",
	"Formation Coordinator",
	"Accounts",
	"Student",
]

LEVELS = ["1", "2", "3", "4"]
DEPARTMENTS = ["BIST", "THST", "CHMI", "HIST", "REMI", "GEST"]
COURSE_TYPES = ["Core", "Elective", "Practicum", "General Studies"]
FORMATS = ["Pre-Recorded", "Zoom Live", "Residential"]

WEEKDAYS = [
	("Monday", 1),
	("Tuesday", 2),
	("Wednesday", 3),
	("Thursday", 4),
	("Friday", 5),
	("Saturday", 6),
	("Sunday", 7),
]


# ---------------------------------------------------------------------------
# 1. Weekday -- lookup so Course Offering.zoom_days can be a multiselect
# ---------------------------------------------------------------------------


def _weekday():
	ensure_doctype(
		"Weekday",
		MODULE,
		fields=[
			f("weekday_name", "Weekday", reqd=1, unique=1, in_list_view=1),
			f("day_index", "Day Index", "Int", in_list_view=1),
		],
		permissions=[full("System Manager"), read("Academic Coordinator")],
		autoname="field:weekday_name",
		naming_rule="By fieldname",
		sort_field="day_index",
		sort_order="ASC",
		allow_rename=0,
	)

	for name, index in WEEKDAYS:
		if not frappe.db.exists("Weekday", name):
			frappe.get_doc(
				{"doctype": "Weekday", "weekday_name": name, "day_index": index}
			).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# 2. Grade Scale (+ rows)
# ---------------------------------------------------------------------------


def _grade_scale():
	ensure_doctype(
		"Grade Scale Row",
		MODULE,
		istable=1,
		fields=[
			f("grade", "Grade", reqd=1, in_list_view=1, columns=2),
			f("min_pct", "Min %", "Float", reqd=1, in_list_view=1, columns=2),
			f("max_pct", "Max %", "Float", reqd=1, in_list_view=1, columns=2),
			f("grade_points", "Grade Points", "Float", in_list_view=1, columns=2),
			check("is_pass", "Is Pass", in_list_view=1, columns=2),
		],
	)

	ensure_doctype(
		"Grade Scale",
		MODULE,
		fields=[
			f("scale_name", "Scale Name", reqd=1, unique=1, in_list_view=1),
			check("is_default", "Is Default"),
			f(
				"pass_percentage",
				"Pass Percentage",
				"Float",
				default="60",
				description="Minimum aggregate percentage required to pass a course.",
			),
			f("description", "Description", "Small Text"),
			section("sb_bands", "Grade Bands"),
			table("grade_rows", "Grades", "Grade Scale Row"),
		],
		permissions=[
			full("System Manager"),
			edit("Registrar"),
			read("Academic Coordinator"),
			read("Faculty"),
		],
		autoname="field:scale_name",
		naming_rule="By fieldname",
	)


# ---------------------------------------------------------------------------
# 3. Program (+ requirements)
# ---------------------------------------------------------------------------


def _program():
	ensure_doctype(
		"Program Requirement",
		MODULE,
		istable=1,
		fields=[
			select(
				"rule_type",
				"Rule Type",
				[
					"Level Credits",
					"Elective Minimum",
					"Practicum",
					"Residential",
					"Internship Hours",
				],
				reqd=1,
				in_list_view=1,
				columns=2,
			),
			select(
				"level",
				"Level",
				[""] + LEVELS,
				in_list_view=1,
				columns=1,
				description="Leave blank for rules that are not level-specific.",
			),
			f("min_credits", "Min Credits", "Float", in_list_view=1, columns=2),
			f("min_courses", "Min Courses", "Int", in_list_view=1, columns=2),
			f(
				"min_hours",
				"Min Hours",
				"Int",
				in_list_view=1,
				columns=2,
				description="Used by the Internship Hours rule.",
			),
			f("notes", "Notes", "Small Text"),
		],
	)

	ensure_doctype(
		"Program",
		MODULE,
		fields=[
			section("sb_identity"),
			f("program_name", "Program Name", reqd=1, in_list_view=1),
			f("abbr", "Abbreviation", reqd=1, unique=1, in_list_view=1, length=16),
			column("cb_identity"),
			check("is_active", "Is Active", default=1),
			check(
				"requires_ata_fee",
				"Requires ATA Registration Fee",
				description="ATA registration is billed on enrollment for M.Div only.",
			),
			section("sb_structure", "Structure"),
			f("total_credits", "Total Credits", "Float"),
			f("total_courses", "Total Courses", "Int"),
			column("cb_structure"),
			f("min_years", "Min Years", "Float", precision="1"),
			f("max_years", "Max Years", "Float", precision="1"),
			f("internship_hours", "Internship Hours", "Int", default="0"),
			section("sb_requirements", "Graduation Requirements"),
			table("program_requirements", "Requirements", "Program Requirement"),
			section("sb_about", "About"),
			f("description", "Description", "Small Text"),
		],
		permissions=[
			full("System Manager"),
			full("Registrar"),
			read("Academic Coordinator"),
			read("Faculty"),
			read("Student"),
		],
		autoname="field:abbr",
		naming_rule="By fieldname",
		title_field="program_name",
		show_title_field_in_link=1,
		search_fields="program_name,abbr",
	)


# ---------------------------------------------------------------------------
# 4. Course (+ program links, + prerequisites added in a second pass)
# ---------------------------------------------------------------------------


def _course():
	ensure_doctype(
		"Course Program Link",
		MODULE,
		istable=1,
		fields=[link("program", "Program", "Program", reqd=1, in_list_view=1)],
	)

	ensure_doctype(
		"Course",
		MODULE,
		fields=[
			section("sb_identity"),
			f("course_code", "Course Code", reqd=1, unique=1, in_list_view=1),
			f("course_title", "Course Title", reqd=1, in_list_view=1),
			column("cb_identity"),
			check("is_active", "Is Active", default=1),
			section("sb_academic", "Academic"),
			f("credits", "Credits", "Float", reqd=1, default="3", in_list_view=1),
			select(
				"level",
				"Level",
				LEVELS,
				reqd=1,
				in_list_view=1,
				in_standard_filter=1,
				description=(
					"The course's own level. A student's level lives on Program "
					"Enrollment and is deliberately independent of this."
				),
			),
			column("cb_academic"),
			select(
				"course_type",
				"Course Type",
				COURSE_TYPES,
				reqd=1,
				in_standard_filter=1,
			),
			select("department", "Department", DEPARTMENTS, reqd=1, in_standard_filter=1),
			select("default_format", "Default Format", [""] + FORMATS),
			section("sb_programs", "Programs"),
			multiselect(
				"programs",
				"Counts Toward Programs",
				"Course Program Link",
				description="Which programs this course may satisfy requirements for.",
			),
			section("sb_lms", "LMS"),
			link("lms_course", "LMS Course", "LMS Course"),
			section("sb_about", "Description"),
			f("description", "Description", "Text Editor"),
		],
		permissions=[
			full("System Manager"),
			full("Academic Coordinator"),
			read("Registrar"),
			read("Faculty"),
			read("Student"),
		],
		autoname="field:course_code",
		naming_rule="By fieldname",
		title_field="course_title",
		show_title_field_in_link=1,
		search_fields="course_title,department,level",
	)

	# Course <-> Course Prerequisite is a definition cycle: create the child
	# (which links to Course) only once Course exists, then extend Course.
	ensure_doctype(
		"Course Prerequisite",
		MODULE,
		istable=1,
		fields=[
			link("prerequisite_course", "Prerequisite Course", "Course", reqd=1, in_list_view=1, columns=3),
			fetched(
				"prerequisite_course_title",
				"Title",
				"prerequisite_course.course_title",
				in_list_view=1,
				columns=4,
			),
			check(
				"is_hard",
				"Hard Prerequisite",
				in_list_view=1,
				columns=2,
				description="Hard prerequisites block registration until passed.",
			),
		],
	)

	add_fields(
		"Course",
		[
			section("sb_prerequisites", "Prerequisites"),
			table("course_prerequisites", "Prerequisites", "Course Prerequisite"),
		],
		insert_after="programs",
	)


# ---------------------------------------------------------------------------
# 5. Instructor
# ---------------------------------------------------------------------------


def _instructor():
	ensure_doctype(
		"Instructor Course",
		MODULE,
		istable=1,
		fields=[link("course", "Course", "Course", reqd=1, in_list_view=1)],
	)

	ensure_doctype(
		"Instructor",
		MODULE,
		fields=[
			section("sb_identity"),
			f(
				"naming_series",
				"Series",
				"Select",
				options="INS-.#####",
				default="INS-.#####",
				reqd=1,
				hidden=1,
			),
			f("full_name", "Full Name", reqd=1, in_list_view=1),
			link("user", "User", "User", description="Optional login for this instructor."),
			column("cb_identity"),
			f("email", "Email", "Data", options="Email", in_list_view=1),
			f("mobile", "Mobile", "Data", options="Phone"),
			section("sb_status"),
			check("is_facilitator", "Is Facilitator"),
			column("cb_status"),
			check("is_active", "Is Active", default=1),
			section("sb_teaching", "Teaching"),
			f("qualification", "Qualification", "Small Text"),
			multiselect("courses_qualified", "Courses Qualified", "Instructor Course"),
		],
		permissions=[
			full("System Manager"),
			full("Academic Coordinator"),
			read("Registrar"),
			read("Faculty"),
		],
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="full_name",
		show_title_field_in_link=1,
		search_fields="full_name,email",
	)


# ---------------------------------------------------------------------------
# 6. Academic Term
# ---------------------------------------------------------------------------


def _academic_term():
	ensure_doctype(
		"Academic Term",
		MODULE,
		fields=[
			section("sb_identity"),
			f("term_name", "Term Name", reqd=1, unique=1, in_list_view=1),
			f("term_code", "Term Code", in_list_view=1),
			column("cb_identity"),
			select(
				"status",
				"Status",
				["Planned", "Open", "Active", "Closed"],
				default="Planned",
				in_list_view=1,
				in_standard_filter=1,
			),
			f(
				"duration_months",
				"Duration (Months)",
				"Int",
				default="2",
				description="Drives the recurring tuition calculation in Phase 4.",
			),
			section("sb_dates", "Term Dates"),
			f("start_date", "Start Date", "Date", reqd=1, in_list_view=1),
			f("end_date", "End Date", "Date", reqd=1, in_list_view=1),
			column("cb_dates"),
			f("application_deadline", "Application Deadline", "Date"),
			f("registration_opens", "Registration Opens", "Date"),
			f("registration_closes", "Registration Closes", "Date"),
		],
		permissions=[
			full("System Manager"),
			full("Academic Coordinator"),
			read("Registrar"),
			read("Faculty"),
			read("Student"),
		],
		autoname="field:term_name",
		naming_rule="By fieldname",
		sort_field="start_date",
		sort_order="DESC",
	)


# ---------------------------------------------------------------------------
# 7. Course Offering
# ---------------------------------------------------------------------------


def _course_offering():
	ensure_doctype(
		"Course Offering Weekday",
		MODULE,
		istable=1,
		fields=[link("weekday", "Weekday", "Weekday", reqd=1, in_list_view=1)],
	)

	ensure_doctype(
		"Course Offering",
		MODULE,
		fields=[
			section("sb_identity"),
			link("course", "Course", "Course", reqd=1, in_list_view=1),
			fetched("course_title", "Course Title", "course.course_title", in_list_view=1),
			column("cb_identity"),
			link("term", "Term", "Academic Term", reqd=1, in_list_view=1, in_standard_filter=1),
			select(
				"status",
				"Status",
				["Draft", "Published", "Running", "Completed"],
				default="Draft",
				in_list_view=1,
				in_standard_filter=1,
			),
			section("sb_delivery", "Delivery"),
			select("format", "Format", FORMATS, reqd=1, in_standard_filter=1),
			link("instructor", "Instructor", "Instructor"),
			link(
				"facilitator",
				"Facilitator",
				"Instructor",
				description="Facilitators handle forums and attendance, never final grades.",
			),
			column("cb_delivery"),
			multiselect("zoom_days", "Zoom Days", "Course Offering Weekday"),
			f("zoom_time", "Zoom Time", "Time"),
			section("sb_capacity", "Capacity"),
			f("capacity", "Capacity", "Int", description="0 means unlimited."),
			column("cb_capacity"),
			f("enrolled_count", "Enrolled", "Int", read_only=1),
			section("sb_academic", "Academic (from Course)"),
			fetched("course_level", "Course Level", "course.level"),
			column("cb_academic"),
			fetched("credits", "Credits", "course.credits", fieldtype="Float"),
			section("sb_lms", "LMS"),
			link("lms_batch", "LMS Batch", "LMS Batch"),
		],
		permissions=[
			full("System Manager"),
			full("Academic Coordinator"),
			read("Registrar"),
			read("Faculty"),
			read("Facilitator"),
			read("Student"),
		],
		autoname="format:{course}-{term}",
		naming_rule="Expression",
		title_field="course_title",
		search_fields="course,term,instructor",
		sort_field="modified",
		sort_order="DESC",
	)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def build():
	"""Create the Academic module, roles and all Phase 1 master DocTypes."""
	ensure_module(MODULE)

	for role in ROLES:
		ensure_role(role)

	_weekday()
	_grade_scale()
	_program()
	_course()
	_instructor()
	_academic_term()
	_course_offering()

	frappe.db.commit()

	created = frappe.get_all(
		"DocType", filters={"module": MODULE}, pluck="name", order_by="name"
	)
	print(f"Academic module DocTypes ({len(created)}):")
	for name in created:
		print(f"  - {name}")
