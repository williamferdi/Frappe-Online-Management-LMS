"""Demo dataset for manual acceptance testing.

    bench --site online.sibbc.org execute sibbcs.setup.demo_data.seed
    bench --site online.sibbc.org execute sibbcs.setup.demo_data.purge

Everything created here is prefixed `DEMO` (course codes, term, instructor and
student names, grade scale) so `purge` can remove all of it without touching a
single real record. It deliberately does NOT touch the four real Programs or
the five real 2026 Academic Terms -- it makes its own term instead.

The catalog is a representative sample, not the real curriculum: it spans all
four levels and includes a hard prerequisite, so every branch of the §3 rule
engine can be exercised by hand.
"""

import frappe
from frappe.utils import add_days, flt, today

PREFIX = "DEMO"
TERM = "DEMO-TERM-A"
SECOND_TERM = "DEMO-TERM-B"
GRADE_SCALE = "DEMO Grade Scale"

# code, title, credits, level, type, department, format, prerequisites
COURSES = [
	("DEMO GEST501", "Orientation to Online Study", 3, "1", "General Studies", "GEST", "Pre-Recorded", []),
	("DEMO BIST502", "Introduction to the Old Testament", 3, "1", "Core", "BIST", "Zoom Live", [("DEMO GEST501", 1)]),
	("DEMO BIST503", "Introduction to the New Testament", 3, "2", "Core", "BIST", "Zoom Live", []),
	("DEMO CHMI504", "Pastoral Ministry", 2, "1", "Elective", "CHMI", "Pre-Recorded", []),
	("DEMO THST601", "Systematic Theology I", 3, "3", "Core", "THST", "Zoom Live", []),
	("DEMO THST701", "Advanced Theology Seminar", 3, "4", "Core", "THST", "Residential", []),
]

INSTRUCTORS = [
	("DEMO Rev. Daniel Raj", "demo.daniel@example.invalid", 0),
	("DEMO Mrs. Anita George", "demo.anita@example.invalid", 1),  # facilitator
]

# A provisional scale ONLY so grading can be exercised. The real letters, bands
# and grade points are open decisions #2 and #3 -- do not treat this as agreed.
GRADE_BANDS = [
	("A", 90, 100, 4.0, 1),
	("B", 80, 89.99, 3.0, 1),
	("C", 70, 79.99, 2.0, 1),
	("D", 60, 69.99, 1.0, 1),
	("F", 0, 59.99, 0.0, 0),
]


def _term(name, offset_days=0):
	if frappe.db.exists("Academic Term", name):
		return name
	start = add_days(today(), -7 + offset_days)
	frappe.get_doc(
		{
			"doctype": "Academic Term",
			"term_name": name,
			"term_code": name.replace("-", ""),
			"start_date": start,
			"end_date": add_days(start, 60),
			"application_deadline": add_days(start, -1),
			"registration_opens": add_days(start, -14),
			"registration_closes": add_days(start, 30),
			"duration_months": 2,
			"status": "Open",
		}
	).insert(ignore_permissions=True)
	return name


def _courses():
	for code, title, credits, level, ctype, dept, fmt, _prereqs in COURSES:
		if frappe.db.exists("Course", code):
			continue
		frappe.get_doc(
			{
				"doctype": "Course",
				"course_code": code,
				"course_title": title,
				"credits": credits,
				"level": level,
				"course_type": ctype,
				"department": dept,
				"default_format": fmt,
				"is_active": 1,
			}
		).insert(ignore_permissions=True)

	# second pass so prerequisites can point at courses defined later
	for code, _t, _c, _l, _ct, _d, _f, prereqs in COURSES:
		if not prereqs:
			continue
		doc = frappe.get_doc("Course", code)
		existing = {r.prerequisite_course for r in doc.course_prerequisites}
		changed = False
		for target, is_hard in prereqs:
			if target in existing or not frappe.db.exists("Course", target):
				continue
			doc.append(
				"course_prerequisites", {"prerequisite_course": target, "is_hard": is_hard}
			)
			changed = True
		if changed:
			doc.save(ignore_permissions=True)


def _instructors():
	names = []
	for full_name, email, is_facilitator in INSTRUCTORS:
		existing = frappe.db.get_value("Instructor", {"full_name": full_name})
		if existing:
			names.append(existing)
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Instructor",
				"full_name": full_name,
				"email": email,
				"is_facilitator": is_facilitator,
				"is_active": 1,
			}
		).insert(ignore_permissions=True)
		names.append(doc.name)
	return names


def _offerings(term, instructors):
	created = []
	for index, (code, _t, _c, _l, _ct, _d, fmt, _p) in enumerate(COURSES):
		name = f"{code}-{term}"
		if frappe.db.exists("Course Offering", name):
			created.append(name)
			continue

		payload = {
			"doctype": "Course Offering",
			"course": code,
			"term": term,
			"format": fmt,
			"status": "Published",
			"capacity": 25,
			"instructor": instructors[0] if instructors else None,
		}
		if fmt == "Zoom Live":
			payload["zoom_time"] = "19:00:00"
			payload["zoom_days"] = [{"weekday": "Monday"}, {"weekday": "Thursday"}]

		doc = frappe.get_doc(payload).insert(ignore_permissions=True)
		created.append(doc.name)
	return created


def _grade_scale():
	if frappe.db.exists("Grade Scale", GRADE_SCALE):
		return GRADE_SCALE
	doc = frappe.get_doc(
		{
			"doctype": "Grade Scale",
			"scale_name": GRADE_SCALE,
			"pass_percentage": 60,
			"is_default": 1,
			"description": (
				"PROVISIONAL, for testing only. Real letters, bands and grade "
				"points are open decisions #2 and #3."
			),
		}
	)
	for grade, low, high, points, is_pass in GRADE_BANDS:
		doc.append(
			"grade_rows",
			{
				"grade": grade,
				"min_pct": low,
				"max_pct": high,
				"grade_points": points,
				"is_pass": is_pass,
			},
		)
	doc.insert(ignore_permissions=True)
	return doc.name


def _lead():
	if frappe.db.exists("Lead", {"full_name": "DEMO Walk-in Enquiry"}):
		return
	frappe.get_doc(
		{
			"doctype": "Lead",
			"full_name": "DEMO Walk-in Enquiry",
			"mobile": "9000000100",
			"email": "demo.lead@example.invalid",
			"source": "WhatsApp",
			"program_interest": "MDIV" if frappe.db.exists("Program", "MDIV") else None,
			"status": "New",
		}
	).insert(ignore_permissions=True)


# A student to actually look at the portal with. Without one, seed() produces a
# catalog and nothing that exercises My Courses, Grades or the dashboard -- the
# portal renders its "no active enrollment" state and that is all you can see.
#
# The shape is chosen to exercise the interesting paths at once: two graded
# courses behind them, one registered and unpaid, one course whose prerequisite
# they have now met, and two above their level that the rule engine refuses
# with a reason.
STUDENT_EMAIL = "demo.ruth@example.invalid"
STUDENT_NAME = f"{PREFIX} Ruth Anandhi"

# course code -> component marks, as (component, weight %, max, obtained)
GRADED = {
	"DEMO GEST501": [
		("Assignment", 40, 100, 88),
		("Final Paper", 60, 100, 84),
	],
	"DEMO CHMI504": [
		("Assignment", 30, 100, 95),
		("Discussion Forum", 20, 100, 90),
		("Final Paper", 50, 100, 92),
	],
}


def _student_user():
	if frappe.db.exists("User", STUDENT_EMAIL):
		return STUDENT_EMAIL

	frappe.get_doc(
		{
			"doctype": "User",
			"email": STUDENT_EMAIL,
			"first_name": "Ruth",
			"last_name": "Anandhi",
			"send_welcome_email": 0,
			"roles": [{"role": "Student"}, {"role": "LMS Student"}],
		}
	).insert(ignore_permissions=True)
	return STUDENT_EMAIL


def _student():
	"""One enrolled student with history. Idempotent."""
	user = _student_user()

	student = frappe.db.get_value("Student", {"email": STUDENT_EMAIL}, "name")
	if not student:
		student = frappe.get_doc(
			{
				"doctype": "Student",
				"full_name": STUDENT_NAME,
				"email": STUDENT_EMAIL,
				"mobile": "+91 98400 11223",
				"whatsapp": "+91 98400 11223",
				"address": "12 Trichy Road, Coimbatore 641018",
				"dob": "1996-04-11",
				"gender": "Female",
				"status": "Active",
				"user": user,
			}
		).insert(ignore_permissions=True).name

	enrollment = frappe.db.get_value("Program Enrollment", {"student": student}, "name")
	if not enrollment:
		enrollment = frappe.get_doc(
			{
				"doctype": "Program Enrollment",
				"student": student,
				"program": "MDIV",
				"status": "Active",
				"enrollment_date": add_days(today(), -240),
				"start_term": TERM,
				"current_level": "2",
			}
		).insert(ignore_permissions=True).name

	_registrations(enrollment)
	return student, enrollment


def _register(enrollment, offering, status="Registered"):
	existing = frappe.db.get_value(
		"Course Registration",
		{"program_enrollment": enrollment, "course_offering": offering},
		"name",
	)
	if existing:
		return frappe.get_doc("Course Registration", existing)

	doc = frappe.get_doc(
		{
			"doctype": "Course Registration",
			"program_enrollment": enrollment,
			"course_offering": offering,
			"registration_date": add_days(today(), -60),
			"status": status,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _settle_completed_fees(enrollment):
	"""Pay for the finished courses, through a real Payment Entry.

	Fee Invoice derives paid_amount from the Payment Allocation rows
	pointing at it, so writing `status = Paid` onto the invoice is undone by
	its own validate(). The money has to arrive the way it does in life.

	Leaving every demo invoice unpaid would show three payment prompts and
	no course anyone can open, which is not what the screens are for."""
	completed = frappe.get_all(
		"Course Registration",
		filters={"program_enrollment": enrollment, "status": "Completed"},
		fields=["registration_fee_invoice", "student"],
	)
	owing = [
		row
		for row in completed
		if row.registration_fee_invoice
		and frappe.db.get_value("Fee Invoice", row.registration_fee_invoice, "status")
			!= "Paid"
	]
	if not owing:
		return

	allocations = []
	total = 0.0
	for row in owing:
		invoice = frappe.db.get_value(
			"Fee Invoice",
			row.registration_fee_invoice,
			["name", "net_amount", "outstanding_amount"],
			as_dict=True,
		)
		allocations.append(
			{
				"fee_invoice": invoice.name,
				"invoice_net": invoice.net_amount,
				"invoice_outstanding": invoice.outstanding_amount,
				"allocated_amount": invoice.outstanding_amount,
			}
		)
		total += float(invoice.outstanding_amount or 0)

	frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"student": owing[0].student,
			"amount": total,
			"received_on": add_days(today(), -70),
			"mode": "UPI",
			"reference_no": "DEMO-UPI-0001",
			"remarks": "DEMO seed payment",
			"allocations": allocations,
		}
	).insert(ignore_permissions=True)

def _registrations(enrollment):
	"""Two terms of history: graded work behind, live registrations ahead."""
	for code, components in GRADED.items():
		offering = frappe.db.get_value(
			"Course Offering", {"course": code, "term": TERM}, "name"
		)
		if not offering:
			continue

		doc = _register(enrollment, offering)
		if doc.grade:
			continue

		doc.set("grade_components", [])
		for component, weight, maximum, obtained in components:
			doc.append(
				"grade_components",
				{
					"component": component,
					"weight_pct": weight,
					"max_marks": maximum,
					"obtained_marks": obtained,
				},
			)
		doc.status = "Completed"
		# compute_grade() derives weighted_score, final_marks and the letter
		# from the scale, so only the raw marks are set here.
		doc.save(ignore_permissions=True)

	current = frappe.db.get_value(
		"Course Offering", {"course": "DEMO BIST503", "term": SECOND_TERM}, "name"
	)
	if current:
		_register(enrollment, current)

	_settle_completed_fees(enrollment)

	from sibbcs.academic.doctype.course_registration.course_registration import (
		refresh_enrollment_progress,
	)

	refresh_enrollment_progress(enrollment)


# Notices and a conversation, so Announcements and the Inbox have something in
# them. Every title carries the DEMO prefix so purge() can find them, and the
# audiences are chosen to prove the filtering rather than just to fill a page:
# one goes to everybody, one only to MDiv, one only to Level 4 -- and Ruth is a
# Level 2 MDiv student, so she should see the first two and never the third.
ANNOUNCEMENTS = [
	(
		"DEMO Chapel returns on Wednesdays",
		"General",
		"All Students",
		{},
		"<p>Weekly chapel resumes this Wednesday at 7:00 pm IST on Zoom. The link "
		"is on your calendar. Attendance is not marked, but the hour is worth "
		"keeping.</p>",
		1,
	),
	(
		"DEMO Reading week for M.Div. students",
		"Academic",
		"Programme",
		{"program": "MDIV"},
		"<p>There will be no live sessions during reading week. Assignments due "
		"that week move to the following Monday.</p><p>Use the time well.</p>",
		0,
	),
	(
		"DEMO Thesis submission deadline",
		"Urgent",
		"Level",
		{"level": "4"},
		"<p>Level 4 candidates must submit their thesis by the end of the month. "
		"Late submissions carry a one-grade penalty.</p>",
		0,
	),
]

MESSAGE_SUBJECT = "DEMO Welcome to the portal"
MESSAGE_BODY = (
	"<p>Dear Ruth,</p><p>Your account is now active. You can see your courses, "
	"grades and fees here, and reply to this message if anything looks wrong.</p>"
	"<p>The Registrar's office</p>"
)


def _announcements():
	"""Idempotent: matched on title, which carries the DEMO prefix."""
	if not frappe.db.exists("DocType", "Announcement"):
		return 0

	made = 0
	for title, category, audience, targets, body, pinned in ANNOUNCEMENTS:
		if frappe.db.exists("Announcement", {"title": title}):
			continue
		frappe.get_doc(
			{
				"doctype": "Announcement",
				"title": title,
				"category": category,
				"audience": audience,
				"body": body,
				"pinned": pinned,
				"published": 1,
				"publish_on": add_days(today(), -3),
				**targets,
			}
		).insert(ignore_permissions=True)
		_evidence(
			application.name,
			documents=len(DOCUMENT_TYPES) if "documents" in steps else 0,
			references=2 if "reference_1" in steps else 0,
			mentor="mentor_form" in steps,
		)

		made += 1
	return made


def _message(student_user):
	"""One conversation from the office, so the Inbox is not an empty box."""
	if not frappe.db.exists("DocType", "Portal Message"):
		return 0
	if frappe.db.exists("Portal Message", {"subject": MESSAGE_SUBJECT}):
		return 0

	frappe.get_doc(
		{
			"doctype": "Portal Message",
			"subject": MESSAGE_SUBJECT,
			"body": MESSAGE_BODY,
			"sender": "Administrator",
			"sent_on": add_days(today(), -2),
			"recipients": [{"recipient": student_user}],
		}
	).insert(ignore_permissions=True)
	return 1


# Candidates spread across the pipeline, so the admissions console has a funnel
# worth looking at rather than one bar. The steps advanced for each are named by
# their stable key, never by number -- the college has reordered these once
# already and will again.
APPLICANTS = [
	# name, program, workflow state, {step key: status}
	(
		"DEMO Anand Selvaraj",
		"MDIV",
		"Draft",
		{},
	),
	(
		"DEMO Grace Thangam",
		"MDIV",
		"In Review",
		{
			"application_review": "Approved",
			"documents": "Verified",
			"reference_1": "Request Sent",
			"reference_2": "Request Sent",
		},
	),
	(
		"DEMO Immanuel Raj",
		"MACS",
		"In Review",
		{
			"application_review": "Approved",
			"documents": "Verified",
			"reference_1": "Reviewed",
			"reference_2": "Reviewed",
			"mentor_form": "Verified",
			"lms_account": "Link Sent",
			"entrance_exam": "Passed",
			"interview": "Invite Sent",
		},
	),
	(
		"DEMO Deborah Vasanthi",
		"MDIV",
		"In Review",
		{
			"application_review": "Approved",
			"documents": "Verified",
			"reference_1": "Reviewed",
			"reference_2": "Reviewed",
			"mentor_form": "Verified",
			"lms_account": "Link Sent",
			"entrance_exam": "Passed",
			"interview": "Cleared",
			"admission_fee": "Paid",
			"decision": "Admitted",
			"manual_reading": "Sent",
		},
	),
	(
		"DEMO Joshua Prabhakaran",
		"GDCS",
		"Rejected",
		{
			"application_review": "Approved",
			"documents": "Verified",
			"entrance_exam": "Failed",
		},
	),
]


# Documents, references and a mentor form, so the admissions console has
# something to open. Only the candidates far enough along get them -- a Draft
# application with two completed references would misrepresent the workflow as
# much as an empty one misrepresents the screen.
DOCUMENT_TYPES = [
	"SSC/10th Mark Sheet",
	"HSLC/12th Mark Sheet",
	"Undergraduate Degree Certificate",
	"Personal Testimony",
	"National ID",
]

# Answers keyed by the reference form's own field names, so `format_answers`
# renders them under the real questions rather than as leftovers.
REFERENCE_ANSWERS = {
	"relationship": "Pastor",
	"known_duration": "4-6 years",
	"commitment_to_christ": "Strongly devoted, actively growing in faith",
	"ministry_involvement": "Very active (regular attendance, leadership, or service)",
	"leadership_potential": "Strong leadership, leads others effectively in ministry",
	"moral_character": "Excellent, a strong example of Christian integrity",
	"teamwork": "Excellent teamwork and relational skills",
	"discipline": "Very responsible and disciplined",
	"calling": "Yes, strongly convinced of their calling",
	"recommendation_choice": "I strongly recommend",
	"additional_comments": (
		"A dependable and teachable member of our congregation who has led the "
		"youth ministry for three years. I recommend them without reservation."
	),
}

MENTOR_ANSWERS = {
	"mentoring_experience": "Eight years mentoring ministry candidates",
	"prior_theological_education": "B.Th., Chennai",
	"denomination": "Baptist",
	"current_position": "Senior Pastor",
	"years_of_ministry": 18,
	"church": f"{PREFIX} Grace Baptist Church",
	"city": "Coimbatore",
	"state": "Tamil Nadu",
	"country": "India",
	"handbook_acknowledged": 1,
}


def _evidence(application, *, documents, references, mentor):
	"""Attach evidence to one application. Idempotent per child table."""
	import json

	doc = frappe.get_doc("Admission Application", application)
	changed = False

	if documents and not doc.get("application_documents"):
		for index, document_type in enumerate(DOCUMENT_TYPES[:documents]):
			doc.append(
				"application_documents",
				{
					"document_type": document_type,
					# No file: these are demo rows, and inventing a PDF that
					# claims to be somebody's mark sheet is worse than a blank.
					"verified": 1 if index < documents - 1 else 0,
					"verified_by": "Administrator" if index < documents - 1 else None,
				},
			)
		changed = True

	if references and not doc.get("reference_requests"):
		for index in range(references):
			replied = index < references - 1 if references > 1 else True
			doc.append(
				"reference_requests",
				{
					"referee_name": f"{PREFIX} Rev. Referee {index + 1}",
					"referee_email": f"referee{index + 1}@example.invalid",
					"referee_type": "Pastor-Mentor" if index == 0 else "Professor-Employer",
					"token": frappe.generate_hash(length=32),
					"sent_on": add_days(today(), -20),
					"submitted_on": add_days(today(), -12) if replied else None,
					"recommendation": "Strong" if replied else None,
					"response_json": json.dumps(REFERENCE_ANSWERS) if replied else None,
				},
			)
		changed = True

	if mentor and not doc.get("mentor_consents"):
		doc.append(
			"mentor_consents",
			{
				"mentor_name": f"{PREFIX} Rev. Daniel Raj",
				"mentor_email": "demo.daniel@example.invalid",
				"mentor_mobile": "+91 90000 12345",
				"token": frappe.generate_hash(length=32),
				"sent_on": add_days(today(), -20),
				"consented_on": add_days(today(), -11),
				**MENTOR_ANSWERS,
			},
		)
		changed = True

	if changed:
		doc.save(ignore_permissions=True)


def _applications():
	"""Applications at a spread of stages. Idempotent, matched on e-mail."""
	from sibbcs.admissions import checklist

	made = 0
	for full_name, program, state, steps in APPLICANTS:
		email = full_name.replace(f"{PREFIX} ", "").lower().replace(" ", ".")
		email = f"{email}@example.invalid"

		if frappe.db.exists("Admission Application", {"email": email}):
			continue

		application = frappe.get_doc(
			{
				"doctype": "Admission Application",
				"full_name": full_name,
				"email": email,
				"mobile": "+91 90000 0000%d" % (made % 10),
				"dob": "1994-07-15",
				"gender": "Male" if made % 2 == 0 else "Female",
				"program": program,
				"church_name": f"{PREFIX} Grace Baptist Church",
				"current_role": "Youth Pastor",
				"years_of_ministry": 3,
				"address": "Coimbatore, Tamil Nadu",
			}
		).insert(ignore_permissions=True)

		# Advance by stable key. `update_step` enforces the gates, so a status
		# that would need a prerequisite simply will not take -- which is the
		# behaviour worth demonstrating, not worth working around.
		for key, status in steps.items():
			try:
				checklist.update_step(application.name, checklist.NO[key], status)
			except Exception:
				frappe.log_error(title=f"demo checklist {application.name} {key}")

		if state != frappe.db.get_value("Admission Application", application.name, "workflow_state"):
			frappe.db.set_value(
				"Admission Application", application.name, "workflow_state", state
			)

		made += 1
	return made


def seed():
	"""Create the demo catalog. Idempotent."""
	term = _term(TERM)
	second = _term(SECOND_TERM, offset_days=60)
	_courses()
	instructors = _instructors()
	offerings = _offerings(term, instructors)
	_offerings(second, instructors)
	scale = _grade_scale()
	_lead()
	student, enrollment = _student()
	candidates = _applications()
	notices = _announcements()
	_message(STUDENT_EMAIL)

	frappe.db.commit()

	print("Demo data ready.")
	print(f"  Terms      : {term}, {second}  (status Open)")
	print(f"  Courses    : {len(COURSES)}  (levels 1-4, one hard prerequisite)")
	print(f"  Instructors: {len(instructors)}")
	print(f"  Offerings  : {len(offerings)} per term, all Published, capacity 25")
	print(f"  Grade Scale: {scale}  (PROVISIONAL -- decisions #2/#3 still open)")
	print(f"  Student    : {STUDENT_NAME} <{STUDENT_EMAIL}>  ({enrollment})")
	print(f"  Notices    : {len(ANNOUNCEMENTS)} announcements ({notices} new), 1 inbox message")
	print(f"  Applicants : {len(APPLICANTS)} across the pipeline ({candidates} new)")
	print("               set a password with sibbcs.setup.demo_data.set_student_password")
	print("")
	print("Remove it all again with:")
	print("  bench --site <site> execute sibbcs.setup.demo_data.purge")


def purge():
	"""Delete everything seed() created, plus anything derived from it.

	Matches on the DEMO prefix and on reserved test e-mail domains only, so a
	real record can never be caught by it.
	"""
	removed = {}

	def _drop(doctype, names):
		names = [n for n in names if n]
		for name in names:
			try:
				frappe.delete_doc(
					doctype, name, force=1, ignore_permissions=True, delete_permanently=True
				)
			except Exception:
				frappe.log_error(title=f"demo purge failed for {doctype} {name}")
		if names:
			removed[doctype] = removed.get(doctype, 0) + len(names)

	demo_terms = frappe.get_all(
		"Academic Term", filters={"name": ("like", f"{PREFIX}%")}, pluck="name"
	)
	demo_courses = frappe.get_all(
		"Course", filters={"name": ("like", f"{PREFIX}%")}, pluck="name"
	)
	demo_offerings = frappe.get_all(
		"Course Offering", filters={"course": ("in", demo_courses or [""])}, pluck="name"
	)

	# lms_sync creates an LMS Course per Course and an LMS Batch per offering
	# the moment a demo student registers. Collect them now, while the rows
	# holding the links still exist -- deleting the Course first strands them,
	# and a stray published course in the LMS is indistinguishable from a real
	# one by the time anybody notices.
	demo_lms_courses = [
		row.lms_course
		for row in frappe.get_all(
			"Course",
			filters={"name": ("in", demo_courses or [""])},
			fields=["name", "lms_course"],
		)
		if row.lms_course
	]
	demo_lms_batches = [
		row.lms_batch
		for row in frappe.get_all(
			"Course Offering",
			filters={"name": ("in", demo_offerings or [""])},
			fields=["name", "lms_batch"],
		)
		if row.lms_batch
	]

	# students created by demo conversions
	demo_students = [
		d.name
		for d in frappe.get_all("Student", fields=["name", "email", "full_name"])
		if (d.email or "").endswith("@example.invalid")
		or (d.full_name or "").startswith(PREFIX)
	]
	demo_enrollments = frappe.get_all(
		"Program Enrollment", filters={"student": ("in", demo_students or [""])}, pluck="name"
	)
	demo_registrations = frappe.get_all(
		"Course Registration",
		filters={"course_offering": ("in", demo_offerings or [""])},
		pluck="name",
	) + frappe.get_all(
		"Course Registration",
		filters={"program_enrollment": ("in", demo_enrollments or [""])},
		pluck="name",
	)
	demo_applications = [
		d.name
		for d in frappe.get_all("Admission Application", fields=["name", "email", "full_name"])
		if (d.email or "").endswith("@example.invalid")
		or (d.full_name or "").startswith(PREFIX)
	]
	demo_students_set = set(demo_students)

	# finance first -- it points at everything else
	_drop(
		"Payment Entry",
		frappe.get_all(
			"Payment Entry", filters={"student": ("in", demo_students or [""])}, pluck="name"
		),
	)
	_drop(
		"Fee Invoice",
		frappe.get_all(
			"Fee Invoice", filters={"student": ("in", demo_students or [""])}, pluck="name"
		),
	)
	_drop(
		"Level Promotion",
		frappe.get_all(
			"Level Promotion",
			filters={"program_enrollment": ("in", demo_enrollments or [""])},
			pluck="name",
		),
	)
	_drop("Course Registration", set(demo_registrations))
	_drop("Program Enrollment", demo_enrollments)
	_drop("Student", demo_students)

	for dt in ("Qualifying Exam Result", "Interview Record", "Scholarship Request"):
		_drop(
			dt,
			frappe.get_all(
				dt, filters={"application": ("in", demo_applications or [""])}, pluck="name"
			),
		)
	_drop("Admission Application", demo_applications)

	_drop("Course Offering", demo_offerings)
	_drop("Course", demo_courses)
	_drop("Academic Term", demo_terms)
	_drop("Grade Scale", frappe.get_all(
		"Grade Scale", filters={"name": ("like", f"{PREFIX}%")}, pluck="name"
	))
	_drop("Instructor", [
		d.name
		for d in frappe.get_all("Instructor", fields=["name", "full_name"])
		if (d.full_name or "").startswith(PREFIX)
	])
	# The LMS side, deepest first: an enrolment holds the batch, the batch
	# holds the course.
	for child, field, parents in (
		("LMS Batch Enrollment", "batch", demo_lms_batches),
		("LMS Enrollment", "course", demo_lms_courses),
		("LMS Course Progress", "course", demo_lms_courses),
	):
		_drop(
			child,
			frappe.get_all(
				child, filters={field: ("in", parents or [""])}, pluck="name"
			),
		)
	_drop("LMS Batch", demo_lms_batches)
	for lms_course in demo_lms_courses:
		_drop(
			"Course Lesson",
			frappe.get_all("Course Lesson", filters={"course": lms_course}, pluck="name"),
		)
		_drop(
			"Course Chapter",
			frappe.get_all("Course Chapter", filters={"course": lms_course}, pluck="name"),
		)
	_drop("LMS Course", demo_lms_courses)
	# Portal communications. Announcements are matched on the DEMO prefix in
	# the title; a message on its subject.
	if frappe.db.exists("DocType", "Announcement"):
		demo_notices = [
			row.name
			for row in frappe.get_all("Announcement", fields=["name", "title"])
			if (row.title or "").startswith(PREFIX)
		]
		_drop(
			"Announcement Read",
			frappe.get_all(
				"Announcement Read",
				filters={"announcement": ("in", demo_notices or [""])},
				pluck="name",
			),
		)
		_drop("Announcement", demo_notices)

	if frappe.db.exists("DocType", "Portal Message"):
		_drop(
			"Portal Message",
			[
				row.name
				for row in frappe.get_all("Portal Message", fields=["name", "subject"])
				if (row.subject or "").startswith(PREFIX)
			],
		)
	_drop("Lead", [
		d.name
		for d in frappe.get_all("Lead", fields=["name", "full_name"])
		if (d.full_name or "").startswith(PREFIX)
	])
	_drop("User", [
		d.name
		for d in frappe.get_all("User", fields=["name"])
		if d.name.endswith("@example.invalid")
	])

	frappe.db.commit()
	print("Purged:", removed or "nothing")


@frappe.whitelist()
def set_student_password(student, password):
	"""Set a demo student's login password.

	SMTP is not configured yet, so the welcome e-mail never arrives and there is
	otherwise no way to sign in as a student to test the portal. Restricted to
	System Manager, and refuses any student outside the demo set.
	"""
	frappe.only_for("System Manager")

	email, full_name = frappe.db.get_value("Student", student, ["email", "full_name"])
	if not (email or "").endswith("@example.invalid") and not (full_name or "").startswith(PREFIX):
		frappe.throw("This helper is for DEMO students only.")

	user = frappe.db.get_value("Student", student, "user")
	if not user:
		frappe.throw(f"{student} has no linked User.")

	from frappe.utils.password import update_password

	update_password(user, password)
	frappe.db.commit()
	return {"user": user}
