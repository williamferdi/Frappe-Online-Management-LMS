# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class ProgramEnrollment(Document):
	def validate(self):
		self.validate_unique_enrollment()
		self.validate_scholarship()
		self.validate_dates()

	def validate_unique_enrollment(self):
		"""One active enrollment per student per program.

		The docname is {student}-{program}, so the database already enforces
		this; catching it here gives a message the Registrar can act on.
		"""
		existing = frappe.db.exists(
			"Program Enrollment",
			{"student": self.student, "program": self.program, "name": ("!=", self.name)},
		)
		if existing:
			frappe.throw(
				_("{0} is already enrolled in {1} ({2}).").format(
					self.student, self.program, existing
				),
				title=_("Duplicate Enrollment"),
			)

	def validate_scholarship(self):
		for field in (
			"scholarship_monthly_discount",
			"scholarship_total_cap",
			"scholarship_used_to_date",
		):
			if flt(self.get(field)) < 0:
				frappe.throw(
					_("{0} cannot be negative.").format(frappe.unscrub(field)),
					title=_("Invalid Scholarship"),
				)

		if flt(self.scholarship_used_to_date) > flt(self.scholarship_total_cap):
			frappe.throw(
				_("Scholarship used ({0}) exceeds the total cap ({1}).").format(
					self.scholarship_used_to_date, self.scholarship_total_cap
				),
				title=_("Scholarship Cap Exceeded"),
			)

		if flt(self.scholarship_monthly_discount) and not flt(self.scholarship_total_cap):
			frappe.msgprint(
				_(
					"A monthly discount with no total cap will never stop. "
					"Set a cap unless that is intended."
				),
				indicator="orange",
				alert=True,
			)

	def validate_dates(self):
		if (
			self.enrollment_date
			and self.expected_completion
			and getdate(self.expected_completion) <= getdate(self.enrollment_date)
		):
			frappe.throw(
				_("Expected Completion must be after the Enrollment Date."),
				title=_("Invalid Dates"),
			)

	# -- scholarship budget ------------------------------------------------

	def scholarship_remaining(self):
		"""Headroom left under the cap. Phase 4's tuition job spends this."""
		return max(flt(self.scholarship_total_cap) - flt(self.scholarship_used_to_date), 0.0)

	def discount_for_months(self, months):
		"""Discount available for `months` of tuition, clipped to the cap."""
		wanted = flt(self.scholarship_monthly_discount) * int(months)
		return min(wanted, self.scholarship_remaining())
