"""Where Razorpay returns the candidate after payment.

URL: /fee-paid?invoice=FEE-2026-00001  (or ?application=APP-2026-00001)

The webhook is what actually records the payment; this page only reports the
current state. Razorpay's redirect can arrive before the webhook does, so the
page says "confirming" rather than claiming success it cannot verify.

Frappe maps `-` to `_` when resolving a page controller, so fee-paid.html is
served by fee_paid.py -- see www/test_www_pages.py.
"""

import frappe

no_cache = 1


def get_context(context):
	context.no_cache = 1

	application = frappe.form_dict.get("application")
	invoice = frappe.form_dict.get("invoice")

	if not application and invoice and frappe.db.exists("Fee Invoice", invoice):
		application = frappe.db.get_value("Fee Invoice", invoice, "admission_application")

	context.application = application
	context.found = bool(application and frappe.db.exists("Admission Application", application))

	if not context.found:
		return context

	from sibbcs.admissions.public_form import payment_status

	context.update(payment_status(application))
	return context
