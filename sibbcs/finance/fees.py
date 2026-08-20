"""The fee engine -- architecture doc §5.

Four independent streams. They are never merged into one invoice, because a
student can legitimately owe an application fee, a registration fee and a
tuition instalment at the same time, each with its own due date and its own
answer to "has this been paid".

  Stream 1  one-time         lifecycle events: application, admission, ATA, graduation
  Stream 2  per-registration Rs350 on every Course Registration, NOT discountable
  Stream 3  recurring        the paused tuition subscription, billed per active term
  Stream 4  scholarship      caps the discount stream 3 may apply

Tuition ceiling (open decision #1, answered "cap at Rs54,000, pay-as-you-go"):
tuition bills only in terms where the student registered at least one course,
and stops once `Program.tuition_total` has been billed. The ceiling is measured
against **gross** tuition by default (`Program.cap_on_gross`) -- see
`tuition_billed_to_date` for why measuring it against net would quietly cancel
out every scholarship.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate, today

APPLICATION_FEE = "Application Fee"
ADMISSION_FEE = "Admission Fee"
REGISTRATION_FEE = "Course Registration Fee"
TUITION_FEE = "Monthly Tuition"
ATA_FEE = "ATA Registration"
GRADUATION_FEE = "Graduation & Transcript"

DEFAULT_DUE_DAYS = 14

ACTIVE_REGISTRATION_STATUSES = ("Registered", "Active", "Completed")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def get_fee_type(fee_name):
	if not frappe.db.exists("Fee Type", fee_name):
		return None
	fee_type = frappe.get_cached_doc("Fee Type", fee_name)
	return fee_type if fee_type.is_active else None


def fee_applies_to_program(fee_type, program):
	"""A Fee Type with no program list applies everywhere."""
	programs = [r.program for r in fee_type.applies_to_programs]
	return program in programs if programs else True


def _existing_invoice(filters):
	return frappe.db.exists("Fee Invoice", filters)


def create_invoice(
	student,
	fee_name,
	gross=None,
	discount=0,
	due_date=None,
	program_enrollment=None,
	term=None,
	course_registration=None,
	months_billed=None,
	remarks=None,
):
	"""Raise one invoice. Callers are responsible for idempotency checks."""
	fee_type = get_fee_type(fee_name)
	if not fee_type:
		return None

	invoice = frappe.get_doc(
		{
			"doctype": "Fee Invoice",
			"student": student,
			"program_enrollment": program_enrollment,
			"fee_type": fee_name,
			"term": term,
			"course_registration": course_registration,
			"months_billed": months_billed,
			"gross_amount": flt(gross if gross is not None else fee_type.default_amount),
			"discount_amount": flt(discount) if fee_type.discountable else 0,
			"due_date": due_date or add_days(today(), DEFAULT_DUE_DAYS),
			"status": "Unpaid",
			"remarks": remarks,
		}
	)
	invoice.insert(ignore_permissions=True)
	return invoice


# ---------------------------------------------------------------------------
# stream 1 -- one-time lifecycle fees
# ---------------------------------------------------------------------------


def raise_application_fee(application):
	"""§5 Stream 1 -- the Rs350 fee that gates `Draft -> Submitted`.

	Raised against the Admission Application, not a Student: the applicant does
	not become a Student until the conversion point, several states later.
	"""
	fee_type = get_fee_type(APPLICATION_FEE)
	if not fee_type:
		return None

	existing = frappe.db.exists(
		"Fee Invoice",
		{"admission_application": application, "fee_type": APPLICATION_FEE,
		 "status": ("!=", "Cancelled")},
	)
	if existing:
		return frappe.get_doc("Fee Invoice", existing)

	app = frappe.db.get_value(
		"Admission Application", application, ["full_name", "program"], as_dict=True
	)

	invoice = frappe.get_doc(
		{
			"doctype": "Fee Invoice",
			"admission_application": application,
			"fee_type": APPLICATION_FEE,
			"gross_amount": flt(fee_type.default_amount),
			"discount_amount": 0,
			"due_date": add_days(today(), 7),
			"status": "Unpaid",
			"remarks": _("Application fee for {0}").format(app.full_name if app else application),
		}
	)
	invoice.insert(ignore_permissions=True)
	return invoice


def application_fee_invoice(application):
	name = frappe.db.get_value(
		"Fee Invoice",
		{"admission_application": application, "fee_type": APPLICATION_FEE,
		 "status": ("!=", "Cancelled")},
		"name",
	)
	return frappe.get_doc("Fee Invoice", name) if name else None


def mark_application_fee_paid(application):
	"""Flip the gate and place the application.

	Called from the payment webhook. There is no Frappe Workflow to advance any
	more -- the 13-step checklist owns the process, and `workflow_state` is a
	derived summary. Paying the application fee is what moves an application out
	of Draft and onto the review board.
	"""
	from sibbcs.admissions.checklist import sync_overall_state
	from sibbcs.admissions.notifications import dispatch_on_placement

	doc = frappe.get_doc("Admission Application", application)

	if not doc.application_fee_paid:
		doc.db_set("application_fee_paid", 1, update_modified=False)
		doc.reload()

	state = sync_overall_state(doc)

	# Dispatch explicitly rather than relying on the on_update hook: both the
	# flag and the state are written with db_set, which goes straight to the
	# database and never runs document hooks. This is the moment the
	# application is actually placed, so it is where the referee and mentor
	# requests belong.
	try:
		doc.reload()
		dispatch_on_placement(doc)
	except Exception:
		frappe.log_error(title=f"Request dispatch failed for {application}")

	return state


def raise_admission_fee(student, program_enrollment=None, program=None):
	fee_type = get_fee_type(ADMISSION_FEE)
	if not fee_type:
		return None
	if _existing_invoice({"student": student, "fee_type": ADMISSION_FEE}):
		return None
	return create_invoice(student, ADMISSION_FEE, program_enrollment=program_enrollment)


def raise_ata_fee(student, program_enrollment, program):
	"""ATA Registration -- M.Div only, on enrollment."""
	fee_type = get_fee_type(ATA_FEE)
	if not fee_type:
		return None
	if not fee_applies_to_program(fee_type, program):
		return None
	if not frappe.db.get_value("Program", program, "requires_ata_fee"):
		return None
	if _existing_invoice({"student": student, "fee_type": ATA_FEE}):
		return None
	return create_invoice(student, ATA_FEE, program_enrollment=program_enrollment)


def raise_graduation_fee(student, program_enrollment=None):
	if _existing_invoice({"student": student, "fee_type": GRADUATION_FEE}):
		return None
	return create_invoice(student, GRADUATION_FEE, program_enrollment=program_enrollment)


# ---------------------------------------------------------------------------
# stream 2 -- per-registration
# ---------------------------------------------------------------------------


def raise_registration_fee(course_registration):
	"""Rs350 on every Course Registration. Never discountable (§5 Stream 2)."""
	doc = (
		course_registration
		if hasattr(course_registration, "doctype")
		else frappe.get_doc("Course Registration", course_registration)
	)

	if doc.registration_fee_invoice:
		return None
	if doc.status in ("Draft", "Withdrawn"):
		return None

	if _existing_invoice({"course_registration": doc.name, "fee_type": REGISTRATION_FEE}):
		return None

	student = frappe.db.get_value("Program Enrollment", doc.program_enrollment, "student")
	if not student:
		return None

	invoice = create_invoice(
		student,
		REGISTRATION_FEE,
		program_enrollment=doc.program_enrollment,
		course_registration=doc.name,
		term=doc.term,
		remarks=_("Registration fee for {0}").format(doc.course),
	)
	if invoice:
		doc.db_set("registration_fee_invoice", invoice.name, update_modified=False)
	return invoice


# ---------------------------------------------------------------------------
# stream 3 -- recurring tuition, the paused subscription
# ---------------------------------------------------------------------------


def tuition_billed_to_date(program_enrollment, on_gross=True):
	"""How much tuition has already been billed for this enrollment.

	Measured on **gross** by default. If the ceiling were measured on net, a
	student with a scholarship would simply take longer to reach Rs54,000 and
	end up paying the same total -- the discount would stretch the payment
	period instead of reducing the bill, which defeats Stream 4 entirely.
	"""
	field = "gross_amount" if on_gross else "net_amount"
	rows = frappe.get_all(
		"Fee Invoice",
		filters={
			"program_enrollment": program_enrollment,
			"fee_type": TUITION_FEE,
			"status": ("!=", "Cancelled"),
		},
		fields=[field],
	)
	return flt(sum(flt(r.get(field)) for r in rows), 2)


def has_active_registrations(program_enrollment, term):
	"""The pause condition: tuition bills only when the student is studying."""
	return bool(
		frappe.db.exists(
			"Course Registration",
			{
				"program_enrollment": program_enrollment,
				"term": term,
				"status": ("in", ACTIVE_REGISTRATION_STATUSES),
			},
		)
	)


def compute_tuition(enrollment, program, months):
	"""Gross, discount and the reason tuition would be skipped.

	Returns a dict; `gross` of 0 means nothing should be billed.
	"""
	monthly = flt(program.monthly_tuition) or 1500.0
	gross = monthly * int(months)

	ceiling = flt(program.tuition_total)
	if ceiling:
		on_gross = bool(getattr(program, "cap_on_gross", 1))
		billed = tuition_billed_to_date(enrollment.name, on_gross=on_gross)
		remaining = ceiling - billed
		if remaining <= 0:
			return {"gross": 0.0, "discount": 0.0, "reason": "ceiling reached"}
		# Bill the remainder rather than overshooting the advertised total.
		gross = min(gross, remaining)

	# stream 4 -- scholarship, clipped to its own cap
	wanted = flt(enrollment.scholarship_monthly_discount) * int(months)
	headroom = max(
		flt(enrollment.scholarship_total_cap) - flt(enrollment.scholarship_used_to_date), 0.0
	)
	discount = min(wanted, headroom, gross)

	return {"gross": flt(gross, 2), "discount": flt(discount, 2), "reason": None}


def bill_enrollment_for_term(enrollment_name, term_name, dry_run=False):
	"""Raise one term's tuition for one enrollment. Idempotent."""
	enrollment = frappe.get_doc("Program Enrollment", enrollment_name)
	term = frappe.get_cached_doc("Academic Term", term_name)

	result = {"enrollment": enrollment_name, "term": term_name, "invoice": None, "skipped": None}

	if enrollment.status != "Active":
		result["skipped"] = "enrollment not active"
		return result

	if _existing_invoice(
		{"program_enrollment": enrollment_name, "fee_type": TUITION_FEE, "term": term_name}
	):
		result["skipped"] = "already billed for this term"
		return result

	if not has_active_registrations(enrollment_name, term_name):
		result["skipped"] = "no registrations -- tuition paused"
		return result

	program = frappe.get_cached_doc("Program", enrollment.program)
	months = int(term.duration_months or 2)
	amounts = compute_tuition(enrollment, program, months)

	if not amounts["gross"]:
		result["skipped"] = amounts["reason"] or "nothing to bill"
		return result

	result["gross"] = amounts["gross"]
	result["discount"] = amounts["discount"]

	if dry_run:
		result["skipped"] = "dry run"
		return result

	invoice = create_invoice(
		enrollment.student,
		TUITION_FEE,
		gross=amounts["gross"],
		discount=amounts["discount"],
		program_enrollment=enrollment_name,
		term=term_name,
		months_billed=months,
		due_date=add_days(term.start_date or today(), DEFAULT_DUE_DAYS),
		remarks=_("Tuition for {0} ({1} month(s))").format(term_name, months),
	)

	if invoice and amounts["discount"]:
		# Spending the scholarship is what makes the cap real.
		frappe.db.set_value(
			"Program Enrollment",
			enrollment_name,
			"scholarship_used_to_date",
			flt(enrollment.scholarship_used_to_date) + amounts["discount"],
			update_modified=False,
		)

	result["invoice"] = invoice.name if invoice else None
	return result


def run_term_tuition(term=None, dry_run=False):
	"""Scheduled at each term start. Safe to re-run -- billing is per-term idempotent."""
	term = term or _current_term()
	if not term:
		frappe.logger("sibbcs").info("tuition job: no active term")
		return {"term": None, "billed": [], "skipped": []}

	enrollments = frappe.get_all(
		"Program Enrollment", filters={"status": "Active"}, pluck="name"
	)

	billed, skipped = [], []
	for name in enrollments:
		outcome = bill_enrollment_for_term(name, term, dry_run=dry_run)
		(billed if outcome["invoice"] else skipped).append(outcome)

	frappe.logger("sibbcs").info(
		f"tuition job for {term}: {len(billed)} billed, {len(skipped)} skipped"
	)
	return {"term": term, "billed": billed, "skipped": skipped}


def _current_term():
	return frappe.db.get_value(
		"Academic Term", {"status": "Active"}, "name", order_by="start_date desc"
	)


def run_term_tuition_scheduled():
	"""Daily hook: bill only on the day a term actually starts.

	Running daily and gating on the date is more robust than trying to schedule
	a job per term, and the per-term idempotency check makes a double-run safe.
	"""
	today_date = getdate(nowdate())
	terms = frappe.get_all(
		"Academic Term",
		filters={"status": ("in", ("Open", "Active")), "start_date": today_date},
		pluck="name",
	)
	for term in terms:
		run_term_tuition(term)


@frappe.whitelist()
def preview_term_tuition(term):
	"""Dry run for a term, so Accounts can see the bill before raising it."""
	frappe.only_for(("Accounts", "System Manager", "Registrar"))
	return run_term_tuition(term, dry_run=True)
