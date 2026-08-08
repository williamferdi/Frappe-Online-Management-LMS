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

	frappe.db.commit()

	print("Demo data ready.")
	print(f"  Terms      : {term}, {second}  (status Open)")
	print(f"  Courses    : {len(COURSES)}  (levels 1-4, one hard prerequisite)")
	print(f"  Instructors: {len(instructors)}")
	print(f"  Offerings  : {len(offerings)} per term, all Published, capacity 25")
	print(f"  Grade Scale: {scale}  (PROVISIONAL -- decisions #2/#3 still open)")
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
