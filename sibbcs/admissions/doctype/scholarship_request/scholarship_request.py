# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class ScholarshipRequest(Document):
	def validate(self):
		self.validate_subject()
		self.validate_amounts()
		self.stamp_approval()

	def on_update(self):
		self.link_to_application()
		self.push_to_enrollment()

	def validate_subject(self):
		if not (self.application or self.student):
			frappe.throw(
				_("A scholarship request needs either an Admission Application or a Student."),
				title=_("No Subject"),
			)

		if self.application and not self.program:
			self.program = frappe.db.get_value("Admission Application", self.application, "program")

	def validate_amounts(self):
		for field in ("requested_amount", "approved_amount", "monthly_discount"):
			if flt(self.get(field)) < 0:
				frappe.throw(
					_("{0} cannot be negative.").format(frappe.unscrub(field)),
					title=_("Invalid Amount"),
				)

		if self.status == "Approved":
			if not flt(self.approved_amount):
				frappe.throw(
					_("An approved scholarship needs an Approved Total -- it becomes the cap."),
					title=_("Incomplete Approval"),
				)
			if not flt(self.monthly_discount):
				frappe.throw(
					_("An approved scholarship needs a Monthly Discount."),
					title=_("Incomplete Approval"),
				)
			if flt(self.monthly_discount) > flt(self.approved_amount):
				frappe.throw(
					_("Monthly Discount ({0}) cannot exceed the Approved Total ({1}).").format(
						self.monthly_discount, self.approved_amount
					),
					title=_("Invalid Approval"),
				)

	def stamp_approval(self):
		if self.status == "Approved" and not self.approved_by:
			self.approved_by = frappe.session.user
			self.approved_on = today()
		elif self.status != "Approved":
			self.approved_by = None
			self.approved_on = None

	def link_to_application(self):
		if not self.application:
			return
		current = frappe.db.get_value(
			"Admission Application", self.application, "scholarship_request"
		)
		if current != self.name:
			frappe.db.set_value(
				"Admission Application",
				self.application,
				"scholarship_request",
				self.name,
				update_modified=False,
			)

	def push_to_enrollment(self):
		"""Apply an approved award to an already-enrolled student.

		Pre-enrollment awards are picked up by the conversion function instead.
		Only the cap and the monthly figure are written; `used_to_date` is owned
		by the Phase 4 tuition job and must never be reset here.
		"""
		if self.status != "Approved" or not self.student:
			return

		enrollment = frappe.db.get_value(
			"Program Enrollment", {"student": self.student, "program": self.program}, "name"
		)
		if not enrollment:
			return

		frappe.db.set_value(
			"Program Enrollment",
			enrollment,
			{
				"scholarship_monthly_discount": flt(self.monthly_discount),
				"scholarship_total_cap": flt(self.approved_amount),
			},
			update_modified=False,
		)
