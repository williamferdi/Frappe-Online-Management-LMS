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
