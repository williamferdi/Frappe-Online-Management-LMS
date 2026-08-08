"""Phase 3 -- Course Registration, Grade Component and Level Promotion.

    bench --site online.sibbc.org execute sibbcs.setup.phase3_registration.build

Idempotent.

Course Registration is the join between a student and one run of a course. It
is where the eligibility rule engine (§3) fires, where the LMS enrollment is
created (§6), and where the grade eventually lands (§5). A student's transcript
is simply their set of Completed registrations.
"""

import frappe

from sibbcs.setup.schema import (
	check,
	column,
	edit,
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

ACADEMIC = "Academic"
LEVELS = ["1", "2", "3", "4"]

GRADE_COMPONENTS = ["Assignment", "Discussion Forum", "Attendance", "Final Paper"]

REGISTRATION_STATUSES = [
	"Draft",
	"Registered",
	"Active",
	"Completed",
	"Withdrawn",
	"Failed",
]


def _grade_component():
	ensure_doctype(
		"Grade Component",
		ACADEMIC,
		istable=1,
		fields=[
			select("component", "Component", GRADE_COMPONENTS, reqd=1, in_list_view=1, columns=2),
			f("weight_pct", "Weight %", "Float", reqd=1, in_list_view=1, columns=2),
			f("max_marks", "Max Marks", "Float", default="100", in_list_view=1, columns=2),
			f("obtained_marks", "Obtained", "Float", in_list_view=1, columns=2),
			f(
				"weighted_score",
				"Weighted",
				"Float",
				read_only=1,
				in_list_view=1,
				columns=2,
				description="obtained / max * weight",
			),
		],
	)


def _course_registration():
	ensure_doctype(
		"Course Registration",
		ACADEMIC,
		fields=[
			section("sb_who", "Student"),
			link(
				"program_enrollment",
				"Program Enrollment",
				"Program Enrollment",
				reqd=1,
				in_list_view=1,
			),
			fetched("student", "Student", "program_enrollment.student", "Link", options="Student"),
			fetched("student_name", "Student Name", "program_enrollment.student_name", in_list_view=1),
			column("cb_who"),
			fetched("program", "Program", "program_enrollment.program", "Link", options="Program"),
			f(
				"level_at_registration",
				"Level at Registration",
				"Data",
				read_only=1,
				description="The student's sticky level when they registered. Kept for audit.",
			),
			section("sb_what", "Offering"),
			link("course_offering", "Course Offering", "Course Offering", reqd=1, in_list_view=1),
			fetched("course", "Course", "course_offering.course", "Link", options="Course"),
			fetched("course_title", "Course Title", "course_offering.course_title"),
			column("cb_what"),
			fetched("term", "Term", "course_offering.term", "Link", options="Academic Term",
			        in_standard_filter=1),
			fetched("credits", "Credits", "course_offering.credits", "Float"),
			f("registration_date", "Registration Date", "Date", reqd=1),
			section("sb_status", "Status"),
			select(
				"status",
				"Status",
				REGISTRATION_STATUSES,
				default="Draft",
				reqd=1,
				in_list_view=1,
				in_standard_filter=1,
			),
			column("cb_status"),
			check("lms_enrollment_created", "LMS Enrollment Created", read_only=1),
			section("sb_override", "Cross-level Override"),
			f(
				"override_reason",
				"Override Reason",
				"Small Text",
				description=(
					"Required when registering outside the normal level rules. "
					"Only an Academic Coordinator may authorise it."
				),
			),
			column("cb_override"),
			link("override_by", "Override By", "User", read_only=1),
			section("sb_grading", "Grading"),
			table("grade_components", "Grade Components", "Grade Component"),
			section("sb_result"),
			f("final_marks", "Final Marks %", "Float", read_only=1, permlevel=1),
			f("grade", "Grade", "Data", read_only=1, permlevel=1, in_list_view=1),
			column("cb_result"),
			f("grade_points", "Grade Points", "Float", read_only=1, permlevel=1),
			check("passed", "Passed", read_only=1, permlevel=1),
			section("sb_fee", "Fee"),
			link(
				"registration_fee_invoice",
				"Registration Fee Invoice",
				"Fee Invoice",
				read_only=1,
			)
			if frappe.db.exists("DocType", "Fee Invoice")
			else f(
				"registration_fee_invoice",
				"Registration Fee Invoice",
				"Data",
				read_only=1,
				description="Becomes a Link to Fee Invoice in Phase 4.",
			),
		],
		permissions=[
			full("System Manager"),
			full("Registrar"),
			full("Academic Coordinator"),
			edit("Faculty"),
			read("Facilitator"),
			read("Accounts"),
			read("Student"),
			# permlevel 1 -- only faculty and above may write a grade
			level("System Manager", 1),
			level("Registrar", 1),
			level("Academic Coordinator", 1),
			level("Faculty", 1),
			level("Facilitator", 1, write=0),
			level("Student", 1, write=0),
		],
		autoname="format:{program_enrollment}-{course_offering}",
		naming_rule="Expression",
		title_field="student_name",
		search_fields="student,course,term",
		sort_field="modified",
		sort_order="DESC",
	)


def _level_promotion():
	ensure_doctype(
		"Level Promotion",
		ACADEMIC,
		fields=[
			section("sb_who"),
			f(
				"naming_series",
				"Series",
				"Select",
				options="LPR-.YYYY.-.#####",
				default="LPR-.YYYY.-.#####",
				reqd=1,
				hidden=1,
			),
			link(
				"program_enrollment",
				"Program Enrollment",
				"Program Enrollment",
				reqd=1,
				in_list_view=1,
			),
			fetched("student_name", "Student", "program_enrollment.student_name", in_list_view=1),
			column("cb_who"),
			select("from_level", "From Level", LEVELS, reqd=1, in_list_view=1),
			select("to_level", "To Level", LEVELS, reqd=1, in_list_view=1),
			section("sb_evidence", "Evidence"),
			f("credits_at_promotion", "Credits at Promotion", "Float", read_only=1),
			f("courses_passed", "Courses Passed", "Int", read_only=1),
			column("cb_evidence"),
			link("approved_by", "Approved By", "User", read_only=1),
			f("approved_on", "Approved On", "Date", read_only=1),
			section("sb_remarks"),
			f("remarks", "Remarks", "Small Text"),
		],
		permissions=[
			full("System Manager"),
			full("Registrar"),
			full("Academic Coordinator"),
			read("Faculty"),
			read("Student"),
		],
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="student_name",
	)


def build():
	_grade_component()
	_course_registration()
	_level_promotion()

	frappe.db.commit()

	names = frappe.get_all(
		"DocType", filters={"module": ACADEMIC}, pluck="name", order_by="name"
	)
	print(f"Academic DocTypes ({len(names)}):")
	for name in names:
		print(f"  - {name}")
