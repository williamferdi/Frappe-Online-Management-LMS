# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate


class AcademicTerm(Document):
	def validate(self):
		self.validate_term_dates()
		self.validate_registration_window()

	def validate_term_dates(self):
		if getdate(self.end_date) <= getdate(self.start_date):
			frappe.throw(
				_("End Date ({0}) must be after Start Date ({1}).").format(
					self.end_date, self.start_date
				),
				title=_("Invalid Term Dates"),
			)

		if not self.duration_months or self.duration_months < 1:
			frappe.throw(
				_("Duration (Months) must be at least 1. It drives tuition billing."),
				title=_("Invalid Duration"),
			)

	def validate_registration_window(self):
		if self.registration_opens and self.registration_closes:
			if getdate(self.registration_closes) < getdate(self.registration_opens):
				frappe.throw(
					_("Registration Closes cannot be before Registration Opens."),
					title=_("Invalid Registration Window"),
				)

		# Registration after the term has ended is always a data-entry mistake.
		if self.registration_opens and getdate(self.registration_opens) > getdate(self.end_date):
			frappe.throw(
				_("Registration Opens ({0}) is after the term ends ({1}).").format(
					self.registration_opens, self.end_date
				),
				title=_("Invalid Registration Window"),
			)

		# These are odd but legitimate (late registration, rolling admissions),
		# so warn rather than block.
		if self.application_deadline and getdate(self.application_deadline) > getdate(
			self.end_date
		):
			frappe.msgprint(
				_("Application Deadline falls after the term ends."),
				indicator="orange",
				alert=True,
			)

	def is_registration_open(self):
		"""True when today falls inside the registration window.

		Phase 3's Course Registration uses this; a term with no window
		configured is treated as open so early terms are not accidentally
		locked out.
		"""
		if self.status == "Closed":
			return False
		if not (self.registration_opens and self.registration_closes):
			return self.status in ("Open", "Active")

		today = getdate()
		return getdate(self.registration_opens) <= today <= getdate(self.registration_closes)


def get_current_term():
	"""The Active term, else the nearest Open term by start date."""
	term = frappe.db.get_value(
		"Academic Term", {"status": "Active"}, "name", order_by="start_date desc"
	)
	if term:
		return term

	return frappe.db.get_value(
		"Academic Term", {"status": "Open"}, "name", order_by="start_date asc"
	)


def derive_term_dates(application_deadline, duration_months=2, registration_lead_days=30):
	"""Provisional term dates from a published application deadline.

	Used by the Phase 1 seeder. SIBBCS publishes application deadlines but the
	exact teaching start/end dates are not in the architecture document, so the
	seeder derives them and flags each term for review.
	"""
	start = getdate(application_deadline)
	end = add_days(frappe.utils.add_months(start, duration_months), -1)
	return {
		"start_date": start,
		"end_date": end,
		"registration_opens": add_days(start, -registration_lead_days),
		"registration_closes": start,
	}
