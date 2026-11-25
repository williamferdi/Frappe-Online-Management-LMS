# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class FeeInvoice(Document):
	def validate(self):
		self.validate_owner()
		self.validate_amounts()
		self.compute_totals()
		self.validate_tuition_cancellation()
		self.set_status()

	def on_update(self):
		self.undo_tuition_billing_when_cancelled()

	def is_tuition(self):
		from sibbcs.finance.fees import TUITION_FEE

		return self.fee_type == TUITION_FEE

	def validate_tuition_cancellation(self):
		"""Cancelling a tuition invoice undoes its billing, so it must be safe to.

		Two things would make it unsafe, and both are refused rather than
		quietly handled.

		**Money already taken.** Cancelling reopens the term, so the billing job
		raises it again. With a payment sitting on the old invoice the student
		would be billed twice for the same term.

		**Reopening a cancelled one.** The job raises the term itself, so a
		revived invoice would sit beside its replacement and bill the term twice.
		"""
		if not self.is_tuition():
			return

		before = self.get_doc_before_save()
		was = before.status if before else None

		if self.status == "Cancelled" and was not in (None, "Cancelled"):
			if flt(self.paid_amount) > 0:
				frappe.throw(
					_(
						"{0} has {1} paid against it. Cancelling it would bill {2} again and "
						"charge the student twice. Waive it, or reverse the payment first."
					).format(self.name, self.paid_amount, self.term or _("the term")),
					title=_("Payment Recorded"),
				)

		if was == "Cancelled" and self.status != "Cancelled":
			frappe.throw(
				_(
					"{0} is cancelled and cannot be reopened. Its term is billed again by the "
					"nightly job, which raises a fresh invoice."
				).format(self.name),
				title=_("Cancelled Invoice"),
			)

	def undo_tuition_billing_when_cancelled(self):
		"""Cancel means the billing never happened.

		The ceiling already stops counting a cancelled invoice, and the billing
		job now treats its term as unbilled. The one thing left is the
		scholarship, which billing spent when it raised the invoice and which
		nothing used to return. Only on the save that cancels it: saving a
		cancelled invoice again (to add a remark, say) must not return it twice.
		"""
		if not self.is_tuition() or self.status != "Cancelled":
			return

		before = self.get_doc_before_save()
		if not before or before.status == "Cancelled":
			return

		from sibbcs.finance.fees import return_scholarship

		given_back = return_scholarship(self.program_enrollment, self.discount_amount)

		frappe.msgprint(
			_("{0} cancelled. {1} is billed again by the nightly job while the student is registered.").format(
				self.name, self.term or _("Its term")
			)
			+ (
				" " + _("{0} of scholarship returned.").format(frappe.format_value(given_back, {"fieldtype": "Currency"}))
				if given_back
				else ""
			),
			indicator="orange",
			alert=True,
		)

	def validate_owner(self):
		"""Exactly one of student / admission_application.

		The application fee is owed before a Student exists, so `student` alone
		cannot be mandatory -- but an invoice belonging to nobody would never
		appear on any ledger.
		"""
		if not self.student and not self.get("admission_application"):
			frappe.throw(
				_("A Fee Invoice needs either a Student or an Admission Application."),
				title=_("No Owner"),
			)

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
		"""Allocations pointing at this invoice, plus anything recorded directly.

		`paid_amount` is derived, never assigned -- which is why marking an
		invoice Paid in Desk does not stick. But not every payment can be a
		Payment Entry: `Payment Entry.student` is mandatory and an application
		fee is owed before the applicant becomes a Student, so the only record
		of that money is `direct_paid_amount` on the invoice itself.

		Counting it here is what makes such a payment survive. Both the gateway
		and `fees.settle_application_fee` used to write `paid_amount` straight
		through, and the next save of the invoice -- an officer adding a remark
		would do it -- recomputed the figure from allocations alone and silently
		put the invoice back to Unpaid.
		"""
		if self.is_new():
			return flt(self.direct_paid_amount)
		rows = frappe.get_all(
			"Payment Allocation",
			filters={"fee_invoice": self.name, "parenttype": "Payment Entry", "docstatus": ("<", 2)},
			fields=["allocated_amount"],
		)
		allocated = sum(flt(r.allocated_amount) for r in rows)
		return flt(allocated + flt(self.direct_paid_amount), 2)

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

		# db_set does not run on_update, and payment almost always arrives as a
		# Payment Entry allocation rather than a save -- so the course would
		# never open if this were left to the doc hook alone.
		from sibbcs.finance.hooks_handlers import open_course_when_fee_settled

		open_course_when_fee_settled(self)


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
