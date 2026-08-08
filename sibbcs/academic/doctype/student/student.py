# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class Student(Document):
	def validate(self):
		self.normalise()
		self.validate_dob()
		self.validate_unique_email()

	def normalise(self):
		self.full_name = (self.full_name or "").strip()
		self.email = (self.email or "").strip().lower()

	def validate_dob(self):
		if self.dob and getdate(self.dob) >= getdate(nowdate()):
			frappe.throw(_("Date of Birth must be in the past."), title=_("Invalid Date of Birth"))

	def validate_unique_email(self):
		"""Email is the login identity, so two students cannot share one."""
		if not self.email:
			return
		existing = frappe.db.exists(
			"Student", {"email": self.email, "name": ("!=", self.name)}
		)
		if existing:
			frappe.throw(
				_("Student {0} already uses {1}.").format(existing, self.email),
				title=_("Duplicate Email"),
			)

	def active_enrollment(self):
		name = frappe.db.get_value(
			"Program Enrollment", {"student": self.name, "status": "Active"}, "name"
		)
		return frappe.get_doc("Program Enrollment", name) if name else None
