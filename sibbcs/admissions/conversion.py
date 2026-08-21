"""The conversion point: Admission Application -> enrolled Student.

Architecture doc §4 specifies six things that must happen together when the
admission fee is paid:

  1. Create Student with a student_id
  2. Create a Frappe User with role Student, send the welcome email
  3. Create Program Enrollment at current_level 1, applying any scholarship
  4. Create the Mentor record from the consent form
  5. Raise the ATA Registration invoice (M.Div only)
  6. Register the student for GEST O501 Orientation

Steps 4-6 depend on DocTypes that arrive in later phases (Mentor in Phase 6,
Fee Invoice in Phase 4, Course Registration in Phase 3). Rather than block
Phase 2 on them, each is attempted only if its DocType exists and is recorded
in the returned report as `deferred` otherwise. That keeps the conversion
honest -- it never silently claims to have done something it skipped -- and
means the same function completes itself as later phases land.

Atomicity: the caller runs inside Frappe's request transaction. Any exception
propagates and the whole conversion rolls back; we never commit halfway. The
one genuinely external effect is the welcome email, which is queued (not sent
inline) so a mail failure cannot leave a half-created student behind.
"""

import frappe
from frappe import _
from frappe.utils import add_years, flt, nowdate, today

DEFAULT_ORIENTATION_COURSE = "GEST O501"


def orientation_course():
	"""The course every new student is auto-registered for.

	Read from site config rather than hardcoded, so a site whose catalog uses a
	different code (or a demo catalog) can point at its own without a patch:

	    bench --site <site> set-config orientation_course_code "GEST O501"
	"""
	return frappe.conf.get("orientation_course_code") or DEFAULT_ORIENTATION_COURSE


def _deferred(report, step, reason):
	report["deferred"].append({"step": step, "reason": reason})


def convert(application_name, ignore_permissions=False):
	"""Turn an application into a Student. Idempotent.

	Returns a report dict describing what was created and what was deferred.
	"""
	app = frappe.get_doc("Admission Application", application_name)

	report = {
		"application": app.name,
		"created": {},
		"deferred": [],
		"already_converted": False,
	}

	if app.student:
		report["already_converted"] = True
		report["created"]["student"] = app.student
		return report

	_assert_ready(app)

	student = _create_student(app, ignore_permissions)
	report["created"]["student"] = student.name

	user = _create_user(student, app)
	if user:
		report["created"]["user"] = user
	else:
		_deferred(report, "user", "no email on the application")

	enrollment = _create_program_enrollment(app, student)
	report["created"]["program_enrollment"] = enrollment.name

	_create_mentor(app, student, report)
	_raise_ata_invoice(app, student, enrollment, report)
	_register_orientation(app, student, enrollment, report)

	app.db_set("student", student.name, update_modified=False)
	app.db_set("enrolled_on", frappe.utils.now_datetime(), update_modified=False)

	return report


def _fee_settled(app):
	"""Paid, or waived on the checklist.

	A waiver is a decision the Registrar records at step 10; it is not a
	payment, so `admission_fee_paid` stays false and a fee-paid-only check
	would make every waived candidate impossible to onboard.
	"""
	from sibbcs.admissions.checklist import NO, status_of

	return bool(app.admission_fee_paid) or status_of(app, NO["admission_fee"]) == "Waived"


def _assert_ready(app):
	"""Refuse to convert an application that has not cleared its gates."""
	if not _fee_settled(app):
		frappe.throw(
			_("The admission fee is neither paid nor waived."),
			title=_("Not Ready"),
		)

	if not app.program:
		frappe.throw(_("Application has no Program."), title=_("Not Ready"))

	existing = frappe.db.exists("Student", {"admission_application": app.name})
	if existing:
		frappe.throw(
			_("Student {0} was already created from this application.").format(existing),
			title=_("Already Converted"),
		)


def _create_student(app, ignore_permissions=False):
	student = frappe.get_doc(
		{
			"doctype": "Student",
			"full_name": app.full_name,
			"dob": app.dob,
			"gender": app.gender,
			"mobile": app.mobile,
			"whatsapp": app.whatsapp,
			"email": app.email,
			"address": app.address,
			"photo": app.photo,
			"admission_application": app.name,
			"status": "Active",
		}
	)
	student.insert(ignore_permissions=True)
	return student


def _create_user(student, app):
	"""One login, reused by Desk portal and LMS.

	If a User already exists for this email we link it rather than failing --
	re-applicants and staff-turned-students are both real cases.
	"""
	if not student.email:
		return None

	if frappe.db.exists("User", student.email):
		user_name = student.email
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": student.email,
				"first_name": student.full_name,
				"user_type": "Website User",
				"send_welcome_email": 1,
			}
		)

		# frappe's User.mobile_no carries a UNIQUE index, but shared phones are
		# ordinary here -- a married couple, a family handset, a church office
		# number. Copying the mobile unconditionally would make the second such
		# student impossible to enroll, so only claim a number nobody holds.
		# Student.mobile stays authoritative either way.
		if student.mobile and not frappe.db.exists("User", {"mobile_no": student.mobile}):
			user.mobile_no = student.mobile

		# queue, never send inline: a mail failure must not roll back enrollment
		user.flags.ignore_permissions = True
		user.insert(ignore_permissions=True)
		user_name = user.name

	user_doc = frappe.get_doc("User", user_name)
	if not any(r.role == "Student" for r in user_doc.roles):
		user_doc.append("roles", {"role": "Student"})
		user_doc.save(ignore_permissions=True)

	student.db_set("user", user_name, update_modified=False)
	return user_name


def _create_program_enrollment(app, student):
	program = frappe.get_doc("Program", app.program)

	expected_completion = None
	if program.max_years:
		expected_completion = add_years(nowdate(), int(flt(program.max_years)))

	enrollment = frappe.get_doc(
		{
			"doctype": "Program Enrollment",
			"student": student.name,
			"program": app.program,
			"enrollment_date": today(),
			"start_term": app.onboard_term or app.intake_term,
			# The level is the Registrar's decision at step 13, recorded in
			# `onboard_level`. This deliberately overrides architecture doc §4
			# ("always Level 1"): the college has since confirmed a candidate
			# may be admitted at any level 1-4. `entry_level` on the
			# application stays advisory, and Level 1 is the fallback when
			# nobody has decided.
			"current_level": app.onboard_level or "1",
			"status": "Active",
			"expected_completion": expected_completion,
		}
	)

	_apply_scholarship(app, enrollment)

	enrollment.flags.ignore_permissions = True
	enrollment.insert(ignore_permissions=True)
	return enrollment


def _apply_scholarship(app, enrollment):
	"""Copy an approved award onto the enrollment.

	`scholarship_total_cap` plus `scholarship_used_to_date` is what makes the
	flexible discount safe -- the Phase 4 tuition job stops discounting once the
	cumulative cap is reached, with nobody tracking it by hand.
	"""
	if not app.scholarship_request:
		return

	scholarship = frappe.db.get_value(
		"Scholarship Request",
		app.scholarship_request,
		["status", "monthly_discount", "approved_amount"],
		as_dict=True,
	)
	if not scholarship or scholarship.status != "Approved":
		return

	enrollment.scholarship_monthly_discount = flt(scholarship.monthly_discount)
	enrollment.scholarship_total_cap = flt(scholarship.approved_amount)
	enrollment.scholarship_used_to_date = 0


def _create_mentor(app, student, report):
	"""Mentor arrives in Phase 6; create it when the DocType exists."""
	if not frappe.db.exists("DocType", "Mentor"):
		_deferred(report, "mentor", "Mentor DocType arrives in Phase 6")
		return

	consent = next((c for c in app.mentor_consents if c.consented_on), None)
	if not consent:
		_deferred(report, "mentor", "no completed mentor consent on the application")
		return

	if frappe.db.exists("Mentor", {"email": consent.mentor_email}):
		report["created"]["mentor"] = frappe.db.get_value(
			"Mentor", {"email": consent.mentor_email}, "name"
		)
		return

	mentor = frappe.get_doc(
		{
			"doctype": "Mentor",
			"mentor_name": consent.mentor_name,
			"email": consent.mentor_email,
			"mobile": consent.mentor_mobile,
			"church": consent.church,
			"is_active": 1,
		}
	)
	mentor.insert(ignore_permissions=True)
	report["created"]["mentor"] = mentor.name


def _raise_ata_invoice(app, student, enrollment, report):
	"""ATA Registration, M.Div only. Fee Invoice arrives in Phase 4."""
	if not frappe.db.get_value("Program", app.program, "requires_ata_fee"):
		return

	if not frappe.db.exists("DocType", "Fee Invoice"):
		_deferred(report, "ata_invoice", "Fee Invoice DocType arrives in Phase 4")
		return

	# Delegate to the fee engine rather than hand-building an invoice: it owns
	# the amount, the program scoping and the not-billed-twice check, and it is
	# the version that is actually tested.
	from sibbcs.finance import fees

	invoice = fees.raise_ata_fee(student.name, enrollment.name, app.program)
	if invoice:
		report["created"]["ata_invoice"] = invoice.name
	else:
		_deferred(report, "ata_invoice", "already raised or fee type inactive")


def _register_orientation(app, student, enrollment, report):
	"""Auto-register GEST O501. Course Registration arrives in Phase 3."""
	if not frappe.db.exists("DocType", "Course Registration"):
		_deferred(report, "orientation", "Course Registration DocType arrives in Phase 3")
		return

	course = orientation_course()

	if not frappe.db.exists("Course", course):
		_deferred(report, "orientation", f"{course} is not in the course catalog")
		return

	offering = frappe.db.get_value(
		"Course Offering",
		{"course": course, "term": app.onboard_term or app.intake_term},
		"name",
	)
	if not offering:
		_deferred(
			report,
			"orientation",
			f"no {course} offering for term {app.onboard_term or app.intake_term}",
		)
		return

	registration = frappe.get_doc(
		{
			"doctype": "Course Registration",
			"program_enrollment": enrollment.name,
			"course_offering": offering,
			"registration_date": today(),
			"status": "Registered",
		}
	)
	registration.insert(ignore_permissions=True)
	report["created"]["orientation_registration"] = registration.name


def onboard(application_name):
	"""Step 13. The gated way in: convert, then record the step.

	`convert()` stays callable on its own -- it is what the fee-paid path and
	the tests use -- but step 13 is the one that must not run early, so the
	checklist gate is checked *before* a Student exists rather than after.
	Creating the record and then discovering the manual was never acknowledged
	would leave a half-onboarded candidate to unpick by hand.
	"""
	from sibbcs.admissions.checklist import NO, blocked_reason, set_status

	app = frappe.get_doc("Admission Application", application_name)

	if not app.student:
		reason = blocked_reason(app, NO["onboarding"])
		if reason:
			frappe.throw(reason, title=_("Not Ready to Onboard"))

	report = convert(application_name)

	app.reload()
	set_status(app, NO["onboarding"], "Onboarded")

	report["level"] = frappe.db.get_value(
		"Program Enrollment", report["created"].get("program_enrollment"), "current_level"
	)
	return report


@frappe.whitelist()
def onboard_application(application_name):
	"""Desk-callable step 13."""
	app = frappe.get_doc("Admission Application", application_name)
	app.check_permission("write")
	report = onboard(application_name)

	if report["already_converted"]:
		frappe.msgprint(
			_("Already onboarded -- Student {0}.").format(report["created"]["student"]),
			indicator="orange",
		)
		return report

	_report_msgprint(report, _("Onboarding Complete"))
	return report


def _report_msgprint(report, title):
	lines = [_("Created:")]
	for key, value in report["created"].items():
		lines.append(f"&nbsp;&nbsp;&bull; {frappe.unscrub(key)}: <b>{value}</b>")
	if report.get("level"):
		lines.append("<br>" + _("Enrolled at level <b>{0}</b>.").format(report["level"]))
	if report["deferred"]:
		lines.append("<br>" + _("Deferred to a later phase:"))
		for item in report["deferred"]:
			lines.append(f"&nbsp;&nbsp;&bull; {frappe.unscrub(item['step'])} — {item['reason']}")

	frappe.msgprint("<br>".join(lines), title=title, indicator="green")


@frappe.whitelist()
def convert_application(application_name):
	"""Desk-callable wrapper. Requires write access to the application."""
	app = frappe.get_doc("Admission Application", application_name)
	app.check_permission("write")
	report = convert(application_name)

	if report["already_converted"]:
		frappe.msgprint(
			_("Already converted -- Student {0}.").format(report["created"]["student"]),
			indicator="orange",
		)
		return report

	lines = [_("Created:")]
	for key, value in report["created"].items():
		lines.append(f"&nbsp;&nbsp;&bull; {frappe.unscrub(key)}: <b>{value}</b>")
	if report["deferred"]:
		lines.append("<br>" + _("Deferred to a later phase:"))
		for item in report["deferred"]:
			lines.append(f"&nbsp;&nbsp;&bull; {frappe.unscrub(item['step'])} — {item['reason']}")

	frappe.msgprint("<br>".join(lines), title=_("Enrollment Complete"), indicator="green")
	return report
