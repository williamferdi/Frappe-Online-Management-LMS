"""Student-facing registration API.

Everything here is scoped to the logged-in student's own enrollment. A student
can never register someone else, and never grants themselves an override --
`register` deliberately does not accept an override argument, so the rule engine
is the only thing deciding.
"""

import frappe
from frappe import _
from frappe.utils import today

from sibbcs.academic.eligibility import explain


def get_student(user=None):
	user = user or frappe.session.user
	if user == "Guest":
		return None
	return frappe.db.get_value("Student", {"user": user}, "name")


def get_enrollment(user=None):
	student = get_student(user)
	if not student:
		return None
	return frappe.db.get_value(
		"Program Enrollment", {"student": student, "status": "Active"}, "name"
	)


def _open_terms():
	return frappe.get_all(
		"Academic Term", filters={"status": ("in", ("Open", "Active"))}, pluck="name"
	)


def available_offerings(enrollment=None):
	"""Offerings the student could see, each annotated with an eligibility verdict.

	Returning blocked offerings *with a reason* is deliberate: "why can't I take
	this?" is the question the registrar otherwise fields by email.
	"""
	enrollment = enrollment or get_enrollment()
	if not enrollment:
		return []

	terms = _open_terms()
	if not terms:
		return []

	offerings = frappe.get_all(
		"Course Offering",
		filters={"term": ("in", terms), "status": ("in", ("Published", "Running"))},
		fields=[
			"name", "course", "course_title", "term", "format",
			"capacity", "enrolled_count", "zoom_time", "credits", "course_level",
		],
		order_by="term asc, course asc",
	)

	registered = set(
		frappe.get_all(
			"Course Registration",
			filters={
				"program_enrollment": enrollment,
				"status": ("in", ("Registered", "Active", "Completed")),
			},
			pluck="course_offering",
		)
	)

	rows = []
	for offering in offerings:
		offering["already_registered"] = offering.name in registered
		if offering["already_registered"]:
			offering["eligibility"] = {"allowed": False, "reason": _("Already registered")}
		else:
			offering["eligibility"] = explain(enrollment, offering.name)
		rows.append(offering)

	return rows


def my_registrations(enrollment=None):
	enrollment = enrollment or get_enrollment()
	if not enrollment:
		return []

	rows = frappe.get_all(
		"Course Registration",
		filters={"program_enrollment": enrollment},
		fields=[
			"name", "course", "course_title", "term", "status",
			"credits", "grade", "final_marks", "passed", "lms_enrollment_created",
			"registration_fee_invoice",
		],
		order_by="registration_date desc",
	)

	# The course opens on payment, so "why can I not see my course?" is
	# answered on this page rather than by email.
	for row in rows:
		row["fee"] = _fee_state(row.get("registration_fee_invoice"))

	return rows


def _fee_state(invoice):
	if not invoice:
		return {"invoice": None, "status": "Pending", "outstanding": 0, "settled": False,
		        "label": _("Fee not yet raised")}

	row = frappe.db.get_value(
		"Fee Invoice", invoice,
		["status", "outstanding_amount", "net_amount", "payment_link"],
		as_dict=True,
	) or {}
	settled = row.get("status") in ("Paid", "Waived", "Cancelled")
	return {
		"invoice": invoice,
		"status": row.get("status"),
		"outstanding": row.get("outstanding_amount") or 0,
		"amount": row.get("net_amount") or 0,
		"payment_link": row.get("payment_link"),
		"settled": settled,
		"label": _("Paid") if settled else _("Payment pending"),
	}


@frappe.whitelist()
def register(course_offering):
	"""Register the logged-in student for an offering.

	No override parameter, by design: a student cannot authorise their own
	cross-level exception. Only the rule engine decides.
	"""
	enrollment = get_enrollment()
	if not enrollment:
		frappe.throw(_("No active enrollment found for your account."), frappe.PermissionError)

	if not frappe.db.exists("Course Offering", course_offering):
		frappe.throw(_("Course Offering not found."))

	registration = frappe.get_doc(
		{
			"doctype": "Course Registration",
			"program_enrollment": enrollment,
			"course_offering": course_offering,
			"registration_date": today(),
			"status": "Registered",
		}
	)
	registration.insert(ignore_permissions=True)

	return {
		"registration": registration.name,
		"lms_ready": bool(registration.lms_enrollment_created),
	}


@frappe.whitelist()
def withdraw(registration):
	"""Withdraw from a course the student registered for."""
	enrollment = get_enrollment()
	doc = frappe.get_doc("Course Registration", registration)

	if doc.program_enrollment != enrollment:
		frappe.throw(_("That registration is not yours."), frappe.PermissionError)

	if doc.status in ("Completed", "Failed"):
		frappe.throw(_("A completed course cannot be withdrawn."))

	doc.status = "Withdrawn"
	doc.save(ignore_permissions=True)
	return {"registration": doc.name, "status": doc.status}


@frappe.whitelist()
def pay_registration(registration):
	"""A payment link for one registration fee, for the student's own row.

	Scoped to the caller's own enrollment: a registration name is guessable,
	and this returns a payable link.
	"""
	enrollment = get_enrollment()
	if not enrollment:
		frappe.throw(_("No active enrollment found for your account."), frappe.PermissionError)

	row = frappe.db.get_value(
		"Course Registration",
		registration,
		["program_enrollment", "registration_fee_invoice"],
		as_dict=True,
	)
	if not row or row.program_enrollment != enrollment:
		frappe.throw(_("Registration not found."), frappe.PermissionError)

	if not row.registration_fee_invoice:
		frappe.throw(
			_("The fee for this registration has not been raised yet. Please try "
			  "again shortly, or contact the Accounts Office."),
			title=_("Not Ready"),
		)

	invoice = frappe.db.get_value(
		"Fee Invoice",
		row.registration_fee_invoice,
		["status", "payment_link"],
		as_dict=True,
	)
	if invoice.status in ("Paid", "Waived", "Cancelled"):
		return {"settled": True, "url": None}

	if invoice.payment_link:
		return {"settled": False, "url": invoice.payment_link}

	from sibbcs.finance import gateway

	if not gateway.is_configured():
		frappe.throw(
			_("Online payment is not available yet. Please contact the Accounts "
			  "Office to settle this fee."),
			title=_("Payment Unavailable"),
		)

	url = gateway.create_payment_link(row.registration_fee_invoice)
	return {"settled": False, "url": url}
