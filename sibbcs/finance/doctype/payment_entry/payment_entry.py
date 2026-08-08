# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PaymentEntry(Document):
	def validate(self):
		self.validate_amount()
		self.validate_allocations()
		self.compute_totals()
		self.stamp_reconciler()

	def on_update(self):
		self.refresh_invoices()

	def on_trash(self):
		self.refresh_invoices(removing=True)

	def validate_amount(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Payment amount must be greater than zero."), title=_("Invalid Amount"))

	def validate_allocations(self):
		seen = set()
		for row in self.allocations:
			if flt(row.allocated_amount) <= 0:
				frappe.throw(
					_("Row {0}: allocated amount must be greater than zero.").format(row.idx),
					title=_("Invalid Allocation"),
				)

			if row.fee_invoice in seen:
				frappe.throw(
					_("{0} is allocated twice. Combine the rows instead.").format(row.fee_invoice),
					title=_("Duplicate Allocation"),
				)
			seen.add(row.fee_invoice)

			invoice = frappe.db.get_value(
				"Fee Invoice",
				row.fee_invoice,
				["student", "net_amount", "status"],
				as_dict=True,
			)
			if not invoice:
				continue

			if invoice.student != self.student:
				frappe.throw(
					_("{0} belongs to a different student.").format(row.fee_invoice),
					title=_("Wrong Student"),
				)

			if invoice.status == "Cancelled":
				frappe.throw(
					_("{0} is cancelled and cannot be paid.").format(row.fee_invoice),
					title=_("Cancelled Invoice"),
				)

			# Over-allocation across payments is the classic reconciliation bug:
			# check the invoice total, not just this row.
			already = self._allocated_elsewhere(row.fee_invoice)
			if flt(already) + flt(row.allocated_amount) > flt(invoice.net_amount) + 0.01:
				frappe.throw(
					_(
						"{0} would be over-paid: net {1}, already allocated {2}, "
						"this entry adds {3}."
					).format(
						row.fee_invoice, invoice.net_amount, already, row.allocated_amount
					),
					title=_("Over-allocation"),
				)

		total = sum(flt(r.allocated_amount) for r in self.allocations)
		if total > flt(self.amount) + 0.01:
			frappe.throw(
				_("Allocated ({0}) exceeds the payment amount ({1}).").format(
					flt(total, 2), self.amount
				),
				title=_("Over-allocation"),
			)

	def _allocated_elsewhere(self, fee_invoice):
		rows = frappe.get_all(
			"Payment Allocation",
			filters={
				"fee_invoice": fee_invoice,
				"parenttype": "Payment Entry",
				"parent": ("!=", self.name or ""),
			},
			fields=["allocated_amount"],
		)
		return flt(sum(flt(r.allocated_amount) for r in rows), 2)

	def compute_totals(self):
		self.allocated_amount = flt(
			sum(flt(r.allocated_amount) for r in self.allocations), 2
		)
		self.unallocated_amount = flt(flt(self.amount) - flt(self.allocated_amount), 2)

	def stamp_reconciler(self):
		if not self.reconciled_by:
			self.reconciled_by = frappe.session.user

	def refresh_invoices(self, removing=False):
		"""Push paid/outstanding back onto every invoice this entry touches."""
		invoices = {r.fee_invoice for r in self.allocations if r.fee_invoice}
		for name in invoices:
			if frappe.db.exists("Fee Invoice", name):
				frappe.get_doc("Fee Invoice", name).refresh_payment_state()

	def auto_allocate(self):
		"""Apply this payment to the student's oldest outstanding invoices."""
		from sibbcs.finance.doctype.fee_invoice.fee_invoice import outstanding_for_student

		remaining = flt(self.amount) - flt(
			sum(flt(r.allocated_amount) for r in self.allocations)
		)
		if remaining <= 0:
			return []

		already = {r.fee_invoice for r in self.allocations}
		applied = []

		for invoice in outstanding_for_student(self.student):
			if remaining <= 0:
				break
			if invoice.name in already:
				continue

			take = min(remaining, flt(invoice.outstanding_amount))
			if take <= 0:
				continue

			self.append(
				"allocations", {"fee_invoice": invoice.name, "allocated_amount": take}
			)
			applied.append((invoice.name, take))
			remaining -= take

		return applied


@frappe.whitelist()
def allocate_automatically(payment_entry):
	"""Desk button: settle the oldest invoices first."""
	doc = frappe.get_doc("Payment Entry", payment_entry)
	doc.check_permission("write")

	applied = doc.auto_allocate()
	if not applied:
		frappe.msgprint(_("Nothing left to allocate."), indicator="orange")
		return []

	doc.save(ignore_permissions=True)
	frappe.msgprint(
		_("Allocated to: {0}").format(", ".join(f"{n} ({a})" for n, a in applied)),
		indicator="green",
	)
	return applied
