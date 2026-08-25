"""Document hooks that raise fees at the right lifecycle moments.

Wired in hooks.py rather than inside the controllers so the fee engine stays a
separable concern -- Phases 1-3 must keep working with the Finance module
absent, which is how they were built and tested.
"""

import frappe

from sibbcs.finance import fees


def course_registration_on_update(doc, method=None):
	"""§5 Stream 2 -- Rs350 on every registration that sticks."""
	if doc.status in ("Draft", "Withdrawn"):
		return
	if doc.registration_fee_invoice:
		return
	if not frappe.db.exists("DocType", "Fee Invoice"):
		return

	try:
		fees.raise_registration_fee(doc)
	except Exception:
		# A billing problem must not roll back an accepted registration; the
		# nightly sweep picks it up.
		frappe.log_error(title=f"Registration fee failed for {doc.name}")


def sweep_missing_registration_fees(limit=500):
	"""Daily: catch registrations whose fee invoice did not get raised."""
	if not frappe.db.exists("DocType", "Fee Invoice"):
		return {"raised": []}

	pending = frappe.get_all(
		"Course Registration",
		filters={
			"status": ("in", ("Registered", "Active", "Completed")),
			"registration_fee_invoice": ("in", ("", None)),
		},
		pluck="name",
		limit=limit,
	)

	raised = []
	for name in pending:
		try:
			invoice = fees.raise_registration_fee(name)
			if invoice:
				raised.append(invoice.name)
		except Exception:
			frappe.log_error(title=f"Registration fee sweep failed for {name}")

	if raised:
		frappe.logger("sibbcs").info(f"registration fee sweep raised {len(raised)} invoices")
	return {"raised": raised}


def open_course_when_fee_settled(fee_invoice, method=None):
	"""A settled registration fee is what opens the course in the LMS.

	Called from Fee Invoice.refresh_payment_state as well as the doc hook,
	because payment usually arrives through a Payment Entry allocation, which
	updates the invoice with db_set and so never runs on_update.
	"""
	doc = (
		fee_invoice
		if hasattr(fee_invoice, "doctype")
		else frappe.get_doc("Fee Invoice", fee_invoice)
	)

	if not doc.get("course_registration"):
		return
	if doc.status not in ("Paid", "Waived", "Cancelled"):
		return
	if not frappe.db.exists("Course Registration", doc.course_registration):
		return

	try:
		from sibbcs.academic import lms_sync

		registration = frappe.get_doc("Course Registration", doc.course_registration)
		if registration.lms_enrollment_created:
			return
		if registration.status not in ("Registered", "Active", "Completed"):
			return
		lms_sync.sync_registration(registration)
	except Exception:
		# The student has paid; an LMS problem must not undo that. The hourly
		# sync_pending sweep retries.
		frappe.log_error(title=f"Opening course after payment failed for {doc.name}")
