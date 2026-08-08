# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class FeeInvoice(Document):
	def validate(self):
		self.validate_amounts()
		self.compute_totals()
		self.set_status()

	def validate_amounts(self):
		if flt(self.gross_amount) < 0:
			frappe.throw(_("Gross cannot be negative."), title=_("Invalid Amount"))

		if flt(self.discount_amount) < 0:
			frappe.throw(_("Discount cannot be negative."), title=_("Invalid Amount"))

		if flt(self.discount_amount) > flt(self.gross_amount):
			frappe.throw(
				_("Discount ({0}) cannot exceed gross ({1}).").format(
					self.discount_amount, self.gross_amount
				),
				title=_("Invalid Discount"),
			)

		# §5 Stream 2: the per-registration fee is deliberately not discountable.
		if self.fee_type and flt(self.discount_amount):
			discountable = frappe.db.get_value("Fee Type", self.fee_type, "discountable")
			if not discountable:
				frappe.throw(
					_("{0} cannot be discounted by a scholarship.").format(self.fee_type),
					title=_("Not Discountable"),
				)

	def compute_totals(self):
		self.net_amount = flt(flt(self.gross_amount) - flt(self.discount_amount), 2)
		self.paid_amount = self.get_paid_amount()
		self.outstanding_amount = flt(flt(self.net_amount) - flt(self.paid_amount), 2)

	def get_paid_amount(self):
		"""Sum of allocations pointing at this invoice."""
		if self.is_new():
			return 0.0
		rows = frappe.get_all(
			"Payment Allocation",
			filters={"fee_invoice": self.name, "parenttype": "Payment Entry", "docstatus": ("<", 2)},
			fields=["allocated_amount"],
		)
		return flt(sum(flt(r.allocated_amount) for r in rows), 2)

	def set_status(self):
		"""Waived and Cancelled are set by a human and must stick."""
		if self.status in ("Waived", "Cancelled"):
			return

		paid = flt(self.paid_amount)
		net = flt(self.net_amount)

		if net <= 0 or paid >= net:
			self.status = "Paid"
		elif paid > 0:
			self.status = "Partly Paid"
		else:
			self.status = "Unpaid"

	def refresh_payment_state(self):
		"""Recompute after an allocation changes, without a full save."""
		paid = self.get_paid_amount()
		net = flt(self.net_amount)

		if self.status in ("Waived", "Cancelled"):
			status = self.status
		elif net <= 0 or paid >= net:
			status = "Paid"
		elif paid > 0:
			status = "Partly Paid"
		else:
			status = "Unpaid"

		self.db_set(
			{
				"paid_amount": paid,
				"outstanding_amount": flt(net - paid, 2),
				"status": status,
			},
			update_modified=False,
		)


def outstanding_for_student(student):
	"""Every unpaid or partly paid invoice, oldest first."""
	return frappe.get_all(
		"Fee Invoice",
		filters={"student": student, "status": ("in", ("Unpaid", "Partly Paid"))},
		fields=["name", "fee_type", "term", "net_amount", "paid_amount", "outstanding_amount", "due_date"],
		order_by="due_date asc, creation asc",
	)


def total_outstanding(student):
	return flt(sum(flt(r.outstanding_amount) for r in outstanding_for_student(student)), 2)
