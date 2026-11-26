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
and stops once `Program.tuition_total` has been billed, or once less than one
month of it is left. The ceiling is measured
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


OFFLINE_MODES = ("UPI", "Bank Transfer", "Cash", "Cheque")


def settle_application_fee(
	application, amount=None, mode="Bank Transfer", reference_no=None,
	received_on=None, remarks=None,
):
	"""Record an application fee that arrived outside a gateway, and place the
	application.

	    bench --site online.sibbc.org execute \\
	        sibbcs.finance.fees.settle_application_fee \\
	        --kwargs "{'application': 'APP-2026-00001', 'mode': 'UPI', \\
	                   'reference_no': '4296...'}"

	**Why this has to exist.** Until now nothing but the Razorpay webhook could
	settle an application fee. `Payment Entry.student` is mandatory and an
	applicant does not become a Student until the conversion point, several
	states later -- so there is no Payment Entry to write -- and `Fee Invoice`
	derives `paid_amount` from its allocations, so marking the invoice Paid in
	Desk is undone by its own `validate`. With no gateway configured, which is
	the position today and for as long as the college takes UPI and bank
	transfers by hand, an application could be submitted and then stand in
	Draft for ever with no way for anybody to say the money had arrived.

	The money is recorded in `direct_paid_amount`, which `get_paid_amount`
	counts: writing `paid_amount` straight through, as the gateway path did,
	leaves a payment the next save of the invoice silently reverses.

	`payment_provider` is left blank on purpose -- that field records *which
	gateway* handled a row, and inventing a value for money counted at the
	office would make a hand-written receipt indistinguishable from a
	settlement a gateway signed for.
	"""
	from sibbcs.admissions.checklist import derive_state

	invoice = application_fee_invoice(application)
	if not invoice:
		frappe.throw(
			_("{0} has no application fee invoice to settle.").format(application),
			title=_("Nothing to Pay"),
		)

	if invoice.status == "Cancelled":
		frappe.throw(
			_("{0} is cancelled and cannot be paid.").format(invoice.name),
			title=_("Cancelled Invoice"),
		)

	if mode not in OFFLINE_MODES:
		# "Online" is the gateway's own word for its own rows. Money recorded
		# here came in some other way, and saying how is the whole audit trail.
		frappe.throw(
			_("Mode must be one of: {0}.").format(", ".join(OFFLINE_MODES)),
			title=_("Unknown Payment Mode"),
		)

	# Idempotent: a second call after the money is in reports the state rather
	# than recording the fee twice. An officer told to "just run it again"
	# because the first run looked like it did nothing must not double-count.
	if flt(invoice.outstanding_amount) <= 0 or invoice.status in ("Paid", "Waived"):
		doc = frappe.get_doc("Admission Application", application)
		if not doc.application_fee_paid:
			# Settled, but the gate was never flipped -- finish the job.
			return mark_application_fee_paid(application)
		return derive_state(doc)

	outstanding = flt(invoice.outstanding_amount)
	taken = flt(amount) if amount is not None else outstanding

	if taken <= 0:
		frappe.throw(_("A payment must be for more than nothing."), title=_("Invalid Amount"))

	if taken > outstanding + 0.01:
		# Clamping is right for a gateway -- the money demonstrably arrived.
		# A figure typed at the office is a typo until somebody confirms it.
		frappe.throw(
			_("{0} is owed {1}, but {2} was entered. Correct the figure, or raise the invoice.").format(
				invoice.name, outstanding, taken
			),
			title=_("More Than Is Owed"),
		)

	when = getdate(received_on) if received_on else getdate(today())
	note = _("Paid {0} by {1}").format(when, mode)
	if reference_no:
		note += _(" · ref {0}").format(reference_no)
	note += _(" · recorded by {0}").format(frappe.session.user)
	if remarks:
		note += f" · {remarks}"

	paid = flt(flt(invoice.direct_paid_amount) + taken, 2)
	net = flt(invoice.net_amount)

	# Through db_set, not save(): `compute_totals` would recompute paid_amount
	# from `direct_paid_amount` anyway, but a save also re-runs every amount
	# rule on an invoice nobody asked to re-validate. `modified_by` is left to
	# move, because who recorded this money is part of the record.
	invoice.db_set(
		{
			"direct_paid_amount": paid,
			"paid_amount": paid,
			"outstanding_amount": flt(net - paid, 2),
			"status": "Paid" if paid >= net else "Partly Paid",
			"payment_reference": reference_no or invoice.payment_reference,
			"remarks": f"{invoice.remarks} · {note}" if invoice.remarks else note,
		}
	)

	if paid < net:
		# Part of the fee is not the fee. The gate stays shut and the
		# application stays in Draft, which is the honest answer.
		return derive_state(frappe.get_doc("Admission Application", application))

	return mark_application_fee_paid(application)


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
	if doc.get("legacy_source"):
		# Carried over from Zoho: history, billed (or not) under the old system.
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


DEFAULT_MONTHLY_TUITION = 1500.0


def monthly_rate(program):
	return flt(program.monthly_tuition) or DEFAULT_MONTHLY_TUITION


def ceiling_state(ceiling, billed, monthly):
	"""(remaining, reached) for one enrollment against its programme's ceiling.

	The single statement of when billing stops, so that what the nightly job
	does and what the screens say cannot drift apart.

	Less than one month left is not a month of study, so it is not billed. The
	advertised ceilings are round figures (Rs78,000, Rs52,000) and the monthly
	rate is not a divisor of them: after 18 full two-month terms of Rs4,332 an
	M.Div. student has been billed Rs77,976, and what was left, Rs24, used to
	arrive as an invoice of its own. `<` and not `<=`: a remainder of exactly
	one month is still a month.

	`ceiling` of 0 means uncapped, which is never reached.
	"""
	if not flt(ceiling):
		return None, False
	remaining = flt(flt(ceiling) - flt(billed), 2)
	return remaining, remaining < flt(monthly)


def compute_tuition(enrollment, program, months):
	"""Gross, discount and the reason tuition would be skipped.

	Returns a dict; `gross` of 0 means nothing should be billed.
	"""
	monthly = monthly_rate(program)
	gross = monthly * int(months)

	ceiling = flt(program.tuition_total)
	if ceiling:
		on_gross = bool(getattr(program, "cap_on_gross", 1))
		billed = tuition_billed_to_date(enrollment.name, on_gross=on_gross)
		remaining, reached = ceiling_state(ceiling, billed, monthly)
		if reached:
			return {"gross": 0.0, "discount": 0.0, "reason": "ceiling reached"}
		# At least a month left: bill it rather than overshooting the total.
		gross = min(gross, remaining)

	# stream 4 -- scholarship, clipped to its own cap
	wanted = flt(enrollment.scholarship_monthly_discount) * int(months)
	headroom = max(
		flt(enrollment.scholarship_total_cap) - flt(enrollment.scholarship_used_to_date), 0.0
	)
	discount = min(wanted, headroom, gross)

	return {"gross": flt(gross, 2), "discount": flt(discount, 2), "reason": None}


# ---------------------------------------------------------------------------
# where each student stands -- what the screens show
# ---------------------------------------------------------------------------


def _position(enrollment, program, tuition):
	"""One enrollment's position, from facts already in hand.

	`tuition` is `{"gross", "net", "terms"}` for its non-cancelled tuition
	invoices. Kept free of queries so the roster can build every row from one.
	"""
	monthly = monthly_rate(program)
	ceiling = flt(program.tuition_total)
	on_gross = bool(program.get("cap_on_gross", 1))
	billed = flt(tuition["gross"] if on_gross else tuition["net"], 2)
	remaining, reached = ceiling_state(ceiling, billed, monthly)

	if not ceiling:
		state = "uncapped"
	elif reached:
		state = "ceiling_reached"
	else:
		state = "billing"

	award_cap = flt(enrollment.get("scholarship_total_cap"))
	award_monthly = flt(enrollment.get("scholarship_monthly_discount"))
	scholarship = None
	if award_cap or award_monthly:
		used = flt(enrollment.get("scholarship_used_to_date"))
		scholarship = {
			"monthly": award_monthly,
			"cap": award_cap,
			"used": used,
			"remaining": flt(max(award_cap - used, 0.0), 2),
		}

	return {
		"enrollment": enrollment.get("name"),
		"state": state,
		"monthly": monthly,
		"ceiling": ceiling,
		"billed": billed,
		# Billing stops with this much unbilled -- never more than a month's worth.
		"remaining": remaining,
		"terms_billed": int(tuition["terms"]),
		"scholarship": scholarship,
	}


def _tuition_totals(enrollment_names=None):
	"""{enrollment: {gross, net, terms}} for non-cancelled tuition invoices."""
	conditions = ["fee_type = %(fee)s", "status != 'Cancelled'", "program_enrollment IS NOT NULL"]
	values = {"fee": TUITION_FEE}
	if enrollment_names is not None:
		if not enrollment_names:
			return {}
		conditions.append("program_enrollment IN %(names)s")
		values["names"] = tuple(enrollment_names)

	rows = frappe.db.sql(
		f"""
		SELECT program_enrollment, SUM(gross_amount) AS gross,
		       SUM(net_amount) AS net, COUNT(name) AS terms
		FROM `tabFee Invoice`
		WHERE {' AND '.join(conditions)}
		GROUP BY program_enrollment
		""",
		values,
		as_dict=True,
	)
	return {row.program_enrollment: row for row in rows}


NO_TUITION = {"gross": 0, "net": 0, "terms": 0}


def tuition_position(enrollment):
	"""Where one student stands against the programme ceiling and the scholarship cap."""
	doc = (
		enrollment
		if hasattr(enrollment, "doctype")
		else frappe.get_doc("Program Enrollment", enrollment)
	)
	program = frappe.get_cached_doc("Program", doc.program)
	totals = _tuition_totals([doc.name]).get(doc.name, NO_TUITION)
	return _position(doc, program, totals)


def tuition_positions():
	"""Every active enrollment's position, those at the ceiling first.

	This is the answer to "who has reached the ceiling", which the nightly job
	used to work out and throw away: it knew, logged a count, and told nobody.
	Computed from the invoices on every call rather than stored, so it cannot
	go stale -- a cancelled or waived invoice moves it at once.
	"""
	enrollments = frappe.get_all(
		"Program Enrollment",
		filters={"status": "Active"},
		fields=[
			"name", "student", "student_name", "program", "current_level",
			"scholarship_monthly_discount", "scholarship_total_cap",
			"scholarship_used_to_date",
		],
	)
	totals = _tuition_totals([e.name for e in enrollments])
	programs = {}

	rows = []
	for enrollment in enrollments:
		if enrollment.program not in programs:
			programs[enrollment.program] = frappe.get_cached_doc("Program", enrollment.program)
		position = _position(
			enrollment, programs[enrollment.program], totals.get(enrollment.name, NO_TUITION)
		)
		position.update(
			student=enrollment.student,
			student_name=enrollment.student_name,
			program=enrollment.program,
			level=enrollment.current_level,
		)
		rows.append(position)

	order = {"ceiling_reached": 0, "billing": 1, "uncapped": 2}
	rows.sort(key=lambda r: (order[r["state"]], r["remaining"] if r["remaining"] is not None else 0, r["student_name"] or ""))
	return rows


def _billing_date(term):
	"""The date the fortnight to pay runs from: the term's start, or today if later.

	An invoice raised for a student who registered mid-term would otherwise fall
	due at `start_date + 14`, which can already be in the past -- it would be
	overdue the moment it appeared, for a bill they had no way to see before.
	On a term's first day the two dates are the same, so nothing changes there.
	"""
	started = getdate(term.start_date) if term.start_date else None
	now = getdate(today())
	return max(started, now) if started else now


def return_scholarship(program_enrollment, amount):
	"""Give back what a cancelled tuition invoice spent of the scholarship cap.

	Billing spends the cap at the moment an invoice is raised, so cancelling the
	invoice without returning it left the cap short by a discount nobody
	received: the student lost that money for good, and the term was billed
	again at full price at the far end of the programme. Never below zero, and
	never more than was used.

	Returns what was actually given back.
	"""
	amount = flt(amount)
	if not program_enrollment or amount <= 0:
		return 0.0

	used = flt(
		frappe.db.get_value(
			"Program Enrollment", program_enrollment, "scholarship_used_to_date", for_update=True
		)
	)
	remaining = flt(max(used - amount, 0.0), 2)
	frappe.db.set_value(
		"Program Enrollment",
		program_enrollment,
		"scholarship_used_to_date",
		remaining,
		update_modified=False,
	)
	return flt(used - remaining, 2)


def bill_enrollment_for_term(enrollment_name, term_name, dry_run=False):
	"""Raise one term's tuition for one enrollment. Idempotent."""
	enrollment = frappe.get_doc("Program Enrollment", enrollment_name)
	term = frappe.get_cached_doc("Academic Term", term_name)

	result = {"enrollment": enrollment_name, "term": term_name, "invoice": None, "skipped": None}

	if enrollment.status != "Active":
		result["skipped"] = "enrollment not active"
		return result

	# A cancelled invoice does not count: cancelling one undoes that term's
	# billing (see `return_scholarship`), so the term is billable again. This
	# used to ignore status, which left a cancelled term unbillable for ever
	# while the ceiling reopened and the same tuition arrived at the far end.
	if _existing_invoice(
		{
			"program_enrollment": enrollment_name,
			"fee_type": TUITION_FEE,
			"term": term_name,
			"status": ("!=", "Cancelled"),
		}
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
		due_date=add_days(_billing_date(term), DEFAULT_DUE_DAYS),
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
	"""Raise tuition for one term. Safe to re-run -- billing is per-term idempotent.

	The daily job calls this for every started term, not only on a start date;
	see `terms_to_bill`.
	"""
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


def terms_to_bill(on=None):
	"""Every term tuition may be raised for today: Open or Active, and started.

	**Not only the terms that start today.** This used to match
	`start_date == today`, so a student who registered even one day after a term
	began was never billed for it: the job ran every night, reported "Complete",
	and found nothing, because by then no term was starting. Registration stays
	open for weeks into a term -- 2026-T6 began on 16 Nov and registration closes
	on 30 Nov -- so late registrants are the ordinary case, not an edge.

	Whether a student is owed a bill is decided per enrollment by
	`bill_enrollment_for_term`, which is idempotent per term. Offering it every
	started term every night is therefore safe: whoever already has an invoice is
	skipped, and whoever registered since the last run is picked up.

	A term the college has closed, or has not yet started, is never offered.
	Status is the college's switch, so a term left Active after its end date is
	still billed -- close it to stop that.
	"""
	on = getdate(on or nowdate())
	return frappe.get_all(
		"Academic Term",
		filters={"status": ("in", ("Open", "Active")), "start_date": ("<=", on)},
		pluck="name",
		order_by="start_date asc",
	)


def run_term_tuition_scheduled():
	"""Daily hook: bill every started term, so a late registrant is billed too.

	See `terms_to_bill` for why this is no longer gated on the start date.
	"""
	for term in terms_to_bill():
		run_term_tuition(term)


@frappe.whitelist()
def preview_term_tuition(term):
	"""Dry run for a term, so Accounts can see the bill before raising it."""
	frappe.only_for(("Accounts", "System Manager", "Registrar"))
	return run_term_tuition(term, dry_run=True)
