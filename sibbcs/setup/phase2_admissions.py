"""Phase 2 -- Admissions DocTypes, plus the two Academic DocTypes the
conversion point produces.

Run with:

    bench --site online.sibbc.org execute sibbcs.setup.phase2_admissions.build

Idempotent. Creation order works around two definition cycles:

  Student.admission_application  <->  Admission Application.student
  Admission Application.scholarship_request  <->  Scholarship Request.application

Both are closed with a second pass (`add_fields`), same technique Phase 1 used
for Course <-> Course Prerequisite.

Student and Program Enrollment live in the **Academic** module, per
architecture doc §2.2, even though it is the admissions conversion that creates
them.
"""

import frappe

from sibbcs.setup.schema import (
	add_fields,
	check,
	column,
	edit,
	ensure_doctype,
	ensure_module,
	f,
	fetched,
	full,
	level,
	link,
	multiselect,
	read,
	section,
	select,
	table,
)

ADMISSIONS = "Admissions"
ACADEMIC = "Academic"

LEVELS = ["1", "2", "3", "4"]
GENDERS = ["", "Male", "Female"]

DOCUMENT_TYPES = [
	"10th Marksheet",
	"12th Marksheet",
	"Degree Certificate",
	"Degree Marksheet",
	"Testimony",
	"ID Proof",
	"Ministry Proof",
	"Photo",
]

LEAD_SOURCES = [
	"Phone",
	"WhatsApp",
	"Meta Ads",
	"Google Ads",
	"Referral",
	"Website",
]


# ---------------------------------------------------------------------------
# Academic additions: Student, Program Enrollment
# ---------------------------------------------------------------------------


def _student():
	ensure_doctype(
		"Student",
		ACADEMIC,
		fields=[
			section("sb_identity"),
			f(
				"naming_series",
				"Series",
				"Select",
				options="SIB-.YYYY.-.####",
				default="SIB-.YYYY.-.####",
				reqd=1,
				hidden=1,
			),
			f("full_name", "Full Name", reqd=1, in_list_view=1),
			f("dob", "Date of Birth", "Date"),
			select("gender", "Gender", GENDERS),
			column("cb_identity"),
			f("photo", "Photo", "Attach Image"),
			select(
				"status",
				"Status",
				["Active", "On Leave", "Graduated", "Withdrawn", "Dismissed"],
				default="Active",
				in_list_view=1,
				in_standard_filter=1,
			),
			section("sb_contact", "Contact"),
			f("mobile", "Mobile", "Data", options="Phone", in_list_view=1),
			f("whatsapp", "WhatsApp", "Data", options="Phone"),
			column("cb_contact"),
			f("email", "Email", "Data", options="Email", in_list_view=1),
			f("address", "Address", "Small Text"),
			section("sb_login", "Login"),
			link(
				"user",
				"User",
				"User",
				read_only=1,
				description="The single login this student uses for both Desk portal and LMS.",
			),
		],
		permissions=[
			full("System Manager"),
			full("Registrar"),
			read("Admissions Officer"),
			read("Academic Coordinator"),
			read("Faculty"),
			read("Accounts"),
			read("Formation Coordinator"),
		],
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="full_name",
		show_title_field_in_link=1,
		search_fields="full_name,email,mobile",
	)


def _program_enrollment():
	ensure_doctype(
		"Program Enrollment",
		ACADEMIC,
		fields=[
			section("sb_identity"),
			link("student", "Student", "Student", reqd=1, in_list_view=1),
			fetched("student_name", "Student Name", "student.full_name", in_list_view=1),
			link("program", "Program", "Program", reqd=1, in_list_view=1, in_standard_filter=1),
			column("cb_identity"),
			select(
				"status",
				"Status",
				["Active", "On Leave", "Completed", "Withdrawn", "Dismissed"],
				default="Active",
				in_list_view=1,
				in_standard_filter=1,
			),
			f("enrollment_date", "Enrollment Date", "Date", reqd=1),
			link("start_term", "Start Term", "Academic Term"),
			f("expected_completion", "Expected Completion", "Date"),
			section("sb_level", "Level"),
			select(
				"current_level",
				"Current Level",
				LEVELS,
				default="1",
				reqd=1,
				permlevel=1,
				in_list_view=1,
				description=(
					"The student's sticky level. Deliberately independent of the level of "
					"any course they sit. Only the Registrar and Academic Coordinator may "
					"change it, and every change should go through Level Promotion."
				),
			),
			section("sb_scholarship", "Scholarship"),
			f("scholarship_monthly_discount", "Monthly Discount", "Currency"),
			f("scholarship_total_cap", "Total Cap", "Currency"),
			column("cb_scholarship"),
			f(
				"scholarship_used_to_date",
				"Used to Date",
				"Currency",
				read_only=1,
				description="Incremented by the term tuition job; stops the discount at the cap.",
			),
			section("sb_progress", "Progress"),
			f("cgpa", "CGPA", "Float", read_only=1, precision="2"),
			column("cb_progress"),
			f("credits_earned", "Credits Earned", "Float", read_only=1),
		],
		permissions=[
			full("System Manager"),
			full("Registrar"),
			edit("Academic Coordinator"),
			read("Accounts"),
			read("Faculty"),
			# permlevel 1 gates current_level
			level("System Manager", 1),
			level("Registrar", 1),
			level("Academic Coordinator", 1),
		],
		autoname="format:{student}-{program}",
		naming_rule="Expression",
		title_field="student_name",
		search_fields="student,program",
	)


# ---------------------------------------------------------------------------
# Admission Application children
# ---------------------------------------------------------------------------


def _application_children():
	ensure_doctype(
		"Application Document",
		ADMISSIONS,
		istable=1,
		fields=[
			select("document_type", "Document Type", DOCUMENT_TYPES, reqd=1, in_list_view=1, columns=3),
			f("file", "File", "Attach", in_list_view=1, columns=3),
			check("verified", "Verified", in_list_view=1, columns=1),
			link("verified_by", "Verified By", "User", read_only=1, columns=2),
			f("remarks", "Remarks", "Small Text", columns=2),
		],
	)

	ensure_doctype(
		"Reference Request",
		ADMISSIONS,
		istable=1,
		fields=[
			f("referee_name", "Referee Name", reqd=1, in_list_view=1, columns=2),
			f("referee_email", "Referee Email", "Data", options="Email", reqd=1, in_list_view=1, columns=2),
			select(
				"referee_type",
				"Referee Type",
				["Pastor-Mentor", "Professor-Employer"],
				reqd=1,
				in_list_view=1,
				columns=2,
			),
			select(
				"recommendation",
				"Recommendation",
				["", "Strong", "Positive", "Neutral", "Negative"],
				read_only=1,
				in_list_view=1,
				columns=2,
			),
			section("sb_token"),
			f("token", "Token", read_only=1, no_copy=1),
			f("sent_on", "Sent On", "Datetime", read_only=1, no_copy=1),
			column("cb_token"),
			f("submitted_on", "Submitted On", "Datetime", read_only=1, no_copy=1),
			f("response_json", "Response", "Long Text", read_only=1, no_copy=1),
		],
	)

	ensure_doctype(
		"Mentor Consent",
		ADMISSIONS,
		istable=1,
		fields=[
			f("mentor_name", "Mentor Name", reqd=1, in_list_view=1, columns=2),
			f("mentor_email", "Mentor Email", "Data", options="Email", reqd=1, in_list_view=1, columns=3),
			f("mentor_mobile", "Mentor Mobile", "Data", options="Phone", columns=2),
			f("church", "Church", in_list_view=1, columns=2),
			section("sb_token"),
			f("token", "Token", read_only=1, no_copy=1),
			f("sent_on", "Sent On", "Datetime", read_only=1, no_copy=1),
			column("cb_token"),
			f("consented_on", "Consented On", "Datetime", read_only=1, no_copy=1),
			f("consent_file", "Consent File", "Attach", read_only=1, no_copy=1),
		],
	)

	ensure_doctype(
		"Interview Panel Member",
		ADMISSIONS,
		istable=1,
		fields=[link("user", "Panel Member", "User", reqd=1, in_list_view=1)],
	)


# ---------------------------------------------------------------------------
# Admission Application
# ---------------------------------------------------------------------------


def _admission_application():
	ensure_doctype(
		"Admission Application",
		ADMISSIONS,
		fields=[
			section("sb_applicant", "Applicant"),
			f(
				"naming_series",
				"Series",
				"Select",
				options="APP-.YYYY.-.#####",
				default="APP-.YYYY.-.#####",
				reqd=1,
				hidden=1,
			),
			f("full_name", "Full Name", reqd=1, in_list_view=1),
			f("dob", "Date of Birth", "Date"),
			f("age", "Age", "Int", read_only=1),
			select("gender", "Gender", GENDERS),
			column("cb_applicant"),
			f("mobile", "Mobile", "Data", options="Phone", reqd=1, in_list_view=1),
			f("whatsapp", "WhatsApp", "Data", options="Phone"),
			f("email", "Email", "Data", options="Email", reqd=1, in_list_view=1),
			section("sb_applicant_more"),
			f("address", "Address", "Small Text"),
			column("cb_applicant_more"),
			f("photo", "Photo", "Attach Image"),
			f("id_document", "ID Document", "Attach"),
			section("sb_ministry", "Ministry"),
			f("church_name", "Church"),
			f("current_role", "Current Role"),
			column("cb_ministry"),
			f("years_of_ministry", "Years of Ministry", "Int"),
			check("has_bachelors", "Has Bachelor's Degree"),
			f("ministry_experience_doc", "Ministry Experience Document", "Attach"),
			section("sb_program", "Program"),
			link("program", "Program", "Program", reqd=1, in_list_view=1, in_standard_filter=1),
			link("intake_term", "Intake Term", "Academic Term", in_standard_filter=1),
			column("cb_program"),
			select("entry_level", "Entry Level", LEVELS, default="1"),
			section("sb_workflow", "Status"),
			link(
				"workflow_state",
				"Workflow State",
				"Workflow State",
				read_only=1,
				in_list_view=1,
				in_standard_filter=1,
				no_copy=1,
			),
			section("sb_gates", "Gates"),
			check("application_fee_paid", "Application Fee Paid"),
			check("docs_verified", "Documents Verified", read_only=1),
			f("qualifying_exam_score", "Qualifying Exam Score", "Float", read_only=1),
			column("cb_gates"),
			select(
				"interview_outcome",
				"Interview Outcome",
				["", "Recommend", "Reject", "Defer"],
				read_only=1,
			),
			f("offer_sent_on", "Offer Sent On", "Date", read_only=1),
			check("admission_fee_paid", "Admission Fee Paid"),
			section("sb_documents", "Documents"),
			table("application_documents", "Documents", "Application Document"),
			section("sb_references", "References"),
			table("reference_requests", "Reference Requests", "Reference Request"),
			section("sb_mentor", "Mentor"),
			table("mentor_consents", "Mentor Consent", "Mentor Consent"),
			section("sb_outcome", "Outcome"),
			link("student", "Student", "Student", read_only=1, no_copy=1),
			column("cb_outcome"),
			f("enrolled_on", "Enrolled On", "Datetime", read_only=1, no_copy=1),
			section("sb_notes"),
			f("notes", "Internal Notes", "Text"),
		],
		permissions=[
			full("System Manager"),
			full("Admissions Officer"),
			full("Registrar"),
			read("Academic Coordinator"),
			read("Accounts"),
		],
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="full_name",
		show_title_field_in_link=1,
		search_fields="full_name,email,mobile,program",
		sort_field="modified",
		sort_order="DESC",
	)


# ---------------------------------------------------------------------------
# Scholarship, exam, interview, lead
# ---------------------------------------------------------------------------


def _scholarship_request():
	ensure_doctype(
		"Scholarship Request",
		ADMISSIONS,
		fields=[
			section("sb_subject", "Subject"),
			f(
				"naming_series",
				"Series",
				"Select",
				options="SCH-.YYYY.-.#####",
				default="SCH-.YYYY.-.#####",
				reqd=1,
				hidden=1,
			),
			link("application", "Admission Application", "Admission Application", in_list_view=1),
			link("student", "Student", "Student", in_list_view=1),
			column("cb_subject"),
			link("program", "Program", "Program", reqd=1),
			select(
				"status",
				"Status",
				["Draft", "Submitted", "Approved", "Rejected"],
				default="Draft",
				in_list_view=1,
				in_standard_filter=1,
			),
			section("sb_request", "Request"),
			f("requested_amount", "Requested Amount", "Currency"),
			f("justification", "Justification", "Text"),
			section("sb_approval", "Approval"),
			f(
				"approved_amount",
				"Approved Total",
				"Currency",
				description="Total value of the award. Copied to Program Enrollment as the cap.",
			),
			f(
				"monthly_discount",
				"Monthly Discount",
				"Currency",
				description="Deducted from each month of tuition until the total cap is reached.",
			),
			column("cb_approval"),
			link("approved_by", "Approved By", "User", read_only=1),
			f("approved_on", "Approved On", "Date", read_only=1),
		],
		permissions=[
			full("System Manager"),
			full("Registrar"),
			edit("Admissions Officer"),
			read("Accounts"),
		],
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
	)


def _qualifying_exam_result():
	ensure_doctype(
		"Qualifying Exam Result",
		ADMISSIONS,
		fields=[
			section("sb_subject"),
			f(
				"naming_series",
				"Series",
				"Select",
				options="QER-.YYYY.-.#####",
				default="QER-.YYYY.-.#####",
				reqd=1,
				hidden=1,
			),
			link(
				"application",
				"Admission Application",
				"Admission Application",
				reqd=1,
				in_list_view=1,
			),
			fetched("applicant_name", "Applicant", "application.full_name", in_list_view=1),
			column("cb_subject"),
			f("conducted_on", "Conducted On", "Date"),
			f(
				"pass_mark",
				"Pass Mark %",
				"Float",
				default="60",
				description="Architecture doc confirms 60%.",
			),
			section("sb_scores", "Scores"),
			f("english_score", "English", "Float"),
			f("bible_score", "Bible", "Float"),
			column("cb_scores"),
			f("theology_score", "Theology", "Float"),
			f("ministry_score", "Ministry", "Float"),
			section("sb_result", "Result"),
			f("total", "Total", "Float", read_only=1, in_list_view=1),
			column("cb_result"),
			select("result", "Result", ["", "Pass", "Fail"], read_only=1, in_list_view=1),
		],
		permissions=[
			full("System Manager"),
			full("Admissions Officer"),
			read("Registrar"),
			read("Academic Coordinator"),
		],
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
	)


def _interview_record():
	ensure_doctype(
		"Interview Record",
		ADMISSIONS,
		fields=[
			section("sb_subject"),
			f(
				"naming_series",
				"Series",
				"Select",
				options="INT-.YYYY.-.#####",
				default="INT-.YYYY.-.#####",
				reqd=1,
				hidden=1,
			),
			link(
				"application",
				"Admission Application",
				"Admission Application",
				reqd=1,
				in_list_view=1,
			),
			fetched("applicant_name", "Applicant", "application.full_name", in_list_view=1),
			column("cb_subject"),
			f("scheduled_on", "Scheduled On", "Datetime"),
			select(
				"outcome",
				"Outcome",
				["", "Recommend", "Reject", "Defer"],
				in_list_view=1,
				in_standard_filter=1,
			),
			section("sb_panel", "Panel"),
			multiselect("panel", "Panel", "Interview Panel Member"),
			section("sb_notes", "Notes"),
			f("notes", "Notes", "Text"),
		],
		permissions=[
			full("System Manager"),
			full("Admissions Officer"),
			read("Registrar"),
			read("Academic Coordinator"),
		],
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
	)


def _lead():
	ensure_doctype(
		"Lead",
		ADMISSIONS,
		fields=[
			section("sb_identity"),
			f(
				"naming_series",
				"Series",
				"Select",
				options="LEAD-.YYYY.-.#####",
				default="LEAD-.YYYY.-.#####",
				reqd=1,
				hidden=1,
			),
			f("full_name", "Full Name", reqd=1, in_list_view=1),
			f("mobile", "Mobile", "Data", options="Phone", in_list_view=1),
			f("email", "Email", "Data", options="Email"),
			column("cb_identity"),
			select("source", "Source", [""] + LEAD_SOURCES, in_standard_filter=1),
			link("program_interest", "Program Interest", "Program"),
			select(
				"status",
				"Status",
				["New", "Contacted", "Applied", "Dropped"],
				default="New",
				in_list_view=1,
				in_standard_filter=1,
			),
			section("sb_followup", "Follow-up"),
			link("owner_officer", "Owner Officer", "User"),
			link(
				"application",
				"Application",
				"Admission Application",
				read_only=1,
				description="Set when this lead becomes an application.",
			),
			section("sb_notes"),
			f("notes", "Notes", "Text"),
		],
		permissions=[
			full("System Manager"),
			full("Admissions Officer"),
			read("Registrar"),
		],
		autoname="naming_series:",
		naming_rule='By "Naming Series" field',
		title_field="full_name",
		show_title_field_in_link=1,
		search_fields="full_name,mobile,email",
	)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def build():
	ensure_module(ADMISSIONS)

	# Academic side first -- Admission Application links to Student.
	_student()
	_program_enrollment()

	_application_children()
	_admission_application()

	# close the Student <-> Admission Application cycle
	add_fields(
		"Student",
		[
			link(
				"admission_application",
				"Admission Application",
				"Admission Application",
				read_only=1,
			)
		],
		insert_after="user",
	)

	_scholarship_request()

	# close the Admission Application <-> Scholarship Request cycle
	add_fields(
		"Admission Application",
		[link("scholarship_request", "Scholarship Request", "Scholarship Request", read_only=1)],
		insert_after="student",
	)

	_qualifying_exam_result()
	_interview_record()
	_lead()

	frappe.db.commit()

	for module in (ADMISSIONS, ACADEMIC):
		names = frappe.get_all(
			"DocType", filters={"module": module}, pluck="name", order_by="name"
		)
		print(f"{module} DocTypes ({len(names)}):")
		for name in names:
			print(f"  - {name}")
